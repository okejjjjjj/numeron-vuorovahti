package fi.oma.numeron

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.CalendarContract
import android.text.InputType
import android.text.method.HideReturnsTransformationMethod
import android.text.method.PasswordTransformationMethod
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class SettingsActivity : AppCompatActivity() {

    private data class CalendarItem(val id: Long, val title: String)
    private val calendarList = mutableListOf<CalendarItem>()
    private lateinit var calendarSpinner: Spinner
    private lateinit var nextReminderStatusText: TextView
    private lateinit var lastReminderStatusText: TextView
    private lateinit var syncStatusText: TextView
    private var testWebView: WebView? = null
    private val mainHandler = Handler(Looper.getMainLooper())

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val rootScroll = ScrollView(this).apply {
            layoutParams = ViewGroup.LayoutParams(-1, -1)
            setBackgroundColor(Color.parseColor("#0B1120"))
            isFillViewport = true
            fitsSystemWindows = true
        }


        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(24), dp(20), dp(36))
        }

        val titleView = TextView(this).apply {
            text = "Asetukset"
            textSize = 24f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#F8FAFC"))
            setPadding(dp(4), 0, dp(4), dp(4))
        }
        val subHeaderView = TextView(this).apply {
            text = "Numeron Vuorovahti – automaation ja kalenterin hallinta"
            textSize = 13f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(dp(4), 0, dp(4), dp(20))
        }
        container.addView(titleView)
        container.addView(subHeaderView)

        fun createCard(sectionTitle: String, subtitle: String): LinearLayout {
            val card = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(20), dp(18), dp(20), dp(18))
                layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(14) }
                background = GradientDrawable().apply {
                    shape = GradientDrawable.RECTANGLE
                    cornerRadius = dp(18).toFloat()
                    setColor(Color.parseColor("#1E293B"))
                    setStroke(dp(1), Color.parseColor("#334155"))
                }
            }
            card.addView(TextView(this).apply {
                text = sectionTitle
                textSize = 15.5f
                setTypeface(null, Typeface.BOLD)
                setTextColor(Color.parseColor("#38BDF8"))
            })
            if (subtitle.isNotEmpty()) {
                card.addView(TextView(this).apply {
                    text = subtitle
                    textSize = 12.5f
                    setTextColor(Color.parseColor("#94A3B8"))
                    setPadding(0, dp(4), 0, dp(12))
                })
            }
            container.addView(card)
            return card
        }

        fun styleEdit(edit: EditText) {
            edit.setTextColor(Color.parseColor("#F8FAFC"))
            edit.setHintTextColor(Color.parseColor("#64748B"))
            edit.textSize = 14.5f
            edit.setPadding(dp(16), dp(13), dp(16), dp(13))
            edit.background = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = dp(12).toFloat()
                setColor(Color.parseColor("#0F172A"))
                setStroke(dp(1), Color.parseColor("#334155"))
            }
            edit.layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) }
        }

        fun createStyledSwitch(label: String, checked: Boolean): Switch {
            return Switch(this).apply {
                text = label
                textSize = 14.5f
                setTextColor(Color.parseColor("#F1F5F9"))
                isChecked = checked
                setPadding(0, dp(4), 0, dp(4))
                val states = arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf(-android.R.attr.state_checked))
                thumbTintList = ColorStateList(states, intArrayOf(Color.parseColor("#10B981"), Color.parseColor("#94A3B8")))
                trackTintList = ColorStateList(states, intArrayOf(Color.parseColor("#065F46"), Color.parseColor("#334155")))
            }
        }

        // 1. Organisaatio & Tunnukset
        val cardOrg = createCard(
            "1. Organisaatio ja kirjautuminen",
            "Syötä organisaation tunnus (esim. omaorganisaatio) tai palvelimen osoite, sekä kirjautumistiedot. (Esittelytila: syötä tunnukseksi ja salasanaksi 'demo')."
        )
        val orgEdit = EditText(this).apply {
            hint = "Organisaatio tai osoite (esim. omaorganisaatio.numeronwfm.com)"
            setText(SettingsManager.getOrganizationRaw(this@SettingsActivity))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            styleEdit(this)
        }
        val userEdit = EditText(this).apply {
            hint = "Käyttäjätunnus"
            setText(SettingsManager.getUsername(this@SettingsActivity))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
            styleEdit(this)
        }

        val passRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) }
            background = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = dp(12).toFloat()
                setColor(Color.parseColor("#0F172A"))
                setStroke(dp(1), Color.parseColor("#334155"))
            }
        }

        val passEdit = EditText(this).apply {
            hint = "Salasana"
            setText(SettingsManager.getPassword(this@SettingsActivity))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            transformationMethod = PasswordTransformationMethod.getInstance()
            setTextColor(Color.parseColor("#F8FAFC"))
            setHintTextColor(Color.parseColor("#64748B"))
            textSize = 14.5f
            setPadding(dp(16), dp(13), dp(8), dp(13))
            background = null
            layoutParams = LinearLayout.LayoutParams(0, -2, 1f)
        }

        var isPasswordVisible = false
        val btnTogglePass = Button(this).apply {
            text = "Näytä"
            isAllCaps = false
            textSize = 12f
            setTextColor(Color.parseColor("#38BDF8"))
            background = null
            minHeight = 0
            minimumHeight = 0
            minWidth = 0
            minimumWidth = 0
            setPadding(dp(12), dp(8), dp(14), dp(8))
            setOnClickListener {
                isPasswordVisible = !isPasswordVisible
                val sel = passEdit.selectionEnd
                if (isPasswordVisible) {
                    passEdit.transformationMethod = HideReturnsTransformationMethod.getInstance()
                    text = "Piilota"
                } else {
                    passEdit.transformationMethod = PasswordTransformationMethod.getInstance()
                    text = "Näytä"
                }
                if (sel >= 0) passEdit.setSelection(sel)
            }
        }
        passRow.addView(passEdit)
        passRow.addView(btnTogglePass)

        val authStatusText = TextView(this).apply {
            text = ""
            textSize = 12.5f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(dp(4), dp(6), dp(4), dp(2))
            visibility = View.GONE
        }

        val btnTestCreds = Button(this).apply {
            text = "Testaa yhteys ja tunnukset"
            isAllCaps = false
            textSize = 13f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#E2E8F0"))
            background = GradientDrawable().apply {
                cornerRadius = dp(10).toFloat()
                setColor(Color.parseColor("#334155"))
                setStroke(dp(1), Color.parseColor("#475569"))
            }
            layoutParams = LinearLayout.LayoutParams(-1, dp(42)).apply { topMargin = dp(2) }
            setOnClickListener {
                verifyCredentialsLive(
                    orgEdit.text.toString().trim(),
                    userEdit.text.toString().trim(),
                    passEdit.text.toString(),
                    this,
                    authStatusText
                )
            }
        }

        cardOrg.addView(orgEdit)
        cardOrg.addView(userEdit)
        cardOrg.addView(passRow)
        cardOrg.addView(btnTestCreds)
        cardOrg.addView(authStatusText)

        // 2. Biometrinen tunnistus
        val cardBio = createCard(
            "2. Sormenjälkitunnistus",
            "Vahvista työvuorotoiveiden tallennus ja poisto sormenjäljellä tai lukituskoodilla."
        )
        val bioSwitch = createStyledSwitch(
            "Käytä biometristä tunnistusta",
            SettingsManager.isBiometricEnabled(this)
        )
        cardBio.addView(bioSwitch)

        // 3. Automaattinen vuorojen synkronointi
        val cardSync = createCard(
            "3. Työvuorojen automaattinen haku",
            "Tarkistaa uudet 3 viikon listat julkaisuperjantaisin klo 11 jälkeen ja vie ne kalenteriin."
        )
        val syncSwitch = createStyledSwitch(
            "Synkronoi työvuorot automaattisesti",
            SettingsManager.isAutoSyncEnabled(this)
        )
        syncStatusText = TextView(this).apply {
            text = VuorovahtiHelper.getLastSyncStatus(this@SettingsActivity)
            textSize = 12f
            setTextColor(Color.parseColor("#10B981"))
            setPadding(0, dp(8), 0, 0)
        }
        cardSync.addView(syncSwitch)
        cardSync.addView(syncStatusText)

        // 4. Kohdekalenteri
        val cardCal = createCard(
            "4. Kohdekalenteri",
            "Valitse mihin puhelimen kalenteriin työvuorot ja vuosilomat tallennetaan."
        )
        calendarSpinner = Spinner(this).apply {
            setPadding(dp(12), dp(10), dp(12), dp(10))
            background = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = dp(12).toFloat()
                setColor(Color.parseColor("#0F172A"))
                setStroke(dp(1), Color.parseColor("#334155"))
            }
        }
        cardCal.addView(calendarSpinner)

        // 5. Leimausnotifikaatiot
        val cardNotif = createCard(
            "5. Leimausmuistutukset",
            "Näytä hiljainen ilmoitus ja pikaleimausnappi 30 min ennen vuoron alkua ja loppua."
        )
        val notifSwitch = createStyledSwitch(
            "Käytä leimausnotifikaatioita",
            SettingsManager.isStampNotificationEnabled(this)
        )

        val reminderInfoBox = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(12), dp(10), dp(12), dp(10))
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(10) }
            background = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = dp(10).toFloat()
                setColor(Color.parseColor("#0F172A"))
                setStroke(dp(1), Color.parseColor("#1E293B"))
            }
        }

        lastReminderStatusText = TextView(this).apply {
            text = "Edellinen muistutus: ${VuorovahtiHelper.getLastTriggeredReminder(this@SettingsActivity)}"
            textSize = 12f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, 0, 0, dp(6))
        }

        nextReminderStatusText = TextView(this).apply {
            text = "Seuraava muistutus: ${VuorovahtiHelper.getNextScheduledReminderText(this@SettingsActivity)}"
            textSize = 12f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#38BDF8"))
        }

        notifSwitch.setOnCheckedChangeListener { _, isChecked ->
            if (!isChecked) {
                nextReminderStatusText.text = "Seuraava muistutus: Ei käytössä (kytketty pois)"
                nextReminderStatusText.setTextColor(Color.parseColor("#64748B"))
            } else {
                VuorovahtiHelper.ensureRemindersFromCalendar(this@SettingsActivity)
                nextReminderStatusText.text = "Seuraava muistutus: ${VuorovahtiHelper.getNextScheduledReminderText(this@SettingsActivity)}"
                nextReminderStatusText.setTextColor(Color.parseColor("#38BDF8"))
            }
        }

        reminderInfoBox.addView(lastReminderStatusText)
        reminderInfoBox.addView(nextReminderStatusText)

        cardNotif.addView(notifSwitch)
        cardNotif.addView(reminderInfoBox)

        // Painikkeet
        val btnRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(10) }
        }

        val btnCancel = Button(this).apply {
            text = "Peruuta"
            isAllCaps = false
            textSize = 14f
            setTextColor(Color.parseColor("#CBD5E1"))
            background = GradientDrawable().apply {
                cornerRadius = dp(14).toFloat()
                setColor(Color.parseColor("#334155"))
            }
            layoutParams = LinearLayout.LayoutParams(0, dp(48), 1f).apply { marginEnd = dp(8) }
            setOnClickListener { finish() }
        }

        val btnSave = Button(this).apply {
            text = "Tallenna asetukset"
            isAllCaps = false
            textSize = 14.5f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.WHITE)
            background = GradientDrawable().apply {
                cornerRadius = dp(14).toFloat()
                colors = intArrayOf(Color.parseColor("#0284C7"), Color.parseColor("#0369A1"))
                orientation = GradientDrawable.Orientation.LEFT_RIGHT
            }
            layoutParams = LinearLayout.LayoutParams(0, dp(48), 1.5f).apply { marginStart = dp(8) }
            setOnClickListener {
                val orgText = orgEdit.text.toString().trim()
                val userText = userEdit.text.toString().trim()
                val passText = passEdit.text.toString()
                val isDemoUser = userText.equals("demo", ignoreCase = true)

                if (orgText.isEmpty() && !isDemoUser) {
                    Toast.makeText(this@SettingsActivity, "Syötä ensin organisaation tunnus tai osoite.", Toast.LENGTH_LONG).show()
                    return@setOnClickListener
                }

                val selectedIdx = calendarSpinner.selectedItemPosition
                val calId = if (selectedIdx in calendarList.indices) calendarList[selectedIdx].id else -1L
                SettingsManager.saveAll(
                    this@SettingsActivity,
                    if (isDemoUser && orgText.isEmpty()) "demo" else orgText,
                    userText,
                    passText,
                    bioSwitch.isChecked,
                    syncSwitch.isChecked,
                    notifSwitch.isChecked,
                    calId
                )
                VuorovahtiHelper.ensureRemindersFromCalendar(this@SettingsActivity)
                VuorovahtiHelper.triggerConfirmHaptics(window.decorView)
                Toast.makeText(this@SettingsActivity, "Asetukset tallennettu!", Toast.LENGTH_SHORT).show()
                setResult(RESULT_OK)
                finish()
            }
        }

        btnRow.addView(btnCancel)
        btnRow.addView(btnSave)
        container.addView(btnRow)

        val disclaimerView = TextView(this).apply {
            text = "Numeron Vuorovahti on itsenäinen ja epävirallinen aputyökalu. Kehittäjä ei vastaa mahdollisista virheistä työvuorojen synkronoinnissa tai leimauksissa. Tarkista viralliset työaikatiedot aina suoraan työnantajan järjestelmästä."
            textSize = 11.5f
            setTextColor(Color.parseColor("#64748B"))
            gravity = Gravity.CENTER
            setPadding(dp(12), dp(24), dp(12), dp(8))
        }
        container.addView(disclaimerView)

        rootScroll.addView(container)
        setContentView(rootScroll)

        VuorovahtiHelper.ensureRemindersFromCalendar(this)
        refreshReminderTexts()
        loadAvailableCalendars()
    }

    private fun refreshReminderTexts() {
        lastReminderStatusText.text = "Edellinen muistutus: ${VuorovahtiHelper.getLastTriggeredReminder(this)}"
        nextReminderStatusText.text = "Seuraava muistutus: ${VuorovahtiHelper.getNextScheduledReminderText(this)}"
    }


    @SuppressLint("SetJavaScriptEnabled")
    private fun verifyCredentialsLive(
        orgRaw: String,
        user: String,
        pass: String,
        btn: Button,
        statusView: TextView
    ) {
        statusView.visibility = View.VISIBLE

        if (VuorovahtiHelper.isDemoMode(user, pass)) {
            statusView.setTextColor(Color.parseColor("#10B981"))
            statusView.text = "✓ Demo-tila tunnistettu! Voit tallentaa asetukset."
            VuorovahtiHelper.triggerConfirmHaptics(window.decorView)
            return
        }

        if (orgRaw.isEmpty() || user.isEmpty() || pass.isEmpty()) {
            statusView.setTextColor(Color.parseColor("#F87171"))
            statusView.text = "✗ Täytä organisaatio, käyttäjätunnus ja salasana ennen testiä."
            return
        }

        val cleanOrg = orgRaw.lowercase()
            .removePrefix("https://")
            .removePrefix("http://")
            .substringBefore("/")
            .substringBefore("?")
            .trim()
        val baseUrl = if (cleanOrg.contains(".")) "https://$cleanOrg" else "https://$cleanOrg.numeronwfm.com"
        val testUrl = "$baseUrl/WorktimeStamping"

        btn.isEnabled = false
        btn.text = "Testataan yhteyttä..."
        statusView.setTextColor(Color.parseColor("#38BDF8"))
        statusView.text = "Yhdistetään osoitteeseen $baseUrl..."

        mainHandler.removeCallbacksAndMessages(null)
        (testWebView?.parent as? ViewGroup)?.removeView(testWebView)
        testWebView?.destroy()

        val safeU = user.replace("\\", "\\\\").replace("'", "\\'")
        val safeP = pass.replace("\\", "\\\\").replace("'", "\\'")

        var loginSubmitted = false
        var testFinished = false
        var pollCount = 0
        var postSubmitPolls = 0

        fun finishTest(success: Boolean, message: String) {
            if (testFinished) return
            testFinished = true
            mainHandler.removeCallbacksAndMessages(null)
            btn.isEnabled = true
            btn.text = "Testaa yhteys ja tunnukset"
            statusView.setTextColor(Color.parseColor(if (success) "#10B981" else "#F87171"))
            statusView.text = message
            if (success) VuorovahtiHelper.triggerConfirmHaptics(window.decorView)
            (testWebView?.parent as? ViewGroup)?.removeView(testWebView)
            testWebView?.destroy()
            testWebView = null
        }

        val webView = WebView(this).apply {
            layoutParams = ViewGroup.LayoutParams(1, 1)
            alpha = 0.01f
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.databaseEnabled = true
        }

        val cookieManager = CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, true)
        }

        addContentView(webView, ViewGroup.LayoutParams(1, 1))
        testWebView = webView

        fun pollLoginState() {
            if (testFinished || testWebView == null) return
            pollCount++
            if (loginSubmitted) postSubmitPolls++

            if (pollCount > 28) {
                finishTest(false, "✗ Aikakatkaisu: Palvelin ei vastannut tai kirjautuminen jäi odottamaan vahvistusta.")
                return
            }

            val submittedFlag = if (loginSubmitted) "true" else "false"
            val js = """
                (function() {
                    var bodyTxt = (document.body ? document.body.innerText : "").toLowerCase();
                    var href = (window.location.href || "").toLowerCase();
                    var passInputs = document.querySelectorAll('input[type="password"]');
                    var passEl = null;
                    for (var p = 0; p < passInputs.length; p++) {
                        if (!passInputs[p].disabled) { passEl = passInputs[p]; break; }
                    }

                    // 1. Onnistunut sisäänkirjautuminen: ei salasanakenttää ja ollaan Numeronin sisäsivulla
                    if (!passEl && href.indexOf('login') === -1 && href.indexOf('auth') === -1 &&
                        (href.indexOf('worktimestamping') !== -1 || bodyTxt.indexOf('leimaa') !== -1 ||
                         bodyTxt.indexOf('työaika') !== -1 || bodyTxt.indexOf('kalenteri') !== -1 ||
                         bodyTxt.indexOf('uloskirjaus') !== -1 || bodyTxt.indexOf('kirjaudu ulos') !== -1 ||
                         bodyTxt.indexOf('työvuoro') !== -1)) {
                        return "LOGGED_IN_SUCCESS";
                    }

                    // 2. Selkeä virheilmoitus kirjautumisyrityksen jälkeen
                    if ($submittedFlag && (bodyTxt.indexOf('virheellinen') !== -1 || bodyTxt.indexOf('epäonnistui') !== -1 ||
                        bodyTxt.indexOf('invalid') !== -1 || bodyTxt.indexOf('väärä salasana') !== -1 ||
                        bodyTxt.indexOf('väärä käyttäjätunnus') !== -1 || bodyTxt.indexOf('tarkista käyttäjätunnus') !== -1 ||
                        bodyTxt.indexOf('incorrect') !== -1 || bodyTxt.indexOf('login failed') !== -1)) {
                        return "LOGIN_FAILED_ERROR";
                    }

                    function setNativeValue(el, val) {
                        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        if (setter) setter.call(el, val);
                        else el.value = val;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }

                    var userInputs = document.querySelectorAll('input[type="email"], input[name*="user" i], input[name*="login" i], input[id*="user" i], input[name*="fmt" i], input[type="text"]');
                    var userEl = null;
                    for (var u = 0; u < userInputs.length; u++) {
                        if (!userInputs[u].readOnly && !userInputs[u].disabled) { userEl = userInputs[u]; break; }
                    }

                    if (!passEl && userEl && !window._userStepDone) {
                        window._userStepDone = true;
                        setNativeValue(userEl, '$safeU');
                        var nextBtn = document.querySelector('input[type="submit"], button[type="submit"], button[id*="next" i], input[id*="next" i]');
                        if (nextBtn) { nextBtn.click(); return "STEP_USER_SUBMITTED"; }
                    }

                    if (passEl && !window._passStepDone) {
                        window._passStepDone = true;
                        if (userEl) setNativeValue(userEl, '$safeU');
                        setNativeValue(passEl, '$safeP');
                        var submitBtn = document.querySelector('input[type="submit"], button[type="submit"], button[id*="login" i], button[name*="login" i], input[id*="SignIn" i]');
                        if (submitBtn) { submitBtn.click(); return "SUBMITTED_NOW"; }
                        if (passEl.form) { passEl.form.submit(); return "SUBMITTED_NOW"; }
                    }

                    if ($submittedFlag && passEl) {
                        return "STILL_ON_LOGIN";
                    }

                    return "WAITING";
                })();
            """.trimIndent()

            webView.evaluateJavascript(js) { res ->
                if (testFinished) return@evaluateJavascript
                val r = res ?: ""
                when {
                    r.contains("LOGGED_IN_SUCCESS") -> {
                        finishTest(true, "✓ Kirjautuminen onnistui! Tunnukset ja yhteys toimivat.")
                    }
                    r.contains("LOGIN_FAILED_ERROR") -> {
                        finishTest(false, "✗ Kirjautuminen epäonnistui: Tarkista käyttäjätunnus ja salasana.")
                    }
                    r.contains("SUBMITTED_NOW") -> {
                        loginSubmitted = true
                        postSubmitPolls = 0
                        statusView.text = "Tarkistetaan käyttäjätunnusta ja salasanaa..."
                        mainHandler.postDelayed({ pollLoginState() }, 2200L)
                    }
                    r.contains("STILL_ON_LOGIN") && postSubmitPolls >= 5 -> {
                        finishTest(false, "✗ Kirjautuminen ei mennyt läpi. Tarkista käyttäjätunnus ja salasana.")
                    }
                    else -> {
                        mainHandler.postDelayed({ pollLoginState() }, 1000L)
                    }
                }
            }
        }

        webView.webViewClient = object : WebViewClient() {
            override fun onReceivedError(
                view: WebView?,
                request: android.webkit.WebResourceRequest?,
                error: android.webkit.WebResourceError?
            ) {
                val code = error?.errorCode ?: 0
                // Ohitetaan uudelleenohjauksista johtuvat keskeytykset, reagoidaan vain oikeaan verkkovirheeseen
                val isFatalHostError = code == ERROR_HOST_LOOKUP || code == ERROR_CONNECT || code == ERROR_TIMEOUT
                if (request?.isForMainFrame == true && isFatalHostError) {
                    finishTest(false, "✗ Yhteysvirhe: Palvelinta ($baseUrl) ei löytynyt. Tarkista organisaation tunnus.")
                }
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                if (!testFinished) {
                    mainHandler.removeCallbacksAndMessages(null)
                    mainHandler.postDelayed({ pollLoginState() }, 700L)
                }
            }
        }

        // Tyhjennetään vanhat evästeet ja ladataan testisivu vasta kun tyhjennys on valmis
        cookieManager.removeAllCookies {
            cookieManager.flush()
            if (!testFinished) {
                webView.loadUrl(testUrl)
            }
        }
    }




    private fun loadAvailableCalendars() {
        calendarList.clear()
        calendarList.add(CalendarItem(-1L, "Oletuskalenteri (Automaattinen)"))

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.READ_CALENDAR, Manifest.permission.WRITE_CALENDAR), 201)
        } else {
            val proj = arrayOf(
                CalendarContract.Calendars._ID,
                CalendarContract.Calendars.CALENDAR_DISPLAY_NAME,
                CalendarContract.Calendars.ACCOUNT_NAME
            )
            val sel = "${CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL} >= ${CalendarContract.Calendars.CAL_ACCESS_CONTRIBUTOR}"
            try {
                contentResolver.query(CalendarContract.Calendars.CONTENT_URI, proj, sel, null, null)?.use { c ->
                    while (c.moveToNext()) {
                        val id = c.getLong(0)
                        val name = c.getString(1) ?: "Kalenteri"
                        val acc = c.getString(2) ?: ""
                        calendarList.add(CalendarItem(id, if (acc.isNotEmpty()) "$name ($acc)" else name))
                    }
                }
            } catch (_: Exception) {}
        }

        val adapter = object : ArrayAdapter<String>(
            this,
            android.R.layout.simple_spinner_item,
            calendarList.map { it.title }
        ) {
            override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
                return (super.getView(position, convertView, parent) as TextView).apply {
                    setTextColor(Color.parseColor("#F8FAFC"))
                    textSize = 14f
                }
            }
            override fun getDropDownView(position: Int, convertView: View?, parent: ViewGroup): View {
                return (super.getDropDownView(position, convertView, parent) as TextView).apply {
                    setTextColor(Color.parseColor("#F8FAFC"))
                    setBackgroundColor(Color.parseColor("#1E293B"))
                    setPadding(dp(16), dp(14), dp(16), dp(14))
                }
            }
        }
        calendarSpinner.adapter = adapter

        val savedId = SettingsManager.getTargetCalendarId(this)
        val idx = calendarList.indexOfFirst { it.id == savedId }
        if (idx >= 0) calendarSpinner.setSelection(idx)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 201) {
            loadAvailableCalendars()
            VuorovahtiHelper.ensureRemindersFromCalendar(this)
            refreshReminderTexts()
        }
    }

    override fun onDestroy() {
        mainHandler.removeCallbacksAndMessages(null)
        (testWebView?.parent as? ViewGroup)?.removeView(testWebView)
        testWebView?.destroy()
        testWebView = null
        super.onDestroy()
    }
}
