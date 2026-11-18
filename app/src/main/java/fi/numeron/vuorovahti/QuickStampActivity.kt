package fi.numeron.vuorovahti

import android.annotation.SuppressLint
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import org.json.JSONTokener
import java.io.ByteArrayInputStream
import java.time.LocalDate
import java.time.LocalTime
import java.time.format.DateTimeFormatter

class QuickStampActivity : AppCompatActivity() {

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private val mainHandler = Handler(Looper.getMainLooper())
    private var activeJob: Job? = null
    private var timeoutRunnable: Runnable? = null

    private lateinit var progressBar: ProgressBar
    private lateinit var statusBadge: TextView
    private lateinit var titleText: TextView
    private lateinit var statusText: TextView
    private lateinit var greetingText: TextView
    private var hiddenWebView: WebView? = null

    private var isCompleted = false
    private var sessionRetried = false

    override fun onCreate(savedInstanceState: Bundle?) {
        setTheme(R.style.Theme_Vuorovahti_Translucent)
        super.onCreate(savedInstanceState)

        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = Color.TRANSPARENT

        buildOverlayUi()
        processIntent(intent)
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (intent != null) {
            isCompleted = false
            sessionRetried = false
            activeJob?.cancel()
            cancelTimeout()
            destroyHiddenWebView()
            resetToLoadingUi()
            processIntent(intent)
        }
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun buildOverlayUi() {
        val root = FrameLayout(this).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            setBackgroundColor(Color.TRANSPARENT)
            setOnClickListener {
                finishCleanly()
            }
        }

        val cardBg = GradientDrawable().apply {
            setColor(Color.parseColor("#182332"))
            setStroke(dp(1), Color.parseColor("#2A394A"))
            cornerRadius = dp(18).toFloat()
        }

        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            background = cardBg
            elevation = dp(12).toFloat()
            setPadding(dp(26), dp(24), dp(26), dp(22))
            isClickable = true
            isFocusable = true
            layoutParams = FrameLayout.LayoutParams(
                dp(296),
                ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.CENTER
            )
        }

