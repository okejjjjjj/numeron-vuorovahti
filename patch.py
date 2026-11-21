import os
import re
import sys


def find_file(filename):
    default_path = os.path.join("app", "src", "main", "java", "fi", "numeron", "vuorovahti", filename)
    if os.path.isfile(default_path):
        return default_path
    for root, _, files in os.walk("."):
        if filename in files:
            return os.path.join(root, filename)
    return None


def patch_url_normalizer():
    path = find_file("UrlNormalizer.kt")
    if not path:
        print("VAROITUS: UrlNormalizer.kt ei löytynyt.")
        return
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    old = '''    fun getSavedBaseUrl(context: Context): String {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val raw = prefs.getString("server_url", "") ?: ""
        return normalizeOrgUrl(raw)
    }'''

    new = '''    fun getSavedBaseUrl(context: Context): String {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val serverUrl = (prefs.getString("server_url", "") ?: "").trim()
        val rawOrg = (prefs.getString("org_raw_input", "") ?: "").trim()
        val candidate = serverUrl.ifEmpty { rawOrg }
        val normalized = normalizeOrgUrl(candidate)
        return if (normalized.equals("demo", ignoreCase = true)) "" else normalized
    }'''

    if new not in src and old in src:
        src = src.replace(old, new, 1)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(src)
        print(f"Päivitetty: {path}")
    else:
        print(f"Ei muutoksia: {path}")


def patch_demo_mode_helper():
    path = find_file("DemoModeHelper.kt")
    if not path:
        print("VAROITUS: DemoModeHelper.kt ei löytynyt.")
        return
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    old = '''    fun isDemoEnabled(context: Context): Boolean {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val org = (prefs.getString("org_raw_input", "") ?: "").trim()
        val serverUrl = (prefs.getString("server_url", "") ?: "").trim()
        val user = (SecureCredentialManager.getUsername(context) ?: "").trim()
        val pass = SecureCredentialManager.getPassword(context) ?: ""

        if (user.isEmpty() || pass.isEmpty() || (org.isEmpty() && serverUrl.isEmpty())) {
            return true
        }
        return isDemoCredentials(org.ifEmpty { serverUrl }, user, pass)
    }'''

    new = '''    fun isDemoEnabled(context: Context): Boolean {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val org = (prefs.getString("org_raw_input", "") ?: "").trim()
        val serverUrl = (prefs.getString("server_url", "") ?: "").trim()
        val user = (SecureCredentialManager.getUsername(context) ?: "").trim()
        val pass = SecureCredentialManager.getPassword(context) ?: ""

        if (user.isEmpty() || pass.isEmpty() || (org.isEmpty() && serverUrl.isEmpty())) {
            return true
        }
        if (UrlNormalizer.isDemoInput(org) || UrlNormalizer.isDemoInput(serverUrl)) {
            return true
        }
        return isDemoCredentials(org.ifEmpty { serverUrl }, user, pass)
    }'''

    if new not in src and old in src:
        src = src.replace(old, new, 1)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(src)
        print(f"Päivitetty: {path}")
    else:
        print(f"Ei muutoksia: {path}")


def patch_settings_dialog():
    path = find_file("SettingsDialogHelper.kt")
    if not path:
        print("VAROITUS: SettingsDialogHelper.kt ei löytynyt.")
        return
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    old = '''        val editOrg = EditText(context).apply {
            hint = "demo"
            setText(prefs.getString("org_raw_input", ""))'''

    new = '''        val savedOrgPref = (prefs.getString("org_raw_input", "") ?: "").trim()
            .ifEmpty { (prefs.getString("server_url", "") ?: "").trim() }
        val editOrg = EditText(context).apply {
            hint = "demo"
            setText(savedOrgPref)'''

    if new not in src and old in src:
        src = src.replace(old, new, 1)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(src)
        print(f"Päivitetty: {path}")
    else:
        print(f"Ei muutoksia: {path}")


