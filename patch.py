#!/usr/bin/env python3
import os
import re


# ==============================================================================
# PYSYVÄ OSIO: Versionumeron automaattinen nosto (+1)
# ==============================================================================
def bump_version_code():
    gradle_path = "app/build.gradle.kts"
    if not os.path.exists(gradle_path):
        print(f"Ohitetaan: {gradle_path} ei löytynyt.")
        return

    with open(gradle_path, "r", encoding="utf-8") as f:
        content = f.read()

    def increment(match):
        old_code = int(match.group(1))
        new_code = old_code + 1
        print(f"Päivitetään versionCode: {old_code} -> {new_code}")
        return f"versionCode = {new_code}"

    updated, count = re.subn(r"versionCode\s*=\s*(\d+)", increment, content, count=1)
    if count > 0:
        with open(gradle_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated)


# ==============================================================================
# === POISTETTAVA KORJAUSOSIO ALKAA (Poista kun muutokset on ajettu) ===
# ==============================================================================
def replace_idempotent(content: str, old: str, new: str, label: str) -> str:
    if new in content:
        return content
    if old not in content:
        raise RuntimeError(f"Hakulohkoa ei löytynyt ({label})")
    return content.replace(old, new, 1)


def apply_feature_updates():
    # --------------------------------------------------------------------------
    # 1. CalendarSyncHelper.kt
    # --------------------------------------------------------------------------
    sync_path = "app/src/main/java/fi/numeron/vuorovahti/CalendarSyncHelper.kt"
    with open(sync_path, "r", encoding="utf-8") as f:
        sync = f.read()
    orig_sync = sync

    sync = replace_idempotent(
        sync,
        """import androidx.core.content.ContextCompat
import java.time.Instant""",
        """import androidx.core.content.ContextCompat
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant""",
        "CalendarSyncHelper imports",
    )

    sync = replace_idempotent(
        sync,
        """    private fun isSameCalendarDay(ms1: Long, ms2: Long, isAllDay: Boolean): Boolean {
        val zone = if (isAllDay) ZoneOffset.UTC else ZoneId.systemDefault()
        val d1 = Instant.ofEpochMilli(ms1).atZone(zone).toLocalDate()
        val d2 = Instant.ofEpochMilli(ms2).atZone(zone).toLocalDate()
        return d1 == d2
    }

    fun scheduleShiftReminders(context: Context, calendarId: Long) {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return
        }
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val minutesBefore = prefs.getInt("reminder_minutes", 30)
        val userTag = getUserTag(context)

        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val now = System.currentTimeMillis()
        val twoWeeksAhead = now + 14L * 24 * 60 * 60 * 1000L
        val timeFmt = DateTimeFormatter.ofPattern("HH:mm")

        val projection = arrayOf(
            CalendarContract.Events.TITLE,
            CalendarContract.Events.DESCRIPTION,
            CalendarContract.Events.DTSTART,
            CalendarContract.Events.DTEND,
            CalendarContract.Events.ALL_DAY
        )
        val selection = "${CalendarContract.Events.CALENDAR_ID} = ? AND " +
                "${CalendarContract.Events.DESCRIPTION} LIKE ? AND " +
                "${CalendarContract.Events.DTEND} > ? AND " +
                "${CalendarContract.Events.DTSTART} < ? AND " +
                "${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(calendarId.toString(), "%$EVENT_DESCRIPTION_TAG%", now.toString(), twoWeeksAhead.toString())

        val userShifts = mutableListOf<ReminderEventItem>()

        context.contentResolver.query(
            CalendarContract.Events.CONTENT_URI,
            projection,
            selection,
            selectionArgs,
            "${CalendarContract.Events.DTSTART} ASC"
        )?.use { cursor ->
            while (cursor.moveToNext()) {
                val baseTitle = cursor.getString(0) ?: continue
                val desc = cursor.getString(1) ?: ""
                val startMs = cursor.getLong(2)
                val endMs = cursor.getLong(3)
                val isAllDay = cursor.getInt(4) == 1

                if (isAllDay) continue
                if (!belongsToCurrentUser(desc, baseTitle, userTag)) continue

                val shiftRoleInfo = desc.substringBefore(EVENT_DESCRIPTION_TAG).trim()
                val displayTitle = if (shiftRoleInfo.isNotEmpty()) "$baseTitle ($shiftRoleInfo)" else baseTitle
                userShifts.add(ReminderEventItem(displayTitle, startMs, endMs))
            }
        }""",
        """    private fun isSameCalendarDay(ms1: Long, ms2: Long, isAllDay: Boolean): Boolean {
        val zone = if (isAllDay) ZoneOffset.UTC else ZoneId.systemDefault()
        val d1 = Instant.ofEpochMilli(ms1).atZone(zone).toLocalDate()
        val d2 = Instant.ofEpochMilli(ms2).atZone(zone).toLocalDate()
        return d1 == d2
    }

    fun saveCachedShifts(context: Context, shifts: List<WorkShift>) {
        val zone = ZoneId.systemDefault()
        val arr = JSONArray()
        for (shift in shifts) {
            val obj = JSONObject().apply {
                put("title", shift.title)
                put("startMs", shift.start.atZone(zone).toInstant().toEpochMilli())
                put("endMs", shift.end.atZone(zone).toInstant().toEpochMilli())
                put("isAllDayLeave", shift.isAllDayLeave)
                put("location", shift.location)
                put("description", shift.description)
            }
            arr.put(obj)
        }
        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putString("cached_work_shifts_json", arr.toString())
            .apply()
    }

    fun hasCachedShifts(context: Context): Boolean {
        val raw = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .getString("cached_work_shifts_json", null)
        return !raw.isNullOrBlank()
    }

    private fun loadCachedShifts(context: Context): List<WorkShift>? {
        val raw = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .getString("cached_work_shifts_json", null) ?: return null
        return try {
            val zone = ZoneId.systemDefault()
            val arr = JSONArray(raw)
            val list = ArrayList<WorkShift>(arr.length())
            for (i in 0 until arr.length()) {
                val obj = arr.getJSONObject(i)
                val startMs = obj.getLong("startMs")
                val endMs = obj.getLong("endMs")
                list.add(
                    WorkShift(
                        title = obj.optString("title", "Työvuoro"),
                        start = Instant.ofEpochMilli(startMs).atZone(zone).toLocalDateTime(),
                        end = Instant.ofEpochMilli(endMs).atZone(zone).toLocalDateTime(),
                        isAllDayLeave = obj.optBoolean("isAllDayLeave", false),
                        location = obj.optString("location", ""),
                        description = obj.optString("description", "")
                    )
                )
            }
            list
        } catch (_: Exception) {
            null
        }
    }

    fun countFutureSyncedEvents(context: Context, calendarId: Long): Int {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return 0
        }
        val nowMs = System.currentTimeMillis()
        val userTag = getUserTag(context)
        var count = 0
        val projection = arrayOf(
            CalendarContract.Events.TITLE,
            CalendarContract.Events.DESCRIPTION
        )
        val selection = "${CalendarContract.Events.CALENDAR_ID} = ? AND " +
                "${CalendarContract.Events.DTEND} > ? AND " +
                "${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(calendarId.toString(), nowMs.toString())

        context.contentResolver.query(CalendarContract.Events.CONTENT_URI, projection, selection, selectionArgs, null)?.use { c ->
            while (c.moveToNext()) {
                val title = c.getString(0) ?: ""
                val desc = c.getString(1) ?: ""
                if (belongsToAnotherUser(desc, userTag)) continue
                if (belongsToCurrentUser(desc, title, userTag)) {
                    count++
                }
            }
        }
        return count
    }

    fun deleteFutureSyncedEvents(context: Context, calendarId: Long): Int {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_CALENDAR) != PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return 0
        }
        val resolver = context.contentResolver
        val nowMs = System.currentTimeMillis()
        val userTag = getUserTag(context)
        val toDeleteIds = mutableListOf<Long>()

        val projection = arrayOf(
            CalendarContract.Events._ID,
            CalendarContract.Events.TITLE,
            CalendarContract.Events.DESCRIPTION
        )
        val selection = "${CalendarContract.Events.CALENDAR_ID} = ? AND " +
                "${CalendarContract.Events.DTEND} > ? AND " +
                "${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(calendarId.toString(), nowMs.toString())

        resolver.query(CalendarContract.Events.CONTENT_URI, projection, selection, selectionArgs, null)?.use { c ->
            while (c.moveToNext()) {
                val id = c.getLong(0)
                val title = c.getString(1) ?: ""
                val desc = c.getString(2) ?: ""
                if (belongsToAnotherUser(desc, userTag)) continue
                if (belongsToCurrentUser(desc, title, userTag)) {
                    toDeleteIds.add(id)
                }
            }
        }

        for (id in toDeleteIds) {
            val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, id)
            resolver.delete(uri, null, null)
        }
        if (toDeleteIds.isNotEmpty()) {
            CalendarChangeTracker.saveChanges(context, emptyList())
        }
        return toDeleteIds.size
    }

    fun cancelAllShiftReminders(context: Context) {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val oldReqCodes = prefs.getStringSet("scheduled_alarm_req_codes", emptySet()) ?: emptySet()
        for (oldCodeStr in oldReqCodes) {
            val oldCode = oldCodeStr.toIntOrNull() ?: continue
            val cancelIntent = Intent(context, ShiftReminderReceiver::class.java)
            val existingPi = PendingIntent.getBroadcast(
                context,
                oldCode,
                cancelIntent,
                PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE
            )
            if (existingPi != null) {
                alarmManager.cancel(existingPi)
                existingPi.cancel()
            }
        }
        prefs.edit()
            .remove("scheduled_alarm_req_codes")
            .remove("next_reminder_ms")
            .remove("next_reminder_label")
            .apply()
    }

    fun scheduleShiftReminders(context: Context, calendarId: Long? = getTargetCalendarId(context)) {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        if (!prefs.getBoolean("shift_reminders_enabled", true)) {
            cancelAllShiftReminders(context)
            return
        }

        val minutesBefore = prefs.getInt("reminder_minutes", 30)
        val userTag = getUserTag(context)
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val now = System.currentTimeMillis()
        val twoWeeksAhead = now + 14L * 24 * 60 * 60 * 1000L
        val timeFmt = DateTimeFormatter.ofPattern("HH:mm")
        val zone = ZoneId.systemDefault()

        val userShifts = mutableListOf<ReminderEventItem>()
        val cachedShifts = loadCachedShifts(context)

        if (cachedShifts != null) {
            for (shift in cachedShifts) {
                if (shift.isAllDayLeave) continue
                val startMs = shift.start.atZone(zone).toInstant().toEpochMilli()
                val endMs = shift.end.atZone(zone).toInstant().toEpochMilli()
                if (endMs <= now || startMs >= twoWeeksAhead) continue

                val baseTitle = formatShiftTitle(shift.title, userTag)
                val shiftRoleInfo = shift.description.trim()
                val displayTitle = if (shiftRoleInfo.isNotEmpty()) "$baseTitle ($shiftRoleInfo)" else baseTitle
                userShifts.add(ReminderEventItem(displayTitle, startMs, endMs))
            }
        } else if (calendarId != null &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) == PackageManager.PERMISSION_GRANTED
        ) {
            val projection = arrayOf(
                CalendarContract.Events.TITLE,
                CalendarContract.Events.DESCRIPTION,
                CalendarContract.Events.DTSTART,
                CalendarContract.Events.DTEND,
                CalendarContract.Events.ALL_DAY
            )
            val selection = "${CalendarContract.Events.CALENDAR_ID} = ? AND " +
                    "${CalendarContract.Events.DESCRIPTION} LIKE ? AND " +
                    "${CalendarContract.Events.DTEND} > ? AND " +
                    "${CalendarContract.Events.DTSTART} < ? AND " +
                    "${CalendarContract.Events.DELETED} = 0"
            val selectionArgs = arrayOf(calendarId.toString(), "%$EVENT_DESCRIPTION_TAG%", now.toString(), twoWeeksAhead.toString())

            context.contentResolver.query(
                CalendarContract.Events.CONTENT_URI,
                projection,
                selection,
                selectionArgs,
                "${CalendarContract.Events.DTSTART} ASC"
            )?.use { cursor ->
                while (cursor.moveToNext()) {
                    val baseTitle = cursor.getString(0) ?: continue
                    val desc = cursor.getString(1) ?: ""
                    val startMs = cursor.getLong(2)
                    val endMs = cursor.getLong(3)
                    val isAllDay = cursor.getInt(4) == 1

                    if (isAllDay) continue
                    if (!belongsToCurrentUser(desc, baseTitle, userTag)) continue

                    val shiftRoleInfo = desc.substringBefore(EVENT_DESCRIPTION_TAG).trim()
                    val displayTitle = if (shiftRoleInfo.isNotEmpty()) "$baseTitle ($shiftRoleInfo)" else baseTitle
                    userShifts.add(ReminderEventItem(displayTitle, startMs, endMs))
                }
            }
        }""",
        "CalendarSyncHelper cache & scheduleShiftReminders",
    )

    if sync != orig_sync:
        with open(sync_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(sync)
        print(f"Päivitetty: {sync_path}")
    else:
        print(f"Jo ajan tasalla: {sync_path}")

    # --------------------------------------------------------------------------
    # 2. ShiftReminderReceiver.kt
    # --------------------------------------------------------------------------
    rec_path = "app/src/main/java/fi/numeron/vuorovahti/ShiftReminderReceiver.kt"
    with open(rec_path, "r", encoding="utf-8") as f:
        rec = f.read()
    orig_rec = rec

    rec = replace_idempotent(
        rec,
        """        // 1. Puhelin käynnistyi uudelleen TAI sovellus päivitettiin (MY_PACKAGE_REPLACED)
        if (action == Intent.ACTION_BOOT_COMPLETED || action == Intent.ACTION_MY_PACKAGE_REPLACED) {
            val calId = CalendarSyncHelper.getTargetCalendarId(context)
            if (calId != null) {
                CalendarSyncHelper.scheduleShiftReminders(context, calId)
            }
            ensureBackgroundSyncScheduled(context)
            return
        }""",
        """        // 1. Puhelin käynnistyi uudelleen TAI sovellus päivitettiin (MY_PACKAGE_REPLACED)
        if (action == Intent.ACTION_BOOT_COMPLETED || action == Intent.ACTION_MY_PACKAGE_REPLACED) {
            CalendarSyncHelper.scheduleShiftReminders(context)
            ensureBackgroundSyncScheduled(context)
            return
        }""",
        "ShiftReminderReceiver boot",
    )

    rec = replace_idempotent(
        rec,
        """        if (!isTest) {
            CalendarSyncHelper.getTargetCalendarId(context)?.let { calId ->
                CalendarSyncHelper.scheduleShiftReminders(context, calId)
            }
        }""",
        """        if (!isTest) {
            CalendarSyncHelper.scheduleShiftReminders(context)
        }""",
        "ShiftReminderReceiver showReminderNotification",
    )

    rec = replace_idempotent(
        rec,
        """        fun ensureBackgroundSyncScheduled(context: Context) {
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

            context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                .edit()
                .putLong("next_calendar_sync_ms", nextTargetMs)
                .apply()
        }""",
        """        fun ensureBackgroundSyncScheduled(context: Context) {
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
        }""",
        "ShiftReminderReceiver ensureBackgroundSyncScheduled",
    )

    rec = replace_idempotent(
        rec,
        """        val baseUrl = UrlNormalizer.getSavedBaseUrl(appContext)
        val trackRequests = prefs.getBoolean("track_requests", true)

        if (rawUser.isEmpty() || rawPass.isEmpty() || baseUrl.isEmpty()) return@withContext Result.failure()

        val calId = CalendarSyncHelper.getTargetCalendarId(appContext)
            ?: return@withContext Result.failure()

        val now = LocalDate.now()
        val nextMonth = now.plusMonths(1)
        val currentMonthUrl = "$baseUrl/Calendar/Month?month=${now.monthValue}&year=${now.year}"
        val nextMonthUrl = "$baseUrl/Calendar/Month?month=${nextMonth.monthValue}&year=${nextMonth.year}"

        val htmlPages = suspendCancellableCoroutine<List<String>> { continuation ->
            val collectedHtml = mutableListOf<String>()
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
                if (continuation.isActive) continuation.resume(collectedHtml)
            }
            timeoutHandler.postDelayed(timeoutRunnable, 35_000L)

            bgWebView.webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    if (url == null) return
                    when {
                        url.contains("/Login/Login", ignoreCase = true) -> {
                            val jsLogin = \"\"\"
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
                            \"\"\".trimIndent()
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
                                    } else {
                                        timeoutHandler.removeCallbacks(timeoutRunnable)
                                        bgWebView.destroy()
                                        if (continuation.isActive) {
                                            continuation.resume(collectedHtml)
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

        if (htmlPages.isNotEmpty()) {
            CookieManager.getInstance().flush()
            val changes = withContext(Dispatchers.IO) {
                val allShifts = htmlPages.flatMap { NumeronParser.parseCalendarHtml(it) }
                val detectedChanges = CalendarSyncHelper.syncShiftsToCalendar(appContext, calId, allShifts)
                CalendarSyncHelper.scheduleShiftReminders(appContext, calId)
                if (trackRequests) {
                    fetchRequestsJson(baseUrl)?.let { checkRequestUpdates(it) }
                }
                detectedChanges
            }
            if (changes.isNotEmpty()) {
                ShiftReminderReceiver.showCalendarChangesNotification(appContext, changes)
            }
            prefs.edit()
                .putLong("last_valid_session_ms", System.currentTimeMillis())
                .apply()
            ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext)
            Result.success()
        } else {
            ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext)
            Result.retry()
        }""",
        """        val baseUrl = UrlNormalizer.getSavedBaseUrl(appContext)
        val syncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
        val shiftReminders = prefs.getBoolean("shift_reminders_enabled", true)
        val trackRequests = prefs.getBoolean("track_requests", true)

        if (!syncCalendar && !shiftReminders && !trackRequests) {
            ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext)
            return@withContext Result.success()
        }

        if (rawUser.isEmpty() || rawPass.isEmpty() || baseUrl.isEmpty()) return@withContext Result.failure()

        val needShifts = syncCalendar || shiftReminders
        val calId = if (syncCalendar) CalendarSyncHelper.getTargetCalendarId(appContext) else null

        val now = LocalDate.now()
        val nextMonth = now.plusMonths(1)
        val currentMonthUrl = "$baseUrl/Calendar/Month?month=${now.monthValue}&year=${now.year}"
        val nextMonthUrl = "$baseUrl/Calendar/Month?month=${nextMonth.monthValue}&year=${nextMonth.year}"
        val initialUrl = if (needShifts) currentMonthUrl else "$baseUrl/WorktimeStamping"

        data class WorkerFetchResult(val htmlPages: List<String>, val sessionAuthenticated: Boolean)

        val fetchResult = suspendCancellableCoroutine<WorkerFetchResult> { continuation ->
            val collectedHtml = mutableListOf<String>()
            var sessionOk = false
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
                if (continuation.isActive) continuation.resume(WorkerFetchResult(collectedHtml, sessionOk))
            }
            timeoutHandler.postDelayed(timeoutRunnable, 35_000L)

            bgWebView.webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    if (url == null) return
                    when {
                        url.contains("/Login/Login", ignoreCase = true) -> {
                            val jsLogin = \"\"\"
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
                            \"\"\".trimIndent()
                            view?.evaluateJavascript(jsLogin, null)
                        }
                        !needShifts && (
                            url.contains("/WorktimeStamping", ignoreCase = true) ||
                            url.contains("/InfraDashboard", ignoreCase = true) ||
                            url.contains("/Calendar", ignoreCase = true)
                        ) -> {
                            sessionOk = true
                            timeoutHandler.removeCallbacks(timeoutRunnable)
                            bgWebView.destroy()
                            if (continuation.isActive) {
                                continuation.resume(WorkerFetchResult(emptyList(), true))
                            }
                        }
                        needShifts && url.contains("/Calendar/Month", ignoreCase = true) -> {
                            sessionOk = true
                            view?.postDelayed({
                                view.evaluateJavascript("document.documentElement.outerHTML") { rawHtml ->
                                    if (rawHtml != null && rawHtml != "null") {
                                        val unescaped = JSONTokener(rawHtml).nextValue() as? String
                                        if (unescaped != null) collectedHtml.add(unescaped)
                                    }

                                    if (step == 0) {
                                        step = 1
                                        view.loadUrl(nextMonthUrl)
                                    } else {
                                        timeoutHandler.removeCallbacks(timeoutRunnable)
                                        bgWebView.destroy()
                                        if (continuation.isActive) {
                                            continuation.resume(WorkerFetchResult(collectedHtml, true))
                                        }
                                    }
                                }
                            }, 1200L)
                        }
                    }
                }
            }
            bgWebView.loadUrl(initialUrl)
        }

        val success = if (needShifts) fetchResult.htmlPages.isNotEmpty() else fetchResult.sessionAuthenticated
        if (success) {
            CookieManager.getInstance().flush()
            val changes = withContext(Dispatchers.IO) {
                val detectedChanges = if (needShifts) {
                    val allShifts = fetchResult.htmlPages.flatMap { NumeronParser.parseCalendarHtml(it) }
                    CalendarSyncHelper.saveCachedShifts(appContext, allShifts)
                    val calChanges = if (syncCalendar && calId != null) {
                        CalendarSyncHelper.syncShiftsToCalendar(appContext, calId, allShifts)
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
                detectedChanges
            }
            if (changes.isNotEmpty()) {
                ShiftReminderReceiver.showCalendarChangesNotification(appContext, changes)
            }
            prefs.edit()
                .putLong("last_valid_session_ms", System.currentTimeMillis())
                .apply()
            ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext)
            Result.success()
        } else {
            ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext)
            Result.retry()
        }""",
        "BackgroundSyncWorker independent flags",
    )

    if rec != orig_rec:
        with open(rec_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(rec)
        print(f"Päivitetty: {rec_path}")
    else:
        print(f"Jo ajan tasalla: {rec_path}")

    # --------------------------------------------------------------------------
    # 3. MainActivity.kt
    # --------------------------------------------------------------------------
    main_path = "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt"
    with open(main_path, "r", encoding="utf-8") as f:
        main = f.read()
    orig_main = main

    main = replace_idempotent(
        main,
        """        CalendarSyncHelper.getTargetCalendarId(this)?.let {
            CalendarSyncHelper.scheduleShiftReminders(this, it)
        }""",
        """        CalendarSyncHelper.scheduleShiftReminders(this)""",
        "MainActivity onCreate scheduleShiftReminders",
    )

    main = replace_idempotent(
        main,
        """                onSaved = {
                    CalendarSyncHelper.getTargetCalendarId(this)?.let {
                        CalendarSyncHelper.scheduleShiftReminders(this, it)
                    }
                    navigateToTab(currentTab)
                }""",
        """                onSaved = {
                    CalendarSyncHelper.scheduleShiftReminders(this)
                    ShiftReminderReceiver.ensureBackgroundSyncScheduled(this)
                    navigateToTab(currentTab)
                }""",
        "MainActivity onSaved",
    )

    main = replace_idempotent(
        main,
        """    private fun startCalendarSync() {
        if (DemoModeHelper.isDemoEnabled(this)) {
            scope.launch(Dispatchers.IO) {
                val calId = CalendarSyncHelper.getTargetCalendarId(this@MainActivity)
                if (calId != null) {
                    val demoShifts = DemoModeHelper.generateDemoWorkShifts(this@MainActivity)
                    val changes = CalendarSyncHelper.syncShiftsToCalendar(this@MainActivity, calId, demoShifts)
                    CalendarSyncHelper.scheduleShiftReminders(this@MainActivity, calId)
                    withContext(Dispatchers.Main) {
                        if (changes.isNotEmpty()) {
                            Toast.makeText(
                                this@MainActivity,
                                "Kalenterimuutokset: ${CalendarChangeTracker.formatSummary(changes)}",
                                Toast.LENGTH_LONG
                            ).show()
                            CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                        } else {
                            Toast.makeText(
                                this@MainActivity,
                                "Demovuorot ovat jo ajan tasalla kalenterissa",
                                Toast.LENGTH_SHORT
                            ).show()
                        }
                    }
                } else {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(this@MainActivity, "Kalenterioikeus tai kalenteri puuttuu", Toast.LENGTH_LONG).show()
                    }
                }
            }
            return
        }

        pendingAction = Action.SYNC_CALENDAR
        syncStep = 0
        collectedCalendarHtml.clear()
        val now = LocalDate.now()
        val baseUrl = getBaseUrl()
        webView.loadUrl("$baseUrl/Calendar/Month?month=${now.monthValue}&year=${now.year}")
    }""",
        """    private fun startCalendarSync() {
        val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val syncCalendar = prefs.getBoolean("sync_calendar_enabled", true)

        if (DemoModeHelper.isDemoEnabled(this)) {
            scope.launch(Dispatchers.IO) {
                val calId = if (syncCalendar) CalendarSyncHelper.getTargetCalendarId(this@MainActivity) else null
                val demoShifts = DemoModeHelper.generateDemoWorkShifts(this@MainActivity)
                CalendarSyncHelper.saveCachedShifts(this@MainActivity, demoShifts)
                val changes = if (syncCalendar && calId != null) {
                    CalendarSyncHelper.syncShiftsToCalendar(this@MainActivity, calId, demoShifts)
                } else {
                    prefs.edit().putLong("last_calendar_sync_ms", System.currentTimeMillis()).apply()
                    emptyList()
                }
                CalendarSyncHelper.scheduleShiftReminders(this@MainActivity, calId)

                withContext(Dispatchers.Main) {
                    if (syncCalendar && calId == null) {
                        Toast.makeText(this@MainActivity, "Kalenterioikeus tai kalenteri puuttuu", Toast.LENGTH_LONG).show()
                    } else if (changes.isNotEmpty()) {
                        Toast.makeText(
                            this@MainActivity,
                            "Kalenterimuutokset: ${CalendarChangeTracker.formatSummary(changes)}",
                            Toast.LENGTH_LONG
                        ).show()
                        CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                    } else {
                        val msg = if (syncCalendar) {
                            "Demovuorot ovat jo ajan tasalla kalenterissa"
                        } else {
                            "Demovuorot ja muistutukset päivitetty (${demoShifts.size} vuoroa)"
                        }
                        Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                    }
                }
            }
            return
        }

        pendingAction = Action.SYNC_CALENDAR
        syncStep = 0
        collectedCalendarHtml.clear()
        val now = LocalDate.now()
        val baseUrl = getBaseUrl()
        webView.loadUrl("$baseUrl/Calendar/Month?month=${now.monthValue}&year=${now.year}")
    }""",
        "MainActivity startCalendarSync",
    )

    main = replace_idempotent(
        main,
        """                scope.launch(Dispatchers.IO) {
                    val calId = CalendarSyncHelper.getTargetCalendarId(this@MainActivity)
                    if (calId != null) {
                        val allShifts = pagesToParse.flatMap { NumeronParser.parseCalendarHtml(it) }
                        val changes = CalendarSyncHelper.syncShiftsToCalendar(this@MainActivity, calId, allShifts)
                        CalendarSyncHelper.scheduleShiftReminders(this@MainActivity, calId)

                        withContext(Dispatchers.Main) {
                            if (changes.isNotEmpty()) {
                                Toast.makeText(
                                    this@MainActivity,
                                    "Kalenteria päivitetty: ${CalendarChangeTracker.formatSummary(changes)}",
                                    Toast.LENGTH_LONG
                                ).show()
                                CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                            } else {
                                Toast.makeText(
                                    this@MainActivity,
                                    "Kalenteri on ajan tasalla (${allShifts.size} vuoroa)",
                                    Toast.LENGTH_SHORT
                                ).show()
                            }
                        }
                    }
                }""",
        """                scope.launch(Dispatchers.IO) {
                    val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                    val syncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
                    val calId = if (syncCalendar) CalendarSyncHelper.getTargetCalendarId(this@MainActivity) else null
                    val allShifts = pagesToParse.flatMap { NumeronParser.parseCalendarHtml(it) }
                    CalendarSyncHelper.saveCachedShifts(this@MainActivity, allShifts)

                    val changes = if (syncCalendar && calId != null) {
                        CalendarSyncHelper.syncShiftsToCalendar(this@MainActivity, calId, allShifts)
                    } else {
                        prefs.edit().putLong("last_calendar_sync_ms", System.currentTimeMillis()).apply()
                        emptyList()
                    }
                    CalendarSyncHelper.scheduleShiftReminders(this@MainActivity, calId)

                    withContext(Dispatchers.Main) {
                        if (syncCalendar && calId == null) {
                            Toast.makeText(
                                this@MainActivity,
                                "Vuorot haettu (${allShifts.size} kpl), mutta kalenteria ei ole valittu",
                                Toast.LENGTH_LONG
                            ).show()
                        } else if (changes.isNotEmpty()) {
                            Toast.makeText(
                                this@MainActivity,
                                "Kalenteria päivitetty: ${CalendarChangeTracker.formatSummary(changes)}",
                                Toast.LENGTH_LONG
                            ).show()
                            CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                        } else {
                            val msg = if (syncCalendar) {
                                "Kalenteri on ajan tasalla (${allShifts.size} vuoroa)"
                            } else {
                                "Työvuorot ja muistutukset päivitetty (${allShifts.size} vuoroa)"
                            }
                            Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                        }
                    }
                }""",
        "MainActivity handleCalendarPage",
    )

    if main != orig_main:
        with open(main_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(main)
        print(f"Päivitetty: {main_path}")
    else:
        print(f"Jo ajan tasalla: {main_path}")

    # --------------------------------------------------------------------------
    # 4. SettingsDialogHelper.kt
    # --------------------------------------------------------------------------
    settings_path = "app/src/main/java/fi/numeron/vuorovahti/SettingsDialogHelper.kt"
    with open(settings_path, "r", encoding="utf-8") as f:
        st = f.read()
    orig_st = st

    st = replace_idempotent(
        st,
        """import android.text.InputType
import android.view.Gravity""",
        """import android.content.res.ColorStateList
import android.text.InputType
import android.text.method.PasswordTransformationMethod
import android.view.Gravity""",
        "SettingsDialogHelper imports 1",
    )

    st = replace_idempotent(
        st,
        """import android.widget.Spinner
import android.widget.TextView""",
        """import android.widget.Spinner
import android.widget.Switch
import android.widget.TextView""",
        "SettingsDialogHelper imports 2",
    )

    st = replace_idempotent(
        st,
        """        fun styleSpinner(spinner: Spinner) {
            spinner.background = makeCardBg("#111923", "#37475A", 8)
            spinner.setPadding(dp(8), dp(6), dp(8), dp(6))
        }""",
        """        fun styleSpinner(spinner: Spinner) {
            spinner.background = makeCardBg("#111923", "#37475A", 8)
            spinner.setPadding(dp(8), dp(6), dp(8), dp(6))
        }

        fun createToggleRow(
            parent: LinearLayout,
            title: String,
            subtitle: String,
            initialChecked: Boolean,
            onToggle: ((Boolean) -> Unit)? = null
        ): Switch {
            val row = LinearLayout(context).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                background = makeCardBg("#111923", "#2A394A", 8)
                setPadding(dp(12), dp(10), dp(12), dp(10))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    topMargin = dp(6)
                    bottomMargin = dp(4)
                }
            }

            val textCol = LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
                    marginEnd = dp(10)
                }
            }
            textCol.addView(TextView(context).apply {
                text = title
                textSize = 14f
                setTypeface(null, Typeface.BOLD)
                setTextColor(Color.parseColor("#F1F5F9"))
            })
            textCol.addView(TextView(context).apply {
                text = subtitle
                textSize = 12f
                setTextColor(Color.parseColor("#94A3B8"))
                setPadding(0, dp(2), 0, 0)
            })

            val sw = Switch(context).apply {
                isChecked = initialChecked
                thumbTintList = ColorStateList(
                    arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()),
                    intArrayOf(Color.parseColor("#38BDF8"), Color.parseColor("#94A3B8"))
                )
                trackTintList = ColorStateList(
                    arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()),
                    intArrayOf(Color.parseColor("#1E3A5F"), Color.parseColor("#233040"))
                )
                setOnCheckedChangeListener { _, checked ->
                    onToggle?.invoke(checked)
                }
            }

            row.setOnClickListener {
                sw.isChecked = !sw.isChecked
            }

            row.addView(textCol)
            row.addView(sw)
            parent.addView(row)
            return sw
        }""",
        "SettingsDialogHelper createToggleRow",
    )

    st = replace_idempotent(
        st,
        """        val lastSyncMs = prefs.getLong("last_calendar_sync_ms", 0L)
        val nextSyncMs = resolveNextSyncMs(context, prefs.getLong("next_calendar_sync_ms", 0L))
        val lastNotifMs = prefs.getLong("last_reminder_sent_ms", 0L)
        val lastNotifLabel = prefs.getString("last_reminder_sent_label", "") ?: ""
        val nextNotifMs = prefs.getLong("next_reminder_ms", 0L)
        val nextNotifLabel = prefs.getString("next_reminder_label", "") ?: \"\"""",
        """        val initialSyncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
        val initialShiftReminders = prefs.getBoolean("shift_reminders_enabled", true)
        val initialTrackRequests = prefs.getBoolean("track_requests", true)
        val anyBackgroundEnabled = initialSyncCalendar || initialShiftReminders || initialTrackRequests

        val lastSyncMs = prefs.getLong("last_calendar_sync_ms", 0L)
        val nextSyncMs = resolveNextSyncMs(context, prefs.getLong("next_calendar_sync_ms", 0L))
        val lastNotifMs = prefs.getLong("last_reminder_sent_ms", 0L)
        val lastNotifLabel = prefs.getString("last_reminder_sent_label", "") ?: ""
        val nextNotifMs = prefs.getLong("next_reminder_ms", 0L)
        val nextNotifLabel = prefs.getString("next_reminder_label", "") ?: \"\"""",
        "SettingsDialogHelper status vars",
    )

    st = replace_idempotent(
        st,
        """        addStatusRow(
            statusCard,
            "Kalenterimerkinnät tarkistettu edellisen kerran",
            formatTimestamp(lastSyncMs, "Ei vielä tarkistettu")
        )
        addStatusRow(
            statusCard,
            "Seuraava kalenteritarkistus ajoitettu",
            formatTimestamp(nextSyncMs, "Arkisin klo 09:30 ja 14:30")
        )
        addStatusRow(
            statusCard,
            "Edellinen leimausnotifikaatio lähetetty",
            formatTimestamp(lastNotifMs, "Ei vielä lähetetty"),
            if (lastNotifMs > 0L) lastNotifLabel else null
        )
        addStatusRow(
            statusCard,
            "Seuraava leimausnotifikaatio lähetetään",
            if (nextNotifMs > System.currentTimeMillis()) formatTimestamp(nextNotifMs, "") else "Ei tulevia ajoitettuja hälytyksiä",
            if (nextNotifMs > System.currentTimeMillis()) nextNotifLabel else null
        )""",
        """        addStatusRow(
            statusCard,
            "Työvuorot ja kalenteri tarkistettu",
            formatTimestamp(lastSyncMs, "Ei vielä tarkistettu")
        )
        addStatusRow(
            statusCard,
            "Seuraava automaattinen tarkistus",
            if (!anyBackgroundEnabled) "Pois käytöstä" else formatTimestamp(nextSyncMs, "Arkisin klo 09:30 ja 14:30")
        )
        addStatusRow(
            statusCard,
            "Edellinen leimausnotifikaatio lähetetty",
            formatTimestamp(lastNotifMs, "Ei vielä lähetetty"),
            if (lastNotifMs > 0L) lastNotifLabel else null
        )
        addStatusRow(
            statusCard,
            "Seuraava leimausnotifikaatio lähetetään",
            when {
                !initialShiftReminders -> "Leimausmuistutukset pois käytöstä"
                nextNotifMs > System.currentTimeMillis() -> formatTimestamp(nextNotifMs, "")
                else -> "Ei tulevia ajoitettuja hälytyksiä"
            },
            if (initialShiftReminders && nextNotifMs > System.currentTimeMillis()) nextNotifLabel else null
        )""",
        "SettingsDialogHelper status rows",
    )

    st = replace_idempotent(
        st,
        """        authCard.addView(createLabel("Salasana"))
        val editPass = EditText(context).apply {
            hint = "Salasana"
            setText(SecureCredentialManager.getPassword(context) ?: "")
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            isSingleLine = true
            styleEditText(this)
        }
        authCard.addView(editPass)""",
        """        val existingPassword = SecureCredentialManager.getPassword(context) ?: ""
        val hasSavedPassword = existingPassword.isNotEmpty()

        authCard.addView(createLabel("Salasana"))
        val editPass = EditText(context).apply {
            hint = if (hasSavedPassword) {
                "•••••••• (tallennettu – kirjoita uusi vaihtaaksesi)"
            } else {
                "Salasana"
            }
            setText("")
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            transformationMethod = PasswordTransformationMethod.getInstance()
            isSingleLine = true
            styleEditText(this)
        }
        authCard.addView(editPass)""",
        "SettingsDialogHelper hide saved password",
    )

    st = replace_idempotent(
        st,
        """                val normalizedUrl = UrlNormalizer.normalizeOrgUrl(editOrg.text.toString())
                val user = editUser.text.toString().trim()
                val pass = editPass.text.toString()""",
        """                val normalizedUrl = UrlNormalizer.normalizeOrgUrl(editOrg.text.toString())
                val user = editUser.text.toString().trim()
                val typedPass = editPass.text.toString()
                val pass = if (typedPass.isNotEmpty()) typedPass else existingPassword""",
        "SettingsDialogHelper test button password",
    )

    st = replace_idempotent(
        st,
        """        // === KORTTI 3: KALENTERI JA VÄRIKOODIT ===
        val calCard = createSectionCard("Kalenteri ja värikoodit")

        calCard.addView(createLabel("Kohdekalenteri"))
        val calendars = getAvailableCalendars(context)
        val spinnerCalendar = Spinner(context).apply { styleSpinner(this) }
        if (calendars.isNotEmpty()) {
            spinnerCalendar.adapter = createDarkAdapter(calendars)
            val savedCalId = prefs.getLong("calendar_id", -1L)
            val idx = calendars.indexOfFirst { it.id == savedCalId }
            spinnerCalendar.setSelection(if (idx >= 0) idx else 0)
        }
        calCard.addView(spinnerCalendar)

        calCard.addView(createLabel("Henkilötunniste yhteiskalenteriin (valinnainen, esim. Jukka)"))
        val editUserTag = EditText(context).apply {
            hint = "Jätä tyhjäksi omassa kalenterissa"
            setText(prefs.getString("calendar_user_tag", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_WORDS
            isSingleLine = true
            styleEditText(this)
        }
        calCard.addView(editUserTag)

        fun createColorSpinner(savedRgb: Int): Spinner {
            val spinner = Spinner(context).apply { styleSpinner(this) }
            spinner.adapter = createDarkAdapter(SHIFT_COLOR_CHOICES)
            val idx = SHIFT_COLOR_CHOICES.indexOfFirst { it.rgb == savedRgb }
            if (idx >= 0) spinner.setSelection(idx)
            return spinner
        }

        calCard.addView(createLabel("Aamuvuoron väri"))
        val spinnerMorningColor = createColorSpinner(prefs.getInt("color_morning_rgb", DEFAULT_MORNING_RGB))
        calCard.addView(spinnerMorningColor)

        calCard.addView(createLabel("Iltavuoron väri"))
        val spinnerEveningColor = createColorSpinner(prefs.getInt("color_evening_rgb", DEFAULT_EVENING_RGB))
        calCard.addView(spinnerEveningColor)

        calCard.addView(createLabel("Yövuoron väri"))
        val spinnerNightColor = createColorSpinner(prefs.getInt("color_night_rgb", DEFAULT_NIGHT_RGB))
        calCard.addView(spinnerNightColor)

        // === KORTTI 4: MUISTUTUKSET JA TOIMINNOT ===
        val actionCard = createSectionCard("Muistutukset ja toiminnot")

        actionCard.addView(createLabel("Muistutus ennen vuoroa (min)"))
        val editReminder = EditText(context).apply {
            setText(prefs.getInt("reminder_minutes", 30).toString())
            inputType = InputType.TYPE_CLASS_NUMBER
            isSingleLine = true
            styleEditText(this)
        }
        actionCard.addView(editReminder)

        val btnSync = Button(context).apply {
            text = "Synkronoi työvuorot kalenteriin nyt"
            styleButton(this, "#1982C4", "#38BDF8", "#FFFFFF")
        }
        actionCard.addView(btnSync)

        val btnChanges = Button(context).apply {
            text = "Hallitse kalenterimuutoksia"
            styleButton(this, "#233040", "#37475A", "#F1F5F9")
        }
        actionCard.addView(btnChanges)

        val btnTestNotif = Button(context).apply {
            text = "Lähetä testi-ilmoitus"
            styleButton(this, "#233040", "#37475A", "#F1F5F9")
        }
        actionCard.addView(btnTestNotif)""",
        """        // === KORTTI 3: KALENTERISYNRONOINTI JA VÄRIKOODIT ===
        val calCard = createSectionCard("Kalenterisynkronointi ja värikoodit")

        val calDetailsContainer = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            visibility = if (initialSyncCalendar) View.VISIBLE else View.GONE
        }

        val switchSyncCalendar = createToggleRow(
            parent = calCard,
            title = "Synkronoi työvuorot Google-kalenteriin",
            subtitle = "Vie työvuorot ja poissaolot valittuun kalenteriin automaattisesti",
            initialChecked = initialSyncCalendar
        ) { enabled ->
            calDetailsContainer.visibility = if (enabled) View.VISIBLE else View.GONE
        }

        calDetailsContainer.addView(createLabel("Kohdekalenteri"))
        val calendars = getAvailableCalendars(context)
        val spinnerCalendar = Spinner(context).apply { styleSpinner(this) }
        if (calendars.isNotEmpty()) {
            spinnerCalendar.adapter = createDarkAdapter(calendars)
            val savedCalId = prefs.getLong("calendar_id", -1L)
            val idx = calendars.indexOfFirst { it.id == savedCalId }
            spinnerCalendar.setSelection(if (idx >= 0) idx else 0)
        }
        calDetailsContainer.addView(spinnerCalendar)

        calDetailsContainer.addView(createLabel("Henkilötunniste yhteiskalenteriin (valinnainen, esim. Jukka)"))
        val editUserTag = EditText(context).apply {
            hint = "Jätä tyhjäksi omassa kalenterissa"
            setText(prefs.getString("calendar_user_tag", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_WORDS
            isSingleLine = true
            styleEditText(this)
        }
        calDetailsContainer.addView(editUserTag)

        fun createColorSpinner(savedRgb: Int): Spinner {
            val spinner = Spinner(context).apply { styleSpinner(this) }
            spinner.adapter = createDarkAdapter(SHIFT_COLOR_CHOICES)
            val idx = SHIFT_COLOR_CHOICES.indexOfFirst { it.rgb == savedRgb }
            if (idx >= 0) spinner.setSelection(idx)
            return spinner
        }

        calDetailsContainer.addView(createLabel("Aamuvuoron väri"))
        val spinnerMorningColor = createColorSpinner(prefs.getInt("color_morning_rgb", DEFAULT_MORNING_RGB))
        calDetailsContainer.addView(spinnerMorningColor)

        calDetailsContainer.addView(createLabel("Iltavuoron väri"))
        val spinnerEveningColor = createColorSpinner(prefs.getInt("color_evening_rgb", DEFAULT_EVENING_RGB))
        calDetailsContainer.addView(spinnerEveningColor)

        calDetailsContainer.addView(createLabel("Yövuoron väri"))
        val spinnerNightColor = createColorSpinner(prefs.getInt("color_night_rgb", DEFAULT_NIGHT_RGB))
        calDetailsContainer.addView(spinnerNightColor)

        calCard.addView(calDetailsContainer)

        // === KORTTI 4: MUISTUTUKSET JA ILMOITUKSET ===
        val actionCard = createSectionCard("Muistutukset ja ilmoitukset")

        val reminderDetailsContainer = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            visibility = if (initialShiftReminders) View.VISIBLE else View.GONE
        }

        val switchShiftReminders = createToggleRow(
            parent = actionCard,
            title = "Työvuorojen leimausmuistutukset",
            subtitle = "Ilmoitus ennen vuoron alkua ja loppua pikaleimauspainikkeella (toimii myös ilman kalenterisynkronointia)",
            initialChecked = initialShiftReminders
        ) { enabled ->
            reminderDetailsContainer.visibility = if (enabled) View.VISIBLE else View.GONE
        }

        reminderDetailsContainer.addView(createLabel("Muistutus ennen vuoroa (min)"))
        val editReminder = EditText(context).apply {
            setText(prefs.getInt("reminder_minutes", 30).toString())
            inputType = InputType.TYPE_CLASS_NUMBER
            isSingleLine = true
            styleEditText(this)
        }
        reminderDetailsContainer.addView(editReminder)
        actionCard.addView(reminderDetailsContainer)

        val switchTrackRequests = createToggleRow(
            parent = actionCard,
            title = "Ilmoita käsitellyistä toiveista",
            subtitle = "Lähettää ilmoituksen, kun työvuoro- tai lomatoiveesi hyväksytään tai hylätään",
            initialChecked = initialTrackRequests
        )

        val btnSync = Button(context).apply {
            text = "Hae ja päivitä työvuorot nyt"
            styleButton(this, "#1982C4", "#38BDF8", "#FFFFFF")
        }
        actionCard.addView(btnSync)

        val btnChanges = Button(context).apply {
            text = "Hallitse kalenterimuutoksia"
            styleButton(this, "#233040", "#37475A", "#F1F5F9")
        }
        actionCard.addView(btnChanges)

        val btnTestNotif = Button(context).apply {
            text = "Lähetä testi-ilmoitus"
            styleButton(this, "#233040", "#37475A", "#F1F5F9")
        }
        actionCard.addView(btnTestNotif)""",
        "SettingsDialogHelper independent switches",
    )

    st = replace_idempotent(
        st,
        """            val savedUser = editUser.text.toString().trim()
            val savedPass = editPass.text.toString()
            val isDemo = savedUser.isEmpty() || savedPass.isEmpty() || rawOrg.isEmpty() ||
                DemoModeHelper.isDemoCredentials(rawOrg, savedUser, savedPass)

            SecureCredentialManager.saveCredentials(context, savedUser, savedPass)

            prefs.edit()
                .putString("org_raw_input", rawOrg)
                .putString("server_url", normalizedUrl)
                .putBoolean("demo_mode", isDemo)
                .putString("calendar_user_tag", userTag)
                .putInt("reminder_minutes", reminderMins)
                .putInt("color_morning_rgb", morningRgb)
                .putInt("color_evening_rgb", eveningRgb)
                .putInt("color_night_rgb", nightRgb)
                .apply {
                    if (selectedCal != null) putLong("calendar_id", selectedCal.id)
                }
                .apply()

            val statusMsg = if (isDemo) "Demotila aktiivinen" else "Tallennettu ($normalizedUrl)"
            Toast.makeText(context, statusMsg, Toast.LENGTH_SHORT).show()
            dialog.dismiss()
            onSaved()""",
        """            val savedUser = editUser.text.toString().trim()
            val typedPass = editPass.text.toString()
            val savedPass = when {
                savedUser.isEmpty() -> ""
                typedPass.isNotEmpty() -> typedPass
                else -> existingPassword
            }
            val newSyncCalendar = switchSyncCalendar.isChecked
            val newShiftReminders = switchShiftReminders.isChecked
            val newTrackRequests = switchTrackRequests.isChecked

            val isDemo = savedUser.isEmpty() || savedPass.isEmpty() || rawOrg.isEmpty() ||
                DemoModeHelper.isDemoCredentials(rawOrg, savedUser, savedPass)

            SecureCredentialManager.saveCredentials(context, savedUser, savedPass)

            prefs.edit()
                .putString("org_raw_input", rawOrg)
                .putString("server_url", normalizedUrl)
                .putBoolean("demo_mode", isDemo)
                .putBoolean("sync_calendar_enabled", newSyncCalendar)
                .putBoolean("shift_reminders_enabled", newShiftReminders)
                .putBoolean("track_requests", newTrackRequests)
                .putString("calendar_user_tag", userTag)
                .putInt("reminder_minutes", reminderMins)
                .putInt("color_morning_rgb", morningRgb)
                .putInt("color_evening_rgb", eveningRgb)
                .putInt("color_night_rgb", nightRgb)
                .apply {
                    if (selectedCal != null) putLong("calendar_id", selectedCal.id)
                }
                .apply()

            val turnedOnSync = !initialSyncCalendar && newSyncCalendar
            val missingCacheForReminders = newShiftReminders && !CalendarSyncHelper.hasCachedShifts(context)
            val shouldTriggerSync = turnedOnSync || (!initialShiftReminders && missingCacheForReminders)

            fun finishSave(extraMsg: String? = null, forceSync: Boolean = false) {
                val statusMsg = extraMsg ?: if (isDemo) "Demotila aktiivinen" else "Tallennettu ($normalizedUrl)"
                Toast.makeText(context, statusMsg, Toast.LENGTH_SHORT).show()
                dialog.dismiss()
                onSaved()
                if ((shouldTriggerSync || forceSync) && !isDemo && savedUser.isNotEmpty() && savedPass.isNotEmpty() && normalizedUrl.isNotEmpty()) {
                    ShiftReminderReceiver.triggerImmediateSync(context)
                }
            }

            if (initialSyncCalendar && !newSyncCalendar) {
                val targetCalId = selectedCal?.id ?: CalendarSyncHelper.getTargetCalendarId(context)
                val futureCount = if (targetCalId != null) {
                    CalendarSyncHelper.countFutureSyncedEvents(context, targetCalId)
                } else {
                    0
                }
                if (targetCalId != null && futureCount > 0) {
                    AlertDialog.Builder(context)
                        .setTitle("Poistetaanko kalenterimerkinnät?")
                        .setMessage("Kalenterisynkronointi otettiin pois käytöstä. Haluatko poistaa sovelluksen Google-kalenteriin lisäämät tulevat merkinnät ($futureCount kpl)?")
                        .setPositiveButton("Poista merkinnät") { _, _ ->
                            val deletedCount = CalendarSyncHelper.deleteFutureSyncedEvents(context, targetCalId)
                            finishSave("Asetukset tallennettu (poistettu $deletedCount merkintää)", forceSync = missingCacheForReminders)
                        }
                        .setNegativeButton("Jätä kalenteriin") { _, _ ->
                            finishSave("Asetukset tallennettu")
                        }
                        .setCancelable(false)
                        .show()
                } else {
                    finishSave()
                }
            } else {
                finishSave()
            }""",
        "SettingsDialogHelper save and delete prompt",
    )

    if st != orig_st:
        with open(settings_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(st)
        print(f"Päivitetty: {settings_path}")
    else:
        print(f"Jo ajan tasalla: {settings_path}")
# ==============================================================================
# === POISTETTAVA KORJAUSOSIO PÄÄTTYY ===
# ==============================================================================


if __name__ == "__main__":
    bump_version_code()
    apply_feature_updates()
