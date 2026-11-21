import os
import re
import sys

def find_file(filename):
    for root, _, files in os.walk("."):
        if filename in files:
            return os.path.join(root, filename)
    return None

def patch_main_activity(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Lisätään Job-import ja navigointitilan seuranta
    if "import kotlinx.coroutines.Job" not in content:
        content = content.replace(
            "import kotlinx.coroutines.CoroutineScope",
            "import kotlinx.coroutines.CoroutineScope\nimport kotlinx.coroutines.Job"
        )

    old_fields = """    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())

    private var pendingAction: Action = Action.NONE"""

    new_fields = """    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var navigateJob: Job? = null
    private var navigationToken: Int = 0
    private var isAutoSubmittingLogin: Boolean = false

    private var pendingAction: Action = Action.NONE"""

    assert old_fields in content, "MainActivity: kenttiä ei löytynyt"
    content = content.replace(old_fields, new_fields, 1)

    # 2. Korjataan startSnapshotTransition, endSnapshotTransition ja navigateToTab
    old_nav_block = """    private var transitionOverlay: FrameLayout? = null
    private var snapshotView: ImageView? = null
    private var isTransitionActive: Boolean = false
    private val transitionFallbackRunnable = Runnable {
        endSnapshotTransition()
    }"""

    new_nav_block = """    private var transitionOverlay: FrameLayout? = null
    private var snapshotView: ImageView? = null
    private var snapshotBitmap: Bitmap? = null
    private var isTransitionActive: Boolean = false
    private val transitionFallbackRunnable = Runnable {
        isAutoSubmittingLogin = false
        endSnapshotTransition()
    }"""

    assert old_nav_block in content, "MainActivity: transition-kenttiä ei löytynyt"
    content = content.replace(old_nav_block, new_nav_block, 1)

    old_start_end_nav = """    private fun startSnapshotTransition(onReady: (() -> Unit)? = null) {
        val overlay = ensureTransitionOverlay()
        overlay.animate().cancel()

        if (!isTransitionActive) {
            isTransitionActive = true

            if (webView.width > 0 && webView.height > 0 && webView.alpha > 0.5f) {
                try {
                    val bitmap = Bitmap.createBitmap(webView.width, webView.height, Bitmap.Config.RGB_565)
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
            webView.post { syncOverlayBoundsToWebView(overlay) }
            webView.removeCallbacks(transitionFallbackRunnable)
            webView.postDelayed(transitionFallbackRunnable, 4000L)

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
        snapshotView?.setImageDrawable(null)
        snapshotView?.visibility = View.GONE
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
                val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                val lastSessionMs = prefs.getLong("last_valid_session_ms", 0L)
                val sessionAgeMs = System.currentTimeMillis() - lastSessionMs
                val existingCookies = CookieManager.getInstance().getCookie(baseUrl)
                val isAutoStamping = (pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT)
                val maxSessionAgeMs = if (isAutoStamping) 10L * 60 * 1000L else 25L * 60 * 1000L

                if (existingCookies.isNullOrBlank() || sessionAgeMs > maxSessionAgeMs) {
                    scope.launch {
                        try {
                            val ok = BackgroundAuthHelper.ensureAuthenticatedSession(this@MainActivity)
                            if (ok) {
                                prefs.edit().putLong("last_valid_session_ms", System.currentTimeMillis()).apply()
                            }
                        } catch (_: Exception) {
                        }
                        webView.loadUrl(url)
                    }
                } else {
                    webView.loadUrl(url)
                }
            }
        }
    }"""

    new_start_end_nav = """    private fun recycleSnapshotBitmap() {
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
    }"""

    assert old_start_end_nav in content, "MainActivity: navigateToTab-lohkoa ei löytynyt"
    content = content.replace(old_start_end_nav, new_start_end_nav, 1)

    # 3. Korjataan onReceivedError (ohitetaan ERROR_ABORTED = -1) ja onPageFinished (ei paljasteta Login-sivua kesken lähetyksen)
    old_error_block = """            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: android.webkit.WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    endSnapshotTransition()
                    val code = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) error?.errorCode ?: 0 else 0
                    val desc = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) error?.description?.toString().orEmpty() else ""
                    if (code != android.webkit.WebViewClient.ERROR_UNKNOWN) {
                        Toast.makeText(this@MainActivity, "Sivun latausvirhe ($code): $desc", Toast.LENGTH_LONG).show()
                    }
                }
            }"""

    new_error_block = """            override fun onReceivedError(
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
            }"""

    assert old_error_block in content, "MainActivity: onReceivedError-lohkoa ei löytynyt"
    content = content.replace(old_error_block, new_error_block, 1)

    old_page_finished_tail = """                when {
                    url.contains("/Login/Login", ignoreCase = true) -> {
                        startSnapshotTransition()
                        handleAutoLogin()
                    }
                    url.contains("/InfraDashboard", ignoreCase = true) && dashboardRedirectCount < 2 -> {
                        dashboardRedirectCount++
                        webView.loadUrl(resolveResumeUrl(getBaseUrl()))
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
                }, revealDelay)"""

    new_page_finished_tail = """                when {
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
                }, revealDelay)"""

    assert old_page_finished_tail in content, "MainActivity: onPageFinished-lohkoa ei löytynyt"
    content = content.replace(old_page_finished_tail, new_page_finished_tail, 1)

    # 4. Korjataan MutationObserver-silmukat leimaussivulla (applyStampingColors & watchStampPageDom)
    old_stamp_colors = """                        applyStampingColors();
                        if (!window._stampingColorObserverInstalled && document.body && typeof MutationObserver !== 'undefined') {
                            window._stampingColorObserverInstalled = true;
                            var stampObs = new MutationObserver(function() {
                                applyStampingColors();
                            });
                            stampObs.observe(document.body, { childList: true, subtree: true, characterData: true });
                        }"""

    new_stamp_colors = """                        applyStampingColors();
                        var stampTblForColor = document.getElementById('table-latest-stamps');
                        if (stampTblForColor && !stampTblForColor._colorObsInstalled && typeof MutationObserver !== 'undefined') {
                            stampTblForColor._colorObsInstalled = true;
                            var colorScheduled = false;
                            var stampObs = new MutationObserver(function() {
                                if (colorScheduled) return;
                                colorScheduled = true;
                                setTimeout(function() {
                                    colorScheduled = false;
                                    applyStampingColors();
                                }, 80);
                            });
                            stampObs.observe(stampTblForColor, { childList: true, subtree: true });
                        }"""

    assert old_stamp_colors in content, "MainActivity: applyStampingColors-observeria ei löytynyt"
    content = content.replace(old_stamp_colors, new_stamp_colors, 1)

    old_watch_stamp = """                    function watchStampPageDom() {
                        var panel = getForgotPanel();
                        if (panel && !panel._vvWatched && typeof MutationObserver !== 'undefined') {
                            panel._vvWatched = true;
                            var pObs = new MutationObserver(function() {
                                var st = panel.getAttribute('style') || '';
                                var isTop100 = /top\s*:\s*100%/i.test(st);
                                if (!isTop100 && !panel.classList.contains('minimized') && st.indexOf('top:') !== -1) {
                                    panel.classList.add('force-open');
                                } else if (isTop100) {
                                    panel.classList.remove('force-open');
                                }
                            });
                            pObs.observe(panel, { attributes: true, attributeFilter: ['style', 'class'] });
                        }
                        var stampTbl = document.getElementById('table-latest-stamps');
                        if (stampTbl && !stampTbl._vvWatched && typeof MutationObserver !== 'undefined') {
                            stampTbl._vvWatched = true;
                            new MutationObserver(revealHiddenStampRows).observe(stampTbl, { childList: true, subtree: true });
                        }
                    }
                    watchStampPageDom();
                    if (document.body && typeof MutationObserver !== 'undefined') {
                        new MutationObserver(watchStampPageDom).observe(document.body, { childList: true, subtree: true });
                    }"""

    new_watch_stamp = """                    function watchStampPageDom() {
                        var stampTbl = document.getElementById('table-latest-stamps');
                        if (stampTbl && !stampTbl._vvWatched && typeof MutationObserver !== 'undefined') {
                            stampTbl._vvWatched = true;
                            var rowsScheduled = false;
                            new MutationObserver(function() {
                                if (rowsScheduled) return;
                                rowsScheduled = true;
                                setTimeout(function() {
                                    rowsScheduled = false;
                                    revealHiddenStampRows();
                                }, 80);
                            }).observe(stampTbl, { childList: true, subtree: true });
                        }
                    }
                    watchStampPageDom();"""

    assert old_watch_stamp in content, "MainActivity: watchStampPageDom-lohkoa ei löytynyt"
    content = content.replace(old_watch_stamp, new_watch_stamp, 1)

    # 5. Vapautetaan bitmap myös onDestroyssa
    content = content.replace(
        "    override fun onDestroy() {\n        try {",
        "    override fun onDestroy() {\n        recycleSnapshotBitmap()\n        try {",
        1
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"OK: {path} päivitetty.")

def patch_background_auth(path):
    if not path or not os.path.exists(path):
        print("HUOM: BackgroundAuthHelper.kt ei löytynyt, ohitetaan.")
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "stopAfterRedirect = true" in content:
        content = content.replace("stopAfterRedirect = true", "stopAfterRedirect = false", 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"OK: {path} (stopAfterRedirect = false) päivitetty.")
    else:
        print(f"OK: {path} ei vaatinut muutoksia.")

def bump_version_code():
    for candidate in ["app/build.gradle.kts", "app/build.gradle"]:
        if os.path.exists(candidate):
            with open(candidate, "r", encoding="utf-8") as f:
                gradle = f.read()
            match = re.search(r"(versionCode\s*=?\s*)(\d+)", gradle)
            if match:
                old_vc = int(match.group(2))
                new_vc = old_vc + 1
                gradle = gradle[:match.start(2)] + str(new_vc) + gradle[match.end(2):]
                with open(candidate, "w", encoding="utf-8") as f:
                    f.write(gradle)
                print(f"OK: {candidate} versionCode päivitetty: {old_vc} -> {new_vc}")
            return

if __name__ == "__main__":
    main_act = find_file("MainActivity.kt")
    if not main_act:
        print("VIRHE: MainActivity.kt ei löytynyt projektista!")
        sys.exit(1)

    bg_auth = find_file("BackgroundAuthHelper.kt")

    patch_main_activity(main_act)
    patch_background_auth(bg_auth)
    bump_version_code()
    print("\nValmis! Voit nyt kääntää ja testata sovelluksen.")