def patch_main_activity():
    path = find_file("MainActivity.kt")
    if not path:
        print("VIRHE: MainActivity.kt ei löytynyt.")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    changed = False

    # 1. Korvataan siirtymäpeitto ja navigateToTab yhtenäiseksi, varmistetuksi kokonaisuudeksi
    transition_pattern = re.compile(
        r"    private var transitionOverlay: FrameLayout\? = null.*?    private fun setupBottomBar\(\)",
        re.DOTALL
    )
    new_transition_block = '''    private var transitionOverlay: FrameLayout? = null
    private var snapshotView: ImageView? = null
    private var isTransitionActive: Boolean = false
    private val transitionFallbackRunnable = Runnable {
        if (isTransitionActive) {
            endSnapshotTransition()
        }
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

    private fun startSnapshotTransition(onReady: (() -> Unit)? = null) {
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
            webView.postDelayed(transitionFallbackRunnable, 5000L)

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
        val overlay = transitionOverlay ?: run {
            isTransitionActive = false
            return
        }
        if (!isTransitionActive) return

        overlay.animate().cancel()
        overlay.animate()
            .alpha(0f)
            .setDuration(260L)
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

    private fun setupBottomBar()'''

    if transition_pattern.search(src):
        src = transition_pattern.sub(new_transition_block, src, count=1)
        changed = True
    else:
        print("VAROITUS: Siirtymäpeiton lohkoa ei voitu korvata automaattisesti.")

    # 2. Sallitaan kaikki numeronwfm-alidomainit sisäisessä WebView'ssä
    old_internal = '''                    val isInternal = reqHost.equals("demo.local", ignoreCase = true) ||
                        (!allowedHost.isNullOrBlank() && reqHost.equals(allowedHost, ignoreCase = true))'''
    new_internal = '''                    val isInternal = reqHost.equals("demo.local", ignoreCase = true) ||
                        (!reqHost.isNullOrBlank() && (reqHost.endsWith(".numeronwfm.com", ignoreCase = true) || reqHost.endsWith(".numeronwfm.fi", ignoreCase = true))) ||
                        (!allowedHost.isNullOrBlank() && reqHost.equals(allowedHost, ignoreCase = true))'''
    if new_internal not in src and old_internal in src:
        src = src.replace(old_internal, new_internal, 1)
        changed = True

    # 3. Virheenkäsittely ja /InfraDashboard-uudelleenohjaus aktiiviselle välilehdelle
    if "override fun onReceivedError(" not in src:
        old_fin = "            override fun onPageFinished(view: WebView?, url: String?) {"
        new_fin = '''            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: android.webkit.WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    endSnapshotTransition()
                }
            }

            override fun onPageFinished(view: WebView?, url: String?) {'''
        if old_fin in src:
            src = src.replace(old_fin, new_fin, 1)
            changed = True

    old_when_login = '''                    url.contains("/Login/Login", ignoreCase = true) -> {
                        startSnapshotTransition()
                        handleAutoLogin()
                    }'''
    new_when_login = '''                    url.contains("/Login/Login", ignoreCase = true) -> {
                        startSnapshotTransition()
                        handleAutoLogin()
                    }
                    url.contains("/InfraDashboard", ignoreCase = true) && dashboardRedirectCount < 2 -> {
                        dashboardRedirectCount++
                        webView.loadUrl(resolveResumeUrl(getBaseUrl()))
                    }'''
    if "url.contains(\"/InfraDashboard\", ignoreCase = true) && dashboardRedirectCount < 2" not in src and old_when_login in src:
        src = src.replace(old_when_login, new_when_login, 1)
        changed = True

    # 4. Poistetaan mahdollisesti jäänyt sisäkkäinen värikoodauslohko applyShiftFormat-funktiosta
    nested_pattern = re.compile(
        r"(nameEl\.setAttribute\('data-formatted-for', 'v3:' \+ rawText\);)\s*// === SISÄÄN / ULOS -LEIMAUKSEN VÄRIKOODAUS ===\s*\(function setupStampingColorCoding\(\).*?\}\)\(\);",
        re.DOTALL
    )
    if nested_pattern.search(src):
        src = nested_pattern.sub(r"\1", src, count=1)
        changed = True

    if changed:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(src)
        print(f"Päivitetty: {path}")
    else:
        print(f"Ei muutoksia: {path}")


def main():
    patch_url_normalizer()
    patch_demo_mode_helper()
    patch_settings_dialog()
    patch_main_activity()


if __name__ == "__main__":
    main()