        val indicatorContainer = FrameLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(dp(48), dp(48)).apply {
                bottomMargin = dp(14)
            }
        }

        progressBar = ProgressBar(this).apply {
            isIndeterminate = true
            indeterminateTintList = ColorStateList.valueOf(Color.parseColor("#38BDF8"))
            layoutParams = FrameLayout.LayoutParams(dp(42), dp(42), Gravity.CENTER)
        }
        indicatorContainer.addView(progressBar)

        statusBadge = TextView(this).apply {
            textSize = 20f
            setTypeface(null, Typeface.BOLD)
            gravity = Gravity.CENTER
            visibility = View.GONE
            layoutParams = FrameLayout.LayoutParams(dp(44), dp(44), Gravity.CENTER)
        }
        indicatorContainer.addView(statusBadge)

        card.addView(indicatorContainer)

        titleText = TextView(this).apply {
            text = "Suoritetaan leimausta"
            textSize = 16f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#F1F5F9"))
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                bottomMargin = dp(6)
            }
        }
        card.addView(titleText)

        statusText = TextView(this).apply {
            text = "Valmistellaan yhteyttä…"
            textSize = 13.5f
            setTextColor(Color.parseColor("#94A3B8"))
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        }
        card.addView(statusText)

        val greetingBg = GradientDrawable().apply {
            setColor(Color.parseColor("#111923"))
            setStroke(dp(1), Color.parseColor("#2A394A"))
            cornerRadius = dp(10).toFloat()
        }

        greetingText = TextView(this).apply {
            text = buildGreeting(isEnding = false)
            textSize = 13f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#38BDF8"))
            background = greetingBg
            gravity = Gravity.CENTER
            setPadding(dp(12), dp(8), dp(12), dp(8))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                topMargin = dp(14)
            }
        }
        card.addView(greetingText)

        val webHolder = FrameLayout(this).apply {
            visibility = View.INVISIBLE
            alpha = 0f
            layoutParams = FrameLayout.LayoutParams(1, 1)
        }
        root.addView(webHolder)
        root.addView(card)

        setContentView(root)
    }

        private fun buildGreeting(isEnding: Boolean): String {
        val hour = LocalTime.now().hour
        val options = if (isEnding) {
            when (hour) {
                in 5..10 -> listOf(
                    "Hyvää huomenta, kiitos yövuorosta!",
                    "Aamu valkenee – hyvää lepoa vuoron päälle!",
                    "Kiitos yövuorosta, nyt ansaituille unille!",
                    "Hyvää huomenta ja rentouttavaa vapaata!"
                )
                in 11..16 -> listOf(
                    "Kiitos työvuorosta, mukavaa loppupäivää!",
                    "Vuoro paketissa – nauti loppupäivästä!",
                    "Hyvää loppupäivää, kiitos panoksestasi!",
                    "Työt tehty tältä erää, rentoa loppupäivää!"
                )
                in 17..21 -> listOf(
                    "Hyvää iltaa, kiitos työvuorosta!",
                    "Iltavuoro takana – mukavaa iltaa!",
                    "Kiitos tästä vuorosta, rentouttavaa iltaa!",
                    "Vuoro pulkassa, rauhallista iltaa!"
                )
                else -> listOf(
                    "Hyvää yötä, kiitos työvuorosta!",
                    "Kiitos myöhäisestä vuorosta, hyvää yötä!",
                    "Työpäivä taputeltu – rauhallista yötä!",
                    "Hyvää yötä ja mukavaa palautumista!"
                )
            }
        } else {
            when (hour) {
                in 4..9 -> listOf(
                    "Hyvää huomenta ja mukavaa työvuoroa!",
                    "Huomenta! Virkeää mieltä ja sujuvaa vuoroa!",
                    "Hyvää huomenta, tästä se työpäivä lähtee!",
                    "Mukavaa aamuvuoroa ja hyvää työvirettä!"
                )
                in 10..13 -> listOf(
                    "Hyvää päivää ja mukavaa työvuoroa!",
                    "Mukavaa työpäivää, hommat rullaamaan!",
                    "Hyvää päivää ja sujuvaa vuoroa!",
                    "Tsemppiä päivän vuoroon!"
                )
                in 14..17 -> listOf(
                    "Hyvää iltapäivää ja mukavaa iltavuoroa!",
                    "Tsemppiä iltavuoroon ja hyvää työvirettä!",
                    "Hyvää iltapäivää, sujuvaa vuoroa!",
                    "Mukavaa ja sujuvaa iltavuoroa!"
                )
                in 18..21 -> listOf(
                    "Hyvää iltaa ja tsemppiä vuoroon!",
                    "Rauhallista ja sujuvaa iltaa vuoroon!",
                    "Hyvää iltaa, hyvää virettä työvuoroon!",
                    "Tsemppiä alkavaan vuoroon!"
                )
                else -> listOf(
                    "Hyvää yötä ja tsemppiä yövuoroon!",
                    "Rauhallista yövuoroa ja hyvää virettä!",
                    "Tsemppiä yövuoroon, kyllä se siitä rullaa!",
                    "Sujuvaa ja rauhallista yötä töihin!"
                )
            }
        }
        return options.random()
    }


    private fun resetToLoadingUi() {
        progressBar.visibility = View.VISIBLE
        statusBadge.visibility = View.GONE
        greetingText.visibility = View.VISIBLE
    }

    private fun showFinalState(
        title: String,
        subtitle: String,
        badgeText: String,
        badgeFillHex: String,
        badgeStrokeHex: String,
        badgeTextHex: String,
        closeDelayMs: Long = 1200L
    ) {
        if (isCompleted || isFinishing || isDestroyed) return
        isCompleted = true
        cancelTimeout()

        progressBar.visibility = View.GONE
        statusBadge.background = GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            setColor(Color.parseColor(badgeFillHex))
            setStroke(dp(1), Color.parseColor(badgeStrokeHex))
        }
        statusBadge.text = badgeText
        statusBadge.setTextColor(Color.parseColor(badgeTextHex))
        statusBadge.visibility = View.VISIBLE

        if (badgeText == "!" && badgeFillHex != "#1E3A5F") {
            greetingText.visibility = View.GONE
        }

        titleText.text = title
        statusText.text = subtitle

        mainHandler.postDelayed({
            finishCleanly()
        }, closeDelayMs)
    }

    private fun finishCleanly() {
        cancelTimeout()
        destroyHiddenWebView()
        if (!isFinishing && !isDestroyed) {
            finish()
            overridePendingTransition(0, 0)
        }
    }

    private fun scheduleTimeout(ms: Long = 22_000L) {
        cancelTimeout()
        val r = Runnable {
            showFinalState(
                title = "Aikakatkaisu",
                subtitle = "Leimausta ei voitu vahvistaa ajoissa",
                badgeText = "!",
                badgeFillHex = "#3B2810",
                badgeStrokeHex = "#F59E0B",
                badgeTextHex = "#FBBF24",
                closeDelayMs = 1700L
            )
        }
        timeoutRunnable = r
        mainHandler.postDelayed(r, ms)
    }

    private fun cancelTimeout() {
        timeoutRunnable?.let { mainHandler.removeCallbacks(it) }
        timeoutRunnable = null
    }

    private fun processIntent(incoming: Intent?) {
        val notifId = incoming?.getIntExtra("NOTIF_ID", -1) ?: -1
        if (notifId > 0) {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.cancel(notifId)
        }

        val isEnding = incoming?.getBooleanExtra("IS_ENDING", false) ?: false
        val isTest = incoming?.getBooleanExtra("IS_TEST", false) ?: false
        val targetText = if (isEnding) "Ulos" else "Sisään"
        val actionTitle = if (isEnding) "Leimataan ulos" else "Leimataan sisään"

        greetingText.text = buildGreeting(isEnding)
        greetingText.visibility = View.VISIBLE

        titleText.text = actionTitle
        progressBar.indeterminateTintList = ColorStateList.valueOf(
            Color.parseColor(if (isEnding) "#F97316" else "#38BDF8")
        )

        if (isTest) {
            statusText.text = "Testi-ilmoitus ($targetText)…"
            activeJob = scope.launch {
                delay(650L)
                showFinalState(
                    title = "Testi-ilmoitus ($targetText)",
                    subtitle = "Oikeaa leimausta ei suoritettu",
                    badgeText = "✓",
                    badgeFillHex = "#0F2E26",
                    badgeStrokeHex = "#10B981",
                    badgeTextHex = "#34D399",
                    closeDelayMs = 1400L
                )
            }
            return
        }

        if (DemoModeHelper.isDemoEnabled(this)) {
            handleDemoQuickStamp(wantIn = !isEnding, targetText = targetText)
            return
        }

        val baseUrl = UrlNormalizer.getSavedBaseUrl(this)
        val user = SecureCredentialManager.getUsername(this).orEmpty()
        val pass = SecureCredentialManager.getPassword(this).orEmpty()

        if (baseUrl.isEmpty() || user.isEmpty() || pass.isEmpty()) {
            showFinalState(
                title = "Tunnukset puuttuvat",
                subtitle = "Tarkista kirjautuminen sovelluksesta",
                badgeText = "!",
                badgeFillHex = "#3B2810",
                badgeStrokeHex = "#F59E0B",
                badgeTextHex = "#FBBF24",
                closeDelayMs = 1700L
            )
            return
        }

        scheduleTimeout(22_000L)

        activeJob = scope.launch {
            val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val lastSessionMs = prefs.getLong("last_valid_session_ms", 0L)
            val sessionAgeMs = System.currentTimeMillis() - lastSessionMs
            val existingCookies = CookieManager.getInstance().getCookie(baseUrl)

            if (existingCookies.isNullOrBlank() || sessionAgeMs > 10L * 60 * 1000L) {
                statusText.text = "Kirjaudutaan sisään…"
                val ok = BackgroundAuthHelper.ensureAuthenticatedSession(this@QuickStampActivity)
                if (ok) {
                    prefs.edit().putLong("last_valid_session_ms", System.currentTimeMillis()).apply()
                }
            }

            if (!isCompleted) {
                statusText.text = "Avataan työaikaleimaus…"
                startHiddenStampingWebView(baseUrl, targetText)
            }
        }
    }

    private fun handleDemoQuickStamp(wantIn: Boolean, targetText: String) {
        statusText.text = "Suoritetaan demoleimaus…"
        activeJob = scope.launch {
            delay(550L)
            val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val currentlyIn = prefs.getBoolean("demo_stamped_in", false)
            if (wantIn != currentlyIn) {
                val nowDate = LocalDate.now().format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
                val nowTime = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
                val oldHistory = prefs.getString("demo_stamp_history", "") ?: ""
                val newHistory = "$nowDate | $nowTime | $targetText\n$oldHistory"
                prefs.edit()
                    .putBoolean("demo_stamped_in", wantIn)
                    .putString("demo_stamp_history", newHistory)
                    .apply()

                showFinalState(
                    title = "Demoleimaus vahvistettu",
                    subtitle = "$targetText • klo $nowTime",
                    badgeText = "✓",
                    badgeFillHex = "#0F2E26",
                    badgeStrokeHex = "#10B981",
                    badgeTextHex = "#34D399",
                    closeDelayMs = 1200L
                )
            } else {
                showFinalState(
                    title = "Ei leimattu",
                    subtitle = "Demotila: Olet jo tilassa $targetText",
                    badgeText = "!",
                    badgeFillHex = "#1E3A5F",
                    badgeStrokeHex = "#38BDF8",
                    badgeTextHex = "#7DD3FC",
                    closeDelayMs = 1400L
                )
            }
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun startHiddenStampingWebView(baseUrl: String, targetText: String) {
        destroyHiddenWebView()

        val root = findViewById<ViewGroup>(android.R.id.content).getChildAt(0) as? ViewGroup
        val webHolder = root?.getChildAt(0) as? ViewGroup

        val wv = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.databaseEnabled = true
            settings.userAgentString = WebSettings.getDefaultUserAgent(this@QuickStampActivity)
        }
        webHolder?.addView(wv, ViewGroup.LayoutParams(1, 1))
        hiddenWebView = wv

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(wv, true)

        var loginAttempted = false
        var stampClicked = false

        wv.webViewClient = object : WebViewClient() {

            override fun shouldInterceptRequest(
                view: WebView?,
                request: WebResourceRequest?
            ): WebResourceResponse? {
                val url = request?.url?.toString()?.lowercase()
                    ?: return super.shouldInterceptRequest(view, request)
                if (url.contains("amplitude.com") || url.endsWith(".css") || url.contains("/content/css/")) {
                    return WebResourceResponse("text/plain", "UTF-8", ByteArrayInputStream(ByteArray(0)))
                }
                return super.shouldInterceptRequest(view, request)
            }

            override fun onReceivedError(
                view: WebView?,
                errorCode: Int,
                description: String?,
                failingUrl: String?
            ) {
                if (!isCompleted && failingUrl?.contains(baseUrl, ignoreCase = true) == true) {
                    showFinalState(
                        title = "Yhteysvirhe",
                        subtitle = "Verkkoyhteys epäonnistui",
                        badgeText = "!",
                        badgeFillHex = "#3B181E",
                        badgeStrokeHex = "#EF4444",
                        badgeTextHex = "#F87171",
                        closeDelayMs = 1600L
                    )
                }
            }

            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                super.onPageStarted(view, url, favicon)
                if (url == null || isCompleted) return
                if (url.contains("/Login/Login", ignoreCase = true)) {
                    statusText.text = "Kirjaudutaan sisään…"
                } else if (url.contains("/WorktimeStamping", ignoreCase = true) && !stampClicked) {
                    statusText.text = "Haetaan leimaustilaa…"
                }
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                if (url == null || isCompleted) return

                CookieManager.getInstance().flush()
                if (!url.contains("/Login/", ignoreCase = true)) {
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                }

                when {
                    url.contains("/Login/Login", ignoreCase = true) -> {
                        if (!loginAttempted) {
                            loginAttempted = true
                            statusText.text = "Vahvistetaan kirjautuminen…"
                            submitAutoLogin(view)
                        } else {
                            showFinalState(
                                title = "Kirjautuminen epäonnistui",
                                subtitle = "Tarkista käyttäjätunnus ja salasana",
                                badgeText = "!",
                                badgeFillHex = "#3B181E",
                                badgeStrokeHex = "#EF4444",
                                badgeTextHex = "#F87171",
                                closeDelayMs = 1700L
                            )
                        }
                    }

                    url.contains("/WorktimeStamping", ignoreCase = true) -> {
                        if (!stampClicked) {
                            triggerStampClick(view, targetText, 0) {
                                stampClicked = true
                            }
                        }
                    }

                    else -> {
                        view?.loadUrl("$baseUrl/WorktimeStamping")
                    }
                }
            }
        }

        wv.loadUrl("$baseUrl/WorktimeStamping")
    }

    private fun submitAutoLogin(view: WebView?, attempt: Int = 0) {
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
                    p.value = '$pass';
                    u.dispatchEvent(new Event('input', { bubbles: true }));
                    p.dispatchEvent(new Event('input', { bubbles: true }));
                    f.submit();
                    return 'SUBMITTED';
                }
                return 'WAITING';
            })();
        """.trimIndent()

        view.evaluateJavascript(js) { res ->
            if (res?.contains("WAITING") == true && attempt < 10 && !isCompleted) {
                mainHandler.postDelayed({ submitAutoLogin(view, attempt + 1) }, 250L)
            }
        }
    }

    private fun triggerStampClick(
        view: WebView?,
        targetText: String,
        attempt: Int,
        onClicked: () -> Unit
    ) {
        if (view == null || isCompleted) return
        val targetLower = targetText.lowercase()

        val js = """
            (function() {
                var btn = document.getElementById('punchButton');
                if (!btn) return JSON.stringify({ status: 'NO_BUTTON' });
                var btnText = (btn.innerText || btn.textContent || '').trim();
                if (!btnText) return JSON.stringify({ status: 'NO_BUTTON' });
                var firstRow = '';
                var rowEl = document.querySelector('#table-latest-stamps tbody tr, #table-latest-stamps tr');
                if (rowEl) {
                    firstRow = (rowEl.innerText || rowEl.textContent || '').replace(/\s+/g, ' ').trim();
                }
                if (btnText.toLowerCase().indexOf('$targetLower') !== -1) {
                    btn.click();
                    return JSON.stringify({ status: 'CLICKED', btn: btnText, row: firstRow });
                } else {
                    return JSON.stringify({ status: 'WRONG_DIRECTION', btn: btnText, row: firstRow });
                }
            })();
        """.trimIndent()

        view.evaluateJavascript(js) { rawResult ->
            if (isCompleted) return@evaluateJavascript
            val obj = parseJsonResult(rawResult)
            val status = obj?.optString("status", "") ?: ""

            when {
                status == "CLICKED" -> {
                    onClicked()
                    val beforeBtn = obj?.optString("btn", "") ?: ""
                    val beforeRow = obj?.optString("row", "") ?: ""
                    statusText.text = "Lähetetään leimaus ($targetText)…"
                    verifyStampResult(view, targetText, beforeBtn, beforeRow, 0)
                }

                status == "WRONG_DIRECTION" -> {
                    showFinalState(
                        title = "Ei leimattu",
                        subtitle = "Olet jo leimannut tilaan: $targetText",
                        badgeText = "!",
                        badgeFillHex = "#1E3A5F",
                        badgeStrokeHex = "#38BDF8",
                        badgeTextHex = "#7DD3FC",
                        closeDelayMs = 1400L
                    )
                }

                status == "NO_BUTTON" && attempt < 12 -> {
                    mainHandler.postDelayed({
                        triggerStampClick(view, targetText, attempt + 1, onClicked)
                    }, 250L)
                }

                else -> {
                    showFinalState(
                        title = "Leimaus epäonnistui",
                        subtitle = "Leimauspainiketta ei löytynyt sivulta",
                        badgeText = "!",
                        badgeFillHex = "#3B181E",
                        badgeStrokeHex = "#EF4444",
                        badgeTextHex = "#F87171",
                        closeDelayMs = 1600L
                    )
                }
            }
        }
    }

    private fun verifyStampResult(
        view: WebView?,
        targetText: String,
        beforeBtn: String,
        beforeRow: String,
        checkAttempt: Int
    ) {
        if (view == null || isCompleted) return
        val targetLower = targetText.lowercase()

        val verifyJs = """
            (function() {
                var expired = false;
                var modals = document.querySelectorAll('#session-expired-modal, #sessionExpiredModal, #SessionExpiredModal, .modal, [role="dialog"]');
                for (var i = 0; i < modals.length; i++) {
                    var m = modals[i];
                    var st = window.getComputedStyle(m);
                    var vis = (m.offsetParent !== null) || (st && st.display !== 'none' && st.visibility !== 'hidden');
                    if (vis) {
                        var t = (m.innerText || m.textContent || '').toLowerCase();
                        if (m.id === 'session-expired-modal' || m.id === 'sessionExpiredModal' || t.indexOf('istunto vanhentunut') !== -1 || t.indexOf('session expired') !== -1) {
                            expired = true;
                            break;
                        }
                    }
                }
                if (window.location.pathname.toLowerCase().indexOf('/login') !== -1) {
                    expired = true;
                }
                var btn = document.getElementById('punchButton');
                var btnText = btn ? (btn.innerText || btn.textContent || '').trim() : '';
                var rowEl = document.querySelector('#table-latest-stamps tbody tr, #table-latest-stamps tr');
                var firstRow = rowEl ? (rowEl.innerText || rowEl.textContent || '').replace(/\s+/g, ' ').trim() : '';
                return JSON.stringify({ btn: btnText, row: firstRow, expired: expired });
            })();
        """.trimIndent()

        mainHandler.postDelayed({
            if (isCompleted || isFinishing || isDestroyed) return@postDelayed
            view.evaluateJavascript(verifyJs) { rawResult ->
                if (isCompleted) return@evaluateJavascript
                val obj = parseJsonResult(rawResult)
                val nowBtn = obj?.optString("btn", "") ?: ""
                val nowRow = obj?.optString("row", "") ?: ""
                val sessionExpired = obj?.optBoolean("expired", false) ?: false

                if (sessionExpired) {
                    if (!sessionRetried) {
                        sessionRetried = true
                        statusText.text = "Uusitaan istuntoa…"
                        getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                            .edit()
                            .putLong("last_valid_session_ms", 0L)
                            .apply()
                        val baseUrl = UrlNormalizer.getSavedBaseUrl(this)
                        scope.launch {
                            BackgroundAuthHelper.ensureAuthenticatedSession(this@QuickStampActivity)
                            if (!isCompleted && baseUrl.isNotEmpty()) {
                                startHiddenStampingWebView(baseUrl, targetText)
                            }
                        }
                    } else {
                        showFinalState(
                            title = "Istunto vanhentunut",
                            subtitle = "Avaa sovellus ja tarkista kirjautuminen",
                            badgeText = "!",
                            badgeFillHex = "#3B181E",
                            badgeStrokeHex = "#EF4444",
                            badgeTextHex = "#F87171",
                            closeDelayMs = 1700L
                        )
                    }
                    return@evaluateJavascript
                }

                val buttonFlipped = nowBtn.isNotEmpty() && nowBtn != beforeBtn &&
                    nowBtn.lowercase().indexOf(targetLower) == -1
                val rowUpdated = nowRow.isNotEmpty() && nowRow != beforeRow

                if (buttonFlipped || rowUpdated) {
                    CookieManager.getInstance().flush()
                    val nowTime = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
                    showFinalState(
                        title = "Leimaus vahvistettu",
                        subtitle = "$targetText • klo $nowTime",
                        badgeText = "✓",
                        badgeFillHex = "#0F2E26",
                        badgeStrokeHex = "#10B981",
                        badgeTextHex = "#34D399",
                        closeDelayMs = 1150L
                    )
                } else if (checkAttempt < 25) {
                    if (checkAttempt == 2) {
                        statusText.text = "Vahvistetaan leimausta…"
                    }
                    verifyStampResult(view, targetText, beforeBtn, beforeRow, checkAttempt + 1)
                } else {
                    showFinalState(
                        title = "Vahvistus viivästyi",
                        subtitle = "Tarkista leimaustila sovelluksesta",
                        badgeText = "!",
                        badgeFillHex = "#3B2810",
                        badgeStrokeHex = "#F59E0B",
                        badgeTextHex = "#FBBF24",
                        closeDelayMs = 1700L
                    )
                }
            }
        }, 280L)
    }

    private fun parseJsonResult(rawResult: String?): JSONObject? {
        return try {
            if (rawResult != null && rawResult != "null") {
                val unescaped = JSONTokener(rawResult).nextValue() as? String
                if (unescaped != null) JSONObject(unescaped) else null
            } else {
                null
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun destroyHiddenWebView() {
        try {
            hiddenWebView?.let { wv ->
                (wv.parent as? ViewGroup)?.removeView(wv)
                wv.stopLoading()
                wv.destroy()
            }
        } catch (_: Exception) {
        } finally {
            hiddenWebView = null
        }
    }

    override fun onDestroy() {
        cancelTimeout()
        try {
            CookieManager.getInstance().flush()
        } catch (_: Exception) {
        }
        destroyHiddenWebView()
        scope.cancel()
        super.onDestroy()
    }
}
