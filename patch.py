import os
import sys

OLD_OVERLAY_ADD = '''        rootContent.addView(overlay, FrameLayout.LayoutParams(webView.width, webView.height))
        syncOverlayBoundsToWebView(overlay)
        transitionOverlay = overlay
        return overlay'''

NEW_OVERLAY_ADD = '''        rootContent.addView(overlay, FrameLayout.LayoutParams(webView.width, webView.height))
        syncOverlayBoundsToWebView(overlay)
        webView.post { syncOverlayBoundsToWebView(overlay) }
        transitionOverlay = overlay
        return overlay'''

OLD_TRANSITION_FUNCS = '''    private var transitionOverlay: FrameLayout? = null
    private var snapshotView: ImageView? = null
    private var isTransitionActive: Boolean = false'''

NEW_TRANSITION_FUNCS = '''    private var transitionOverlay: FrameLayout? = null
    private var snapshotView: ImageView? = null
    private var isTransitionActive: Boolean = false
    private val transitionFallbackRunnable = Runnable {
        if (isTransitionActive) {
            endSnapshotTransition()
        }
    }'''

OLD_START_TRANSITION_END = '''            overlay.alpha = 1f
            overlay.visibility = View.VISIBLE
            webView.alpha = 0f

            if (onReady != null) {
                webView.post { onReady() }
            }
        } else {
            onReady?.invoke()
        }'''

NEW_START_TRANSITION_END = '''            overlay.alpha = 1f
            overlay.visibility = View.VISIBLE
            webView.alpha = 0f
            webView.post { syncOverlayBoundsToWebView(overlay) }
            webView.removeCallbacks(transitionFallbackRunnable)
            webView.postDelayed(transitionFallbackRunnable, 8000L)

            if (onReady != null) {
                webView.post { onReady() }
            }
        } else {
            onReady?.invoke()
        }'''

OLD_END_TRANSITION = '''    private fun endSnapshotTransition() {
        val overlay = transitionOverlay ?: return
        if (!isTransitionActive) return

        overlay.animate().cancel()
        webView.alpha = 1f'''

NEW_END_TRANSITION = '''    private fun endSnapshotTransition() {
        webView.removeCallbacks(transitionFallbackRunnable)
        webView.alpha = 1f
        val overlay = transitionOverlay ?: run {
            isTransitionActive = false
            return
        }
        if (!isTransitionActive) return

        overlay.animate().cancel()'''

OLD_EMPTY_BASEURL = '''            val baseUrl = getBaseUrl()
            if (baseUrl.isEmpty()) {
                Toast.makeText(this, if (DemoModeHelper.isEnglish(this)) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista", Toast.LENGTH_LONG).show()
                btnNavSettings.performClick()
                return
            }'''

NEW_EMPTY_BASEURL = '''            val baseUrl = getBaseUrl()
            if (baseUrl.isEmpty()) {
                endSnapshotTransition()
                Toast.makeText(this, if (DemoModeHelper.isEnglish(this)) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista", Toast.LENGTH_LONG).show()
                btnNavSettings.performClick()
                return
            }'''

OLD_ON_PAGE_FINISHED = '''            override fun onPageFinished(view: WebView?, url: String?) {'''

NEW_ON_PAGE_FINISHED = '''            override fun onReceivedError(
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

OLD_DUP_NESTED = r'''                        nameEl.setAttribute('data-raw-shift', rawText);
                        nameEl.setAttribute('data-formatted-for', 'v3:' + rawText);

                // === SISÄÄN / ULOS -LEIMAUKSEN VÄRIKOODAUS ===
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

                    applyStampingColors();
                    if (!window._stampingColorObserverInstalled && document.body && typeof MutationObserver !== 'undefined') {
                        window._stampingColorObserverInstalled = true;
                        var stampObs = new MutationObserver(function() {
                            applyStampingColors();
                        });
                        stampObs.observe(document.body, { childList: true, subtree: true, characterData: true });
                    }
                })();'''

NEW_DUP_NESTED = r'''                        nameEl.setAttribute('data-raw-shift', rawText);
                        nameEl.setAttribute('data-formatted-for', 'v3:' + rawText);'''


def find_file(filename):
    default_path = os.path.join("app", "src", "main", "java", "fi", "numeron", "vuorovahti", filename)
    if os.path.isfile(default_path):
        return default_path
    for root, _, files in os.walk("."):
        if filename in files:
            return os.path.join(root, filename)
    return None


def main():
    main_path = find_file("MainActivity.kt")
    if not main_path:
        print("VIRHE: MainActivity.kt ei löytynyt.")
        sys.exit(1)

    with open(main_path, "r", encoding="utf-8") as f:
        src = f.read()

    changed = False
    for label, old, new in [
        ("Overlayn koko layoutin jälkeen", OLD_OVERLAY_ADD, NEW_OVERLAY_ADD),
        ("Siirtymän aikakatkaisumuuttuja", OLD_TRANSITION_FUNCS, NEW_TRANSITION_FUNCS),
        ("Siirtymän aikakatkaisun käynnistys", OLD_START_TRANSITION_END, NEW_START_TRANSITION_END),
        ("WebView alpha -palautus", OLD_END_TRANSITION, NEW_END_TRANSITION),
        ("Tyhjän baseUrl-tilan siirtymän vapautus", OLD_EMPTY_BASEURL, NEW_EMPTY_BASEURL),
        ("onReceivedError-käsittelijä", OLD_ON_PAGE_FINISHED, NEW_ON_PAGE_FINISHED),
        ("Sisäkkäisen värikoodauslohkon siivous", OLD_DUP_NESTED, NEW_DUP_NESTED),
    ]:
        if new in src:
            continue
        if old not in src:
            print(f"VAROITUS: Kohtaa '{label}' ei löytynyt.")
            continue
        src = src.replace(old, new, 1)
        changed = True

    if changed:
        with open(main_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(src)
        print(f"Päivitetty: {main_path}")
    else:
        print(f"Ei muutoksia (jo päivitetty): {main_path}")


if __name__ == "__main__":
    main()
