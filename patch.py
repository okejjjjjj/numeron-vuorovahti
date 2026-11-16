#!/usr/bin/env python3
import os
import sys

def find_file(filename):
    for root, dirs, files in os.walk("."):
        if filename in files:
            return os.path.join(root, filename)
    return None

def patch_settings_dialog_helper(filepath):
    tq = '"""'
    new_content = r"""package fi.numeron.vuorovahti

import android.Manifest
import android.app.AlertDialog
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Color
import android.provider.CalendarContract
import android.text.InputType
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.ContextCompat

data class CalendarOption(
    val id: Long,
    val name: String,
    val accountName: String,
    val accountType: String
) {
    override fun toString(): String {
        val typeTag = if (accountType == "com.google") "Google" else "Paikallinen"
        return "$name ($accountName) [$typeTag]"
    }
}

data class ShiftColorChoice(
    val name: String,
    val rgb: Int
) {
    override fun toString(): String = name
}

object SettingsDialogHelper {

    val SHIFT_COLOR_CHOICES = listOf(
        ShiftColorChoice("Basilika (Vihreä)", Color.rgb(11, 128, 67)),
        ShiftColorChoice("Salvia (Vaaleanvihreä)", Color.rgb(51, 182, 121)),
        ShiftColorChoice("Mandariini (Oranssi)", Color.rgb(244, 81, 30)),
        ShiftColorChoice("Banaani (Keltainen)", Color.rgb(246, 191, 38)),
        ShiftColorChoice("Viinirypäle (Lila)", Color.rgb(142, 36, 170)),
        ShiftColorChoice("Mustikka (Sininen)", Color.rgb(63, 81, 181)),
        ShiftColorChoice("Riikinkukko (Turkoosi)", Color.rgb(3, 155, 229)),
        ShiftColorChoice("Flamingo (Vaaleanpunainen)", Color.rgb(230, 124, 115)),
        ShiftColorChoice("Tomaatti (Punainen)", Color.rgb(213, 0, 0)),
        ShiftColorChoice("Grafiitti (Harmaa)", Color.rgb(97, 97, 97))
    )

    val DEFAULT_MORNING_RGB = Color.rgb(11, 128, 67)
    val DEFAULT_EVENING_RGB = Color.rgb(244, 81, 30)
    val DEFAULT_NIGHT_RGB = Color.rgb(142, 36, 170)

    fun getAvailableCalendars(context: Context): List<CalendarOption> {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return emptyList()
        }
        val list = mutableListOf<CalendarOption>()
        val projection = arrayOf(
            CalendarContract.Calendars._ID,
            CalendarContract.Calendars.CALENDAR_DISPLAY_NAME,
            CalendarContract.Calendars.ACCOUNT_NAME,
            CalendarContract.Calendars.ACCOUNT_TYPE,
            CalendarContract.Calendars.IS_PRIMARY
        )
        val selection = "${CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL} >= ? AND ${CalendarContract.Calendars.VISIBLE} = 1"
        val selectionArgs = arrayOf(CalendarContract.Calendars.CAL_ACCESS_CONTRIBUTOR.toString())

        context.contentResolver.query(
            CalendarContract.Calendars.CONTENT_URI,
            projection,
            selection,
            selectionArgs,
            null
        )?.use { cursor ->
            while (cursor.moveToNext()) {
                val id = cursor.getLong(0)
                val name = cursor.getString(1) ?: "Kalenteri"
                val account = cursor.getString(2) ?: ""
                val accountType = cursor.getString(3) ?: ""
                val isPrimary = cursor.getInt(4) == 1
                list.add(CalendarOption(id, name, account, accountType))
                if (accountType == "com.google" && (isPrimary || name.equals(account, ignoreCase = true))) {
                    val item = list.removeAt(list.lastIndex)
                    list.add(0, item)
                }
            }
        }
        return list.sortedBy { if (it.accountType == "com.google") 0 else 1 }
    }

    fun showSettingsDialog(
        context: Context,
        onManualSync: () -> Unit,
        onManageChanges: () -> Unit,
        onTestNotification: () -> Unit,
        onSaved: () -> Unit
    ) {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)

        val scrollView = ScrollView(context)
        val layout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 36, 48, 24)
        }
        scrollView.addView(layout)

        fun createLabel(text: String): TextView = TextView(context).apply {
            this.text = text
            textSize = 13f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, 16, 0, 6)
        }

        layout.addView(createLabel("Organisaatiotunnus (esim. siunsote)"))
        val editOrg = EditText(context).apply {
            hint = "siunsote"
            setText(prefs.getString("org_raw_input", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            isSingleLine = true
        }
        layout.addView(editOrg)

        layout.addView(createLabel("Käyttäjätunnus"))
        val editUser = EditText(context).apply {
            hint = "Käyttäjätunnus"
            setText(prefs.getString("username", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            isSingleLine = true
        }
        layout.addView(editUser)

        layout.addView(createLabel("Salasana"))
        val editPass = EditText(context).apply {
            hint = "Salasana"
            setText(prefs.getString("password", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            isSingleLine = true
        }
        layout.addView(editPass)

        val tvTestStatus = TextView(context).apply {
            text = ""
            textSize = 13f
            setPadding(0, 12, 0, 12)
        }

        val btnTestCredentials = Button(context).apply {
            text = "Testaa yhteys ja tunnukset"
            setOnClickListener {
                val normalizedUrl = UrlNormalizer.normalizeOrgUrl(editOrg.text.toString())
                val user = editUser.text.toString().trim()
                val pass = editPass.text.toString()

                if (normalizedUrl.isEmpty()) {
                    tvTestStatus.setTextColor(Color.parseColor("#EF4444"))
                    tvTestStatus.text = "Virhe: Syötä organisaatiotunnus."
                    return@setOnClickListener
                }
                if (user.isEmpty() || pass.isEmpty()) {
                    tvTestStatus.setTextColor(Color.parseColor("#EF4444"))
                    tvTestStatus.text = "Virhe: Syötä käyttäjätunnus ja salasana."
                    return@setOnClickListener
                }

                isEnabled = false
                tvTestStatus.setTextColor(Color.parseColor("#38BDF8"))
                tvTestStatus.text = "Testataan osoitetta $normalizedUrl..."

                testLoginWithHiddenWebView(context, normalizedUrl, user, pass) { success, message ->
                    isEnabled = true
                    tvTestStatus.setTextColor(
                        if (success) Color.parseColor("#10B981") else Color.parseColor("#EF4444")
                    )
                    tvTestStatus.text = message
                }
            }
        }
        layout.addView(btnTestCredentials)
        layout.addView(tvTestStatus)

        layout.addView(createLabel("Kohdekalenteri"))
        val calendars = getAvailableCalendars(context)
        val spinnerCalendar = Spinner(context)
        if (calendars.isNotEmpty()) {
            val adapter = ArrayAdapter(context, android.R.layout.simple_spinner_dropdown_item, calendars)
            spinnerCalendar.adapter = adapter
            val savedCalId = prefs.getLong("calendar_id", -1L)
            val idx = calendars.indexOfFirst { it.id == savedCalId }
            spinnerCalendar.setSelection(if (idx >= 0) idx else 0)
        }
        layout.addView(spinnerCalendar)

        layout.addView(createLabel("Henkilötunniste yhteiskalenteriin (valinnainen, esim. Jukka)"))
        val editUserTag = EditText(context).apply {
            hint = "Jätä tyhjäksi omassa kalenterissa"
            setText(prefs.getString("calendar_user_tag", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_WORDS
            isSingleLine = true
        }
        layout.addView(editUserTag)

        fun createColorSpinner(savedRgb: Int): Spinner {
            val spinner = Spinner(context)
            val adapter = ArrayAdapter(context, android.R.layout.simple_spinner_dropdown_item, SHIFT_COLOR_CHOICES)
            spinner.adapter = adapter
            val idx = SHIFT_COLOR_CHOICES.indexOfFirst { it.rgb == savedRgb }
            if (idx >= 0) spinner.setSelection(idx)
            return spinner
        }

        layout.addView(createLabel("Aamuvuoron väri"))
        val spinnerMorningColor = createColorSpinner(prefs.getInt("color_morning_rgb", DEFAULT_MORNING_RGB))
        layout.addView(spinnerMorningColor)

        layout.addView(createLabel("Iltavuoron väri"))
        val spinnerEveningColor = createColorSpinner(prefs.getInt("color_evening_rgb", DEFAULT_EVENING_RGB))
        layout.addView(spinnerEveningColor)

        layout.addView(createLabel("Yövuoron väri"))
        val spinnerNightColor = createColorSpinner(prefs.getInt("color_night_rgb", DEFAULT_NIGHT_RGB))
        layout.addView(spinnerNightColor)

        layout.addView(createLabel("Muistutus ennen vuoroa (min)"))
        val editReminder = EditText(context).apply {
            setText(prefs.getInt("reminder_minutes", 30).toString())
            inputType = InputType.TYPE_CLASS_NUMBER
            isSingleLine = true
        }
        layout.addView(editReminder)

        val btnSync = Button(context).apply {
            text = "Synkronoi työvuorot kalenteriin nyt"
            setOnClickListener { onManualSync() }
        }
        layout.addView(btnSync)

        val btnChanges = Button(context).apply {
            text = "Hallitse kalenterimuutoksia"
            setOnClickListener { onManageChanges() }
        }
        layout.addView(btnChanges)

        val btnTestNotif = Button(context).apply {
            text = "Lähetä testi-ilmoitus"
            setOnClickListener { onTestNotification() }
        }
        layout.addView(btnTestNotif)

        AlertDialog.Builder(context)
            .setTitle("Vuorovahti – Asetukset")
            .setView(scrollView)
            .setPositiveButton("Tallenna") { _, _ ->
                val rawOrg = editOrg.text.toString().trim()
                val normalizedUrl = UrlNormalizer.normalizeOrgUrl(rawOrg)
                val selectedCal = spinnerCalendar.selectedItem as? CalendarOption
                val userTag = editUserTag.text.toString().trim()
                val reminderMins = editReminder.text.toString().toIntOrNull() ?: 30

                val morningRgb = (spinnerMorningColor.selectedItem as? ShiftColorChoice)?.rgb ?: DEFAULT_MORNING_RGB
                val eveningRgb = (spinnerEveningColor.selectedItem as? ShiftColorChoice)?.rgb ?: DEFAULT_EVENING_RGB
                val nightRgb = (spinnerNightColor.selectedItem as? ShiftColorChoice)?.rgb ?: DEFAULT_NIGHT_RGB

                prefs.edit()
                    .putString("org_raw_input", rawOrg)
                    .putString("server_url", normalizedUrl)
                    .putString("username", editUser.text.toString().trim())
                    .putString("password", editPass.text.toString())
                    .putString("calendar_user_tag", userTag)
                    .putInt("reminder_minutes", reminderMins)
                    .putInt("color_morning_rgb", morningRgb)
                    .putInt("color_evening_rgb", eveningRgb)
                    .putInt("color_night_rgb", nightRgb)
                    .apply {
                        if (selectedCal != null) putLong("calendar_id", selectedCal.id)
                    }
                    .apply()

                Toast.makeText(context, "Tallennettu ($normalizedUrl)", Toast.LENGTH_SHORT).show()
                onSaved()
            }
            .setNegativeButton("Peruuta", null)
            .show()
    }

    private fun testLoginWithHiddenWebView(
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

        CookieManager.getInstance().removeAllCookies(null)

        var loginAttempted = false
        var finished = false

        fun cleanupAndRespond(success: Boolean, msg: String) {
            if (finished) return
            finished = true
            testWebView.stopLoading()
            testWebView.destroy()
            callback(success, msg)
        }

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
                        val js = __TQ__
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
                        __TQ__.trimIndent()
                        view?.evaluateJavascript(js) { res ->
                            if (res?.contains("NO_FORM") == true) {
                                cleanupAndRespond(false, "Virhe: Kirjautumislomaketta ei tunnistettu sivulta.")
                            }
                        }
                    } else {
                        val errJs = __TQ__
                            (function() {
                                var err = document.querySelector('.validation-summary-errors, .alert-danger');
                                return err ? err.innerText.trim() : '';
                            })();
                        __TQ__.trimIndent()
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
    }
}
""".replace("__TQ__", tq)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"[OK] Päivitetty: {filepath}")

