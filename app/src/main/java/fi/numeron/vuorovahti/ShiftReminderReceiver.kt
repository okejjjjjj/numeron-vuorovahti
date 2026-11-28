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

            if (action == ACTION_FORGOTTEN_STAMP_CHECK) {
                val appCtx = context.applicationContext
                val prefs = appCtx.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                if (!prefs.getBoolean("forgotten_stamp_guard_enabled", true) || DemoModeHelper.isDemoEnabled(appCtx)) {
                    return
                }
                val title = intent.getStringExtra("SHIFT_TITLE") ?: if (DemoModeHelper.isEnglish(appCtx)) "Work Shift" else "Työvuoro"
                val timeStr = intent.getStringExtra("SHIFT_TIME") ?: ""
                val isEnding = intent.getBooleanExtra("IS_ENDING", false)

                val pendingResult = goAsync()
                CoroutineScope(Dispatchers.IO).launch {
                    try {
                        if (BackgroundAuthHelper.isCredentialBlocked(appCtx)) return@launch
                        val state = kotlinx.coroutines.withTimeoutOrNull(12_000L) {
                            NumeronApiClient.fetchStampingState(appCtx, forceRefreshSession = false)
                        } ?: return@launch
                        ShiftWidgetProvider.updateAllWidgets(appCtx)
                        QuickStampTileService.requestTileUpdate(appCtx)

                        val missedIn = !isEnding && state.nextDirection.equals("IN", ignoreCase = true)
                        val missedOut = isEnding && state.nextDirection.equals("OUT", ignoreCase = true)
                        if (missedIn || missedOut) {
                            ShiftReminderReceiver().showForgottenStampGuardNotification(
                                context = appCtx,
                                shiftTitle = title,
                                timeStr = timeStr,
                                isEnding = isEnding
                            )
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

    fun showForgottenStampGuardNotification(
        context: Context,
        shiftTitle: String,
        timeStr: String,
        isEnding: Boolean
    ) {
        if (!canPostNotifications(context)) return
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channelId = "numeron_vuorovahti_reminders"

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(
                NotificationChannel(
                    channelId,
                    "Työvuoro- ja kalenteri-ilmoitukset",
                    NotificationManager.IMPORTANCE_HIGH
                )
            )
        }

        val en = DemoModeHelper.isEnglish(context)
        val notifId = if (isEnding) NOTIF_ID_FORGOTTEN_GUARD_OUT else NOTIF_ID_FORGOTTEN_GUARD_IN
        val contentTitle = if (en) {
            if (isEnding) "⚠ Forgot to clock out? ($timeStr)" else "⚠ Forgot to clock in? ($timeStr)"
        } else {
            if (isEnding) "⚠ Unohditko leimata ulos? ($timeStr)" else "⚠ Unohditko leimata sisään? ($timeStr)"
        }
        val subtitleText = if (en) {
            if (isEnding) "Still clocked in • $shiftTitle" else "Not clocked in yet • $shiftTitle"
        } else {
            if (isEnding) "Olet yhä leimattuna sisään • $shiftTitle" else "Sisäänleimaus puuttuu • $shiftTitle"
        }
        val fullButtonLabel = if (en) {
            if (isEnding) "CLOCK OUT NOW" else "CLOCK IN NOW"
        } else {
            if (isEnding) "LEIMAA ULOS NYT" else "LEIMAA SISÄÄN NYT"
        }
        val shortButtonLabel = if (en) {
            if (isEnding) "OUT" else "IN"
        } else {
            if (isEnding) "ULOS" else "SISÄÄN"
        }
        val btnBgRes = if (isEnding) R.drawable.bg_notif_btn_out else R.drawable.bg_notif_btn_in

        val stampIntent = Intent(context, QuickStampActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("AUTO_STAMP", true)
            putExtra("IS_ENDING", isEnding)
            putExtra("IS_TEST", false)
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
            setTextViewText(R.id.notifSubtitleCollapsed, subtitleText)
            setTextViewText(R.id.btnNotifStampCollapsed, shortButtonLabel)
            setInt(R.id.btnNotifStampCollapsed, "setBackgroundResource", btnBgRes)
            setOnClickPendingIntent(R.id.btnNotifStampCollapsed, stampPi)
        }

        val expandedView = RemoteViews(context.packageName, R.layout.notification_stamp_expanded).apply {
            setTextViewText(R.id.notifTitle, contentTitle)
            setTextViewText(R.id.notifSubtitle, subtitleText)
            setTextViewText(R.id.btnNotifStamp, fullButtonLabel)
            setInt(R.id.btnNotifStamp, "setBackgroundResource", btnBgRes)
            setOnClickPendingIntent(R.id.btnNotifStamp, stampPi)
        }

        val notification = NotificationCompat.Builder(context, channelId)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle(contentTitle)
            .setContentText(subtitleText)
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
        const val ACTION_FORGOTTEN_STAMP_CHECK = "fi.numeron.vuorovahti.ACTION_FORGOTTEN_STAMP_CHECK"
        const val ACTION_REVERT_ALL_CALENDAR_CHANGES = "fi.numeron.vuorovahti.ACTION_REVERT_ALL_CALENDAR_CHANGES"
        const val NOTIF_ID_FORGOTTEN_GUARD_IN = 3001
        const val NOTIF_ID_FORGOTTEN_GUARD_OUT = 3002
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

        suspend fun syncRequestsAndNotify(context: Context, baseUrl: String): Int {
            if (baseUrl.isBlank()) return 0
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val result = NumeronApiClient.fetchRequests(context, "active")
            val items = result.items
            if (items == null || result.fromCache) {
                prefs.edit()
                    .putString("last_requests_check_status", if (result.fromCache) "CACHE_ONLY" else "FETCH_FAILED")
                    .apply()
                return 0
            }
            return checkRequestUpdates(context, items)
        }

        private fun checkRequestUpdates(context: Context, items: List<PersonRequestItem>): Int {
            var sentCount = 0
            try {
                val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                val notifiedIds = prefs.getStringSet("notified_request_ids", emptySet())?.toMutableSet() ?: mutableSetOf()
                val baselineInitialized = prefs.getBoolean("requests_baseline_initialized", false) || notifiedIds.isNotEmpty()
                val nowMs = System.currentTimeMillis()
                val dateFmt = java.time.format.DateTimeFormatter.ofPattern("dd.MM.yyyy")
                val en = DemoModeHelper.isEnglish(context)
                var changed = false
                var processedFound = 0

                for (item in items) {
                    val statusId = item.statusCode
                    if (item.id > 0 && (statusId == 50 || statusId == 80 || statusId == 40)) {
                        processedFound++
                        val key = "${item.id}_$statusId"
                        if (!notifiedIds.contains(key)) {
                            notifiedIds.add(key)
                            changed = true
                            val approvedMs = item.approvedDateMs
                            val approvedRecently = approvedMs != null && (nowMs - approvedMs) in 0L..(24L * 60L * 60L * 1000L)
                            if (baselineInitialized || approvedRecently) {
                                val dateStr = item.dateFrom?.format(dateFmt).orEmpty()
                                val bodyText = if (dateStr.isNotEmpty()) "${item.type} ($dateStr)" else item.type
                                showRequestDecisionNotification(
                                    context,
                                    if (en) "Request processed: ${item.statusDescription}" else "Toive käsitelty: ${item.statusDescription}",
                                    bodyText,
                                    item.id
                                )
                                sentCount++
                            }
                        }
                    }
                }
                prefs.edit().apply {
                    putString("last_requests_check_status", "OK:${items.size}/$processedFound")
                    if (changed || !baselineInitialized) {
                        putStringSet("notified_request_ids", notifiedIds)
                        putBoolean("requests_baseline_initialized", true)
                    }
                }.apply()
            } catch (_: Exception) {
            }
            return sentCount
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
                val docs = pages.map { org.jsoup.Jsoup.parse(it) }
                val circleDates = mutableSetOf<LocalDate>()
                docs.forEach { doc ->
                    val displayData = NumeronParser.parseMonthForDisplayDoc(doc)
                    if (displayData != null) {
                        NumeronApiClient.saveMonthDisplayCache(appContext, displayData)
                        PeriodBalanceManager.recordMonthSnapshot(appContext, displayData)
                        displayData.days.values.forEach { day ->
                            if (day.hasCommentCircle) circleDates.add(day.date)
                        }
                    } else {
                        circleDates.addAll(NumeronParser.extractCircleDatesFromDoc(doc))
                    }
                }
                val parsed = docs.map { NumeronParser.parseCalendarDoc(it) }
                if (parsed.any { it == null }) {
                    null
                } else {
                    val cookies = SessionCookieStore.getCookieHeader(appContext, baseUrl)
                    val enriched = NumeronParser.enrichShiftsWithListCommentsFromCircleDates(
                        baseUrl = baseUrl,
                        cookieHeader = cookies,
                        circleDates = circleDates,
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
            ShiftWidgetProvider.updateAllWidgets(appContext)
            QuickStampTileService.requestTileUpdate(appContext)
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
