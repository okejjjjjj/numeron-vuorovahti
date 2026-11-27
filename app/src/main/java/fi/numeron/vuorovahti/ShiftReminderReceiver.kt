package fi.numeron.vuorovahti

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.webkit.CookieManager
import android.widget.RemoteViews
import android.widget.Toast
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.NetworkType
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.time.LocalDate
import java.util.concurrent.TimeUnit

class ShiftReminderReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        if (action == Intent.ACTION_BOOT_COMPLETED || action == Intent.ACTION_MY_PACKAGE_REPLACED) {
            CalendarSyncHelper.scheduleShiftReminders(context)
            ensureBackgroundSyncScheduled(context)
        }
    }

    class InternalReceiver : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val action = intent.action

            if (action == ACTION_REVERT_ALL_CALENDAR_CHANGES) {
                val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                nm.cancel(NOTIF_ID_CALENDAR_CHANGES)
                val appCtx = context.applicationContext
                val pendingResult = goAsync()
                CoroutineScope(Dispatchers.IO).launch {
                    try {
                        val count = CalendarChangeTracker.revertAllChanges(appCtx)
                        val en = DemoModeHelper.isEnglish(appCtx)
                        withContext(Dispatchers.Main) {
                            val msg = if (en) "Reverted $count calendar changes" else "Peruttu $count kalenterimuutosta"
                            Toast.makeText(appCtx, msg, Toast.LENGTH_LONG).show()
                        }
                    } finally {
                        pendingResult.finish()
                    }
                }
                return
            }

            if (action != ACTION_SHIFT_REMINDER) return

            val title = intent.getStringExtra("SHIFT_TITLE") ?: if (DemoModeHelper.isEnglish(context)) "Work Shift" else "Työvuoro"
            val timeStr = intent.getStringExtra("SHIFT_TIME") ?: ""
            val isEnding = intent.getBooleanExtra("IS_ENDING", false)
            val shiftStartMs = intent.getLongExtra("SHIFT_START_MS", 0L)

            if (!isEnding && shiftStartMs > 0L) {
                context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                    .edit()
                    .putLong("notified_ongoing_start_ms", shiftStartMs)
                    .apply()
            }

            ShiftReminderReceiver().showReminderNotification(context, title, timeStr, isEnding)

            val appCtx = context.applicationContext
            val pendingResult = goAsync()
            CoroutineScope(Dispatchers.IO).launch {
                try {
                    kotlinx.coroutines.withTimeoutOrNull(7_000L) {
                        BackgroundAuthHelper.ensureAuthenticatedSession(appCtx)
                    }
                } finally {
                    pendingResult.finish()
                }
            }
        }
    }

    fun showReminderNotification(
        context: Context,
        shiftTitle: String,
        timeStr: String,
        isEnding: Boolean,
        isTest: Boolean = false,
        rescheduleNext: Boolean = true
    ) {
        if (!canPostNotifications(context)) {
            if (!isTest && rescheduleNext) {
                CalendarSyncHelper.scheduleShiftReminders(context)
            }
            return
        }

        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channelId = "numeron_vuorovahti_reminders"

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "Työvuoro- ja kalenteri-ilmoitukset",
                NotificationManager.IMPORTANCE_HIGH
            )
            nm.createNotificationChannel(channel)
        }

        val en = DemoModeHelper.isEnglish(context)
        val notifId = when {
            isTest -> 2999
            isEnding -> 2002
            else -> 1001
        }
        val fullButtonLabel = if (isTest) {
            if (en) "TEST (NO STAMP)" else "TESTI (EI LEIMAA)"
        } else if (en) {
            if (isEnding) "CLOCK OUT" else "CLOCK IN"
        } else {
            if (isEnding) "LEIMAA ULOS" else "LEIMAA SISÄÄN"
        }
        val shortButtonLabel = if (isTest) {
            if (en) "TEST" else "TESTI"
        } else if (en) {
            if (isEnding) "OUT" else "IN"
        } else {
            if (isEnding) "ULOS" else "SISÄÄN"
        }
        val contentTitle = if (en) {
            if (isEnding) "Shift ends at $timeStr" else "Shift starts at $timeStr"
        } else {
            if (isEnding) "Vuoro päättyy klo $timeStr" else "Vuoro alkaa klo $timeStr"
        }
        val btnBgRes = if (isEnding) R.drawable.bg_notif_btn_out else R.drawable.bg_notif_btn_in

        val dirTag = if (en) {
            if (isEnding) "Out" else "In"
        } else {
            if (isEnding) "Ulos" else "Sisään"
        }
        val testSuffix = if (isTest) (if (en) " [Test]" else " [Testi]") else ""
        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putLong("last_reminder_sent_ms", System.currentTimeMillis())
            .putString("last_reminder_sent_label", "$dirTag – $shiftTitle$testSuffix")
            .apply()

        if (!isTest && rescheduleNext) {
            CalendarSyncHelper.scheduleShiftReminders(context)
        }

        val stampIntent = Intent(context, QuickStampActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("AUTO_STAMP", true)
            putExtra("IS_ENDING", isEnding)
            putExtra("IS_TEST", isTest)
            putExtra("NOTIF_ID", notifId)
        }
        val stampPi = PendingIntent.getActivity(
            context,
            notifId,
            stampIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val openAppIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val openAppPi = PendingIntent.getActivity(
            context,
            notifId + 10,
            openAppIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val collapsedView = RemoteViews(context.packageName, R.layout.notification_stamp_collapsed).apply {
            setTextViewText(R.id.notifTitleCollapsed, contentTitle)
            setTextViewText(R.id.notifSubtitleCollapsed, shiftTitle)
            setTextViewText(R.id.btnNotifStampCollapsed, shortButtonLabel)
            setInt(R.id.btnNotifStampCollapsed, "setBackgroundResource", btnBgRes)
            setOnClickPendingIntent(R.id.btnNotifStampCollapsed, stampPi)
        }

        val expandedView = RemoteViews(context.packageName, R.layout.notification_stamp_expanded).apply {
            setTextViewText(R.id.notifTitle, contentTitle)
            setTextViewText(R.id.notifSubtitle, shiftTitle)
            setTextViewText(R.id.btnNotifStamp, fullButtonLabel)
            setInt(R.id.btnNotifStamp, "setBackgroundResource", btnBgRes)
            setOnClickPendingIntent(R.id.btnNotifStamp, stampPi)
        }

        val notification = NotificationCompat.Builder(context, channelId)
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle(contentTitle)
            .setContentText(shiftTitle)
            .setStyle(NotificationCompat.DecoratedCustomViewStyle())
            .setCustomContentView(collapsedView)
            .setCustomBigContentView(expandedView)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(openAppPi)
            .build()

        nm.notify(notifId, notification)
    }

    companion object {
        const val ACTION_SHIFT_REMINDER = "fi.numeron.vuorovahti.ACTION_SHIFT_REMINDER"
        const val ACTION_REVERT_ALL_CALENDAR_CHANGES = "fi.numeron.vuorovahti.ACTION_REVERT_ALL_CALENDAR_CHANGES"
        const val NOTIF_ID_CALENDAR_CHANGES = 4001

        fun canPostNotifications(context: Context): Boolean {
            val hasPerm = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
                ContextCompat.checkSelfPermission(
                    context,
                    Manifest.permission.POST_NOTIFICATIONS
                ) == PackageManager.PERMISSION_GRANTED
            return hasPerm && NotificationManagerCompat.from(context).areNotificationsEnabled()
        }

        fun showCalendarChangesNotification(context: Context, changes: List<CalendarChangeItem>) {
            if (changes.isEmpty() || !canPostNotifications(context)) return
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val channelId = "numeron_vuorovahti_reminders"

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                nm.createNotificationChannel(
                    NotificationChannel(channelId, "Työvuoro- ja kalenteri-ilmoitukset", NotificationManager.IMPORTANCE_HIGH)
                )
            }

            val en = DemoModeHelper.isEnglish(context)
            val summary = CalendarChangeTracker.formatSummary(changes)
            val shownItems = changes.take(6).map { CalendarChangeTracker.formatNotificationLine(it) }.toMutableList()
            if (changes.size > 6) {
                shownItems.add(
                    if (en) "...and ${changes.size - 6} more changes" else "...ja ${changes.size - 6} muuta muutosta"
                )
            }
            val detailsLines = shownItems.joinToString("\n")
            val collapsedText = shownItems.firstOrNull()
                ?: if (en) "Tap to edit or undo individual changes" else "Napauta muokataksesi tai peruaksesi yksittäisiä muutoksia"

            // Avaa sovelluksessa suoraan muutosten muokkaus- ja perumisikkunan
            val manageIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra("OPEN_CALENDAR_CHANGES", true)
            }
            val managePi = PendingIntent.getActivity(
                context,
                NOTIF_ID_CALENDAR_CHANGES,
                manageIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            // Suora pikatoiminto ilmoituksesta: Peru kaikki muutokset
            val revertAllIntent = Intent(context, InternalReceiver::class.java).apply {
                action = ACTION_REVERT_ALL_CALENDAR_CHANGES
            }
            val revertAllPi = PendingIntent.getBroadcast(
                context,
                NOTIF_ID_CALENDAR_CHANGES + 1,
                revertAllIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            val notification = NotificationCompat.Builder(context, channelId)
                .setSmallIcon(android.R.drawable.ic_menu_my_calendar)
                .setContentTitle(
                    if (en) "Google Calendar updated ($summary)" else "Google-kalenteria päivitetty ($summary)"
                )
                .setContentText(collapsedText)
                .setStyle(NotificationCompat.BigTextStyle().bigText(detailsLines))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .setContentIntent(managePi)
                .addAction(android.R.drawable.ic_menu_edit, if (en) "Edit / Undo" else "Muokkaa / Peru", managePi)
                .addAction(android.R.drawable.ic_menu_revert, if (en) "Undo all" else "Peru kaikki", revertAllPi)
                .build()

            nm.notify(NOTIF_ID_CALENDAR_CHANGES, notification)
        }

        fun computeNextOfficeHourSyncMs(nowMs: Long = System.currentTimeMillis()): Long {
            val zone = java.time.ZoneId.systemDefault()
            val now = java.time.Instant.ofEpochMilli(nowMs).atZone(zone).toLocalDateTime()
            val baseDate = now.toLocalDate()
            val minAllowed = now.plusMinutes(5)
            val windows = listOf(
                Pair(java.time.LocalTime.of(10, 15), java.time.LocalTime.of(11, 0)),
                Pair(java.time.LocalTime.of(14, 30), java.time.LocalTime.of(15, 0))
            )

            for (dayOffset in 0..7) {
                val date = baseDate.plusDays(dayOffset.toLong())
                val dow = date.dayOfWeek
                if (dow == java.time.DayOfWeek.SATURDAY || dow == java.time.DayOfWeek.SUNDAY) continue
                for ((startTime, endTime) in windows) {
                    val windowStart = java.time.LocalDateTime.of(date, startTime)
                    if (dayOffset == 0 && !now.isBefore(windowStart)) continue

                    val windowEnd = java.time.LocalDateTime.of(date, endTime)
                    val earliest = if (minAllowed.isAfter(windowStart)) minAllowed else windowStart
                    val spanSeconds = java.time.Duration.between(earliest, windowEnd).seconds.coerceAtLeast(0L)
                    val randomOffsetSec = if (spanSeconds > 0L) {
                        kotlin.random.Random.nextLong(0L, spanSeconds + 1L)
                    } else {
                        0L
                    }
                    val candidate = earliest.plusSeconds(randomOffsetSec)
                    return candidate.atZone(zone).toInstant().toEpochMilli()
                }
            }
            return nowMs + TimeUnit.HOURS.toMillis(12)
        }

        fun ensureBackgroundSyncScheduled(context: Context, forceReplace: Boolean = false) {
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val syncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
            val shiftReminders = prefs.getBoolean("shift_reminders_enabled", true)
            val trackRequests = prefs.getBoolean("track_requests", true)

            if (!syncCalendar && !shiftReminders && !trackRequests) {
                WorkManager.getInstance(context).cancelUniqueWork("NumeronVuorovahtiSync")
                prefs.edit().remove("next_calendar_sync_ms").apply()
                return
            }

            val nowMs = System.currentTimeMillis()
            val nextTargetMs = computeNextOfficeHourSyncMs(nowMs)
            val delayMs = (nextTargetMs - nowMs).coerceAtLeast(60_000L)

            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val syncRequest = androidx.work.OneTimeWorkRequestBuilder<BackgroundSyncWorker>()
                .setInitialDelay(delayMs, TimeUnit.MILLISECONDS)
                .setConstraints(constraints)
                .build()

            val policy = if (forceReplace) {
                androidx.work.ExistingWorkPolicy.REPLACE
            } else {
                androidx.work.ExistingWorkPolicy.KEEP
            }

            WorkManager.getInstance(context).enqueueUniqueWork(
                "NumeronVuorovahtiSync",
                policy,
                syncRequest
            )

            if (forceReplace || prefs.getLong("next_calendar_sync_ms", 0L) <= nowMs) {
                prefs.edit()
                    .putLong("next_calendar_sync_ms", nextTargetMs)
                    .apply()
            }
        }

        fun triggerImmediateSync(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val immediateRequest = androidx.work.OneTimeWorkRequestBuilder<BackgroundSyncWorker>()
                .setConstraints(constraints)
                .build()

            WorkManager.getInstance(context).enqueueUniqueWork(
                "NumeronVuorovahtiImmediateSync",
                androidx.work.ExistingWorkPolicy.REPLACE,
                immediateRequest
            )
        }

        fun showRequestDecisionNotification(context: Context, title: String, body: String, id: Int) {
            if (!canPostNotifications(context)) return
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val channelId = "numeron_vuorovahti_reminders"
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                nm.createNotificationChannel(
                    NotificationChannel(channelId, "Työvuoro- ja kalenteri-ilmoitukset", NotificationManager.IMPORTANCE_HIGH)
                )
            }
            val openIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra("OPEN_REQUESTS", true)
            }
            val notifId = 100_000 + (id and 0x7FFF)
            val pi = PendingIntent.getActivity(
                context, notifId, openIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            val notif = NotificationCompat.Builder(context, channelId)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(title)
                .setContentText(body)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .setContentIntent(pi)
                .build()
            nm.notify(notifId, notif)
        }

        fun syncRequestsAndNotify(context: Context, baseUrl: String): Int {
            if (baseUrl.isBlank()) return 0
            val jsonStr = fetchRequestsJson(context, baseUrl) ?: return 0
            return checkRequestUpdates(context, jsonStr)
        }

        private fun fetchRequestsJson(context: Context, baseUrl: String): String? {
            var conn: java.net.HttpURLConnection? = null
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            return try {
                val cookies = CookieManager.getInstance().getCookie(baseUrl)
                if (cookies.isNullOrBlank()) {
                    prefs.edit().putString("last_requests_check_status", "NO_COOKIES").apply()
                    return null
                }
                conn = (java.net.URL("$baseUrl/PersonRequests/Read?selectedFilter=active").openConnection() as java.net.HttpURLConnection).apply {
                    requestMethod = "POST"
                    instanceFollowRedirects = false
                    setRequestProperty("Cookie", cookies)
                    setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
                    setRequestProperty("Accept", "application/json, text/javascript, */*; q=0.01")
                    setRequestProperty("X-Requested-With", "XMLHttpRequest")
                    setRequestProperty(
                        "User-Agent",
                        "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
                    )
                    doOutput = true
                    connectTimeout = 15000
                    readTimeout = 15000
                }
                java.io.OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { writer ->
                    writer.write("sort=&page=1&pageSize=100&group=&filter=&selectedFilter=active")
                    writer.flush()
                }
                val code = conn.responseCode
                val text = if (code == 200) {
                    conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
                } else {
                    null
                }
                if (text != null && text.trim().startsWith("{")) {
                    text
                } else {
                    prefs.edit().putString("last_requests_check_status", "HTTP_$code").apply()
                    null
                }
            } catch (e: Exception) {
                prefs.edit().putString("last_requests_check_status", "ERR:${e.javaClass.simpleName}").apply()
                null
            } finally {
                conn?.disconnect()
            }
        }

        private fun resolveRequestStatusCode(rawStatus: Int, statusDesc: String): Int {
            if (rawStatus == 40 || rawStatus == 50 || rawStatus == 80) return rawStatus
            val lower = statusDesc.trim().lowercase()
            if (lower.isEmpty()) return rawStatus
            return when {
                lower.contains("odottaa") || lower.contains("pending") || lower.contains("waiting") || lower.contains("väntar") -> 10
                lower.contains("osittain") || lower.contains("partial") || lower.contains("delvis") -> 40
                lower.contains("hylätty") || lower.contains("reject") || lower.contains("denied") || lower.contains("avslag") -> 80
                lower.contains("hyväksytty") || lower.contains("approved") || lower.contains("godkänd") -> 50
                else -> rawStatus
            }
        }

        private fun fallbackStatusLabel(statusId: Int, en: Boolean): String = when (statusId) {
            40 -> if (en) "Partially approved" else "Osittain hyväksytty"
            50 -> if (en) "Approved" else "Hyväksytty"
            80 -> if (en) "Rejected" else "Hylätty"
            else -> ""
        }

        private fun checkRequestUpdates(context: Context, jsonStr: String): Int {
            var sentCount = 0
            try {
                val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                val baselineInitialized = prefs.getBoolean("requests_baseline_initialized", false)
                val notifiedIds = prefs.getStringSet("notified_request_ids", emptySet())?.toMutableSet() ?: mutableSetOf()
                var changed = false
                var processedFound = 0

                val root = JSONObject(jsonStr)
                val dataArray = root.optJSONArray("data") ?: root.optJSONArray("Data") ?: return 0
                val en = DemoModeHelper.isEnglish(context)

                for (i in 0 until dataArray.length()) {
                    val item = dataArray.optJSONObject(i) ?: continue
                    val id = item.optInt("Id", -1).let { if (it > 0) it else item.optInt("RowId", -1) }
                    val rawStatus = item.optInt("Status", -1).let { if (it > 0) it else item.optInt("StatusId", -1) }
                    val typeName = item.optString("Type", if (en) "Request" else "Toive")
                    val rawDesc = item.optString("StatusDescription", "").trim()
                    val statusId = resolveRequestStatusCode(rawStatus, rawDesc)
                    val statusDesc = rawDesc.ifEmpty { fallbackStatusLabel(statusId, en) }
                    val dateStr = formatRequestDate(item.optString("DateFrom", ""))
                    val bodyText = if (dateStr.isNotEmpty()) "$typeName ($dateStr)" else typeName

                    if (id > 0 && (statusId == 50 || statusId == 80 || statusId == 40)) {
                        processedFound++
                        val key = "${id}_$statusId"
                        if (!notifiedIds.contains(key)) {
                            notifiedIds.add(key)
                            changed = true
                            if (baselineInitialized) {
                                showRequestDecisionNotification(
                                    context,
                                    if (en) "Request processed: $statusDesc" else "Toive käsitelty: $statusDesc",
                                    bodyText,
                                    id
                                )
                                sentCount++
                            }
                        }
                    }
                }
                prefs.edit().apply {
                    putString("last_requests_check_status", "OK:${dataArray.length()}/$processedFound")
                    if (changed || !baselineInitialized) {
                        putStringSet("notified_request_ids", notifiedIds)
                        putBoolean("requests_baseline_initialized", true)
                    }
                }.apply()
            } catch (_: Exception) {
            }
            return sentCount
        }

        private fun formatRequestDate(raw: String): String {
            val trimmed = raw.trim()
            if (trimmed.isEmpty() || trimmed.equals("null", ignoreCase = true)) return ""
            val fmt = java.time.format.DateTimeFormatter.ofPattern("dd.MM.yyyy")
            val msMatch = Regex("/Date\\((-?\\d+)\\)/").find(trimmed)
            if (msMatch != null) {
                val ms = msMatch.groupValues[1].toLongOrNull() ?: return ""
                return java.time.Instant.ofEpochMilli(ms)
                    .atZone(java.time.ZoneId.systemDefault())
                    .toLocalDate()
                    .format(fmt)
            }
            val isoMatch = Regex("^(\\d{4}-\\d{2}-\\d{2})").find(trimmed)
            if (isoMatch != null) {
                return try {
                    LocalDate.parse(isoMatch.groupValues[1]).format(fmt)
                } catch (_: Exception) {
                    ""
                }
            }
            val fiMatch = Regex("^\\d{1,2}\\.\\d{1,2}\\.\\d{4}").find(trimmed)
            return fiMatch?.value ?: ""
        }
    }
}

