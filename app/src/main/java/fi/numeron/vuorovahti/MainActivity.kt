package fi.numeron.vuorovahti

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
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
import android.widget.ImageView
import android.graphics.Canvas
import android.graphics.Color
import android.widget.ProgressBar
import android.widget.FrameLayout
import android.view.ViewGroup
import android.view.Gravity
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
    private var inFlightStampAction: Action = Action.NONE
    private var lastSessionRecoveryMs: Long = 0L
    private var currentTab: Tab = Tab.STAMP
    private var dashboardRedirectCount: Int = 0
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

        window.statusBarColor = Color.parseColor("#0F1722")
        window.navigationBarColor = Color.parseColor("#0F1722")
        androidx.core.view.WindowInsetsControllerCompat(window, window.decorView).apply {
            isAppearanceLightStatusBars = false
            isAppearanceLightNavigationBars = false
        }
        val contentFrame = findViewById<ViewGroup>(android.R.id.content)
        contentFrame.setBackgroundColor(Color.parseColor("#0F1722"))
        val activityRoot = contentFrame.getChildAt(0)
        if (activityRoot != null) {
            androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(activityRoot) { v, windowInsets ->
                val insets = windowInsets.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars())
                v.setPadding(insets.left, insets.top, insets.right, insets.bottom)
                windowInsets
            }
        }

        requestNeededPermissions()
        ShiftReminderReceiver.ensureBackgroundSyncScheduled(this)

        CalendarSyncHelper.scheduleShiftReminders(this)

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

        // Näytetään heti käynnistyksessä splash-ruutu "Kirjaudutaan..."
        startSnapshotTransition()

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


    private fun resolveResumeUrl(baseUrl: String): String {
        return when {
            pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> "$baseUrl/WorktimeStamping"
            pendingAction == Action.SYNC_CALENDAR -> "$baseUrl/Calendar/Month"
            currentTab == Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
            currentTab == Tab.SHIFTS -> "$baseUrl/Calendar/Month"
            else -> "$baseUrl/WorktimeStamping"
        }
    }

    private fun getBaseUrl(): String {
        return UrlNormalizer.getSavedBaseUrl(this)
    }

    private fun updateDemoBanner() {
        bannerDemoMode.visibility = if (DemoModeHelper.isDemoEnabled(this)) View.VISIBLE else View.GONE
    }

    private var transitionOverlay: FrameLayout? = null
    private var snapshotView: ImageView? = null
    private var isTransitionActive: Boolean = false

        private fun ensureTransitionOverlay(): FrameLayout {
        transitionOverlay?.let { overlay ->
            syncOverlayBoundsToWebView(overlay)
            return overlay
        }

        val rootContent = findViewById<FrameLayout>(android.R.id.content)
        val overlay = FrameLayout(this).apply {
            setBackgroundColor(Color.parseColor("#0F1722"))
            alpha = 0f
            visibility = View.GONE
            isClickable = true
            isFocusable = true
        }

        val snap = ImageView(this).apply {
            scaleType = ImageView.ScaleType.FIT_XY
            alpha = 1f
            visibility = View.GONE
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
                try {
                    val blur = android.graphics.RenderEffect.createBlurEffect(24f, 24f, android.graphics.Shader.TileMode.CLAMP)
                    setRenderEffect(blur)
                } catch (_: Exception) {}
            }
        }
        overlay.addView(
            snap,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        snapshotView = snap

        val scrim = View(this).apply {
            setBackgroundColor(Color.parseColor("#660F1722"))
        }
        overlay.addView(
            scrim,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )

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

    private fun startSnapshotTransition(onReady: (() -> Unit)? = null) {
        val overlay = ensureTransitionOverlay()
        overlay.animate().cancel()

        if (!isTransitionActive) {
            isTransitionActive = true

            if (webView.width > 0 && webView.height > 0 && webView.alpha > 0.5f) {
                try {
                    val bitmap = Bitmap.createBitmap(webView.width, webView.height, Bitmap.Config.ARGB_8888)
                    val canvas = Canvas(bitmap)
                    webView.draw(canvas)
                    snapshotView?.setImageBitmap(bitmap)
                    snapshotView?.visibility = View.VISIBLE
                } catch (_: Exception) {
                    snapshotView?.setImageDrawable(null)
                    snapshotView?.visibility = View.GONE
                }
            } else {
                snapshotView?.setImageDrawable(null)
                snapshotView?.visibility = View.GONE
            }

            overlay.alpha = 1f
            overlay.visibility = View.VISIBLE
            webView.alpha = 0f

            if (onReady != null) {
                webView.post { onReady() }
            }
        } else {
            onReady?.invoke()
        }
    }

    private fun endSnapshotTransition() {
        val overlay = transitionOverlay ?: return
        if (!isTransitionActive) return

        overlay.animate().cancel()
        webView.alpha = 1f

        overlay.animate()
            .alpha(0f)
            .setDuration(320L)
            .withEndAction {
                overlay.visibility = View.GONE
                snapshotView?.setImageDrawable(null)
                snapshotView?.visibility = View.GONE
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
            startSnapshotTransition {
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
            startSnapshotTransition {
                val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                val lastSessionMs = prefs.getLong("last_valid_session_ms", 0L)
                val sessionAgeMs = System.currentTimeMillis() - lastSessionMs
                val existingCookies = CookieManager.getInstance().getCookie(baseUrl)
                val isAutoStamping = (pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT)
                val maxSessionAgeMs = if (isAutoStamping) 10L * 60 * 1000L else 25L * 60 * 1000L

                if (existingCookies.isNullOrBlank() || sessionAgeMs > maxSessionAgeMs) {
                    scope.launch {
                        val ok = BackgroundAuthHelper.ensureAuthenticatedSession(this@MainActivity)
                        if (ok) {
                            prefs.edit().putLong("last_valid_session_ms", System.currentTimeMillis()).apply()
                        }
                        webView.loadUrl(url)
                    }
                } else {
                    webView.loadUrl(url)
                }
            }
        }
    }

    private fun setupBottomBar() {
        btnNavStamp.setOnClickListener {
            pendingAction = Action.NONE
            inFlightStampAction = Action.NONE
            navigateToTab(Tab.STAMP)
        }

        btnNavRequests.setOnClickListener {
            pendingAction = Action.NONE
            inFlightStampAction = Action.NONE
            navigateToTab(Tab.REQUESTS)
        }

        btnNavShifts.setOnClickListener {
            pendingAction = Action.NONE
            inFlightStampAction = Action.NONE
            navigateToTab(Tab.SHIFTS)
        }

        btnNavSettings.setOnClickListener {
            SettingsDialogHelper.showSettingsDialog(
                context = this,
                onManualSync = { startCalendarSync() },
                onManageChanges = { CalendarChangeTracker.showManageChangesDialog(this) },
                onTestNotification = { triggerTestReminderNotification() },
                onSaved = {
                    CalendarSyncHelper.scheduleShiftReminders(this)
                    ShiftReminderReceiver.ensureBackgroundSyncScheduled(this)
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
        val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val syncCalendar = prefs.getBoolean("sync_calendar_enabled", true)

        if (DemoModeHelper.isDemoEnabled(this)) {
            scope.launch(Dispatchers.IO) {
                val calId = if (syncCalendar) CalendarSyncHelper.getTargetCalendarId(this@MainActivity) else null
                val demoShifts = DemoModeHelper.generateDemoWorkShifts(this@MainActivity)
                CalendarSyncHelper.saveCachedShifts(this@MainActivity, demoShifts)
                val changes = if (syncCalendar && calId != null) {
                    CalendarSyncHelper.syncShiftsToCalendar(this@MainActivity, calId, demoShifts)
                } else {
                    prefs.edit().putLong("last_calendar_sync_ms", System.currentTimeMillis()).apply()
                    emptyList()
                }
                CalendarSyncHelper.scheduleShiftReminders(this@MainActivity, calId)

                withContext(Dispatchers.Main) {
                    if (syncCalendar && calId == null) {
                        Toast.makeText(this@MainActivity, "Kalenterioikeus tai kalenteri puuttuu", Toast.LENGTH_LONG).show()
                    } else if (changes.isNotEmpty()) {
                        Toast.makeText(
                            this@MainActivity,
                            "Kalenterimuutokset: ${CalendarChangeTracker.formatSummary(changes)}",
                            Toast.LENGTH_LONG
                        ).show()
                        CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                    } else {
                        val msg = if (syncCalendar) {
                            "Demovuorot ovat jo ajan tasalla kalenterissa"
                        } else {
                            "Demovuorot ja muistutukset päivitetty (${demoShifts.size} vuoroa)"
                        }
                        Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
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
        val notifId = intent?.getIntExtra("NOTIF_ID", -1) ?: -1
        if (notifId > 0) {
            intent?.removeExtra("NOTIF_ID")
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
            nm.cancel(notifId)
        }

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

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val alarmManager = getSystemService(Context.ALARM_SERVICE) as android.app.AlarmManager
            val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            if (!alarmManager.canScheduleExactAlarms() && !prefs.getBoolean("exact_alarm_prompted", false)) {
                prefs.edit().putBoolean("exact_alarm_prompted", true).apply()
                Toast.makeText(
                    this,
                    "Salli tarkat hälytykset, jotta vuoromuistutukset tulevat ajallaan",
                    Toast.LENGTH_LONG
                ).show()
                try {
                    startActivity(
                        Intent(
                            android.provider.Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                            android.net.Uri.parse("package:$packageName")
                        )
                    )
                } catch (_: Exception) {
                }
            }
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

        webView.addJavascriptInterface(
            object {
                @android.webkit.JavascriptInterface
                fun onSessionExpired() {
                    runOnUiThread {
                        handleWebSessionExpired()
                    }
                }
            },
            "SessionBridge"
        )

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)

        webView.webViewClient = object : WebViewClient() {

            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val url = request?.url?.toString() ?: return false
                if (url.startsWith("http://") || url.startsWith("https://")) {
                    startSnapshotTransition()
                    return false
                }
                return super.shouldOverrideUrlLoading(view, request)
            }

            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                super.onPageStarted(view, url, favicon)
                startSnapshotTransition()
            }

            override fun shouldInterceptRequest(
                view: WebView?,
                request: WebResourceRequest?
            ): WebResourceResponse? {
                val url = request?.url?.toString()?.lowercase()
                    ?: return super.shouldInterceptRequest(view, request)

                if (url.contains("amplitude.com")) {
                    return WebResourceResponse(
                        "application/javascript",
                        "UTF-8",
                        ByteArrayInputStream(ByteArray(0))
                    )
                }

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
                    endSnapshotTransition()
                    return
                }

                injectDarkTheme(view)
                CookieManager.getInstance().flush()
                if (!url.contains("/Login/", ignoreCase = true) && !url.contains("/InfraDashboard", ignoreCase = true)) {
                    dashboardRedirectCount = 0
                }
                if (!url.contains("/Login/", ignoreCase = true)) {
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                }

                when {
                    url.contains("/Login/Login", ignoreCase = true) -> {
                        startSnapshotTransition()
                        handleAutoLogin()
                    }
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
                    pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> {
                        webView.loadUrl("${getBaseUrl()}/WorktimeStamping")
                    }
                }

                val revealDelay = if (url.contains("/Calendar", ignoreCase = true)) 280L else 200L
                view?.postDelayed({
                    endSnapshotTransition()
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
            .punching-shift-times {
                display: block !important;
                font-size: 24px !important;
                font-weight: 700 !important;
                color: #FFFFFF !important;
                line-height: 1.25 !important;
                margin-bottom: 6px !important;
            }
            .punching-shift-name {
                display: block !important;
                font-size: 16px !important;
                font-weight: 600 !important;
                color: #38BDF8 !important;
                line-height: 1.3 !important;
            }
            .punching-shift-workplace {
                display: block !important;
                font-size: 16px !important;
                font-weight: 600 !important;
                color: #38BDF8 !important;
                line-height: 1.3 !important;
                margin-bottom: 2px !important;
            }
            .punching-shift-role {
                display: block !important;
                font-size: 14px !important;
                font-weight: 500 !important;
                color: #CBD5E1 !important;
                line-height: 1.3 !important;
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
            #forgotStampPanel,
            #forgotStampPanel.minimized,
            #forgotStampPanel[style*="top: 100%"],
            #forgotStampPanel[style*="top:100%"] {
                display: none !important;
            }
            #forgotStampPanel[style*="top:"]:not(.minimized):not([style*="top: 100%"]):not([style*="top:100%"]),
            #forgotStampPanel.force-open {
                display: block !important;
                position: fixed !important;
                left: 12px !important;
                right: 12px !important;
                bottom: 12px !important;
                top: auto !important;
                z-index: 1050 !important;
                background-color: #182332 !important;
                border: 1px solid #2A394A !important;
                border-radius: 14px !important;
                padding: 16px !important;
                box-shadow: 0 10px 25px rgba(0,0,0,0.5) !important;
                max-height: 85vh !important;
                overflow-y: auto !important;
                color: #F1F5F9 !important;
            }
            .drw-fog-of-war.showing {
                display: block !important;
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                right: 0 !important;
                bottom: 0 !important;
                background-color: rgba(0, 0, 0, 0.65) !important;
                z-index: 1040 !important;
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
            .k-grid {
                overflow-x: auto !important;
            }
            .k-grid-content {
                overflow-x: auto !important;
                -webkit-overflow-scrolling: touch !important;
            }
            .k-grid-header th.k-header,
            .k-grid-header th.k-header .k-link,
            .k-grid-header th.k-header .k-column-title,
            .k-grid-header th.k-header .k-grid-header-menu,
            .k-grid-header th.k-header .k-icon {
                background-color: #233040 !important;
                color: #F1F5F9 !important;
                border-color: #2A394A !important;
            }
            .k-grid-header th.k-header {
                padding: 10px 8px !important;
            }
            .k-checkbox,
            .k-grid input[type="checkbox"] {
                background-color: #111923 !important;
                border: 1px solid #38BDF8 !important;
                border-radius: 4px !important;
                width: 18px !important;
                height: 18px !important;
                appearance: auto !important;
                -webkit-appearance: checkbox !important;
            }
            .k-checkbox:checked {
                background-color: #1982C4 !important;
                border-color: #38BDF8 !important;
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
            .k-widget, .k-dropdown-wrap, .k-picker-wrap, .k-numeric-wrap, .k-select, .k-input,
            .k-picker, .k-dropdownlist, .k-input-inner, .k-input-value-text,
            .k-pager-wrap .k-link, .k-pager-info {
                background-color: #111923 !important;
                color: #F1F5F9 !important;
                border-color: #37475A !important;
            }
            .k-pager-wrap .k-picker,
            .k-pager-wrap .k-dropdownlist {
                min-width: 68px !important;
                height: 34px !important;
                display: inline-flex !important;
                align-items: center !important;
            }
            .k-pager-wrap .k-input-inner {
                padding: 4px 8px !important;
                display: flex !important;
                align-items: center !important;
            }
            .k-pager-wrap .k-input-value-text {
                color: #F1F5F9 !important;
                font-size: 13px !important;
                visibility: visible !important;
                opacity: 1 !important;
            }
            .k-input-button {
                background-color: #233040 !important;
                color: #F1F5F9 !important;
                border-left: 1px solid #37475A !important;
            }
            .k-list-container, .k-list, .k-dropdown, .k-dropdown-wrap, .k-picker-wrap,
            select, .k-animation-container, .k-popup, .k-list-ul, .k-calendar, .k-time-list-wrapper {
                background-color: #182332 !important;
                color: #F1F5F9 !important;
                border: 1px solid #2A394A !important;
            }
            .k-calendar-header, .k-calendar-view, .k-calendar td, .k-calendar th {
                background-color: #182332 !important;
                color: #F1F5F9 !important;
                border-color: #2A394A !important;
            }
            .k-calendar td.k-selected .k-link, .k-calendar td.k-state-selected .k-link {
                background-color: #1982C4 !important;
                color: #FFFFFF !important;
            }
            .k-list .k-item, .k-list-item, .k-time-list .k-item {
                color: #F1F5F9 !important;
                background-color: #182332 !important;
                padding: 10px 12px !important;
            }
            .k-list .k-item:hover, .k-list .k-state-focused, .k-list .k-state-selected,
            .k-list-item:hover, .k-list-item.k-hover, .k-list-item.k-selected, .k-list-item.k-focus {
                background-color: #2A394A !important;
                color: #FFFFFF !important;
            }

            /* === SELECT2 & TOIVEEN MUOKKAUS (/PersonRequests/Edit) === */
            .select2-container {
                width: 100% !important;
            }
            .select2-container--default .select2-selection--single {
                background-color: #111923 !important;
                border: 1px solid #37475A !important;
                border-radius: 8px !important;
                height: 40px !important;
                display: flex !important;
                align-items: center !important;
            }
            .select2-container--default .select2-selection--single .select2-selection__rendered {
                color: #F1F5F9 !important;
                line-height: 38px !important;
                padding-left: 12px !important;
                padding-right: 30px !important;
            }
            .select2-container--default .select2-selection--single .select2-selection__placeholder {
                color: #64748B !important;
            }
            .select2-container--default .select2-selection--single .select2-selection__arrow {
                height: 38px !important;
                right: 8px !important;
            }
            .select2-container--default .select2-selection--single .select2-selection__arrow b {
                border-color: #94A3B8 transparent transparent transparent !important;
            }
            .select2-dropdown {
                background-color: #182332 !important;
                border: 1px solid #37475A !important;
                border-radius: 8px !important;
                color: #F1F5F9 !important;
            }
            .select2-search--dropdown .select2-search__field {
                background-color: #111923 !important;
                color: #F1F5F9 !important;
                border: 1px solid #37475A !important;
                border-radius: 6px !important;
            }
            .select2-results__option {
                background-color: #182332 !important;
                color: #F1F5F9 !important;
                padding: 10px 12px !important;
            }
            .select2-container--default .select2-results__option--highlighted[aria-selected],
            .select2-container--default .select2-results__option--highlighted {
                background-color: #1982C4 !important;
                color: #FFFFFF !important;
            }
            .select2-container--default .select2-results__option[aria-selected="true"] {
                background-color: #233040 !important;
                color: #38BDF8 !important;
            }
            #FullDaySwitch,
            #SeriesRequestSwitch {
                min-width: 54px !important;
                height: 28px !important;
                border-radius: 14px !important;
                position: relative !important;
            }
            #FullDaySwitch:not(.active),
            #SeriesRequestSwitch:not(.active) {
                background-color: #233040 !important;
                border-color: #475569 !important;
            }
            #FullDaySwitch.active,
            #SeriesRequestSwitch.active {
                background-color: #1982C4 !important;
                border-color: #38BDF8 !important;
            }
            .input-group-addon {
                background-color: #233040 !important;
                border: 1px solid #37475A !important;
                color: #38BDF8 !important;
                border-radius: 0 8px 8px 0 !important;
            }
            .vismaicon-datepicker::before {
                content: "📅" !important;
                font-style: normal !important;
            }
            .vismaicon-time::before {
                content: "🕒" !important;
                font-style: normal !important;
            }
            hr {
                border-top: 1px solid #2A394A !important;
            }
            .editPageContainer table {
                width: 100% !important;
            }
            .editPageContainer td {
                padding-right: 6px !important;
            }
            #InfoTextArea {
                width: 100% !important;
            }
            .FooterPanel {
                display: flex !important;
                flex-direction: column !important;
                gap: 8px !important;
            }
            .FooterPanel .SubmitButton:not(.hidden) {
                width: 100% !important;
                margin: 0 !important;
                padding: 12px !important;
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
                // === LISÄTTÄVÄT PÄIVÄNTOIVOTUKSET TYÖVUOROILLE ===
                (function addShiftGreeting() {
                    var container = document.querySelector('.punching-shift-container');
                    if (!container || document.getElementById('numeron-login-greeting')) return;
                    var hour = new Date().getHours();
                    var greeting = "Hyvää työpäivää!";
                    if (hour < 10) greeting = "Hyvää huomenta, mukavaa työvirettä!";
                    else if (hour >= 14 && hour < 20) greeting = "Hyvää iltapäivää, jaksuja vuoroon!";
                    else if (hour >= 20 || hour < 4) greeting = "Hyvää iltaa ja tsemppiä vuoroon!";

                    var greetDiv = document.createElement('div');
                    greetDiv.id = 'numeron-login-greeting';
                    greetDiv.style.cssText = 'font-size:13px;color:#38BDF8;font-weight:600;margin-bottom:8px;padding:6px 10px;background:#111923;border:1px solid #2A394A;border-radius:8px;';
                    greetDiv.textContent = '✨ ' + greeting;
                    container.insertBefore(greetDiv, container.firstChild);
                })();
                // === TÄNÄÄN-OSION MUOTOILU KOLMELLE RIVILLE ===
                (function formatTodayShiftBox() {
                    function capFirst(str) {
                        if (!str) return '';
                        return str.charAt(0).toUpperCase() + str.slice(1);
                    }

                    function parseShiftText(rawName) {
                        var cleaned = (rawName || '').trim().replace(/^\d+\s*/, '').trim();
                        if (!cleaned) return { location: '', shiftName: '', role: '' };

                        // Vapaapäivät / poissaolot jätetään yhdelle riville
                        if (/^(ei\s+(työ)?vuoroa|vapaa|vapaapäivä|vuosiloma|sairausloma|poissaolo)/i.test(cleaned)) {
                            return { location: capFirst(cleaned), shiftName: '', role: '' };
                        }

                        var tokens = cleaned.split(/\s+/).filter(function(t) { return t.length > 0; });
                        if (tokens.length === 0) return { location: '', shiftName: '', role: '' };

                        var shiftKeywords = {
                            'aamu': true, 'aamuvuoro': true,
                            'ilta': true, 'iltavuoro': true,
                            'yö': true, 'yövuoro': true,
                            'päivä': true, 'päivävuoro': true,
                            'väli': true, 'välivuoro': true
                        };

                        var firstKwIdx = -1;
                        for (var i = 0; i < tokens.length; i++) {
                            if (shiftKeywords[tokens[i].toLowerCase()]) {
                                firstKwIdx = i;
                                break;
                            }
                        }

                        if (firstKwIdx !== -1) {
                            var location = tokens.slice(0, firstKwIdx).join(' ');
                            var remainder = tokens.slice(firstKwIdx);
                            var lastKwOffset = -1;
                            for (var j = remainder.length - 1; j >= 0; j--) {
                                if (shiftKeywords[remainder[j].toLowerCase()]) {
                                    lastKwOffset = j;
                                    break;
                                }
                            }
                            var shiftName = capFirst(remainder.slice(0, lastKwOffset + 1).join(' '));
                            var role = capFirst(remainder.slice(lastKwOffset + 1).join(' '));
                            return { location: location, shiftName: shiftName, role: role };
                        } else if (tokens.length >= 2) {
                            var roleOnly = capFirst(tokens[tokens.length - 1]);
                            var locOnly = tokens.slice(0, tokens.length - 1).join(' ');
                            return { location: locOnly, shiftName: '', role: roleOnly };
                        } else {
                            return { location: cleaned, shiftName: '', role: '' };
                        }
                    }

                    function applyShiftFormat() {
                        var container = document.querySelector('.punching-shift-container');
                        if (!container) return;
                        var nameEl = container.querySelector('.punching-shift-name');
                        if (!nameEl) return;

                        var existingWp = nameEl.querySelector('.punching-shift-workplace');
                        var rawText = existingWp
                            ? (nameEl.getAttribute('data-raw-shift') || '')
                            : (nameEl.textContent || '').replace(/\s+/g, ' ').trim();
                        if (!rawText) return;

                        if (existingWp && nameEl.getAttribute('data-formatted-for') === 'v2:' + rawText) {
                            return;
                        }
                        nameEl.setAttribute('data-raw-shift', rawText);
                        nameEl.setAttribute('data-formatted-for', 'v2:' + rawText);

                        var parsed = parseShiftText(rawText);
                        var thirdLine = [parsed.shiftName, parsed.role]
                            .filter(function(s) { return s && s.length > 0; })
                            .join(' • ');

                        nameEl.textContent = '';
                        if (parsed.location) {
                            var wpSpan = document.createElement('span');
                            wpSpan.className = 'punching-shift-workplace';
                            wpSpan.textContent = parsed.location;
                            nameEl.appendChild(wpSpan);
                        }

                        if (thirdLine) {
                            var roleSpan = document.createElement('span');
                            roleSpan.className = 'punching-shift-role';
                            roleSpan.textContent = thirdLine;
                            nameEl.appendChild(roleSpan);
                        }
                    }

                    applyShiftFormat();
                    if (!window._todayShiftObserverInstalled) {
                        window._todayShiftObserverInstalled = true;
                        var target = document.querySelector('.punching-shift-container') || document.body;
                        if (target && typeof MutationObserver !== 'undefined') {
                            var obs = new MutationObserver(function() {
                                applyShiftFormat();
                            });
                            obs.observe(target, { childList: true, subtree: true, characterData: true });
                        }
                    }
                })();

                if (!window._sessionWatchInstalled) {
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
                }
                if (!window._forgotStampHelperInstalled) {
                    window._forgotStampHelperInstalled = true;
                    document.addEventListener('click', function(e) {
                        var btn = e.target && e.target.closest('#forgottenStampButton');
                        if (btn) {
                            setTimeout(function() {
                                var panel = document.getElementById('forgotStampPanel');
                                if (panel) {
                                    var topVal = panel.style.top || '';
                                    if (panel.classList.contains('minimized') || !topVal || topVal === '100%') {
                                        panel.classList.remove('minimized');
                                        panel.classList.add('force-open');
                                        panel.style.top = '0px';
                                    }
                                }
                            }, 350);
                        }
                        var cancelBtn = e.target && e.target.closest('#cancelPunchForgottenButton, #cancelPunchForgottenButtonHeader');
                        if (cancelBtn) {
                            var panel = document.getElementById('forgotStampPanel');
                            if (panel) {
                                panel.classList.remove('force-open');
                                panel.classList.add('minimized');
                                panel.style.top = '100%';
                            }
                        }
                    }, true);
                }

                // === SUORA "LISÄÄ TOIVE TÄLLE PÄIVÄLLE" -OIKOPOLKU KALENTERIPÄIVÄSTÄ ===
                if (window.location.pathname.toLowerCase().indexOf('/calendar/month') !== -1 && !window._quickRequestInstalled) {
                    window._quickRequestInstalled = true;
                    var monthsFi = {
                        'tammikuu': 1, 'helmikuu': 2, 'maaliskuu': 3, 'huhtikuu': 4,
                        'toukokuu': 5, 'kesäkuu': 6, 'heinäkuu': 7, 'elokuu': 8,
                        'syyskuu': 9, 'lokakuu': 10, 'marraskuu': 11, 'joulukuu': 12
                    };
                    document.addEventListener('click', function(e) {
                        if (e.target && e.target.closest('a, button')) return;
                        var cell = e.target && e.target.closest('table.month-table td.month-day');
                        if (!cell || cell.classList.contains('day-different-month')) return;

                        var dayEl = cell.querySelector('.dayNum');
                        var monthHeader = document.getElementById('monthText');
                        if (!dayEl || !monthHeader) return;

                        var dayNum = parseInt((dayEl.textContent || '').trim(), 10);
                        var parts = (monthHeader.textContent || '').trim().toLowerCase().split(/\s+/);
                        if (!dayNum || parts.length < 2) return;

                        var mNum = monthsFi[parts[0]];
                        var yNum = parseInt(parts[1], 10);
                        if (!mNum || !yNum) return;

                        var isoDate = yNum + '-' + String(mNum).padStart(2, '0') + '-' + String(dayNum).padStart(2, '0');
                        var fiDate = String(dayNum).padStart(2, '0') + '.' + String(mNum).padStart(2, '0') + '.' + yNum;

                        var existing = document.getElementById('numeron-quick-req-bar');
                        if (existing) existing.remove();

                        var bar = document.createElement('div');
                        bar.id = 'numeron-quick-req-bar';
                        bar.style.cssText = 'position:fixed;left:12px;right:12px;bottom:14px;z-index:1100;background:#182332;border:1px solid #38BDF8;border-radius:12px;padding:12px 14px;display:flex;justify-content:space-between;align-items:center;box-shadow:0 8px 24px rgba(0,0,0,0.6);';
                        bar.innerHTML = '<span style="color:#F1F5F9;font-size:14px;font-weight:600;">' + fiDate + '</span>' +
                            '<div style="display:flex;gap:8px;">' +
                            '<button id="numeron-qr-close" type="button" style="background:#233040;color:#CBD5E1;border:1px solid #37475A;border-radius:8px;padding:8px 12px;font-size:13px;">Sulje</button>' +
                            '<a href="/PersonRequests/Edit?calendarView=Month&returnValue=' + isoDate + '" style="background:#1982C4;color:#FFFFFF !important;border-radius:8px;padding:8px 14px;font-size:13px;font-weight:600;text-decoration:none;">+ Lisää toive</a>' +
                            '</div>';
                        document.body.appendChild(bar);
                        document.getElementById('numeron-qr-close').onclick = function() { bar.remove(); };
                    }, false);
                }
            })();
        """.trimIndent()
        view?.evaluateJavascript(js, null)
    }

            private fun handleAutoLogin() {
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
                    p.value = '$pass';
                    u.dispatchEvent(new Event('input', { bubbles: true }));
                    p.dispatchEvent(new Event('input', { bubbles: true }));
                    f.submit();
                    return 'SUBMITTED';
                }
                return 'WAITING';
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { res ->
            if (res?.contains("WAITING") == true) {
                webView.postDelayed({ handleAutoLogin() }, 300L)
            }
        }
    }




    private fun handleWebSessionExpired() {
        val now = System.currentTimeMillis()
        if (now - lastSessionRecoveryMs < 3000L) return
        lastSessionRecoveryMs = now

        if (inFlightStampAction == Action.STAMP_IN || inFlightStampAction == Action.STAMP_OUT) {
            pendingAction = inFlightStampAction
            inFlightStampAction = Action.NONE
            Toast.makeText(this, "Istunto vanhentunut – kirjaudutaan uudelleen ja leimataan...", Toast.LENGTH_SHORT).show()
        }

        getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putLong("last_valid_session_ms", 0L)
            .apply()

        val baseUrl = getBaseUrl()
        if (baseUrl.isEmpty()) return

        startSnapshotTransition {
            scope.launch {
                val ok = BackgroundAuthHelper.ensureAuthenticatedSession(this@MainActivity)
                if (ok) {
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                    val targetUrl = resolveResumeUrl(baseUrl)
                    webView.loadUrl(targetUrl)
                } else {
                    webView.loadUrl("$baseUrl/Login/Login")
                }
            }
        }
    }

    private fun handleStampingPage(attempt: Int = 0) {
        if (pendingAction != Action.STAMP_IN && pendingAction != Action.STAMP_OUT) return

        val targetText = if (pendingAction == Action.STAMP_IN) "Sisään" else "Ulos"
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

        webView.evaluateJavascript(js) { rawResult ->
            val unescaped = try {
                if (rawResult != null && rawResult != "null") JSONTokener(rawResult).nextValue() as? String else null
            } catch (_: Exception) {
                null
            }
            val obj = try {
                if (unescaped != null) org.json.JSONObject(unescaped) else null
            } catch (_: Exception) {
                null
            }
            val status = obj?.optString("status", "") ?: ""

            when {
                status == "CLICKED" -> {
                    inFlightStampAction = pendingAction
                    pendingAction = Action.NONE
                    val beforeBtn = obj?.optString("btn", "") ?: ""
                    val beforeRow = obj?.optString("row", "") ?: ""
                    Toast.makeText(this, "Leimataan ($targetText)...", Toast.LENGTH_SHORT).show()
                    verifyStampAndClose(targetText, beforeBtn, beforeRow, 0)
                }
                status == "WRONG_DIRECTION" -> {
                    pendingAction = Action.NONE
                    inFlightStampAction = Action.NONE
                    Toast.makeText(this, "Olet jo leimannut tilaan: $targetText", Toast.LENGTH_LONG).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                }
                status == "NO_BUTTON" && attempt < 10 -> {
                    webView.postDelayed({ handleStampingPage(attempt + 1) }, 300L)
                }
                else -> {
                    pendingAction = Action.NONE
                }
            }
        }
    }

    private fun verifyStampAndClose(
        targetText: String,
        beforeBtn: String,
        beforeRow: String,
        checkAttempt: Int
    ) {
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

        webView.postDelayed({
            if (isFinishing || isDestroyed) return@postDelayed
            webView.evaluateJavascript(verifyJs) { rawResult ->
                val unescaped = try {
                    if (rawResult != null && rawResult != "null") JSONTokener(rawResult).nextValue() as? String else null
                } catch (_: Exception) {
                    null
                }
                val obj = try {
                    if (unescaped != null) org.json.JSONObject(unescaped) else null
                } catch (_: Exception) {
                    null
                }
                val nowBtn = obj?.optString("btn", "") ?: ""
                val nowRow = obj?.optString("row", "") ?: ""
                val sessionExpired = obj?.optBoolean("expired", false) ?: false

                if (sessionExpired) {
                    handleWebSessionExpired()
                    return@evaluateJavascript
                }

                val buttonFlipped = nowBtn.isNotEmpty() && nowBtn != beforeBtn &&
                    nowBtn.lowercase().indexOf(targetLower) == -1
                val rowUpdated = nowRow.isNotEmpty() && nowRow != beforeRow

                if (buttonFlipped || rowUpdated) {
                    inFlightStampAction = Action.NONE
                    CookieManager.getInstance().flush()
                    // Poistettu ylimääräinen Toast, luotetaan visuaaliseen tilaan
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                } else if (checkAttempt < 25) {
                    verifyStampAndClose(targetText, beforeBtn, beforeRow, checkAttempt + 1)
                } else {
                    Toast.makeText(
                        this,
                        "Leimausta ei voitu vahvistaa automaattisesti – tarkista tila ruudulta",
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        }, 300L)
    }

    private fun handleCalendarPage() {
        if (pendingAction != Action.SYNC_CALENDAR) return

        webView.evaluateJavascript("document.documentElement.outerHTML") { rawHtml ->
            if (rawHtml == null || rawHtml == "null") return@evaluateJavascript
            val unescapedHtml = JSONTokener(rawHtml).nextValue() as? String ?: return@evaluateJavascript
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
                    val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                    val syncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
                    val calId = if (syncCalendar) CalendarSyncHelper.getTargetCalendarId(this@MainActivity) else null
                    val allShifts = pagesToParse.flatMap { NumeronParser.parseCalendarHtml(it) }
                    CalendarSyncHelper.saveCachedShifts(this@MainActivity, allShifts)

                    val changes = if (syncCalendar && calId != null) {
                        CalendarSyncHelper.syncShiftsToCalendar(this@MainActivity, calId, allShifts)
                    } else {
                        prefs.edit().putLong("last_calendar_sync_ms", System.currentTimeMillis()).apply()
                        emptyList()
                    }
                    CalendarSyncHelper.scheduleShiftReminders(this@MainActivity, calId)

                    withContext(Dispatchers.Main) {
                        if (syncCalendar && calId == null) {
                            Toast.makeText(
                                this@MainActivity,
                                "Vuorot haettu (${allShifts.size} kpl), mutta kalenteria ei ole valittu",
                                Toast.LENGTH_LONG
                            ).show()
                        } else if (changes.isNotEmpty()) {
                            Toast.makeText(
                                this@MainActivity,
                                "Kalenteria päivitetty: ${CalendarChangeTracker.formatSummary(changes)}",
                                Toast.LENGTH_LONG
                            ).show()
                            CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                        } else {
                            val msg = if (syncCalendar) {
                                "Kalenteri on ajan tasalla (${allShifts.size} vuoroa)"
                            } else {
                                "Työvuorot ja muistutukset päivitetty (${allShifts.size} vuoroa)"
                            }
                            Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                        }
                    }
                }
            }
        }
    }

    override fun onDestroy() {
        try {
            CookieManager.getInstance().flush()
        } catch (_: Exception) {}
        try {
            (webView.parent as? ViewGroup)?.removeView(webView)
            webView.stopLoading()
            webView.destroy()
        } catch (_: Exception) {}
        scope.cancel()
        super.onDestroy()
    }
}
