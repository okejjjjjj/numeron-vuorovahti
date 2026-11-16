#!/usr/bin/env python3
import os
import re
import sys

def find_main_activity():
    for root, dirs, files in os.walk("."):
        if "MainActivity.kt" in files:
            return os.path.join(root, "MainActivity.kt")
    return None

def patch_main_activity(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original_content = content

    # 1. Lisätään ValueAnimator-import
    if "import android.animation.ValueAnimator" not in content:
        content = content.replace(
            "import android.os.Bundle",
            "import android.animation.ValueAnimator\nimport android.os.Bundle",
            1
        )
        print("[OK] Lisätty import android.animation.ValueAnimator.")

    # 2. Korvataan transitionOverlay -> navigateToTab -lohko
    pattern_transition_and_nav = re.compile(
        r"    private var transitionOverlay: FrameLayout\? = null.*?    private fun setupBottomBar\(\)",
        re.DOTALL
    )

    replacement_transition_and_nav = """    private var transitionOverlay: FrameLayout? = null
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

    private fun setupBottomBar()"""

    if pattern_transition_and_nav.search(content):
        content = pattern_transition_and_nav.sub(replacement_transition_and_nav, content, count=1)
        print("[OK] Blur-siirtymä ja navigateToTab() päivitetty.")
    else:
        print("[VAROITUS] Siirtymälohkoa ei löytynyt odotetussa muodossa.")

    # 3. Päivitetään revealDelay onPageFinished-metodissa
    old_reveal = 'val revealDelay = if (url.contains("/Calendar", ignoreCase = true)) 160L else 80L'
    new_reveal = 'val revealDelay = if (url.contains("/Calendar", ignoreCase = true)) 280L else 200L'
    if old_reveal in content:
        content = content.replace(old_reveal, new_reveal, 1)
        print("[OK] revealDelay päivitetty.")
    else:
        print("[VAROITUS] revealDelay-riviä ei löytynyt.")

    if content != original_content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[VALMIS] Muutokset tallennettu tiedostoon: {filepath}")
    else:
        print("[EI MUUTOKSIA] Tiedostoa ei muutettu.")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else find_main_activity()
    if not target or not os.path.exists(target):
        print("Virhe: MainActivity.kt-tiedostoa ei löytynyt.")
        sys.exit(1)
    patch_main_activity(target)
