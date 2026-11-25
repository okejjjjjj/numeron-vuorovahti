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
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.Switch
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.work.WorkManager
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

data class CalendarOption(
    val id: Long,
    val name: String,
    val accountName: String,
    val accountType: String,
    val isEnglish: Boolean = false
) {
    override fun toString(): String {
        val typeTag = if (accountType == "com.google") "Google" else if (isEnglish) "Local" else "Paikallinen"
        return "$name ($accountName) [$typeTag]"
    }
}

data class ShiftColorChoice(
    val name: String,
    val rgb: Int,
    val enName: String = name,
    val isEnglish: Boolean = false
) {
    override fun toString(): String = if (isEnglish) enName else name
}

object SettingsDialogHelper {

    const val PRIVACY_POLICY_URL = "https://github.com/okejjjjjj/numeron-vuorovahti/blob/main/privacy.md"

    val SHIFT_COLOR_CHOICES = listOf(
        ShiftColorChoice("Basilika (Vihreä)", Color.rgb(11, 128, 67), "Basil (Green)"),
        ShiftColorChoice("Salvia (Vaaleanvihreä)", Color.rgb(51, 182, 121), "Sage (Light green)"),
        ShiftColorChoice("Mandariini (Oranssi)", Color.rgb(244, 81, 30), "Tangerine (Orange)"),
        ShiftColorChoice("Banaani (Keltainen)", Color.rgb(246, 191, 38), "Banana (Yellow)"),
        ShiftColorChoice("Viinirypäle (Lila)", Color.rgb(142, 36, 170), "Grape (Purple)"),
        ShiftColorChoice("Mustikka (Sininen)", Color.rgb(63, 81, 181), "Blueberry (Blue)"),
        ShiftColorChoice("Riikinkukko (Turkoosi)", Color.rgb(3, 155, 229), "Peacock (Turquoise)"),
        ShiftColorChoice("Flamingo (Vaaleanpunainen)", Color.rgb(230, 124, 115), "Flamingo (Pink)"),
        ShiftColorChoice("Tomaatti (Punainen)", Color.rgb(213, 0, 0), "Tomato (Red)"),
        ShiftColorChoice("Grafiitti (Harmaa)", Color.rgb(97, 97, 97), "Graphite (Gray)")
    )

    val DEFAULT_MORNING_RGB = Color.rgb(11, 128, 67)
    val DEFAULT_EVENING_RGB = Color.rgb(246, 191, 38)
    val DEFAULT_NIGHT_RGB = Color.rgb(142, 36, 170)

