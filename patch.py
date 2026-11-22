#!/usr/bin/env python3
"""
Numeron Vuorovahti – kriittisten bugien korjauspatch.

Käyttö:
    python3 patch.py --dry-run   # Tarkistaa osumat muuttamatta tiedostoja
    python3 patch.py             # Ajaa muutokset
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

IGNORED_DIRS = {".git", ".gradle", ".idea", "build", "node_modules", "__pycache__"}


def find_file(root: Path, filename: str, must_contain: str | None = None) -> Path:
    matches: list[Path] = []
    for p in root.rglob(filename):
        if any(part in IGNORED_DIRS for part in p.parts):
            continue
        if must_contain is None or must_contain in p.read_text(encoding="utf-8", errors="ignore"):
            matches.append(p)
    if len(matches) != 1:
        raise RuntimeError(
            f"Odotettiin täsmälleen yhtä '{filename}'-tiedostoa, löytyi {len(matches)}: {matches}"
        )
    return matches[0]


def replace_once(content: str, old: str, new: str, label: str) -> str:
    count = content.count(old)
    if count != 1:
        raise RuntimeError(
            f"[{label}] Odotettiin 1 osumaa, löytyi {count}. Tarkista tiedoston versio."
        )
    return content.replace(old, new, 1)


def patch_build_gradle(text: str) -> str:
    text = replace_once(text, "compileSdk = 35", "compileSdk = 36", "build.gradle:compileSdk")
    text = replace_once(text, "versionCode = 112", "versionCode = 113", "build.gradle:versionCode")
    text = replace_once(text, 'versionName = "3.2.8"', 'versionName = "3.2.9"', "build.gradle:versionName")
    return text


def patch_background_auth_helper(text: str) -> str:
    text = replace_once(
        text,
        r'''    @Volatile
    private var lastAuthBaseUrl: String = ""

    suspend fun ensureAuthenticatedSession(context: Context): Boolean = withContext(Dispatchers.IO) {''',
        r'''    @Volatile
    private var lastAuthBaseUrl: String = ""

    fun clearSessionCache(context: Context? = null) {
        lastAuthSuccessMs = 0L
        lastAuthBaseUrl = ""
        if (context != null) {
            context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                .edit()
                .putLong("last_valid_session_ms", 0L)
                .apply()
            try {
                val cm = CookieManager.getInstance()
                cm.removeAllCookies(null)
                cm.flush()
            } catch (_: Exception) {
            }
        }
    }

    suspend fun ensureAuthenticatedSession(
        context: Context,
        forceRefresh: Boolean = false
    ): Boolean = withContext(Dispatchers.IO) {''',
        "BackgroundAuthHelper:signature_and_clear",
    )

    text = replace_once(
        text,
        r'''            if (!cachedCookies.isNullOrBlank() &&
                baseUrl == lastAuthBaseUrl &&
                (nowMs - lastAuthSuccessMs) < 90_000L
            ) {
                return@withLock true
            }''',
        r'''            if (!forceRefresh &&
                !cachedCookies.isNullOrBlank() &&
                baseUrl == lastAuthBaseUrl &&
                (nowMs - lastAuthSuccessMs) < 90_000L
            ) {
                return@withLock true
            }''',
        "BackgroundAuthHelper:forceRefresh_check",
    )

    text = replace_once(
        text,
        r'''            if (stillOnLogin || cookieStore.isEmpty()) {
                return@withContext false
            }''',
        r'''            if (loginResp.statusCode !in 200..399 || stillOnLogin || cookieStore.isEmpty()) {
                return@withContext false
            }''',
        "BackgroundAuthHelper:login_status_code",
    )

    text = replace_once(
        text,
        r'''            val respDoc = Jsoup.parse(loginResp.body)
            val stillOnLogin = respDoc.selectFirst("#LoginForm, input[type=password]") != null
            if (stillOnLogin || cookieStore.isEmpty()) {''',
        r'''            if (loginResp.statusCode !in 200..399) {
                return false to "Palvelinvirhe kirjautumisessa (HTTP ${loginResp.statusCode})."
            }
            val respDoc = Jsoup.parse(loginResp.body)
            val stillOnLogin = respDoc.selectFirst("#LoginForm, input[type=password]") != null
            if (stillOnLogin || cookieStore.isEmpty()) {''',
        "BackgroundAuthHelper:testCredentials_status_code",
    )

    text = replace_once(
        text,
        r'''            updated.forEach { (k, v) ->
                if (original[k] != v) {
                    cm.setCookie(baseUrl, "$k=$v; Path=/$secureAttr")
                }
            }
            cm.flush()''',
        r'''            updated.forEach { (k, v) ->
                if (original[k] != v) {
                    cm.setCookie(baseUrl, "$k=$v; Path=/$secureAttr")
                }
            }
            original.keys.forEach { k ->
                if (k !in updated) {
                    cm.setCookie(baseUrl, "$k=; Max-Age=0; Path=/$secureAttr")
                }
            }
            cm.flush()''',
        "BackgroundAuthHelper:expire_removed_cookies",
    )

    text = replace_once(
        text,
        r'''        if (anyNeedsLogin) {
            if (!ensureAuthenticatedSession(context)) return@withContext null
            cookies = readCookiesFromManager()
            responses = fetchAllParallel(cookies)
        }''',
        r'''        if (anyNeedsLogin) {
            if (!ensureAuthenticatedSession(context, forceRefresh = true)) return@withContext null
            cookies = readCookiesFromManager()
            responses = fetchAllParallel(cookies)
        }''',
        "BackgroundAuthHelper:force_reauth_on_fetch",
    )
    return text


def patch_stamping_web_helper(text: str) -> str:
    if "object StampingWebHelper {" not in text:
        raise RuntimeError("[StampingWebHelper] Odottamaton tiedostorakenne.")
    return r'''package fi.numeron.vuorovahti

import org.json.JSONObject
import org.json.JSONTokener

/**
 * Jaettu JS- ja tilantarkistuslogiikka MainActivitylle ja QuickStampActivitylle.
 */
object StampingWebHelper {

    fun buildClickStampJs(wantIn: Boolean): String {
        val expectedDir = if (wantIn) "IN" else "OUT"
        val wordPattern = if (wantIn) {
            "(?:^|[^a-zäöå])(sisään|in)(?:$|[^a-zäöå])"
        } else {
            "(?:^|[^a-zäöå])(ulos|out)(?:$|[^a-zäöå])"
        }
        return """
        (function() {
            var btn = document.getElementById('punchButton');
            if (!btn) return JSON.stringify({ status: 'NO_BUTTON' });
            var btnText = (btn.innerText || btn.textContent || '').trim();
            if (!btnText) return JSON.stringify({ status: 'NO_BUTTON' });

            var dirEl = document.querySelector('[data-next-stamp-direction]');
            var nextDir = dirEl ? (dirEl.getAttribute('data-next-stamp-direction') || '').trim().toUpperCase() : '';

            var firstRow = '';
            var firstRowId = '';
            var rowEl = document.querySelector('#table-latest-stamps tbody tr, #table-latest-stamps tr');
            if (rowEl) {
                firstRow = (rowEl.innerText || rowEl.textContent || '').replace(/\s+/g, ' ').trim();
                var idInput = rowEl.querySelector('input[name^="RowID_"]');
                if (idInput && idInput.value) firstRowId = String(idInput.value).trim();
            }

            var matchesDir = false;
            if (nextDir === 'IN' || nextDir === 'OUT') {
                matchesDir = (nextDir === '$expectedDir');
            } else {
                var rx = new RegExp('$wordPattern', 'i');
                matchesDir = rx.test(btnText);
            }

            if (matchesDir) {
                btn.click();
                return JSON.stringify({ status: 'CLICKED', dir: nextDir, btn: btnText, row: firstRow, rowId: firstRowId });
            } else {
                return JSON.stringify({ status: 'WRONG_DIRECTION', dir: nextDir, btn: btnText, row: firstRow, rowId: firstRowId });
            }
        })();
        """.trimIndent()
    }

    fun buildVerifyStampJs(): String = """
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
            var dirEl = document.querySelector('[data-next-stamp-direction]');
            var nextDir = dirEl ? (dirEl.getAttribute('data-next-stamp-direction') || '').trim().toUpperCase() : '';
            var btn = document.getElementById('punchButton');
            var btnText = btn ? (btn.innerText || btn.textContent || '').trim() : '';
            var firstRow = '';
            var firstRowId = '';
            var rowEl = document.querySelector('#table-latest-stamps tbody tr, #table-latest-stamps tr');
            if (rowEl) {
                firstRow = (rowEl.innerText || rowEl.textContent || '').replace(/\s+/g, ' ').trim();
                var idInput = rowEl.querySelector('input[name^="RowID_"]');
                if (idInput && idInput.value) firstRowId = String(idInput.value).trim();
            }
            return JSON.stringify({ dir: nextDir, btn: btnText, row: firstRow, rowId: firstRowId, expired: expired });
        })();
    """.trimIndent()

    fun parseJsonResult(rawResult: String?): JSONObject? {
        return try {
            if (rawResult != null && rawResult != "null") {
                val unescaped = JSONTokener(rawResult).nextValue() as? String
                if (unescaped != null) JSONObject(unescaped) else null
            } else {
                null
            }
        } catch (_: Exception) {
            null
        }
    }

    fun isStampConfirmed(
        wantIn: Boolean,
        beforeDir: String,
        beforeBtn: String,
        beforeRow: String,
        beforeRowId: String,
        nowDir: String,
        nowBtn: String,
        nowRow: String,
        nowRowId: String
    ): Boolean {
        val oppositeDir = if (wantIn) "OUT" else "IN"
        val dirFlipped = nowDir.equals(oppositeDir, ignoreCase = true) &&
            !nowDir.equals(beforeDir, ignoreCase = true)
        val rowIdChanged = nowRowId.isNotEmpty() && nowRowId != beforeRowId
        val targetRegex = if (wantIn) {
            Regex("(?:^|[^a-zäöå])(sisään|in)(?:$|[^a-zäöå])", RegexOption.IGNORE_CASE)
        } else {
            Regex("(?:^|[^a-zäöå])(ulos|out)(?:$|[^a-zäöå])", RegexOption.IGNORE_CASE)
        }
        val buttonFlipped = nowBtn.isNotEmpty() && nowBtn != beforeBtn && !targetRegex.containsMatchIn(nowBtn)
        val rowUpdated = nowRow.isNotEmpty() && nowRow != beforeRow
        return dirFlipped || rowIdChanged || buttonFlipped || rowUpdated
    }
}
'''


def patch_quick_stamp_activity(text: str) -> str:
    text = replace_once(
        text,
        r'''            if (!isCompleted) {
                statusText.text = "Avataan työaikaleimaus…"
                startHiddenStampingWebView(baseUrl, targetText)
            }''',
        r'''            if (!isCompleted) {
                statusText.text = if (en) "Opening time stamping…" else "Avataan työaikaleimaus…"
                startHiddenStampingWebView(baseUrl, wantIn = !isEnding, targetText = targetText)
            }''',
        "QuickStampActivity:processIntent_call",
    )

    text = replace_once(
        text,
        r'''                val oldHistory = prefs.getString("demo_stamp_history", "") ?: ""
                val newHistory = "$nowDate | $nowTime | $targetText\n$oldHistory"''',
        r'''                val yest = LocalDate.now().minusDays(1).format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
                val defaultHistory = "$yest | 14:30 | Ulos\n$yest | 07:00 | Sisään"
                val oldHistory = prefs.getString("demo_stamp_history", defaultHistory) ?: defaultHistory
                val newHistory = "$nowDate | $nowTime | $targetText\n$oldHistory"''',
        "QuickStampActivity:demo_default_history",
    )

    text = replace_once(
        text,
        r'''    @SuppressLint("SetJavaScriptEnabled")
    private fun startHiddenStampingWebView(baseUrl: String, targetText: String) {''',
        r'''    @SuppressLint("SetJavaScriptEnabled")
    private fun startHiddenStampingWebView(baseUrl: String, wantIn: Boolean, targetText: String) {''',
        "QuickStampActivity:startHiddenStampingWebView_sig",
    )

    text = replace_once(
        text,
        r'''        webHolder?.addView(wv, ViewGroup.LayoutParams(1, 1))
        hiddenWebView = wv''',
        r'''        webHolder?.addView(wv, ViewGroup.LayoutParams(1, 1))
        hiddenWebView = wv
        wv.resumeTimers()
        wv.onResume()''',
        "QuickStampActivity:resumeTimers",
    )

    text = replace_once(
        text,
        r'''            override fun onReceivedError(
                view: WebView?,
                errorCode: Int,
                description: String?,
                failingUrl: String?
            ) {
                if (!isCompleted && failingUrl?.contains(baseUrl, ignoreCase = true) == true) {
                    showFinalState(
                        title = "Yhteysvirhe",
                        subtitle = "Verkkoyhteys epäonnistui",
                        badgeText = "!",
                        badgeFillHex = "#3B181E",
                        badgeStrokeHex = "#EF4444",
                        badgeTextHex = "#F87171",
                        closeDelayMs = 1600L
                    )
                }
            }''',
        r'''            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: android.webkit.WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame != true || isCompleted) return
                val code = error?.errorCode ?: 0
                if (code == -1 || code == WebViewClient.ERROR_UNKNOWN) return
                showFinalState(
                    title = "Yhteysvirhe",
                    subtitle = "Verkkoyhteys epäonnistui",
                    badgeText = "!",
                    badgeFillHex = "#3B181E",
                    badgeStrokeHex = "#EF4444",
                    badgeTextHex = "#F87171",
                    closeDelayMs = 1600L
                )
            }''',
        "QuickStampActivity:onReceivedError_mainFrame",
    )

    text = replace_once(
        text,
        r'''                when {
                    url.contains("/Login/Login", ignoreCase = true) -> {
                        if (!loginAttempted) {
                            loginAttempted = true
                            statusText.text = "Vahvistetaan kirjautuminen…"
                            submitAutoLogin(view)
                        } else {
                            showFinalState(
                                title = "Kirjautuminen epäonnistui",
                                subtitle = "Tarkista käyttäjätunnus ja salasana",
                                badgeText = "!",
                                badgeFillHex = "#3B181E",
                                badgeStrokeHex = "#EF4444",
                                badgeTextHex = "#F87171",
                                closeDelayMs = 1700L
                            )
                        }
                    }

                    url.contains("/WorktimeStamping", ignoreCase = true) -> {
                        if (!stampClicked) {
                            triggerStampClick(view, targetText, 0) {
                                stampClicked = true
                            }
                        }
                    }

                    else -> {
                        view?.loadUrl("$baseUrl/WorktimeStamping")
                    }
                }''',
        r'''                when {
                    url.contains("/Login/LogOff", ignoreCase = true) -> {
                        view?.loadUrl("$baseUrl/Login/Login")
                    }

                    url.contains("/Login/Login", ignoreCase = true) -> {
                        if (!loginAttempted) {
                            loginAttempted = true
                            statusText.text = "Vahvistetaan kirjautuminen…"
                            submitAutoLogin(view)
                        } else {
                            showFinalState(
                                title = "Kirjautuminen epäonnistui",
                                subtitle = "Tarkista käyttäjätunnus ja salasana",
                                badgeText = "!",
                                badgeFillHex = "#3B181E",
                                badgeStrokeHex = "#EF4444",
                                badgeTextHex = "#F87171",
                                closeDelayMs = 1700L
                            )
                        }
                    }

                    url.contains("/WorktimeStamping", ignoreCase = true) -> {
                        if (!stampClicked) {
                            triggerStampClick(view, wantIn, targetText, 0) {
                                stampClicked = true
                            }
                        }
                    }

                    else -> {
                        view?.loadUrl("$baseUrl/WorktimeStamping")
                    }
                }''',
        "QuickStampActivity:onPageFinished_logoff_and_wantIn",
    )

    text = replace_once(
        text,
        r'''    private fun triggerStampClick(
        view: WebView?,
        targetText: String,
        attempt: Int,
        onClicked: () -> Unit
    ) {
        if (view == null || isCompleted) return
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

        view.evaluateJavascript(js) { rawResult ->
            if (isCompleted) return@evaluateJavascript
            val obj = parseJsonResult(rawResult)
            val status = obj?.optString("status", "") ?: ""

            when {
                status == "CLICKED" -> {
                    onClicked()
                    val beforeBtn = obj?.optString("btn", "") ?: ""
                    val beforeRow = obj?.optString("row", "") ?: ""
                    statusText.text = "Lähetetään leimaus ($targetText)…"
                    verifyStampResult(view, targetText, beforeBtn, beforeRow, 0)
                }

                status == "WRONG_DIRECTION" -> {
                    showFinalState(
                        title = "Ei leimattu",
                        subtitle = "Olet jo leimannut tilaan: $targetText",
                        badgeText = "!",
                        badgeFillHex = "#1E3A5F",
                        badgeStrokeHex = "#38BDF8",
                        badgeTextHex = "#7DD3FC",
                        closeDelayMs = 1400L
                    )
                }

                status == "NO_BUTTON" && attempt < 12 -> {
                    mainHandler.postDelayed({
                        triggerStampClick(view, targetText, attempt + 1, onClicked)
                    }, 250L)
                }

                else -> {
                    showFinalState(
                        title = "Leimaus epäonnistui",
                        subtitle = "Leimauspainiketta ei löytynyt sivulta",
                        badgeText = "!",
                        badgeFillHex = "#3B181E",
                        badgeStrokeHex = "#EF4444",
                        badgeTextHex = "#F87171",
                        closeDelayMs = 1600L
                    )
                }
            }
        }
    }

    private fun verifyStampResult(
        view: WebView?,
        targetText: String,
        beforeBtn: String,
        beforeRow: String,
        checkAttempt: Int
    ) {
        if (view == null || isCompleted) return
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

        mainHandler.postDelayed({
            if (isCompleted || isFinishing || isDestroyed) return@postDelayed
            view.evaluateJavascript(verifyJs) { rawResult ->
                if (isCompleted) return@evaluateJavascript
                val obj = parseJsonResult(rawResult)
                val nowBtn = obj?.optString("btn", "") ?: ""
                val nowRow = obj?.optString("row", "") ?: ""
                val sessionExpired = obj?.optBoolean("expired", false) ?: false

                if (sessionExpired) {
                    if (!sessionRetried) {
                        sessionRetried = true
                        statusText.text = "Uusitaan istuntoa…"
                        getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                            .edit()
                            .putLong("last_valid_session_ms", 0L)
                            .apply()
                        val baseUrl = UrlNormalizer.getSavedBaseUrl(this)
                        scope.launch {
                            BackgroundAuthHelper.ensureAuthenticatedSession(this@QuickStampActivity)
                            if (!isCompleted && baseUrl.isNotEmpty()) {
                                startHiddenStampingWebView(baseUrl, targetText)
                            }
                        }
                    } else {
                        showFinalState(
                            title = "Istunto vanhentunut",
                            subtitle = "Avaa sovellus ja tarkista kirjautuminen",
                            badgeText = "!",
                            badgeFillHex = "#3B181E",
                            badgeStrokeHex = "#EF4444",
                            badgeTextHex = "#F87171",
                            closeDelayMs = 1700L
                        )
                    }
                    return@evaluateJavascript
                }

                val buttonFlipped = nowBtn.isNotEmpty() && nowBtn != beforeBtn &&
                    nowBtn.lowercase().indexOf(targetLower) == -1
                val rowUpdated = nowRow.isNotEmpty() && nowRow != beforeRow

                if (buttonFlipped || rowUpdated) {
                    CookieManager.getInstance().flush()
                    val nowTime = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
                    showFinalState(
                        title = "Leimaus vahvistettu",
                        subtitle = "$targetText • klo $nowTime",
                        badgeText = "✓",
                        badgeFillHex = "#0F2E26",
                        badgeStrokeHex = "#10B981",
                        badgeTextHex = "#34D399",
                        closeDelayMs = 1150L
                    )
                } else if (checkAttempt < 25) {
                    if (checkAttempt == 2) {
                        statusText.text = "Vahvistetaan leimausta…"
                    }
                    verifyStampResult(view, targetText, beforeBtn, beforeRow, checkAttempt + 1)
                } else {
                    showFinalState(
                        title = "Vahvistus viivästyi",
                        subtitle = "Tarkista leimaustila sovelluksesta",
                        badgeText = "!",
                        badgeFillHex = "#3B2810",
                        badgeStrokeHex = "#F59E0B",
                        badgeTextHex = "#FBBF24",
                        closeDelayMs = 1700L
                    )
                }
            }
        }, 280L)
    }''',
        r'''    private fun triggerStampClick(
        view: WebView?,
        wantIn: Boolean,
        targetText: String,
        attempt: Int,
        onClicked: () -> Unit
    ) {
        if (view == null || isCompleted) return

        view.evaluateJavascript(StampingWebHelper.buildClickStampJs(wantIn)) { rawResult ->
            if (isCompleted) return@evaluateJavascript
            val obj = StampingWebHelper.parseJsonResult(rawResult)
            val status = obj?.optString("status", "") ?: ""

            when {
                status == "CLICKED" -> {
                    onClicked()
                    val beforeDir = obj?.optString("dir", "") ?: ""
                    val beforeBtn = obj?.optString("btn", "") ?: ""
                    val beforeRow = obj?.optString("row", "") ?: ""
                    val beforeRowId = obj?.optString("rowId", "") ?: ""
                    statusText.text = "Lähetetään leimaus ($targetText)…"
                    verifyStampResult(view, wantIn, targetText, beforeDir, beforeBtn, beforeRow, beforeRowId, 0)
                }

                status == "WRONG_DIRECTION" -> {
                    showFinalState(
                        title = "Ei leimattu",
                        subtitle = "Olet jo leimannut tilaan: $targetText",
                        badgeText = "!",
                        badgeFillHex = "#1E3A5F",
                        badgeStrokeHex = "#38BDF8",
                        badgeTextHex = "#7DD3FC",
                        closeDelayMs = 1400L
                    )
                }

                status == "NO_BUTTON" && attempt < 12 -> {
                    mainHandler.postDelayed({
                        triggerStampClick(view, wantIn, targetText, attempt + 1, onClicked)
                    }, 250L)
                }

                else -> {
                    showFinalState(
                        title = "Leimaus epäonnistui",
                        subtitle = "Leimauspainiketta ei löytynyt sivulta",
                        badgeText = "!",
                        badgeFillHex = "#3B181E",
                        badgeStrokeHex = "#EF4444",
                        badgeTextHex = "#F87171",
                        closeDelayMs = 1600L
                    )
                }
            }
        }
    }

    private fun verifyStampResult(
        view: WebView?,
        wantIn: Boolean,
        targetText: String,
        beforeDir: String,
        beforeBtn: String,
        beforeRow: String,
        beforeRowId: String,
        checkAttempt: Int
    ) {
        if (view == null || isCompleted) return

        mainHandler.postDelayed({
            if (isCompleted || isFinishing || isDestroyed) return@postDelayed
            view.evaluateJavascript(StampingWebHelper.buildVerifyStampJs()) { rawResult ->
                if (isCompleted) return@evaluateJavascript
                val obj = StampingWebHelper.parseJsonResult(rawResult)
                val nowDir = obj?.optString("dir", "") ?: ""
                val nowBtn = obj?.optString("btn", "") ?: ""
                val nowRow = obj?.optString("row", "") ?: ""
                val nowRowId = obj?.optString("rowId", "") ?: ""
                val sessionExpired = obj?.optBoolean("expired", false) ?: false

                if (sessionExpired) {
                    if (!sessionRetried) {
                        sessionRetried = true
                        statusText.text = "Uusitaan istuntoa…"
                        getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                            .edit()
                            .putLong("last_valid_session_ms", 0L)
                            .apply()
                        val baseUrl = UrlNormalizer.getSavedBaseUrl(this)
                        scope.launch {
                            BackgroundAuthHelper.ensureAuthenticatedSession(
                                this@QuickStampActivity,
                                forceRefresh = true
                            )
                            if (!isCompleted && baseUrl.isNotEmpty()) {
                                startHiddenStampingWebView(baseUrl, wantIn, targetText)
                            }
                        }
                    } else {
                        showFinalState(
                            title = "Istunto vanhentunut",
                            subtitle = "Avaa sovellus ja tarkista kirjautuminen",
                            badgeText = "!",
                            badgeFillHex = "#3B181E",
                            badgeStrokeHex = "#EF4444",
                            badgeTextHex = "#F87171",
                            closeDelayMs = 1700L
                        )
                    }
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
                    CookieManager.getInstance().flush()
                    val nowTime = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
                    showFinalState(
                        title = "Leimaus vahvistettu",
                        subtitle = "$targetText • klo $nowTime",
                        badgeText = "✓",
                        badgeFillHex = "#0F2E26",
                        badgeStrokeHex = "#10B981",
                        badgeTextHex = "#34D399",
                        closeDelayMs = 1150L
                    )
                } else if (checkAttempt < 25) {
                    if (checkAttempt == 2) {
                        statusText.text = "Vahvistetaan leimausta…"
                    }
                    verifyStampResult(
                        view, wantIn, targetText, beforeDir, beforeBtn, beforeRow, beforeRowId, checkAttempt + 1
                    )
                } else {
                    showFinalState(
                        title = "Vahvistus viivästyi",
                        subtitle = "Tarkista leimaustila sovelluksesta",
                        badgeText = "!",
                        badgeFillHex = "#3B2810",
                        badgeStrokeHex = "#F59E0B",
                        badgeTextHex = "#FBBF24",
                        closeDelayMs = 1700L
                    )
                }
            }
        }, 280L)
    }''',
        "QuickStampActivity:shared_stamping_helper",
    )
    return text


def patch_main_activity(text: str) -> str:
    text = replace_once(
        text,
        r'''                withContext(Dispatchers.Main) {
                    val en = DemoModeHelper.isEnglish(this@MainActivity)
                    if (syncCalendar && calId == null) {
                        Toast.makeText(
                            this@MainActivity,
                            if (en) "Calendar permission or calendar missing" else "Kalenterioikeus tai kalenteri puuttuu",''',
        r'''                withContext(Dispatchers.Main) {
                    if (isFinishing || isDestroyed) return@withContext
                    val en = DemoModeHelper.isEnglish(this@MainActivity)
                    if (syncCalendar && calId == null) {
                        Toast.makeText(
                            this@MainActivity,
                            if (en) "Calendar permission or calendar missing" else "Kalenterioikeus tai kalenteri puuttuu",''',
        "MainActivity:demo_sync_lifecycle_guard",
    )

    text = replace_once(
        text,
        r'''                when {
                    url.contains("/Login/Login", ignoreCase = true) -> {
                        isAutoSubmittingLogin = true
                        startSnapshotTransition()
                        handleAutoLogin()
                        return
                    }''',
        r'''                when {
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
                    }''',
        "MainActivity:onPageFinished_logoff",
    )

    text = replace_once(
        text,
        r'''            #FullDaySwitch.active,
            #SeriesRequestSwitch.active {
                background-color: #1982C4 !important;
                border-color: #38BDF8 !important;
            }''',
        r'''            #FullDaySwitch.active,
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
            }''',
        "MainActivity:dark_theme_datetimepicker_switches_alerts",
    )

    text = replace_once(
        text,
        r'''            /* === 8. KALENTERI: LUETTELONÄKYMÄ (/Calendar/List) === */
            #calendar-content {
                height: auto !important;
                overflow-y: visible !important;
            }''',
        r'''            /* === 8. KALENTERI: LUETTELONÄKYMÄ (/Calendar/List) === */
            .schedule-content #calendar-content {
                height: calc(100vh - 115px) !important;
                overflow-y: auto !important;
                -webkit-overflow-scrolling: touch !important;
            }''',
        "MainActivity:list_view_infinite_scroll",
    )

    text = replace_once(
        text,
        r'''                        window.vvApplyStampingColors = applyStampingColors;
                        applyStampingColors();
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
                        }''',
        r'''                        window.vvApplyStampingColors = applyStampingColors;
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
                        }''',
        "MainActivity:stamping_color_observers",
    )

    text = replace_once(
        text,
        r'''                    document.addEventListener('click', function(e) {
                        if (isForgotOpenTrigger(e.target)) {
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
                    watchStampPageDom();''',
        r'''                    document.addEventListener('click', function(e) {
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
                    watchStampPageDom();''',
        "MainActivity:forgot_stamp_panel_open_and_close",
    )

    text = replace_once(
        text,
        r'''                    document.addEventListener('click', function(e) {
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
                    }, false);''',
        r'''                    document.addEventListener('click', function(e) {
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
                    }, true);''',
        "MainActivity:quick_request_capture_phase",
    )

    text = replace_once(
        text,
        r'''        val rawUser = SecureCredentialManager.getUsername(this) ?: ""
        val rawPass = SecureCredentialManager.getPassword(this) ?: ""
        if (rawUser.isEmpty() || rawPass.isEmpty()) return''',
        r'''        val rawUser = SecureCredentialManager.getUsername(this) ?: ""
        val rawPass = SecureCredentialManager.getPassword(this) ?: ""
        if (rawUser.isEmpty() || rawPass.isEmpty()) {
            isAutoSubmittingLogin = false
            endSnapshotTransition()
            return
        }''',
        "MainActivity:handleAutoLogin_empty_creds",
    )

    text = replace_once(
        text,
        r'''        startSnapshotTransition {
            scope.launch {
                val ok = BackgroundAuthHelper.ensureAuthenticatedSession(this@MainActivity)''',
        r'''        startSnapshotTransition {
            scope.launch {
                val ok = BackgroundAuthHelper.ensureAuthenticatedSession(
                    this@MainActivity,
                    forceRefresh = true
                )''',
        "MainActivity:handleWebSessionExpired_forceRefresh",
    )

    text = replace_once(
        text,
        r'''    private fun handleStampingPage(attempt: Int = 0) {
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
                    val en = DemoModeHelper.isEnglish(this)
                    val dirLabel = if (en) (if (targetText == "Sisään") "In" else "Out") else targetText
                    Toast.makeText(this, if (en) "Stamping ($dirLabel)..." else "Leimataan ($targetText)...", Toast.LENGTH_SHORT).show()
                    verifyStampAndClose(targetText, beforeBtn, beforeRow, 0)
                }
                status == "WRONG_DIRECTION" -> {
                    pendingAction = Action.NONE
                    inFlightStampAction = Action.NONE
                    val en = DemoModeHelper.isEnglish(this)
                    val dirLabel = if (en) (if (targetText == "Sisään") "In" else "Out") else targetText
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

                if (StampingWebHelper.isStampConfirmed(targetLower, beforeBtn, beforeRow, nowBtn, nowRow)) {
                    inFlightStampAction = Action.NONE
                    CookieManager.getInstance().flush()
                    // Poistettu ylimääräinen Toast, luotetaan visuaaliseen tilaan
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                } else if (checkAttempt < 25) {
                    verifyStampAndClose(targetText, beforeBtn, beforeRow, checkAttempt + 1)
                } else {
                    Toast.makeText(
                        this,
                        if (DemoModeHelper.isEnglish(this)) "Could not verify stamp automatically – please check status on screen" else "Leimausta ei voitu vahvistaa automaattisesti – tarkista tila ruudulta",
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        }, 300L)
    }''',
        r'''    private fun handleStampingPage(attempt: Int = 0) {
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
    }''',
        "MainActivity:shared_stamping_helper",
    )

    text = replace_once(
        text,
        r'''            withContext(Dispatchers.Main) {
                val en = DemoModeHelper.isEnglish(this@MainActivity)
                if (syncCalendar && calId == null) {
                    Toast.makeText(
                        this@MainActivity,
                        if (en) "Shifts fetched (${allShifts.size}), but no calendar is selected"''',
        r'''            withContext(Dispatchers.Main) {
                if (isFinishing || isDestroyed) return@withContext
                val en = DemoModeHelper.isEnglish(this@MainActivity)
                if (syncCalendar && calId == null) {
                    Toast.makeText(
                        this@MainActivity,
                        if (en) "Shifts fetched (${allShifts.size}), but no calendar is selected"''',
        "MainActivity:processSyncedCalendarPages_lifecycle_guard",
    )

    text = replace_once(
        text,
        r'''    override fun onPause() {
        try {
            webView.onPause()
            webView.pauseTimers()
        } catch (_: Exception) {}
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        try {
            webView.resumeTimers()
            webView.onResume()
        } catch (_: Exception) {}
    }''',
        r'''    override fun onPause() {
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
    }''',
        "MainActivity:remove_global_pauseTimers",
    )
    return text


def patch_calendar_change_tracker(text: str) -> str:
    text = replace_once(
        text,
        r'''    fun revertSingleChange(context: Context, item: CalendarChangeItem): Boolean {
        return try {
            val resolver = context.contentResolver
            when (item.type) {
                ChangeType.ADDED -> {
                    var removedFromCal = false
                    val eid = item.eventId
                    if (eid != null && eid > 0L) {
                        val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, eid)
                        if (resolver.delete(uri, null, null) > 0) {
                            removedFromCal = true
                        }
                    }
                    if (!removedFromCal) {
                        val sel = "${CalendarContract.Events.CALENDAR_ID} = ? AND ${CalendarContract.Events.TITLE} = ? AND ${CalendarContract.Events.DTSTART} = ? AND ${CalendarContract.Events.DTEND} = ?"
                        val args = arrayOf(
                            item.calendarId.toString(),
                            item.title,
                            item.startMs.toString(),
                            item.endMs.toString()
                        )
                        resolver.delete(CalendarContract.Events.CONTENT_URI, sel, args)
                    }
                }
                ChangeType.MODIFIED -> {
                    val prevTitle = item.prevTitle
                    val prevStart = item.prevStartMs
                    val prevEnd = item.prevEndMs
                    if (!prevTitle.isNullOrEmpty() && prevStart != null && prevEnd != null && prevStart > 0L && prevEnd > 0L) {
                        val values = ContentValues().apply {
                            put(CalendarContract.Events.TITLE, prevTitle)
                            if (item.prevLocation != null) {
                                put(CalendarContract.Events.EVENT_LOCATION, item.prevLocation)
                            }
                            if (item.prevDescription != null) {
                                put(CalendarContract.Events.DESCRIPTION, item.prevDescription)
                            }
                            put(CalendarContract.Events.DTSTART, prevStart)
                            put(CalendarContract.Events.DTEND, prevEnd)
                            put(CalendarContract.Events.ALL_DAY, if (item.prevIsAllDay) 1 else 0)
                            put(
                                CalendarContract.Events.EVENT_TIMEZONE,
                                if (item.prevIsAllDay) "UTC" else ZoneId.systemDefault().id
                            )
                        }
                        var restored = false
                        val eid = item.eventId
                        if (eid != null && eid > 0L) {
                            val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, eid)
                            if (resolver.update(uri, values, null, null) > 0) {
                                restored = true
                            }
                        }
                        if (!restored) {
                            val sel = "${CalendarContract.Events.CALENDAR_ID} = ? AND ${CalendarContract.Events.TITLE} = ? AND ${CalendarContract.Events.DTSTART} = ?"
                            val args = arrayOf(
                                item.calendarId.toString(),
                                item.title,
                                item.startMs.toString()
                            )
                            resolver.update(CalendarContract.Events.CONTENT_URI, values, sel, args)
                        }
                    }
                }
                ChangeType.REMOVED -> {
                    val targetCalId = if (item.calendarId > 0L) {
                        item.calendarId
                    } else {
                        CalendarSyncHelper.getTargetCalendarId(context) ?: -1L
                    }
                    if (targetCalId > 0L) {
                        val values = ContentValues().apply {
                            put(CalendarContract.Events.CALENDAR_ID, targetCalId)
                            put(CalendarContract.Events.TITLE, item.title)
                            put(CalendarContract.Events.EVENT_LOCATION, item.location)
                            put(CalendarContract.Events.DESCRIPTION, item.description)
                            put(CalendarContract.Events.DTSTART, item.startMs)
                            put(CalendarContract.Events.DTEND, item.endMs)
                            put(CalendarContract.Events.ALL_DAY, if (item.isAllDay) 1 else 0)
                            put(
                                CalendarContract.Events.EVENT_TIMEZONE,
                                if (item.isAllDay) "UTC" else ZoneId.systemDefault().id
                            )
                        }
                        resolver.insert(CalendarContract.Events.CONTENT_URI, values)
                    }
                }
            }
            true
        } catch (_: Exception) {
            false
        }
    }

    fun revertSingleChangeAndSave(context: Context, item: CalendarChangeItem): Boolean {
        if (!revertSingleChange(context, item)) return false
        val remaining = getLastChanges(context).filterNot { it.id == item.id }
        saveChanges(context, remaining)
        CalendarSyncHelper.getTargetCalendarId(context)?.let { calId ->
            CalendarSyncHelper.scheduleShiftReminders(context, calId)
        }
        return true
    }

    fun revertAllChanges(context: Context): Int {
        val current = getLastChanges(context).toList()
        val succeededIds = mutableSetOf<String>()
        for (item in current) {
            if (revertSingleChange(context, item)) {
                succeededIds.add(item.id)
            }
        }
        if (succeededIds.isNotEmpty()) {
            val remaining = current.filterNot { it.id in succeededIds }
            saveChanges(context, remaining)
            CalendarSyncHelper.getTargetCalendarId(context)?.let { calId ->
                CalendarSyncHelper.scheduleShiftReminders(context, calId)
            }
        }
        return succeededIds.size
    }

    fun updateSingleEvent(
        context: Context,
        item: CalendarChangeItem,
        newTitle: String,
        newStartMs: Long,
        newEndMs: Long,
        newIsAllDay: Boolean
    ): Boolean {
        return try {
            val resolver = context.contentResolver
            val values = ContentValues().apply {
                put(CalendarContract.Events.TITLE, newTitle)
                put(CalendarContract.Events.DTSTART, newStartMs)
                put(CalendarContract.Events.DTEND, newEndMs)
                put(CalendarContract.Events.ALL_DAY, if (newIsAllDay) 1 else 0)
                put(
                    CalendarContract.Events.EVENT_TIMEZONE,
                    if (newIsAllDay) "UTC" else ZoneId.systemDefault().id
                )
            }
            var updatedInCal = false
            val eid = item.eventId
            if (eid != null && eid > 0L) {
                val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, eid)
                if (resolver.update(uri, values, null, null) > 0) {
                    updatedInCal = true
                }
            }
            if (!updatedInCal) {
                val sel = "${CalendarContract.Events.CALENDAR_ID} = ? AND ${CalendarContract.Events.TITLE} = ? AND ${CalendarContract.Events.DTSTART} = ? AND ${CalendarContract.Events.DTEND} = ?"
                val args = arrayOf(
                    item.calendarId.toString(),
                    item.title,
                    item.startMs.toString(),
                    item.endMs.toString()
                )
                resolver.update(CalendarContract.Events.CONTENT_URI, values, sel, args)
            }
            val updatedItem = item.copy(
                title = newTitle,
                startMs = newStartMs,
                endMs = newEndMs,
                isAllDay = newIsAllDay
            )
            val updatedList = getLastChanges(context).map { if (it.id == item.id) updatedItem else it }
            saveChanges(context, updatedList)
            CalendarSyncHelper.getTargetCalendarId(context)?.let { calId ->
                CalendarSyncHelper.scheduleShiftReminders(context, calId)
            }
            true
        } catch (_: Exception) {
            false
        }
    }''',
        r'''    private fun invalidateShiftCacheAndReschedule(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .remove("cached_work_shifts_json")
            .apply()
        CalendarSyncHelper.getTargetCalendarId(context)?.let { calId ->
            CalendarSyncHelper.scheduleShiftReminders(context, calId)
        }
    }

    fun revertSingleChange(context: Context, item: CalendarChangeItem): Boolean {
        return try {
            val resolver = context.contentResolver
            when (item.type) {
                ChangeType.ADDED -> {
                    var removedFromCal = false
                    val eid = item.eventId
                    if (eid != null && eid > 0L) {
                        val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, eid)
                        if (resolver.delete(uri, null, null) > 0) {
                            removedFromCal = true
                        }
                    }
                    if (!removedFromCal) {
                        val sel = "${CalendarContract.Events.CALENDAR_ID} = ? AND ${CalendarContract.Events.TITLE} = ? AND ${CalendarContract.Events.DTSTART} = ? AND ${CalendarContract.Events.DTEND} = ?"
                        val args = arrayOf(
                            item.calendarId.toString(),
                            item.title,
                            item.startMs.toString(),
                            item.endMs.toString()
                        )
                        removedFromCal = resolver.delete(CalendarContract.Events.CONTENT_URI, sel, args) > 0
                    }
                    removedFromCal
                }
                ChangeType.MODIFIED -> {
                    val prevTitle = item.prevTitle
                    val prevStart = item.prevStartMs
                    val prevEnd = item.prevEndMs
                    var restored = false
                    if (!prevTitle.isNullOrEmpty() && prevStart != null && prevEnd != null && prevStart > 0L && prevEnd > 0L) {
                        val values = ContentValues().apply {
                            put(CalendarContract.Events.TITLE, prevTitle)
                            if (item.prevLocation != null) {
                                put(CalendarContract.Events.EVENT_LOCATION, item.prevLocation)
                            }
                            if (item.prevDescription != null) {
                                put(CalendarContract.Events.DESCRIPTION, item.prevDescription)
                            }
                            put(CalendarContract.Events.DTSTART, prevStart)
                            put(CalendarContract.Events.DTEND, prevEnd)
                            put(CalendarContract.Events.ALL_DAY, if (item.prevIsAllDay) 1 else 0)
                            put(
                                CalendarContract.Events.EVENT_TIMEZONE,
                                if (item.prevIsAllDay) "UTC" else ZoneId.systemDefault().id
                            )
                        }
                        val eid = item.eventId
                        if (eid != null && eid > 0L) {
                            val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, eid)
                            if (resolver.update(uri, values, null, null) > 0) {
                                restored = true
                            }
                        }
                        if (!restored) {
                            val sel = "${CalendarContract.Events.CALENDAR_ID} = ? AND ${CalendarContract.Events.TITLE} = ? AND ${CalendarContract.Events.DTSTART} = ?"
                            val args = arrayOf(
                                item.calendarId.toString(),
                                item.title,
                                item.startMs.toString()
                            )
                            restored = resolver.update(CalendarContract.Events.CONTENT_URI, values, sel, args) > 0
                        }
                    }
                    restored
                }
                ChangeType.REMOVED -> {
                    val targetCalId = if (item.calendarId > 0L) {
                        item.calendarId
                    } else {
                        CalendarSyncHelper.getTargetCalendarId(context) ?: -1L
                    }
                    if (targetCalId > 0L) {
                        val values = ContentValues().apply {
                            put(CalendarContract.Events.CALENDAR_ID, targetCalId)
                            put(CalendarContract.Events.TITLE, item.title)
                            put(CalendarContract.Events.EVENT_LOCATION, item.location)
                            put(CalendarContract.Events.DESCRIPTION, item.description)
                            put(CalendarContract.Events.DTSTART, item.startMs)
                            put(CalendarContract.Events.DTEND, item.endMs)
                            put(CalendarContract.Events.ALL_DAY, if (item.isAllDay) 1 else 0)
                            put(
                                CalendarContract.Events.EVENT_TIMEZONE,
                                if (item.isAllDay) "UTC" else ZoneId.systemDefault().id
                            )
                        }
                        resolver.insert(CalendarContract.Events.CONTENT_URI, values) != null
                    } else {
                        false
                    }
                }
            }
        } catch (_: Exception) {
            false
        }
    }

    fun revertSingleChangeAndSave(context: Context, item: CalendarChangeItem): Boolean {
        if (!revertSingleChange(context, item)) return false
        val remaining = getLastChanges(context).filterNot { it.id == item.id }
        saveChanges(context, remaining)
        invalidateShiftCacheAndReschedule(context)
        return true
    }

    fun revertAllChanges(context: Context): Int {
        val current = getLastChanges(context).toList()
        val succeededIds = mutableSetOf<String>()
        for (item in current) {
            if (revertSingleChange(context, item)) {
                succeededIds.add(item.id)
            }
        }
        if (succeededIds.isNotEmpty()) {
            val remaining = current.filterNot { it.id in succeededIds }
            saveChanges(context, remaining)
            invalidateShiftCacheAndReschedule(context)
        }
        return succeededIds.size
    }

    fun updateSingleEvent(
        context: Context,
        item: CalendarChangeItem,
        newTitle: String,
        newStartMs: Long,
        newEndMs: Long,
        newIsAllDay: Boolean
    ): Boolean {
        if (item.type == ChangeType.REMOVED) return false
        return try {
            val resolver = context.contentResolver
            val values = ContentValues().apply {
                put(CalendarContract.Events.TITLE, newTitle)
                put(CalendarContract.Events.DTSTART, newStartMs)
                put(CalendarContract.Events.DTEND, newEndMs)
                put(CalendarContract.Events.ALL_DAY, if (newIsAllDay) 1 else 0)
                put(
                    CalendarContract.Events.EVENT_TIMEZONE,
                    if (newIsAllDay) "UTC" else ZoneId.systemDefault().id
                )
            }
            var updatedInCal = false
            val eid = item.eventId
            if (eid != null && eid > 0L) {
                val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, eid)
                if (resolver.update(uri, values, null, null) > 0) {
                    updatedInCal = true
                }
            }
            if (!updatedInCal) {
                val sel = "${CalendarContract.Events.CALENDAR_ID} = ? AND ${CalendarContract.Events.TITLE} = ? AND ${CalendarContract.Events.DTSTART} = ? AND ${CalendarContract.Events.DTEND} = ?"
                val args = arrayOf(
                    item.calendarId.toString(),
                    item.title,
                    item.startMs.toString(),
                    item.endMs.toString()
                )
                updatedInCal = resolver.update(CalendarContract.Events.CONTENT_URI, values, sel, args) > 0
            }
            if (!updatedInCal) return false
            val updatedItem = item.copy(
                title = newTitle,
                startMs = newStartMs,
                endMs = newEndMs,
                isAllDay = newIsAllDay
            )
            val updatedList = getLastChanges(context).map { if (it.id == item.id) updatedItem else it }
            saveChanges(context, updatedList)
            invalidateShiftCacheAndReschedule(context)
            true
        } catch (_: Exception) {
            false
        }
    }''',
        "CalendarChangeTracker:revert_and_cache_invalidation",
    )

    text = replace_once(
        text,
        r'''                btnRow.addView(btnEdit)
                btnRow.addView(btnRevert)''',
        r'''                if (item.type != ChangeType.REMOVED) {
                    btnRow.addView(btnEdit)
                }
                btnRow.addView(btnRevert)''',
        "CalendarChangeTracker:hide_edit_on_removed",
    )

    text = replace_once(
        text,
        r'''                    java.util.concurrent.Executors.newSingleThreadExecutor().execute {
                        val ok = revertSingleChangeAndSave(appCtx, item)
                        android.os.Handler(android.os.Looper.getMainLooper()).post {''',
        r'''                    val exec = java.util.concurrent.Executors.newSingleThreadExecutor()
                    exec.execute {
                        val ok = try {
                            revertSingleChangeAndSave(appCtx, item)
                        } finally {
                            exec.shutdown()
                        }
                        android.os.Handler(android.os.Looper.getMainLooper()).post {''',
        "CalendarChangeTracker:shutdown_revert_executor",
    )

    text = replace_once(
        text,
        r'''                setOnClickListener {
                    val reverted = revertAllChanges(context)
                    Toast.makeText(context, "Peruttu $reverted kalenterimuutosta", Toast.LENGTH_LONG).show()
                    dialogRef?.dismiss()
                    onChanged?.invoke()
                }''',
        r'''                setOnClickListener {
                    isEnabled = false
                    val appCtx = context.applicationContext
                    val exec = java.util.concurrent.Executors.newSingleThreadExecutor()
                    exec.execute {
                        val reverted = try {
                            revertAllChanges(appCtx)
                        } finally {
                            exec.shutdown()
                        }
                        android.os.Handler(android.os.Looper.getMainLooper()).post {
                            val act = context as? android.app.Activity
                            if (act != null && (act.isFinishing || act.isDestroyed)) return@post
                            Toast.makeText(appCtx, "Peruttu $reverted kalenterimuutosta", Toast.LENGTH_LONG).show()
                            if (dialogRef?.isShowing == true) {
                                dialogRef?.dismiss()
                            }
                            onChanged?.invoke()
                        }
                    }
                }''',
        "CalendarChangeTracker:revertAll_background_thread",
    )

    text = replace_once(
        text,
        r'''            setOnClickListener {
                dialogRef?.dismiss()
                onChanged?.invoke()
            }''',
        r'''            setOnClickListener {
                clearChanges(context)
                dialogRef?.dismiss()
                onChanged?.invoke()
            }''',
        "CalendarChangeTracker:accept_clears_changes",
    )
    return text


def patch_calendar_sync_helper(text: str) -> str:
    text = replace_once(
        text,
        r'''        if (lower == desiredTitle.lowercase() || lower.startsWith("työvuoro")) return true
        return KNOWN_SHIFT_OR_LEAVE_KEYWORDS.any { kw -> lower.contains(kw) }''',
        r'''        if (lower == desiredTitle.lowercase() || lower.startsWith("työvuoro")) return true
        return KNOWN_SHIFT_OR_LEAVE_KEYWORDS.any { kw ->
            lower == kw || lower.startsWith("$kw ") || lower.startsWith("$kw(") || lower.startsWith("$kw-")
        }''',
        "CalendarSyncHelper:stricter_external_match",
    )

    text = replace_once(
        text,
        r'''        val upcomingShifts = shifts.filter { it.end.isAfter(now) }''',
        r'''        // Jo alkaneita työvuoroja ei ylikirjoiteta toteutuneilla leimausajoilla;
        // koko päivän lomat huomioidaan päättymishetkeen saakka.
        val upcomingShifts = shifts.filter { shift ->
            if (shift.isAllDayLeave) shift.end.isAfter(now) else shift.start.isAfter(now)
        }''',
        "CalendarSyncHelper:skip_started_shifts",
    )
    return text


def patch_numeron_parser(text: str) -> str:
    text = replace_once(
        text,
        r'''    private val finnishMonths = mapOf(
        "tammikuu" to 1, "helmikuu" to 2, "maaliskuu" to 3, "huhtikuu" to 4,
        "toukokuu" to 5, "kesäkuu" to 6, "heinäkuu" to 7, "elokuu" to 8,
        "syyskuu" to 9, "lokakuu" to 10, "marraskuu" to 11, "joulukuu" to 12
    )''',
        r'''    private val finnishMonths = mapOf(
        "tammikuu" to 1, "helmikuu" to 2, "maaliskuu" to 3, "huhtikuu" to 4,
        "toukokuu" to 5, "kesäkuu" to 6, "heinäkuu" to 7, "elokuu" to 8,
        "syyskuu" to 9, "lokakuu" to 10, "marraskuu" to 11, "joulukuu" to 12,
        "january" to 1, "february" to 2, "march" to 3, "april" to 4,
        "may" to 5, "june" to 6, "july" to 7, "august" to 8,
        "september" to 9, "october" to 10, "november" to 11, "december" to 12,
        "januari" to 1, "februari" to 2, "mars" to 3, "maj" to 5,
        "juni" to 6, "juli" to 7, "augusti" to 8, "oktober" to 10
    )''',
        "NumeronParser:multilingual_months",
    )

    text = replace_once(
        text,
        r'''        val leaves = rawShifts.filter { it.isAllDayLeave }.sortedBy { it.start }''',
        r'''        val leaves = rawShifts.filter { it.isAllDayLeave }
            .sortedWith(compareBy<WorkShift> { it.title }.thenBy { it.start })''',
        "NumeronParser:sort_leaves_by_title_and_start",
    )
    return text


def patch_secure_credential_manager(text: str) -> str:
    text = replace_once(
        text,
        r'''            try {
                val appCtx = context.applicationContext
                val masterKey = MasterKey.Builder(appCtx, MasterKey.DEFAULT_MASTER_KEY_ALIAS)
                    .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                    .build()

                EncryptedSharedPreferences.create(
                    appCtx,
                    PREFS_FILE,
                    masterKey,
                    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
                ).also { cachedEncryptedPrefs = it }
            } catch (_: Exception) {
                null
            }''',
        r'''            val appCtx = context.applicationContext
            fun createPrefs(): SharedPreferences {
                val masterKey = MasterKey.Builder(appCtx, MasterKey.DEFAULT_MASTER_KEY_ALIAS)
                    .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                    .build()
                return EncryptedSharedPreferences.create(
                    appCtx,
                    PREFS_FILE,
                    masterKey,
                    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
                )
            }
            try {
                createPrefs().also { cachedEncryptedPrefs = it }
            } catch (_: Exception) {
                try {
                    appCtx.deleteSharedPreferences(PREFS_FILE)
                    val ks = java.security.KeyStore.getInstance("AndroidKeyStore")
                    ks.load(null)
                    if (ks.containsAlias(MasterKey.DEFAULT_MASTER_KEY_ALIAS)) {
                        ks.deleteEntry(MasterKey.DEFAULT_MASTER_KEY_ALIAS)
                    }
                    createPrefs().also { cachedEncryptedPrefs = it }
                } catch (_: Exception) {
                    null
                }
            }''',
        "SecureCredentialManager:keystore_recovery",
    )
    return text


def patch_settings_dialog_helper(text: str) -> str:
    text = replace_once(
        text,
        r'''        var dialogRef: AlertDialog? = null''',
        r'''        var dialogRef: AlertDialog? = null
        var testCredentialsJob: kotlinx.coroutines.Job? = null''',
        "SettingsDialogHelper:testJob_var",
    )

    text = replace_once(
        text,
        r'''                testLoginWithHiddenWebView(context, normalizedUrl, user, pass) { success, message ->''',
        r'''                testCredentialsJob?.cancel()
                testCredentialsJob = testLoginWithHiddenWebView(context, normalizedUrl, user, pass) { success, message ->''',
        "SettingsDialogHelper:track_testJob",
    )

    text = replace_once(
        text,
        r'''            val isDemo = savedUser.isEmpty() || savedPass.isEmpty() || rawOrg.isEmpty() ||
                DemoModeHelper.isDemoCredentials(rawOrg, savedUser, savedPass)

            SecureCredentialManager.saveCredentials(context, savedUser, savedPass)''',
        r'''            val prevUser = SecureCredentialManager.getUsername(context).orEmpty()
            val prevUrl = UrlNormalizer.getSavedBaseUrl(context)

            val isDemo = savedUser.isEmpty() || savedPass.isEmpty() || rawOrg.isEmpty() ||
                UrlNormalizer.isDemoInput(rawOrg) ||
                DemoModeHelper.isDemoCredentials(rawOrg, savedUser, savedPass)

            SecureCredentialManager.saveCredentials(context, savedUser, savedPass)
            if (savedUser != prevUser || savedPass != existingPassword || normalizedUrl != prevUrl) {
                BackgroundAuthHelper.clearSessionCache(context)
            }''',
        "SettingsDialogHelper:clear_session_on_cred_change",
    )

    text = replace_once(
        text,
        r'''        dialog.setOnDismissListener {
            rootContainer.viewTreeObserver.removeOnWindowFocusChangeListener(focusListener)
            billingHelper.destroy()
        }''',
        r'''        dialog.setOnDismissListener {
            testCredentialsJob?.cancel()
            rootContainer.viewTreeObserver.removeOnWindowFocusChangeListener(focusListener)
            billingHelper.destroy()
        }''',
        "SettingsDialogHelper:cancel_testJob_on_dismiss",
    )

    text = replace_once(
        text,
        r'''    private fun testLoginWithHiddenWebView(
        @Suppress("UNUSED_PARAMETER") context: Context,
        baseUrl: String,
        username: String,
        password: String,
        callback: (Boolean, String) -> Unit
    ) {
        CoroutineScope(Dispatchers.IO).launch {''',
        r'''    private fun testLoginWithHiddenWebView(
        @Suppress("UNUSED_PARAMETER") context: Context,
        baseUrl: String,
        username: String,
        password: String,
        callback: (Boolean, String) -> Unit
    ): kotlinx.coroutines.Job {
        return CoroutineScope(Dispatchers.IO).launch {''',
        "SettingsDialogHelper:return_testJob",
    )
    return text


def patch_shift_reminder_receiver(text: str) -> str:
    text = replace_once(
        text,
        r'''            CoroutineScope(Dispatchers.IO).launch {
                try {
                    BackgroundAuthHelper.ensureAuthenticatedSession(appCtx)
                } finally {
                    pendingResult.finish()
                }
            }''',
        r'''            CoroutineScope(Dispatchers.IO).launch {
                try {
                    kotlinx.coroutines.withTimeoutOrNull(7_000L) {
                        BackgroundAuthHelper.ensureAuthenticatedSession(appCtx)
                    }
                } finally {
                    pendingResult.finish()
                }
            }''',
        "ShiftReminderReceiver:goAsync_timeout",
    )

    text = replace_once(
        text,
        r'''        val notifId = if (isEnding) 2002 else 1001''',
        r'''        val notifId = when {
            isTest -> 2999
            isEnding -> 2002
            else -> 1001
        }''',
        "ShiftReminderReceiver:separate_test_notif_id",
    )

    text = replace_once(
        text,
        r'''        fun ensureBackgroundSyncScheduled(context: Context) {
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val syncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
            val shiftReminders = prefs.getBoolean("shift_reminders_enabled", true)
            val trackRequests = prefs.getBoolean("track_requests", true)

            if (!syncCalendar && !shiftReminders && !trackRequests) {
                WorkManager.getInstance(context).cancelUniqueWork("NumeronVuorovahtiSync")
                prefs.edit().remove("next_calendar_sync_ms").apply()
                return
            }

            val nowMs = System.currentTimeMillis()
            val nextTargetMs = computeNextOfficeHourSyncMs(nowMs)
            val delayMs = (nextTargetMs - nowMs).coerceAtLeast(60_000L)

            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val syncRequest = androidx.work.OneTimeWorkRequestBuilder<BackgroundSyncWorker>()
                .setInitialDelay(delayMs, TimeUnit.MILLISECONDS)
                .setConstraints(constraints)
                .build()

            WorkManager.getInstance(context).enqueueUniqueWork(
                "NumeronVuorovahtiSync",
                androidx.work.ExistingWorkPolicy.REPLACE,
                syncRequest
            )

            prefs.edit()
                .putLong("next_calendar_sync_ms", nextTargetMs)
                .apply()
        }''',
        r'''        fun ensureBackgroundSyncScheduled(context: Context, forceReplace: Boolean = false) {
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val syncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
            val shiftReminders = prefs.getBoolean("shift_reminders_enabled", true)
            val trackRequests = prefs.getBoolean("track_requests", true)

            if (!syncCalendar && !shiftReminders && !trackRequests) {
                WorkManager.getInstance(context).cancelUniqueWork("NumeronVuorovahtiSync")
                prefs.edit().remove("next_calendar_sync_ms").apply()
                return
            }

            val nowMs = System.currentTimeMillis()
            val nextTargetMs = computeNextOfficeHourSyncMs(nowMs)
            val delayMs = (nextTargetMs - nowMs).coerceAtLeast(60_000L)

            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val syncRequest = androidx.work.OneTimeWorkRequestBuilder<BackgroundSyncWorker>()
                .setInitialDelay(delayMs, TimeUnit.MILLISECONDS)
                .setConstraints(constraints)
                .build()

            val policy = if (forceReplace) {
                androidx.work.ExistingWorkPolicy.REPLACE
            } else {
                androidx.work.ExistingWorkPolicy.KEEP
            }

            WorkManager.getInstance(context).enqueueUniqueWork(
                "NumeronVuorovahtiSync",
                policy,
                syncRequest
            )

            if (forceReplace || prefs.getLong("next_calendar_sync_ms", 0L) <= nowMs) {
                prefs.edit()
                    .putLong("next_calendar_sync_ms", nextTargetMs)
                    .apply()
            }
        }''',
        "ShiftReminderReceiver:keep_existing_schedule",
    )

    text = replace_once(
        text,
        r'''            ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext)
            Result.success()
        } else {
            Result.retry()
        }''',
        r'''            ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext, forceReplace = true)
            Result.success()
        } else {
            if (runAttemptCount >= 3) {
                ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext, forceReplace = true)
                Result.failure()
            } else {
                Result.retry()
            }
        }''',
        "ShiftReminderReceiver:cap_retries_and_reschedule",
    )

    text = replace_once(
        text,
        r'''    private fun fetchRequestsJson(baseUrl: String): String? {
        return try {
            val cookies = CookieManager.getInstance().getCookie(baseUrl)
            if (cookies.isNullOrBlank()) return null
            val conn = (java.net.URL("$baseUrl/PersonRequests/Read?selectedFilter=active").openConnection() as java.net.HttpURLConnection).apply {
                requestMethod = "POST"
                setRequestProperty("Cookie", cookies)
                setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
                setRequestProperty("X-Requested-With", "XMLHttpRequest")
                doOutput = true
                connectTimeout = 15000
                readTimeout = 15000
            }
            java.io.OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { writer ->
                writer.write("page=1&pageSize=50")
                writer.flush()
            }
            val text = if (conn.responseCode == 200) {
                conn.inputStream.bufferedReader().use { it.readText() }
            } else {
                null
            }
            conn.disconnect()
            if (text != null && text.trim().startsWith("{")) text else null
        } catch (_: Exception) {
            null
        }
    }''',
        r'''    private fun fetchRequestsJson(baseUrl: String): String? {
        var conn: java.net.HttpURLConnection? = null
        return try {
            val cookies = CookieManager.getInstance().getCookie(baseUrl)
            if (cookies.isNullOrBlank()) return null
            conn = (java.net.URL("$baseUrl/PersonRequests/Read?selectedFilter=active").openConnection() as java.net.HttpURLConnection).apply {
                requestMethod = "POST"
                setRequestProperty("Cookie", cookies)
                setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
                setRequestProperty("X-Requested-With", "XMLHttpRequest")
                doOutput = true
                connectTimeout = 15000
                readTimeout = 15000
            }
            java.io.OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { writer ->
                writer.write("page=1&pageSize=50")
                writer.flush()
            }
            val text = if (conn.responseCode == 200) {
                conn.inputStream.bufferedReader().use { it.readText() }
            } else {
                null
            }
            if (text != null && text.trim().startsWith("{")) text else null
        } catch (_: Exception) {
            null
        } finally {
            conn?.disconnect()
        }
    }''',
        "ShiftReminderReceiver:fetchRequestsJson_finally",
    )

    text = replace_once(
        text,
        r'''            val prefs = appContext.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val notifiedIds = prefs.getStringSet("notified_request_ids", emptySet())?.toMutableSet() ?: mutableSetOf()
            var changed = false

            val root = JSONObject(jsonStr)
            val dataArray = root.optJSONArray("data") ?: return

            for (i in 0 until dataArray.length()) {
                val item = dataArray.optJSONObject(i) ?: continue
                val id = item.optInt("Id", -1)
                val statusId = item.optInt("Status", -1)
                val typeName = item.optString("Type", "Toive")
                val statusDesc = item.optString("StatusDescription", "")

                if (id > 0 && (statusId == 50 || statusId == 80 || statusId == 40)) {
                    val key = "${id}_$statusId"
                    if (!notifiedIds.contains(key)) {
                        notifiedIds.add(key)
                        changed = true
                        ShiftReminderReceiver.showRequestDecisionNotification(
                            appContext,
                            if (DemoModeHelper.isEnglish(appContext)) "Request processed: $statusDesc" else "Toive käsitelty: $statusDesc",
                            typeName,
                            id
                        )
                    }
                }
            }
            if (changed) {
                prefs.edit().putStringSet("notified_request_ids", notifiedIds).apply()
            }''',
        r'''            val prefs = appContext.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val baselineInitialized = prefs.getBoolean("requests_baseline_initialized", false)
            val notifiedIds = prefs.getStringSet("notified_request_ids", emptySet())?.toMutableSet() ?: mutableSetOf()
            var changed = false

            val root = JSONObject(jsonStr)
            val dataArray = root.optJSONArray("data") ?: return

            for (i in 0 until dataArray.length()) {
                val item = dataArray.optJSONObject(i) ?: continue
                val id = item.optInt("Id", -1)
                val statusId = item.optInt("Status", -1)
                val typeName = item.optString("Type", "Toive")
                val statusDesc = item.optString("StatusDescription", "")

                if (id > 0 && (statusId == 50 || statusId == 80 || statusId == 40)) {
                    val key = "${id}_$statusId"
                    if (!notifiedIds.contains(key)) {
                        notifiedIds.add(key)
                        changed = true
                        if (baselineInitialized) {
                            ShiftReminderReceiver.showRequestDecisionNotification(
                                appContext,
                                if (DemoModeHelper.isEnglish(appContext)) "Request processed: $statusDesc" else "Toive käsitelty: $statusDesc",
                                typeName,
                                id
                            )
                        }
                    }
                }
            }
            if (changed || !baselineInitialized) {
                prefs.edit()
                    .putStringSet("notified_request_ids", notifiedIds)
                    .putBoolean("requests_baseline_initialized", true)
                    .apply()
            }''',
        "ShiftReminderReceiver:requests_baseline",
    )
    return text


def patch_demo_mode_helper(text: str) -> str:
    text = replace_once(
        text,
        r'''    fun isDemoCredentials(org: String, user: String, pass: String): Boolean {
        return org.trim().equals("demo", ignoreCase = true) &&
            user.trim().equals("demo", ignoreCase = true) &&
            pass.trim().equals("demo", ignoreCase = true)
    }''',
        r'''    fun isDemoCredentials(org: String, user: String, pass: String): Boolean {
        val cleanOrg = org.trim().trimEnd('/')
        val isDemoOrg = cleanOrg.equals("demo", ignoreCase = true) ||
            cleanOrg.equals("demo.numeronwfm.com", ignoreCase = true) ||
            cleanOrg.equals("https://demo.numeronwfm.com", ignoreCase = true)
        return isDemoOrg &&
            user.trim().equals("demo", ignoreCase = true) &&
            pass.trim().equals("demo", ignoreCase = true)
    }''',
        "DemoModeHelper:demo_url_credentials",
    )

    text = replace_once(
        text,
        r'''                """<tr>
                    <td>${p[0]}</td>
                    <td><strong>${p[1]}</strong></td>
                    <td><span class="$badgeClass">${p[2]}</span></td>
                </tr>"""''',
        r'''                val safeDate = android.text.TextUtils.htmlEncode(p[0])
                val safeType = android.text.TextUtils.htmlEncode(p[1])
                val safeStatus = android.text.TextUtils.htmlEncode(p[2])
                """<tr>
                    <td>$safeDate</td>
                    <td><strong>$safeType</strong></td>
                    <td><span class="$badgeClass">$safeStatus</span></td>
                </tr>"""''',
        "DemoModeHelper:html_encode_requests",
    )

    text = replace_once(
        text,
        r'''            val oldHistory = prefs.getString("demo_stamp_history", "") ?: ""
            val newHistory = "$nowDate | $nowTime | $actionLabel\n$oldHistory"''',
        r'''            val yest = LocalDate.now().minusDays(1).format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
            val defaultHistory = "$yest | 14:30 | Ulos\n$yest | 07:00 | Sisään"
            val oldHistory = prefs.getString("demo_stamp_history", defaultHistory) ?: defaultHistory
            val newHistory = "$nowDate | $nowTime | $actionLabel\n$oldHistory"''',
        "DemoModeHelper:preserve_default_stamp_history",
    )

    text = replace_once(
        text,
        r'''            val oldList = prefs.getString("demo_requests", "") ?: ""
            val newList = "$cleanDate | $type | $statusLabel\n$oldList"''',
        r'''            val today = LocalDate.now()
            val fmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")
            val defaultRequests = if (en) {
                "${today.plusDays(5).format(fmt)} | Annual leave | Approved\n${today.plusDays(12).format(fmt)} | Day off | Pending approval"
            } else {
                "${today.plusDays(5).format(fmt)} | Vuosiloma | Hyväksytty\n${today.plusDays(12).format(fmt)} | Vapaapäivä | Odottaa käsittelyä"
            }
            val oldList = prefs.getString("demo_requests", defaultRequests) ?: defaultRequests
            val newList = "$cleanDate | $type | $statusLabel\n$oldList"''',
        "DemoModeHelper:preserve_default_requests",
    )
    return text


def patch_support_billing_helper(text: str) -> str:
    text = replace_once(
        text,
        r'''            if (billingClient.isReady) {
                billingClient.endConnection()
            }''',
        r'''            if (billingClient.connectionState != BillingClient.ConnectionState.CLOSED) {
                billingClient.endConnection()
            }''',
        "SupportBillingHelper:endConnection_connecting",
    )
    return text


PATCH_PLAN = [
    ("build.gradle.kts", 'applicationId = "com.numeron_vuorovahti"', patch_build_gradle),
    ("BackgroundAuthHelper.kt", "object BackgroundAuthHelper", patch_background_auth_helper),
    ("StampingWebHelper.kt", "object StampingWebHelper", patch_stamping_web_helper),
    ("QuickStampActivity.kt", "class QuickStampActivity", patch_quick_stamp_activity),
    ("MainActivity.kt", "class MainActivity", patch_main_activity),
    ("CalendarChangeTracker.kt", "object CalendarChangeTracker", patch_calendar_change_tracker),
    ("CalendarSyncHelper.kt", "object CalendarSyncHelper", patch_calendar_sync_helper),
    ("NumeronParser.kt", "object NumeronParser", patch_numeron_parser),
    ("SecureCredentialManager.kt", "object SecureCredentialManager", patch_secure_credential_manager),
    ("SettingsDialogHelper.kt", "object SettingsDialogHelper", patch_settings_dialog_helper),
    ("ShiftReminderReceiver.kt", "class ShiftReminderReceiver", patch_shift_reminder_receiver),
    ("DemoModeHelper.kt", "object DemoModeHelper", patch_demo_mode_helper),
    ("SupportBillingHelper.kt", "class SupportBillingHelper", patch_support_billing_helper),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Numeron Vuorovahti bugfix patch")
    parser.add_argument("--root", default=".", help="Projektin juurikansio")
    parser.add_argument("--dry-run", action="store_true", help="Tarkista muutokset kirjoittamatta tiedostoja")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    staged_writes: list[tuple[Path, str, str]] = []

    for filename, marker, patch_fn in PATCH_PLAN:
        path = find_file(root, filename, marker)
        raw_bytes = path.read_bytes()
        raw_text = raw_bytes.decode("utf-8")
        eol = "\r\n" if "\r\n" in raw_text else "\n"
        normalized = raw_text.replace("\r\n", "\n")

        patched = patch_fn(normalized)
        if patched == normalized:
            raise RuntimeError(f"[{filename}] Tiedostoon ei tullut muutoksia.")

        final_text = patched.replace("\n", eol)
        staged_writes.append((path, final_text, filename))
        print(f"OK: {path.relative_to(root)}")

    if args.dry_run:
        print(f"\nDRY-RUN OK: {len(staged_writes)} tiedostoa tarkistettu, mitään ei kirjoitettu.")
        return 0

    for path, final_text, _ in staged_writes:
        path.write_text(final_text, encoding="utf-8")

    print(f"\nVALMIS: {len(staged_writes)} tiedostoa päivitetty onnistuneesti.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"VIRHE: {exc}", file=sys.stderr)
        sys.exit(1)
