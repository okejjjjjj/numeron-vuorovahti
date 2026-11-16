#!/usr/bin/env python3
import os
import re

TARGET_PATH = os.path.join("app", "src", "main", "java", "fi", "numeron", "vuorovahti", "MainActivity.kt")

if not os.path.exists(TARGET_PATH):
    raise FileNotFoundError(f"Tiedostoa ei löytynyt: {TARGET_PATH}")

with open(TARGET_PATH, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Lisätään tarvittavat importit (Canvas, ImageView)
imports_to_add = [
    "import android.graphics.Canvas",
    "import android.widget.ImageView",
]
for imp in imports_to_add:
    if imp not in content:
        content = content.replace("import android.graphics.Bitmap", f"import android.graphics.Bitmap\n{imp}", 1)

# 2. Korvataan vanha blur-siirtymälogiikka kuvakaappaus-crossfade-logiikalla
old_transition_block = re.search(
    r"    private var transitionOverlay: FrameLayout\? = null.*?    private fun endBlurTransition\(\).*?\n    \}\n",
    content,
    flags=re.DOTALL,
)

if not old_transition_block:
    raise RuntimeError("Alkuperäistä transitionOverlay / startBlurTransition / endBlurTransition -lohkoa ei löytynyt.")

new_transition_block = """    private var transitionOverlay: FrameLayout? = null
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
            .setDuration(220L)
            .withEndAction {
                overlay.visibility = View.GONE
                snapshotView?.setImageDrawable(null)
                snapshotView?.visibility = View.GONE
                isTransitionActive = false
            }
            .start()
    }
"""

content = content[:old_transition_block.start()] + new_transition_block + content[old_transition_block.end():]

# 3. Päivitetään kutsut startBlurTransition -> startSnapshotTransition ja endBlurTransition -> endSnapshotTransition
content = content.replace("startBlurTransition", "startSnapshotTransition")
content = content.replace("endBlurTransition", "endSnapshotTransition")

# 4. Lisätään shouldOverrideUrlLoading WebViewClientiin, jotta kuvakaappaus otetaan heti klikkaushetkellä
old_on_page_started = """        webView.webViewClient = object : WebViewClient() {

            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                super.onPageStarted(view, url, favicon)
                startSnapshotTransition()
            }"""

new_on_page_started = """        webView.webViewClient = object : WebViewClient() {

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
            }"""

if old_on_page_started not in content:
    raise RuntimeError("WebViewClient.onPageStarted-lohkoa ei löytynyt.")

content = content.replace(old_on_page_started, new_on_page_started, 1)

with open(TARGET_PATH, "w", encoding="utf-8") as f:
    f.write(content)

print("patch.py suoritettu onnistuneesti: MainActivity.kt päivitetty kuvakaappaus-crossfade-siirtymällä.")
