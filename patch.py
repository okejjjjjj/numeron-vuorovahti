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
    new_content = f"""package fi.numeron.vuorovahti

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
) {{
    override fun toString(): String {{
        val typeTag = if (accountType == "com.google") "Google" else "Paikallinen"
        return "$name ($accountName) [$typeTag]"
    }}
}}

data class ShiftColorChoice(
    val name: String,
    val rgb: Int
) {{
    override fun toString(): String = name
}}

object SettingsDialogHelper {{

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

    fun getAvailableCalendars(context: Context): List<CalendarOption> {{
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {{
            return emptyList()
        }}
        val list = mutableListOf<CalendarOption>()
        val projection = arrayOf(
            CalendarContract.Calendars._ID,
            CalendarContract.Calendars.CALENDAR_DISPLAY_NAME,
            CalendarContract.Calendars.ACCOUNT_NAME,
            CalendarContract.Calendars.ACCOUNT_TYPE,
            CalendarContract.Calendars.IS_PRIMARY
        )
        val selection = "${{CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL}} >= ? AND ${{CalendarContract.Calendars.VISIBLE}} = 1"
        val selectionArgs = arrayOf(CalendarContract.Calendars.CAL_ACCESS_CONTRIBUTOR.toString())

        context.contentResolver.query(
            CalendarContract.Calendars.CONTENT_URI,
            projection,
            selection,
            selectionArgs,
            null
        )?.use {{ cursor ->
            while (cursor.moveToNext()) {{
                val id = cursor.getLong(0)
                val name = cursor.getString(1) ?: "Kalenteri"
                val account = cursor.getString(2) ?: ""
                val accountType = cursor.getString(3) ?: ""
                val isPrimary = cursor.getInt(4) == 1
                list.add(CalendarOption(id, name, account, accountType))
                if (accountType == "com.google" && (isPrimary || name.equals(account, ignoreCase = true))) {{
                    val item = list.removeAt(list.lastIndex)
                    list.add(0, item)
                }}
            }}
        }}
        return list.sortedBy {{ if (it.accountType == "com.google") 0 else 1 }}
    }}

    fun showSettingsDialog(
        context: Context,
        onManualSync: () -> Unit,
        onManageChanges: () -> Unit,
        onTestNotification: () -> Unit,
        onSaved: () -> Unit
    ) {{
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)

        val scrollView = ScrollView(context)
        val layout = LinearLayout(context).apply {{
            orientation = LinearLayout.VERTICAL
            setPadding(48, 36, 48, 24)
        }}
        scrollView.addView(layout)

        fun createLabel(text: String): TextView = TextView(context).apply {{
            this.text = text
            textSize = 13f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, 16, 0, 6)
        }}

        layout.addView(createLabel("Organisaatiotunnus (esim. siunsote)"))
        val editOrg = EditText(context).apply {{
            hint = "siunsote"
            setText(prefs.getString("org_raw_input", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            isSingleLine = true
        }}
        layout.addView(editOrg)

        layout.addView(createLabel("Käyttäjätunnus"))
        val editUser = EditText(context).apply {{
            hint = "Käyttäjätunnus"
            setText(prefs.getString("username", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            isSingleLine = true
        }}
        layout.addView(editUser)

        layout.addView(createLabel("Salasana"))
        val editPass = EditText(context).apply {{
            hint = "Salasana"
            setText(prefs.getString("password", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            isSingleLine = true
        }}
        layout.addView(editPass)

        val tvTestStatus = TextView(context).apply {{
            text = ""
            textSize = 13f
            setPadding(0, 12, 0, 12)
        }}

        val btnTestCredentials = Button(context).apply {{
            text = "Testaa yhteys ja tunnukset"
            setOnClickListener {{
                val normalizedUrl = UrlNormalizer.normalizeOrgUrl(editOrg.text.toString())
                val user = editUser.text.toString().trim()
                val pass = editPass.text.toString()

                if (normalizedUrl.isEmpty()) {{
                    tvTestStatus.setTextColor(Color.parseColor("#EF4444"))
                    tvTestStatus.text = "Virhe: Syötä organisaatiotunnus."
                    return@setOnClickListener
                }}
                if (user.isEmpty() || pass.isEmpty()) {{
                    tvTestStatus.setTextColor(Color.parseColor("#EF4444"))
                    tvTestStatus.text = "Virhe: Syötä käyttäjätunnus ja salasana."
                    return@setOnClickListener
                }}

                isEnabled = false
                tvTestStatus.setTextColor(Color.parseColor("#38BDF8"))
                tvTestStatus.text = "Testataan osoitetta $normalizedUrl..."

                testLoginWithHiddenWebView(context, normalizedUrl, user, pass) {{ success, message ->
                    isEnabled = true
                    tvTestStatus.setTextColor(
                        if (success) Color.parseColor("#10B981") else Color.parseColor("#EF4444")
                    )
                    tvTestStatus.text = message
                }}
            }}
        }}
        layout.addView(btnTestCredentials)
        layout.addView(tvTestStatus)

        layout.addView(createLabel("Kohdekalenteri"))
        val calendars = getAvailableCalendars(context)
        val spinnerCalendar = Spinner(context)
        if (calendars.isNotEmpty()) {{
            val adapter = ArrayAdapter(context, android.R.layout.simple_spinner_dropdown_item, calendars)
            spinnerCalendar.adapter = adapter
            val savedCalId = prefs.getLong("calendar_id", -1L)
            val idx = calendars.indexOfFirst {{ it.id == savedCalId }}
            spinnerCalendar.setSelection(if (idx >= 0) idx else 0)
        }}
        layout.addView(spinnerCalendar)

        fun createColorSpinner(savedRgb: Int): Spinner {{
            val spinner = Spinner(context)
            val adapter = ArrayAdapter(context, android.R.layout.simple_spinner_dropdown_item, SHIFT_COLOR_CHOICES)
            spinner.adapter = adapter
            val idx = SHIFT_COLOR_CHOICES.indexOfFirst {{ it.rgb == savedRgb }}
            if (idx >= 0) spinner.setSelection(idx)
            return spinner
        }}

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
        val editReminder = EditText(context).apply {{
            setText(prefs.getInt("reminder_minutes", 30).toString())
            inputType = InputType.TYPE_CLASS_NUMBER
            isSingleLine = true
        }}
        layout.addView(editReminder)

        val btnSync = Button(context).apply {{
            text = "Synkronoi työvuorot kalenteriin nyt"
            setOnClickListener {{ onManualSync() }}
        }}
        layout.addView(btnSync)

        val btnChanges = Button(context).apply {{
            text = "Hallitse kalenterimuutoksia"
            setOnClickListener {{ onManageChanges() }}
        }}
        layout.addView(btnChanges)

        val btnTestNotif = Button(context).apply {{
            text = "Lähetä testi-ilmoitus"
            setOnClickListener {{ onTestNotification() }}
        }}
        layout.addView(btnTestNotif)

        AlertDialog.Builder(context)
            .setTitle("Vuorovahti – Asetukset")
            .setView(scrollView)
            .setPositiveButton("Tallenna") {{ _, _ ->
                val rawOrg = editOrg.text.toString().trim()
                val normalizedUrl = UrlNormalizer.normalizeOrgUrl(rawOrg)
                val selectedCal = spinnerCalendar.selectedItem as? CalendarOption
                val reminderMins = editReminder.text.toString().toIntOrNull() ?: 30

                val morningRgb = (spinnerMorningColor.selectedItem as? ShiftColorChoice)?.rgb ?: DEFAULT_MORNING_RGB
                val eveningRgb = (spinnerEveningColor.selectedItem as? ShiftColorChoice)?.rgb ?: DEFAULT_EVENING_RGB
                val nightRgb = (spinnerNightColor.selectedItem as? ShiftColorChoice)?.rgb ?: DEFAULT_NIGHT_RGB

                prefs.edit()
                    .putString("org_raw_input", rawOrg)
                    .putString("server_url", normalizedUrl)
                    .putString("username", editUser.text.toString().trim())
                    .putString("password", editPass.text.toString())
                    .putInt("reminder_minutes", reminderMins)
                    .putInt("color_morning_rgb", morningRgb)
                    .putInt("color_evening_rgb", eveningRgb)
                    .putInt("color_night_rgb", nightRgb)
                    .apply {{
                        if (selectedCal != null) putLong("calendar_id", selectedCal.id)
                    }}
                    .apply()

                Toast.makeText(context, "Tallennettu ($normalizedUrl)", Toast.LENGTH_SHORT).show()
                onSaved()
            }}
            .setNegativeButton("Peruuta", null)
            .show()
    }}

    private fun testLoginWithHiddenWebView(
        context: Context,
        baseUrl: String,
        username: String,
        password: String,
        callback: (Boolean, String) -> Unit
    ) {{
        val testWebView = WebView(context).apply {{
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
        }}

        CookieManager.getInstance().removeAllCookies(null)

        var loginAttempted = false
        var finished = false

        fun cleanupAndRespond(success: Boolean, msg: String) {{
            if (finished) return
            finished = true
            testWebView.stopLoading()
            testWebView.destroy()
            callback(success, msg)
        }}

        testWebView.webViewClient = object : WebViewClient() {{
            override fun onReceivedError(
                view: WebView?,
                errorCode: Int,
                description: String?,
                failingUrl: String?
            ) {{
                cleanupAndRespond(
                    false,
                    "Yhteysvirhe: Organisaatiota '$baseUrl' ei löytynyt tai verkkoyhteys puuttuu."
                )
            }}

            override fun onPageFinished(view: WebView?, url: String?) {{
                if (url == null || finished) return

                if (url.contains("/Login/Login", ignoreCase = true)) {{
                    if (!loginAttempted) {{
                        loginAttempted = true
                        val safeUser = username.replace("\\\\", "\\\\\\\\").replace("'", "\\\\'")
                        val safePass = password.replace("\\\\", "\\\\\\\\").replace("'", "\\\\'")
                        val js = {tq}
                            (function() {{
                                var u = document.getElementById('Username');
                                var p = document.getElementById('Password');
                                var f = document.getElementById('LoginForm');
                                if (u && p && f) {{
                                    u.value = '$safeUser';
                                    p.value = '$safePass';
                                    f.submit();
                                    return 'SUBMITTED';
                                }}
                                return 'NO_FORM';
                            }})();
                        {tq}.trimIndent()
                        view?.evaluateJavascript(js) {{ res ->
                            if (res?.contains("NO_FORM") == true) {{
                                cleanupAndRespond(false, "Virhe: Kirjautumislomaketta ei tunnistettu sivulta.")
                            }}
                        }}
                    }} else {{
                        val errJs = {tq}
                            (function() {{
                                var err = document.querySelector('.validation-summary-errors, .alert-danger');
                                return err ? err.innerText.trim() : '';
                            }})();
                        {tq}.trimIndent()
                        view?.evaluateJavascript(errJs) {{ errText ->
                            val cleanErr = errText?.replace("\\"", "")?.trim() ?: ""
                            if (cleanErr.isNotEmpty()) {{
                                cleanupAndRespond(false, "Kirjautuminen epäonnistui: $cleanErr")
                            }} else {{
                                cleanupAndRespond(false, "Virheellinen käyttäjätunnus tai salasana.")
                            }}
                        }}
                    }}
                }} else if (
                    url.contains("/WorktimeStamping", ignoreCase = true) ||
                    url.contains("/InfraDashboard", ignoreCase = true) ||
                    url.contains("/Calendar", ignoreCase = true)
                ) {{
                    cleanupAndRespond(true, "Yhteys ja tunnukset toimivat! ($baseUrl)")
                }}
            }}
        }}

        testWebView.loadUrl("$baseUrl/Login/Login")
    }}
}}
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"[OK] Päivitetty: {filepath}")

def patch_calendar_sync_helper(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    old_block = """    private fun resolveGoogleShiftColorKeys(context: Context, calendarId: Long): ShiftColorKeys {
        val resolver = context.contentResolver"""
    new_block = """    private fun resolveGoogleShiftColorKeys(context: Context, calendarId: Long): ShiftColorKeys {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val morningRgb = prefs.getInt("color_morning_rgb", SettingsDialogHelper.DEFAULT_MORNING_RGB)
        val eveningRgb = prefs.getInt("color_evening_rgb", SettingsDialogHelper.DEFAULT_EVENING_RGB)
        val nightRgb = prefs.getInt("color_night_rgb", SettingsDialogHelper.DEFAULT_NIGHT_RGB)
        val resolver = context.contentResolver"""

    old_colors = """        // Google Calendarin tapahtumavärien tavoitesävyt: vihreä (Basil/Sage), oranssi (Tangerine), lila (Grape)
        val greenKey = findClosestKey(Color.rgb(11, 128, 67))
        val orangeKey = findClosestKey(Color.rgb(244, 81, 30))
        val purpleKey = findClosestKey(Color.rgb(142, 36, 170))"""
    new_colors = """        val greenKey = findClosestKey(morningRgb)
        val orangeKey = findClosestKey(eveningRgb)
        val purpleKey = findClosestKey(nightRgb)"""

    if old_block in content and old_colors in content:
        content = content.replace(old_block, new_block, 1).replace(old_colors, new_colors, 1)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[OK] Päivitetty: {filepath}")
    else:
        print(f"[VAROITUS] Odotettua koodia ei löytynyt tiedostosta {filepath}")

def patch_shift_reminder_receiver(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    old_quick_stamp = """        // 2. Käyttäjä painoi ilmoituksen "Leimaa sisään/ulos" -painiketta
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
        }"""

    new_quick_stamp = """        // 2. Käyttäjä painoi ilmoituksen "Leimaa sisään/ulos" -painiketta
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
        }"""

    old_show_sig = """    fun showReminderNotification(
        context: Context,
        shiftTitle: String,
        timeStr: String,
        isEnding: Boolean
    ) {"""

    new_show_sig = """    fun showReminderNotification(
        context: Context,
        shiftTitle: String,
        timeStr: String,
        isEnding: Boolean,
        isTest: Boolean = false
    ) {"""

    old_stamp_intent = """        val stampIntent = Intent(context, ShiftReminderReceiver::class.java).apply {
            action = ACTION_QUICK_STAMP
            putExtra("IS_ENDING", isEnding)
            putExtra("NOTIF_ID", notifId)
        }"""

    new_stamp_intent = """        val stampIntent = Intent(context, ShiftReminderReceiver::class.java).apply {
            action = ACTION_QUICK_STAMP
            putExtra("IS_ENDING", isEnding)
            putExtra("IS_TEST", isTest)
            putExtra("NOTIF_ID", notifId)
        }"""

    if old_quick_stamp in content and old_show_sig in content and old_stamp_intent in content:
        content = (
            content.replace(old_quick_stamp, new_quick_stamp, 1)
            .replace(old_show_sig, new_show_sig, 1)
            .replace(old_stamp_intent, new_stamp_intent, 1)
        )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[OK] Päivitetty: {filepath}")
    else:
        print(f"[VAROITUS] Odotettua koodia ei löytynyt tiedostosta {filepath}")

def patch_main_activity(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    old_test_notif = """    private fun triggerTestReminderNotification() {
        val timeStr = LocalTime.now().plusMinutes(30).format(DateTimeFormatter.ofPattern("HH:mm"))
        ShiftReminderReceiver().showReminderNotification(
            context = this,
            shiftTitle = "Aamuvuoro (Testi-ilmoitus)",
            timeStr = timeStr,
            isEnding = false
        )
    }"""

    new_test_notif = """    private fun triggerTestReminderNotification() {
        val timeStr = LocalTime.now().plusMinutes(30).format(DateTimeFormatter.ofPattern("HH:mm"))
        ShiftReminderReceiver().showReminderNotification(
            context = this,
            shiftTitle = "Aamuvuoro (Testi-ilmoitus)",
            timeStr = timeStr,
            isEnding = false,
            isTest = true
        )
    }"""

    old_incoming = """    private fun handleIncomingIntent(intent: Intent?) {
        if (intent?.getBooleanExtra("AUTO_STAMP", false) == true) {
            val isEnding = intent.getBooleanExtra("IS_ENDING", false)
            intent.removeExtra("AUTO_STAMP")
            pendingAction = if (isEnding) Action.STAMP_OUT else Action.STAMP_IN
            Toast.makeText(this, "Suoritetaan automaattinen leimaus...", Toast.LENGTH_SHORT).show()
        }
    }"""

    new_incoming = """    private fun handleIncomingIntent(intent: Intent?) {
        if (intent?.getBooleanExtra("AUTO_STAMP", false) == true) {
            val isEnding = intent.getBooleanExtra("IS_ENDING", false)
            val isTest = intent.getBooleanExtra("IS_TEST", false)
            intent.removeExtra("AUTO_STAMP")
            intent.removeExtra("IS_TEST")

            if (isTest) {
                val dir = if (isEnding) "Ulos" else "Sisään"
                Toast.makeText(
                    this,
                    "Testi-ilmoitus ($dir): Oikeaa leimausta ei suoritettu",
                    Toast.LENGTH_LONG
                ).show()
                return
            }

            pendingAction = if (isEnding) Action.STAMP_OUT else Action.STAMP_IN
            Toast.makeText(this, "Suoritetaan automaattinen leimaus...", Toast.LENGTH_SHORT).show()
        }
    }"""

    if old_test_notif in content and old_incoming in content:
        content = content.replace(old_test_notif, new_test_notif, 1).replace(old_incoming, new_incoming, 1)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[OK] Päivitetty: {filepath}")
    else:
        print(f"[VAROITUS] Odotettua koodia ei löytynyt tiedostosta {filepath}")

if __name__ == "__main__":
    files = {
        "SettingsDialogHelper.kt": patch_settings_dialog_helper,
        "CalendarSyncHelper.kt": patch_calendar_sync_helper,
        "ShiftReminderReceiver.kt": patch_shift_reminder_receiver,
        "MainActivity.kt": patch_main_activity,
    }
    for fname, fn in files.items():
        path = find_file(fname)
        if path:
            fn(path)
        else:
            print(f"[VIRHE] Tiedostoa {fname} ei löytynyt!")
            sys.exit(1)
