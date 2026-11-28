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
import java.io.ByteArrayInputStream
import java.time.LocalDate
import java.time.LocalTime
import java.time.format.DateTimeFormatter

class QuickStampActivity : AppCompatActivity() {

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private val mainHandler = Handler(Looper.getMainLooper())
    private var activeJob: Job? = null
    private var timeoutRunnable: Runnable? = null
    private var closeRunnable: Runnable? = null

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
            mainHandler.removeCallbacksAndMessages(null)
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
                if (isCompleted) {
                    finishCleanly()
                }
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
        val en = DemoModeHelper.isEnglish(this)
        val hour = LocalTime.now().hour
        if (en) {
            val enOptions = if (isEnding) {
                when (hour) {
                    in 5..10 -> listOf(
                        "Good morning, thank you for the night shift!",
                        "Morning has arrived – get some well-earned rest!",
                        "Night shift complete, have a restful day!"
                    )
                    in 11..16 -> listOf(
                        "Thanks for your shift, enjoy the rest of your day!",
                        "Shift wrapped up – have a great afternoon!",
                        "Work done for now, enjoy your time off!"
                    )
                    in 17..21 -> listOf(
                        "Good evening, thank you for your shift!",
                        "Evening shift done – have a relaxing evening!",
                        "Thanks for today's shift, enjoy your evening!"
                    )
                    else -> listOf(
                        "Good night, thank you for your shift!",
                        "Thanks for the late shift, sleep well!",
                        "Shift complete – have a peaceful night!"
                    )
                }
            } else {
                when (hour) {
                    in 4..9 -> listOf(
                        "Good morning and have a great shift!",
                        "Morning! Wishing you a smooth and steady shift!",
                        "Have a pleasant morning shift!"
                    )
                    in 10..13 -> listOf(
                        "Good day and have a smooth shift!",
                        "Wishing you a productive day shift!",
                        "Have a great shift today!"
                    )
                    in 14..17 -> listOf(
                        "Good afternoon and have a great evening shift!",
                        "Wishing you a smooth evening shift!",
                        "Have a pleasant afternoon and evening shift!"
                    )
                    in 18..21 -> listOf(
                        "Good evening and have a smooth shift!",
                        "Wishing you a calm and steady evening!",
                        "Have a great shift tonight!"
                    )
                    else -> listOf(
                        "Good night and have a smooth night shift!",
                        "Wishing you a calm and steady night shift!",
                        "Have a great night shift!"
                    )
                }
            }
            return enOptions.random()
        }
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

