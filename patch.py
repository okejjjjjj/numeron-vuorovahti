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
def apply_codebase_fixes():
    # 1. Poista vanhentunut RequestCheckWorker.kt
    obsolete_worker = "app/src/main/java/fi/numeron/vuorovahti/RequestCheckWorker.kt"
    if os.path.exists(obsolete_worker):
        os.remove(obsolete_worker)
        print(f"Poistettu tarpeeton tiedosto: {obsolete_worker}")

    # 2. CalendarSyncHelper.kt: haamuhälytysten peruminen, monipäiväiset lomat, tuplailmoituksen poisto
    sync_path = "app/src/main/java/fi/numeron/vuorovahti/CalendarSyncHelper.kt"
    if os.path.exists(sync_path):
        with open(sync_path, "r", encoding="utf-8") as f:
            sync = f.read()

        orig_sync = sync

        old_selection = """        val selection = "${CalendarContract.Events.CALENDAR_ID} = ? AND " +
                "${CalendarContract.Events.DTSTART} > ? AND " +
                "${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(calendarId.toString(), nowMs.toString())"""

        new_selection = """        val selection = "${CalendarContract.Events.CALENDAR_ID} = ? AND " +
                "${CalendarContract.Events.DTEND} > ? AND " +
                "${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(calendarId.toString(), nowMs.toString())"""

        if old_selection in sync:
            sync = sync.replace(old_selection, new_selection, 1)

        old_exact_match = """            if (exactMatch != null) {
                unmatchedOwned.remove(exactMatch)
                continue
            }

            val sameDayOwned = unmatchedOwned.firstOrNull { ex ->
                ex.isAllDay == shift.isAllDayLeave &&
                isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave) &&
                (!shift.isAllDayLeave || ex.title.equals(desiredTitle, ignoreCase = true) || ex.startMs == newStartMs)
            } ?: unmatchedOwned.firstOrNull { ex ->
                ex.isAllDay == shift.isAllDayLeave && isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave)
            }"""

        new_exact_match = """            if (exactMatch != null) {
                unmatchedOwned.remove(exactMatch)
                continue
            }

            if (shift.isAllDayLeave) {
                val coveringOwned = unmatchedOwned.firstOrNull { ex ->
                    ex.isAllDay &&
                    ex.title.equals(desiredTitle, ignoreCase = true) &&
                    ex.startMs < newStartMs &&
                    ex.endMs == newEndMs
                }
                if (coveringOwned != null) {
                    unmatchedOwned.remove(coveringOwned)
                    continue
                }
                val coveringExternal = unmatchedExternal.firstOrNull { ex ->
                    ex.isAllDay &&
                    ex.title.equals(desiredTitle, ignoreCase = true) &&
                    ex.startMs < newStartMs &&
                    ex.endMs == newEndMs
                }
                if (coveringExternal != null) {
                    unmatchedExternal.remove(coveringExternal)
                    continue
                }
            }

            val sameDayOwned = unmatchedOwned.firstOrNull { ex ->
                ex.isAllDay == shift.isAllDayLeave &&
                isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave) &&
                (!shift.isAllDayLeave || ex.title.equals(desiredTitle, ignoreCase = true) || ex.startMs == newStartMs)
            } ?: unmatchedOwned.firstOrNull { ex ->
                shift.isAllDayLeave &&
                ex.isAllDay &&
                ex.title.equals(desiredTitle, ignoreCase = true) &&
                ex.startMs < newStartMs &&
                ex.endMs > newStartMs
            } ?: unmatchedOwned.firstOrNull { ex ->
                ex.isAllDay == shift.isAllDayLeave && isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave)
            }"""

        if old_exact_match in sync and "coveringOwned" not in sync:
            sync = sync.replace(old_exact_match, new_exact_match, 1)

        old_update_block = """                val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, targetMatch.eventId)
                val values = ContentValues().apply {
                    put(CalendarContract.Events.TITLE, desiredTitle)
                    put(CalendarContract.Events.EVENT_LOCATION, shift.location)
                    put(CalendarContract.Events.DESCRIPTION, fullDescription)
                    if (desiredColorKey != null) {
                        put(CalendarContract.Events.EVENT_COLOR_KEY, desiredColorKey)
                    } else {
                        putNull(CalendarContract.Events.EVENT_COLOR_KEY)
                    }
                    put(CalendarContract.Events.ALL_DAY, if (shift.isAllDayLeave) 1 else 0)
                    put(CalendarContract.Events.EVENT_TIMEZONE, if (shift.isAllDayLeave) "UTC" else TimeZone.getDefault().id)
                    put(CalendarContract.Events.DTSTART, newStartMs)
                    put(CalendarContract.Events.DTEND, newEndMs)
                }
                resolver.update(uri, values, null, null)

                detectedChanges.add(
                    CalendarChangeItem(
                        id = UUID.randomUUID().toString(),
                        type = ChangeType.MODIFIED,
                        calendarId = calendarId,
                        eventId = targetMatch.eventId,
                        title = desiredTitle,
                        startMs = newStartMs,
                        endMs = newEndMs,"""

        new_update_block = """                val effectiveStartMs = if (shift.isAllDayLeave && targetMatch.startMs < newStartMs) {
                    targetMatch.startMs
                } else {
                    newStartMs
                }
                val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, targetMatch.eventId)
                val values = ContentValues().apply {
                    put(CalendarContract.Events.TITLE, desiredTitle)
                    put(CalendarContract.Events.EVENT_LOCATION, shift.location)
                    put(CalendarContract.Events.DESCRIPTION, fullDescription)
                    if (desiredColorKey != null) {
                        put(CalendarContract.Events.EVENT_COLOR_KEY, desiredColorKey)
                    } else {
                        putNull(CalendarContract.Events.EVENT_COLOR_KEY)
                    }
                    put(CalendarContract.Events.ALL_DAY, if (shift.isAllDayLeave) 1 else 0)
                    put(CalendarContract.Events.EVENT_TIMEZONE, if (shift.isAllDayLeave) "UTC" else TimeZone.getDefault().id)
                    put(CalendarContract.Events.DTSTART, effectiveStartMs)
                    put(CalendarContract.Events.DTEND, newEndMs)
                }
                resolver.update(uri, values, null, null)

                detectedChanges.add(
                    CalendarChangeItem(
                        id = UUID.randomUUID().toString(),
                        type = ChangeType.MODIFIED,
                        calendarId = calendarId,
                        eventId = targetMatch.eventId,
                        title = desiredTitle,
                        startMs = effectiveStartMs,
                        endMs = newEndMs,"""

        if old_update_block in sync and "effectiveStartMs" not in sync:
            sync = sync.replace(old_update_block, new_update_block, 1)

        old_removed_loop = """        for (removedEx in unmatchedOwned) {
            val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, removedEx.eventId)"""

        new_removed_loop = """        for (removedEx in unmatchedOwned) {
            if (removedEx.startMs <= nowMs) continue
            val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, removedEx.eventId)"""

        if old_removed_loop in sync and "if (removedEx.startMs <= nowMs) continue" not in sync:
            sync = sync.replace(old_removed_loop, new_removed_loop, 1)

        old_notif_call = """        if (detectedChanges.isNotEmpty()) {
            CalendarChangeTracker.saveChanges(context, detectedChanges)
            ShiftReminderReceiver.showCalendarChangesNotification(context, detectedChanges)
        }"""

        new_notif_call = """        if (detectedChanges.isNotEmpty()) {
            CalendarChangeTracker.saveChanges(context, detectedChanges)
        }"""

        if old_notif_call in sync:
            sync = sync.replace(old_notif_call, new_notif_call, 1)

        old_alarm_loop = """        val sortedShifts = userShifts.sortedBy { it.startMs }
        val maxGapMs = 15L * 60_000L
        var earliestNextTriggerMs = Long.MAX_VALUE
        var earliestNextLabel = ""

        for (i in sortedShifts.indices) {
            val current = sortedShifts[i]
            val prev = if (i > 0) sortedShifts[i - 1] else null
            val next = if (i < sortedShifts.lastIndex) sortedShifts[i + 1] else null

            val continuesFromPrev = prev != null && (current.startMs - prev.endMs) in (-maxGapMs)..maxGapMs
            val continuesToNext = next != null && (next.startMs - current.endMs) in (-maxGapMs)..maxGapMs

            if (!continuesFromPrev) {
                val startTrigger = current.startMs - (minutesBefore * 60_000L)
                if (startTrigger > now) {
                    val startStr = Instant.ofEpochMilli(current.startMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                    setExactAlarmSafe(context, alarmManager, startTrigger, current.displayTitle, startStr, isEnding = false)
                    if (startTrigger < earliestNextTriggerMs) {
                        earliestNextTriggerMs = startTrigger
                        earliestNextLabel = "Sisään (${current.displayTitle}, vuoro klo $startStr)"
                    }
                }
            }

            if (!continuesToNext) {
                val endTrigger = current.endMs - (minutesBefore * 60_000L)
                if (endTrigger > now) {
                    val endStr = Instant.ofEpochMilli(current.endMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                    setExactAlarmSafe(context, alarmManager, endTrigger, current.displayTitle, endStr, isEnding = true)
                    if (endTrigger < earliestNextTriggerMs) {
                        earliestNextTriggerMs = endTrigger
                        earliestNextLabel = "Ulos (${current.displayTitle}, päättyy klo $endStr)"
                    }
                }
            }
        }

        prefs.edit().apply {
            if (earliestNextTriggerMs < Long.MAX_VALUE) {
                putLong("next_reminder_ms", earliestNextTriggerMs)
                putString("next_reminder_label", earliestNextLabel)
            } else {
                remove("next_reminder_ms")
                remove("next_reminder_label")
            }
        }.apply()
    }

    private fun setExactAlarmSafe(
        context: Context,
        alarmManager: AlarmManager,
        triggerMs: Long,
        title: String,
        timeStr: String,
        isEnding: Boolean
    ) {
        val reqCode = ((triggerMs / 60_000L) + if (isEnding) 1 else 0).toInt()
        val intent = Intent(context, ShiftReminderReceiver::class.java).apply {
            putExtra("SHIFT_TITLE", title)
            putExtra("SHIFT_TIME", timeStr)
            putExtra("IS_ENDING", isEnding)
        }
        val pi = PendingIntent.getBroadcast(
            context,
            reqCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !alarmManager.canScheduleExactAlarms()) {
                alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerMs, pi)
            } else {
                alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerMs, pi)
            }
        } catch (_: SecurityException) {
            alarmManager.set(AlarmManager.RTC_WAKEUP, triggerMs, pi)
        }
    }"""

        new_alarm_loop = """        val sortedShifts = userShifts.sortedBy { it.startMs }
        val maxGapMs = 15L * 60_000L
        var earliestNextTriggerMs = Long.MAX_VALUE
        var earliestNextLabel = ""
        val newReqCodes = mutableSetOf<String>()

        for (i in sortedShifts.indices) {
            val current = sortedShifts[i]
            val prev = if (i > 0) sortedShifts[i - 1] else null
            val next = if (i < sortedShifts.lastIndex) sortedShifts[i + 1] else null

            val continuesFromPrev = prev != null && (current.startMs - prev.endMs) in (-maxGapMs)..maxGapMs
            val continuesToNext = next != null && (next.startMs - current.endMs) in (-maxGapMs)..maxGapMs

            if (!continuesFromPrev) {
                val startTrigger = current.startMs - (minutesBefore * 60_000L)
                if (startTrigger > now) {
                    val startStr = Instant.ofEpochMilli(current.startMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                    val code = setExactAlarmSafe(context, alarmManager, startTrigger, current.displayTitle, startStr, isEnding = false)
                    newReqCodes.add(code.toString())
                    if (startTrigger < earliestNextTriggerMs) {
                        earliestNextTriggerMs = startTrigger
                        earliestNextLabel = "Sisään (${current.displayTitle}, vuoro klo $startStr)"
                    }
                }
            }

            if (!continuesToNext) {
                val endTrigger = current.endMs - (minutesBefore * 60_000L)
                if (endTrigger > now) {
                    val endStr = Instant.ofEpochMilli(current.endMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                    val code = setExactAlarmSafe(context, alarmManager, endTrigger, current.displayTitle, endStr, isEnding = true)
                    newReqCodes.add(code.toString())
                    if (endTrigger < earliestNextTriggerMs) {
                        earliestNextTriggerMs = endTrigger
                        earliestNextLabel = "Ulos (${current.displayTitle}, päättyy klo $endStr)"
                    }
                }
            }
        }

        val oldReqCodes = prefs.getStringSet("scheduled_alarm_req_codes", emptySet()) ?: emptySet()
        for (oldCodeStr in oldReqCodes) {
            if (oldCodeStr !in newReqCodes) {
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
        }

        prefs.edit().apply {
            putStringSet("scheduled_alarm_req_codes", newReqCodes)
            if (earliestNextTriggerMs < Long.MAX_VALUE) {
                putLong("next_reminder_ms", earliestNextTriggerMs)
                putString("next_reminder_label", earliestNextLabel)
            } else {
                remove("next_reminder_ms")
                remove("next_reminder_label")
            }
        }.apply()
    }

    private fun setExactAlarmSafe(
        context: Context,
        alarmManager: AlarmManager,
        triggerMs: Long,
        title: String,
        timeStr: String,
        isEnding: Boolean
    ): Int {
        val reqCode = ((triggerMs / 60_000L) + if (isEnding) 1 else 0).toInt()
        val intent = Intent(context, ShiftReminderReceiver::class.java).apply {
            putExtra("SHIFT_TITLE", title)
            putExtra("SHIFT_TIME", timeStr)
            putExtra("IS_ENDING", isEnding)
        }
        val pi = PendingIntent.getBroadcast(
            context,
            reqCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !alarmManager.canScheduleExactAlarms()) {
                alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerMs, pi)
            } else {
                alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerMs, pi)
            }
        } catch (_: SecurityException) {
            alarmManager.set(AlarmManager.RTC_WAKEUP, triggerMs, pi)
        }
        return reqCode
    }"""

        if old_alarm_loop in sync:
            sync = sync.replace(old_alarm_loop, new_alarm_loop, 1)

        if sync != orig_sync:
            with open(sync_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(sync)
            print(f"Päivitetty: {sync_path}")

    # 3. MainActivity.kt: leimauksen vahvistus, istunnon aikaleima, WebView cleanup, turvallinen tyyppimuunnos
    main_path = "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt"
    if os.path.exists(main_path):
        with open(main_path, "r", encoding="utf-8") as f:
            main = f.read()

        orig_main = main

        for unused_imp in [
            "import android.animation.ValueAnimator\n",
            "import android.graphics.Shader\n",
            "import android.graphics.RenderEffect\n",
        ]:
            main = main.replace(unused_imp, "")

        old_page_finished = """                injectDarkTheme(view)
                CookieManager.getInstance().flush()

                when {"""

        new_page_finished = """                injectDarkTheme(view)
                CookieManager.getInstance().flush()
                if (!url.contains("/Login/", ignoreCase = true)) {
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                }

                when {"""

        if old_page_finished in main and "last_valid_session_ms" not in main.split("override fun onPageFinished")[1]:
            main = main.replace(old_page_finished, new_page_finished, 1)

        old_stamp_fn = """    private fun handleStampingPage(attempt: Int = 0) {
        if (pendingAction != Action.STAMP_IN && pendingAction != Action.STAMP_OUT) return

        val targetText = if (pendingAction == Action.STAMP_IN) "Sisään" else "Ulos"
        val targetLower = targetText.lowercase()

        val js = \"\"\"
            (function() {
                var btn = document.getElementById('punchButton');
                if (!btn) return 'NO_BUTTON';
                var btnText = (btn.innerText || btn.textContent || '').trim();
                if (!btnText) return 'NO_BUTTON';
                if (btnText.toLowerCase().indexOf('$targetLower') !== -1) {
                    btn.click();
                    return 'STAMPED_' + btnText;
                } else {
                    return 'WRONG_DIRECTION_' + btnText;
                }
            })();
        \"\"\".trimIndent()

        webView.evaluateJavascript(js) { result ->
            val cleanResult = (result ?: "").replace("\\"", "")
            when {
                cleanResult.startsWith("STAMPED_") -> {
                    pendingAction = Action.NONE
                    Toast.makeText(this, "Leimaus suoritettu ($targetText)", Toast.LENGTH_SHORT).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                }
                cleanResult.startsWith("WRONG_DIRECTION_") -> {
                    pendingAction = Action.NONE
                    Toast.makeText(this, "Olet jo leimannut tilaan: $targetText", Toast.LENGTH_LONG).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                }
                cleanResult == "NO_BUTTON" && attempt < 10 -> {
                    webView.postDelayed({ handleStampingPage(attempt + 1) }, 300L)
                }
                else -> {
                    pendingAction = Action.NONE
                }
            }
        }
    }"""

        new_stamp_fn = """    private fun handleStampingPage(attempt: Int = 0) {
        if (pendingAction != Action.STAMP_IN && pendingAction != Action.STAMP_OUT) return

        val targetText = if (pendingAction == Action.STAMP_IN) "Sisään" else "Ulos"
        val targetLower = targetText.lowercase()

        val js = \"\"\"
            (function() {
                var btn = document.getElementById('punchButton');
                if (!btn) return JSON.stringify({ status: 'NO_BUTTON' });
                var btnText = (btn.innerText || btn.textContent || '').trim();
                if (!btnText) return JSON.stringify({ status: 'NO_BUTTON' });
                var firstRow = '';
                var rowEl = document.querySelector('#table-latest-stamps tbody tr, #table-latest-stamps tr');
                if (rowEl) {
                    firstRow = (rowEl.innerText || rowEl.textContent || '').replace(/\\s+/g, ' ').trim();
                }
                if (btnText.toLowerCase().indexOf('$targetLower') !== -1) {
                    btn.click();
                    return JSON.stringify({ status: 'CLICKED', btn: btnText, row: firstRow });
                } else {
                    return JSON.stringify({ status: 'WRONG_DIRECTION', btn: btnText, row: firstRow });
                }
            })();
        \"\"\".trimIndent()

        webView.evaluateJavascript(js) { rawResult ->
            val unescaped = try {
                if (rawResult != null && rawResult != "null") JSONTokener(rawResult).nextValue() as? String else null
            } catch (_: Exception) {
                null
            }
            val obj = try {
                if (unescaped != null) org.json.JSONObject(unescaped) else null
            } catch (_: Exception) {
                null
            }
            val status = obj?.optString("status", "") ?: ""

            when {
                status == "CLICKED" -> {
                    pendingAction = Action.NONE
                    val beforeBtn = obj?.optString("btn", "") ?: ""
                    val beforeRow = obj?.optString("row", "") ?: ""
                    Toast.makeText(this, "Leimataan ($targetText)...", Toast.LENGTH_SHORT).show()
                    verifyStampAndClose(targetText, beforeBtn, beforeRow, 0)
                }
                status == "WRONG_DIRECTION" -> {
                    pendingAction = Action.NONE
                    Toast.makeText(this, "Olet jo leimannut tilaan: $targetText", Toast.LENGTH_LONG).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                }
                status == "NO_BUTTON" && attempt < 10 -> {
                    webView.postDelayed({ handleStampingPage(attempt + 1) }, 300L)
                }
                else -> {
                    pendingAction = Action.NONE
                }
            }
        }
    }

    private fun verifyStampAndClose(
        targetText: String,
        beforeBtn: String,
        beforeRow: String,
        checkAttempt: Int
    ) {
        val targetLower = targetText.lowercase()
        val verifyJs = \"\"\"
            (function() {
                var btn = document.getElementById('punchButton');
                var btnText = btn ? (btn.innerText || btn.textContent || '').trim() : '';
                var rowEl = document.querySelector('#table-latest-stamps tbody tr, #table-latest-stamps tr');
                var firstRow = rowEl ? (rowEl.innerText || rowEl.textContent || '').replace(/\\s+/g, ' ').trim() : '';
                return JSON.stringify({ btn: btnText, row: firstRow });
            })();
        \"\"\".trimIndent()

        webView.postDelayed({
            if (isFinishing || isDestroyed) return@postDelayed
            webView.evaluateJavascript(verifyJs) { rawResult ->
                val unescaped = try {
                    if (rawResult != null && rawResult != "null") JSONTokener(rawResult).nextValue() as? String else null
                } catch (_: Exception) {
                    null
                }
                val obj = try {
                    if (unescaped != null) org.json.JSONObject(unescaped) else null
                } catch (_: Exception) {
                    null
                }
                val nowBtn = obj?.optString("btn", "") ?: ""
                val nowRow = obj?.optString("row", "") ?: ""

                val buttonFlipped = nowBtn.isNotEmpty() && nowBtn != beforeBtn &&
                    nowBtn.lowercase().indexOf(targetLower) == -1
                val rowUpdated = nowRow.isNotEmpty() && nowRow != beforeRow

                if (buttonFlipped || rowUpdated) {
                    CookieManager.getInstance().flush()
                    Toast.makeText(this, "Leimaus vahvistettu ($targetText)", Toast.LENGTH_SHORT).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 600L)
                } else if (checkAttempt < 25) {
                    verifyStampAndClose(targetText, beforeBtn, beforeRow, checkAttempt + 1)
                } else {
                    Toast.makeText(
                        this,
                        "Leimausta ei voitu vahvistaa automaattisesti – tarkista tila ruudulta",
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        }, 300L)
    }"""

        if old_stamp_fn in main:
            main = main.replace(old_stamp_fn, new_stamp_fn, 1)

        old_cal_cast = """            val unescapedHtml = JSONTokener(rawHtml).nextValue() as String"""
        new_cal_cast = """            val unescapedHtml = JSONTokener(rawHtml).nextValue() as? String ?: return@evaluateJavascript"""
        if old_cal_cast in main:
            main = main.replace(old_cal_cast, new_cal_cast, 1)

        old_destroy = """    override fun onDestroy() {
        super.onDestroy()
        try {
            CookieManager.getInstance().flush()
        } catch (_: Exception) {}
        scope.cancel()
    }"""

        new_destroy = """    override fun onDestroy() {
        try {
            CookieManager.getInstance().flush()
        } catch (_: Exception) {}
        try {
            (webView.parent as? ViewGroup)?.removeView(webView)
            webView.stopLoading()
            webView.destroy()
        } catch (_: Exception) {}
        scope.cancel()
        super.onDestroy()
    }"""

        if old_destroy in main:
            main = main.replace(old_destroy, new_destroy, 1)

        if main != orig_main:
            with open(main_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(main)
            print(f"Päivitetty: {main_path}")

    # 4. CalendarChangeTracker.kt: loppupäivän korjaus (-1/+1 pv) ja hälytysten päivitys
    tracker_path = "app/src/main/java/fi/numeron/vuorovahti/CalendarChangeTracker.kt"
    if os.path.exists(tracker_path):
        with open(tracker_path, "r", encoding="utf-8") as f:
            trk = f.read()

        orig_trk = trk

        old_save_rem = """            val remaining = getLastChanges(context).filterNot { it.id == item.id }
            saveChanges(context, remaining)
            true"""

        new_save_rem = """            val remaining = getLastChanges(context).filterNot { it.id == item.id }
            saveChanges(context, remaining)
            CalendarSyncHelper.getTargetCalendarId(context)?.let { calId ->
                CalendarSyncHelper.scheduleShiftReminders(context, calId)
            }
            true"""

        if old_save_rem in trk and "scheduleShiftReminders" not in trk:
            trk = trk.replace(old_save_rem, new_save_rem, 1)

        old_save_upd = """            val updatedList = getLastChanges(context).map { if (it.id == item.id) updatedItem else it }
            saveChanges(context, updatedList)
            true"""

        new_save_upd = """            val updatedList = getLastChanges(context).map { if (it.id == item.id) updatedItem else it }
            saveChanges(context, updatedList)
            CalendarSyncHelper.getTargetCalendarId(context)?.let { calId ->
                CalendarSyncHelper.scheduleShiftReminders(context, calId)
            }
            true"""

        if old_save_upd in trk:
            trk = trk.replace(old_save_upd, new_save_upd, 1)

        old_sel_end = """        var selectedEnd = if (item.isAllDay) {
            Instant.ofEpochMilli(item.endMs).atZone(ZoneOffset.UTC).toLocalDateTime()
        } else {
            Instant.ofEpochMilli(item.endMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
        }"""

        new_sel_end = """        var selectedEnd = if (item.isAllDay) {
            Instant.ofEpochMilli(item.endMs).atZone(ZoneOffset.UTC).toLocalDateTime().minusDays(1)
        } else {
            Instant.ofEpochMilli(item.endMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
        }"""

        if old_sel_end in trk:
            trk = trk.replace(old_sel_end, new_sel_end, 1)

        old_allday_calc = """            if (allDay) {
                val sDate = selectedStart.toLocalDate()
                var eDate = selectedEnd.toLocalDate()
                if (!eDate.isAfter(sDate)) eDate = sDate.plusDays(1)
                finalStartMs = sDate.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli()
                finalEndMs = eDate.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli()
            }"""

        new_allday_calc = """            if (allDay) {
                val sDate = selectedStart.toLocalDate()
                var eDate = selectedEnd.toLocalDate()
                if (eDate.isBefore(sDate)) eDate = sDate
                finalStartMs = sDate.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli()
                finalEndMs = eDate.plusDays(1).atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli()
            }"""

        if old_allday_calc in trk:
            trk = trk.replace(old_allday_calc, new_allday_calc, 1)

        if trk != orig_trk:
            with open(tracker_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(trk)
            print(f"Päivitetty: {tracker_path}")

    # 5. ShiftReminderReceiver.kt: poista kuollut ACTION_QUICK_STAMP ja siirrä toivehaku IO-säikeelle
    rec_path = "app/src/main/java/fi/numeron/vuorovahti/ShiftReminderReceiver.kt"
    if os.path.exists(rec_path):
        with open(rec_path, "r", encoding="utf-8") as f:
            rec = f.read()

        orig_rec = rec

        old_dead_branch = """        // 2. Käyttäjä painoi ilmoituksen "Leimaa sisään/ulos" -painiketta
        if (action == ACTION_QUICK_STAMP) {
            val isEnding = intent.getBooleanExtra("IS_ENDING", false)
            val isTest = intent.getBooleanExtra("IS_TEST", false)
            val notifId = intent.getIntExtra("NOTIF_ID", 1001)
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.cancel(notifId)

            val launchIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra("AUTO_STAMP", true)
                putExtra("IS_ENDING", isEnding)
                putExtra("IS_TEST", isTest)
            }
            context.startActivity(launchIntent)
            return
        }

"""
        if old_dead_branch in rec:
            rec = rec.replace(old_dead_branch, "", 1)

        rec = rec.replace('        const val ACTION_QUICK_STAMP = "fi.numeron.vuorovahti.ACTION_QUICK_STAMP"\n', "")

        old_worker_sync = """        data class SyncPayload(val htmlPages: List<String>, val requestsJson: String?)

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
                                    } else if (trackRequests) {
                                        val jsFetchRequests = \"\"\"
                                            (function() {
                                                var xhr = new XMLHttpRequest();
                                                xhr.open('POST', '/PersonRequests/Read?selectedFilter=active', false);
                                                xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                                                xhr.send('page=1&pageSize=50');
                                                return xhr.responseText;
                                            })();
                                        \"\"\".trimIndent()
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
            CookieManager.getInstance().flush()
            val changes = withContext(Dispatchers.IO) {
                val allShifts = payload.htmlPages.flatMap { NumeronParser.parseCalendarHtml(it) }
                val detectedChanges = CalendarSyncHelper.syncShiftsToCalendar(appContext, calId, allShifts)
                payload.requestsJson?.let { checkRequestUpdates(it) }
                detectedChanges
            }"""

        new_worker_sync = """        val htmlPages = suspendCancellableCoroutine<List<String>> { continuation ->
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
                if (trackRequests) {
                    fetchRequestsJson(baseUrl)?.let { checkRequestUpdates(it) }
                }
                detectedChanges
            }"""

        if old_worker_sync in rec:
            rec = rec.replace(old_worker_sync, new_worker_sync, 1)

        old_check_req = """    private fun checkRequestUpdates(jsonStr: String) {"""
        new_check_req = """    private fun fetchRequestsJson(baseUrl: String): String? {
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

    private fun checkRequestUpdates(jsonStr: String) {"""

        if old_check_req in rec and "fetchRequestsJson" not in rec:
            rec = rec.replace(old_check_req, new_check_req, 1)

        if rec != orig_rec:
            with open(rec_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(rec)
            print(f"Päivitetty: {rec_path}")

    # 6. NumeronParser.kt: turvallinen aikojen jäsennys
    parser_path = "app/src/main/java/fi/numeron/vuorovahti/NumeronParser.kt"
    if os.path.exists(parser_path):
        with open(parser_path, "r", encoding="utf-8") as f:
            prs = f.read()

        old_time_parse = """                val timeParts = timesText.split("-").map { it.trim() }
                if (timeParts.size == 2) {
                    val startTime = LocalTime.parse(timeParts[0], DateTimeFormatter.ofPattern("H:mm"))
                    val endTime = LocalTime.parse(timeParts[1], DateTimeFormatter.ofPattern("H:mm"))"""

        new_time_parse = """                val timeParts = timesText.split("-").map { it.trim() }
                if (timeParts.size == 2) {
                    val startTime = try {
                        LocalTime.parse(timeParts[0], DateTimeFormatter.ofPattern("H:mm"))
                    } catch (_: Exception) {
                        return@forEach
                    }
                    val endTime = try {
                        LocalTime.parse(timeParts[1], DateTimeFormatter.ofPattern("H:mm"))
                    } catch (_: Exception) {
                        return@forEach
                    }"""

        if old_time_parse in prs:
            prs = prs.replace(old_time_parse, new_time_parse, 1)
            with open(parser_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(prs)
            print(f"Päivitetty: {parser_path}")

    # 7. SettingsDialogHelper.kt: yhteystestin aikakatkaisu + evästeiden palautus epäonnistuessa
    settings_path = "app/src/main/java/fi/numeron/vuorovahti/SettingsDialogHelper.kt"
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            st = f.read()

        old_test_setup = """        CookieManager.getInstance().removeAllCookies(null)

        var loginAttempted = false
        var finished = false

        fun cleanupAndRespond(success: Boolean, msg: String) {
            if (finished) return
            finished = true
            testWebView.stopLoading()
            testWebView.destroy()
            callback(success, msg)
        }"""

        new_test_setup = """        val cm = CookieManager.getInstance()
        val previousCookies = cm.getCookie(baseUrl)
        cm.removeAllCookies(null)
        cm.flush()

        var loginAttempted = false
        var finished = false
        val timeoutHandler = android.os.Handler(android.os.Looper.getMainLooper())
        lateinit var timeoutRunnable: Runnable

        fun cleanupAndRespond(success: Boolean, msg: String) {
            if (finished) return
            finished = true
            timeoutHandler.removeCallbacks(timeoutRunnable)
            if (!success && !previousCookies.isNullOrBlank()) {
                previousCookies.split(";").forEach { cookie ->
                    val trimmed = cookie.trim()
                    if (trimmed.isNotEmpty()) {
                        cm.setCookie(baseUrl, trimmed)
                    }
                }
                cm.flush()
            }
            testWebView.stopLoading()
            testWebView.destroy()
            callback(success, msg)
        }

        timeoutRunnable = Runnable {
            cleanupAndRespond(false, "Aikakatkaisu: Palvelin '$baseUrl' ei vastannut ajoissa.")
        }
        timeoutHandler.postDelayed(timeoutRunnable, 15_000L)"""

        if old_test_setup in st:
            st = st.replace(old_test_setup, new_test_setup, 1)
            with open(settings_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(st)
            print(f"Päivitetty: {settings_path}")
# ==============================================================================
# === POISTETTAVA KORJAUSOSIO PÄÄTTYY ===
# ==============================================================================


if __name__ == "__main__":
    bump_version_code()
    apply_codebase_fixes()
