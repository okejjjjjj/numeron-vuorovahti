#!/usr/bin/env python3
"""
Numeron Vuorovahti – automaattinen korjaus- ja optimointipäivitys (patch.py).
Turvallinen ajaa useita kertoja (idempotentti).
"""

from pathlib import Path
import sys


def find_file(root: Path, filename: str) -> Path | None:
    direct = root / filename
    if direct.is_file():
        return direct
    matches = [p for p in root.rglob(filename) if ".git" not in p.parts and "build" not in p.parts]
    return matches[0] if matches else None


def replace_exact(content: str, old: str, new: str, label: str, already_marker: str | None = None) -> tuple[str, bool]:
    if already_marker and already_marker in content:
        print(f"  [OHITETTU] {label} (on jo päivitetty)")
        return content, False
    if new in content:
        print(f"  [OHITETTU] {label} (on jo päivitetty)")
        return content, False
    count = content.count(old)
    if count == 0:
        raise RuntimeError(f"Kohdetta ei löytynyt: {label}")
    if count > 1:
        raise RuntimeError(f"Kohde ei ole yksikäsitteinen ({count} osumaa): {label}")
    print(f"  [OK] {label}")
    return content.replace(old, new, 1), True


def patch_android_manifest(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = r'''        <receiver
            android:name=".ShiftReminderReceiver"
            android:enabled="true"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.BOOT_COMPLETED" />
                <action android:name="android.intent.action.MY_PACKAGE_REPLACED" />
            </intent-filter>
        </receiver>'''
    new = r'''        <receiver
            android:name=".ShiftReminderReceiver"
            android:enabled="true"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.BOOT_COMPLETED" />
                <action android:name="android.intent.action.MY_PACKAGE_REPLACED" />
            </intent-filter>
        </receiver>

        <receiver
            android:name=".ShiftReminderReceiver$InternalReceiver"
            android:enabled="true"
            android:exported="false" />'''
    updated, changed = replace_exact(
        text,
        old,
        new,
        "AndroidManifest.xml: sisäinen ei-julkinen hälytysvastaanotin",
        already_marker="ShiftReminderReceiver$InternalReceiver",
    )
    if changed:
        path.write_text(updated, encoding="utf-8")


def patch_background_auth_helper(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old_cookies = r'''            // 3. Tallenna evästeet Androidin jaettuun CookieManageriin
            val cm = CookieManager.getInstance()
            cm.setAcceptCookie(true)
            cookieStore.forEach { (name, value) ->
                cm.setCookie(baseUrl, "$name=$value; Path=/; Secure")
            }
            cm.flush()'''
    new_cookies = r'''            // 3. Tallenna evästeet Androidin jaettuun CookieManageriin
            val cm = CookieManager.getInstance()
            cm.setAcceptCookie(true)
            val secureAttr = if (baseUrl.startsWith("https://", ignoreCase = true)) "; Secure" else ""
            cookieStore.forEach { (name, value) ->
                cm.setCookie(baseUrl, "$name=$value; Path=/$secureAttr")
            }
            cm.flush()'''
    text, c1 = replace_exact(text, old_cookies, new_cookies, "BackgroundAuthHelper: ehdollinen Secure-evästemääre")
    old_exec = r'''        repeat(maxRedirects + 1) {
            val conn = (URL(currentUrl).openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = false
                requestMethod = currentMethod
                connectTimeout = 15000
                readTimeout = 15000
                setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36")

                if (cookieStore.isNotEmpty()) {
                    val cookieHeader = cookieStore.entries.joinToString("; ") { "${it.key}=${it.value}" }
                    setRequestProperty("Cookie", cookieHeader)
                }

                if (currentMethod == "POST" && currentBody != null) {
                    doOutput = true
                    setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
                }
            }

            if (currentMethod == "POST" && currentBody != null) {
                OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { it.write(currentBody) }
            }

            val code = conn.responseCode

            conn.headerFields["Set-Cookie"]?.forEach { rawCookie ->
                val pair = rawCookie.substringBefore(";").trim()
                val eqIndex = pair.indexOf('=')
                if (eqIndex > 0) {
                    val name = pair.substring(0, eqIndex).trim()
                    val value = pair.substring(eqIndex + 1).trim()
                    if (value.isNotEmpty()) {
                        cookieStore[name] = value
                    } else {
                        cookieStore.remove(name)
                    }
                }
            }

            if (code in 300..399) {
                val location = conn.getHeaderField("Location") ?: return null
                currentUrl = if (location.startsWith("http")) {
                    location
                } else {
                    URL(URL(currentUrl), location).toString()
                }
                currentMethod = "GET"
                currentBody = null
                conn.disconnect()
            } else {
                val stream = if (code in 200..299) conn.inputStream else conn.errorStream
                val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
                conn.disconnect()
                return HttpResult(currentUrl, code, text)
            }
        }
        return null
    }
}'''
    new_exec = r'''        repeat(maxRedirects + 1) {
            val conn = (URL(currentUrl).openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = false
                requestMethod = currentMethod
                connectTimeout = 15000
                readTimeout = 15000
                setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36")

                if (cookieStore.isNotEmpty()) {
                    val cookieHeader = cookieStore.entries.joinToString("; ") { "${it.key}=${it.value}" }
                    setRequestProperty("Cookie", cookieHeader)
                }

                if (currentMethod == "POST" && currentBody != null) {
                    doOutput = true
                    setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
                }
            }

            try {
                if (currentMethod == "POST" && currentBody != null) {
                    OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { it.write(currentBody) }
                }

                val code = conn.responseCode

                conn.headerFields
                    .filterKeys { it != null && it.equals("Set-Cookie", ignoreCase = true) }
                    .values
                    .flatten()
                    .forEach { rawCookie ->
                        val pair = rawCookie.substringBefore(";").trim()
                        val eqIndex = pair.indexOf('=')
                        if (eqIndex > 0) {
                            val name = pair.substring(0, eqIndex).trim()
                            val value = pair.substring(eqIndex + 1).trim()
                            if (value.isNotEmpty()) {
                                cookieStore[name] = value
                            } else {
                                cookieStore.remove(name)
                            }
                        }
                    }

                if (code in 300..399) {
                    val location = conn.getHeaderField("Location") ?: return null
                    currentUrl = if (location.startsWith("http")) {
                        location
                    } else {
                        URL(URL(currentUrl), location).toString()
                    }
                    currentMethod = "GET"
                    currentBody = null
                } else {
                    val stream = if (code in 200..299) conn.inputStream else conn.errorStream
                    val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
                    return HttpResult(currentUrl, code, text)
                }
            } finally {
                conn.disconnect()
            }
        }
        return null
    }

    fun testCredentials(baseUrl: String, username: String, password: String): Pair<Boolean, String> {
        val cookieStore = mutableMapOf<String, String>()
        return try {
            val initial = executeRequest(
                urlString = "$baseUrl/Login/Login",
                method = "GET",
                cookieStore = cookieStore
            ) ?: return false to "Yhteysvirhe: Organisaatiota '$baseUrl' ei löytynyt tai verkkoyhteys puuttuu."

            val doc = Jsoup.parse(initial.body, initial.finalUrl)
            val form = doc.selectFirst("#LoginForm")
                ?: doc.selectFirst("form:has(input[type=password])")
                ?: return false to "Virhe: Kirjautumislomaketta ei tunnistettu sivulta."

            val actionAttr = form.attr("action").ifBlank { initial.finalUrl }
            val postUrl = if (actionAttr.startsWith("http")) {
                actionAttr
            } else {
                URL(URL(initial.finalUrl), actionAttr).toString()
            }

            val formParams = mutableListOf<Pair<String, String>>()
            form.select("input[type=hidden]").forEach { input ->
                val name = input.attr("name")
                if (name.isNotBlank()) {
                    formParams.add(name to input.attr("value"))
                }
            }

            val userField = form.selectFirst("#Username, input[name=Username], input[type=text]")
                ?.attr("name")
                ?.ifBlank { "Username" } ?: "Username"
            val passField = form.selectFirst("#Password, input[name=Password], input[type=password]")
                ?.attr("name")
                ?.ifBlank { "Password" } ?: "Password"

            formParams.add(userField to username)
            formParams.add(passField to password)

            val encodedBody = formParams.joinToString("&") { (k, v) ->
                "${URLEncoder.encode(k, "UTF-8")}=${URLEncoder.encode(v, "UTF-8")}"
            }

            val loginResp = executeRequest(
                urlString = postUrl,
                method = "POST",
                cookieStore = cookieStore,
                postBody = encodedBody
            ) ?: return false to "Yhteysvirhe kirjautumisen aikana."

            val respDoc = Jsoup.parse(loginResp.body)
            val stillOnLogin = respDoc.selectFirst("#LoginForm, input[type=password]") != null
            if (stillOnLogin || cookieStore.isEmpty()) {
                val errText = respDoc.selectFirst(".validation-summary-errors, .alert-danger")?.text()?.trim().orEmpty()
                if (errText.isNotEmpty()) {
                    false to "Kirjautuminen epäonnistui: $errText"
                } else {
                    false to "Virheellinen käyttäjätunnus tai salasana."
                }
            } else {
                true to "Yhteys ja tunnukset toimivat! ($baseUrl)"
            }
        } catch (e: Exception) {
            false to "Yhteysvirhe: ${e.message ?: "Palvelimeen ei saatu yhteyttä"}"
        }
    }

    suspend fun fetchAuthenticatedPages(context: Context, urls: List<String>): List<String>? = withContext(Dispatchers.IO) {
        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) return@withContext null

        val cookieStore = mutableMapOf<String, String>()
        fun loadFromCookieManager() {
            cookieStore.clear()
            val raw = CookieManager.getInstance().getCookie(baseUrl).orEmpty()
            raw.split(";").forEach { part ->
                val trimmed = part.trim()
                val eq = trimmed.indexOf('=')
                if (eq > 0) {
                    cookieStore[trimmed.substring(0, eq).trim()] = trimmed.substring(eq + 1).trim()
                }
            }
        }

        loadFromCookieManager()
        if (cookieStore.isEmpty()) {
            if (!ensureAuthenticatedSession(context)) return@withContext null
            loadFromCookieManager()
        }

        val results = mutableListOf<String>()
        var reauthed = false

        for (targetUrl in urls) {
            var res = executeRequest(targetUrl, "GET", cookieStore) ?: return@withContext null
            val needsLogin = res.finalUrl.contains("/Login", ignoreCase = true) ||
                res.body.contains("id="LoginForm"", ignoreCase = true)

            if (needsLogin && !reauthed) {
                reauthed = true
                if (!ensureAuthenticatedSession(context)) return@withContext null
                loadFromCookieManager()
                res = executeRequest(targetUrl, "GET", cookieStore) ?: return@withContext null
            }

            if (res.statusCode !in 200..299 ||
                res.finalUrl.contains("/Login", ignoreCase = true) ||
                res.body.contains("id="LoginForm"", ignoreCase = true)
            ) {
                return@withContext null
            }
            results.add(res.body)
        }

        results
    }
}'''
    text, c2 = replace_exact(
        text,
        old_exec,
        new_exec,
        "BackgroundAuthHelper: HTTP/2 Set-Cookie, finally.disconnect sekä testCredentials & fetchAuthenticatedPages",
        already_marker="fun fetchAuthenticatedPages(",
    )
    if c1 or c2:
        path.write_text(text, encoding="utf-8")


def patch_demo_mode_helper(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old_toast_1 = r'''            Toast.makeText(context, "Demoleimaus suoritettu: $actionLabel ($nowTime)", Toast.LENGTH_SHORT).show()'''
    new_toast_1 = r'''            android.os.Handler(android.os.Looper.getMainLooper()).post {
                Toast.makeText(context, "Demoleimaus suoritettu: $actionLabel ($nowTime)", Toast.LENGTH_SHORT).show()
            }'''
    old_toast_2 = r'''            Toast.makeText(context, "Demotoive lisätty: $type", Toast.LENGTH_SHORT).show()'''
    new_toast_2 = r'''            android.os.Handler(android.os.Looper.getMainLooper()).post {
                Toast.makeText(context, "Demotoive lisätty: $type", Toast.LENGTH_SHORT).show()
            }'''
    text, c1 = replace_exact(text, old_toast_1, new_toast_1, "DemoModeHelper: toggleStamp Toast pääsäikeeseen")
    text, c2 = replace_exact(text, old_toast_2, new_toast_2, "DemoModeHelper: addRequest Toast pääsäikeeseen")
    if c1 or c2:
        path.write_text(text, encoding="utf-8")


def patch_calendar_change_tracker(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old_clear = r'''    fun clearChanges(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .remove(KEY_CHANGES)
            .apply()
    }'''
    new_clear = r'''    fun mergeChanges(context: Context, newChanges: List<CalendarChangeItem>) {
        if (newChanges.isEmpty()) return
        val existing = getLastChanges(context).toMutableList()
        for (item in newChanges) {
            if (item.eventId != null) {
                existing.removeAll { it.eventId == item.eventId }
            }
            existing.add(item)
        }
        saveChanges(context, existing)
    }

    fun clearChanges(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .remove(KEY_CHANGES)
            .apply()
    }'''
    text, c1 = replace_exact(text, old_clear, new_clear, "CalendarChangeTracker: mergeChanges-yhdistäminen")
    old_revert = r'''                ChangeType.REMOVED -> {
                    val targetCalId = if (item.calendarId > 0L) {
                        item.calendarId
                    } else {
                        CalendarSyncHelper.getTargetCalendarId(context) ?: -1L
                    }
                    if (targetCalId > 0L) {
                        val values = ContentValues().apply {
                            put(CalendarContract.Events.CALENDAR_ID, targetCalId)
                            put(CalendarContract.Events.TITLE, item.title)
                            put(CalendarContract.Events.DTSTART, item.startMs)
                            put(CalendarContract.Events.DTEND, item.endMs)
                            put(CalendarContract.Events.ALL_DAY, if (item.isAllDay) 1 else 0)
                            put(
                                CalendarContract.Events.EVENT_TIMEZONE,
                                if (item.isAllDay) "UTC" else ZoneId.systemDefault().id
                            )
                        }
                        resolver.insert(CalendarContract.Events.CONTENT_URI, values)
                    }
                }
            }
            val remaining = getLastChanges(context).filterNot { it.id == item.id }
            saveChanges(context, remaining)
            CalendarSyncHelper.getTargetCalendarId(context)?.let { calId ->
                CalendarSyncHelper.scheduleShiftReminders(context, calId)
            }
            true
        } catch (_: Exception) {
            false
        }
    }

    fun revertAllChanges(context: Context): Int {
        val current = getLastChanges(context).toList()
        var count = 0
        for (item in current) {
            if (revertSingleChange(context, item)) {
                count++
            }
        }
        return count
    }'''
    new_revert = r'''                ChangeType.REMOVED -> {
                    val targetCalId = if (item.calendarId > 0L) {
                        item.calendarId
                    } else {
                        CalendarSyncHelper.getTargetCalendarId(context) ?: -1L
                    }
                    if (targetCalId > 0L) {
                        val values = ContentValues().apply {
                            put(CalendarContract.Events.CALENDAR_ID, targetCalId)
                            put(CalendarContract.Events.TITLE, item.title)
                            put(CalendarContract.Events.EVENT_LOCATION, item.location)
                            put(CalendarContract.Events.DESCRIPTION, item.description)
                            put(CalendarContract.Events.DTSTART, item.startMs)
                            put(CalendarContract.Events.DTEND, item.endMs)
                            put(CalendarContract.Events.ALL_DAY, if (item.isAllDay) 1 else 0)
                            put(
                                CalendarContract.Events.EVENT_TIMEZONE,
                                if (item.isAllDay) "UTC" else ZoneId.systemDefault().id
                            )
                        }
                        resolver.insert(CalendarContract.Events.CONTENT_URI, values)
                    }
                }
            }
            true
        } catch (_: Exception) {
            false
        }
    }

    fun revertSingleChangeAndSave(context: Context, item: CalendarChangeItem): Boolean {
        if (!revertSingleChange(context, item)) return false
        val remaining = getLastChanges(context).filterNot { it.id == item.id }
        saveChanges(context, remaining)
        CalendarSyncHelper.getTargetCalendarId(context)?.let { calId ->
            CalendarSyncHelper.scheduleShiftReminders(context, calId)
        }
        return true
    }

    fun revertAllChanges(context: Context): Int {
        val current = getLastChanges(context).toList()
        val succeededIds = mutableSetOf<String>()
        for (item in current) {
            if (revertSingleChange(context, item)) {
                succeededIds.add(item.id)
            }
        }
        if (succeededIds.isNotEmpty()) {
            val remaining = current.filterNot { it.id in succeededIds }
            saveChanges(context, remaining)
            CalendarSyncHelper.getTargetCalendarId(context)?.let { calId ->
                CalendarSyncHelper.scheduleShiftReminders(context, calId)
            }
        }
        return succeededIds.size
    }'''
    text, c2 = replace_exact(
        text,
        old_revert,
        new_revert,
        "CalendarChangeTracker: sijainnin/kuvauksen palautus ja eräkohtainen revertAllChanges",
        already_marker="fun revertSingleChangeAndSave(",
    )
    old_btn_revert = r'''                btnRevert.setOnClickListener {
                    if (revertSingleChange(context, item)) {'''
    new_btn_revert = r'''                btnRevert.setOnClickListener {
                    if (revertSingleChangeAndSave(context, item)) {'''
    text, c3 = replace_exact(text, old_btn_revert, new_btn_revert, "CalendarChangeTracker: yksittäisen muutoksen peruutusnappi")
    old_time_btns = r'''        val btnEndTime = Button(context).apply {
            text = "Loppuaika: ${selectedEnd.format(timeFmt)}"
            stylePickerBtn(this)
        }'''
    new_time_btns = r'''        val btnEndTime = Button(context).apply {
            text = "Loppuaika: ${selectedEnd.format(timeFmt)}"
            stylePickerBtn(this)
        }

        fun updateTimeButtonsVisibility(isAllDayChecked: Boolean) {
            val vis = if (isAllDayChecked) View.GONE else View.VISIBLE
            btnStartTime.visibility = vis
            btnEndTime.visibility = vis
        }
        updateTimeButtonsVisibility(item.isAllDay)
        chkAllDay.setOnCheckedChangeListener { _, isChecked ->
            updateTimeButtonsVisibility(isChecked)
        }'''
    text, c4 = replace_exact(
        text,
        old_time_btns,
        new_time_btns,
        "CalendarChangeTracker: piilota kellonajat koko päivän tapahtumissa",
        already_marker="updateTimeButtonsVisibility",
    )
    if c1 or c2 or c3 or c4:
        path.write_text(text, encoding="utf-8")


def patch_calendar_sync_helper(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old_save = r'''        if (detectedChanges.isNotEmpty()) {
            CalendarChangeTracker.saveChanges(context, detectedChanges)
        }'''
    new_save = r'''        if (detectedChanges.isNotEmpty()) {
            CalendarChangeTracker.mergeChanges(context, detectedChanges)
        }'''
    text, c1 = replace_exact(text, old_save, new_save, "CalendarSyncHelper: mergeChanges kuittaamattomille muutoksille")
    old_cancel = r'''            val cancelIntent = Intent(context, ShiftReminderReceiver::class.java)
            val existingPi = PendingIntent.getBroadcast(
                context,
                oldCode,
                cancelIntent,
                PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE
            )'''
    new_cancel = r'''            val cancelIntent = Intent(context, ShiftReminderReceiver.InternalReceiver::class.java).apply {
                action = ShiftReminderReceiver.ACTION_SHIFT_REMINDER
            }
            val existingPi = PendingIntent.getBroadcast(
                context,
                oldCode,
                cancelIntent,
                PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE
            )'''
    text, c2 = replace_exact(text, old_cancel, new_cancel, "CalendarSyncHelper: cancelAllShiftReminders sisäiselle vastaanottimelle")
    old_cancel_2 = r'''                val cancelIntent = Intent(context, ShiftReminderReceiver::class.java)
                val existingPi = PendingIntent.getBroadcast(
                    context,
                    oldCode,
                    cancelIntent,
                    PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE
                )'''
    new_cancel_2 = r'''                val cancelIntent = Intent(context, ShiftReminderReceiver.InternalReceiver::class.java).apply {
                    action = ShiftReminderReceiver.ACTION_SHIFT_REMINDER
                }
                val existingPi = PendingIntent.getBroadcast(
                    context,
                    oldCode,
                    cancelIntent,
                    PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE
                )'''
    text, c3 = replace_exact(text, old_cancel_2, new_cancel_2, "CalendarSyncHelper: vanhojen hälytysten peruutus sisäiselle vastaanottimelle")
    old_alarm = r'''        val reqCode = ((triggerMs / 60_000L) + if (isEnding) 1 else 0).toInt()
        val intent = Intent(context, ShiftReminderReceiver::class.java).apply {
            putExtra("SHIFT_TITLE", title)
            putExtra("SHIFT_TIME", timeStr)
            putExtra("IS_ENDING", isEnding)
        }'''
    new_alarm = r'''        val reqCode = ((triggerMs / 60_000L).toInt() * 2) + (if (isEnding) 1 else 0)
        val intent = Intent(context, ShiftReminderReceiver.InternalReceiver::class.java).apply {
            action = ShiftReminderReceiver.ACTION_SHIFT_REMINDER
            putExtra("SHIFT_TITLE", title)
            putExtra("SHIFT_TIME", timeStr)
            putExtra("IS_ENDING", isEnding)
        }'''
    text, c4 = replace_exact(text, old_alarm, new_alarm, "CalendarSyncHelper: yksilöllinen requestCode ja sisäinen vastaanotin")
    if c1 or c2 or c3 or c4:
        path.write_text(text, encoding="utf-8")


def patch_secure_credential_manager(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = r'''package fi.numeron.vuorovahti

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

object SecureCredentialManager {

    private const val PREFS_FILE = "secure_numeron_prefs"
    private const val KEY_USERNAME = "secure_username"
    private const val KEY_PASSWORD = "secure_password"

    private fun getEncryptedPrefs(context: Context) = try {
        val masterKey = MasterKey.Builder(context, MasterKey.DEFAULT_MASTER_KEY_ALIAS)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        EncryptedSharedPreferences.create(
            context,
            PREFS_FILE,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    } catch (e: Exception) {
        null
    }

    fun saveCredentials(context: Context, username: String, password: String) {
        getEncryptedPrefs(context)?.edit()?.apply {
            putString(KEY_USERNAME, username)
            putString(KEY_PASSWORD, password)
            apply()
        }
    }

    fun getUsername(context: Context): String? {
        // Fallback vanhoihin suojaamattomiin SharedPreferences-tietoihin migraatiota varten
        getEncryptedPrefs(context)?.getString(KEY_USERNAME, null)?.let { if (it.isNotEmpty()) return it }
        return context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE).getString("username", null)
    }

    fun getPassword(context: Context): String? {
        getEncryptedPrefs(context)?.getString(KEY_PASSWORD, null)?.let { if (it.isNotEmpty()) return it }
        return context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE).getString("password", null)
    }'''
    new = r'''package fi.numeron.vuorovahti

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

object SecureCredentialManager {

    private const val PREFS_FILE = "secure_numeron_prefs"
    private const val KEY_USERNAME = "secure_username"
    private const val KEY_PASSWORD = "secure_password"

    @Volatile
    private var cachedEncryptedPrefs: SharedPreferences? = null

    private fun getEncryptedPrefs(context: Context): SharedPreferences? {
        cachedEncryptedPrefs?.let { return it }
        return synchronized(this) {
            cachedEncryptedPrefs?.let { return@synchronized it }
            try {
                val appCtx = context.applicationContext
                val masterKey = MasterKey.Builder(appCtx, MasterKey.DEFAULT_MASTER_KEY_ALIAS)
                    .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                    .build()

                EncryptedSharedPreferences.create(
                    appCtx,
                    PREFS_FILE,
                    masterKey,
                    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
                ).also { cachedEncryptedPrefs = it }
            } catch (_: Exception) {
                null
            }
        }
    }

    private fun migrateLegacyIfNeeded(context: Context) {
        val legacyPrefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val legacyUser = legacyPrefs.getString("username", null)
        val legacyPass = legacyPrefs.getString("password", null)
        if (!legacyUser.isNullOrEmpty() || !legacyPass.isNullOrEmpty()) {
            val enc = getEncryptedPrefs(context)
            if (enc != null) {
                enc.edit().apply {
                    if (!legacyUser.isNullOrEmpty() && enc.getString(KEY_USERNAME, null).isNullOrEmpty()) {
                        putString(KEY_USERNAME, legacyUser)
                    }
                    if (!legacyPass.isNullOrEmpty() && enc.getString(KEY_PASSWORD, null).isNullOrEmpty()) {
                        putString(KEY_PASSWORD, legacyPass)
                    }
                    apply()
                }
                legacyPrefs.edit().remove("username").remove("password").apply()
            }
        }
    }

    fun saveCredentials(context: Context, username: String, password: String) {
        getEncryptedPrefs(context)?.edit()?.apply {
            putString(KEY_USERNAME, username)
            putString(KEY_PASSWORD, password)
            apply()
        }
        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .remove("username")
            .remove("password")
            .apply()
    }

    fun getUsername(context: Context): String? {
        migrateLegacyIfNeeded(context)
        getEncryptedPrefs(context)?.getString(KEY_USERNAME, null)?.let { if (it.isNotEmpty()) return it }
        return context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE).getString("username", null)
    }

    fun getPassword(context: Context): String? {
        migrateLegacyIfNeeded(context)
        getEncryptedPrefs(context)?.getString(KEY_PASSWORD, null)?.let { if (it.isNotEmpty()) return it }
        return context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE).getString("password", null)
    }'''
    updated, changed = replace_exact(
        text,
        old,
        new,
        "SecureCredentialManager: välimuistitettu EncryptedSharedPreferences ja automaattinen migraatio",
        already_marker="cachedEncryptedPrefs",
    )
    if changed:
        path.write_text(updated, encoding="utf-8")


def patch_numeron_parser(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = r'''    fun parseCalendarHtml(html: String): List<WorkShift> {
        val doc = Jsoup.parse(html)
        val shifts = mutableListOf<WorkShift>()

        val monthHeader = doc.selectFirst("#monthText")?.text()?.trim()?.lowercase() ?: return emptyList()
        val parts = monthHeader.split(" ")
        if (parts.size < 2) return emptyList()

        val currentMonth = finnishMonths[parts[0]] ?: return emptyList()
        val currentYear = parts[1].toIntOrNull() ?: return emptyList()
        val now = LocalDateTime.now()
        val today = now.toLocalDate()

        val dayCells = doc.select("table.month-table td.month-day")'''
    new = r'''    fun parseCalendarHtml(html: String): List<WorkShift>? {
        val doc = Jsoup.parse(html)
        val shifts = mutableListOf<WorkShift>()

        val monthHeader = doc.selectFirst("#monthText")?.text()?.trim()?.lowercase() ?: return null
        val parts = monthHeader.split(Regex("\s+"))
        if (parts.size < 2) return null

        val currentMonth = finnishMonths[parts[0]] ?: return null
        val currentYear = parts[1].toIntOrNull() ?: return null
        val now = LocalDateTime.now()
        val today = now.toLocalDate()

        val dayCells = doc.select("table.month-table td.month-day")
        if (dayCells.isEmpty()) return null'''
    text, c1 = replace_exact(text, old, new, "NumeronParser: turvallinen null-palautus ja whitespace-jako")
    old_end = r'''        return mergeConsecutiveLeaves(shifts)
    }

    private fun mergeConsecutiveLeaves(rawShifts: List<WorkShift>): List<WorkShift> {'''
    new_end = r'''        return shifts
    }

    fun mergeConsecutiveLeaves(rawShifts: List<WorkShift>): List<WorkShift> {'''
    text, c2 = replace_exact(text, old_end, new_end, "NumeronParser: julkinen mergeConsecutiveLeaves kuukausien yli")
    if c1 or c2:
        path.write_text(text, encoding="utf-8")


def patch_main_activity(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old_bitmap = r'''            if (webView.width > 0 && webView.height > 0 && webView.alpha > 0.5f) {
                try {
                    val bitmap = Bitmap.createBitmap(webView.width, webView.height, Bitmap.Config.ARGB_8888)'''
    new_bitmap = r'''            if (webView.width > 0 && webView.height > 0 && webView.alpha > 0.5f) {
                try {
                    val bitmap = Bitmap.createBitmap(webView.width, webView.height, Bitmap.Config.RGB_565)'''
    text, c1 = replace_exact(text, old_bitmap, new_bitmap, "MainActivity: kevyempi RGB_565-bittikartta siirtymään")
    old_override = r'''            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val url = request?.url?.toString() ?: return false
                if (url.startsWith("http://") || url.startsWith("https://")) {
                    startSnapshotTransition()
                    return false
                }
                return super.shouldOverrideUrlLoading(view, request)
            }'''
    new_override = r'''            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val uri = request?.url ?: return false
                val url = uri.toString()
                if (url.startsWith("http://") || url.startsWith("https://")) {
                    val allowedHost = try {
                        android.net.Uri.parse(getBaseUrl()).host
                    } catch (_: Exception) {
                        null
                    }
                    val reqHost = uri.host
                    val isInternal = reqHost.equals("demo.local", ignoreCase = true) ||
                        (!allowedHost.isNullOrBlank() && reqHost.equals(allowedHost, ignoreCase = true))
                    if (isInternal) {
                        startSnapshotTransition()
                        return false
                    }
                    try {
                        startActivity(Intent(Intent.ACTION_VIEW, uri))
                    } catch (_: Exception) {
                    }
                    return true
                }
                return super.shouldOverrideUrlLoading(view, request)
            }'''
    text, c2 = replace_exact(text, old_override, new_override, "MainActivity: ulkoisten linkkien avaus selaimeen")
    old_css_inject = r'''        val js = """
            (function() {
                var style = document.getElementById('custom-dark-theme');
                if (!style) {
                    style = document.createElement('style');
                    style.id = 'custom-dark-theme';
                    document.head.appendChild(style);
                }
                style.innerHTML = '$safeCss';'''
    new_css_inject = r'''        val js = """
            (function() {
                var style = document.getElementById('custom-dark-theme');
                if (!style) {
                    style = document.createElement('style');
                    style.id = 'custom-dark-theme';
                    (document.head || document.documentElement).appendChild(style);
                    style.textContent = '$safeCss';
                }'''
    text, c3 = replace_exact(text, old_css_inject, new_css_inject, "MainActivity: vältä tumman teeman CSS:n tuplaruiskutus")
    old_session_watch = r'''                if (!window._sessionWatchInstalled) {
                    window._sessionWatchInstalled = true;
                    setInterval(function() {
                        if (window._sessionExpiredHandled) return;
                        var expired = false;
                        var candidates = document.querySelectorAll('#session-expired-modal, #sessionExpiredModal, #SessionExpiredModal, .modal, [role="dialog"]');
                        for (var i = 0; i < candidates.length; i++) {
                            var m = candidates[i];
                            var style = window.getComputedStyle(m);
                            var isVisible = (m.offsetParent !== null) || (style && style.display !== 'none' && style.visibility !== 'hidden' && parseFloat(style.opacity || '1') > 0);
                            if (!isVisible) continue;
                            var txt = (m.innerText || m.textContent || '').toLowerCase();
                            if (m.id === 'session-expired-modal' || m.id === 'sessionExpiredModal' || txt.indexOf('istunto vanhentunut') !== -1 || txt.indexOf('session expired') !== -1) {
                                expired = true;
                                break;
                            }
                        }
                        if (expired) {
                            window._sessionExpiredHandled = true;
                            if (window.SessionBridge && typeof window.SessionBridge.onSessionExpired === 'function') {
                                window.SessionBridge.onSessionExpired();
                            } else {
                                window.location.href = '/Login/Login';
                            }
                        }
                    }, 250);
                }'''
    new_session_watch = r'''                if (!window._sessionWatchInstalled) {
                    window._sessionWatchInstalled = true;
                    function checkSessionModal() {
                        if (window._sessionExpiredHandled) return;
                        var expired = false;
                        var candidates = document.querySelectorAll('#session-expired-modal, #sessionExpiredModal, #SessionExpiredModal, .modal, [role="dialog"]');
                        for (var i = 0; i < candidates.length; i++) {
                            var m = candidates[i];
                            var style = window.getComputedStyle(m);
                            var isVisible = (m.offsetParent !== null) || (style && style.display !== 'none' && style.visibility !== 'hidden' && parseFloat(style.opacity || '1') > 0);
                            if (!isVisible) continue;
                            var txt = (m.innerText || m.textContent || '').toLowerCase();
                            if (m.id === 'session-expired-modal' || m.id === 'sessionExpiredModal' || txt.indexOf('istunto vanhentunut') !== -1 || txt.indexOf('session expired') !== -1) {
                                expired = true;
                                break;
                            }
                        }
                        if (expired) {
                            window._sessionExpiredHandled = true;
                            if (window.SessionBridge && typeof window.SessionBridge.onSessionExpired === 'function') {
                                window.SessionBridge.onSessionExpired();
                            } else {
                                window.location.href = '/Login/Login';
                            }
                        }
                    }
                    checkSessionModal();
                    if (document.body && typeof MutationObserver !== 'undefined') {
                        var sessionObs = new MutationObserver(checkSessionModal);
                        sessionObs.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class'] });
                    }
                }'''
    text, c4 = replace_exact(text, old_session_watch, new_session_watch, "MainActivity: korvaa 250 ms setInterval MutationObserverilla")
    old_login = r'''            private fun handleAutoLogin() {
        val user = (SecureCredentialManager.getUsername(this) ?: "").replace("\\", "\\\\").replace("'", "\\'")
        val pass = (SecureCredentialManager.getPassword(this) ?: "").replace("\\", "\\\\").replace("'", "\\'")
        if (user.isEmpty() || pass.isEmpty()) return

        val js = """
            (function() {
                var cookieBtn = Array.from(document.querySelectorAll('button, a')).find(function(el) {
                    return el.innerText.includes('Hyväksy');
                });
                if (cookieBtn) { cookieBtn.click(); }

                var u = document.getElementById('Username');
                var p = document.getElementById('Password');
                var f = document.getElementById('LoginForm');
                if (u && p && f) {
                    u.value = '$user';
                    p.value = '$pass';'''
    new_login = r'''            private fun handleAutoLogin() {
        val rawUser = SecureCredentialManager.getUsername(this) ?: ""
        val rawPass = SecureCredentialManager.getPassword(this) ?: ""
        if (rawUser.isEmpty() || rawPass.isEmpty()) return
        val userJson = org.json.JSONObject.quote(rawUser)
        val passJson = org.json.JSONObject.quote(rawPass)

        val js = """
            (function() {
                var cookieBtn = Array.from(document.querySelectorAll('button, a')).find(function(el) {
                    return el.innerText.includes('Hyväksy');
                });
                if (cookieBtn) { cookieBtn.click(); }

                var u = document.getElementById('Username');
                var p = document.getElementById('Password');
                var f = document.getElementById('LoginForm');
                if (u && p && f) {
                    u.value = $userJson;
                    p.value = $passJson;'''
    text, c5 = replace_exact(text, old_login, new_login, "MainActivity: turvallinen JSONObject.quote kirjautumistiedoille")
    old_cal_parse = r'''                    val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                    val syncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
                    val calId = if (syncCalendar) CalendarSyncHelper.getTargetCalendarId(this@MainActivity) else null
                    val allShifts = pagesToParse.flatMap { NumeronParser.parseCalendarHtml(it) }
                    CalendarSyncHelper.saveCachedShifts(this@MainActivity, allShifts)'''
    new_cal_parse = r'''                    val parsedPages = pagesToParse.map { NumeronParser.parseCalendarHtml(it) }
                    if (parsedPages.any { it == null }) {
                        withContext(Dispatchers.Main) {
                            Toast.makeText(
                                this@MainActivity,
                                "Työvuorojen luku epäonnistui – kalenteria ei muutettu",
                                Toast.LENGTH_LONG
                            ).show()
                        }
                        return@launch
                    }
                    val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                    val syncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
                    val calId = if (syncCalendar) CalendarSyncHelper.getTargetCalendarId(this@MainActivity) else null
                    val allShifts = NumeronParser.mergeConsecutiveLeaves(parsedPages.filterNotNull().flatten())
                    CalendarSyncHelper.saveCachedShifts(this@MainActivity, allShifts)'''
    text, c6 = replace_exact(text, old_cal_parse, new_cal_parse, "MainActivity: null-tarkistus ja kuukausien yli menevien lomien yhdistäminen")
    if c1 or c2 or c3 or c4 or c5 or c6:
        path.write_text(text, encoding="utf-8")


def patch_quick_stamp_activity(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = r'''    private fun submitAutoLogin(view: WebView?, attempt: Int = 0) {
        if (view == null || isCompleted) return
        val user = (SecureCredentialManager.getUsername(this) ?: "").replace("\\", "\\\\").replace("'", "\\'")
        val pass = (SecureCredentialManager.getPassword(this) ?: "").replace("\\", "\\\\").replace("'", "\\'")

        val js = """
            (function() {
                var u = document.getElementById('Username');
                var p = document.getElementById('Password');
                var f = document.getElementById('LoginForm');
                if (u && p && f) {
                    u.value = '$user';
                    p.value = '$pass';'''
    new = r'''    private fun submitAutoLogin(view: WebView?, attempt: Int = 0) {
        if (view == null || isCompleted) return
        val userJson = JSONObject.quote(SecureCredentialManager.getUsername(this) ?: "")
        val passJson = JSONObject.quote(SecureCredentialManager.getPassword(this) ?: "")

        val js = """
            (function() {
                var u = document.getElementById('Username');
                var p = document.getElementById('Password');
                var f = document.getElementById('LoginForm');
                if (u && p && f) {
                    u.value = $userJson;
                    p.value = $passJson;'''
    updated, changed = replace_exact(text, old, new, "QuickStampActivity: turvallinen JSONObject.quote kirjautumiseen")
    if changed:
        path.write_text(updated, encoding="utf-8")


def patch_settings_dialog_helper(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old_imports = r'''import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient'''
    new_imports = r'''import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext'''
    text, c1 = replace_exact(text, old_imports, new_imports, "SettingsDialogHelper: poista tarpeettomat WebView-importit")
    old_next_sync = r'''        addStatusRow(
            statusCard,
            "Seuraava automaattinen tarkistus",
            if (!anyBackgroundEnabled) "Pois käytöstä" else formatTimestamp(nextSyncMs, "Arkisin klo 09:30 ja 14:30")
        )'''
    new_next_sync = r'''        val (nextSyncValueTv, _) = addStatusRow(
            statusCard,
            "Seuraava automaattinen tarkistus",
            if (!anyBackgroundEnabled) "Pois käytöstä" else formatTimestamp(prefs.getLong("next_calendar_sync_ms", 0L), "Arkisin klo 09:30 ja 14:30")
        )
        if (anyBackgroundEnabled) {
            try {
                val future = WorkManager.getInstance(context).getWorkInfosForUniqueWork("NumeronVuorovahtiSync")
                future.addListener({
                    try {
                        val infos = future.get()
                        val nextRun = infos.firstOrNull { !it.state.isFinished }?.nextScheduleTimeMillis ?: 0L
                        if (nextRun > System.currentTimeMillis() && nextRun < Long.MAX_VALUE) {
                            nextSyncValueTv.text = formatTimestamp(nextRun, "Arkisin klo 09:30 ja 14:30")
                        }
                    } catch (_: Exception) {
                    }
                }, ContextCompat.getMainExecutor(context))
            } catch (_: Exception) {
            }
        }'''
    text, c2 = replace_exact(
        text,
        old_next_sync,
        new_next_sync,
        "SettingsDialogHelper: ei-blokkaava WorkManager-aikataulun luku",
        already_marker="val (nextSyncValueTv, _)",
    )
    old_sync_var = r'''        val lastSyncMs = prefs.getLong("last_calendar_sync_ms", 0L)
        val nextSyncMs = resolveNextSyncMs(context, prefs.getLong("next_calendar_sync_ms", 0L))
        val lastReminderMs = prefs.getLong("last_reminder_sent_ms", 0L)'''
    new_sync_var = r'''        val lastSyncMs = prefs.getLong("last_calendar_sync_ms", 0L)
        val lastReminderMs = prefs.getLong("last_reminder_sent_ms", 0L)'''
    text, c3 = replace_exact(text, old_sync_var, new_sync_var, "SettingsDialogHelper: poista synkroninen resolveNextSyncMs-kutsu")
    old_test_fn = r'''    private fun testLoginWithHiddenWebView(
        context: Context,
        baseUrl: String,
        username: String,
        password: String,
        callback: (Boolean, String) -> Unit
    ) {
        val testWebView = WebView(context).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
        }

        val cm = CookieManager.getInstance()
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
        timeoutHandler.postDelayed(timeoutRunnable, 15_000L)

        testWebView.webViewClient = object : WebViewClient() {
            override fun onReceivedError(
                view: WebView?,
                errorCode: Int,
                description: String?,
                failingUrl: String?
            ) {
                cleanupAndRespond(
                    false,
                    "Yhteysvirhe: Organisaatiota '$baseUrl' ei löytynyt tai verkkoyhteys puuttuu."
                )
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                if (url == null || finished) return

                if (url.contains("/Login/Login", ignoreCase = true)) {
                    if (!loginAttempted) {
                        loginAttempted = true
                        val safeUser = username.replace("\\", "\\\\").replace("'", "\\'")
                        val safePass = password.replace("\\", "\\\\").replace("'", "\\'")
                        val js = """
                            (function() {
                                var u = document.getElementById('Username');
                                var p = document.getElementById('Password');
                                var f = document.getElementById('LoginForm');
                                if (u && p && f) {
                                    u.value = '$safeUser';
                                    p.value = '$safePass';
                                    f.submit();
                                    return 'SUBMITTED';
                                }
                                return 'NO_FORM';
                            })();
                        """.trimIndent()
                        view?.evaluateJavascript(js) { res ->
                            if (res?.contains("NO_FORM") == true) {
                                cleanupAndRespond(false, "Virhe: Kirjautumislomaketta ei tunnistettu sivulta.")
                            }
                        }
                    } else {
                        val errJs = """
                            (function() {
                                var err = document.querySelector('.validation-summary-errors, .alert-danger');
                                return err ? err.innerText.trim() : '';
                            })();
                        """.trimIndent()
                        view?.evaluateJavascript(errJs) { errText ->
                            val cleanErr = errText?.replace("\"", "")?.trim() ?: ""
                            if (cleanErr.isNotEmpty()) {
                                cleanupAndRespond(false, "Kirjautuminen epäonnistui: $cleanErr")
                            } else {
                                cleanupAndRespond(false, "Virheellinen käyttäjätunnus tai salasana.")
                            }
                        }
                    }
                } else if (
                    url.contains("/WorktimeStamping", ignoreCase = true) ||
                    url.contains("/InfraDashboard", ignoreCase = true) ||
                    url.contains("/Calendar", ignoreCase = true)
                ) {
                    cleanupAndRespond(true, "Yhteys ja tunnukset toimivat! ($baseUrl)")
                }
            }
        }

        testWebView.loadUrl("$baseUrl/Login/Login")
    }'''
    new_test_fn = r'''    private fun testLoginWithHiddenWebView(
        @Suppress("UNUSED_PARAMETER") context: Context,
        baseUrl: String,
        username: String,
        password: String,
        callback: (Boolean, String) -> Unit
    ) {
        CoroutineScope(Dispatchers.IO).launch {
            val (success, msg) = BackgroundAuthHelper.testCredentials(baseUrl, username, password)
            withContext(Dispatchers.Main) {
                callback(success, msg)
            }
        }
    }'''
    text, c4 = replace_exact(
        text,
        old_test_fn,
        new_test_fn,
        "SettingsDialogHelper: eristetty HTTP-yhteystesti ilman evästeiden tyhjennystä",
        already_marker="BackgroundAuthHelper.testCredentials",
    )
    if c1 or c2 or c3 or c4:
        path.write_text(text, encoding="utf-8")


def patch_shift_reminder_receiver(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old_receiver = r'''class ShiftReminderReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action

        // 1. Puhelin käynnistyi uudelleen TAI sovellus päivitettiin (MY_PACKAGE_REPLACED)
        if (action == Intent.ACTION_BOOT_COMPLETED || action == Intent.ACTION_MY_PACKAGE_REPLACED) {
            CalendarSyncHelper.scheduleShiftReminders(context)
            ensureBackgroundSyncScheduled(context)
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

        val appCtx = context.applicationContext
        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                BackgroundAuthHelper.ensureAuthenticatedSession(appCtx)
            } finally {
                pendingResult.finish()
            }
        }
    }'''
    new_receiver = r'''class ShiftReminderReceiver : BroadcastReceiver() {

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
    }'''
    text, c1 = replace_exact(
        text,
        old_receiver,
        new_receiver,
        "ShiftReminderReceiver: sisäinen vastaanotin ja asynkroninen Peru kaikki -käsittely",
        already_marker="class InternalReceiver : BroadcastReceiver()",
    )
    old_companion = r'''    companion object {
        const val ACTION_REVERT_ALL_CALENDAR_CHANGES = "fi.numeron.vuorovahti.ACTION_REVERT_ALL_CALENDAR_CHANGES"
        const val NOTIF_ID_CALENDAR_CHANGES = 4001'''
    new_companion = r'''    companion object {
        const val ACTION_SHIFT_REMINDER = "fi.numeron.vuorovahti.ACTION_SHIFT_REMINDER"
        const val ACTION_REVERT_ALL_CALENDAR_CHANGES = "fi.numeron.vuorovahti.ACTION_REVERT_ALL_CALENDAR_CHANGES"
        const val NOTIF_ID_CALENDAR_CHANGES = 4001'''
    text, c2 = replace_exact(text, old_companion, new_companion, "ShiftReminderReceiver: ACTION_SHIFT_REMINDER-vakio")
    old_revert_pi = r'''            // Suora pikatoiminto ilmoituksesta: Peru kaikki muutokset
            val revertAllIntent = Intent(context, ShiftReminderReceiver::class.java).apply {
                action = ACTION_REVERT_ALL_CALENDAR_CHANGES
            }'''
    new_revert_pi = r'''            // Suora pikatoiminto ilmoituksesta: Peru kaikki muutokset
            val revertAllIntent = Intent(context, InternalReceiver::class.java).apply {
                action = ACTION_REVERT_ALL_CALENDAR_CHANGES
            }'''
    text, c3 = replace_exact(text, old_revert_pi, new_revert_pi, "ShiftReminderReceiver: revertAllIntent sisäiselle vastaanottimelle")
    old_req_pi = r'''            val pi = PendingIntent.getActivity(
                context, id, openIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )'''
    new_req_pi = r'''            val pi = PendingIntent.getActivity(
                context, 3000 + id, openIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )'''
    text, c4 = replace_exact(text, old_req_pi, new_req_pi, "ShiftReminderReceiver: yksilöllinen PendingIntent requestCode toiveille")
    old_worker = r'''    @SuppressLint("SetJavaScriptEnabled")
    override suspend fun doWork(): Result = withContext(Dispatchers.Main) {
        if (DemoModeHelper.isDemoEnabled(appContext)) {
            return@withContext Result.success()
        }

        val prefs = appContext.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val rawUser = SecureCredentialManager.getUsername(appContext) ?: ""
        val rawPass = SecureCredentialManager.getPassword(appContext) ?: ""
        val user = rawUser.replace("\\", "\\\\").replace("'", "\\'")
        val pass = rawPass.replace("\\", "\\\\").replace("'", "\\'")
        val baseUrl = UrlNormalizer.getSavedBaseUrl(appContext)
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
        }
    }'''
    new_worker = r'''    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
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
    }'''
    text, c5 = replace_exact(
        text,
        old_worker,
        new_worker,
        "BackgroundSyncWorker: suora HTTP-haku tausta-WebView'n sijaan ja turvallinen virheenkäsittely",
        already_marker="BackgroundAuthHelper.fetchAuthenticatedPages(",
    )
    if c1 or c2 or c3 or c4 or c5:
        path.write_text(text, encoding="utf-8")


def patch_support_billing_helper(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old_flag = r'''    private val mainHandler = Handler(Looper.getMainLooper())
    private var isDestroyed = false'''
    new_flag = r'''    private val mainHandler = Handler(Looper.getMainLooper())

    @Volatile
    private var isDestroyed = false'''
    text, c1 = replace_exact(text, old_flag, new_flag, "SupportBillingHelper: @Volatile isDestroyed")
    old_start = r'''    fun startConnection() {
        if (isDestroyed) return
        if (billingClient.isReady) {
            queryTipProducts()
            return
        }'''
    new_start = r'''    fun startConnection() {
        if (isDestroyed) return
        if (billingClient.isReady) {
            queryTipProducts()
            return
        }
        if (billingClient.connectionState == BillingClient.ConnectionState.CONNECTING) {
            return
        }'''
    text, c2 = replace_exact(text, old_start, new_start, "SupportBillingHelper: estä päällekkäiset CONNECTING-kutsut")
    old_owned = r'''            BillingClient.BillingResponseCode.USER_CANCELED -> {
                // Käyttäjä peruutti maksun – ei näytetä virheilmoitusta
            }
            else -> {'''
    new_owned = r'''            BillingClient.BillingResponseCode.USER_CANCELED -> {
                // Käyttäjä peruutti maksun – ei näytetä virheilmoitusta
            }
            BillingClient.BillingResponseCode.ITEM_ALREADY_OWNED -> {
                consumeUnfinishedPurchases()
                postStatus("Keskeneräinen tuki vahvistetaan – voit tukea uudelleen hetken kuluttua.", true)
            }
            else -> {'''
    text, c3 = replace_exact(text, old_owned, new_owned, "SupportBillingHelper: ITEM_ALREADY_OWNED-käsittely")
    if c1 or c2 or c3:
        path.write_text(text, encoding="utf-8")


def patch_url_normalizer(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = r'''    fun normalizeOrgUrl(rawInput: String?): String {
        val cleaned = rawInput?.trim()?.lowercase() ?: ""
        if (cleaned.isEmpty()) return ""
        if (cleaned == "demo") return "demo"

        // Jos käyttäjä syötti täyden custom-domainin (joka ei ole numeronwfm.com), säilytetään se
        if ((cleaned.startsWith("http://") || cleaned.startsWith("https://")) && !cleaned.contains("numeronwfm.com")) {
            return cleaned.trimEnd('/')
        }

        // Poistetaan protokolla, polut ja pääteosa, jotta jäljelle jää pelkkä organisaatiotunnus
        val orgSlug = cleaned
            .removePrefix("https://")
            .removePrefix("http://")
            .substringBefore("/")
            .substringBefore("?")
            .removeSuffix(".numeronwfm.com")
            .removeSuffix(".numeronwfm.fi")
            .replace("\\s+".toRegex(), "") // Poistaa välilyönnit (esim. "Siun sote" -> "siunsote")
            .replace("[^a-z0-9-]".toRegex(), "") // Poistaa erikoismerkit

        if (orgSlug.isEmpty()) return ""

        return "https://$orgSlug.numeronwfm.com"
    }'''
    new = r'''    fun normalizeOrgUrl(rawInput: String?): String {
        val trimmed = rawInput?.trim() ?: ""
        if (trimmed.isEmpty()) return ""
        if (trimmed.equals("demo", ignoreCase = true)) return "demo"

        val lower = trimmed.lowercase()
        val isNumeronHost = lower.contains("numeronwfm.com") || lower.contains("numeronwfm.fi")

        // Jos käyttäjä syötti oman custom-domainin protokollalla, säilytetään polun kirjainkoko
        if ((lower.startsWith("http://") || lower.startsWith("https://")) && !isNumeronHost) {
            return trimmed.trimEnd('/')
        }

        // Jos käyttäjä syötti oman domainin ilman protokollaa (esim. wfm.yritys.fi)
        if (!isNumeronHost && !trimmed.contains(" ") && trimmed.substringBefore("/").contains(".")) {
            return "https://${trimmed.trimEnd('/')}"
        }

        // Poistetaan protokolla, polut ja pääteosa, jotta jäljelle jää pelkkä organisaatiotunnus
        val orgSlug = lower
            .removePrefix("https://")
            .removePrefix("http://")
            .substringBefore("/")
            .substringBefore("?")
            .removeSuffix(".numeronwfm.com")
            .removeSuffix(".numeronwfm.fi")
            .replace("\\s+".toRegex(), "")
            .replace("[^a-z0-9-]".toRegex(), "")

        if (orgSlug.isEmpty()) return ""

        return "https://$orgSlug.numeronwfm.com"
    }'''
    updated, changed = replace_exact(
        text,
        old,
        new,
        "UrlNormalizer: mukautettujen verkkotunnusten ja polkujen kirjainkoon säilytys",
        already_marker="val isNumeronHost =",
    )
    if changed:
        path.write_text(updated, encoding="utf-8")


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    print(f"Suoritetaan korjaukset hakemistossa: {root}")

    tasks = [
        ("AndroidManifest.xml", patch_android_manifest),
        ("BackgroundAuthHelper.kt", patch_background_auth_helper),
        ("DemoModeHelper.kt", patch_demo_mode_helper),
        ("CalendarChangeTracker.kt", patch_calendar_change_tracker),
        ("CalendarSyncHelper.kt", patch_calendar_sync_helper),
        ("SecureCredentialManager.kt", patch_secure_credential_manager),
        ("NumeronParser.kt", patch_numeron_parser),
        ("MainActivity.kt", patch_main_activity),
        ("QuickStampActivity.kt", patch_quick_stamp_activity),
        ("SettingsDialogHelper.kt", patch_settings_dialog_helper),
        ("ShiftReminderReceiver.kt", patch_shift_reminder_receiver),
        ("SupportBillingHelper.kt", patch_support_billing_helper),
        ("UrlNormalizer.kt", patch_url_normalizer),
    ]

    for filename, fn in tasks:
        target = find_file(root, filename)
        if target is None:
            raise FileNotFoundError(f"Tiedostoa ei löytynyt projektista: {filename}")
        print(f"Käsitellään {target.relative_to(root)}...")
        fn(target)

    print("Kaikki korjaukset suoritettu onnistuneesti!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
