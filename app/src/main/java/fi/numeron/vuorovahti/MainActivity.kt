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
import kotlinx.coroutines.Job
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
    private var navigateJob: Job? = null
    private var navigationToken: Int = 0
    private var isAutoSubmittingLogin: Boolean = false
    private var lastThemedUrl: String? = null
    private var lastThemedAtMs: Long = 0L

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
        setupBackNavigation()
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
        val isDemo = DemoModeHelper.isDemoEnabled(this)
        val en = DemoModeHelper.isEnglish(this)
        bannerDemoMode.visibility = if (isDemo) View.VISIBLE else View.GONE
        bannerDemoMode.text = if (en) {
            "DEMO MODE ACTIVE – Try stamping, shifts & notifications"
        } else {
            "DEMOTILA AKTIIVINEN – Kokeile leimausta, vuoroja ja ilmoituksia"
        }
        btnNavStamp.text = if (en) "Stamp" else "Leimaus"
        btnNavRequests.text = if (en) "Requests" else "Toiveet"
        btnNavShifts.text = if (en) "Shifts" else "Vuorot"
    }

    private var transitionOverlay: FrameLayout? = null
    private var snapshotView: ImageView? = null
    private var snapshotBitmap: Bitmap? = null
    private var isTransitionActive: Boolean = false
    private val transitionFallbackRunnable = Runnable {
        isAutoSubmittingLogin = false
        endSnapshotTransition()
    }

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
            isClickable = false
            isFocusable = false
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

        val progressBar = ProgressBar(this).apply {
            isIndeterminate = true
            indeterminateTintList = ColorStateList.valueOf(Color.parseColor("#38BDF8"))
        }
        val spinnerParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            gravity = Gravity.CENTER
        }
        overlay.addView(progressBar, spinnerParams)

        rootContent.addView(overlay, FrameLayout.LayoutParams(webView.width, webView.height))
        syncOverlayBoundsToWebView(overlay)
        webView.post { syncOverlayBoundsToWebView(overlay) }
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

    private fun recycleSnapshotBitmap() {
        snapshotView?.setImageDrawable(null)
        snapshotView?.visibility = View.GONE
        try {
            snapshotBitmap?.let {
                if (!it.isRecycled) it.recycle()
            }
        } catch (_: Exception) {}
        snapshotBitmap = null
    }

    private fun startSnapshotTransition(onReady: (() -> Unit)? = null) {
        val overlay = ensureTransitionOverlay()
        overlay.animate().cancel()
        webView.removeCallbacks(transitionFallbackRunnable)
        webView.postDelayed(transitionFallbackRunnable, 6500L)

        if (!isTransitionActive) {
            isTransitionActive = true
            recycleSnapshotBitmap()

            if (webView.width > 0 && webView.height > 0 && webView.alpha > 0.5f) {
                try {
                    val bitmap = Bitmap.createBitmap(webView.width, webView.height, Bitmap.Config.RGB_565)
                    val canvas = Canvas(bitmap)
                    webView.draw(canvas)
                    snapshotBitmap = bitmap
                    snapshotView?.setImageBitmap(bitmap)
                    snapshotView?.visibility = View.VISIBLE
                } catch (_: Exception) {
                    recycleSnapshotBitmap()
                }
            }

            overlay.alpha = 1f
            overlay.visibility = View.VISIBLE
            webView.alpha = 0f
            webView.post { syncOverlayBoundsToWebView(overlay) }

            if (onReady != null) {
                webView.post { onReady() }
            }
        } else {
            onReady?.invoke()
        }
    }

    private fun endSnapshotTransition() {
        webView.removeCallbacks(transitionFallbackRunnable)
        webView.alpha = 1f
        isTransitionActive = false

        val overlay = transitionOverlay ?: return
        overlay.animate().cancel()
        overlay.alpha = 0f
        overlay.visibility = View.GONE
        recycleSnapshotBitmap()
    }

    private fun navigateToTab(tab: Tab) {
        currentTab = tab
        dashboardRedirectCount = 0
        isAutoSubmittingLogin = false
        val token = ++navigationToken
        navigateJob?.cancel()
        updateDemoBanner()

        when (tab) {
            Tab.STAMP -> setActiveTab(btnNavStamp)
            Tab.REQUESTS -> setActiveTab(btnNavRequests)
            Tab.SHIFTS -> setActiveTab(btnNavShifts)
        }

        if (DemoModeHelper.isDemoEnabled(this)) {
            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition
                val html = when (tab) {
                    Tab.STAMP -> DemoModeHelper.getDemoStampingHtml(this)
                    Tab.REQUESTS -> DemoModeHelper.getDemoRequestsHtml(this)
                    Tab.SHIFTS -> DemoModeHelper.getDemoShiftsHtml(this)
                }
                webView.stopLoading()
                webView.loadDataWithBaseURL("https://demo.local/", html, "text/html", "UTF-8", null)
            }
        } else {
            val baseUrl = getBaseUrl()
            if (baseUrl.isEmpty() || (!baseUrl.startsWith("http://") && !baseUrl.startsWith("https://"))) {
                endSnapshotTransition()
                Toast.makeText(
                    this,
                    if (DemoModeHelper.isEnglish(this)) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista",
                    Toast.LENGTH_LONG
                ).show()
                btnNavSettings.performClick()
                return
            }
            val now = LocalDate.now()
            val url = when (tab) {
                Tab.STAMP -> "$baseUrl/WorktimeStamping"
                Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
                Tab.SHIFTS -> "$baseUrl/Calendar/Month?month=${now.monthValue}&year=${now.year}"
            }
            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition
                navigateJob?.cancel()
                val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                val lastSessionMs = prefs.getLong("last_valid_session_ms", 0L)
                val sessionAgeMs = System.currentTimeMillis() - lastSessionMs
                val existingCookies = CookieManager.getInstance().getCookie(baseUrl)
                val isAutoStamping = (pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT)
                val maxSessionAgeMs = if (isAutoStamping) 10L * 60 * 1000L else 25L * 60 * 1000L

                if (existingCookies.isNullOrBlank() || sessionAgeMs > maxSessionAgeMs) {
                    navigateJob = scope.launch {
                        try {
                            val ok = BackgroundAuthHelper.ensureAuthenticatedSession(this@MainActivity)
                            if (ok) {
                                prefs.edit().putLong("last_valid_session_ms", System.currentTimeMillis()).apply()
                            }
                        } catch (_: Exception) {
                        }
                        if (token == navigationToken && !isFinishing && !isDestroyed) {
                            webView.stopLoading()
                            webView.loadUrl(url)
                        }
                    }
                } else {
                    webView.stopLoading()
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
            endSnapshotTransition()
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

    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(
            this,
            object : androidx.activity.OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    if (::webView.isInitialized && webView.canGoBack()) {
                        startSnapshotTransition()
                        webView.goBack()
                    } else {
                        isEnabled = false
                        onBackPressedDispatcher.onBackPressed()
                    }
                }
            }
        )
    }

    private fun triggerTestReminderNotification() {
        val en = DemoModeHelper.isEnglish(this)
        val timeStr = LocalTime.now().plusMinutes(30).format(DateTimeFormatter.ofPattern("HH:mm"))
        ShiftReminderReceiver().showReminderNotification(
            context = this,
            shiftTitle = if (en) "Morning Shift (Test notification)" else "Aamuvuoro (Testi-ilmoitus)",
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
                    if (isFinishing || isDestroyed) return@withContext
                    val en = DemoModeHelper.isEnglish(this@MainActivity)
                    if (syncCalendar && calId == null) {
                        Toast.makeText(
                            this@MainActivity,
                            if (en) "Calendar permission or calendar missing" else "Kalenterioikeus tai kalenteri puuttuu",
                            Toast.LENGTH_LONG
                        ).show()
                    } else if (changes.isNotEmpty()) {
                        Toast.makeText(
                            this@MainActivity,
                            if (en) "Calendar changes: ${CalendarChangeTracker.formatSummary(changes)}" else "Kalenterimuutokset: ${CalendarChangeTracker.formatSummary(changes)}",
                            Toast.LENGTH_LONG
                        ).show()
                        CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                    } else {
                        val msg = if (syncCalendar) {
                            if (en) "Demo shifts are already up to date in calendar" else "Demovuorot ovat jo ajan tasalla kalenterissa"
                        } else {
                            if (en) "Demo shifts and reminders updated (${demoShifts.size} shifts)" else "Demovuorot ja muistutukset päivitetty (${demoShifts.size} vuoroa)"
                        }
                        Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                    }
                }
            }
            return
        }

        val baseUrl = getBaseUrl()
        if (baseUrl.isBlank()) {
            val en = DemoModeHelper.isEnglish(this)
            Toast.makeText(
                this,
                if (en) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista",
                Toast.LENGTH_LONG
            ).show()
            return
        }

        val now = LocalDate.now()
        val nextMonth = now.plusMonths(1)
        val urls = listOf(
            "$baseUrl/Calendar/Month?month=${now.monthValue}&year=${now.year}",
            "$baseUrl/Calendar/Month?month=${nextMonth.monthValue}&year=${nextMonth.year}"
        )

        val enStart = DemoModeHelper.isEnglish(this)
        Toast.makeText(
            this,
            if (enStart) "Syncing shifts..." else "Synkronoidaan työvuoroja...",
            Toast.LENGTH_SHORT
        ).show()

        scope.launch {
            val fetchedPages = BackgroundAuthHelper.fetchAuthenticatedPages(this@MainActivity, urls)
            if (fetchedPages != null && fetchedPages.size == 2) {
                processSyncedCalendarPages(fetchedPages)
            } else {
                pendingAction = Action.SYNC_CALENDAR
                syncStep = 0
                collectedCalendarHtml.clear()
                webView.loadUrl(urls[0])
            }
        }
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
                val en = DemoModeHelper.isEnglish(this)
                val dir = if (en) (if (isEnding) "Out" else "In") else (if (isEnding) "Ulos" else "Sisään")
                val msg = if (en) "Test notification ($dir): No real stamp was performed" else "Testi-ilmoitus ($dir): Oikeaa leimausta ei suoritettu"
                Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
                return
            }

            pendingAction = if (isEnding) Action.STAMP_OUT else Action.STAMP_IN
            val autoMsg = if (DemoModeHelper.isEnglish(this)) "Performing automatic stamp..." else "Suoritetaan automaattinen leimaus..."
            Toast.makeText(this, autoMsg, Toast.LENGTH_SHORT).show()
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

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 101 && grantResults.any { it == PackageManager.PERMISSION_GRANTED }) {
            CalendarSyncHelper.scheduleShiftReminders(this)
            ShiftReminderReceiver.ensureBackgroundSyncScheduled(this)
            val calGranted = ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.READ_CALENDAR
            ) == PackageManager.PERMISSION_GRANTED
            if (calGranted &&
                !DemoModeHelper.isDemoEnabled(this) &&
                !CalendarSyncHelper.hasCachedShifts(this) &&
                getBaseUrl().isNotEmpty()
            ) {
                ShiftReminderReceiver.triggerImmediateSync(this)
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
        webView.webChromeClient = android.webkit.WebChromeClient()

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

                @android.webkit.JavascriptInterface
                fun onSessionExpiringSoon() {
                    runOnUiThread {
                        handleWebSessionExpiringSoon()
                    }
                }
            },
            "SessionBridge"
        )

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)

        webView.webViewClient = object : WebViewClient() {

            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
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
                        (!reqHost.isNullOrBlank() && (reqHost.endsWith(".numeronwfm.com", ignoreCase = true) || reqHost.endsWith(".numeronwfm.fi", ignoreCase = true))) ||
                        (!allowedHost.isNullOrBlank() && reqHost.equals(allowedHost, ignoreCase = true))
                    if (isInternal) {
                        if (request?.isForMainFrame == true &&
                            url.contains("/InfraDashboard", ignoreCase = true) &&
                            dashboardRedirectCount < 2
                        ) {
                            dashboardRedirectCount++
                            startSnapshotTransition()
                            view?.loadUrl(resolveResumeUrl(getBaseUrl()))
                            return true
                        }
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
            }

            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                super.onPageStarted(view, url, favicon)
                lastThemedUrl = null
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
                    injectDarkTheme(view, forceDomInit = false)
                }
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: android.webkit.WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    val code = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) error?.errorCode ?: 0 else 0
                    // -1 = net::ERR_ABORTED (tapahtuu normaalisti kun käyttäjä vaihtaa välilehteä kesken latauksen)
                    if (code == -1 || code == android.webkit.WebViewClient.ERROR_UNKNOWN) return
                    isAutoSubmittingLogin = false
                    endSnapshotTransition()
                    val desc = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) error?.description?.toString().orEmpty() else ""
                    Toast.makeText(this@MainActivity, "Sivun latausvirhe ($code): $desc", Toast.LENGTH_LONG).show()
                }
            }

            override fun onReceivedHttpError(
                view: WebView?,
                request: WebResourceRequest?,
                errorResponse: WebResourceResponse?
            ) {
                super.onReceivedHttpError(view, request, errorResponse)
                if (request?.isForMainFrame == true) {
                    val status = errorResponse?.statusCode ?: 0
                    if (status == 401 || status == 403) {
                        handleWebSessionExpired()
                        return
                    }
                    endSnapshotTransition()
                    if (status >= 400) {
                        Toast.makeText(this@MainActivity, "Palvelinvirhe HTTP $status", Toast.LENGTH_LONG).show()
                    }
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

                injectDarkTheme(view, forceDomInit = true)
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
                    url.contains("/Login/LogOff", ignoreCase = true) -> {
                        isAutoSubmittingLogin = true
                        startSnapshotTransition()
                        webView.loadUrl("${getBaseUrl()}/Login/Login")
                        return
                    }
                    url.contains("/Login/Login", ignoreCase = true) -> {
                        isAutoSubmittingLogin = true
                        startSnapshotTransition()
                        handleAutoLogin()
                        return
                    }
                    url.contains("/InfraDashboard", ignoreCase = true) && dashboardRedirectCount < 2 -> {
                        dashboardRedirectCount++
                        startSnapshotTransition()
                        webView.loadUrl(resolveResumeUrl(getBaseUrl()))
                        return
                    }
                    url.contains("/WorktimeStamping", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        setActiveTab(btnNavStamp)
                        handleStampingPage()
                    }
                    url.contains("/PersonRequests", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        setActiveTab(btnNavRequests)
                    }
                    url.contains("/Calendar", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        setActiveTab(btnNavShifts)
                        handleCalendarPage()
                    }
                    pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> {
                        isAutoSubmittingLogin = false
                        webView.loadUrl("${getBaseUrl()}/WorktimeStamping")
                        return
                    }
                    else -> {
                        isAutoSubmittingLogin = false
                    }
                }

                val revealDelay = if (url.contains("/Calendar", ignoreCase = true)) 280L else 180L
                view?.postDelayed({
                    if (!isAutoSubmittingLogin) {
                        endSnapshotTransition()
                    }
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
                val en = DemoModeHelper.isEnglish(this)
                val stateStr = if (en) (if (wantIn) "In" else "Out") else (if (wantIn) "Sisään" else "Ulos")
                val msg = if (en) "Demo mode: Already clocked $stateStr" else "Demotila: Olet jo leimannut tilaan $stateStr"
                Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
                webView.postDelayed({ finishAndRemoveTask() }, 1200L)
            }
        }
    }

    private fun injectDarkTheme(view: WebView?, forceDomInit: Boolean = false) {
        val currentUrl = view?.url
        val nowMs = System.currentTimeMillis()
        if (!forceDomInit && !currentUrl.isNullOrEmpty() && currentUrl == lastThemedUrl && (nowMs - lastThemedAtMs) < 1500L) {
            return
        }
        lastThemedUrl = currentUrl
        lastThemedAtMs = nowMs

        val themePrefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val morningRgb = themePrefs.getInt("color_morning_rgb", SettingsDialogHelper.DEFAULT_MORNING_RGB)
        val eveningRgb = themePrefs.getInt("color_evening_rgb", SettingsDialogHelper.DEFAULT_EVENING_RGB)
        val nightRgb = themePrefs.getInt("color_night_rgb", SettingsDialogHelper.DEFAULT_NIGHT_RGB)
        fun rgbToHex(rgb: Int): String = String.format("#%06X", 0xFFFFFF and rgb)
        fun contrastFg(rgb: Int): String {
            val lum = 0.299 * Color.red(rgb) + 0.587 * Color.green(rgb) + 0.114 * Color.blue(rgb)
            return if (lum > 150.0) "#0F1722" else "#FFFFFF"
        }
        val morningBg = rgbToHex(morningRgb)
        val morningFg = contrastFg(morningRgb)
        val eveningBg = rgbToHex(eveningRgb)
        val eveningFg = contrastFg(eveningRgb)
        val nightBg = rgbToHex(nightRgb)
        val nightFg = contrastFg(nightRgb)
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
            .container h1:not(#monthText), .container-fluid h1:not(#monthText),
            .container .h1:not(#monthText), .container-fluid .h1:not(#monthText) {
                display: none !important;
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
            #punchButton.vv-punch-in {
                background-color: #15803D !important;
                border-color: #22C55E !important;
                color: #FFFFFF !important;
            }
            #punchButton.vv-punch-out {
                background-color: #B91C1C !important;
                border-color: #F87171 !important;
                color: #FFFFFF !important;
            }
            .vv-stamp-badge {
                display: inline-block !important;
                padding: 2px 10px !important;
                border-radius: 999px !important;
                font-size: 12px !important;
                font-weight: 700 !important;
                letter-spacing: 0.02em !important;
            }
            .vv-stamp-badge.vv-stamp-in {
                background-color: rgba(22, 163, 74, 0.22) !important;
                border: 1px solid rgba(74, 222, 128, 0.45) !important;
                color: #4ADE80 !important;
            }
            .vv-stamp-badge.vv-stamp-out {
                background-color: rgba(220, 38, 38, 0.22) !important;
                border: 1px solid rgba(248, 113, 113, 0.45) !important;
                color: #F87171 !important;
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
            #forgotStampPanel:not(.force-open) {
                display: none !important;
            }
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
            #waitPunch, .fog-of-war-punch, #wait, .container .fog-of-war {
                display: none !important;
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
            #FullDaySwitch::after,
            #SeriesRequestSwitch::after {
                content: "" !important;
                position: absolute !important;
                top: 3px !important;
                left: 4px !important;
                width: 20px !important;
                height: 20px !important;
                border-radius: 50% !important;
                background-color: #F1F5F9 !important;
                transition: left 0.15s ease !important;
            }
            #FullDaySwitch.active::after,
            #SeriesRequestSwitch.active::after {
                left: 28px !important;
            }
            .bootstrap-datetimepicker-widget,
            .bootstrap-datetimepicker-widget.dropdown-menu {
                background-color: #182332 !important;
                color: #F1F5F9 !important;
                border: 1px solid #37475A !important;
            }
            .bootstrap-datetimepicker-widget table td,
            .bootstrap-datetimepicker-widget table th {
                color: #F1F5F9 !important;
                background-color: transparent !important;
            }
            .bootstrap-datetimepicker-widget table td.day:hover,
            .bootstrap-datetimepicker-widget table td.hour:hover,
            .bootstrap-datetimepicker-widget table td.minute:hover,
            .bootstrap-datetimepicker-widget table th:hover {
                background-color: #2A394A !important;
                color: #FFFFFF !important;
            }
            .bootstrap-datetimepicker-widget table td.active,
            .bootstrap-datetimepicker-widget table td.active:hover {
                background-color: #1982C4 !important;
                color: #FFFFFF !important;
            }
            .bootstrap-datetimepicker-widget table td.old,
            .bootstrap-datetimepicker-widget table td.new {
                color: #64748B !important;
            }
            .alert-danger {
                background-color: #3F1D24 !important;
                border-color: #DC2626 !important;
                color: #FEE2E2 !important;
            }
            .alert-warning {
                background-color: #3B2810 !important;
                border-color: #F59E0B !important;
                color: #FEF3C7 !important;
            }
            .alert-success {
                background-color: #0F2E26 !important;
                border-color: #10B981 !important;
                color: #D1FAE5 !important;
            }
            .alert-info {
                background-color: #1E3A5F !important;
                border-color: #38BDF8 !important;
                color: #E0F2FE !important;
            }
            .modal-header .close,
            .alert .close,
            button.close {
                color: #F1F5F9 !important;
                text-shadow: none !important;
                opacity: 0.85 !important;
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
            .month-week-days td:first-child {
                width: 24px !important;
                padding-left: 1px !important;
                padding-right: 1px !important;
                font-size: 10px !important;
                white-space: nowrap !important;
            }
            .month-week-number {
                width: 24px !important;
                background-color: #131C28 !important;
                color: #64748B !important;
                font-size: 10px !important;
                text-align: center !important;
                vertical-align: top !important;
                padding: 6px 1px 0 1px !important;
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
            td.month-day.has-spanning-absence {
                overflow: visible !important;
            }
            td.month-day:not(.has-spanning-absence) {
                overflow: hidden !important;
            }
            .month-item.absence, .month-item.dummy-item {
                display: none !important;
            }
            .month-item.absence.vuorovahti-visible {
                display: block !important;
                position: relative !important;
                z-index: 5 !important;
                box-sizing: border-box !important;
                border-radius: 5px !important;
                padding: 3px 6px !important;
                margin-bottom: 2px !important;
                font-size: 11px !important;
                font-weight: 600 !important;
                line-height: 1.25 !important;
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
                color: #FFFFFF !important;
            }
            .month-item.absence.vuorovahti-visible .itemName {
                display: inline !important;
                color: inherit !important;
                white-space: nowrap !important;
            }
            .month-item.absence.vuorovahti-visible .itemTimes {
                display: none !important;
            }
            .month-item.absence.vuorovahti-vacation {
                background-color: #15803D !important;
                border: 1px solid #22C55E !important;
                color: #FFFFFF !important;
            }
            .month-item.absence.vuorovahti-sick {
                background-color: #B91C1C !important;
                border: 1px solid #F87171 !important;
                color: #FFFFFF !important;
            }
            .month-item.absence.vuorovahti-other {
                background-color: #334155 !important;
                border: 1px solid #64748B !important;
                color: #F1F5F9 !important;
            }
            .month-item.request {
                display: flex !important;
                align-items: center !important;
                gap: 4px !important;
                background-color: #2E1F47 !important;
                border: 1px solid #8B5CF6 !important;
                border-left: 3px solid #A78BFA !important;
                border-radius: 5px !important;
                padding: 2px 5px !important;
                margin-bottom: 2px !important;
                color: #EDE9FE !important;
                font-size: 10.5px !important;
                font-weight: 600 !important;
                line-height: 1.2 !important;
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
            }
            .vv-request-badge {
                display: inline-block !important;
                flex-shrink: 0 !important;
                padding: 1px 4px !important;
                border-radius: 4px !important;
                background-color: rgba(167, 139, 250, 0.22) !important;
                color: #DDD6FE !important;
                font-size: 9px !important;
                font-weight: 700 !important;
                letter-spacing: 0.02em !important;
            }
            .month-day-header {
                display: flex !important;
                align-items: center !important;
                justify-content: space-between !important;
            }
            .month-day-header .hidden {
                display: none !important;
            }
            .month-day-header .circle {
                display: inline-block !important;
                width: 6px !important;
                height: 6px !important;
                min-width: 6px !important;
                border-radius: 50% !important;
                background-color: #F59E0B !important;
                box-shadow: 0 0 0 1px rgba(245, 158, 11, 0.35) !important;
                margin-right: 4px !important;
                flex-shrink: 0 !important;
            }

            /* === 8. KALENTERI: LUETTELONÄKYMÄ (/Calendar/List) === */
            .schedule-content #calendar-content {
                height: calc(100vh - 115px) !important;
                overflow-y: auto !important;
                -webkit-overflow-scrolling: touch !important;
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

        val safeCss = css
            .replace("\r", " ")
            .replace("\n", " ")
            .replace("\\", "\\\\")
            .replace("'", "\\'")
        val js = """
            (function() {
                var style = document.getElementById('custom-dark-theme');
                if (!style) {
                    style = document.createElement('style');
                    style.id = 'custom-dark-theme';
                }
                var targetParent = document.head || document.documentElement;
                if (targetParent && style.parentNode !== targetParent) {
                    targetParent.appendChild(style);
                }
                if (style.textContent !== '$safeCss') {
                    style.textContent = '$safeCss';
                }

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
                        if (/^(ei\s+suunniteltuja\s+töitä|ei\s+(työ)?vuoroa|vapaa|vapaapäivä|arkipyhävapaa|arkipyhä|viikkolepo|viikkovapaa|tasausvapaa|saldovapaa|pekkanen|pekkaspäivä|vuosiloma|sairaus|hoitovapaa|poissaolo)(?=$|[\s,.:;!?()\-–—])/i.test(cleaned)) {
                            return { location: capFirst(cleaned), shiftName: '', role: '' };
                        }

                        var tokens = cleaned.split(/\s+/).filter(function(t) { return t.length > 0; });
                        if (tokens.length === 0) return { location: '', shiftName: '', role: '' };

                        var kShiftIdx = -1;
                        for (var k = 0; k < tokens.length; k++) {
                            if (tokens[k].toLowerCase() === 'k-vuoro') {
                                kShiftIdx = k;
                                break;
                            }
                        }
                        if (kShiftIdx !== -1) {
                            var kLoc = tokens.filter(function(_, idx) { return idx !== kShiftIdx; }).join(' ');
                            return { location: kLoc, shiftName: '', role: 'K-vuoro' };
                        }

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

                        if (existingWp && nameEl.getAttribute('data-formatted-for') === 'v3:' + rawText) {
                            return;
                        }
                        nameEl.setAttribute('data-raw-shift', rawText);
                        nameEl.setAttribute('data-formatted-for', 'v3:' + rawText);

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
                    if (typeof MutationObserver !== 'undefined') {
                        var shiftTarget = document.querySelector('.punching-shift-container');
                        if (shiftTarget && !shiftTarget._vvShiftObs) {
                            shiftTarget._vvShiftObs = true;
                            new MutationObserver(function() {
                                applyShiftFormat();
                            }).observe(shiftTarget, { childList: true, subtree: true, characterData: true });
                        }
                    }
                })();

                // === SISÄÄN / ULOS -LEIMAUKSEN VÄRIKOODAUS ===
                try {
                    (function setupStampingColorCoding() {
                        function applyStampingColors() {
                            var btn = document.getElementById('punchButton');
                            if (btn) {
                                var btnTxt = (btn.innerText || btn.textContent || '').toLowerCase();
                                if (btnTxt.indexOf('ulos') !== -1 || btnTxt.indexOf('out') !== -1) {
                                    btn.classList.remove('vv-punch-in');
                                    btn.classList.add('vv-punch-out');
                                } else if (btnTxt.indexOf('sisään') !== -1 || btnTxt.indexOf('in') !== -1) {
                                    btn.classList.remove('vv-punch-out');
                                    btn.classList.add('vv-punch-in');
                                }
                            }

                            var rows = document.querySelectorAll('#table-latest-stamps tr');
                            for (var i = 0; i < rows.length; i++) {
                                var cells = rows[i].querySelectorAll('td');
                                if (!cells || cells.length === 0) continue;
                                for (var j = 0; j < cells.length; j++) {
                                    var cell = cells[j];
                                    var raw = (cell.textContent || '').replace(/\s+/g, ' ').trim();
                                    var lower = raw.toLowerCase();
                                    if (lower === 'sisään' || lower === 'in' || lower === 'ulos' || lower === 'out') {
                                        var isIn = (lower === 'sisään' || lower === 'in');
                                        var badge = cell.querySelector('.vv-stamp-badge');
                                        if (!badge) {
                                            cell.textContent = '';
                                            badge = document.createElement('span');
                                            badge.className = 'vv-stamp-badge';
                                            cell.appendChild(badge);
                                        }
                                        badge.textContent = raw;
                                        badge.classList.toggle('vv-stamp-in', isIn);
                                        badge.classList.toggle('vv-stamp-out', !isIn);
                                    }
                                }
                            }
                        }

                        window.vvApplyStampingColors = applyStampingColors;
                        applyStampingColors();
                        if (typeof MutationObserver !== 'undefined') {
                            var colorContainers = [
                                document.getElementById('bottomContainer'),
                                document.getElementById('latestStampsContainer'),
                                document.getElementById('table-latest-stamps')
                            ];
                            var colorScheduled = false;
                            var scheduleColor = function() {
                                if (colorScheduled) return;
                                colorScheduled = true;
                                setTimeout(function() {
                                    colorScheduled = false;
                                    applyStampingColors();
                                }, 80);
                            };
                            for (var ci = 0; ci < colorContainers.length; ci++) {
                                var containerEl = colorContainers[ci];
                                if (containerEl && !containerEl._colorObsInstalled) {
                                    containerEl._colorObsInstalled = true;
                                    new MutationObserver(scheduleColor).observe(containerEl, { childList: true, subtree: true });
                                }
                            }
                        }
                    })();
                } catch (_e) {}

                if (!window._sessionWatchInstalled) {
                    window._sessionWatchInstalled = true;
                    function checkSessionModal() {
                        if (window._sessionExpiredHandled) return;
                        var expired = false;
                        var soonModal = null;
                        var candidates = document.querySelectorAll('#session-expired-modal, #sessionExpiredModal, #SessionExpiredModal, #session-expiring-soon-modal, .modal, [role="dialog"]');
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
                            if (m.id === 'session-expiring-soon-modal' || txt.indexOf('istunto päättyy pian') !== -1) {
                                soonModal = m;
                            }
                        }
                        if (expired) {
                            window._sessionExpiredHandled = true;
                            if (window.SessionBridge && typeof window.SessionBridge.onSessionExpired === 'function') {
                                window.SessionBridge.onSessionExpired();
                            } else {
                                window.location.href = '/Login/Login';
                            }
                        } else if (soonModal && !window._sessionExpiringHandled) {
                            window._sessionExpiringHandled = true;
                            try {
                                if (typeof window.HideSessionExpirationSoonNotify === 'function') {
                                    window.HideSessionExpirationSoonNotify();
                                }
                                if (window.jQuery) {
                                    window.jQuery(soonModal).modal('hide');
                                } else {
                                    soonModal.style.display = 'none';
                                }
                            } catch (_err) {}
                            if (window.SessionBridge && typeof window.SessionBridge.onSessionExpiringSoon === 'function') {
                                window.SessionBridge.onSessionExpiringSoon();
                            }
                        }
                    }
                    window._vvCheckSessionModal = checkSessionModal;
                    checkSessionModal();
                }
                if (window._vvCheckSessionModal && document.body && !document.body._vvSessionObs && typeof MutationObserver !== 'undefined') {
                    document.body._vvSessionObs = true;
                    new MutationObserver(window._vvCheckSessionModal).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class'] });
                }
                if (!window._forgotStampHelperInstalled) {
                    window._forgotStampHelperInstalled = true;

                    function getForgotPanel() {
                        return document.getElementById('forgotStampPanel') || document.querySelector('[id*="forgotStampPanel" i], [id*="ForgotStampPanel" i]');
                    }

                    function openForgotPanel() {
                        var panel = getForgotPanel();
                        if (panel) {
                            panel.classList.remove('minimized', 'hidden', 'hide');
                            panel.classList.add('force-open');
                            panel.style.top = '10%';
                            panel.style.display = 'block';
                        }
                        var fog = document.querySelector('.drw-fog-of-war');
                        if (fog) {
                            fog.classList.add('showing');
                            fog.style.display = 'block';
                        }
                    }

                    function closeForgotPanel() {
                        var panel = getForgotPanel();
                        if (panel) {
                            panel.classList.remove('force-open');
                            panel.classList.add('minimized');
                            panel.style.top = '100%';
                            panel.style.display = 'none';
                        }
                        var fog = document.querySelector('.drw-fog-of-war');
                        if (fog) {
                            fog.classList.remove('showing');
                            fog.style.display = 'none';
                        }
                    }

                    function isForgotOpenTrigger(el) {
                        if (!el) return false;
                        if (el.closest('#forgotStampPanel')) return false;
                        if (el.closest('#forgottenStampButton, #punchForgottenButton, [id*="forgotten" i], [id*="ForgotStamp" i]')) return true;
                        var clickable = el.closest('button, a, [role="button"]');
                        if (!clickable) return false;
                        var txt = (clickable.innerText || clickable.textContent || '').toLowerCase();
                        return txt.indexOf('unohtunut leimaus') !== -1 || txt.indexOf('forgotten stamp') !== -1;
                    }

                    function revealHiddenStampRows() {
                        var hiddenRows = document.querySelectorAll('#table-latest-stamps tr.hidden, #table-latest-stamps tr.hide, #table-latest-stamps tr[style*="display: none"], #table-latest-stamps tr[style*="display:none"]');
                        for (var i = 0; i < hiddenRows.length; i++) {
                            hiddenRows[i].classList.remove('hidden', 'hide');
                            hiddenRows[i].style.display = 'table-row';
                        }
                        if (typeof window.vvApplyStampingColors === 'function') {
                            window.vvApplyStampingColors();
                        }
                    }

                    function isShowMoreTrigger(el) {
                        if (!el) return false;
                        var clickable = el.closest('button, a, [role="button"]');
                        if (!clickable) return false;
                        var id = (clickable.id || '').toLowerCase();
                        if (id.indexOf('more') !== -1 || id.indexOf('lisaa') !== -1) return true;
                        var txt = (clickable.innerText || clickable.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
                        return txt === 'näytä lisää' || txt === 'show more' || txt.indexOf('näytä lisää') !== -1 || txt.indexOf('show more') !== -1;
                    }

                    document.addEventListener('click', function(e) {
                        var editRow = e.target && e.target.closest('#table-latest-stamps tbody tr');
                        if (isForgotOpenTrigger(e.target) || editRow) {
                            openForgotPanel();
                            setTimeout(openForgotPanel, 60);
                            setTimeout(openForgotPanel, 250);
                            return;
                        }
                        var cancelBtn = e.target && e.target.closest('#cancelPunchForgottenButton, #cancelPunchForgottenButtonHeader, .drw-fog-of-war');
                        if (cancelBtn) {
                            closeForgotPanel();
                            return;
                        }
                        if (isShowMoreTrigger(e.target)) {
                            revealHiddenStampRows();
                            setTimeout(revealHiddenStampRows, 150);
                            setTimeout(revealHiddenStampRows, 500);
                            setTimeout(revealHiddenStampRows, 1100);
                        }
                    }, true);

                    function watchStampPageDom() {
                        var stampHost = document.getElementById('latestStampsContainer') || document.getElementById('table-latest-stamps');
                        if (stampHost && !stampHost._vvWatched && typeof MutationObserver !== 'undefined') {
                            stampHost._vvWatched = true;
                            var rowsScheduled = false;
                            new MutationObserver(function() {
                                if (rowsScheduled) return;
                                rowsScheduled = true;
                                setTimeout(function() {
                                    rowsScheduled = false;
                                    revealHiddenStampRows();
                                }, 80);
                            }).observe(stampHost, { childList: true, subtree: true });
                        }
                        var forgotPanel = getForgotPanel();
                        if (forgotPanel && !forgotPanel._vvCloseWatched && typeof MutationObserver !== 'undefined') {
                            forgotPanel._vvCloseWatched = true;
                            new MutationObserver(function() {
                                if (forgotPanel.classList.contains('minimized') && forgotPanel.classList.contains('force-open')) {
                                    closeForgotPanel();
                                }
                            }).observe(forgotPanel, { attributes: true, attributeFilter: ['class'] });
                        }
                    }
                    window._vvWatchStampPageDom = watchStampPageDom;
                    watchStampPageDom();
                }
                if (typeof window._vvWatchStampPageDom === 'function') {
                    window._vvWatchStampPageDom();
                }

                // === AJAX- JA FETCH-ISTUNTOVALVONTA LEIMAUSSIVUN HAUILLE ("NÄYTÄ LISÄÄ" YM.) ===
                if (!window._ajaxSessionGuardInstalled) {
                    window._ajaxSessionGuardInstalled = true;
                    function triggerSessionRefreshOnce() {
                        if (window._sessionExpiredHandled) return;
                        window._sessionExpiredHandled = true;
                        if (window.SessionBridge && typeof window.SessionBridge.onSessionExpired === 'function') {
                            window.SessionBridge.onSessionExpired();
                        }
                    }
                    if (window.XMLHttpRequest) {
                        var origOpen = XMLHttpRequest.prototype.open;
                        var origSend = XMLHttpRequest.prototype.send;
                        XMLHttpRequest.prototype.open = function(method, url) {
                            this._vvUrl = url ? String(url) : '';
                            return origOpen.apply(this, arguments);
                        };
                        XMLHttpRequest.prototype.send = function() {
                            this.addEventListener('load', function() {
                                try {
                                    var respUrl = (this.responseURL || '').toLowerCase();
                                    var bodyText = (typeof this.responseText === 'string') ? this.responseText : '';
                                    var redirectedToLogin = respUrl.indexOf('/login') !== -1 || bodyText.indexOf('id="LoginForm"') !== -1;
                                    if (this.status === 401 || this.status === 403 || redirectedToLogin) {
                                        triggerSessionRefreshOnce();
                                    }
                                } catch (_err) {}
                            });
                            return origSend.apply(this, arguments);
                        };
                    }
                    if (typeof window.fetch === 'function') {
                        var origFetch = window.fetch;
                        window.fetch = function() {
                            return origFetch.apply(this, arguments).then(function(response) {
                                try {
                                    var rUrl = (response && response.url ? response.url : '').toLowerCase();
                                    if (response && (response.status === 401 || response.status === 403 || rUrl.indexOf('/login') !== -1)) {
                                        triggerSessionRefreshOnce();
                                    }
                                } catch (_err) {}
                                return response;
                            });
                        };
                    }
                }

                // === KALENTERIN POISSAOLOJEN SIISTINTÄ JA LOMAPALKKIEN YHDISTÄMINEN ===
                (function setupCalendarCleanup() {
                    var ignoreRegex = /^(vapaa|vapaapäivä|arkipyhä|arkipyhävapaa|viikkolepo|viikkovapaa|tasausvapaa|saldovapaa|pekkanen|pekkaspäivä|ei\s+(suunniteltuja\s+töitä|(työ)?vuoroa))(?=$|[\s,.:;!?()\-–—])/i;
                    var sickRegex = /sairaus|hoitovapaa/i;
                    var vacationRegex = /loma|säästövapaa|lomarahavapaa/i;

                    function classifyAbsence(title) {
                        var t = (title || '').replace(/\s+/g, ' ').trim();
                        if (!t || ignoreRegex.test(t)) return 'ignore';
                        if (sickRegex.test(t)) return 'sick';
                        if (vacationRegex.test(t)) return 'vacation';
                        return 'other';
                    }

                    function getAbsenceTitle(el) {
                        var nameEl = el.querySelector('.itemName');
                        var raw = nameEl ? (nameEl.textContent || '') : (el.textContent || '');
                        return raw.replace(/\s+/g, ' ').trim();
                    }

                    function parseDeclaredSpan(el) {
                        var styleAttr = el.getAttribute('style') || '';
                        var m = styleAttr.match(/width\s*:\s*(\d+(?:\.\d+)?)%/i);
                        if (!m) return 1;
                        var pct = parseFloat(m[1]);
                        if (isNaN(pct) || pct <= 120) return 1;
                        return Math.max(1, Math.round(pct / 100));
                    }

                    function cleanMonthTable() {
                        var rows = document.querySelectorAll('table.month-table tr');
                        if (!rows || rows.length === 0) return;

                        for (var r = 0; r < rows.length; r++) {
                            var cells = rows[r].querySelectorAll('td.month-day');
                            if (!cells || cells.length === 0) continue;

                            var hasUnprocessed = false;
                            for (var c0 = 0; c0 < cells.length; c0++) {
                                if (cells[c0].querySelector('.month-item.absence:not([data-vv-done])')) {
                                    hasUnprocessed = true;
                                    break;
                                }
                            }
                            if (!hasUnprocessed) continue;

                            var cellEntries = [];
                            for (var c = 0; c < cells.length; c++) {
                                cells[c].classList.remove('has-spanning-absence');
                                var dummies = cells[c].querySelectorAll('.month-item.dummy-item');
                                for (var d = 0; d < dummies.length; d++) {
                                    dummies[d].style.display = 'none';
                                }
                                var items = cells[c].querySelectorAll('.month-item.absence');
                                var visibleList = [];
                                for (var i = 0; i < items.length; i++) {
                                    var el = items[i];
                                    el.setAttribute('data-vv-done', '1');
                                    var title = getAbsenceTitle(el);
                                    var kind = classifyAbsence(title);
                                    if (kind === 'ignore') {
                                        el.classList.remove('vuorovahti-visible', 'vuorovahti-vacation', 'vuorovahti-sick', 'vuorovahti-other');
                                        el.style.display = 'none';
                                    } else {
                                        visibleList.push({
                                            el: el,
                                            title: title,
                                            kind: kind,
                                            declaredSpan: parseDeclaredSpan(el),
                                            consumed: false
                                        });
                                    }
                                }
                                cellEntries.push(visibleList);
                            }

                            for (var col = 0; col < cells.length; col++) {
                                var list = cellEntries[col];
                                for (var idx = 0; idx < list.length; idx++) {
                                    var entry = list[idx];
                                    if (entry.consumed) continue;
                                    entry.consumed = true;

                                    var maxPossible = cells.length - col;
                                    var span = Math.min(maxPossible, entry.declaredSpan);

                                    var nextCol = col + 1;
                                    while (nextCol < cells.length) {
                                        var nextList = cellEntries[nextCol];
                                        var matchIdx = -1;
                                        for (var n = 0; n < nextList.length; n++) {
                                            if (!nextList[n].consumed && nextList[n].title.toLowerCase() === entry.title.toLowerCase()) {
                                                matchIdx = n;
                                                break;
                                            }
                                        }
                                        if (matchIdx !== -1) {
                                            nextList[matchIdx].consumed = true;
                                            nextList[matchIdx].el.classList.remove('vuorovahti-visible', 'vuorovahti-vacation', 'vuorovahti-sick', 'vuorovahti-other');
                                            nextList[matchIdx].el.style.display = 'none';
                                            if ((nextCol - col + 1) > span) {
                                                span = nextCol - col + 1;
                                            }
                                            nextCol++;
                                        } else {
                                            break;
                                        }
                                    }

                                    for (var k = col + 1; k < col + span; k++) {
                                        var kList = cellEntries[k];
                                        for (var m = 0; m < kList.length; m++) {
                                            if (!kList[m].consumed && kList[m].title.toLowerCase() === entry.title.toLowerCase()) {
                                                kList[m].consumed = true;
                                                kList[m].el.classList.remove('vuorovahti-visible', 'vuorovahti-vacation', 'vuorovahti-sick', 'vuorovahti-other');
                                                kList[m].el.style.display = 'none';
                                            }
                                        }
                                        var firstWork = cells[k].querySelector('.month-item.work');
                                        if (firstWork) {
                                            firstWork.style.marginTop = '23px';
                                        }
                                    }

                                    var targetEl = entry.el;
                                    targetEl.classList.add('vuorovahti-visible');
                                    targetEl.classList.remove('vuorovahti-vacation', 'vuorovahti-sick', 'vuorovahti-other');
                                    if (entry.kind === 'sick') {
                                        targetEl.classList.add('vuorovahti-sick');
                                    } else if (entry.kind === 'vacation') {
                                        targetEl.classList.add('vuorovahti-vacation');
                                    } else {
                                        targetEl.classList.add('vuorovahti-other');
                                    }
                                    targetEl.setAttribute('title', entry.title);

                                    if (span > 1) {
                                        cells[col].classList.add('has-spanning-absence');
                                        targetEl.style.width = 'calc(' + (span * 100) + '% + ' + ((span - 1) * 5) + 'px)';
                                    } else {
                                        targetEl.style.width = '100%';
                                    }
                                }
                            }
                        }
                    }

                    function cleanListView() {
                        var containers = document.querySelectorAll('.schedule-item-container.schedule-item-absence:not([data-vv-done])');
                        for (var i = 0; i < containers.length; i++) {
                            var box = containers[i];
                            box.setAttribute('data-vv-done', '1');
                            var heading = box.querySelector('.schedule-item-description-heading');
                            var title = heading ? (heading.textContent || '').replace(/\s+/g, ' ').trim() : '';
                            var kind = classifyAbsence(title);
                            if (kind === 'ignore') {
                                box.style.display = 'none';
                            } else if (kind === 'sick') {
                                box.style.setProperty('background-color', '#3F1D24', 'important');
                                box.style.setProperty('border-left-color', '#EF4444', 'important');
                            } else if (kind === 'vacation') {
                                box.style.setProperty('background-color', '#122B22', 'important');
                                box.style.setProperty('border-left-color', '#22C55E', 'important');
                            }
                        }
                    }

                    function pickShiftColor(timesText) {
                        var m = (timesText || '').match(/(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})/);
                        if (!m) return null;
                        var sMin = parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
                        var eMin = parseInt(m[3], 10) * 60 + parseInt(m[4], 10);
                        var crossesMidnight = eMin < sMin;
                        if (crossesMidnight || sMin >= 20 * 60 || sMin < 4 * 60) {
                            return { bg: '$nightBg', fg: '$nightFg' };
                        }
                        if (sMin >= 11 * 60 + 30) {
                            return { bg: '$eveningBg', fg: '$eveningFg' };
                        }
                        return { bg: '$morningBg', fg: '$morningFg' };
                    }

                    function colorWorkShifts() {
                        var monthItems = document.querySelectorAll('.month-item.work');
                        for (var i = 0; i < monthItems.length; i++) {
                            var item = monthItems[i];
                            var timesEl = item.querySelector('.itemTimes');
                            var rawTimes = timesEl ? (timesEl.textContent || '') : (item.textContent || '');
                            var col = pickShiftColor(rawTimes);
                            if (col) {
                                item.style.setProperty('background-color', col.bg, 'important');
                                item.style.setProperty('color', col.fg, 'important');
                                if (timesEl) {
                                    timesEl.style.setProperty('color', col.fg, 'important');
                                }
                            }
                        }

                        var listItems = document.querySelectorAll('.schedule-item-container.schedule-item-work');
                        for (var j = 0; j < listItems.length; j++) {
                            var box = listItems[j];
                            var ltEl = box.querySelector('.schedule-item-times');
                            var lCol = pickShiftColor(ltEl ? (ltEl.textContent || '') : '');
                            if (lCol) {
                                box.style.setProperty('border-left-color', lCol.bg, 'important');
                            }
                        }
                    }

                    function runCalendarCleanup() {
                        cleanMonthTable();
                        cleanListView();
                        colorWorkShifts();
                    }

                    runCalendarCleanup();
                    if (!window._calendarCleanupObserver && document.body && typeof MutationObserver !== 'undefined') {
                        window._calendarCleanupObserver = true;
                        var calCleanupTimer = null;
                        var calObs = new MutationObserver(function() {
                            if (calCleanupTimer) clearTimeout(calCleanupTimer);
                            calCleanupTimer = setTimeout(function() { runCalendarCleanup(); }, 80);
                        });
                        calObs.observe(document.body, { childList: true, subtree: true });
                    }
                })();

                // === SUORA "LISÄÄ TOIVE TÄLLE PÄIVÄLLE" -OIKOPOLKU KALENTERIPÄIVÄSTÄ ===
                if (window.location.pathname.toLowerCase().indexOf('/calendar/month') !== -1 && !window._quickRequestInstalled) {
                    window._quickRequestInstalled = true;
                    var monthsFi = {
                        'tammikuu': 1, 'helmikuu': 2, 'maaliskuu': 3, 'huhtikuu': 4,
                        'toukokuu': 5, 'kesäkuu': 6, 'heinäkuu': 7, 'elokuu': 8,
                        'syyskuu': 9, 'lokakuu': 10, 'marraskuu': 11, 'joulukuu': 12,
                        'january': 1, 'february': 2, 'march': 3, 'april': 4,
                        'may': 5, 'june': 6, 'july': 7, 'august': 8,
                        'september': 9, 'october': 10, 'november': 11, 'december': 12,
                        'januari': 1, 'februari': 2, 'mars': 3, 'maj': 5,
                        'juni': 6, 'juli': 7, 'augusti': 8, 'oktober': 10
                    };
                    document.addEventListener('click', function(e) {
                        if (e.target && e.target.closest('a, button, #numeron-quick-req-bar')) return;
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

                        e.preventDefault();
                        e.stopPropagation();
                        if (typeof e.stopImmediatePropagation === 'function') {
                            e.stopImmediatePropagation();
                        }

                        var isoDate = yNum + '-' + String(mNum).padStart(2, '0') + '-' + String(dayNum).padStart(2, '0');
                        var fiDate = String(dayNum).padStart(2, '0') + '.' + String(mNum).padStart(2, '0') + '.' + yNum;
                        var listDate = encodeURIComponent(mNum + '/' + dayNum + '/' + yNum + ' 00:00:00');

                        var existing = document.getElementById('numeron-quick-req-bar');
                        if (existing) existing.remove();

                        var bar = document.createElement('div');
                        bar.id = 'numeron-quick-req-bar';
                        bar.style.cssText = 'position:fixed;left:12px;right:12px;bottom:14px;z-index:1100;background:#182332;border:1px solid #38BDF8;border-radius:12px;padding:12px 14px;display:flex;justify-content:space-between;align-items:center;gap:8px;box-shadow:0 8px 24px rgba(0,0,0,0.6);';
                        bar.innerHTML = '<span style="color:#F1F5F9;font-size:14px;font-weight:600;">' + fiDate + '</span>' +
                            '<div style="display:flex;gap:6px;align-items:center;">' +
                            '<a href="/Calendar/List?date=' + listDate + '" style="background:#233040;color:#E2E8F0 !important;border:1px solid #37475A;border-radius:8px;padding:8px 10px;font-size:13px;font-weight:600;text-decoration:none;">Avaa päivä</a>' +
                            '<a href="/PersonRequests/Edit?calendarView=Month&returnValue=' + isoDate + '" style="background:#1982C4;color:#FFFFFF !important;border-radius:8px;padding:8px 12px;font-size:13px;font-weight:600;text-decoration:none;">+ Toive</a>' +
                            '<button id="numeron-qr-close" type="button" style="background:#233040;color:#CBD5E1;border:1px solid #37475A;border-radius:8px;padding:8px 10px;font-size:13px;">✕</button>' +
                            '</div>';
                        document.body.appendChild(bar);
                        document.getElementById('numeron-qr-close').onclick = function() { bar.remove(); };
                    }, true);
                }
            })();
        """.trimIndent()

        view?.evaluateJavascript(js, null)
    }

            private fun handleAutoLogin(attempt: Int = 0) {
        val rawUser = SecureCredentialManager.getUsername(this) ?: ""
        val rawPass = SecureCredentialManager.getPassword(this) ?: ""
        if (rawUser.isEmpty() || rawPass.isEmpty()) {
            isAutoSubmittingLogin = false
            endSnapshotTransition()
            return
        }
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
                    p.value = $passJson;
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
                if (attempt < 15) { webView.postDelayed({ handleAutoLogin(attempt + 1) }, 300L) }
            }
        }
    }




    private fun handleWebSessionExpiringSoon() {
        val now = System.currentTimeMillis()
        if (now - lastSessionRecoveryMs < 15_000L) return
        lastSessionRecoveryMs = now
        val baseUrl = getBaseUrl()
        if (baseUrl.isEmpty() || DemoModeHelper.isDemoEnabled(this)) return

        scope.launch {
            val ok = BackgroundAuthHelper.ensureAuthenticatedSession(
                this@MainActivity,
                forceRefresh = true
            )
            if (ok) {
                getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                    .edit()
                    .putLong("last_valid_session_ms", System.currentTimeMillis())
                    .apply()
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
            Toast.makeText(this, if (DemoModeHelper.isEnglish(this)) "Session expired – re-authenticating and stamping..." else "Istunto vanhentunut – kirjaudutaan uudelleen ja leimataan...", Toast.LENGTH_SHORT).show()
        }

        getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putLong("last_valid_session_ms", 0L)
            .apply()

        val baseUrl = getBaseUrl()
        if (baseUrl.isEmpty()) return

        startSnapshotTransition {
            scope.launch {
                val ok = BackgroundAuthHelper.ensureAuthenticatedSession(
                    this@MainActivity,
                    forceRefresh = true
                )
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

        val wantIn = (pendingAction == Action.STAMP_IN)
        val targetText = if (wantIn) "Sisään" else "Ulos"

        webView.evaluateJavascript(StampingWebHelper.buildClickStampJs(wantIn)) { rawResult ->
            val obj = StampingWebHelper.parseJsonResult(rawResult)
            val status = obj?.optString("status", "") ?: ""

            when {
                status == "CLICKED" -> {
                    inFlightStampAction = pendingAction
                    pendingAction = Action.NONE
                    val beforeDir = obj?.optString("dir", "") ?: ""
                    val beforeBtn = obj?.optString("btn", "") ?: ""
                    val beforeRow = obj?.optString("row", "") ?: ""
                    val beforeRowId = obj?.optString("rowId", "") ?: ""
                    val en = DemoModeHelper.isEnglish(this)
                    val dirLabel = if (en) (if (wantIn) "In" else "Out") else targetText
                    Toast.makeText(this, if (en) "Stamping ($dirLabel)..." else "Leimataan ($targetText)...", Toast.LENGTH_SHORT).show()
                    verifyStampAndClose(wantIn, beforeDir, beforeBtn, beforeRow, beforeRowId, 0)
                }
                status == "WRONG_DIRECTION" -> {
                    pendingAction = Action.NONE
                    inFlightStampAction = Action.NONE
                    val en = DemoModeHelper.isEnglish(this)
                    val dirLabel = if (en) (if (wantIn) "In" else "Out") else targetText
                    Toast.makeText(this, if (en) "Already clocked $dirLabel" else "Olet jo leimannut tilaan: $targetText", Toast.LENGTH_LONG).show()
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
        wantIn: Boolean,
        beforeDir: String,
        beforeBtn: String,
        beforeRow: String,
        beforeRowId: String,
        checkAttempt: Int
    ) {
        webView.postDelayed({
            if (isFinishing || isDestroyed) return@postDelayed
            webView.evaluateJavascript(StampingWebHelper.buildVerifyStampJs()) { rawResult ->
                val obj = StampingWebHelper.parseJsonResult(rawResult)
                val nowDir = obj?.optString("dir", "") ?: ""
                val nowBtn = obj?.optString("btn", "") ?: ""
                val nowRow = obj?.optString("row", "") ?: ""
                val nowRowId = obj?.optString("rowId", "") ?: ""
                val sessionExpired = obj?.optBoolean("expired", false) ?: false

                if (sessionExpired) {
                    handleWebSessionExpired()
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
                    inFlightStampAction = Action.NONE
                    CookieManager.getInstance().flush()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                } else if (checkAttempt < 25) {
                    verifyStampAndClose(wantIn, beforeDir, beforeBtn, beforeRow, beforeRowId, checkAttempt + 1)
                } else {
                    Toast.makeText(
                        this,
                        if (DemoModeHelper.isEnglish(this)) "Could not verify stamp automatically – please check status on screen" else "Leimausta ei voitu vahvistaa automaattisesti – tarkista tila ruudulta",
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
            val unescapedHtml = try {
                JSONTokener(rawHtml).nextValue() as? String
            } catch (_: Exception) {
                null
            } ?: run {
                pendingAction = Action.NONE
                collectedCalendarHtml.clear()
                return@evaluateJavascript
            }
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
                processSyncedCalendarPages(pagesToParse)
            }
        }
    }

    private fun processSyncedCalendarPages(pagesToParse: List<String>) {
        scope.launch(Dispatchers.IO) {
            val parsedPages = pagesToParse.map { NumeronParser.parseCalendarHtml(it) }
            if (parsedPages.any { it == null }) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(
                        this@MainActivity,
                        if (DemoModeHelper.isEnglish(this@MainActivity)) "Failed to read shifts – calendar was not modified" else "Työvuorojen luku epäonnistui – kalenteria ei muutettu",
                        Toast.LENGTH_LONG
                    ).show()
                }
                return@launch
            }
            val baseUrl = getBaseUrl()
            val cookies = try {
                CookieManager.getInstance().getCookie(baseUrl)
            } catch (_: Exception) {
                null
            }
            val rawShifts = NumeronParser.enrichShiftsWithListComments(
                baseUrl = baseUrl,
                cookieHeader = cookies,
                htmlPages = pagesToParse,
                shifts = parsedPages.filterNotNull().flatten()
            )
            val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val syncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
            val calId = if (syncCalendar) CalendarSyncHelper.getTargetCalendarId(this@MainActivity) else null
            val allShifts = NumeronParser.mergeConsecutiveLeaves(rawShifts)
            CalendarSyncHelper.saveCachedShifts(this@MainActivity, allShifts)

            val changes = if (syncCalendar && calId != null) {
                CalendarSyncHelper.syncShiftsToCalendar(this@MainActivity, calId, allShifts)
            } else {
                prefs.edit().putLong("last_calendar_sync_ms", System.currentTimeMillis()).apply()
                emptyList()
            }
            CalendarSyncHelper.scheduleShiftReminders(this@MainActivity, calId)

            withContext(Dispatchers.Main) {
                if (isFinishing || isDestroyed) return@withContext
                val en = DemoModeHelper.isEnglish(this@MainActivity)
                if (syncCalendar && calId == null) {
                    Toast.makeText(
                        this@MainActivity,
                        if (en) "Shifts fetched (${allShifts.size}), but no calendar is selected" else "Vuorot haettu (${allShifts.size} kpl), mutta kalenteria ei ole valittu",
                        Toast.LENGTH_LONG
                    ).show()
                } else if (changes.isNotEmpty()) {
                    Toast.makeText(
                        this@MainActivity,
                        if (en) "Calendar updated: ${CalendarChangeTracker.formatSummary(changes)}" else "Kalenteria päivitetty: ${CalendarChangeTracker.formatSummary(changes)}",
                        Toast.LENGTH_LONG
                    ).show()
                    CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                } else {
                    val msg = if (syncCalendar) {
                        if (en) "Calendar is up to date (${allShifts.size} shifts)" else "Kalenteri on ajan tasalla (${allShifts.size} vuoroa)"
                    } else {
                        if (en) "Shifts and reminders updated (${allShifts.size} shifts)" else "Työvuorot ja muistutukset päivitetty (${allShifts.size} vuoroa)"
                    }
                    Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    override fun onPause() {
        try {
            webView.onPause()
        } catch (_: Exception) {}
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        try {
            webView.onResume()
        } catch (_: Exception) {}
    }

    override fun onDestroy() {
        navigateJob?.cancel()
        webView.removeCallbacks(transitionFallbackRunnable)
        recycleSnapshotBitmap()
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
