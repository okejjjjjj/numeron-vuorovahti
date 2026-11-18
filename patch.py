#!/usr/bin/env python3
import pathlib
import re
import sys

def find_file(candidates):
    for c in candidates:
        p = pathlib.Path(c)
        if p.exists():
            return p
    return None

def main():
    main_act_path = find_file([
        "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt",
        "MainActivity.kt",
        "MainActivity.kt.txt"
    ])
    if not main_act_path:
        print("Virhe: MainActivity.kt-tiedostoa ei löytynyt.", file=sys.stderr)
        sys.exit(1)

    content = main_act_path.read_text(encoding="utf-8")
    original = content

    # 1. Lisätään inFlightStampAction ja lastSessionRecoveryMs tilamuuttujat
    state_anchor = "    private var pendingAction: Action = Action.NONE"
    state_replacement = """    private var pendingAction: Action = Action.NONE
    private var inFlightStampAction: Action = Action.NONE
    private var lastSessionRecoveryMs: Long = 0L"""

    if "inFlightStampAction" not in content and state_anchor in content:
        content = content.replace(state_anchor, state_replacement, 1)

    # 2. Päivitetään navigateToTab: päivitetään istunto aina ennen automaattileimausta (>10 min)
    # tai jos edellisestä validista istunnosta on yli 25 min (ASP.NET-istunto vanhenee palvelimella ennen evästettä)
    old_session_check = """                val lastSessionMs = prefs.getLong("last_valid_session_ms", 0L)
                val sessionAgeMs = System.currentTimeMillis() - lastSessionMs
                val existingCookies = CookieManager.getInstance().getCookie(baseUrl)

                if (existingCookies.isNullOrBlank() || sessionAgeMs > 11L * 60 * 60 * 1000L) {"""

    new_session_check = """                val lastSessionMs = prefs.getLong("last_valid_session_ms", 0L)
                val sessionAgeMs = System.currentTimeMillis() - lastSessionMs
                val existingCookies = CookieManager.getInstance().getCookie(baseUrl)
                val isAutoStamping = (pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT)
                val maxSessionAgeMs = if (isAutoStamping) 10L * 60 * 1000L else 25L * 60 * 1000L

                if (existingCookies.isNullOrBlank() || sessionAgeMs > maxSessionAgeMs) {"""

    if old_session_check in content:
        content = content.replace(old_session_check, new_session_check, 1)

    # 3. Nollataan inFlightStampAction manuaalisissa välilehden vaihdoissa
    content = content.replace(
        "        btnNavStamp.setOnClickListener {\n            pendingAction = Action.NONE",
        "        btnNavStamp.setOnClickListener {\n            pendingAction = Action.NONE\n            inFlightStampAction = Action.NONE",
        1
    )
    content = content.replace(
        "        btnNavRequests.setOnClickListener {\n            pendingAction = Action.NONE",
        "        btnNavRequests.setOnClickListener {\n            pendingAction = Action.NONE\n            inFlightStampAction = Action.NONE",
        1
    )
    content = content.replace(
        "        btnNavShifts.setOnClickListener {\n            pendingAction = Action.NONE",
        "        btnNavShifts.setOnClickListener {\n            pendingAction = Action.NONE\n            inFlightStampAction = Action.NONE",
        1
    )

    # 4. Lisätään SessionBridge JavascriptInterface setupWebView-metodiin
    bridge_anchor = '            "DemoBridge"\n        )'
    bridge_addition = '''            "DemoBridge"
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
        )'''

    if '"SessionBridge"' not in content and bridge_anchor in content:
        content = content.replace(bridge_anchor, bridge_addition, 1)

    # 5. Korjataan JS-istuntovahti tunnistamaan kaikki Visman "Istunto vanhentunut" -modaalit
    old_js_watcher = """                if (!window._sessionWatchInstalled) {
                    window._sessionWatchInstalled = true;
                    setInterval(function() {
                        var modal = document.getElementById('session-expired-modal');
                        if (modal && (modal.classList.contains('in') || modal.classList.contains('show') || modal.style.display === 'block')) {
                            window.location.href = '/Login/Login';
                        }
                    }, 300);
                }"""

    new_js_watcher = """                if (!window._sessionWatchInstalled) {
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
                }"""

    if old_js_watcher in content:
        content = content.replace(old_js_watcher, new_js_watcher, 1)

    # 6. Säilytetään inFlightStampAction leimauksen aikana ja palautetaan se jos istunto vanheni kesken leimauksen
    old_stamp_handlers = """            when {
                status == "CLICKED" -> {
                    pendingAction = Action.NONE
                    val beforeBtn = obj?.optString("btn", "") ?: ""
                    val beforeRow = obj?.optString("row", "") ?: ""
                    Toast.makeText(this, "Leimataan ($targetText)...", Toast.LENGTH_SHORT).show()
                    verifyStampAndClose(targetText, beforeBtn, beforeRow, 0)
                }
                status == "WRONG_DIRECTION" -> {
                    pendingAction = Action.NONE
                    Toast.makeText(this, "Olet jo leimannut tilaan: $targetText", Toast.LENGTH_LONG).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                }"""

    new_stamp_handlers = """            when {
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
                }"""

    if old_stamp_handlers in content:
        content = content.replace(old_stamp_handlers, new_stamp_handlers, 1)

    old_verify = """        val verifyJs = \"\"\"
            (function() {
                var btn = document.getElementById('punchButton');
                var btnText = btn ? (btn.innerText || btn.textContent || '').trim() : '';
                var rowEl = document.querySelector('#table-latest-stamps tbody tr, #table-latest-stamps tr');
                var firstRow = rowEl ? (rowEl.innerText || rowEl.textContent || '').replace(/\\s+/g, ' ').trim() : '';
                return JSON.stringify({ btn: btnText, row: firstRow });
            })();
        \"\"\".trimIndent()"""

    new_verify = """        val verifyJs = \"\"\"
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
                var firstRow = rowEl ? (rowEl.innerText || rowEl.textContent || '').replace(/\\s+/g, ' ').trim() : '';
                return JSON.stringify({ btn: btnText, row: firstRow, expired: expired });
            })();
        \"\"\".trimIndent()"""

    if old_verify in content:
        content = content.replace(old_verify, new_verify, 1)

    old_verify_check = """                val nowBtn = obj?.optString("btn", "") ?: ""
                val nowRow = obj?.optString("row", "") ?: ""

                val buttonFlipped = nowBtn.isNotEmpty() && nowBtn != beforeBtn &&
                    nowBtn.lowercase().indexOf(targetLower) == -1
                val rowUpdated = nowRow.isNotEmpty() && nowRow != beforeRow

                if (buttonFlipped || rowUpdated) {
                    CookieManager.getInstance().flush()
                    Toast.makeText(this, "Leimaus vahvistettu ($targetText)", Toast.LENGTH_SHORT).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 600L)
                } else if (checkAttempt < 25) {"""

    new_verify_check = """                val nowBtn = obj?.optString("btn", "") ?: ""
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
                    Toast.makeText(this, "Leimaus vahvistettu ($targetText)", Toast.LENGTH_SHORT).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 600L)
                } else if (checkAttempt < 25) {"""

    if old_verify_check in content:
        content = content.replace(old_verify_check, new_verify_check, 1)

    recovery_method = """
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
                    val targetUrl = if (pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT) {
                        "$baseUrl/WorktimeStamping"
                    } else {
                        webView.url ?: "$baseUrl/WorktimeStamping"
                    }
                    webView.loadUrl(targetUrl)
                } else {
                    webView.loadUrl("$baseUrl/Login/Login")
                }
            }
        }
    }
"""

    if "private fun handleWebSessionExpired()" not in content and "    private fun handleStampingPage(" in content:
        content = content.replace(
            "    private fun handleStampingPage(",
            recovery_method + "\n    private fun handleStampingPage(",
            1
        )

    if content != original:
        main_act_path.write_text(content, encoding="utf-8")
        print(f"Päivitetty onnistuneesti (istunnon palautus ja leimauksen varmistus): {main_act_path}")
    else:
        print("Ei muutoksia tehtävänä tai korjaus oli jo lisätty.")

    # Nostetaan versionCode yhdellä pykälällä
    gradle_path = find_file([
        "app/build.gradle.kts",
        "app/build.gradle",
        "build.gradle.kts",
        "build.gradle.kts.txt"
    ])
    if gradle_path:
        g_content = gradle_path.read_text(encoding="utf-8")
        vc_match = re.search(r'versionCode\s*=\s*(\d+)', g_content)
        if vc_match:
            old_code = int(vc_match.group(1))
            new_code = old_code + 1
            g_content = g_content.replace(f"versionCode = {old_code}", f"versionCode = {new_code}", 1)
            gradle_path.write_text(g_content, encoding="utf-8")
            print(f"Nostettu versionCode: {old_code} -> {new_code} ({gradle_path})")

if __name__ == "__main__":
    main()
