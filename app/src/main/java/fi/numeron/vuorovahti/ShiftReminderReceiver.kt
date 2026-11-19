package fi.numeron.vuorovahti

import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.RemoteViews
import android.widget.Toast
import androidx.core.app.NotificationCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.json.JSONTokener
import java.time.LocalDate
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume

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
                        withContext(Dispatchers.Main) {
                            Toast.makeText(appCtx, "Peruttu $count kalenterimuutosta", Toast.LENGTH_LONG).show()
                        }
                    } finally {
                        pendingResult.finish()
                    }
                }
                return
            }

            if (action != ACTION_SHIFT_REMINDER) return

            val title = intent.getStringExtra("SHIFT_TITLE") ?: "Työvuoro"
            val timeStr = intent.getStringExtra("SHIFT_TIME") ?: ""
            val isEnding = intent.getBooleanExtra("IS_ENDING", false)

            ShiftReminderReceiver().showReminderNotification(context, title, timeStr, isEnding)

            val appCtx = context.applicationContext
            val pendingResult = goAsync()
            CoroutineScope(Dispatchers.IO).launch {
                try {
                    BackgroundAuthHelper.ensureAuthenticatedSession(appCtx)
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

        val notifId = if (isEnding) 2002 else 1001
        val fullButtonLabel = if (isEnding) "LEIMAA ULOS" else "LEIMAA SISÄÄN"
        val shortButtonLabel = if (isEnding) "ULOS" else "SISÄÄN"
        val contentTitle = if (isEnding) "Vuoro päättyy klo $timeStr" else "Vuoro alkaa klo $timeStr"
        val btnBgRes = if (isEnding) R.drawable.bg_notif_btn_out else R.drawable.bg_notif_btn_in

        val dirTag = if (isEnding) "Ulos" else "Sisään"
        val testSuffix = if (isTest) " [Testi]" else ""
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

        fun showCalendarChangesNotification(context: Context, changes: List<CalendarChangeItem>) {
            if (changes.isEmpty()) return
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val channelId = "numeron_vuorovahti_reminders"

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                nm.createNotificationChannel(
                    NotificationChannel(channelId, "Työvuoro- ja kalenteri-ilmoitukset", NotificationManager.IMPORTANCE_HIGH)
                )
            }

            val summary = CalendarChangeTracker.formatSummary(changes)
            val shownItems = changes.take(6).map { CalendarChangeTracker.formatNotificationLine(it) }.toMutableList()
            if (changes.size > 6) {
                shownItems.add("...ja ${changes.size - 6} muuta muutosta")
            }
            val detailsLines = shownItems.joinToString("\n")
            val collapsedText = shownItems.firstOrNull()
                ?: "Napauta muokataksesi tai peruaksesi yksittäisiä muutoksia"

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
                .setContentTitle("Google-kalenteria päivitetty ($summary)")
                .setContentText(collapsedText)
                .setStyle(NotificationCompat.BigTextStyle().bigText(detailsLines))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .setContentIntent(managePi)
                .addAction(android.R.drawable.ic_menu_edit, "Muokkaa / Peru", managePi)
                .addAction(android.R.drawable.ic_menu_revert, "Peru kaikki", revertAllPi)
                .build()

            nm.notify(NOTIF_ID_CALENDAR_CHANGES, notification)
        }

        fun computeNextOfficeHourSyncMs(nowMs: Long = System.currentTimeMillis()): Long {
            val zone = java.time.ZoneId.systemDefault()
            val now = java.time.Instant.ofEpochMilli(nowMs).atZone(zone).toLocalDateTime()
            val candidateDate = now.toLocalDate()
            val slots = listOf(java.time.LocalTime.of(9, 30), java.time.LocalTime.of(14, 30))

            for (dayOffset in 0..7) {
                val date = candidateDate.plusDays(dayOffset.toLong())
                val dow = date.dayOfWeek
                if (dow == java.time.DayOfWeek.SATURDAY || dow == java.time.DayOfWeek.SUNDAY) continue
                for (slot in slots) {
                    val candidate = java.time.LocalDateTime.of(date, slot)
                    if (candidate.isAfter(now.plusMinutes(5))) {
                        return candidate.atZone(zone).toInstant().toEpochMilli()
                    }
                }
            }
            return nowMs + TimeUnit.HOURS.toMillis(12)
        }

        fun ensureBackgroundSyncScheduled(context: Context) {
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

            WorkManager.getInstance(context).enqueueUniqueWork(
                "NumeronVuorovahtiSync",
                androidx.work.ExistingWorkPolicy.REPLACE,
                syncRequest
            )

            prefs.edit()
                .putLong("next_calendar_sync_ms", nextTargetMs)
                .apply()
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
            val pi = PendingIntent.getActivity(
                context, 3000 + id, openIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            val notif = NotificationCompat.Builder(context, channelId)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(title)
                .setContentText(body)
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                .setAutoCancel(true)
                .setContentIntent(pi)
                .build()
            nm.notify(3000 + id, notif)
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
                    NumeronParser.mergeConsecutiveLeaves(parsed.filterNotNull().flatten())
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
                fetchRequestsJson(baseUrl)?.let { checkRequestUpdates(it) }
            }

            if (detectedChanges.isNotEmpty()) {
                ShiftReminderReceiver.showCalendarChangesNotification(appContext, detectedChanges)
            }
            prefs.edit()
                .putLong("last_valid_session_ms", System.currentTimeMillis())
                .apply()
            ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext)
            Result.success()
        } else {
            Result.retry()
        }
    }

    private fun fetchRequestsJson(baseUrl: String): String? {
        return try {
            val cookies = CookieManager.getInstance().getCookie(baseUrl)
            if (cookies.isNullOrBlank()) return null
            val conn = (java.net.URL("$baseUrl/PersonRequests/Read?selectedFilter=active").openConnection() as java.net.HttpURLConnection).apply {
                requestMethod = "POST"
                setRequestProperty("Cookie", cookies)
                setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
                setRequestProperty("X-Requested-With", "XMLHttpRequest")
                doOutput = true
                connectTimeout = 15000
                readTimeout = 15000
            }
            java.io.OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { writer ->
                writer.write("page=1&pageSize=50")
                writer.flush()
            }
            val text = if (conn.responseCode == 200) {
                conn.inputStream.bufferedReader().use { it.readText() }
            } else {
                null
            }
            conn.disconnect()
            if (text != null && text.trim().startsWith("{")) text else null
        } catch (_: Exception) {
            null
        }
    }

    private fun checkRequestUpdates(jsonStr: String) {
        try {
            val prefs = appContext.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val notifiedIds = prefs.getStringSet("notified_request_ids", emptySet())?.toMutableSet() ?: mutableSetOf()
            var changed = false

            val root = JSONObject(jsonStr)
            val dataArray = root.optJSONArray("data") ?: return

            for (i in 0 until dataArray.length()) {
                val item = dataArray.optJSONObject(i) ?: continue
                val id = item.optInt("Id", -1)
                val statusId = item.optInt("Status", -1)
                val typeName = item.optString("Type", "Toive")
                val statusDesc = item.optString("StatusDescription", "")

                if (id > 0 && (statusId == 50 || statusId == 80 || statusId == 40)) {
                    val key = "${id}_$statusId"
                    if (!notifiedIds.contains(key)) {
                        notifiedIds.add(key)
                        changed = true
                        ShiftReminderReceiver.showRequestDecisionNotification(
                            appContext,
                            "Toive käsitelty: $statusDesc",
                            typeName,
                            id
                        )
                    }
                }
            }
            if (changed) {
                prefs.edit().putStringSet("notified_request_ids", notifiedIds).apply()
            }
        } catch (_: Exception) {
        }
    }
}
