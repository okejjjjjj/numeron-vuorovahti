import os
import sys


def find_file(filename):
    default_path = os.path.join("app", "src", "main", "java", "fi", "numeron", "vuorovahti", filename)
    if os.path.isfile(default_path):
        return default_path
    for root, _, files in os.walk("."):
        if filename in files:
            return os.path.join(root, filename)
    return None


REPLACEMENT_BLOCK = '''    private var transitionOverlay: FrameLayout? = null
    private var snapshotView: ImageView? = null
    private var isTransitionActive: Boolean = false
    private val transitionFallbackRunnable = Runnable {
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
                webView.stopLoading()
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
                webView.stopLoading()
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

'''


def main():
    path = find_file("MainActivity.kt")
    if not path:
        print("VIRHE: MainActivity.kt ei löytynyt.")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    start_marker = "    private var transitionOverlay: FrameLayout? = null"
    end_marker = "    private fun triggerTestReminderNotification()"

    start_idx = src.find(start_marker)
    end_idx = src.find(end_marker)

    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        print("VIRHE: Korvattavaa lohkoa ei löytynyt MainActivity.kt-tiedostosta.")
        sys.exit(1)

    updated = src[:start_idx] + REPLACEMENT_BLOCK + src[end_idx:]

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(updated)

    print(f"Päivitetty: {path}")


if __name__ == "__main__":
    main()
