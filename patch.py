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
# === POISTETTAVA KORJAUSOSIO ALKAA (Poista tämä lohko kun korjaukset on ajettu) ===
# ==============================================================================
def apply_one_time_fixes():
    # 1. MainActivity.kt: säilytä evästeet suljettaessa ja tallenna ne levylle
    main_path = "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt"
    if os.path.exists(main_path):
        with open(main_path, "r", encoding="utf-8") as f:
            main_content = f.read()

        orig_main = main_content

        # Tallenna evästeet levylle sivun latauduttua
        old_page_finish = """                injectDarkTheme(view)

                when {"""
        new_page_finish = """                injectDarkTheme(view)
                CookieManager.getInstance().flush()

                when {"""
        if old_page_finish in main_content and "CookieManager.getInstance().flush()\n\n                when {" not in main_content:
            main_content = main_content.replace(old_page_finish, new_page_finish, 1)

        # Älä poista evästeitä sovelluksen sulkeutuessa
        old_destroy = """    override fun onDestroy() {
        super.onDestroy()
        try {
            CookieManager.getInstance().removeAllCookies(null)
            CookieManager.getInstance().flush()
        } catch (_: Exception) {}
        scope.cancel()
    }"""
        new_destroy = """    override fun onDestroy() {
        super.onDestroy()
        try {
            CookieManager.getInstance().flush()
        } catch (_: Exception) {}
        scope.cancel()
    }"""
        if old_destroy in main_content:
            main_content = main_content.replace(old_destroy, new_destroy, 1)

        if main_content != orig_main:
            with open(main_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(main_content)
            print(f"Päivitetty: {main_path}")

    # 2. ShiftReminderReceiver.kt: SecureCredentialManager + ilmoitukset + evästeiden tallennus
    receiver_path = "app/src/main/java/fi/numeron/vuorovahti/ShiftReminderReceiver.kt"
    if os.path.exists(receiver_path):
        with open(receiver_path, "r", encoding="utf-8") as f:
            rec_content = f.read()

        orig_rec = rec_content

        # Lisää FLAG_ACTIVITY_NEW_TASK toiveilmoituksen avaamiseen
        old_req_intent = """            val openIntent = Intent(context, MainActivity::class.java).apply {
                putExtra("OPEN_REQUESTS", true)
            }"""
        new_req_intent = """            val openIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra("OPEN_REQUESTS", true)
            }"""
        if old_req_intent in rec_content:
            rec_content = rec_content.replace(old_req_intent, new_req_intent, 1)

        # Hae tunnukset SecureCredentialManagerista ja suojaa erikoismerkit
        old_creds = """        val prefs = appContext.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val user = prefs.getString("username", "") ?: ""
        val pass = prefs.getString("password", "") ?: ""
        val baseUrl = UrlNormalizer.getSavedBaseUrl(appContext)
        val trackRequests = prefs.getBoolean("track_requests", true)

        if (user.isEmpty() || pass.isEmpty() || baseUrl.isEmpty()) return@withContext Result.failure()"""
        new_creds = """        val prefs = appContext.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val rawUser = SecureCredentialManager.getUsername(appContext) ?: ""
        val rawPass = SecureCredentialManager.getPassword(appContext) ?: ""
        val user = rawUser.replace("\\\\", "\\\\\\\\").replace("'", "\\\\'")
        val pass = rawPass.replace("\\\\", "\\\\\\\\").replace("'", "\\\\'")
        val baseUrl = UrlNormalizer.getSavedBaseUrl(appContext)
        val trackRequests = prefs.getBoolean("track_requests", true)

        if (rawUser.isEmpty() || rawPass.isEmpty() || baseUrl.isEmpty()) return@withContext Result.failure()"""
        if old_creds in rec_content:
            rec_content = rec_content.replace(old_creds, new_creds, 1)

        # Tallenna evästeet levylle, päivitä last_calendar_sync_ms ja ilmoita kalenterimuutoksista
        old_sync_finish = """        if (payload.htmlPages.isNotEmpty()) {
            withContext(Dispatchers.IO) {
                val allShifts = payload.htmlPages.flatMap { NumeronParser.parseCalendarHtml(it) }
                CalendarSyncHelper.syncShiftsToCalendar(appContext, calId, allShifts)
                payload.requestsJson?.let { checkRequestUpdates(it) }
            }
            CalendarSyncHelper.scheduleShiftReminders(appContext, calId)
            prefs.edit()
                .putLong("next_calendar_sync_ms", System.currentTimeMillis() + TimeUnit.HOURS.toMillis(12))
                .apply()
            Result.success()"""
        new_sync_finish = """        if (payload.htmlPages.isNotEmpty()) {
            CookieManager.getInstance().flush()
            val changes = withContext(Dispatchers.IO) {
                val allShifts = payload.htmlPages.flatMap { NumeronParser.parseCalendarHtml(it) }
                val detectedChanges = CalendarSyncHelper.syncShiftsToCalendar(appContext, calId, allShifts)
                payload.requestsJson?.let { checkRequestUpdates(it) }
                detectedChanges
            }
            if (changes.isNotEmpty()) {
                ShiftReminderReceiver.showCalendarChangesNotification(appContext, changes)
            }
            CalendarSyncHelper.scheduleShiftReminders(appContext, calId)
            val nowMs = System.currentTimeMillis()
            prefs.edit()
                .putLong("last_calendar_sync_ms", nowMs)
                .putLong("next_calendar_sync_ms", nowMs + TimeUnit.HOURS.toMillis(12))
                .apply()
            Result.success()"""
        if old_sync_finish in rec_content:
            rec_content = rec_content.replace(old_sync_finish, new_sync_finish, 1)

        if rec_content != orig_rec:
            with open(receiver_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(rec_content)
            print(f"Päivitetty: {receiver_path}")
# ==============================================================================
# === POISTETTAVA KORJAUSOSIO PÄÄTTYY ===
# ==============================================================================


if __name__ == "__main__":
    bump_version_code()
    apply_one_time_fixes()
