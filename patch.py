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
def fix_shift_reminder_receiver():
    rec_path = "app/src/main/java/fi/numeron/vuorovahti/ShiftReminderReceiver.kt"
    if not os.path.exists(rec_path):
        print(f"Virhe: {rec_path} ei löytynyt.")
        return

    with open(rec_path, "r", encoding="utf-8") as f:
        rec = f.read()

    orig_rec = rec

    old_block = """        if (htmlPages.isNotEmpty()) {
            CookieManager.getInstance().flush()
            val changes = withContext(Dispatchers.IO) {
                val allShifts = htmlPages.flatMap { NumeronParser.parseCalendarHtml(it) }
                val detectedChanges = CalendarSyncHelper.syncShiftsToCalendar(appContext, calId, allShifts)
                if (trackRequests) {
                    fetchRequestsJson(baseUrl)?.let { checkRequestUpdates(it) }
                }
                detectedChanges
            }
            if (changes.isNotEmpty()) {
                ShiftReminderReceiver.showCalendarChangesNotification(appContext, changes)
            }
            CalendarSyncHelper.scheduleShiftReminders(appContext, calId)
            val nowMs = System.currentTimeMillis()
            prefs.edit()
                .putLong("last_calendar_sync_ms", nowMs)
                .putLong("last_valid_session_ms", nowMs)
                .apply()
            ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext)
            Result.success()
        } else {
            ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext)
            Result.success()
        }
    }

    private fun checkRequestUpdates(jsonStr: String) {"""

    new_block = """        if (htmlPages.isNotEmpty()) {
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

    private fun checkRequestUpdates(jsonStr: String) {"""

    if old_block in rec and "private fun fetchRequestsJson(" not in rec:
        rec = rec.replace(old_block, new_block, 1)

    if rec != orig_rec:
        with open(rec_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(rec)
        print(f"Päivitetty: {rec_path}")
# ==============================================================================
# === POISTETTAVA KORJAUSOSIO PÄÄTTYY ===
# ==============================================================================


if __name__ == "__main__":
    bump_version_code()
    fix_shift_reminder_receiver()