        closeRunnable?.let { mainHandler.removeCallbacks(it) }
        val r = Runnable { finishCleanly() }
        closeRunnable = r
        mainHandler.postDelayed(r, closeDelayMs)
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
        closeRunnable?.let { mainHandler.removeCallbacks(it) }
        closeRunnable = null
    }

    private fun processIntent(incoming: Intent?) {
        val notifId = incoming?.getIntExtra("NOTIF_ID", -1) ?: -1
        if (notifId > 0) {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.cancel(notifId)
        }

        val en = DemoModeHelper.isEnglish(this)
        val isEnding = incoming?.getBooleanExtra("IS_ENDING", false) ?: false
        val isTest = incoming?.getBooleanExtra("IS_TEST", false) ?: false
        val targetText = if (en) {
            if (isEnding) "Out" else "In"
        } else {
            if (isEnding) "Ulos" else "Sisään"
        }
        val actionTitle = if (en) {
            if (isEnding) "Clocking out" else "Clocking in"
        } else {
            if (isEnding) "Leimataan ulos" else "Leimataan sisään"
        }

        greetingText.text = buildGreeting(isEnding)
        greetingText.visibility = View.VISIBLE

        titleText.text = actionTitle
        progressBar.indeterminateTintList = ColorStateList.valueOf(
            Color.parseColor(if (isEnding) "#F97316" else "#38BDF8")
        )

        if (isTest) {
            statusText.text = if (en) "Test notification ($targetText)…" else "Testi-ilmoitus ($targetText)…"
            activeJob = scope.launch {
                delay(650L)
                showFinalState(
                    title = if (en) "Test notification ($targetText)" else "Testi-ilmoitus ($targetText)",
                    subtitle = if (en) "No actual stamp was recorded" else "Oikeaa leimausta ei suoritettu",
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

        if (BackgroundAuthHelper.isCredentialBlocked(this)) {
            showFinalState(
                title = if (en) "Login failed" else "Kirjautuminen epäonnistui",
                subtitle = if (en) "Check username and password in Settings" else "Tarkista käyttäjätunnus ja salasana asetuksista",
                badgeText = "!",
                badgeFillHex = "#3B181E",
                badgeStrokeHex = "#EF4444",
                badgeTextHex = "#F87171",
                closeDelayMs = 1700L
            )
            return
        }

        activeJob = scope.launch {
            val wantIn = !isEnding
            val result = NumeronApiClient.performQuickStamp(
                context = this@QuickStampActivity,
                wantIn = wantIn,
                onStatusUpdate = { msg ->
                    runOnUiThread {
                        if (!isCompleted) statusText.text = msg
                    }
                }
            )
            if (isCompleted) return@launch

            when (result) {
                is StampSubmitResult.Success -> {
                    val nowTime = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
                    showFinalState(
                        title = if (en) "Stamp confirmed" else "Leimaus vahvistettu",
                        subtitle = if (en) "$targetText • at $nowTime" else "$targetText • klo $nowTime",
                        badgeText = "✓",
                        badgeFillHex = "#0F2E26",
                        badgeStrokeHex = "#10B981",
                        badgeTextHex = "#34D399",
                        closeDelayMs = 1150L
                    )
                }
                is StampSubmitResult.AlreadyInDirection -> {
                    showFinalState(
                        title = if (en) "Not stamped" else "Ei leimattu",
                        subtitle = if (en) "Already clocked $targetText" else "Olet jo leimannut tilaan: $targetText",
                        badgeText = "!",
                        badgeFillHex = "#1E3A5F",
                        badgeStrokeHex = "#38BDF8",
                        badgeTextHex = "#7DD3FC",
                        closeDelayMs = 1400L
                    )
                }
                is StampSubmitResult.ValidationRejected -> {
                    showFinalState(
                        title = if (en) "Stamp rejected" else "Leimausta ei hyväksytty",
                        subtitle = result.message,
                        badgeText = "!",
                        badgeFillHex = "#3B2810",
                        badgeStrokeHex = "#F59E0B",
                        badgeTextHex = "#FBBF24",
                        closeDelayMs = 2000L
                    )
                }
                is StampSubmitResult.Failed -> {
                    if (result.fallbackToWebView && !BackgroundAuthHelper.isCredentialBlocked(this@QuickStampActivity)) {
                        statusText.text = if (en) "Opening time stamping…" else "Avataan työaikaleimaus…"
                        startHiddenStampingWebView(baseUrl, wantIn = wantIn, targetText = targetText)
                    } else {
                        showFinalState(
                            title = if (en) "Stamp failed" else "Leimaus epäonnistui",
                            subtitle = result.message,
                            badgeText = "!",
                            badgeFillHex = "#3B181E",
                            badgeStrokeHex = "#EF4444",
                            badgeTextHex = "#F87171",
                            closeDelayMs = 1700L
                        )
                    }
                }
            }
        }
    }

    private fun handleDemoQuickStamp(wantIn: Boolean, targetText: String) {
        val en = DemoModeHelper.isEnglish(this)
        statusText.text = if (en) "Recording demo stamp…" else "Suoritetaan demoleimaus…"
        activeJob = scope.launch {
            delay(550L)
            val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val currentlyIn = prefs.getBoolean("demo_stamped_in", false)
            if (wantIn != currentlyIn) {
                val nowDate = LocalDate.now().format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
                val nowTime = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
                val yest = LocalDate.now().minusDays(1).format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
                val defaultHistory = "$yest | 14:30 | Ulos\n$yest | 07:00 | Sisään"
                val oldHistory = prefs.getString("demo_stamp_history", defaultHistory) ?: defaultHistory
                val newHistory = "$nowDate | $nowTime | $targetText\n$oldHistory"
                prefs.edit()
                    .putBoolean("demo_stamped_in", wantIn)
                    .putString("demo_stamp_history", newHistory)
                    .apply()

                showFinalState(
                    title = if (en) "Demo stamp confirmed" else "Demoleimaus vahvistettu",
                    subtitle = if (en) "$targetText • at $nowTime" else "$targetText • klo $nowTime",
                    badgeText = "✓",
                    badgeFillHex = "#0F2E26",
                    badgeStrokeHex = "#10B981",
                    badgeTextHex = "#34D399",
                    closeDelayMs = 1200L
                )
            } else {
                showFinalState(
                    title = if (en) "Not stamped" else "Ei leimattu",
                    subtitle = if (en) "Demo mode: Already clocked $targetText" else "Demotila: Olet jo tilassa $targetText",
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
    private fun startHiddenStampingWebView(baseUrl: String, wantIn: Boolean, targetText: String) {
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
        wv.resumeTimers()
        wv.onResume()

        SessionCookieStore.syncToWebViewCookieManager(this, baseUrl)
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
                if (url.contains("amplitude") || url.contains("eligibility.") || url.endsWith(".css") || url.contains("/content/css/")) {
                    return WebResourceResponse("text/plain", "UTF-8", ByteArrayInputStream(ByteArray(0)))
                }
                return super.shouldInterceptRequest(view, request)
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: android.webkit.WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame != true || isCompleted) return
                val code = error?.errorCode ?: 0
                if (code == -1 || code == WebViewClient.ERROR_UNKNOWN) return
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
                    SessionCookieStore.importFromWebViewCookieManager(this@QuickStampActivity, baseUrl)
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                }

                when {
                    url.contains("/Login/LogOff", ignoreCase = true) -> {
                        view?.loadUrl("$baseUrl/Login/Login")
                    }

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
                            triggerStampClick(view, wantIn, targetText, 0) {
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
        val userJson = JSONObject.quote(SecureCredentialManager.getUsername(this) ?: "")
        val passJson = JSONObject.quote(SecureCredentialManager.getPassword(this) ?: "")

        val js = """
            (function() {
                var u = document.getElementById('Username');
                var p = document.getElementById('Password');
                var f = document.getElementById('LoginForm');
                if (u && p && f) {
                    u.value = $userJson;
                    p.value = $passJson;
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
        wantIn: Boolean,
        targetText: String,
        attempt: Int,
        onClicked: () -> Unit
    ) {
        if (view == null || isCompleted) return

        view.evaluateJavascript(StampingWebHelper.buildClickStampJs(wantIn)) { rawResult ->
            if (isCompleted) return@evaluateJavascript
            val obj = StampingWebHelper.parseJsonResult(rawResult)
            val status = obj?.optString("status", "") ?: ""

            when {
                status == "CLICKED" -> {
                    onClicked()
                    val beforeDir = obj?.optString("dir", "") ?: ""
                    val beforeBtn = obj?.optString("btn", "") ?: ""
                    val beforeRow = obj?.optString("row", "") ?: ""
                    val beforeRowId = obj?.optString("rowId", "") ?: ""
                    statusText.text = "Lähetetään leimaus ($targetText)…"
                    verifyStampResult(view, wantIn, targetText, beforeDir, beforeBtn, beforeRow, beforeRowId, 0)
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
                        triggerStampClick(view, wantIn, targetText, attempt + 1, onClicked)
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
        wantIn: Boolean,
        targetText: String,
        beforeDir: String,
        beforeBtn: String,
        beforeRow: String,
        beforeRowId: String,
        checkAttempt: Int
    ) {
        if (view == null || isCompleted) return

        mainHandler.postDelayed({
            if (isCompleted || isFinishing || isDestroyed) return@postDelayed
            view.evaluateJavascript(StampingWebHelper.buildVerifyStampJs()) { rawResult ->
                if (isCompleted) return@evaluateJavascript
                val obj = StampingWebHelper.parseJsonResult(rawResult)
                val nowDir = obj?.optString("dir", "") ?: ""
                val nowBtn = obj?.optString("btn", "") ?: ""
                val nowRow = obj?.optString("row", "") ?: ""
                val nowRowId = obj?.optString("rowId", "") ?: ""
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
                            BackgroundAuthHelper.ensureAuthenticatedSession(
                                this@QuickStampActivity,
                                forceRefresh = true
                            )
                            if (!isCompleted && baseUrl.isNotEmpty()) {
                                startHiddenStampingWebView(baseUrl, wantIn, targetText)
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

                if (StampingWebHelper.isStampConfirmed(
                        wantIn = wantIn,
                        beforeDir = beforeDir,
                        beforeBtn = beforeBtn,
                        beforeRow = beforeRow,
                        beforeRowId = beforeRowId,
                        nowDir = nowDir,
                        nowBtn = nowBtn,
                        nowRow = nowRow,
                        nowRowId = nowRowId
                    )
                ) {
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
                    verifyStampResult(
                        view, wantIn, targetText, beforeDir, beforeBtn, beforeRow, beforeRowId, checkAttempt + 1
                    )
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
        isCompleted = true
        activeJob?.cancel()
        mainHandler.removeCallbacksAndMessages(null)
        cancelTimeout()
        try {
            if (hiddenWebView != null) {
                CookieManager.getInstance().flush()
            }
        } catch (_: Exception) {
        }
        destroyHiddenWebView()
        scope.cancel()
        super.onDestroy()
    }
}
