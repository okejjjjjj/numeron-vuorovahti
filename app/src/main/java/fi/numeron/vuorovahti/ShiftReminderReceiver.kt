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
import android.widget.Toast
import androidx.core.app.NotificationCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
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

        // 1. Puhelin käynnistyi uudelleen TAI sovellus päivitettiin (MY_PACKAGE_REPLACED)
        if (action == Intent.ACTION_BOOT_COMPLETED || action == Intent.ACTION_MY_PACKAGE_REPLACED) {
            val calId = CalendarSyncHelper.getTargetCalendarId(context)
            if (calId != null) {
                CalendarSyncHelper.scheduleShiftReminders(context, calId)
            }
            ensureBackgroundSyncScheduled(context)
            return
        }

        // 2. Käyttäjä painoi ilmoituksen "Leimaa sisään/ulos" -painiketta
        if (action == ACTION_QUICK_STAMP) {
            val isEnding = intent.getBooleanExtra("IS_ENDING", false)
            val notifId = intent.getIntExtra("NOTIF_ID", 1001)
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.cancel(notifId)

            val launchIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra("AUTO_STAMP", true)
                putExtra("IS_ENDING", isEnding)
            }
            context.startActivity(launchIntent)
            return
        }

        // 3. Käyttäjä painoi kalenterimuutos-ilmoituksesta "Peru kaikki" suoraan ilmoituksesta
        if (action == ACTION_REVERT_ALL_CALENDAR_CHANGES) {
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.cancel(NOTIF_ID_CALENDAR_CHANGES)
            val count = CalendarChangeTracker.revertAllChanges(context)
            Toast.makeText(context, "Peruttu $count kalenterimuutosta", Toast.LENGTH_LONG).show()
            return
        }

        // 4. Ajastettu tai testattu työvuorohälytys laukesi
        val title = intent.getStringExtra("SHIFT_TITLE") ?: "Työvuoro"
        val timeStr = intent.getStringExtra("SHIFT_TIME") ?: ""
        val isEnding = intent.getBooleanExtra("IS_ENDING", false)

        showReminderNotification(context, title, timeStr, isEnding)
    }

    fun showReminderNotification(
        context: Context,
        shiftTitle: String,
        timeStr: String,
        isEnding: Boolean
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
        val buttonLabel = if (isEnding) "Leimaa ulos" else "Leimaa sisään"
        val contentTitle = if (isEnding) "Vuoro päättyy klo $timeStr" else "Vuoro alkaa klo $timeStr"

        val stampIntent = Intent(context, ShiftReminderReceiver::class.java).apply {
            action = ACTION_QUICK_STAMP
            putExtra("IS_ENDING", isEnding)
            putExtra("NOTIF_ID", notifId)
        }
        val stampPi = PendingIntent.getBroadcast(
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

        val notification = NotificationCompat.Builder(context, channelId)
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle(contentTitle)
            .setContentText(shiftTitle)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(openAppPi)
            .addAction(android.R.drawable.ic_menu_send, buttonLabel, stampPi)
            .build()

        nm.notify(notifId, notification)
    }

    companion object {
        const val ACTION_QUICK_STAMP = "fi.numeron.vuorovahti.ACTION_QUICK_STAMP"
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
            val detailsLines = changes.take(5).joinToString("\n") {
                val prefix = when (it.type) {
                    ChangeType.ADDED -> "+ "
                    ChangeType.MODIFIED -> "~ "
                    ChangeType.REMOVED -> "- "
                }
                "$prefix${it.title}"
            }

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
            val revertAllIntent = Intent(context, ShiftReminderReceiver::class.java).apply {
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
                .setContentText("Napauta muokataksesi tai peruaksesi yksittäisiä muutoksia")
                .setStyle(NotificationCompat.BigTextStyle().bigText(detailsLines))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .setContentIntent(managePi)
                .addAction(android.R.drawable.ic_menu_edit, "Muokkaa / Peru", managePi)
                .addAction(android.R.drawable.ic_menu_revert, "Peru kaikki", revertAllPi)
                .build()

            nm.notify(NOTIF_ID_CALENDAR_CHANGES, notification)
        }

        fun ensureBackgroundSyncScheduled(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val syncRequest = PeriodicWorkRequestBuilder<BackgroundSyncWorker>(12, TimeUnit.HOURS)
                .setConstraints(constraints)
                .build()

            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                "NumeronVuorovahtiSync",
                ExistingPeriodicWorkPolicy.KEEP,
                syncRequest
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
                putExtra("OPEN_REQUESTS", true)
            }
            val pi = PendingIntent.getActivity(
                context, id, openIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
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

    @SuppressLint("SetJavaScriptEnabled")
    override suspend fun doWork(): Result = withContext(Dispatchers.Main) {
        if (DemoModeHelper.isDemoEnabled(appContext)) {
            return@withContext Result.success()
        }

        val prefs = appContext.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val user = prefs.getString("username", "") ?: ""
        val pass = prefs.getString("password", "") ?: ""
        val baseUrl = prefs.getString("server_url", "https://numeronwfm.com")?.trimEnd('/') ?: "https://numeronwfm.com"
        val trackRequests = prefs.getBoolean("track_requests", true)

        if (user.isEmpty() || pass.isEmpty() || baseUrl.isEmpty()) return@withContext Result.failure()

        val calId = CalendarSyncHelper.getTargetCalendarId(appContext)
            ?: return@withContext Result.failure()

        val now = LocalDate.now()
        val nextMonth = now.plusMonths(1)
        val currentMonthUrl = "$baseUrl/Calendar/Month?month=${now.monthValue}&year=${now.year}"
        val nextMonthUrl = "$baseUrl/Calendar/Month?month=${nextMonth.monthValue}&year=${nextMonth.year}"

        data class SyncPayload(val htmlPages: List<String>, val requestsJson: String?)

        val payload = suspendCancellableCoroutine<SyncPayload> { continuation ->
            val collectedHtml = mutableListOf<String>()
            var requestsJsonResult: String? = null
            var step = 0

            val bgWebView = WebView(appContext).apply {
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
            }
            CookieManager.getInstance().setAcceptCookie(true)
            CookieManager.getInstance().setAcceptThirdPartyCookies(bgWebView, true)

            val timeoutHandler = Handler(Looper.getMainLooper())
            val timeoutRunnable = Runnable {
                bgWebView.destroy()
                if (continuation.isActive) continuation.resume(SyncPayload(collectedHtml, requestsJsonResult))
            }
            timeoutHandler.postDelayed(timeoutRunnable, 35_000L)

            bgWebView.webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    if (url == null) return
                    when {
                        url.contains("/Login/Login", ignoreCase = true) -> {
                            val jsLogin = """
                                (function() {
                                    var u = document.getElementById('Username');
                                    var p = document.getElementById('Password');
                                    var f = document.getElementById('LoginForm');
                                    if (u && p && f && u.value === '') {
                                        u.value = '$user';
                                        p.value = '$pass';
                                        f.submit();
                                    }
                                })();
                            """.trimIndent()
                            view?.evaluateJavascript(jsLogin, null)
                        }
                        url.contains("/Calendar/Month", ignoreCase = true) -> {
                            view?.postDelayed({
                                view.evaluateJavascript("document.documentElement.outerHTML") { rawHtml ->
                                    if (rawHtml != null && rawHtml != "null") {
                                        val unescaped = JSONTokener(rawHtml).nextValue() as? String
                                        if (unescaped != null) collectedHtml.add(unescaped)
                                    }

                                    if (step == 0) {
                                        step = 1
                                        view.loadUrl(nextMonthUrl)
                                    } else if (trackRequests) {
                                        val jsFetchRequests = """
                                            (function() {
                                                var xhr = new XMLHttpRequest();
                                                xhr.open('POST', '/PersonRequests/Read?selectedFilter=active', false);
                                                xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                                                xhr.send('page=1&pageSize=50');
                                                return xhr.responseText;
                                            })();
                                        """.trimIndent()
                                        view.evaluateJavascript(jsFetchRequests) { rawJson ->
                                            if (rawJson != null && rawJson != "null") {
                                                requestsJsonResult = JSONTokener(rawJson).nextValue() as? String
                                            }
                                            timeoutHandler.removeCallbacks(timeoutRunnable)
                                            bgWebView.destroy()
                                            if (continuation.isActive) {
                                                continuation.resume(SyncPayload(collectedHtml, requestsJsonResult))
                                            }
                                        }
                                    } else {
                                        timeoutHandler.removeCallbacks(timeoutRunnable)
                                        bgWebView.destroy()
                                        if (continuation.isActive) {
                                            continuation.resume(SyncPayload(collectedHtml, null))
                                        }
                                    }
                                }
                            }, 1200L)
                        }
                    }
                }
            }
            bgWebView.loadUrl(currentMonthUrl)
        }

        if (payload.htmlPages.isNotEmpty()) {
            withContext(Dispatchers.IO) {
                val allShifts = payload.htmlPages.flatMap { NumeronParser.parseCalendarHtml(it) }
                CalendarSyncHelper.syncShiftsToCalendar(appContext, calId, allShifts)
                payload.requestsJson?.let { checkRequestUpdates(it) }
            }
            CalendarSyncHelper.scheduleShiftReminders(appContext, calId)
            Result.success()
        } else {
            Result.retry()
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