        fun getAvailableCalendars(context: Context): List<CalendarOption> {
        val en = DemoModeHelper.isEnglish(context)
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return emptyList()
        }
        val list = mutableListOf<Pair<CalendarOption, Boolean>>()
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
                val name = cursor.getString(1) ?: (if (en) "Calendar" else "Kalenteri")
                val account = cursor.getString(2) ?: ""
                val accountType = cursor.getString(3) ?: ""
                val isPrimary = cursor.getInt(4) == 1
                list.add(CalendarOption(id, name, account, accountType, en) to isPrimary)
            }
        }
        return list
            .sortedWith(
                compareBy<Pair<CalendarOption, Boolean>>(
                    { if (it.first.accountType == "com.google") 0 else 1 },
                    { if (it.second) 0 else 1 },
                    { it.first.id }
                )
            )
            .map { it.first }
    }


    private fun formatTimestamp(ms: Long, fallback: String, en: Boolean = false): String {
        if (ms <= 0L) return fallback
        val fmt = DateTimeFormatter.ofPattern(if (en) "dd.MM.yyyy 'at' HH:mm" else "dd.MM.yyyy 'klo' HH:mm")
        return Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).format(fmt)
    }

    fun showSettingsDialog(
        context: Context,
        onManualSync: () -> Unit,
        onManageChanges: () -> Unit,
        onTestNotification: () -> Unit,
        onSaved: () -> Unit
    ) {
        val en = DemoModeHelper.isEnglish(context)
        val isDemoActive = DemoModeHelper.isDemoEnabled(context)
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
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(20), dp(18), dp(20), dp(14))
        }
        val headerTitleCol = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }
        headerTitleCol.addView(TextView(context).apply {
            text = if (en) "Vuorovahti – Settings" else "Vuorovahti – Asetukset"
            textSize = 19f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#F1F5F9"))
        })
        headerTitleCol.addView(TextView(context).apply {
            text = if (en) "Credentials, calendar sync & notifications" else "Tunnukset, kalenterisynkronointi ja ilmoitukset"
            textSize = 12f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, dp(2), 0, 0)
        })
        headerBar.addView(headerTitleCol)

        var dialogRef: AlertDialog? = null
        var testCredentialsJob: kotlinx.coroutines.Job? = null

        if (isDemoActive) {
            val langPill = LinearLayout(context).apply {
                orientation = LinearLayout.HORIZONTAL
                background = makeCardBg("#111923", "#2A394A", 8)
                setPadding(dp(2), dp(2), dp(2), dp(2))
            }
            fun makeLangBtn(label: String, targetLang: String, active: Boolean): TextView {
                return TextView(context).apply {
                    text = label
                    textSize = 11f
                    setTypeface(null, Typeface.BOLD)
                    setTextColor(Color.parseColor(if (active) "#FFFFFF" else "#94A3B8"))
                    setPadding(dp(9), dp(5), dp(9), dp(5))
                    if (active) {
                        background = makeCardBg("#1982C4", "#38BDF8", 6)
                    }
                    setOnClickListener {
                        DemoModeHelper.setDemoLanguage(context, targetLang)
                        dialogRef?.dismiss()
                        onSaved()
                        showSettingsDialog(context, onManualSync, onManageChanges, onTestNotification, onSaved)
                    }
                }
            }
            langPill.addView(makeLangBtn("FI", "fi", !en))
            langPill.addView(makeLangBtn("EN", "en", en))
            headerBar.addView(langPill)
        }

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
        val statusCard = createSectionCard(if (en) "Status and schedules" else "Tila ja aikataulut")

        val initialSyncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
        val initialShiftReminders = prefs.getBoolean("shift_reminders_enabled", true)
        val initialTrackRequests = prefs.getBoolean("track_requests", true)
        val anyBackgroundEnabled = initialSyncCalendar || initialShiftReminders || initialTrackRequests

        val lastSyncMs = prefs.getLong("last_calendar_sync_ms", 0L)
        val lastNotifMs = prefs.getLong("last_reminder_sent_ms", 0L)
        val lastNotifLabel = prefs.getString("last_reminder_sent_label", "") ?: ""
        val nextNotifMs = prefs.getLong("next_reminder_ms", 0L)
        val nextNotifLabel = prefs.getString("next_reminder_label", "") ?: ""

        fun launchSystemSettingsIntent(intent: android.content.Intent): Boolean {
            return try {
                if (context !is android.app.Activity) {
                    intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                context.startActivity(intent)
                true
            } catch (_: Exception) {
                false
            }
        }

        fun openPlayStorePage() {
            val pkg = context.packageName
            val marketIntent = android.content.Intent(
                android.content.Intent.ACTION_VIEW,
                android.net.Uri.parse("market://details?id=$pkg")
            )
            if (!launchSystemSettingsIntent(marketIntent)) {
                launchSystemSettingsIntent(
                    android.content.Intent(
                        android.content.Intent.ACTION_VIEW,
                        android.net.Uri.parse("https://play.google.com/store/apps/details?id=$pkg")
                    )
                )
            }
        }

        fun openPrivacyPolicy() {
            val url = PRIVACY_POLICY_URL.trim()
            val isConfigured = url.startsWith("https://") || url.startsWith("http://")
            if (isConfigured) {
                val opened = launchSystemSettingsIntent(
                    android.content.Intent(
                        android.content.Intent.ACTION_VIEW,
                        android.net.Uri.parse(url)
                    )
                )
                if (!opened) {
                    android.widget.Toast.makeText(
                        context,
                        if (en) "Could not open browser" else "Selainta ei voitu avata",
                        android.widget.Toast.LENGTH_SHORT
                    ).show()
                }
            } else {
                android.widget.Toast.makeText(
                    context,
                    if (en) "Privacy policy URL is not configured yet" else "Tietoturvaselosteen osoitetta ei ole vielä määritetty",
                    android.widget.Toast.LENGTH_LONG
                ).show()
            }
        }

        // Korostettu päivityskehotus ylimmäksi, näytetään vain jos Play-kaupassa on uudempi versio
        val updateBanner = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            background = makeCardBg("#3B2810", "#F59E0B", 12)
            setPadding(dp(16), dp(14), dp(16), dp(14))
            visibility = View.GONE
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                bottomMargin = dp(14)
            }
        }
        updateBanner.addView(TextView(context).apply {
            text = if (en) "UPDATE AVAILABLE" else "PÄIVITYS SAATAVILLA"
            textSize = 11f
            letterSpacing = 0.06f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#FBBF24"))
        })
        val updateBannerSubTv = TextView(context).apply {
            text = if (en) {
                "Your app version is outdated. Update to the latest version from Google Play."
            } else {
                "Käytössäsi ei ole uusin versio. Suosittelemme päivittämään sovelluksen Google Playsta."
            }
            textSize = 13f
            setTextColor(Color.parseColor("#FEF3C7"))
            setPadding(0, dp(4), 0, dp(8))
        }
        updateBanner.addView(updateBannerSubTv)
        val btnBannerUpdate = Button(context).apply {
            text = if (en) "Update on Google Play" else "Päivitä Google Playsta"
            styleButton(this, "#D97706", "#FBBF24", "#FFFFFF")
            (layoutParams as? LinearLayout.LayoutParams)?.topMargin = dp(2)
            setOnClickListener { openPlayStorePage() }
        }
        updateBanner.addView(btnBannerUpdate)
        layout.addView(updateBanner, 0)

        
        fun openBatteryOptimizationSettings() {
            val pkgUri = android.net.Uri.parse("package:${context.packageName}")
            val openedList = launchSystemSettingsIntent(
                android.content.Intent(
                    android.provider.Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS
                )
            )
            if (!openedList) {
                launchSystemSettingsIntent(
                    android.content.Intent(
                        android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        pkgUri
                    )
                )
            }
        }

        fun openNotificationSettings() {
            val pkgUri = android.net.Uri.parse("package:${context.packageName}")
            val notifIntent = android.content.Intent(
                android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS
            ).apply {
                putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, context.packageName)
            }
            if (!launchSystemSettingsIntent(notifIntent)) {
                launchSystemSettingsIntent(
                    android.content.Intent(
                        android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        pkgUri
                    )
                )
            }
        }

        fun areAppNotificationsAllowed(): Boolean {
            val hasRuntimePerm = android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.TIRAMISU ||
                ContextCompat.checkSelfPermission(
                    context,
                    Manifest.permission.POST_NOTIFICATIONS
                ) == PackageManager.PERMISSION_GRANTED
            return hasRuntimePerm &&
                androidx.core.app.NotificationManagerCompat.from(context).areNotificationsEnabled()
        }

        fun addStatusRow(parent: LinearLayout, title: String, value: String, subValue: String? = null): Pair<TextView, TextView> {
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
            val valueTv = TextView(context).apply {
                text = value
                textSize = 14f
                setTypeface(null, Typeface.BOLD)
                setTextColor(Color.parseColor("#F1F5F9"))
                setPadding(0, dp(2), 0, 0)
            }
            box.addView(valueTv)
            val subTv = TextView(context).apply {
                text = subValue ?: ""
                textSize = 12f
                setTextColor(Color.parseColor("#38BDF8"))
                setPadding(0, dp(2), 0, 0)
                visibility = if (!subValue.isNullOrEmpty()) View.VISIBLE else View.GONE
            }
            box.addView(subTv)
            parent.addView(box)
            return Pair(valueTv, subTv)
        }

        addStatusRow(
            statusCard,
            if (en) "Shifts and calendar checked" else "Työvuorot ja kalenteri tarkistettu",
            formatTimestamp(lastSyncMs, if (en) "Not checked yet" else "Ei vielä tarkistettu", en)
        )
        val (nextSyncValueTv, _) = addStatusRow(
            statusCard,
            if (en) "Next automatic check" else "Seuraava automaattinen tarkistus",
            if (!anyBackgroundEnabled) {
                if (en) "Disabled" else "Pois käytöstä"
            } else {
                formatTimestamp(
                    prefs.getLong("next_calendar_sync_ms", 0L),
                    if (en) "Weekdays at 10:15–11:00 and 14:30–15:00" else "Arkisin klo 10:15–11:00 ja 14:30–15:00",
                    en
                )
            }
        )
        if (anyBackgroundEnabled) {
            try {
                val future = WorkManager.getInstance(context).getWorkInfosForUniqueWork("NumeronVuorovahtiSync")
                future.addListener({
                    try {
                        val infos = future.get()
                        val nextRun = infos.firstOrNull { !it.state.isFinished }?.nextScheduleTimeMillis ?: 0L
                        if (nextRun > System.currentTimeMillis() && nextRun < Long.MAX_VALUE) {
                            nextSyncValueTv.text = formatTimestamp(
                                nextRun,
                                if (en) "Weekdays at 10:15–11:00 and 14:30–15:00" else "Arkisin klo 10:15–11:00 ja 14:30–15:00",
                                en
                            )
                        }
                    } catch (_: Exception) {
                    }
                }, ContextCompat.getMainExecutor(context))
            } catch (_: Exception) {
            }
        }
        addStatusRow(
            statusCard,
            if (en) "Last stamp notification sent" else "Edellinen leimausnotifikaatio lähetetty",
            formatTimestamp(lastNotifMs, if (en) "Not sent yet" else "Ei vielä lähetetty", en),
            if (lastNotifMs > 0L) lastNotifLabel else null
        )
        val (nextNotifValueTv, nextNotifSubTv) = addStatusRow(
            statusCard,
            if (en) "Next stamp notification scheduled" else "Seuraava leimausnotifikaatio lähetetään",
            when {
                !initialShiftReminders -> if (en) "Stamp reminders disabled" else "Leimausmuistutukset pois käytöstä"
                nextNotifMs > System.currentTimeMillis() -> formatTimestamp(nextNotifMs, "", en)
                else -> if (en) "No upcoming scheduled alarms" else "Ei tulevia ajoitettuja hälytyksiä"
            },
            if (initialShiftReminders && nextNotifMs > System.currentTimeMillis()) nextNotifLabel else null
        )


        val powerManager = context.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        val ignoringBatteryOpt = powerManager.isIgnoringBatteryOptimizations(context.packageName)
        val (batteryOptValueTv, batteryOptSubTv) = addStatusRow(
            statusCard,
            if (en) "Battery optimization" else "Akun virransäästörajoitukset",
            if (ignoringBatteryOpt) {
                if (en) "Unrestricted (background sync active)" else "Ei rajoitettu (taustasynkronointi aktiivinen)"
            } else {
                if (en) "Optimized – tap to remove restriction" else "Optimoitu – napauta poistaaksesi rajoitus"
            },
            if (ignoringBatteryOpt) {
                if (en) "Tap to open battery settings" else "Napauta avataksesi virransäästöasetukset"
            } else {
                if (en) "Ensures background sync works in sleep mode" else "Varmistaa tausta-ajojen toiminnan lepotilassa"
            }
        )
        statusCard.getChildAt(statusCard.childCount - 1).setOnClickListener {
            openBatteryOptimizationSettings()
        }

        val (notifPermValueTv, notifPermSubTv) = addStatusRow(
            statusCard,
            if (en) "Notification permission" else "Ilmoitusten tila",
            "",
            ""
        )
        statusCard.getChildAt(statusCard.childCount - 1).setOnClickListener {
            openNotificationSettings()
        }

        // === KORTTI 2: KIRJAUTUMINEN JA YHTEYS ===
        val authCard = createSectionCard(if (en) "Login and connection" else "Kirjautuminen ja yhteys")

        authCard.addView(createLabel(if (en) "Organization ID or address (e.g. demo or https://demo.numeronwfm.com)" else "Organisaatiotunnus tai kirjautumisosoite (esim. demo tai https://demo.numeronwfm.com)"))
        val savedOrgPref = (prefs.getString("org_raw_input", "") ?: "").trim()
            .ifEmpty { (prefs.getString("server_url", "") ?: "").trim() }
        val editOrg = EditText(context).apply {
            hint = "demo"
            setText(savedOrgPref)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            isSingleLine = true
            styleEditText(this)
        }
        authCard.addView(editOrg)

        authCard.addView(createLabel(if (en) "Username" else "Käyttäjätunnus"))
        val editUser = EditText(context).apply {
            hint = if (en) "Username" else "Käyttäjätunnus"
            setText(SecureCredentialManager.getUsername(context) ?: "")
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            isSingleLine = true
            styleEditText(this)
        }
        authCard.addView(editUser)

        val existingPassword = SecureCredentialManager.getPassword(context) ?: ""
        val hasSavedPassword = existingPassword.isNotEmpty()

        authCard.addView(createLabel(if (en) "Password" else "Salasana"))
        val editPass = EditText(context).apply {
            hint = if (hasSavedPassword) {
                if (en) "•••••••• (saved – type new to change)" else "•••••••• (tallennettu – kirjoita uusi vaihtaaksesi)"
            } else {
                if (en) "Password" else "Salasana"
            }
            setText("")
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            transformationMethod = PasswordTransformationMethod.getInstance()
            isSingleLine = true
            styleEditText(this)
        }
        authCard.addView(editPass)

        val wasAuthBlocked = !isDemoActive && BackgroundAuthHelper.isCredentialBlocked(context)
        val tvTestStatus = TextView(context).apply {
            text = if (wasAuthBlocked) {
                if (en) {
                    "Automatic login paused after a rejected password. Please verify your credentials and save."
                } else {
                    "Automaattinen kirjautuminen pysäytettiin virheellisen tunnuksen tai salasanan vuoksi. Tarkista tiedot ja tallenna."
                }
            } else {
                ""
            }
            setTextColor(Color.parseColor(if (wasAuthBlocked) "#EF4444" else "#94A3B8"))
            textSize = 13f
            setPadding(0, dp(8), 0, dp(2))
        }

        val btnTestCredentials = Button(context).apply {
            text = if (en) "Test connection and credentials" else "Testaa yhteys ja tunnukset"
            styleButton(this, "#1E3A5F", "#0284C7", "#E0F2FE")
            setOnClickListener {
                val normalizedUrl = UrlNormalizer.normalizeOrgUrl(editOrg.text.toString())
                val user = editUser.text.toString().trim()
                val typedPass = editPass.text.toString()
                val pass = if (typedPass.isNotEmpty()) typedPass else existingPassword

                if (normalizedUrl.isEmpty()) {
                    tvTestStatus.setTextColor(Color.parseColor("#EF4444"))
                    tvTestStatus.text = if (en) "Error: Enter organization ID." else "Virhe: Syötä organisaatiotunnus."
                    return@setOnClickListener
                }
                if (user.isEmpty() || pass.isEmpty()) {
                    tvTestStatus.setTextColor(Color.parseColor("#EF4444"))
                    tvTestStatus.text = if (en) "Error: Enter username and password." else "Virhe: Syötä käyttäjätunnus ja salasana."
                    return@setOnClickListener
                }
                if (DemoModeHelper.isDemoCredentials(editOrg.text.toString(), user, pass)) {
                    tvTestStatus.setTextColor(Color.parseColor("#10B981"))
                    tvTestStatus.text = if (en) {
                        "Demo mode recognized! Save settings to enable demo mode."
                    } else {
                        "Demotila tunnistettu! Tallenna asetukset ottaaksesi demotilan käyttöön."
                    }
                    return@setOnClickListener
                }

                isEnabled = false
                tvTestStatus.setTextColor(Color.parseColor("#38BDF8"))
                tvTestStatus.text = if (en) "Testing address $normalizedUrl..." else "Testataan osoitetta $normalizedUrl..."

                testCredentialsJob?.cancel()
                testCredentialsJob = testLoginWithHiddenWebView(context, normalizedUrl, user, pass) { success, message ->
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
        authCard.addView(TextView(context).apply {
            text = if (en) {
                "Credentials are stored only on your device and sent solely to the Numeron address you enter. They are never shared with third parties or external servers."
            } else {
                "Tunnukset tallennetaan vain laitteellesi ja välitetään ainoastaan antamaasi Numeron-osoitteeseen. Niitä ei tallenneta tai jaeta ulkopuolisille palvelimille."
            }
            textSize = 11f
            setTextColor(Color.parseColor("#64748B"))
            setPadding(0, dp(8), 0, dp(4))
        })
        authCard.addView(TextView(context).apply {
            text = if (en) "Read privacy policy →" else "Lue tietoturvaseloste →"
            textSize = 12.5f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#38BDF8"))
            paintFlags = paintFlags or android.graphics.Paint.UNDERLINE_TEXT_FLAG
            setPadding(0, dp(4), 0, dp(4))
            setOnClickListener { openPrivacyPolicy() }
        })
        
        // === KORTTI 3: KALENTERISYNRONOINTI JA VÄRIKOODIT ===
        val calCard = createSectionCard(if (en) "Calendar sync and color codes" else "Kalenterisynkronointi ja värikoodit")

        val calDetailsContainer = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            visibility = if (initialSyncCalendar) View.VISIBLE else View.GONE
        }

        val switchSyncCalendar = createToggleRow(
            parent = calCard,
            title = if (en) "Sync shifts to Google Calendar" else "Synkronoi työvuorot Google-kalenteriin",
            subtitle = if (en) "Automatically export work shifts and leaves to the selected calendar" else "Vie työvuorot ja poissaolot valittuun kalenteriin automaattisesti",
            initialChecked = initialSyncCalendar
        ) { enabled ->
            calDetailsContainer.visibility = if (enabled) View.VISIBLE else View.GONE
        }

        calDetailsContainer.addView(createLabel(if (en) "Target calendar" else "Kohdekalenteri"))
        val calendars = getAvailableCalendars(context)
        val spinnerCalendar = Spinner(context).apply { styleSpinner(this) }
        if (calendars.isNotEmpty()) {
            spinnerCalendar.adapter = createDarkAdapter(calendars)
            val savedCalId = prefs.getLong("calendar_id", -1L)
            val idx = calendars.indexOfFirst { it.id == savedCalId }
            spinnerCalendar.setSelection(if (idx >= 0) idx else 0)
        }
        calDetailsContainer.addView(spinnerCalendar)

        calDetailsContainer.addView(createLabel(if (en) "Person tag for shared calendar (optional, e.g. Alex)" else "Henkilötunniste yhteiskalenteriin (valinnainen, esim. Jukka)"))
        val editUserTag = EditText(context).apply {
            hint = if (en) "Leave empty for personal calendar" else "Jätä tyhjäksi omassa kalenterissa"
            setText(prefs.getString("calendar_user_tag", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_WORDS
            isSingleLine = true
            styleEditText(this)
        }
        calDetailsContainer.addView(editUserTag)

        val localizedColors = SHIFT_COLOR_CHOICES.map { it.copy(isEnglish = en) }

        fun createColorSpinner(savedRgb: Int): Spinner {
            val spinner = Spinner(context).apply { styleSpinner(this) }
            spinner.adapter = createDarkAdapter(localizedColors)
            val idx = localizedColors.indexOfFirst { it.rgb == savedRgb }
            if (idx >= 0) spinner.setSelection(idx)
            return spinner
        }

        calDetailsContainer.addView(createLabel(if (en) "Morning shift color" else "Aamuvuoron väri"))
        val spinnerMorningColor = createColorSpinner(prefs.getInt("color_morning_rgb", DEFAULT_MORNING_RGB))
        calDetailsContainer.addView(spinnerMorningColor)

        calDetailsContainer.addView(createLabel(if (en) "Evening shift color" else "Iltavuoron väri"))
        val spinnerEveningColor = createColorSpinner(prefs.getInt("color_evening_rgb", DEFAULT_EVENING_RGB))
        calDetailsContainer.addView(spinnerEveningColor)

        calDetailsContainer.addView(createLabel(if (en) "Night shift color" else "Yövuoron väri"))
        val spinnerNightColor = createColorSpinner(prefs.getInt("color_night_rgb", DEFAULT_NIGHT_RGB))
        calDetailsContainer.addView(spinnerNightColor)

        calCard.addView(calDetailsContainer)

        // === KORTTI 4: MUISTUTUKSET JA ILMOITUKSET ===
        val actionCard = createSectionCard(if (en) "Reminders and notifications" else "Muistutukset ja ilmoitukset")

        val reminderDetailsContainer = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            visibility = if (initialShiftReminders) View.VISIBLE else View.GONE
        }

        val switchShiftReminders = createToggleRow(
            parent = actionCard,
            title = if (en) "Shift stamp reminders" else "Työvuorojen leimausmuistutukset",
            subtitle = if (en) "Notification before shift start and end with quick-stamp action (works without calendar sync)" else "Ilmoitus ennen vuoron alkua ja loppua pikaleimauspainikkeella (toimii myös ilman kalenterisynkronointia)",
            initialChecked = initialShiftReminders
        ) { enabled ->
            reminderDetailsContainer.visibility = if (enabled) View.VISIBLE else View.GONE
        }

        reminderDetailsContainer.addView(createLabel(if (en) "Reminder before shift (min)" else "Muistutus ennen vuoroa (min)"))
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
            title = if (en) "Notify about processed requests" else "Ilmoita käsitellyistä toiveista",
            subtitle = if (en) "Sends a notification when your shift or leave request is approved or rejected" else "Lähettää ilmoituksen, kun työvuoro- tai lomatoiveesi hyväksytään tai hylätään",
            initialChecked = initialTrackRequests
        )

        val btnSync = Button(context).apply {
            text = if (en) "Fetch and update shifts now" else "Hae ja päivitä työvuorot nyt"
            styleButton(this, "#1982C4", "#38BDF8", "#FFFFFF")
        }
        actionCard.addView(btnSync)

        val pendingChangesCount = CalendarChangeTracker.getLastChanges(context).size
        val btnChanges = Button(context).apply {
            val baseLabel = if (en) "Manage calendar changes" else "Hallitse kalenterimuutoksia"
            text = if (pendingChangesCount > 0) "$baseLabel ($pendingChangesCount)" else baseLabel
            styleButton(this, "#233040", "#37475A", "#F1F5F9")
        }
        actionCard.addView(btnChanges)

        val btnTestNotif = Button(context).apply {
            text = if (en) "Send test notification" else "Lähetä testi-ilmoitus"
            styleButton(this, "#233040", "#37475A", "#F1F5F9")
        }
        actionCard.addView(btnTestNotif)

        // === KORTTI 5: VAPAAEHTOINEN TUKI (GOOGLE PLAY BILLING) ===
        val supportCard = createSectionCard(if (en) "Support app development" else "Tue sovelluksen kehitystä")

        supportCard.addView(TextView(context).apply {
            text = if (en) {
                "Vuorovahti is a free, independent hobby project. All features are always available to everyone. If you wish, you can support development with a voluntary one-time tip:"
            } else {
                "Vuorovahti on maksuton ja itsenäinen harrastusprojekti. Kaikki ominaisuudet ovat aina kaikkien käytössä. Halutessasi voit tukea kehitystä vapaaehtoisella kertamaksulla:"
            }
            textSize = 12.5f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, 0, 0, dp(8))
        })

        val tvSupportStatus = TextView(context).apply {
            text = if (en) "Fetching support options from Google Play..." else "Haetaan tukivaihtoehtoja Google Playsta..."
            textSize = 12f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, dp(2), 0, dp(4))
        }
        supportCard.addView(tvSupportStatus)

        val tipButtonsContainer = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
        }
        supportCard.addView(tipButtonsContainer)

        lateinit var billingHelper: SupportBillingHelper

        val btnFallbackSupport = Button(context).apply {
            text = if (en) "☕ Buy the developer a coffee" else "☕ Tarjoa kehittäjälle kahvit"
            styleButton(this, "#1E3A5F", "#0284C7", "#E0F2FE")
            setOnClickListener {
                tvSupportStatus.setTextColor(Color.parseColor("#38BDF8"))
                tvSupportStatus.text = if (en) "Connecting to Google Play..." else "Yhdistetään Google Playhin..."
                billingHelper.startConnection()
            }
        }
        tipButtonsContainer.addView(btnFallbackSupport)

        billingHelper = SupportBillingHelper(
            context = context,
            onProductsLoaded = { products ->
                tvSupportStatus.setTextColor(Color.parseColor("#94A3B8"))
                tvSupportStatus.text = if (en) "Choose a one-time tip (Google Play):" else "Valitse sopiva kertatuki (Google Play):"
                tipButtonsContainer.removeAllViews()

                val icons = listOf("☕", "🥐", "🍲")
                products.forEachIndexed { index, product ->
                    val price = product.oneTimePurchaseOfferDetails?.formattedPrice ?: ""
                    val title = product.name.ifBlank { if (en) "Support development" else "Tue kehitystä" }
                    val icon = icons.getOrElse(index) { "☕" }
                    val btnTier = Button(context).apply {
                        text = if (price.isNotEmpty()) "$icon $title — $price" else "$icon $title"
                        styleButton(this, "#1E3A5F", "#0284C7", "#E0F2FE")
                        setOnClickListener {
                            billingHelper.launchPurchase(product)
                        }
                    }
                    tipButtonsContainer.addView(btnTier)
                }
            },
            onStatusMessage = { msg, isSuccess ->
                tvSupportStatus.setTextColor(
                    Color.parseColor(if (isSuccess) "#10B981" else "#94A3B8")
                )
                tvSupportStatus.text = msg
            }
        )
        billingHelper.startConnection()

        // === KORTTI 6: TIETOJA JA TIETOTURVA ===
        val aboutCard = createSectionCard(if (en) "About and privacy" else "Tietoja ja tietoturva")

        val (installedVersionName, installedVersionCode) = try {
            val pInfo = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
                context.packageManager.getPackageInfo(
                    context.packageName,
                    PackageManager.PackageInfoFlags.of(0)
                )
            } else {
                @Suppress("DEPRECATION")
                context.packageManager.getPackageInfo(context.packageName, 0)
            }
            val vCode = androidx.core.content.pm.PackageInfoCompat.getLongVersionCode(pInfo)
            (pInfo.versionName ?: "?") to vCode
        } catch (_: Exception) {
            "?" to 0L
        }

        val (_, versionSubTv) = addStatusRow(
            aboutCard,
            if (en) "App version" else "Sovelluksen versio",
            "v$installedVersionName ($installedVersionCode)",
            if (en) "Checking for updates..." else "Tarkistetaan päivityksiä..."
        )
        aboutCard.getChildAt(aboutCard.childCount - 1).setOnClickListener {
            openPlayStorePage()
        }

        val btnUpdateApp = Button(context).apply {
            text = if (en) "Update to latest version (Google Play)" else "Päivitä uusimpaan versioon (Google Play)"
            styleButton(this, "#D97706", "#FBBF24", "#FFFFFF")
            visibility = View.GONE
            setOnClickListener { openPlayStorePage() }
        }
        aboutCard.addView(btnUpdateApp)

        val btnPrivacyPolicy = Button(context).apply {
            text = if (en) "Privacy policy" else "Tietoturvaseloste"
            styleButton(this, "#233040", "#37475A", "#38BDF8")
            setOnClickListener { openPrivacyPolicy() }
        }
        aboutCard.addView(btnPrivacyPolicy)

        var isDialogDismissed = false

        fun checkForAppUpdate() {
            try {
                val appUpdateManager = com.google.android.play.core.appupdate.AppUpdateManagerFactory.create(
                    context.applicationContext
                )
                appUpdateManager.appUpdateInfo
                    .addOnSuccessListener { info ->
                        val act = context as? android.app.Activity
                        if (isDialogDismissed || (act != null && (act.isFinishing || act.isDestroyed))) {
                            return@addOnSuccessListener
                        }
                        val availability = info.updateAvailability()
                        val updateAvailable =
                            availability == com.google.android.play.core.install.model.UpdateAvailability.UPDATE_AVAILABLE ||
                            availability == com.google.android.play.core.install.model.UpdateAvailability.DEVELOPER_TRIGGERED_UPDATE_IN_PROGRESS

                        if (updateAvailable) {
                            val availCode = info.availableVersionCode()
                            updateBanner.visibility = View.VISIBLE
                            updateBannerSubTv.text = if (en) {
                                "A newer version (build $availCode) is available on Google Play. Please update for the latest fixes."
                            } else {
                                "Uudempi versio (koontiversio $availCode) on saatavilla Google Playssa. Päivitä sovellus saadaksesi uusimmat korjaukset."
                            }
                            versionSubTv.text = if (en) {
                                "Outdated – update available (build $availCode)"
                            } else {
                                "Vanhentunut – uusi versio saatavilla (koontiversio $availCode)"
                            }
                            versionSubTv.setTextColor(Color.parseColor("#FBBF24"))
                            versionSubTv.visibility = View.VISIBLE
                            btnUpdateApp.visibility = View.VISIBLE
                        } else {
                            versionSubTv.text = if (en) "Up to date" else "Sovellus on ajan tasalla"
                            versionSubTv.setTextColor(Color.parseColor("#34D399"))
                            versionSubTv.visibility = View.VISIBLE
                        }
                    }
                    .addOnFailureListener {
                        val act = context as? android.app.Activity
                        if (isDialogDismissed || (act != null && (act.isFinishing || act.isDestroyed))) {
                            return@addOnFailureListener
                        }
                        versionSubTv.text = if (en) {
                            "Tap to check Google Play for updates"
                        } else {
                            "Napauta tarkistaaksesi päivitykset Google Playsta"
                        }
                        versionSubTv.setTextColor(Color.parseColor("#94A3B8"))
                        versionSubTv.visibility = View.VISIBLE
                    }
            } catch (_: Exception) {
                versionSubTv.text = if (en) {
                    "Tap to check Google Play for updates"
                } else {
                    "Napauta tarkistaaksesi päivitykset Google Playsta"
                }
                versionSubTv.setTextColor(Color.parseColor("#94A3B8"))
                versionSubTv.visibility = View.VISIBLE
            }
        }

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
            text = if (en) "Cancel" else "Peruuta"
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
            text = if (en) "Save" else "Tallenna"
            background = makeCardBg("#1982C4", "#38BDF8", 8)
            setTextColor(Color.parseColor("#FFFFFF"))
            isAllCaps = false
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            setPadding(dp(22), dp(10), dp(22), dp(10))
        }

        footerBar.addView(btnCancel)
        footerBar.addView(btnSave)

        // Vastuuvapauslauseke (epävirallinen sovellus)
        val tvDisclaimer = TextView(context).apply {
            text = if (en) {
                "This is an independent, unofficial third-party client application. Numeron vuorovahti is not affiliated with Visma, Numeron, or any other entity."
            } else {
                "Tämä on itsenäinen, epävirallinen kolmannen osapuolen asiakassovellus. Numeron vuorovahti ei ole millään tavalla sidoksissa Vismaan, Numeroniin tai muihin mahdollisiin tahoihin."
            }
            textSize = 11f
            setTextColor(Color.parseColor("#64748B"))
            gravity = Gravity.CENTER
            setPadding(dp(16), dp(12), dp(16), dp(12))
        }
        rootContainer.addView(tvDisclaimer)

        rootContainer.addView(footerBar)

        val dialog = AlertDialog.Builder(context)
            .setView(rootContainer)
            .create()
        dialogRef = dialog

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
            val reminderMins = (editReminder.text.toString().toIntOrNull() ?: 30).coerceIn(1, 240)

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
                UrlNormalizer.isDemoInput(rawOrg) ||
                DemoModeHelper.isDemoCredentials(rawOrg, savedUser, savedPass)

            SecureCredentialManager.saveCredentials(context, savedUser, savedPass)
            BackgroundAuthHelper.clearSessionCache(context)

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
                .also { if (selectedCal != null) it.putLong("calendar_id", selectedCal.id) }
                .apply()

            val turnedOnSync = !initialSyncCalendar && newSyncCalendar
            val missingCacheForReminders = newShiftReminders && !CalendarSyncHelper.hasCachedShifts(context)
            val shouldTriggerSync = turnedOnSync || (!initialShiftReminders && missingCacheForReminders)

            fun finishSave(forceSync: Boolean = false) {
                dialog.dismiss()
                onSaved()
                if ((shouldTriggerSync || forceSync) && !isDemo && savedUser.isNotEmpty() && savedPass.isNotEmpty() && normalizedUrl.isNotEmpty()) {
                    ShiftReminderReceiver.triggerImmediateSync(context)
                }
            }

            if (initialSyncCalendar && !newSyncCalendar) {
                btnSave.isEnabled = false
                val appCtx = context.applicationContext
                CoroutineScope(Dispatchers.IO).launch {
                    val targetCalId = selectedCal?.id ?: CalendarSyncHelper.getTargetCalendarId(appCtx)
                    val futureCount = if (targetCalId != null) {
                        CalendarSyncHelper.countFutureSyncedEvents(appCtx, targetCalId)
                    } else {
                        0
                    }
                    withContext(Dispatchers.Main) {
                        val act = context as? android.app.Activity
                        if (act != null && (act.isFinishing || act.isDestroyed)) return@withContext
                        if (targetCalId != null && futureCount > 0) {
                            AlertDialog.Builder(context)
                                .setTitle(if (en) "Delete calendar events?" else "Poistetaanko kalenterimerkinnät?")
                                .setMessage(
                                    if (en) {
                                        "Calendar sync was disabled. Do you want to delete the upcoming events added by this app to Google Calendar ($futureCount events)?"
                                    } else {
                                        "Kalenterisynkronointi otettiin pois käytöstä. Haluatko poistaa sovelluksen Google-kalenteriin lisäämät tulevat merkinnät ($futureCount kpl)?"
                                    }
                                )
                                .setPositiveButton(if (en) "Delete events" else "Poista merkinnät") { _, _ ->
                                    CoroutineScope(Dispatchers.IO).launch {
                                        CalendarSyncHelper.deleteFutureSyncedEvents(appCtx, targetCalId)
                                        withContext(Dispatchers.Main) {
                                            val curAct = context as? android.app.Activity
                                            if (curAct == null || (!curAct.isFinishing && !curAct.isDestroyed)) {
                                                finishSave(forceSync = missingCacheForReminders)
                                            }
                                        }
                                    }
                                }
                                .setNegativeButton(if (en) "Keep in calendar" else "Jätä kalenteriin") { _, _ ->
                                    finishSave()
                                }
                                .setCancelable(false)
                                .show()
                        } else {
                            finishSave()
                        }
                    }
                }
            } else {
                finishSave()
            }
        }


        fun refreshSystemPermissionStates() {
            

            val nowIgnoringBattery = powerManager.isIgnoringBatteryOptimizations(context.packageName)
            if (nowIgnoringBattery) {
                batteryOptValueTv.text = if (en) "Unrestricted (background sync active)" else "Ei rajoitettu (taustasynkronointi aktiivinen)"
                batteryOptValueTv.setTextColor(Color.parseColor("#34D399"))
                batteryOptSubTv.text = if (en) "Tap to open battery settings" else "Napauta avataksesi virransäästöasetukset"
                batteryOptSubTv.visibility = View.VISIBLE
            } else {
                batteryOptValueTv.text = if (en) "Optimized – tap to remove restriction" else "Optimoitu – napauta poistaaksesi rajoitus"
                batteryOptValueTv.setTextColor(Color.parseColor("#F1F5F9"))
                batteryOptSubTv.text = if (en) "Ensures background sync works in sleep mode" else "Varmistaa tausta-ajojen toiminnan lepotilassa"
                batteryOptSubTv.visibility = View.VISIBLE
            }

            val notifsAllowed = areAppNotificationsAllowed()
            if (notifsAllowed) {
                notifPermValueTv.text = if (en) "Enabled" else "Käytössä"
                notifPermValueTv.setTextColor(Color.parseColor("#34D399"))
                notifPermSubTv.text = if (en) "Tap to open notification settings" else "Napauta avataksesi ilmoitusasetukset"
                notifPermSubTv.visibility = View.VISIBLE
            } else {
                notifPermValueTv.text = if (en) "Blocked – tap to enable" else "Estetty – napauta ottaaksesi käyttöön"
                notifPermValueTv.setTextColor(Color.parseColor("#F87171"))
                notifPermSubTv.text = if (en) "Required for shift and calendar alerts" else "Vaaditaan leimaus- ja kalenteri-ilmoituksiin"
                notifPermSubTv.visibility = View.VISIBLE
            }

        }

        refreshSystemPermissionStates()

        val focusListener = android.view.ViewTreeObserver.OnWindowFocusChangeListener { hasFocus ->
            if (hasFocus) {
                refreshSystemPermissionStates()
            }
        }
        rootContainer.viewTreeObserver.addOnWindowFocusChangeListener(focusListener)

        dialog.setOnDismissListener {
            isDialogDismissed = true
            testCredentialsJob?.cancel()
            rootContainer.viewTreeObserver.removeOnWindowFocusChangeListener(focusListener)
            billingHelper.destroy()
        }
        dialog.show()
        checkForAppUpdate()
    }

    private fun testLoginWithHiddenWebView(
        @Suppress("UNUSED_PARAMETER") context: Context,
        baseUrl: String,
        username: String,
        password: String,
        callback: (Boolean, String) -> Unit
    ): kotlinx.coroutines.Job {
        return CoroutineScope(Dispatchers.IO).launch {
            val (success, msg) = BackgroundAuthHelper.testCredentials(baseUrl, username, password)
            withContext(Dispatchers.Main) {
                callback(success, msg)
            }
        }
    }
}