class BackgroundSyncWorker(
    private val appContext: Context,
    params: WorkerParameters
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        if (DemoModeHelper.isDemoEnabled(appContext)) {
            return@withContext Result.success()
        }

        val prefs = appContext.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val rawUser = SecureCredentialManager.getUsername(appContext) ?: ""
        val rawPass = SecureCredentialManager.getPassword(appContext) ?: ""
        val baseUrl = UrlNormalizer.getSavedBaseUrl(appContext)
        val syncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
        val shiftReminders = prefs.getBoolean("shift_reminders_enabled", true)
        val trackRequests = prefs.getBoolean("track_requests", true)

        if (!syncCalendar && !shiftReminders && !trackRequests) {
            ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext)
            return@withContext Result.success()
        }

        if (rawUser.isEmpty() || rawPass.isEmpty() || baseUrl.isEmpty()) {
            return@withContext Result.failure()
        }

        val needShifts = syncCalendar || shiftReminders
        val calId = if (syncCalendar) CalendarSyncHelper.getTargetCalendarId(appContext) else null

        val now = LocalDate.now()
        val nextMonth = now.plusMonths(1)
        val currentMonthUrl = "$baseUrl/Calendar/Month?month=${now.monthValue}&year=${now.year}"
        val nextMonthUrl = "$baseUrl/Calendar/Month?month=${nextMonth.monthValue}&year=${nextMonth.year}"

        val parsedShifts: List<WorkShift>? = if (needShifts) {
            val pages = BackgroundAuthHelper.fetchAuthenticatedPages(
                appContext,
                listOf(currentMonthUrl, nextMonthUrl)
            )
            if (pages == null || pages.size < 2) {
                null
            } else {
                val parsed = pages.map { NumeronParser.parseCalendarHtml(it) }
                if (parsed.any { it == null }) {
                    null
                } else {
                    val cookies = try {
                        CookieManager.getInstance().getCookie(baseUrl)
                    } catch (_: Exception) {
                        null
                    }
                    val enriched = NumeronParser.enrichShiftsWithListComments(
                        baseUrl = baseUrl,
                        cookieHeader = cookies,
                        htmlPages = pages,
                        shifts = parsed.filterNotNull().flatten()
                    )
                    NumeronParser.mergeConsecutiveLeaves(enriched)
                }
            }
        } else {
            if (BackgroundAuthHelper.ensureAuthenticatedSession(appContext)) emptyList() else null
        }

        if (parsedShifts != null) {
            val detectedChanges = if (needShifts) {
                CalendarSyncHelper.saveCachedShifts(appContext, parsedShifts)
                val calChanges = if (syncCalendar && calId != null) {
                    CalendarSyncHelper.syncShiftsToCalendar(appContext, calId, parsedShifts)
                } else {
                    prefs.edit().putLong("last_calendar_sync_ms", System.currentTimeMillis()).apply()
                    emptyList()
                }
                CalendarSyncHelper.scheduleShiftReminders(appContext, calId)
                calChanges
            } else {
                CalendarSyncHelper.scheduleShiftReminders(appContext, calId)
                emptyList()
            }

            if (trackRequests) {
                ShiftReminderReceiver.syncRequestsAndNotify(appContext, baseUrl)
            }

            if (detectedChanges.isNotEmpty()) {
                ShiftReminderReceiver.showCalendarChangesNotification(appContext, detectedChanges)
            }
            prefs.edit()
                .putLong("last_valid_session_ms", System.currentTimeMillis())
                .apply()
            ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext, forceReplace = true)
            Result.success()
        } else {
            if (runAttemptCount >= 3) {
                ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext, forceReplace = true)
                Result.failure()
            } else {
                Result.retry()
            }
        }
    }
}