def patch_calendar_sync_helper(filepath):
    new_content = r"""package fi.numeron.vuorovahti

import android.Manifest
import android.app.AlarmManager
import android.app.PendingIntent
import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.provider.CalendarContract
import androidx.core.content.ContextCompat
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.TimeZone
import java.util.UUID

object CalendarSyncHelper {

    const val EVENT_DESCRIPTION_TAG = "Synkronoitu Numeron Vuorovahti -sovelluksesta"

    private val KNOWN_SHIFT_OR_LEAVE_KEYWORDS = listOf(
        "työvuoro", "vuoro", "aamuvuoro", "iltavuoro", "yövuoro", "päivävuoro", "välivuoro",
        "loma", "vuosiloma", "talviloma", "kesäloma", "poissaolo", "vapaa", "koulutus",
        "sairausloma", "isyysvapaa", "vanhempainvapaa", "saldovapaa", "arkipyhä"
    )

    private data class ExistingEvent(
        val eventId: Long,
        val title: String,
        val location: String,
        val description: String,
        val colorKey: String?,
        val startMs: Long,
        val endMs: Long,
        val isAllDay: Boolean,
        val isOwnedByApp: Boolean
    )

    private data class ShiftColorKeys(
        val greenKey: String?,
        val orangeKey: String?,
        val purpleKey: String?
    )

    private data class ReminderEventItem(
        val displayTitle: String,
        val startMs: Long,
        val endMs: Long
    )

    fun getTargetCalendarId(context: Context): Long? {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val available = SettingsDialogHelper.getAvailableCalendars(context)
        val savedId = prefs.getLong("calendar_id", -1L)
        if (savedId > 0 && available.any { it.id == savedId }) return savedId

        val defaultGoogle = available.firstOrNull()
        if (defaultGoogle != null) {
            prefs.edit().putLong("calendar_id", defaultGoogle.id).apply()
        }
        return defaultGoogle?.id
    }

    private fun getUserTag(context: Context): String {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        return (prefs.getString("calendar_user_tag", "") ?: "").trim()
    }

    private fun formatShiftTitle(baseTitle: String, userTag: String): String {
        return if (userTag.isNotEmpty()) "$baseTitle ($userTag)" else baseTitle
    }

    private fun buildUserTagSuffix(userTag: String): String {
        return if (userTag.isNotEmpty()) "$EVENT_DESCRIPTION_TAG [$userTag]" else EVENT_DESCRIPTION_TAG
    }

    private fun buildFullDescription(comment: String, userTag: String): String {
        val clean = comment.trim()
        val tagLine = buildUserTagSuffix(userTag)
        return if (clean.isEmpty()) tagLine else "$clean\n\n$tagLine"
    }

    private fun resolveGoogleShiftColorKeys(context: Context, calendarId: Long): ShiftColorKeys {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val morningRgb = prefs.getInt("color_morning_rgb", SettingsDialogHelper.DEFAULT_MORNING_RGB)
        val eveningRgb = prefs.getInt("color_evening_rgb", SettingsDialogHelper.DEFAULT_EVENING_RGB)
        val nightRgb = prefs.getInt("color_night_rgb", SettingsDialogHelper.DEFAULT_NIGHT_RGB)
        val resolver = context.contentResolver
        var accountName: String? = null
        var accountType: String? = null

        resolver.query(
            CalendarContract.Calendars.CONTENT_URI,
            arrayOf(CalendarContract.Calendars.ACCOUNT_NAME, CalendarContract.Calendars.ACCOUNT_TYPE),
            "${CalendarContract.Calendars._ID} = ?",
            arrayOf(calendarId.toString()),
            null
        )?.use { c ->
            if (c.moveToFirst()) {
                accountName = c.getString(0)
                accountType = c.getString(1)
            }
        }

        if (accountName.isNullOrEmpty() || accountType.isNullOrEmpty()) {
            return ShiftColorKeys(null, null, null)
        }

        val availableColors = mutableListOf<Pair<String, Int>>()
        resolver.query(
            CalendarContract.Colors.CONTENT_URI,
            arrayOf(CalendarContract.Colors.COLOR_KEY, CalendarContract.Colors.COLOR),
            "${CalendarContract.Colors.ACCOUNT_NAME} = ? AND ${CalendarContract.Colors.ACCOUNT_TYPE} = ? AND ${CalendarContract.Colors.COLOR_TYPE} = ?",
            arrayOf(accountName, accountType, CalendarContract.Colors.TYPE_EVENT.toString()),
            null
        )?.use { c ->
            while (c.moveToNext()) {
                val key = c.getString(0) ?: continue
                val colorInt = c.getInt(1)
                availableColors.add(key to colorInt)
            }
        }

        if (availableColors.isEmpty()) {
            return ShiftColorKeys(null, null, null)
        }

        fun findClosestKey(targetRgb: Int): String? {
            val tr = Color.red(targetRgb)
            val tg = Color.green(targetRgb)
            val tb = Color.blue(targetRgb)
            return availableColors.minByOrNull { (_, colorInt) ->
                val dr = Color.red(colorInt) - tr
                val dg = Color.green(colorInt) - tg
                val db = Color.blue(colorInt) - tb
                dr * dr + dg * dg + db * db
            }?.first
        }

        val greenKey = findClosestKey(morningRgb)
        val orangeKey = findClosestKey(eveningRgb)
        val purpleKey = findClosestKey(nightRgb)
        return ShiftColorKeys(greenKey, orangeKey, purpleKey)
    }

    private fun pickColorKeyForShift(shift: WorkShift, keys: ShiftColorKeys): String? {
        if (shift.isAllDayLeave) return null
        val startMinutes = shift.start.hour * 60 + shift.start.minute
        val endMinutes = shift.end.hour * 60 + shift.end.minute
        val crossesMidnight = shift.end.toLocalDate().isAfter(shift.start.toLocalDate()) || endMinutes < startMinutes

        return when {
            crossesMidnight || startMinutes >= 20 * 60 || startMinutes < 4 * 60 -> keys.purpleKey
            startMinutes >= 11 * 60 + 30 -> keys.orangeKey
            else -> keys.greenKey
        }
    }

    private fun belongsToCurrentUser(description: String, title: String, userTag: String): Boolean {
        if (!description.contains(EVENT_DESCRIPTION_TAG)) return false
        if (userTag.isEmpty()) {
            val bracketRegex = Regex("Synkronoitu Numeron Vuorovahti -sovelluksesta\\s*\\[.+?]")
            return !bracketRegex.containsMatchIn(description)
        }
        return description.contains("[$userTag]", ignoreCase = true) ||
               title.endsWith("($userTag)", ignoreCase = true)
    }

    private fun belongsToAnotherUser(description: String, userTag: String): Boolean {
        if (!description.contains(EVENT_DESCRIPTION_TAG)) return false
        val match = Regex("Synkronoitu Numeron Vuorovahti -sovelluksesta\\s*\\[(.+?)]").find(description)
        if (match != null) {
            val owner = match.groupValues[1].trim()
            return !owner.equals(userTag, ignoreCase = true)
        }
        return userTag.isNotEmpty()
    }

    private fun looksLikeShiftOrLeave(title: String, desiredTitle: String, userTag: String): Boolean {
        val lower = title.lowercase().trim()
        if (userTag.isNotEmpty() && !lower.contains(userTag.lowercase())) {
            return false
        }
        if (lower == desiredTitle.lowercase() || lower.startsWith("työvuoro")) return true
        return KNOWN_SHIFT_OR_LEAVE_KEYWORDS.any { kw -> lower.contains(kw) }
    }

    fun syncShiftsToCalendar(context: Context, calendarId: Long, shifts: List<WorkShift>): List<CalendarChangeItem> {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_CALENDAR) != PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return emptyList()
        }

        val resolver = context.contentResolver
        val now = LocalDateTime.now()
        val nowMs = now.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
        val colorKeys = resolveGoogleShiftColorKeys(context, calendarId)
        val userTag = getUserTag(context)

        val upcomingShifts = shifts.filter { it.start.isAfter(now) }

        val ownedEvents = mutableListOf<ExistingEvent>()
        val unownedCandidateEvents = mutableListOf<ExistingEvent>()

        val projection = arrayOf(
            CalendarContract.Events._ID,
            CalendarContract.Events.TITLE,
            CalendarContract.Events.EVENT_LOCATION,
            CalendarContract.Events.DESCRIPTION,
            CalendarContract.Events.EVENT_COLOR_KEY,
            CalendarContract.Events.DTSTART,
            CalendarContract.Events.DTEND,
            CalendarContract.Events.ALL_DAY
        )
        val selection = "${CalendarContract.Events.CALENDAR_ID} = ? AND " +
                "${CalendarContract.Events.DTSTART} > ? AND " +
                "${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(calendarId.toString(), nowMs.toString())

        resolver.query(CalendarContract.Events.CONTENT_URI, projection, selection, selectionArgs, null)?.use { c ->
            while (c.moveToNext()) {
                val id = c.getLong(0)
                val title = c.getString(1) ?: ""
                val loc = c.getString(2) ?: ""
                val desc = c.getString(3) ?: ""
                val cKey = c.getString(4)
                val sMs = c.getLong(5)
                val eMs = c.getLong(6)
                val allDay = c.getInt(7) == 1

                if (belongsToAnotherUser(desc, userTag)) {
                    continue
                }

                val owned = belongsToCurrentUser(desc, title, userTag)
                val ev = ExistingEvent(id, title, loc, desc, cKey, sMs, eMs, allDay, owned)
                if (owned) {
                    ownedEvents.add(ev)
                } else {
                    unownedCandidateEvents.add(ev)
                }
            }
        }

        val unmatchedOwned = ownedEvents.toMutableList()
        val unmatchedExternal = unownedCandidateEvents.toMutableList()
        val detectedChanges = mutableListOf<CalendarChangeItem>()

        for (shift in upcomingShifts) {
            val newStartMs = if (shift.isAllDayLeave) {
                shift.start.toInstant(ZoneOffset.UTC).toEpochMilli()
            } else {
                shift.start.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            }
            val newEndMs = if (shift.isAllDayLeave) {
                shift.end.toInstant(ZoneOffset.UTC).toEpochMilli()
            } else {
                shift.end.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            }
            val desiredTitle = formatShiftTitle(shift.title, userTag)
            val fullDescription = buildFullDescription(shift.description, userTag)
            val desiredColorKey = pickColorKeyForShift(shift, colorKeys)

            val exactMatch = unmatchedOwned.firstOrNull {
                it.title == desiredTitle &&
                it.location == shift.location &&
                it.description == fullDescription &&
                it.colorKey == desiredColorKey &&
                it.startMs == newStartMs &&
                it.endMs == newEndMs &&
                it.isAllDay == shift.isAllDayLeave
            }

            if (exactMatch != null) {
                unmatchedOwned.remove(exactMatch)
                continue
            }

            val sameDayOwned = unmatchedOwned.firstOrNull { ex ->
                ex.isAllDay == shift.isAllDayLeave &&
                isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave) &&
                (!shift.isAllDayLeave || ex.title.equals(desiredTitle, ignoreCase = true) || ex.startMs == newStartMs)
            } ?: unmatchedOwned.firstOrNull { ex ->
                ex.isAllDay == shift.isAllDayLeave && isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave)
            }

            val sameDayExternal = if (sameDayOwned == null) {
                unmatchedExternal.firstOrNull { ex ->
                    ex.isAllDay == shift.isAllDayLeave &&
                    isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave) &&
                    looksLikeShiftOrLeave(ex.title, desiredTitle, userTag)
                }
            } else {
                null
            }

            val targetMatch = sameDayOwned ?: sameDayExternal

            if (targetMatch != null) {
                if (sameDayOwned != null) {
                    unmatchedOwned.remove(sameDayOwned)
                } else if (sameDayExternal != null) {
                    unmatchedExternal.remove(sameDayExternal)
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
                        endMs = newEndMs,
                        isAllDay = shift.isAllDayLeave,
                        prevTitle = targetMatch.title,
                        prevStartMs = targetMatch.startMs,
                        prevEndMs = targetMatch.endMs,
                        prevIsAllDay = targetMatch.isAllDay
                    )
                )
            } else {
                val values = ContentValues().apply {
                    put(CalendarContract.Events.CALENDAR_ID, calendarId)
                    put(CalendarContract.Events.TITLE, desiredTitle)
                    put(CalendarContract.Events.EVENT_LOCATION, shift.location)
                    put(CalendarContract.Events.DESCRIPTION, fullDescription)
                    if (desiredColorKey != null) {
                        put(CalendarContract.Events.EVENT_COLOR_KEY, desiredColorKey)
                    }
                    put(CalendarContract.Events.ALL_DAY, if (shift.isAllDayLeave) 1 else 0)
                    put(CalendarContract.Events.EVENT_TIMEZONE, if (shift.isAllDayLeave) "UTC" else TimeZone.getDefault().id)
                    put(CalendarContract.Events.DTSTART, newStartMs)
                    put(CalendarContract.Events.DTEND, newEndMs)
                }
                val insertedUri = resolver.insert(CalendarContract.Events.CONTENT_URI, values)
                val newEventId = insertedUri?.lastPathSegment?.toLongOrNull()

                detectedChanges.add(
                    CalendarChangeItem(
                        id = UUID.randomUUID().toString(),
                        type = ChangeType.ADDED,
                        calendarId = calendarId,
                        eventId = newEventId,
                        title = desiredTitle,
                        startMs = newStartMs,
                        endMs = newEndMs,
                        isAllDay = shift.isAllDayLeave
                    )
                )
            }
        }

        for (removedEx in unmatchedOwned) {
            val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, removedEx.eventId)
            resolver.delete(uri, null, null)

            detectedChanges.add(
                CalendarChangeItem(
                    id = UUID.randomUUID().toString(),
                    type = ChangeType.REMOVED,
                    calendarId = calendarId,
                    eventId = null,
                    title = removedEx.title,
                    startMs = removedEx.startMs,
                    endMs = removedEx.endMs,
                    isAllDay = removedEx.isAllDay,
                    prevTitle = removedEx.title,
                    prevStartMs = removedEx.startMs,
                    prevEndMs = removedEx.endMs,
                    prevIsAllDay = removedEx.isAllDay
                )
            )
        }

        if (detectedChanges.isNotEmpty()) {
            CalendarChangeTracker.saveChanges(context, detectedChanges)
            ShiftReminderReceiver.showCalendarChangesNotification(context, detectedChanges)
        }

        return detectedChanges
    }

    private fun isSameCalendarDay(ms1: Long, ms2: Long, isAllDay: Boolean): Boolean {
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
        }

        val sortedShifts = userShifts.sortedBy { it.startMs }
        val maxGapMs = 15L * 60_000L

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
                }
            }

            if (!continuesToNext) {
                val endTrigger = current.endMs - (minutesBefore * 60_000L)
                if (endTrigger > now) {
                    val endStr = Instant.ofEpochMilli(current.endMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                    setExactAlarmSafe(context, alarmManager, endTrigger, current.displayTitle, endStr, isEnding = true)
                }
            }
        }
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
    }
}
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"[OK] Päivitetty: {filepath}")

def patch_main_activity(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    old_demo = r"""            if (wantIn != currentlyIn) {
                webView.evaluateJavascript("DemoBridge.toggleStamp()", null)
            } else {
                val stateStr = if (wantIn) "Sisään" else "Ulos"
                Toast.makeText(this, "Demotila: Olet jo leimannut tilaan $stateStr", Toast.LENGTH_SHORT).show()
            }"""

    new_demo = r"""            if (wantIn != currentlyIn) {
                webView.evaluateJavascript("DemoBridge.toggleStamp()", null)
                webView.postDelayed({ finishAndRemoveTask() }, 1200L)
            } else {
                val stateStr = if (wantIn) "Sisään" else "Ulos"
                Toast.makeText(this, "Demotila: Olet jo leimannut tilaan $stateStr", Toast.LENGTH_SHORT).show()
                webView.postDelayed({ finishAndRemoveTask() }, 1200L)
            }"""

    old_stamp = r"""        webView.evaluateJavascript(js) { result ->
            val cleanResult = result.replace("\"", "")
            when {
                cleanResult.startsWith("STAMPED_") -> {
                    Toast.makeText(this, "Leimaus suoritettu ($targetText)", Toast.LENGTH_SHORT).show()
                }
                cleanResult.startsWith("WRONG_DIRECTION_") -> {
                    Toast.makeText(this, "Olet jo leimannut tilaan: $targetText", Toast.LENGTH_LONG).show()
                }
            }
        }"""

    new_stamp = r"""        webView.evaluateJavascript(js) { result ->
            val cleanResult = result.replace("\"", "")
            when {
                cleanResult.startsWith("STAMPED_") -> {
                    Toast.makeText(this, "Leimaus suoritettu ($targetText)", Toast.LENGTH_SHORT).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                }
                cleanResult.startsWith("WRONG_DIRECTION_") -> {
                    Toast.makeText(this, "Olet jo leimannut tilaan: $targetText", Toast.LENGTH_LONG).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                }
            }
        }"""

    if old_demo not in content or old_stamp not in content:
        print("[VIRHE] MainActivity.kt odotettuja lohkoja ei löytynyt!")
        sys.exit(1)

    content = content.replace(old_demo, new_demo, 1).replace(old_stamp, new_stamp, 1)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[OK] Päivitetty: {filepath}")

if __name__ == "__main__":
    files = {
        "SettingsDialogHelper.kt": patch_settings_dialog_helper,
        "CalendarSyncHelper.kt": patch_calendar_sync_helper,
        "MainActivity.kt": patch_main_activity,
    }
    for fname, fn in files.items():
        path = find_file(fname)
        if path:
            fn(path)
        else:
            print(f"[VIRHE] Tiedostoa {fname} ei löytynyt!")
            sys.exit(1)
