package fi.numeron.vuorovahti

import android.Manifest
import android.app.AlertDialog
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.provider.CalendarContract
import android.content.res.ColorStateList
import android.text.InputType
import android.text.method.PasswordTransformationMethod
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.ContextCompat
import androidx.work.WorkManager
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

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

    private fun formatTimestamp(ms: Long, fallback: String): String {
        if (ms <= 0L) return fallback
        val fmt = DateTimeFormatter.ofPattern("dd.MM.yyyy 'klo' HH:mm")
        return Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).format(fmt)
    }

    private fun resolveNextSyncMs(context: Context, fallbackSavedMs: Long): Long {
        try {
            val infos = WorkManager.getInstance(context)
                .getWorkInfosForUniqueWork("NumeronVuorovahtiSync")
                .get()
            val nextRun = infos.firstOrNull { !it.state.isFinished }?.nextScheduleTimeMillis ?: 0L
            if (nextRun > System.currentTimeMillis() && nextRun < Long.MAX_VALUE) {
                return nextRun
            }
        } catch (_: Exception) {
        }
        return fallbackSavedMs
    }

    fun showSettingsDialog(
        context: Context,
        onManualSync: () -> Unit,
        onManageChanges: () -> Unit,
        onTestNotification: () -> Unit,
        onSaved: () -> Unit
    ) {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val density = context.resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()

        fun makeCardBg(fillHex: String = "#182332", strokeHex: String = "#2A394A", radiusDp: Int = 12): GradientDrawable {
            return GradientDrawable().apply {
                setColor(Color.parseColor(fillHex))
                setStroke(dp(1), Color.parseColor(strokeHex))
                cornerRadius = dp(radiusDp).toFloat()
            }
        }

        val rootContainer = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#0F1722"))
        }

        val headerBar = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(20), dp(18), dp(20), dp(14))
        }
        headerBar.addView(TextView(context).apply {
            text = "Vuorovahti – Asetukset"
            textSize = 19f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#F1F5F9"))
        })
        headerBar.addView(TextView(context).apply {
            text = "Tunnukset, kalenterisynkronointi ja ilmoitukset"
            textSize = 12f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, dp(2), 0, 0)
        })
        rootContainer.addView(headerBar)

        val divider = View(context).apply {
            setBackgroundColor(Color.parseColor("#2A394A"))
        }
        rootContainer.addView(divider, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)))

        val scrollView = ScrollView(context).apply {
            isFillViewport = true
        }
        val layout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(14), dp(16), dp(16))
        }
        scrollView.addView(layout)
        rootContainer.addView(scrollView, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))

        fun createSectionCard(title: String): LinearLayout {
            val card = LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                background = makeCardBg("#182332", "#2A394A", 12)
                setPadding(dp(16), dp(14), dp(16), dp(16))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    bottomMargin = dp(14)
                }
            }
            val sectionHeader = TextView(context).apply {
                text = title.uppercase()
                textSize = 11f
                letterSpacing = 0.06f
                setTypeface(null, Typeface.BOLD)
                setTextColor(Color.parseColor("#38BDF8"))
                setPadding(0, 0, 0, dp(8))
            }
            card.addView(sectionHeader)
            layout.addView(card)
            return card
        }

        fun createLabel(text: String): TextView = TextView(context).apply {
            this.text = text
            textSize = 13f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, dp(10), 0, dp(5))
        }

        fun styleEditText(et: EditText) {
            et.background = makeCardBg("#111923", "#37475A", 8)
            et.setTextColor(Color.parseColor("#F1F5F9"))
            et.setHintTextColor(Color.parseColor("#64748B"))
            et.setPadding(dp(12), dp(10), dp(12), dp(10))
            et.textSize = 14f
        }

        fun styleButton(btn: Button, bgHex: String = "#233040", strokeHex: String = "#37475A", textHex: String = "#F1F5F9") {
            btn.background = makeCardBg(bgHex, strokeHex, 8)
            btn.setTextColor(Color.parseColor(textHex))
            btn.isAllCaps = false
            btn.textSize = 14f
            btn.setTypeface(null, Typeface.BOLD)
            btn.setPadding(dp(14), dp(11), dp(14), dp(11))
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                topMargin = dp(10)
            }
            btn.layoutParams = lp
        }

        fun styleSpinner(spinner: Spinner) {
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
        }

        fun createDarkAdapter(items: List<Any>): ArrayAdapter<Any> {
            return object : ArrayAdapter<Any>(context, android.R.layout.simple_spinner_item, items) {
                override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
                    val tv = super.getView(position, convertView, parent) as TextView
                    tv.setTextColor(Color.parseColor("#F1F5F9"))
                    tv.textSize = 14f
                    return tv
                }

                override fun getDropDownView(position: Int, convertView: View?, parent: ViewGroup): View {
                    val tv = super.getDropDownView(position, convertView, parent) as TextView
                    tv.setBackgroundColor(Color.parseColor("#1E293B"))
                    tv.setTextColor(Color.parseColor("#F1F5F9"))
                    tv.setPadding(dp(14), dp(12), dp(14), dp(12))
                    tv.textSize = 14f
                    return tv
                }
            }
        }

        // === KORTTI 1: TILA JA AIKATAULUT ===
        val statusCard = createSectionCard("Tila ja aikataulut")

        val initialSyncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
        val initialShiftReminders = prefs.getBoolean("shift_reminders_enabled", true)
        val initialTrackRequests = prefs.getBoolean("track_requests", true)
        val anyBackgroundEnabled = initialSyncCalendar || initialShiftReminders || initialTrackRequests

        val lastSyncMs = prefs.getLong("last_calendar_sync_ms", 0L)
        val nextSyncMs = resolveNextSyncMs(context, prefs.getLong("next_calendar_sync_ms", 0L))
        val lastNotifMs = prefs.getLong("last_reminder_sent_ms", 0L)
        val lastNotifLabel = prefs.getString("last_reminder_sent_label", "") ?: ""
        val nextNotifMs = prefs.getLong("next_reminder_ms", 0L)
        val nextNotifLabel = prefs.getString("next_reminder_label", "") ?: ""

        fun addStatusRow(parent: LinearLayout, title: String, value: String, subValue: String? = null) {
            val box = LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                background = makeCardBg("#111923", "#233040", 8)
                setPadding(dp(12), dp(9), dp(12), dp(9))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    bottomMargin = dp(8)
                }
            }
            box.addView(TextView(context).apply {
                text = title
                textSize = 11f
                setTextColor(Color.parseColor("#94A3B8"))
            })
            box.addView(TextView(context).apply {
                text = value
                textSize = 14f
                setTypeface(null, Typeface.BOLD)
                setTextColor(Color.parseColor("#F1F5F9"))
                setPadding(0, dp(2), 0, 0)
            })
            if (!subValue.isNullOrEmpty()) {
                box.addView(TextView(context).apply {
                    text = subValue
                    textSize = 12f
                    setTextColor(Color.parseColor("#38BDF8"))
                    setPadding(0, dp(2), 0, 0)
                })
            }
            parent.addView(box)
        }

        addStatusRow(
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
        )

        val exactAlarmAllowed = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            (context.getSystemService(Context.ALARM_SERVICE) as android.app.AlarmManager).canScheduleExactAlarms()
        } else {
            true
        }
        addStatusRow(
            statusCard,
            "Tarkat vuorohälytykset",
            if (exactAlarmAllowed) "Sallittu" else "Rajoitettu – napauta salliaksesi",
            if (exactAlarmAllowed) null else "Avaa järjestelmän hälytysasetukset"
        )
        if (!exactAlarmAllowed && android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            statusCard.getChildAt(statusCard.childCount - 1).setOnClickListener {
                try {
                    context.startActivity(
                        android.content.Intent(
                            android.provider.Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                            android.net.Uri.parse("package:${context.packageName}")
                        ).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                    )
                } catch (_: Exception) {
                }
            }
        }

        val powerManager = context.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        val ignoringBatteryOpt = powerManager.isIgnoringBatteryOptimizations(context.packageName)
        addStatusRow(
            statusCard,
            "Akun virransäästörajoitukset",
            if (ignoringBatteryOpt) "Ei rajoitettu (taustasynkronointi aktiivinen)" else "Optimoitu – napauta poistaaksesi rajoitus",
            if (ignoringBatteryOpt) null else "Varmistaa tausta-ajojen toiminnan lepotilassa"
        )
        if (!ignoringBatteryOpt) {
            statusCard.getChildAt(statusCard.childCount - 1).setOnClickListener {
                try {
                    context.startActivity(
                        android.content.Intent(
                            android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                            android.net.Uri.parse("package:${context.packageName}")
                        ).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                    )
                } catch (_: Exception) {
                }
            }
        }

        // === KORTTI 2: KIRJAUTUMINEN JA YHTEYS ===
        val authCard = createSectionCard("Kirjautuminen ja yhteys")

        authCard.addView(createLabel("Organisaatiotunnus (esim. siunsote)"))
        val editOrg = EditText(context).apply {
            hint = "siunsote"
            setText(prefs.getString("org_raw_input", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            isSingleLine = true
            styleEditText(this)
        }
        authCard.addView(editOrg)

        authCard.addView(createLabel("Käyttäjätunnus"))
        val editUser = EditText(context).apply {
            hint = "Käyttäjätunnus"
            setText(SecureCredentialManager.getUsername(context) ?: "")
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            isSingleLine = true
            styleEditText(this)
        }
        authCard.addView(editUser)

        val existingPassword = SecureCredentialManager.getPassword(context) ?: ""
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
        authCard.addView(editPass)

        val tvTestStatus = TextView(context).apply {
            text = ""
            textSize = 13f
            setPadding(0, dp(8), 0, dp(2))
        }

        val btnTestCredentials = Button(context).apply {
            text = "Testaa yhteys ja tunnukset"
            styleButton(this, "#1E3A5F", "#0284C7", "#E0F2FE")
            setOnClickListener {
                val normalizedUrl = UrlNormalizer.normalizeOrgUrl(editOrg.text.toString())
                val user = editUser.text.toString().trim()
                val typedPass = editPass.text.toString()
                val pass = if (typedPass.isNotEmpty()) typedPass else existingPassword

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
                if (DemoModeHelper.isDemoCredentials(editOrg.text.toString(), user, pass)) {
                    tvTestStatus.setTextColor(Color.parseColor("#10B981"))
                    tvTestStatus.text = "Demotila tunnistettu! Tallenna asetukset ottaaksesi demotilan käyttöön."
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
        authCard.addView(btnTestCredentials)
        authCard.addView(tvTestStatus)

        // === KORTTI 3: KALENTERISYNRONOINTI JA VÄRIKOODIT ===
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
        actionCard.addView(btnTestNotif)

        // Alapalkki: Peruuta ja Tallenna
        val bottomDivider = View(context).apply {
            setBackgroundColor(Color.parseColor("#2A394A"))
        }
        rootContainer.addView(bottomDivider, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)))

        val footerBar = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(16), dp(12), dp(16), dp(12))
        }

        val btnCancel = Button(context).apply {
            text = "Peruuta"
            background = makeCardBg("#233040", "#37475A", 8)
            setTextColor(Color.parseColor("#CBD5E1"))
            isAllCaps = false
            textSize = 14f
            setPadding(dp(18), dp(10), dp(18), dp(10))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                marginEnd = dp(10)
            }
        }

        val btnSave = Button(context).apply {
            text = "Tallenna"
            background = makeCardBg("#1982C4", "#38BDF8", 8)
            setTextColor(Color.parseColor("#FFFFFF"))
            isAllCaps = false
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            setPadding(dp(22), dp(10), dp(22), dp(10))
        }

        footerBar.addView(btnCancel)
        footerBar.addView(btnSave)
        rootContainer.addView(footerBar)

        val dialog = AlertDialog.Builder(context)
            .setView(rootContainer)
            .create()

        dialog.window?.setBackgroundDrawable(makeCardBg("#0F1722", "#2A394A", 14))

        btnSync.setOnClickListener {
            dialog.dismiss()
            onManualSync()
        }

        btnChanges.setOnClickListener {
            dialog.dismiss()
            onManageChanges()
        }

        btnTestNotif.setOnClickListener {
            onTestNotification()
        }

        btnCancel.setOnClickListener {
            dialog.dismiss()
        }

        btnSave.setOnClickListener {
            val rawOrg = editOrg.text.toString().trim()
            val normalizedUrl = UrlNormalizer.normalizeOrgUrl(rawOrg)
            val selectedCal = spinnerCalendar.selectedItem as? CalendarOption
            val userTag = editUserTag.text.toString().trim()
            val reminderMins = editReminder.text.toString().toIntOrNull() ?: 30

            val morningRgb = (spinnerMorningColor.selectedItem as? ShiftColorChoice)?.rgb ?: DEFAULT_MORNING_RGB
            val eveningRgb = (spinnerEveningColor.selectedItem as? ShiftColorChoice)?.rgb ?: DEFAULT_EVENING_RGB
            val nightRgb = (spinnerNightColor.selectedItem as? ShiftColorChoice)?.rgb ?: DEFAULT_NIGHT_RGB

            val savedUser = editUser.text.toString().trim()
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
            }
        }

        dialog.show()
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
    }
}
