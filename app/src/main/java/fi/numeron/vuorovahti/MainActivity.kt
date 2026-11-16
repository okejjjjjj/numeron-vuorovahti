package fi.numeron.vuorovahti

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.animation.ValueAnimator
import android.os.Bundle
import android.view.View
import android.webkit.CookieManager
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONTokener
import java.time.LocalDate
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import android.graphics.Bitmap
import android.graphics.Color
import android.widget.ProgressBar
import android.widget.FrameLayout
import android.view.ViewGroup
import android.view.Gravity
import android.graphics.Shader
import android.graphics.RenderEffect
import android.content.res.ColorStateList
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import java.io.ByteArrayInputStream


class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var bannerDemoMode: TextView
    private lateinit var btnNavStamp: Button
    private lateinit var btnNavRequests: Button
    private lateinit var btnNavShifts: Button
    private lateinit var btnNavSettings: Button
    private lateinit var btnNavClose: Button

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())

    private var pendingAction: Action = Action.NONE
    private var currentTab: Tab = Tab.STAMP
    private var syncStep = 0
    private val collectedCalendarHtml = mutableListOf<String>()

    enum class Action {
        NONE, STAMP_IN, STAMP_OUT, SYNC_CALENDAR
    }

    enum class Tab {
        STAMP, REQUESTS, SHIFTS
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        setTheme(androidx.appcompat.R.style.Theme_AppCompat_NoActionBar)
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        requestNeededPermissions()
        ShiftReminderReceiver.ensureBackgroundSyncScheduled(this)

        CalendarSyncHelper.getTargetCalendarId(this)?.let {
            CalendarSyncHelper.scheduleShiftReminders(this, it)
        }

        webView = findViewById(R.id.webView)
        bannerDemoMode = findViewById(R.id.bannerDemoMode)
        btnNavStamp = findViewById(R.id.btnNavStamp)
        btnNavRequests = findViewById(R.id.btnNavRequests)
        btnNavShifts = findViewById(R.id.btnNavShifts)
        btnNavSettings = findViewById(R.id.btnNavSettings)
        btnNavClose = findViewById(R.id.btnNavClose)

        setupWebView()
        setupBottomBar()
        handleIncomingIntent(intent)

        if (intent?.getBooleanExtra("OPEN_REQUESTS", false) == true) {
            navigateToTab(Tab.REQUESTS)
        } else {
            navigateToTab(Tab.STAMP)
        }

        if (intent?.getBooleanExtra("OPEN_CALENDAR_CHANGES", false) == true) {
            intent.removeExtra("OPEN_CALENDAR_CHANGES")
            CalendarChangeTracker.showManageChangesDialog(this)
        }
    }

    private fun getBaseUrl(): String {
        return UrlNormalizer.getSavedBaseUrl(this)
    }

    private fun updateDemoBanner() {
        bannerDemoMode.visibility = if (DemoModeHelper.isDemoEnabled(this)) View.VISIBLE else View.GONE
    }

    private var transitionOverlay: FrameLayout? = null
    private var isTransitionActive: Boolean = false
    private var blurAnimator: ValueAnimator? = null
    private var currentBlurRadius: Float = 0f

    private fun applyWebViewBlur(radius: Float) {
        currentBlurRadius = radius
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (radius <= 0.5f) {
                webView.setRenderEffect(null)
            } else {
                webView.setRenderEffect(
                    RenderEffect.createBlurEffect(radius, radius, Shader.TileMode.CLAMP)
                )
            }
        }
    }

    private fun ensureTransitionOverlay(): FrameLayout {
        transitionOverlay?.let { overlay ->
            syncOverlayBoundsToWebView(overlay)
            return overlay
        }

        val rootContent = findViewById<FrameLayout>(android.R.id.content)
        val overlay = FrameLayout(this).apply {
            setBackgroundColor(Color.parseColor("#880F1722"))
            alpha = 0f
            visibility = View.GONE
            isClickable = true
            isFocusable = true
        }
        val spinner = ProgressBar(this).apply {
            isIndeterminate = true
            indeterminateTintList = ColorStateList.valueOf(Color.parseColor("#38BDF8"))
        }
        val sizePx = (34 * resources.displayMetrics.density).toInt()
        overlay.addView(spinner, FrameLayout.LayoutParams(sizePx, sizePx, Gravity.CENTER))

        rootContent.addView(overlay, FrameLayout.LayoutParams(webView.width, webView.height))
        syncOverlayBoundsToWebView(overlay)
        transitionOverlay = overlay
        return overlay
    }

    private fun syncOverlayBoundsToWebView(overlay: FrameLayout) {
        if (webView.width <= 0 || webView.height <= 0) return
        val rootContent = findViewById<View>(android.R.id.content)
        val webLoc = IntArray(2)
        val rootLoc = IntArray(2)
        webView.getLocationInWindow(webLoc)
        rootContent.getLocationInWindow(rootLoc)

        val lp = overlay.layoutParams as FrameLayout.LayoutParams
        lp.width = webView.width
        lp.height = webView.height
        lp.leftMargin = webLoc[0] - rootLoc[0]
        lp.topMargin = webLoc[1] - rootLoc[1]
        overlay.layoutParams = lp
    }

    private fun startBlurTransition(onBlurReady: (() -> Unit)? = null) {
        val overlay = ensureTransitionOverlay()
        overlay.animate().cancel()
        blurAnimator?.cancel()

        val maxRadius = 22f * resources.displayMetrics.density

        if (!isTransitionActive) {
            isTransitionActive = true
            overlay.visibility = View.VISIBLE
            overlay.animate()
                .alpha(1f)
                .setDuration(160L)
                .start()

            blurAnimator = ValueAnimator.ofFloat(currentBlurRadius, maxRadius).apply {
                duration = 160L
                addUpdateListener { anim ->
                    applyWebViewBlur(anim.animatedValue as Float)
                }
                start()
            }

            if (onBlurReady != null) {
                webView.postDelayed({ onBlurReady() }, 130L)
            }
        } else {
            onBlurReady?.invoke()
        }
    }

    private fun endBlurTransition() {
        val overlay = transitionOverlay ?: return
        if (!isTransitionActive) return

        overlay.animate().cancel()
        blurAnimator?.cancel()

        blurAnimator = ValueAnimator.ofFloat(currentBlurRadius, 0f).apply {
            duration = 260L
            addUpdateListener { anim ->
                applyWebViewBlur(anim.animatedValue as Float)
            }
            start()
        }

        overlay.animate()
            .alpha(0f)
            .setDuration(260L)
            .withEndAction {
                applyWebViewBlur(0f)
                overlay.visibility = View.GONE
                isTransitionActive = false
            }
            .start()
    }

    private fun navigateToTab(tab: Tab) {
        currentTab = tab
        updateDemoBanner()

        when (tab) {
            Tab.STAMP -> setActiveTab(btnNavStamp)
            Tab.REQUESTS -> setActiveTab(btnNavRequests)
            Tab.SHIFTS -> setActiveTab(btnNavShifts)
        }

        if (DemoModeHelper.isDemoEnabled(this)) {
            startBlurTransition {
                val html = when (tab) {
                    Tab.STAMP -> DemoModeHelper.getDemoStampingHtml(this)
                    Tab.REQUESTS -> DemoModeHelper.getDemoRequestsHtml(this)
                    Tab.SHIFTS -> DemoModeHelper.getDemoShiftsHtml(this)
                }
                webView.loadDataWithBaseURL("https://demo.local/", html, "text/html", "UTF-8", null)
            }
        } else {
            val baseUrl = getBaseUrl()
            if (baseUrl.isEmpty()) {
                Toast.makeText(this, "Aseta ensin organisaatiotunnus asetuksista", Toast.LENGTH_LONG).show()
                btnNavSettings.performClick()
                return
            }
            val url = when (tab) {
                Tab.STAMP -> "$baseUrl/WorktimeStamping"
                Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
                Tab.SHIFTS -> "$baseUrl/Calendar/Month"
            }
            startBlurTransition {
                webView.loadUrl(url)
            }
        }
    }

    private fun setupBottomBar() {
        btnNavStamp.setOnClickListener {
            pendingAction = Action.NONE
            navigateToTab(Tab.STAMP)
        }

        btnNavRequests.setOnClickListener {
            pendingAction = Action.NONE
            navigateToTab(Tab.REQUESTS)
        }

        btnNavShifts.setOnClickListener {
            pendingAction = Action.NONE
            navigateToTab(Tab.SHIFTS)
        }

        btnNavSettings.setOnClickListener {
            SettingsDialogHelper.showSettingsDialog(
                context = this,
                onManualSync = { startCalendarSync() },
                onManageChanges = { CalendarChangeTracker.showManageChangesDialog(this) },
                onTestNotification = { triggerTestReminderNotification() },
                onSaved = {
                    CalendarSyncHelper.getTargetCalendarId(this)?.let {
                        CalendarSyncHelper.scheduleShiftReminders(this, it)
                    }
                    navigateToTab(currentTab)
                }
            )
        }

        btnNavClose.setOnClickListener {
            finishAndRemoveTask()
        }
    }

    private fun triggerTestReminderNotification() {
        val timeStr = LocalTime.now().plusMinutes(30).format(DateTimeFormatter.ofPattern("HH:mm"))
        ShiftReminderReceiver().showReminderNotification(
            context = this,
            shiftTitle = "Aamuvuoro (Testi-ilmoitus)",
            timeStr = timeStr,
            isEnding = false,
            isTest = true
        )
    }

    private fun setActiveTab(activeBtn: Button) {
        val tabs = listOf(btnNavStamp, btnNavRequests, btnNavShifts)
        for (btn in tabs) {
            if (btn == activeBtn) {
                btn.setBackgroundResource(R.drawable.nav_btn_active)
                btn.setTextColor(0xFFFFFFFF.toInt())
            } else {
                btn.setBackgroundResource(R.drawable.nav_btn_inactive)
                btn.setTextColor(0xFFE0E6ED.toInt())
            }
        }
    }

    private fun startCalendarSync() {
        if (DemoModeHelper.isDemoEnabled(this)) {
            scope.launch(Dispatchers.IO) {
                val calId = CalendarSyncHelper.getTargetCalendarId(this@MainActivity)
                if (calId != null) {
                    val demoShifts = DemoModeHelper.generateDemoWorkShifts(this@MainActivity)
                    val changes = CalendarSyncHelper.syncShiftsToCalendar(this@MainActivity, calId, demoShifts)
                    CalendarSyncHelper.scheduleShiftReminders(this@MainActivity, calId)
                    withContext(Dispatchers.Main) {
                        if (changes.isNotEmpty()) {
                            Toast.makeText(
                                this@MainActivity,
                                "Kalenterimuutokset: ${CalendarChangeTracker.formatSummary(changes)}",
                                Toast.LENGTH_LONG
                            ).show()
                            CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                        } else {
                            Toast.makeText(
                                this@MainActivity,
                                "Demovuorot ovat jo ajan tasalla kalenterissa",
                                Toast.LENGTH_SHORT
                            ).show()
                        }
                    }
                } else {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(this@MainActivity, "Kalenterioikeus tai kalenteri puuttuu", Toast.LENGTH_LONG).show()
                    }
                }
            }
            return
        }

        pendingAction = Action.SYNC_CALENDAR
        syncStep = 0
        collectedCalendarHtml.clear()
        val now = LocalDate.now()
        val baseUrl = getBaseUrl()
        webView.loadUrl("$baseUrl/Calendar/Month?month=${now.monthValue}&year=${now.year}")
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIncomingIntent(intent)
        if (pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT) {
            navigateToTab(Tab.STAMP)
        } else if (intent?.getBooleanExtra("OPEN_REQUESTS", false) == true) {
            navigateToTab(Tab.REQUESTS)
        }

        if (intent?.getBooleanExtra("OPEN_CALENDAR_CHANGES", false) == true) {
            intent.removeExtra("OPEN_CALENDAR_CHANGES")
            CalendarChangeTracker.showManageChangesDialog(this)
        }
    }

    private fun handleIncomingIntent(intent: Intent?) {
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
    }

    private fun requestNeededPermissions() {
        val perms = mutableListOf(
            Manifest.permission.READ_CALENDAR,
            Manifest.permission.WRITE_CALENDAR
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            perms.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        val missing = perms.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 101)
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        webView.setBackgroundColor(Color.parseColor("#0F1722"))
        (webView.parent as? View)?.setBackgroundColor(Color.parseColor("#0F1722"))

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            userAgentString = WebSettings.getDefaultUserAgent(this@MainActivity)
        }

        webView.addJavascriptInterface(
            DemoModeHelper.DemoJsBridge(
                context = this,
                onReloadNeeded = { runOnUiThread { navigateToTab(currentTab) } },
                onSyncRequested = { runOnUiThread { startCalendarSync() } },
                onManageChangesRequested = { runOnUiThread { CalendarChangeTracker.showManageChangesDialog(this) } }
            ),
            "DemoBridge"
        )

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)

        webView.webViewClient = object : WebViewClient() {

            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                super.onPageStarted(view, url, favicon)
                startBlurTransition()
            }

            override fun shouldInterceptRequest(
                view: WebView?,
                request: WebResourceRequest?
            ): WebResourceResponse? {
                val url = request?.url?.toString()?.lowercase()
                    ?: return super.shouldInterceptRequest(view, request)

                val blockedCssPatterns = listOf(
                    "/content/css/cssvisma",
                    "/content/css/login.css",
                    "/content/css/calendar.css",
                    "/content/css/buttons.css",
                    "/bundles/cssworktimestamping",
                    "/content/css/worktimestamping.css",
                    "/content/css/listlayout.css",
                    "fonts.googleapis.com"
                )

                if (blockedCssPatterns.any { url.contains(it) }) {
                    return WebResourceResponse(
                        "text/css",
                        "UTF-8",
                        ByteArrayInputStream(ByteArray(0))
                    )
                }

                return super.shouldInterceptRequest(view, request)
            }

            override fun onPageCommitVisible(view: WebView?, url: String?) {
                super.onPageCommitVisible(view, url)
                if (url != null && !url.startsWith("https://demo.local/")) {
                    injectDarkTheme(view)
                }
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                if (url == null) return

                if (url.startsWith("https://demo.local/")) {
                    handleDemoAutoStamp()
                    endBlurTransition()
                    return
                }

                injectDarkTheme(view)

                when {
                    url.contains("/Login/Login", ignoreCase = true) -> handleAutoLogin()
                    url.contains("/WorktimeStamping", ignoreCase = true) -> {
                        setActiveTab(btnNavStamp)
                        handleStampingPage()
                    }
                    url.contains("/PersonRequests", ignoreCase = true) -> {
                        setActiveTab(btnNavRequests)
                    }
                    url.contains("/Calendar", ignoreCase = true) -> {
                        setActiveTab(btnNavShifts)
                        handleCalendarPage()
                    }
                }

                val revealDelay = if (url.contains("/Calendar", ignoreCase = true)) 280L else 200L
                view?.postDelayed({
                    endBlurTransition()
                }, revealDelay)
            }
        }
    }

    private fun handleDemoAutoStamp() {
        if (pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT) {
            val wantIn = (pendingAction == Action.STAMP_IN)
            pendingAction = Action.NONE
            val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val currentlyIn = prefs.getBoolean("demo_stamped_in", false)
            if (wantIn != currentlyIn) {
                webView.evaluateJavascript("DemoBridge.toggleStamp()", null)
                webView.postDelayed({ finishAndRemoveTask() }, 1200L)
            } else {
                val stateStr = if (wantIn) "Sisään" else "Ulos"
                Toast.makeText(this, "Demotila: Olet jo leimannut tilaan $stateStr", Toast.LENGTH_SHORT).show()
                webView.postDelayed({ finishAndRemoveTask() }, 1200L)
            }
        }
    }

        private fun injectDarkTheme(view: WebView?) {
        val css = """
            /* === 1. PERUSRUNKO JA PIILOTETTAVAT ELEMENTIT === */
            html, body {
                background-color: #0F1722 !important;
                background-image: none !important;
                color: #F1F5F9 !important;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            header, nav.navbar, footer, .footer, .copyright, .loginnav, .bottom-nav, .fade-in-box, .fade-out-box {
                display: none !important;
            }
            .container, .container-fluid {
                padding: 12px !important;
                width: 100% !important;
                max-width: 100% !important;
            }
            h1, h2, h3, h4, .h1, .h2, .h3, .h4 {
                color: #F1F5F9 !important;
                font-size: 20px !important;
                font-weight: 600 !important;
                margin-top: 4px !important;
                margin-bottom: 12px !important;
            }
            label, span, p, div {
                color: inherit;
            }
            a {
                color: #38BDF8 !important;
            }

            /* === 2. KORTIT, PANEELIT JA SYÖTTÖKENTÄT === */
            .panel, .panel-default, .whitebox, .card, .stamping-box, .box, .panel-footer, .form-actions {
                background-color: #182332 !important;
                border: 1px solid #2A394A !important;
                border-radius: 12px !important;
                color: #F1F5F9 !important;
                box-shadow: none !important;
                margin-bottom: 14px !important;
            }
            .panel-body {
                padding: 14px !important;
            }
            .panel-heading, .modal-header, .modal-footer {
                background-color: #1E293B !important;
                border-color: #2A394A !important;
                color: #F1F5F9 !important;
            }
            .modal-content {
                background-color: #182332 !important;
                border: 1px solid #37475A !important;
                color: #F1F5F9 !important;
            }
            input, select, textarea, .form-control, .k-textbox {
                background-color: #111923 !important;
                color: #FFFFFF !important;
                border: 1px solid #37475A !important;
                border-radius: 8px !important;
                box-shadow: none !important;
            }
            input[type="checkbox"], input[type="radio"] {
                accent-color: #1982C4 !important;
                width: 18px !important;
                height: 18px !important;
            }
            input::placeholder, textarea::placeholder {
                color: #64748B !important;
            }

            /* === 3. PAINIKKEET JA PUDOTUSVALIKOT === */
            .btn, .btn-default {
                background-color: #233040 !important;
                color: #F1F5F9 !important;
                border: 1px solid #37475A !important;
                border-radius: 8px !important;
                padding: 8px 14px !important;
                font-weight: 500 !important;
            }
            .btn-primary {
                background-color: #1982C4 !important;
                border-color: #1982C4 !important;
                color: #FFFFFF !important;
                font-weight: 600 !important;
            }
            .btn-text, .btn-link {
                background-color: transparent !important;
                border: none !important;
                color: #38BDF8 !important;
                padding: 6px 0 !important;
            }
            .dropdown-menu {
                background-color: #1E293B !important;
                border: 1px solid #37475A !important;
                border-radius: 8px !important;
            }
            .dropdown-menu > li > a {
                color: #F1F5F9 !important;
                padding: 8px 14px !important;
            }
            .dropdown-menu > li > a:hover, .dropdown-menu > li > a:focus {
                background-color: #2A394A !important;
                color: #FFFFFF !important;
            }
            .dropdown-header {
                color: #94A3B8 !important;
            }

            /* === 4. KIRJAUTUMISSIVU === */
            .content {
                padding: 16px !important;
                float: none !important;
                margin: 0 auto !important;
            }
            .blurbox h1 {
                text-align: center !important;
                font-size: 28px !important;
                font-weight: 700 !important;
                margin: 28px 0 20px 0 !important;
                color: #F1F5F9 !important;
            }
            .whitebox {
                padding: 20px !important;
                margin: 0 auto !important;
            }
            .whitebox img, .whitebox hr {
                display: none !important;
            }
            #LoginForm .form-group {
                margin-bottom: 14px !important;
            }
            #LoginForm .pull-left, #LoginForm .pull-right {
                margin-bottom: 12px !important;
                font-size: 13px !important;
            }
            #LoginForm input[type="submit"] {
                margin-top: 8px !important;
                padding: 12px !important;
                font-size: 16px !important;
            }

            /* === 5. TYÖAIKALEIMAUS === */
            .punching-balance-overview-container {
                display: none !important;
            }
            .punching-shift-caption, .previous-stamps-caption, .punching-caption {
                display: block !important;
                font-size: 12px !important;
                text-transform: uppercase !important;
                letter-spacing: 0.05em !important;
                color: #94A3B8 !important;
                margin-bottom: 6px !important;
                font-weight: 600 !important;
            }
            .punching-shift-name {
                font-size: 16px !important;
                font-weight: 600 !important;
                color: #F1F5F9 !important;
            }
            .punching-reason-code-label, .punching-stamp-comment-label, .forgotten-stamp-labels {
                color: #CBD5E1 !important;
                font-size: 13px !important;
                margin-top: 10px !important;
                margin-bottom: 4px !important;
            }
            .punch-reason-code-selector .btn, #dropdownMenu1, #dropdownMenu2, #dropdownMenuStampDirection {
                width: 100% !important;
                display: flex !important;
                justify-content: space-between !important;
                align-items: center !important;
                background-color: #111923 !important;
            }
            #punchButton {
                background-color: #2E7D32 !important;
                border-color: #2E7D32 !important;
                color: #FFFFFF !important;
                border-radius: 10px !important;
                padding: 12px !important;
                margin-top: 16px !important;
                font-weight: 700 !important;
            }
            .nav-tabs-wts {
                list-style: none !important;
                padding: 0 !important;
                margin: 0 0 10px 0 !important;
                border-bottom: 1px solid #2A394A !important;
                display: flex !important;
            }
            .nav-tabs-wts > li > a {
                display: inline-block !important;
                padding: 8px 14px !important;
                color: #F1F5F9 !important;
                border-bottom: 2px solid #2196F3 !important;
                text-decoration: none !important;
                font-weight: 600 !important;
            }
            #table-latest-stamps, .table {
                background-color: transparent !important;
                color: #F1F5F9 !important;
                margin-bottom: 8px !important;
            }
            #table-latest-stamps td, .table td, .table th {
                background-color: transparent !important;
                border-top: 1px solid #2A394A !important;
                color: #F1F5F9 !important;
                padding: 10px 6px !important;
            }
            #table-latest-stamps tr:hover td {
                background-color: #233040 !important;
            }
            #forgotStampPanel {
                display: none !important;
            }
            #forgotStampPanel[style*="top: 0"], #forgotStampPanel[style*="top:0"] {
                display: block !important;
                position: fixed !important;
                left: 8px !important;
                right: 8px !important;
                bottom: 8px !important;
                top: auto !important;
                z-index: 1050 !important;
                max-height: 88vh !important;
                overflow-y: auto !important;
            }

            /* === 6. TOIVEET & KENDO UI === */
            label[for="filterOptions"] {
                color: #F1F5F9 !important;
                margin-right: 6px !important;
            }
            .fixed-menu-bar {
                display: flex !important;
                flex-wrap: wrap !important;
                gap: 8px !important;
                align-items: center !important;
            }
            .k-grid, .k-grid-header, .k-grid-content, .k-pager-wrap {
                background-color: #182332 !important;
                color: #F1F5F9 !important;
                border-color: #2A394A !important;
            }
            .k-grid-header th.k-header, .k-grid-header th.k-header > .k-link {
                background-color: #233040 !important;
                color: #F1F5F9 !important;
                border-color: #2A394A !important;
                padding: 10px 8px !important;
            }
            .k-grid tr {
                background-color: #182332 !important;
                color: #F1F5F9 !important;
            }
            .k-grid tr.k-alt {
                background-color: #131C28 !important;
            }
            .k-grid td {
                border-color: #2A394A !important;
                color: #F1F5F9 !important;
                padding: 10px 8px !important;
            }
            .k-grid tr:hover td {
                background-color: #233040 !important;
                color: #FFFFFF !important;
            }
            .k-grid tr.k-state-selected td {
                background-color: #1982C4 !important;
                color: #FFFFFF !important;
            }
            .k-widget, .k-dropdown-wrap, .k-picker-wrap, .k-numeric-wrap, .k-select, .k-input, .k-pager-wrap .k-link, .k-pager-info {
                background-color: #111923 !important;
                color: #F1F5F9 !important;
                border-color: #37475A !important;
            }
            .k-list-container, .k-list, .k-calendar, .k-calendar .k-header {
                background-color: #1E293B !important;
                color: #F1F5F9 !important;
                border-color: #37475A !important;
            }
            .k-list .k-item:hover, .k-list .k-state-focused, .k-list .k-state-selected {
                background-color: #2A394A !important;
                color: #FFFFFF !important;
            }

            /* === 7. KALENTERI: YLÄPALKKI JA KUUKAUSINÄKYMÄ === */
            .calendar-heading {
                box-shadow: none !important;
                display: flex !important;
                justify-content: space-between !important;
                align-items: center !important;
                background-color: #182332 !important;
                border: 1px solid #2A394A !important;
                border-radius: 12px !important;
                padding: 8px 12px !important;
                margin-bottom: 12px !important;
            }
            .monthSelector .panel-body {
                padding: 4px !important;
                display: flex !important;
                align-items: center !important;
                gap: 12px !important;
            }
            #monthText {
                color: #F1F5F9 !important;
                font-size: 18px !important;
                font-weight: 600 !important;
                margin: 0 !important;
            }
            .prevButton::before {
                content: "◀" !important;
                color: #38BDF8 !important;
                font-size: 16px !important;
                text-decoration: none !important;
            }
            .nextButton::before {
                content: "▶" !important;
                color: #38BDF8 !important;
                font-size: 16px !important;
                text-decoration: none !important;
            }
            .month-table {
                width: 100% !important;
                table-layout: fixed !important;
                border-collapse: collapse !important;
                background-color: #182332 !important;
            }
            .month-week-days td {
                background-color: #233040 !important;
                color: #CBD5E1 !important;
                font-weight: 600 !important;
                font-size: 12px !important;
                padding: 6px 2px !important;
                border: 1px solid #2A394A !important;
                text-align: center !important;
            }
            .month-week-number {
                width: 26px !important;
                background-color: #131C28 !important;
                color: #64748B !important;
                font-size: 11px !important;
                text-align: center !important;
                vertical-align: top !important;
                padding-top: 6px !important;
                border: 1px solid #2A394A !important;
            }
            td.month-day {
                background-color: #182332 !important;
                border: 1px solid #2A394A !important;
                vertical-align: top !important;
                height: 68px !important;
                padding: 2px !important;
            }
            td.month-day.past-day, td.month-day.day-different-month {
                background-color: #121A24 !important;
            }
            td.month-day.todayTd {
                background-color: #1E3A5F !important;
                border: 1px solid #38BDF8 !important;
            }
            .month-day-header {
                margin-bottom: 2px !important;
            }
            .dayNum {
                color: #F1F5F9 !important;
                font-size: 12px !important;
                font-weight: 600 !important;
                padding-left: 3px !important;
            }
            td.day-different-month .dayNum {
                color: #64748B !important;
            }
            .month-item.work {
                background-color: #0284C7 !important;
                color: #FFFFFF !important;
                border-radius: 4px !important;
                padding: 2px 3px !important;
                margin-bottom: 2px !important;
                font-size: 11px !important;
                line-height: 1.2 !important;
            }
            .month-item.work .itemTimes {
                display: block !important;
                color: #FFFFFF !important;
                font-weight: 600 !important;
            }
            .month-item.work .itemName {
                display: none !important;
            }

            /* === 8. KALENTERI: LUETTELONÄKYMÄ (/Calendar/List) === */
            #calendar-content {
                height: auto !important;
                overflow-y: visible !important;
            }
            .schedule-week-separator {
                margin: 14px 0 8px 0 !important;
                padding: 4px 2px !important;
                border-bottom: 1px solid #2A394A !important;
            }
            .schedule-week-separator-text {
                color: #38BDF8 !important;
                font-size: 13px !important;
                font-weight: 700 !important;
                text-transform: uppercase !important;
                letter-spacing: 0.05em !important;
            }
            .schedule-day-container {
                background-color: #182332 !important;
                border: 1px solid #2A394A !important;
                border-radius: 12px !important;
                padding: 12px !important;
                margin-bottom: 10px !important;
            }
            .schedule-day-information {
                display: flex !important;
                align-items: center !important;
                margin-bottom: 8px !important;
                padding-bottom: 6px !important;
                border-bottom: 1px solid #233040 !important;
            }
            .schedule-day {
                color: #94A3B8 !important;
                font-size: 12px !important;
                font-weight: 700 !important;
                letter-spacing: 0.04em !important;
            }
            .schedule-day-date {
                color: #F1F5F9 !important;
                font-size: 14px !important;
                font-weight: 700 !important;
            }
            .schedule-item-container {
                display: flex !important;
                align-items: stretch !important;
                background-color: #111923 !important;
                border: 1px solid #2A394A !important;
                border-left: 4px solid #0284C7 !important;
                border-radius: 8px !important;
                padding: 10px !important;
                margin-bottom: 8px !important;
            }
            .schedule-item-container.schedule-item-absence {
                border-left-color: #F59E0B !important;
            }
            .schedule-item-container.schedule-item-request {
                border-left-color: #8B5CF6 !important;
            }
            .schedule-item-container.schedule-item-opportunity {
                border-left-color: #10B981 !important;
            }
            .schedule-item-color-bar, .schedule-item-icon-td, .clear-float {
                display: none !important;
            }
            .schedule-item-content {
                width: 100% !important;
            }
            .schedule-item-body {
                display: flex !important;
                flex-direction: column !important;
                gap: 4px !important;
            }
            .schedule-item-times {
                color: #38BDF8 !important;
                font-size: 15px !important;
                font-weight: 700 !important;
            }
            .schedule-item-description-table {
                width: 100% !important;
            }
            .schedule-item-description-heading {
                color: #F1F5F9 !important;
                font-size: 14px !important;
                font-weight: 600 !important;
            }
            .schedule-item-description-subheading {
                color: #94A3B8 !important;
                font-size: 12px !important;
                margin-top: 2px !important;
            }
            .schedule-day-content > div[style*="max-height"] {
                max-height: none !important;
                margin-top: 6px !important;
            }
            .schedule-add-button {
                display: inline-block !important;
                color: #38BDF8 !important;
                font-size: 13px !important;
                font-weight: 600 !important;
                padding: 4px 0 !important;
                cursor: pointer !important;
            }
            .schedule-add-options {
                margin-top: 6px !important;
                display: flex !important;
                gap: 8px !important;
            }
            .schedule-option-link {
                background-color: #233040 !important;
                border: 1px solid #37475A !important;
                border-radius: 6px !important;
                padding: 6px 10px !important;
                font-size: 13px !important;
                text-decoration: none !important;
            }
            .mobileAddDiv {
                display: flex !important;
                justify-content: space-between !important;
                align-items: center !important;
                margin-top: 10px !important;
                padding: 4px 0 !important;
            }
            .mobileAddButton, .filterButton {
                background-color: #233040 !important;
                color: #F1F5F9 !important;
                border: 1px solid #37475A !important;
                border-radius: 8px !important;
                padding: 8px 14px !important;
                text-decoration: none !important;
                display: inline-block !important;
            }
            #mobileViewDropdown {
                margin-top: 8px !important;
            }
        """.trimIndent().replace("\n", " ")

        val js = """
        val safeCss = css.replace("\\", "\\\\").replace("'", "\\'")
        val js = """
            (function() {
                var style = document.getElementById('custom-dark-theme');
                if (!style) {
                    style = document.createElement('style');
                    style.id = 'custom-dark-theme';
                    document.head.appendChild(style);
                }
                style.innerHTML = '$safeCss';
            })();
        """.trimIndent()
        view?.evaluateJavascript(js, null)
    }

        private fun handleAutoLogin() {
        val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val user = (prefs.getString("username", "") ?: "").replace("\\", "\\\\").replace("'", "\\'")
        val pass = (prefs.getString("password", "") ?: "").replace("\\", "\\\\").replace("'", "\\'")
        if (user.isEmpty() || pass.isEmpty()) return

        val js = """
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
        webView.evaluateJavascript(js, null)
    }


    private fun handleStampingPage() {
        if (pendingAction != Action.STAMP_IN && pendingAction != Action.STAMP_OUT) return

        val targetText = if (pendingAction == Action.STAMP_IN) "Sisään" else "Ulos"
        pendingAction = Action.NONE

        val js = """
            (function() {
                var btn = document.getElementById('punchButton');
                if (!btn) return 'NO_BUTTON';
                var btnText = btn.innerText.trim();
                if (btnText.indexOf('$targetText') !== -1) {
                    btn.click();
                    return 'STAMPED_' + btnText;
                } else {
                    return 'WRONG_DIRECTION_' + btnText;
                }
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { result ->
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
        }
    }

    private fun handleCalendarPage() {
        if (pendingAction != Action.SYNC_CALENDAR) return

        webView.evaluateJavascript("document.documentElement.outerHTML") { rawHtml ->
            if (rawHtml == null || rawHtml == "null") return@evaluateJavascript
            val unescapedHtml = JSONTokener(rawHtml).nextValue() as String
            collectedCalendarHtml.add(unescapedHtml)

            if (syncStep == 0) {
                syncStep = 1
                val nextMonth = LocalDate.now().plusMonths(1)
                val baseUrl = getBaseUrl()
                webView.loadUrl("$baseUrl/Calendar/Month?month=${nextMonth.monthValue}&year=${nextMonth.year}")
            } else {
                pendingAction = Action.NONE
                val pagesToParse = collectedCalendarHtml.toList()
                collectedCalendarHtml.clear()

                scope.launch(Dispatchers.IO) {
                    val calId = CalendarSyncHelper.getTargetCalendarId(this@MainActivity)
                    if (calId != null) {
                        val allShifts = pagesToParse.flatMap { NumeronParser.parseCalendarHtml(it) }
                        val changes = CalendarSyncHelper.syncShiftsToCalendar(this@MainActivity, calId, allShifts)
                        CalendarSyncHelper.scheduleShiftReminders(this@MainActivity, calId)

                        withContext(Dispatchers.Main) {
                            if (changes.isNotEmpty()) {
                                Toast.makeText(
                                    this@MainActivity,
                                    "Kalenteria päivitetty: ${CalendarChangeTracker.formatSummary(changes)}",
                                    Toast.LENGTH_LONG
                                ).show()
                                CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                            } else {
                                Toast.makeText(
                                    this@MainActivity,
                                    "Kalenteri on ajan tasalla (${allShifts.size} vuoroa)",
                                    Toast.LENGTH_SHORT
                                ).show()
                            }
                        }
                    }
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        scope.cancel()
    }
}
