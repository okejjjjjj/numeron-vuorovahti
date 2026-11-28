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

    companion object {
        @Volatile
        private var cachedSafeDarkCss: String? = null

        private val BLOCKED_CSS_PATTERNS = listOf(
            "/content/css/cssvisma",
            "/content/css/login.css",
            "/content/css/calendar.css",
            "/content/css/buttons.css",
            "/bundles/cssworktimestamping",
            "/content/css/worktimestamping.css",
            "/content/css/listlayout.css",
            "fonts.googleapis.com"
        )
    }

    private var webView: WebView? = null
    private lateinit var webViewHost: android.widget.LinearLayout
    private lateinit var webOverlayHeader: android.widget.LinearLayout
    private lateinit var btnWebOverlayBack: Button
    private lateinit var txtWebOverlayTitle: TextView
    private lateinit var webViewSlot: FrameLayout
    private lateinit var nativeStampContainer: FrameLayout
    private lateinit var nativeShiftsContainer: FrameLayout
    private lateinit var nativeRequestsContainer: FrameLayout
    private var nativeStampView: NativeStampView? = null
    private var nativeShiftsView: NativeShiftsView? = null
    private var nativeRequestsView: NativeRequestsView? = null
    private var isWebOverlayOpen: Boolean = false
    private var pendingOverlayUrl: String? = null
    private var pendingOverlayAction: String? = null

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
    private var webLoginAttemptFingerprint: String = ""
    private var lastThemedUrl: String? = null
    private var lastThemedAtMs: Long = 0L

    private var pendingAction: Action = Action.NONE
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

        webViewHost = findViewById(R.id.webViewHost)
        webOverlayHeader = findViewById(R.id.webOverlayHeader)
        btnWebOverlayBack = findViewById(R.id.btnWebOverlayBack)
        txtWebOverlayTitle = findViewById(R.id.txtWebOverlayTitle)
        webViewSlot = findViewById(R.id.webViewSlot)
        nativeStampContainer = findViewById(R.id.nativeStampContainer)
        nativeShiftsContainer = findViewById(R.id.nativeShiftsContainer)
        nativeRequestsContainer = findViewById(R.id.nativeRequestsContainer)

        bannerDemoMode = findViewById(R.id.bannerDemoMode)
        btnNavStamp = findViewById(R.id.btnNavStamp)
        btnNavRequests = findViewById(R.id.btnNavRequests)
        btnNavShifts = findViewById(R.id.btnNavShifts)
        btnNavSettings = findViewById(R.id.btnNavSettings)
        btnNavClose = findViewById(R.id.btnNavClose)

        btnWebOverlayBack.setOnClickListener {
            closeWebOverlay(refreshNative = true)
        }

        setupBottomBar()
        setupBackNavigation()
        handleIncomingIntent(intent)

        if (intent?.getBooleanExtra("OPEN_REQUESTS", false) == true) {
            intent.removeExtra("OPEN_REQUESTS")
            navigateToTab(Tab.REQUESTS)
        } else {
            navigateToTab(Tab.STAMP)
        }

        if (intent?.getBooleanExtra("OPEN_CALENDAR_CHANGES", false) == true) {
            intent.removeExtra("OPEN_CALENDAR_CHANGES")
            CalendarChangeTracker.showManageChangesDialog(this)
        }

        scope.launch(Dispatchers.IO) {
            SecureCredentialManager.getUsername(this@MainActivity)
            kotlinx.coroutines.delay(1500L)
            if (!isFinishing && !isDestroyed) {
                ShiftReminderReceiver.ensureBackgroundSyncScheduled(this@MainActivity)
                CalendarSyncHelper.scheduleShiftReminders(this@MainActivity)
            }
        }
    }


    private fun resolveResumeUrl(baseUrl: String): String {
        val overlayUrl = pendingOverlayUrl
        return when {
            isWebOverlayOpen && !overlayUrl.isNullOrBlank() -> overlayUrl
            pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> "$baseUrl/WorktimeStamping"
            pendingAction == Action.SYNC_CALENDAR -> "$baseUrl/Calendar/Month"
            currentTab == Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
            currentTab == Tab.SHIFTS -> "$baseUrl/Calendar/Month"
            else -> "$baseUrl/WorktimeStamping"
        }
    }

    private fun ensureWebView(): WebView {
        webView?.let { return it }
        val wv = WebView(this)
        webViewSlot.removeAllViews()
        webViewSlot.addView(
            wv,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        webView = wv
        setupWebView(wv)
        return wv
    }

    private fun ensureNativeStampView(): NativeStampView {
        nativeStampView?.let { return it }
        val v = NativeStampView(
            context = this,
            scope = scope,
            onOpenForgottenStampWeb = {
                val baseUrl = getBaseUrl()
                val en = DemoModeHelper.isEnglish(this)
                if (baseUrl.isNotBlank()) {
                    openWebOverlayUrl(
                        url = "$baseUrl/WorktimeStamping",
                        title = if (en) "Missing stamp" else "Puuttuva leimaus",
                        overlayAction = "FORGOTTEN"
                    )
                }
            },
            onOpenEditStampWeb = { rowId ->
                val baseUrl = getBaseUrl()
                val en = DemoModeHelper.isEnglish(this)
                if (baseUrl.isNotBlank()) {
                    openWebOverlayUrl(
                        url = "$baseUrl/WorktimeStamping",
                        title = if (en) "Edit stamp" else "Muokkaa leimausta",
                        overlayAction = "EDIT:$rowId"
                    )
                }
            },
            onOpenSettings = { btnNavSettings.performClick() }
        )
        nativeStampContainer.removeAllViews()
        nativeStampContainer.addView(
            v,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        nativeStampView = v
        return v
    }

    private fun ensureNativeShiftsView(): NativeShiftsView {
        nativeShiftsView?.let { return it }
        val v = NativeShiftsView(
            context = this,
            scope = scope,
            onOpenWebUrl = { url, title -> openWebOverlayUrl(url, title) }
        )
        nativeShiftsContainer.removeAllViews()
        nativeShiftsContainer.addView(
            v,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        nativeShiftsView = v
        return v
    }

    private fun ensureNativeRequestsView(): NativeRequestsView {
        nativeRequestsView?.let { return it }
        val v = NativeRequestsView(
            context = this,
            scope = scope,
            onOpenWebUrl = { url, title -> openWebOverlayUrl(url, title) }
        )
        nativeRequestsContainer.removeAllViews()
        nativeRequestsContainer.addView(
            v,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        nativeRequestsView = v
        return v
    }

    private fun openWebOverlayUrl(url: String, title: String, overlayAction: String? = null) {
        val baseUrl = getBaseUrl()
        val en = DemoModeHelper.isEnglish(this)
        if (baseUrl.isBlank()) {
            Toast.makeText(
                this,
                if (en) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista",
                Toast.LENGTH_LONG
            ).show()
            return
        }
        isWebOverlayOpen = true
        pendingOverlayUrl = url
        pendingOverlayAction = overlayAction
        dashboardRedirectCount = 0
        isAutoSubmittingLogin = false
        val token = ++navigationToken
        navigateJob?.cancel()

        btnWebOverlayBack.text = if (en) "← Back" else "← Takaisin"
        txtWebOverlayTitle.text = title
        webOverlayHeader.visibility = View.VISIBLE
        nativeStampContainer.visibility = View.GONE
        nativeShiftsContainer.visibility = View.GONE
        nativeRequestsContainer.visibility = View.GONE
        webViewHost.visibility = View.VISIBLE

        val wv = ensureWebView()
        startSnapshotTransition {
            if (token != navigationToken) return@startSnapshotTransition
            if (!NumeronApiClient.isSessionLikelyValid(this, baseUrl, isAutoStamping = false)) {
                navigateJob = scope.launch {
                    try {
                        BackgroundAuthHelper.ensureAuthenticatedSession(this@MainActivity)
                    } catch (_: Exception) {
                    }
                    if (token == navigationToken && isWebOverlayOpen && !isFinishing && !isDestroyed) {
                        SessionCookieStore.syncToWebViewCookieManager(this@MainActivity, baseUrl)
                        wv.stopLoading()
                        wv.loadUrl(url)
                    }
                }
            } else {
                SessionCookieStore.syncToWebViewCookieManager(this, baseUrl)
                wv.stopLoading()
                wv.loadUrl(url)
            }
        }
    }

    private fun closeWebOverlay(refreshNative: Boolean) {
        isWebOverlayOpen = false
        pendingOverlayUrl = null
        pendingOverlayAction = null
        isAutoSubmittingLogin = false
        endSnapshotTransition()
        webOverlayHeader.visibility = View.GONE
        if (webView != null) {
            SessionCookieStore.importFromWebViewCookieManager(this, getBaseUrl())
        }
        webView?.stopLoading()
        webViewHost.visibility = View.GONE

        when (currentTab) {
            Tab.STAMP -> {
                nativeShiftsContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.GONE
                nativeStampContainer.visibility = View.VISIBLE
                if (refreshNative) {
                    ensureNativeStampView().refreshFromNetwork()
                }
            }
            Tab.SHIFTS -> {
                nativeStampContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.GONE
                nativeShiftsContainer.visibility = View.VISIBLE
                if (refreshNative) {
                    ensureNativeShiftsView().refreshFromCacheAndNetwork()
                }
            }
            Tab.REQUESTS -> {
                nativeStampContainer.visibility = View.GONE
                nativeShiftsContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.VISIBLE
                if (refreshNative) {
                    ensureNativeRequestsView().refreshAfterWebEdit()
                }
            }
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

        rootContent.addView(overlay, FrameLayout.LayoutParams(webViewSlot.width, webViewSlot.height))
        syncOverlayBoundsToWebView(overlay)
        webViewSlot.post { syncOverlayBoundsToWebView(overlay) }
        transitionOverlay = overlay
        return overlay
    }

    private fun syncOverlayBoundsToWebView(overlay: FrameLayout) {
        if (webViewSlot.width <= 0 || webViewSlot.height <= 0) return
        val rootContent = findViewById<View>(android.R.id.content)
        val webLoc = IntArray(2)
        val rootLoc = IntArray(2)
        webViewSlot.getLocationInWindow(webLoc)
        rootContent.getLocationInWindow(rootLoc)

        val lp = overlay.layoutParams as FrameLayout.LayoutParams
        lp.width = webViewSlot.width
        lp.height = webViewSlot.height
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
        webViewSlot.removeCallbacks(transitionFallbackRunnable)
        webViewSlot.postDelayed(transitionFallbackRunnable, 6500L)

        val wv = webView
        if (!isTransitionActive) {
            isTransitionActive = true
            recycleSnapshotBitmap()

            if (wv != null && wv.width > 0 && wv.height > 0 && wv.alpha > 0.5f && webViewHost.visibility == View.VISIBLE) {
                try {
                    val bitmap = Bitmap.createBitmap(wv.width, wv.height, Bitmap.Config.RGB_565)
                    val canvas = Canvas(bitmap)
                    wv.draw(canvas)
                    snapshotBitmap = bitmap
                    snapshotView?.setImageBitmap(bitmap)
                    snapshotView?.visibility = View.VISIBLE
                } catch (_: Exception) {
                    recycleSnapshotBitmap()
                }
            }

            overlay.alpha = 1f
            overlay.visibility = View.VISIBLE
            wv?.alpha = 0f
            webViewSlot.post { syncOverlayBoundsToWebView(overlay) }

            if (onReady != null) {
                webViewSlot.post { onReady() }
            }
        } else {
            onReady?.invoke()
        }
    }

    private fun endSnapshotTransition() {
        webViewSlot.removeCallbacks(transitionFallbackRunnable)
        webView?.alpha = 1f
        isTransitionActive = false

        val overlay = transitionOverlay ?: return
        overlay.animate().cancel()
        overlay.alpha = 0f
        overlay.visibility = View.GONE
        recycleSnapshotBitmap()
    }

    private fun navigateToTab(tab: Tab) {
        currentTab = tab
        isWebOverlayOpen = false
        pendingOverlayUrl = null
        pendingOverlayAction = null
        dashboardRedirectCount = 0
        isAutoSubmittingLogin = false
        navigationToken++
        navigateJob?.cancel()
        updateDemoBanner()

        when (tab) {
            Tab.STAMP -> setActiveTab(btnNavStamp)
            Tab.REQUESTS -> setActiveTab(btnNavRequests)
            Tab.SHIFTS -> setActiveTab(btnNavShifts)
        }

        endSnapshotTransition()
        webView?.stopLoading()
        webOverlayHeader.visibility = View.GONE
        webViewHost.visibility = View.GONE

        when (tab) {
            Tab.STAMP -> {
                nativeShiftsContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.GONE
                nativeStampContainer.visibility = View.VISIBLE
                val stampView = ensureNativeStampView()
                if (pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT) {
                    val wantIn = (pendingAction == Action.STAMP_IN)
                    pendingAction = Action.NONE
                    stampView.performAutoStamp(wantIn) {
                        if (!isFinishing && !isDestroyed) finishAndRemoveTask()
                    }
                } else {
                    stampView.onShow(forceNetwork = false)
                }
            }
            Tab.SHIFTS -> {
                nativeStampContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.GONE
                nativeShiftsContainer.visibility = View.VISIBLE
                ensureNativeShiftsView().onShow(forceNetwork = false)
            }
            Tab.REQUESTS -> {
                nativeStampContainer.visibility = View.GONE
                nativeShiftsContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.VISIBLE
                ensureNativeRequestsView().onShow(forceNetwork = false)
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
                    if (isWebOverlayOpen) {
                        closeWebOverlay(refreshNative = true)
                        return
                    }
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
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
        if (BackgroundAuthHelper.isCredentialBlocked(this)) {
            val en = DemoModeHelper.isEnglish(this)
            Toast.makeText(
                this,
                if (en) "Login failed – please check username and password in Settings" else "Kirjautuminen epäonnistui – tarkista käyttäjätunnus ja salasana asetuksista",
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
                SessionCookieStore.syncToWebViewCookieManager(this@MainActivity, baseUrl)
                ensureWebView().loadUrl(urls[0])
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
    private fun setupWebView(wv: WebView) {
        wv.setBackgroundColor(Color.parseColor("#0F1722"))
        (wv.parent as? View)?.setBackgroundColor(Color.parseColor("#0F1722"))

        wv.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            userAgentString = WebSettings.getDefaultUserAgent(this@MainActivity)
        }
        wv.webChromeClient = android.webkit.WebChromeClient()

        wv.addJavascriptInterface(
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
        CookieManager.getInstance().setAcceptThirdPartyCookies(wv, true)

        wv.webViewClient = object : WebViewClient() {

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
                    val isInternal = (!reqHost.isNullOrBlank() && (reqHost.endsWith(".numeronwfm.com", ignoreCase = true) || reqHost.endsWith(".numeronwfm.fi", ignoreCase = true))) ||
                        (!allowedHost.isNullOrBlank() && reqHost.equals(allowedHost, ignoreCase = true))
                    if (isInternal) {
                        if (request?.isForMainFrame == true &&
                            isWebOverlayOpen &&
                            pendingAction != Action.SYNC_CALENDAR &&
                            (url.contains("/PersonRequests/List", ignoreCase = true) ||
                                url.contains("/Calendar/Month", ignoreCase = true))
                        ) {
                            closeWebOverlay(refreshNative = true)
                            return true
                        }
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
                    if (request?.isForMainFrame == true) {
                        try {
                            startActivity(Intent(Intent.ACTION_VIEW, uri))
                        } catch (_: Exception) {
                        }
                        return true
                    }
                    return false
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

                if (url.contains("amplitude") || url.contains("eligibility.")) {
                    return WebResourceResponse(
                        "application/javascript",
                        "UTF-8",
                        ByteArrayInputStream(ByteArray(0))
                    )
                }

                if (BLOCKED_CSS_PATTERNS.any { url.contains(it) }) {
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
                if (url != null) {
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

                if (isWebOverlayOpen &&
                    pendingAction != Action.SYNC_CALENDAR &&
                    (url.contains("/PersonRequests/List", ignoreCase = true) ||
                        url.contains("/Calendar/Month", ignoreCase = true))
                ) {
                    closeWebOverlay(refreshNative = true)
                    return
                }

                injectDarkTheme(view, forceDomInit = true)
                if (url.contains("/Login/", ignoreCase = true) ||
                    url.contains("/WorktimeStamping", ignoreCase = true) ||
                    isAutoSubmittingLogin
                ) {
                    CookieManager.getInstance().flush()
                }
                if (!url.contains("/Login/", ignoreCase = true) && !url.contains("/InfraDashboard", ignoreCase = true)) {
                    dashboardRedirectCount = 0
                }
                if (!url.contains("/Login/", ignoreCase = true)) {
                    SessionCookieStore.importFromWebViewCookieManager(this@MainActivity, getBaseUrl())
                    webLoginAttemptFingerprint = ""
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                }

                when {
                    url.contains("/Login/LogOff", ignoreCase = true) -> {
                        isAutoSubmittingLogin = true
                        startSnapshotTransition()
                        wv.loadUrl("${getBaseUrl()}/Login/Login")
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
                        wv.loadUrl(resolveResumeUrl(getBaseUrl()))
                        return
                    }
                    url.contains("/WorktimeStamping", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        if (!isWebOverlayOpen) setActiveTab(btnNavStamp)
                        val action = pendingOverlayAction
                        if (isWebOverlayOpen && action != null) {
                            pendingOverlayAction = null
                            view?.postDelayed({
                                if (action == "FORGOTTEN") {
                                    view.evaluateJavascript(
                                        "(function(){ try { if (typeof window.reloadForgottenStampPane === 'function') window.reloadForgottenStampPane(); if (typeof window.openForgottenStampPane === 'function') window.openForgottenStampPane(); if (typeof window._vvOpenForgotPanel === 'function') window._vvOpenForgotPanel(); var b = document.getElementById('forgottenStampButton'); if (b) b.click(); } catch(e){} })();",
                                        null
                                    )
                                } else if (action.startsWith("EDIT:")) {
                                    val rowId = action.removePrefix("EDIT:").filter { it.isDigit() }
                                    if (rowId.isNotEmpty()) {
                                        view.evaluateJavascript(
                                            "(function(){ try { if (typeof window.getStampEditModal === 'function') window.getStampEditModal($rowId); } catch(e){} })();",
                                            null
                                        )
                                    }
                                }
                            }, 250L)
                        }
                    }
                    url.contains("/PersonRequests", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        if (!isWebOverlayOpen) setActiveTab(btnNavRequests)
                    }
                    url.contains("/Calendar", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        if (!isWebOverlayOpen) setActiveTab(btnNavShifts)
                        handleCalendarPage()
                    }
                    pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> {
                        isAutoSubmittingLogin = false
                        wv.loadUrl("${getBaseUrl()}/WorktimeStamping")
                        return
                    }
                    else -> {
                        isAutoSubmittingLogin = false
                    }
                }

                val revealDelay = if (url.contains("/Calendar", ignoreCase = true)) 120L else 60L
                view?.postDelayed({
                    if (!isAutoSubmittingLogin) {
                        endSnapshotTransition()
                    }
                }, revealDelay)
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
        val morningBg = rgbToHex(morningRgb)
        val eveningBg = rgbToHex(eveningRgb)
        val nightBg = rgbToHex(nightRgb)
        val colorCacheKey = "$morningBg|$eveningBg|$nightBg"

        val safeCss = cachedSafeDarkCss ?: """
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
            .container h1, .container-fluid h1, .container .h1, .container-fluid .h1 {
                display: none !important;
            }
            label, span, p, div { color: inherit; }
            a { color: #38BDF8 !important; }
            hr { border-top: 1px solid #2A394A !important; }

            /* === 2. KORTIT, SYÖTTÖKENTÄT, PAINIKKEET JA MODAALIT === */
            .panel, .panel-default, .whitebox, .card, .box, .panel-footer, .form-actions {
                background-color: #182332 !important;
                border: 1px solid #2A394A !important;
                border-radius: 12px !important;
                color: #F1F5F9 !important;
                box-shadow: none !important;
                margin-bottom: 14px !important;
            }
            .panel-body { padding: 14px !important; }
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
            input::placeholder, textarea::placeholder { color: #64748B !important; }
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
            .dropdown-header { color: #94A3B8 !important; }
            .alert-danger { background-color: #3F1D24 !important; border-color: #DC2626 !important; color: #FEE2E2 !important; }
            .alert-warning { background-color: #3B2810 !important; border-color: #F59E0B !important; color: #FEF3C7 !important; }
            .alert-success { background-color: #0F2E26 !important; border-color: #10B981 !important; color: #D1FAE5 !important; }
            .alert-info { background-color: #1E3A5F !important; border-color: #38BDF8 !important; color: #E0F2FE !important; }
            .modal-header .close, .alert .close, button.close {
                color: #F1F5F9 !important;
                text-shadow: none !important;
                opacity: 0.85 !important;
            }

            /* === 3. KIRJAUTUMISSIVU (/Login/Login) === */
            .content { padding: 16px !important; float: none !important; margin: 0 auto !important; }
            .blurbox h1 {
                display: block !important;
                text-align: center !important;
                font-size: 28px !important;
                font-weight: 700 !important;
                margin: 28px 0 20px 0 !important;
                color: #F1F5F9 !important;
            }
            .whitebox { padding: 20px !important; margin: 0 auto !important; }
            .whitebox img, .whitebox hr { display: none !important; }
            #LoginForm .form-group { margin-bottom: 14px !important; }
            #LoginForm .pull-left, #LoginForm .pull-right { margin-bottom: 12px !important; font-size: 13px !important; }
            #LoginForm input[type="submit"] { margin-top: 8px !important; padding: 12px !important; font-size: 16px !important; }

            /* === 4. PUUTTUVA / MUOKATTAVA LEIMAUS (#forgotStampPanel & KENDO PICKER) === */
            .forgotten-stamp-labels {
                color: #CBD5E1 !important;
                font-size: 13px !important;
                margin-top: 10px !important;
                margin-bottom: 4px !important;
            }
            #dropdownMenu2, #dropdownMenuStampDirection {
                width: 100% !important;
                display: flex !important;
                justify-content: space-between !important;
                align-items: center !important;
                background-color: #111923 !important;
            }
            #forgotStampPanel:not(.force-open) { display: none !important; }
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
                inset: 0 !important;
                background-color: rgba(0, 0, 0, 0.65) !important;
                z-index: 1040 !important;
            }
            #waitPunch, .fog-of-war-punch, #wait, .container .fog-of-war { display: none !important; }
            .k-widget, .k-dropdown-wrap, .k-picker-wrap, .k-numeric-wrap, .k-select, .k-input,
            .k-picker, .k-dropdownlist, .k-input-inner, .k-input-value-text {
                background-color: #111923 !important;
                color: #F1F5F9 !important;
                border-color: #37475A !important;
            }
            .k-input-button {
                background-color: #233040 !important;
                color: #F1F5F9 !important;
                border-left: 1px solid #37475A !important;
            }
            .k-list-container, .k-list, .k-animation-container, .k-popup, .k-list-ul, .k-calendar, .k-time-list-wrapper {
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

            /* === 5. TOIVEEN LISÄYS JA MUOKKAUS (/PersonRequests/Edit) === */
            .select2-container { width: 100% !important; }
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
            .select2-container--default .select2-selection--single .select2-selection__placeholder { color: #64748B !important; }
            .select2-container--default .select2-selection--single .select2-selection__arrow { height: 38px !important; right: 8px !important; }
            .select2-container--default .select2-selection--single .select2-selection__arrow b { border-color: #94A3B8 transparent transparent transparent !important; }
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
            .select2-results__option { background-color: #182332 !important; color: #F1F5F9 !important; padding: 10px 12px !important; }
            .select2-container--default .select2-results__option--highlighted[aria-selected],
            .select2-container--default .select2-results__option--highlighted { background-color: #1982C4 !important; color: #FFFFFF !important; }
            .select2-container--default .select2-results__option[aria-selected="true"] { background-color: #233040 !important; color: #38BDF8 !important; }
            #FullDaySwitch, #SeriesRequestSwitch {
                min-width: 54px !important;
                height: 28px !important;
                border-radius: 14px !important;
                position: relative !important;
            }
            #FullDaySwitch:not(.active), #SeriesRequestSwitch:not(.active) { background-color: #233040 !important; border-color: #475569 !important; }
            #FullDaySwitch.active, #SeriesRequestSwitch.active { background-color: #1982C4 !important; border-color: #38BDF8 !important; }
            #FullDaySwitch::after, #SeriesRequestSwitch::after {
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
            #FullDaySwitch.active::after, #SeriesRequestSwitch.active::after { left: 28px !important; }
            .bootstrap-datetimepicker-widget, .bootstrap-datetimepicker-widget.dropdown-menu {
                background-color: #182332 !important;
                color: #F1F5F9 !important;
                border: 1px solid #37475A !important;
            }
            .bootstrap-datetimepicker-widget table td, .bootstrap-datetimepicker-widget table th {
                color: #F1F5F9 !important;
                background-color: transparent !important;
            }
            .bootstrap-datetimepicker-widget table td.day:hover,
            .bootstrap-datetimepicker-widget table td.hour:hover,
            .bootstrap-datetimepicker-widget table td.minute:hover,
            .bootstrap-datetimepicker-widget table th:hover { background-color: #2A394A !important; color: #FFFFFF !important; }
            .bootstrap-datetimepicker-widget table td.active,
            .bootstrap-datetimepicker-widget table td.active:hover { background-color: #1982C4 !important; color: #FFFFFF !important; }
            .bootstrap-datetimepicker-widget table td.old,
            .bootstrap-datetimepicker-widget table td.new { color: #64748B !important; }
            .input-group-addon {
                background-color: #233040 !important;
                border: 1px solid #37475A !important;
                color: #38BDF8 !important;
                border-radius: 0 8px 8px 0 !important;
            }
            .vismaicon-datepicker::before { content: "📅" !important; font-style: normal !important; }
            .vismaicon-time::before { content: "🕒" !important; font-style: normal !important; }
            .editPageContainer table { width: 100% !important; }
            .editPageContainer td { padding-right: 6px !important; }
            #InfoTextArea { width: 100% !important; }
            .FooterPanel { display: flex !important; flex-direction: column !important; gap: 8px !important; }
            .FooterPanel .SubmitButton:not(.hidden) { width: 100% !important; margin: 0 !important; padding: 12px !important; }

            /* === 6. KALENTERIN PÄIVÄLUETTELO (/Calendar/List) === */
            .schedule-content #calendar-content {
                height: calc(100vh - 115px) !important;
                overflow-y: auto !important;
                -webkit-overflow-scrolling: touch !important;
            }
            .schedule-week-separator { margin: 14px 0 8px 0 !important; padding: 4px 2px !important; border-bottom: 1px solid #2A394A !important; }
            .schedule-week-separator-text { color: #38BDF8 !important; font-size: 13px !important; font-weight: 700 !important; text-transform: uppercase !important; letter-spacing: 0.05em !important; }
            .schedule-day-container { background-color: #182332 !important; border: 1px solid #2A394A !important; border-radius: 12px !important; padding: 12px !important; margin-bottom: 10px !important; }
            .schedule-day-information { display: flex !important; align-items: center !important; margin-bottom: 8px !important; padding-bottom: 6px !important; border-bottom: 1px solid #233040 !important; }
            .schedule-day { color: #94A3B8 !important; font-size: 12px !important; font-weight: 700 !important; letter-spacing: 0.04em !important; }
            .schedule-day-date { color: #F1F5F9 !important; font-size: 14px !important; font-weight: 700 !important; }
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
            .schedule-item-container.schedule-item-absence { border-left-color: #F59E0B !important; }
            .schedule-item-container.schedule-item-request { border-left-color: #8B5CF6 !important; }
            .schedule-item-container.schedule-item-opportunity { border-left-color: #10B981 !important; }
            .schedule-item-color-bar, .schedule-item-icon-td, .clear-float { display: none !important; }
            .schedule-item-content { width: 100% !important; }
            .schedule-item-body { display: flex !important; flex-direction: column !important; gap: 4px !important; }
            .schedule-item-times { color: #38BDF8 !important; font-size: 15px !important; font-weight: 700 !important; }
            .schedule-item-description-table { width: 100% !important; }
            .schedule-item-description-heading { color: #F1F5F9 !important; font-size: 14px !important; font-weight: 600 !important; }
            .schedule-item-description-subheading { color: #94A3B8 !important; font-size: 12px !important; margin-top: 2px !important; }
            .schedule-day-content > div[style*="max-height"] { max-height: none !important; margin-top: 6px !important; }
            .schedule-add-button { display: inline-block !important; color: #38BDF8 !important; font-size: 13px !important; font-weight: 600 !important; padding: 4px 0 !important; cursor: pointer !important; }
            .schedule-add-options { margin-top: 6px !important; display: flex !important; gap: 8px !important; }
            .schedule-option-link { background-color: #233040 !important; border: 1px solid #37475A !important; border-radius: 6px !important; padding: 6px 10px !important; font-size: 13px !important; text-decoration: none !important; }
            .mobileAddDiv { display: flex !important; justify-content: space-between !important; align-items: center !important; margin-top: 10px !important; padding: 4px 0 !important; }
            .mobileAddButton, .filterButton {
                background-color: #233040 !important;
                color: #F1F5F9 !important;
                border: 1px solid #37475A !important;
                border-radius: 8px !important;
                padding: 8px 14px !important;
                text-decoration: none !important;
                display: inline-block !important;
            }
            #mobileViewDropdown { margin-top: 8px !important; }
        """.trimIndent()
            .replace("\r", " ")
            .replace("\n", " ")
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .also { cachedSafeDarkCss = it }

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
                if (style.getAttribute('data-vv-colors') !== '$colorCacheKey' || !style.textContent) {
                    style.setAttribute('data-vv-colors', '$colorCacheKey');
                    style.textContent = '$safeCss';
                }

                // === ISTUNNON VANHENEMISEN VALVONTA ===
                if (!window._sessionWatchInstalled) {
                    window._sessionWatchInstalled = true;
                    function checkSessionModal() {
                        if (window._sessionExpiredHandled) return;
                        var expired = false;
                        var soonModal = null;
                        var candidates = document.querySelectorAll('#session-expired-modal, #sessionExpiredModal, #SessionExpiredModal, #session-expiring-soon-modal, .modal, [role="dialog"]');
                        for (var i = 0; i < candidates.length; i++) {
                            var m = candidates[i];
                            var st = window.getComputedStyle(m);
                            var vis = (m.offsetParent !== null) || (st && st.display !== 'none' && st.visibility !== 'hidden' && parseFloat(st.opacity || '1') > 0);
                            if (!vis) continue;
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

                // === PUUTTUVAN / MUOKATTAVAN LEIMAUKSEN PANEELIN TUKI ===
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
                    document.addEventListener('click', function(e) {
                        var openBtn = e.target && e.target.closest('#forgottenStampButton, #table-latest-stamps tbody tr');
                        if (openBtn && !e.target.closest('#forgotStampPanel')) {
                            openForgotPanel();
                            setTimeout(openForgotPanel, 80);
                            setTimeout(openForgotPanel, 250);
                            return;
                        }
                        var cancelBtn = e.target && e.target.closest('#cancelPunchForgottenButton, #cancelPunchForgottenButtonHeader, .drw-fog-of-war');
                        if (cancelBtn) {
                            closeForgotPanel();
                        }
                    }, true);
                    window._vvOpenForgotPanel = openForgotPanel;
                }

                // === AJAX- JA FETCH-ISTUNTOVALVONTA ===
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
                        var origSend = XMLHttpRequest.prototype.send;
                        XMLHttpRequest.prototype.send = function() {
                            this.addEventListener('load', function() {
                                try {
                                    var respUrl = (this.responseURL || '').toLowerCase();
                                    var bodyText = (typeof this.responseText === 'string') ? this.responseText : '';
                                    if (this.status === 401 || this.status === 403 || respUrl.indexOf('/login') !== -1 || bodyText.indexOf('id="LoginForm"') !== -1) {
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

                // === PÄIVÄLUETTELON (/Calendar/List) SIISTINTÄ JA VÄRIKOODAUS ===
                if (window.location.pathname.toLowerCase().indexOf('/calendar/list') !== -1) {
                    var ignoreRegex = /^(vapaa|vapaapäivä|arkipyhä|arkipyhävapaa|viikkolepo|viikkovapaa|tasausvapaa|saldovapaa|pekkanen|pekkaspäivä|ei\s+(suunniteltuja\s+töitä|(työ)?vuoroa))(?=$|[\s,.:;!?()\-–—])/i;
                    function styleListView() {
                        var absBoxes = document.querySelectorAll('.schedule-item-container.schedule-item-absence:not([data-vv-done])');
                        for (var i = 0; i < absBoxes.length; i++) {
                            var box = absBoxes[i];
                            box.setAttribute('data-vv-done', '1');
                            var heading = box.querySelector('.schedule-item-description-heading');
                            var title = heading ? (heading.textContent || '').replace(/\s+/g, ' ').trim() : '';
                            if (!title || ignoreRegex.test(title)) {
                                box.style.display = 'none';
                            } else if (/sairaus|hoitovapaa/i.test(title)) {
                                box.style.setProperty('background-color', '#3F1D24', 'important');
                                box.style.setProperty('border-left-color', '#EF4444', 'important');
                            } else if (/loma|säästövapaa|lomarahavapaa/i.test(title)) {
                                box.style.setProperty('background-color', '#122B22', 'important');
                                box.style.setProperty('border-left-color', '#22C55E', 'important');
                            }
                        }
                        var workBoxes = document.querySelectorAll('.schedule-item-container.schedule-item-work');
                        for (var j = 0; j < workBoxes.length; j++) {
                            var ltEl = workBoxes[j].querySelector('.schedule-item-times');
                            var m = (ltEl ? (ltEl.textContent || '') : '').match(/(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})/);
                            if (m) {
                                var sMin = parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
                                var eMin = parseInt(m[3], 10) * 60 + parseInt(m[4], 10);
                                var col = (eMin < sMin || sMin >= 20 * 60 || sMin < 4 * 60) ? '$nightBg' : (sMin >= 11 * 60 + 30 ? '$eveningBg' : '$morningBg');
                                workBoxes[j].style.setProperty('border-left-color', col, 'important');
                            }
                        }
                    }
                    styleListView();
                }
            })();
        """.trimIndent()

        view?.evaluateJavascript(js, null)
    }

    private fun handleAutoLogin(attempt: Int = 0) {
        val baseUrl = getBaseUrl()
        val rawUser = SecureCredentialManager.getUsername(this) ?: ""
        val rawPass = SecureCredentialManager.getPassword(this) ?: ""
        if (rawUser.isEmpty() || rawPass.isEmpty()) {
            isAutoSubmittingLogin = false
            endSnapshotTransition()
            return
        }
        if (BackgroundAuthHelper.isCredentialBlocked(this)) {
            isAutoSubmittingLogin = false
            endSnapshotTransition()
            return
        }
        val fp = BackgroundAuthHelper.computeCredentialFingerprint(baseUrl, rawUser, rawPass)
        if (attempt == 0 && webLoginAttemptFingerprint == fp) {
            BackgroundAuthHelper.markCredentialFailed(
                context = this,
                baseUrl = baseUrl,
                username = rawUser,
                password = rawPass,
                reason = "Virheellinen käyttäjätunnus tai salasana."
            )
            isAutoSubmittingLogin = false
            endSnapshotTransition()
            Toast.makeText(
                this,
                if (DemoModeHelper.isEnglish(this)) {
                    "Login failed – please check username and password in Settings"
                } else {
                    "Kirjautuminen epäonnistui – tarkista käyttäjätunnus ja salasana asetuksista"
                },
                Toast.LENGTH_LONG
            ).show()
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

        val wv = webView ?: return
        wv.evaluateJavascript(js) { res ->
            if (res?.contains("SUBMITTED") == true) {
                webLoginAttemptFingerprint = fp
            } else if (res?.contains("WAITING") == true) {
                if (attempt < 15) {
                    wv.postDelayed({ handleAutoLogin(attempt + 1) }, 300L)
                } else {
                    isAutoSubmittingLogin = false
                    endSnapshotTransition()
                }
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

        getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putLong("last_valid_session_ms", 0L)
            .apply()

        val baseUrl = getBaseUrl()
        if (baseUrl.isEmpty()) return
        if (BackgroundAuthHelper.isCredentialBlocked(this)) {
            endSnapshotTransition()
            return
        }

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
                    SessionCookieStore.syncToWebViewCookieManager(this@MainActivity, baseUrl)
                    ensureWebView().loadUrl(targetUrl)
                } else if (BackgroundAuthHelper.isCredentialBlocked(this@MainActivity)) {
                    endSnapshotTransition()
                    Toast.makeText(
                        this@MainActivity,
                        if (DemoModeHelper.isEnglish(this@MainActivity)) {
                            "Login failed – please check username and password in Settings"
                        } else {
                            "Kirjautuminen epäonnistui – tarkista käyttäjätunnus ja salasana asetuksista"
                        },
                        Toast.LENGTH_LONG
                    ).show()
                } else {
                    ensureWebView().loadUrl("$baseUrl/Login/Login")
                }
            }
        }
    }

    private fun handleCalendarPage() {
        if (pendingAction != Action.SYNC_CALENDAR) return
        val wv = webView ?: return

        wv.evaluateJavascript("document.documentElement.outerHTML") { rawHtml ->
            if (rawHtml == null || rawHtml == "null") {
                pendingAction = Action.NONE
                collectedCalendarHtml.clear()
                return@evaluateJavascript
            }
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
                wv.loadUrl("$baseUrl/Calendar/Month?month=${nextMonth.monthValue}&year=${nextMonth.year}")
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
            pagesToParse.forEach { html ->
                NumeronParser.parseMonthForDisplay(html)?.let { displayData ->
                    NumeronApiClient.saveMonthDisplayCache(this@MainActivity, displayData)
                }
            }
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
            val cookies = SessionCookieStore.getCookieHeader(this@MainActivity, baseUrl)
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
            if (prefs.getBoolean("track_requests", true) && baseUrl.isNotBlank()) {
                ShiftReminderReceiver.syncRequestsAndNotify(this@MainActivity, baseUrl)
            }

            withContext(Dispatchers.Main) {
                if (isFinishing || isDestroyed) return@withContext
                if (currentTab == Tab.SHIFTS && !isWebOverlayOpen) {
                    nativeShiftsView?.onShow(forceNetwork = false)
                } else if (currentTab == Tab.REQUESTS && !isWebOverlayOpen) {
                    nativeRequestsView?.refreshAfterWebEdit()
                }
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
            webView?.onPause()
        } catch (_: Exception) {}
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        try {
            webView?.onResume()
        } catch (_: Exception) {}
    }

    override fun onDestroy() {
        navigateJob?.cancel()
        webViewSlot.removeCallbacks(transitionFallbackRunnable)
        recycleSnapshotBitmap()
        try {
            if (webView != null) {
                CookieManager.getInstance().flush()
            }
        } catch (_: Exception) {}
        try {
            webView?.let { wv ->
                (wv.parent as? ViewGroup)?.removeView(wv)
                wv.stopLoading()
                wv.destroy()
            }
            webView = null
        } catch (_: Exception) {}
        scope.cancel()
        super.onDestroy()
    }
}
