#!/usr/bin/env python3
"""
Numeron Vuorovahti – kalenterin kuukausiotsikon keskitys, isommat selausnapit,
kuukausi/vuosi-hyppyvalitsin, väärän salasanan lukituksen esto sekä optimoinnit.

Käyttö:
    python3 patch.py --dry-run
    python3 patch.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

IGNORED_DIRS = {".git", ".patch_backups", ".gradle", ".idea", "build", "node_modules", "__pycache__"}


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


def bump_version(text: str) -> str:
    m_code = re.search(r"versionCode\s*=\s*(\d+)", text)
    if not m_code:
        raise RuntimeError("[build.gradle:versionCode] versionCode-määritystä ei löytynyt.")
    old_code = int(m_code.group(1))
    text = text[: m_code.start()] + f"versionCode = {old_code + 1}" + text[m_code.end() :]

    m_name = re.search(r'versionName\s*=\s*"(\d+)\.(\d+)\.(\d+)"', text)
    if not m_name:
        raise RuntimeError("[build.gradle:versionName] versionName-määritystä ei löytynyt.")
    major, minor, patch = int(m_name.group(1)), int(m_name.group(2)), int(m_name.group(3))
    new_name = f"{major}.{minor}.{patch + 1}"
    text = text[: m_name.start()] + f'versionName = "{new_name}"' + text[m_name.end() :]
    print(
        f"  Versio päivitetty: {old_code} -> {old_code + 1}, "
        f"{m_name.group(1)}.{m_name.group(2)}.{m_name.group(3)} -> {new_name}"
    )
    return text


def patch_background_auth_helper(text: str) -> str:
    text = replace_once(
        text,
        r"""    private val cookieSyncLock = Any()
    private val authMutex = Mutex()
    @Volatile
    private var lastAuthSuccessMs: Long = 0L
    @Volatile
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
    }""",
        r"""    private val cookieSyncLock = Any()
    private val authMutex = Mutex()
    @Volatile
    private var lastAuthSuccessMs: Long = 0L
    @Volatile
    private var lastAuthBaseUrl: String = ""
    @Volatile
    private var blockedCredentialFingerprint: String = ""

    fun computeCredentialFingerprint(baseUrl: String, username: String, password: String): String {
        val raw = "${baseUrl.trim()}\u0000${username.trim()}\u0000$password"
        return try {
            val digest = java.security.MessageDigest.getInstance("SHA-256")
                .digest(raw.toByteArray(Charsets.UTF_8))
            digest.joinToString("") { "%02x".format(it) }
        } catch (_: Exception) {
            raw.hashCode().toString()
        }
    }

    fun isCredentialBlocked(context: Context): Boolean {
        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        val username = SecureCredentialManager.getUsername(context).orEmpty()
        val password = SecureCredentialManager.getPassword(context).orEmpty()
        if (baseUrl.isBlank() || username.isBlank() || password.isBlank()) return false
        val fp = computeCredentialFingerprint(baseUrl, username, password)
        if (blockedCredentialFingerprint == fp) return true
        val storedFp = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .getString("failed_auth_fingerprint", "")
            .orEmpty()
        if (storedFp == fp) {
            blockedCredentialFingerprint = fp
            return true
        }
        return false
    }

    fun getBlockedReason(context: Context): String {
        return context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .getString("failed_auth_message", "")
            .orEmpty()
    }

    fun markCredentialFailed(
        context: Context,
        baseUrl: String,
        username: String,
        password: String,
        reason: String = ""
    ) {
        if (baseUrl.isBlank() || username.isBlank() || password.isBlank()) return
        val fp = computeCredentialFingerprint(baseUrl, username, password)
        blockedCredentialFingerprint = fp
        lastAuthSuccessMs = 0L
        lastAuthBaseUrl = ""
        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putString("failed_auth_fingerprint", fp)
            .putString("failed_auth_message", reason)
            .putLong("last_valid_session_ms", 0L)
            .apply()
    }

    fun clearSessionCache(context: Context? = null) {
        lastAuthSuccessMs = 0L
        lastAuthBaseUrl = ""
        blockedCredentialFingerprint = ""
        if (context != null) {
            context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                .edit()
                .putLong("last_valid_session_ms", 0L)
                .remove("failed_auth_fingerprint")
                .remove("failed_auth_message")
                .apply()
            try {
                val cm = CookieManager.getInstance()
                cm.removeAllCookies(null)
                cm.flush()
            } catch (_: Exception) {
            }
        }
    }""",
        "BackgroundAuthHelper:credential_lockout_guard",
    )

    text = replace_once(
        text,
        r"""        if (baseUrl.isBlank() || username.isBlank() || password.isBlank()) {
            return@withContext false
        }

        authMutex.withLock {""",
        r"""        if (baseUrl.isBlank() || username.isBlank() || password.isBlank()) {
            return@withContext false
        }
        if (isCredentialBlocked(context)) {
            return@withContext false
        }

        authMutex.withLock {
            if (isCredentialBlocked(context)) {
                return@withLock false
            }""",
        "BackgroundAuthHelper:skip_if_blocked",
    )

    text = replace_once(
        text,
        r"""            if (loginResp.statusCode !in 200..399 || stillOnLogin || cookieStore.isEmpty()) {
                return@withContext false
            }""",
        r"""            if (loginResp.statusCode !in 200..399 || stillOnLogin || cookieStore.isEmpty()) {
                if (loginResp.statusCode in 200..399 && stillOnLogin) {
                    val errReason = if (loginResp.body.isNotEmpty()) {
                        Jsoup.parse(loginResp.body)
                            .selectFirst(".validation-summary-errors, .alert-danger")
                            ?.text()
                            ?.trim()
                            .orEmpty()
                    } else {
                        ""
                    }
                    markCredentialFailed(
                        context = context,
                        baseUrl = baseUrl,
                        username = username,
                        password = password,
                        reason = errReason.ifEmpty { "Virheellinen käyttäjätunnus tai salasana." }
                    )
                }
                return@withContext false
            }""",
        "BackgroundAuthHelper:mark_failed_on_rejected_login",
    )
    return text


def patch_settings_dialog_helper(text: str) -> str:
    text = replace_once(
        text,
        r"""        val tvTestStatus = TextView(context).apply {
            text = ""
            textSize = 13f
            setPadding(0, dp(8), 0, dp(2))
        }""",
        r"""        val wasAuthBlocked = !isDemoActive && BackgroundAuthHelper.isCredentialBlocked(context)
        val tvTestStatus = TextView(context).apply {
            text = if (wasAuthBlocked) {
                if (en) {
                    "Automatic login paused after a rejected password. Please verify your credentials and save."
                } else {
                    "Automaattinen kirjautuminen pysäytettiin virheellisen tunnuksen tai salasanan vuoksi. Tarkista tiedot ja tallenna."
                }
            } else {
                ""
            }
            setTextColor(Color.parseColor(if (wasAuthBlocked) "#EF4444" else "#94A3B8"))
            textSize = 13f
            setPadding(0, dp(8), 0, dp(2))
        }""",
        "SettingsDialogHelper:show_blocked_login_warning",
    )

    text = replace_once(
        text,
        r"""            val prevUser = SecureCredentialManager.getUsername(context).orEmpty()
            val prevUrl = UrlNormalizer.getSavedBaseUrl(context)

            val isDemo = savedUser.isEmpty() || savedPass.isEmpty() || rawOrg.isEmpty() ||
                UrlNormalizer.isDemoInput(rawOrg) ||
                DemoModeHelper.isDemoCredentials(rawOrg, savedUser, savedPass)

            SecureCredentialManager.saveCredentials(context, savedUser, savedPass)
            if (savedUser != prevUser || savedPass != existingPassword || normalizedUrl != prevUrl) {
                BackgroundAuthHelper.clearSessionCache(context)
            }""",
        r"""            val isDemo = savedUser.isEmpty() || savedPass.isEmpty() || rawOrg.isEmpty() ||
                UrlNormalizer.isDemoInput(rawOrg) ||
                DemoModeHelper.isDemoCredentials(rawOrg, savedUser, savedPass)

            SecureCredentialManager.saveCredentials(context, savedUser, savedPass)
            BackgroundAuthHelper.clearSessionCache(context)""",
        "SettingsDialogHelper:always_clear_session_and_block_on_save",
    )
    return text


def patch_main_activity(text: str) -> str:
    # 0. Lisätään webLoginAttemptFingerprint estämään WebView-kirjautumissilmukka
    text = replace_once(
        text,
        r"""    private var isAutoSubmittingLogin: Boolean = false
    private var lastThemedUrl: String? = null""",
        r"""    private var isAutoSubmittingLogin: Boolean = false
    private var webLoginAttemptFingerprint: String = ""
    private var lastThemedUrl: String? = null""",
        "MainActivity:webLoginAttemptFingerprint_field",
    )

    # 1. Siirretään scheduleShiftReminders taustasäikeeseen onCreate-käynnistyksen nopeuttamiseksi
    #    ja tyhjennetään OPEN_REQUESTS-extra käsittelyn jälkeen.
    text = replace_once(
        text,
        r"""        requestNeededPermissions()
        ShiftReminderReceiver.ensureBackgroundSyncScheduled(this)

        CalendarSyncHelper.scheduleShiftReminders(this)""",
        r"""        requestNeededPermissions()
        ShiftReminderReceiver.ensureBackgroundSyncScheduled(this)

        scope.launch(Dispatchers.IO) {
            CalendarSyncHelper.scheduleShiftReminders(this@MainActivity)
        }""",
        "MainActivity:async_onCreate_reminders",
    )

    text = replace_once(
        text,
        r"""        if (intent?.getBooleanExtra("OPEN_REQUESTS", false) == true) {
            navigateToTab(Tab.REQUESTS)
        } else {
            navigateToTab(Tab.STAMP)
        }""",
        r"""        if (intent?.getBooleanExtra("OPEN_REQUESTS", false) == true) {
            intent.removeExtra("OPEN_REQUESTS")
            navigateToTab(Tab.REQUESTS)
        } else {
            navigateToTab(Tab.STAMP)
        }""",
        "MainActivity:clear_open_requests_extra",
    )

    # 2. Nollataan demokalenterin selattu kuukausi nykyhetkeen, kun käyttäjä avaa Vuorot-välilehden
    #    ja estetään kirjautumisyritykset jos tunnukset on jo todettu virheellisiksi.
    text = replace_once(
        text,
        r"""        if (DemoModeHelper.isDemoEnabled(this)) {
            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition""",
        r"""        if (DemoModeHelper.isDemoEnabled(this)) {
            if (tab == Tab.SHIFTS) {
                DemoModeHelper.resetDemoCalendarMonth(this)
            }
            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition""",
        "MainActivity:reset_demo_calendar_on_tab",
    )

    text = replace_once(
        text,
        r"""            val baseUrl = getBaseUrl()
            if (baseUrl.isEmpty() || (!baseUrl.startsWith("http://") && !baseUrl.startsWith("https://"))) {
                endSnapshotTransition()
                Toast.makeText(
                    this,
                    if (DemoModeHelper.isEnglish(this)) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista",
                    Toast.LENGTH_LONG
                ).show()
                btnNavSettings.performClick()
                return
            }""",
        r"""            val baseUrl = getBaseUrl()
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
            if (BackgroundAuthHelper.isCredentialBlocked(this)) {
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
            }""",
        "MainActivity:block_navigation_on_invalid_credentials",
    )

    text = replace_once(
        text,
        r"""                if (existingCookies.isNullOrBlank() || sessionAgeMs > maxSessionAgeMs) {
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
                }""",
        r"""                if (existingCookies.isNullOrBlank() || sessionAgeMs > maxSessionAgeMs) {
                    navigateJob = scope.launch {
                        try {
                            val ok = BackgroundAuthHelper.ensureAuthenticatedSession(this@MainActivity)
                            if (ok) {
                                prefs.edit().putLong("last_valid_session_ms", System.currentTimeMillis()).apply()
                            }
                        } catch (_: Exception) {
                        }
                        if (token == navigationToken && !isFinishing && !isDestroyed) {
                            if (BackgroundAuthHelper.isCredentialBlocked(this@MainActivity)) {
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
                                webView.stopLoading()
                                webView.loadUrl(url)
                            }
                        }
                    }
                }""",
        "MainActivity:stop_webview_load_after_rejected_bg_auth",
    )

    text = replace_once(
        text,
        r"""        val baseUrl = getBaseUrl()
        if (baseUrl.isBlank()) {
            val en = DemoModeHelper.isEnglish(this)
            Toast.makeText(
                this,
                if (en) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista",
                Toast.LENGTH_LONG
            ).show()
            return
        }""",
        r"""        val baseUrl = getBaseUrl()
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
        }""",
        "MainActivity:block_manual_sync_on_invalid_credentials",
    )

    # 3. Estetään ulkoisen selaimen avaus alakehysten (iframe) pyynnöistä
    text = replace_once(
        text,
        r"""                    try {
                        startActivity(Intent(Intent.ACTION_VIEW, uri))
                    } catch (_: Exception) {
                    }
                    return true""",
        r"""                    if (request?.isForMainFrame == true) {
                        try {
                            startActivity(Intent(Intent.ACTION_VIEW, uri))
                        } catch (_: Exception) {
                        }
                        return true
                    }
                    return false""",
        "MainActivity:only_external_main_frame",
    )

    text = replace_once(
        text,
        r"""                if (!url.contains("/Login/", ignoreCase = true)) {
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                }""",
        r"""                if (!url.contains("/Login/", ignoreCase = true)) {
                    webLoginAttemptFingerprint = ""
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                }""",
        "MainActivity:reset_webLoginAttemptFingerprint_on_success",
    )

    # 4. Varmistetaan ettei CSS-välimuisti estä DOM-päivitystä, mutta vältetään turha 20 KB CSS-ylikirjoitus
    old_css_start = (
        "        val nightBg = rgbToHex(nightRgb)\n"
        "        val nightFg = contrastFg(nightRgb)\n"
        '        val css = """'
    )
    new_css_start = (
        "        val nightBg = rgbToHex(nightRgb)\n"
        "        val nightFg = contrastFg(nightRgb)\n"
        '        val colorCacheKey = "$morningBg|$eveningBg|$nightBg"\n'
        '        val css = """'
    )
    text = replace_once(
        text,
        old_css_start,
        new_css_start,
        "MainActivity:color_cache_key",
    )

    # 5. Keskitetään kuukausi ja vuosi, suurennetaan selausnapit ja muotoillaan #monthText + hyppyvalitsin
    text = replace_once(
        text,
        r"""            /* === 7. KALENTERI: YLÄPALKKI JA KUUKAUSINÄKYMÄ === */
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
            }""",
        r"""            /* === 7. KALENTERI: YLÄPALKKI JA KUUKAUSINÄKYMÄ === */
            .calendar-heading {
                box-shadow: none !important;
                display: flex !important;
                flex-direction: column !important;
                justify-content: center !important;
                align-items: center !important;
                background-color: #182332 !important;
                border: 1px solid #2A394A !important;
                border-radius: 12px !important;
                padding: 10px 12px !important;
                margin-bottom: 12px !important;
            }
            .monthSelector {
                width: 100% !important;
                display: flex !important;
                flex-direction: column !important;
                align-items: center !important;
                justify-content: center !important;
                gap: 8px !important;
            }
            .monthSelector .panel-body {
                width: 100% !important;
                padding: 2px !important;
                margin: 0 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                gap: 12px !important;
            }
            #pcTodayButton {
                display: flex !important;
                justify-content: center !important;
                width: 100% !important;
                margin: 0 !important;
            }
            #todayButt {
                padding: 5px 16px !important;
                font-size: 12.5px !important;
                min-width: auto !important;
                max-width: none !important;
                border-radius: 8px !important;
            }
            #monthText {
                color: #F1F5F9 !important;
                font-size: 18px !important;
                font-weight: 700 !important;
                margin: 0 !important;
                text-align: center !important;
                line-height: 1.25 !important;
            }
            #monthText.vv-month-jumpable {
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                gap: 6px !important;
                background-color: #111923 !important;
                border: 1px solid #2A394A !important;
                border-radius: 10px !important;
                padding: 6px 14px !important;
                cursor: pointer !important;
                user-select: none !important;
            }
            #monthText.vv-month-jumpable:active {
                background-color: #233040 !important;
                border-color: #38BDF8 !important;
            }
            #monthText.vv-month-jumpable::after {
                content: "▾" !important;
                color: #38BDF8 !important;
                font-size: 14px !important;
                font-weight: 700 !important;
            }
            .prevButton, .nextButton {
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                width: 42px !important;
                height: 38px !important;
                background-color: #233040 !important;
                border: 1px solid #37475A !important;
                border-radius: 10px !important;
                text-decoration: none !important;
                flex-shrink: 0 !important;
            }
            .prevButton:active, .nextButton:active {
                background-color: #2A394A !important;
                border-color: #38BDF8 !important;
            }
            .prevButton::before {
                content: "◀" !important;
                color: #38BDF8 !important;
                font-size: 18px !important;
                line-height: 1 !important;
                text-decoration: none !important;
            }
            .nextButton::before {
                content: "▶" !important;
                color: #38BDF8 !important;
                font-size: 18px !important;
                line-height: 1 !important;
                text-decoration: none !important;
            }""",
        "MainActivity:center_month_and_bigger_nav_buttons",
    )

    # 6. CSS-päivityksen optimointi: vältetään turha style.textContent-ylikirjoitus jos väriavain ei muuttunut
    text = replace_once(
        text,
        r"""                if (style.textContent !== '$safeCss') {
                    style.textContent = '$safeCss';
                }""",
        r"""                if (style.getAttribute('data-vv-colors') !== '$colorCacheKey' || !style.textContent) {
                    style.setAttribute('data-vv-colors', '$colorCacheKey');
                    style.textContent = '$safeCss';
                }""",
        "MainActivity:optimize_css_reapplication",
    )

    # 7. Rajataan kalenterisiivouksen MutationObserver vain /calendar-sivuille (ei ajeta leimaus-/toivesivuilla)
    text = replace_once(
        text,
        r"""                    runCalendarCleanup();
                    if (!window._calendarCleanupObserver && document.body && typeof MutationObserver !== 'undefined') {
                        window._calendarCleanupObserver = true;
                        var calCleanupTimer = null;
                        var calObs = new MutationObserver(function() {
                            if (calCleanupTimer) clearTimeout(calCleanupTimer);
                            calCleanupTimer = setTimeout(function() { runCalendarCleanup(); }, 80);
                        });
                        calObs.observe(document.body, { childList: true, subtree: true });
                    }""",
        r"""                    if (window.location.pathname.toLowerCase().indexOf('/calendar') !== -1) {
                        runCalendarCleanup();
                        if (!window._calendarCleanupObserver && typeof MutationObserver !== 'undefined') {
                            var calObsRoot = document.getElementById('calendar-content') || document.body;
                            if (calObsRoot) {
                                window._calendarCleanupObserver = true;
                                var calCleanupTimer = null;
                                var calObs = new MutationObserver(function() {
                                    if (calCleanupTimer) clearTimeout(calCleanupTimer);
                                    calCleanupTimer = setTimeout(function() { runCalendarCleanup(); }, 80);
                                });
                                calObs.observe(calObsRoot, { childList: true, subtree: true });
                            }
                        }
                    }""",
        "MainActivity:scope_calendar_observer",
    )

    # 8. Lisätään kuukausi/vuosi-hyppyvalitsin #monthText-otsikon painallukseen
    text = replace_once(
        text,
        r"""                // === SUORA "LISÄÄ TOIVE TÄLLE PÄIVÄLLE" -OIKOPOLKU KALENTERIPÄIVÄSTÄ ===
                if (window.location.pathname.toLowerCase().indexOf('/calendar/month') !== -1 && !window._quickRequestInstalled) {
                    window._quickRequestInstalled = true;""",
        r"""                // === KUUKAUSI- JA VUOSIHYPPYVALITSIN (/Calendar/Month) ===
                if (window.location.pathname.toLowerCase().indexOf('/calendar/month') !== -1) {
                    var monthLabelEl = document.getElementById('monthText');
                    if (monthLabelEl && !monthLabelEl._vvJumpInstalled) {
                        monthLabelEl._vvJumpInstalled = true;
                        monthLabelEl.classList.add('vv-month-jumpable');

                        var jumpMonthMap = {
                            'tammikuu': 1, 'helmikuu': 2, 'maaliskuu': 3, 'huhtikuu': 4,
                            'toukokuu': 5, 'kesäkuu': 6, 'heinäkuu': 7, 'elokuu': 8,
                            'syyskuu': 9, 'lokakuu': 10, 'marraskuu': 11, 'joulukuu': 12,
                            'january': 1, 'february': 2, 'march': 3, 'april': 4,
                            'may': 5, 'june': 6, 'july': 7, 'august': 8,
                            'september': 9, 'october': 10, 'november': 11, 'december': 12,
                            'januari': 1, 'februari': 2, 'mars': 3, 'maj': 5,
                            'juni': 6, 'juli': 7, 'augusti': 8, 'oktober': 10
                        };

                        monthLabelEl.addEventListener('click', function(ev) {
                            ev.preventDefault();
                            ev.stopPropagation();

                            var existingModal = document.getElementById('vv-month-jump-modal');
                            if (existingModal) existingModal.remove();

                            var nowDate = new Date();
                            var curRealMonth = nowDate.getMonth() + 1;
                            var curRealYear = nowDate.getFullYear();

                            var rawTxt = (monthLabelEl.textContent || '').trim().toLowerCase();
                            var txtParts = rawTxt.split(/\s+/);
                            var activeMonth = (txtParts.length >= 2 && jumpMonthMap[txtParts[0]]) ? jumpMonthMap[txtParts[0]] : curRealMonth;
                            var activeYear = (txtParts.length >= 2 && parseInt(txtParts[1], 10)) ? parseInt(txtParts[1], 10) : curRealYear;
                            var selectedYear = activeYear;

                            var isEn = /^(january|february|march|april|may|june|july|august|september|october|november|december)/.test(rawTxt);
                            var shortMonths = isEn
                                ? ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                                : ['Tammi', 'Helmi', 'Maalis', 'Huhti', 'Touko', 'Kesä', 'Heinä', 'Elo', 'Syys', 'Loka', 'Marras', 'Joulu'];

                            var backdrop = document.createElement('div');
                            backdrop.id = 'vv-month-jump-modal';
                            backdrop.style.cssText = 'position:fixed;inset:0;z-index:1250;background:rgba(6,11,19,0.78);display:flex;align-items:center;justify-content:center;padding:16px;';

                            var card = document.createElement('div');
                            card.style.cssText = 'width:100%;max-width:340px;background:#182332;border:1px solid #38BDF8;border-radius:14px;padding:16px;box-shadow:0 16px 36px rgba(0,0,0,0.65);color:#F1F5F9;';

                            var titleRow = document.createElement('div');
                            titleRow.style.cssText = 'font-size:12px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:#38BDF8;margin-bottom:10px;text-align:center;';
                            titleRow.textContent = isEn ? 'Jump to month & year' : 'Siirry kuukauteen ja vuoteen';
                            card.appendChild(titleRow);

                            var yearRow = document.createElement('div');
                            yearRow.style.cssText = 'display:flex;align-items:center;justify-content:space-between;background:#111923;border:1px solid #2A394A;border-radius:10px;padding:6px 10px;margin-bottom:12px;';

                            var btnPrevYear = document.createElement('button');
                            btnPrevYear.type = 'button';
                            btnPrevYear.textContent = '◀';
                            btnPrevYear.style.cssText = 'width:38px;height:34px;background:#233040;color:#38BDF8;border:1px solid #37475A;border-radius:8px;font-size:16px;font-weight:700;';

                            var yearLabel = document.createElement('span');
                            yearLabel.style.cssText = 'font-size:18px;font-weight:700;color:#F1F5F9;';
                            yearLabel.textContent = String(selectedYear);

                            var btnNextYear = document.createElement('button');
                            btnNextYear.type = 'button';
                            btnNextYear.textContent = '▶';
                            btnNextYear.style.cssText = 'width:38px;height:34px;background:#233040;color:#38BDF8;border:1px solid #37475A;border-radius:8px;font-size:16px;font-weight:700;';

                            yearRow.appendChild(btnPrevYear);
                            yearRow.appendChild(yearLabel);
                            yearRow.appendChild(btnNextYear);
                            card.appendChild(yearRow);

                            var grid = document.createElement('div');
                            grid.style.cssText = 'display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px;';
                            card.appendChild(grid);

                            function renderMonthButtons() {
                                yearLabel.textContent = String(selectedYear);
                                grid.innerHTML = '';
                                for (var idx = 0; idx < 12; idx++) {
                                    (function(mVal, mName) {
                                        var btn = document.createElement('button');
                                        btn.type = 'button';
                                        btn.textContent = mName;
                                        var isSelected = (selectedYear === activeYear && mVal === activeMonth);
                                        var isCurrentReal = (selectedYear === curRealYear && mVal === curRealMonth);
                                        var bg = isSelected ? '#1982C4' : '#111923';
                                        var border = isSelected ? '#38BDF8' : (isCurrentReal ? '#38BDF8' : '#2A394A');
                                        var fg = isSelected ? '#FFFFFF' : '#E2E8F0';
                                        btn.style.cssText = 'padding:10px 4px;border-radius:8px;font-size:13px;font-weight:600;background:' + bg + ';border:1px solid ' + border + ';color:' + fg + ';';
                                        btn.onclick = function() {
                                            backdrop.remove();
                                            window.location.href = '/Calendar/Month?month=' + mVal + '&year=' + selectedYear;
                                        };
                                        grid.appendChild(btn);
                                    })(idx + 1, shortMonths[idx]);
                                }
                            }

                            btnPrevYear.onclick = function() {
                                selectedYear -= 1;
                                renderMonthButtons();
                            };
                            btnNextYear.onclick = function() {
                                selectedYear += 1;
                                renderMonthButtons();
                            };

                            var footerRow = document.createElement('div');
                            footerRow.style.cssText = 'display:flex;gap:8px;';

                            var btnTodayJump = document.createElement('button');
                            btnTodayJump.type = 'button';
                            btnTodayJump.textContent = isEn ? 'Current month' : 'Nykyinen kuukausi';
                            btnTodayJump.style.cssText = 'flex:1;padding:10px;background:#233040;color:#38BDF8;border:1px solid #37475A;border-radius:8px;font-size:13px;font-weight:600;';
                            btnTodayJump.onclick = function() {
                                backdrop.remove();
                                window.location.href = '/Calendar/Month?month=' + curRealMonth + '&year=' + curRealYear;
                            };

                            var btnCancelJump = document.createElement('button');
                            btnCancelJump.type = 'button';
                            btnCancelJump.textContent = isEn ? 'Cancel' : 'Peruuta';
                            btnCancelJump.style.cssText = 'flex:1;padding:10px;background:#233040;color:#CBD5E1;border:1px solid #37475A;border-radius:8px;font-size:13px;font-weight:600;';
                            btnCancelJump.onclick = function() {
                                backdrop.remove();
                            };

                            footerRow.appendChild(btnTodayJump);
                            footerRow.appendChild(btnCancelJump);
                            card.appendChild(footerRow);

                            backdrop.appendChild(card);
                            backdrop.addEventListener('click', function(bgEv) {
                                if (bgEv.target === backdrop) backdrop.remove();
                            });
                            document.body.appendChild(backdrop);
                            renderMonthButtons();
                        });
                    }
                }

                // === SUORA "LISÄÄ TOIVE TÄLLE PÄIVÄLLE" -OIKOPOLKU KALENTERIPÄIVÄSTÄ ===
                if (window.location.pathname.toLowerCase().indexOf('/calendar/month') !== -1 && !window._quickRequestInstalled) {
                    window._quickRequestInstalled = true;""",
        "MainActivity:month_year_jump_picker",
    )

    # 9. Estetään WebView-automaattikirjautumisen uusintayritykset väärillä tunnuksilla (max 1 yritys)
    text = replace_once(
        text,
        r'''            private fun handleAutoLogin(attempt: Int = 0) {
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
    }''',
        r'''    private fun handleAutoLogin(attempt: Int = 0) {
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

        webView.evaluateJavascript(js) { res ->
            if (res?.contains("SUBMITTED") == true) {
                webLoginAttemptFingerprint = fp
            } else if (res?.contains("WAITING") == true) {
                if (attempt < 15) {
                    webView.postDelayed({ handleAutoLogin(attempt + 1) }, 300L)
                } else {
                    isAutoSubmittingLogin = false
                    endSnapshotTransition()
                }
            }
        }
    }''',
        "MainActivity:single_attempt_web_login",
    )

    text = replace_once(
        text,
        r"""        val baseUrl = getBaseUrl()
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
        }""",
        r"""        val baseUrl = getBaseUrl()
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
                    webView.loadUrl(targetUrl)
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
                    webView.loadUrl("$baseUrl/Login/Login")
                }
            }
        }""",
        "MainActivity:session_expired_stop_on_bad_credentials",
    )

    # 10. Tyhjennetään pendingAction, jos handleCalendarPage saa null-tuloksen
    text = replace_once(
        text,
        r"""        webView.evaluateJavascript("document.documentElement.outerHTML") { rawHtml ->
            if (rawHtml == null || rawHtml == "null") return@evaluateJavascript""",
        r"""        webView.evaluateJavascript("document.documentElement.outerHTML") { rawHtml ->
            if (rawHtml == null || rawHtml == "null") {
                pendingAction = Action.NONE
                collectedCalendarHtml.clear()
                return@evaluateJavascript
            }""",
        "MainActivity:handleCalendarPage_null_cleanup",
    )

    return text


def patch_demo_mode_helper(text: str) -> str:
    # 1. Lisätään apumetodi demokalenterin kuukauden nollaamiseen
    text = replace_once(
        text,
        r"""    fun setDemoLanguage(context: Context, lang: String) {
        val normalized = if (lang.equals("en", ignoreCase = true)) "en" else "fi"
        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putString("demo_language", normalized)
            .apply()
    }""",
        r"""    fun setDemoLanguage(context: Context, lang: String) {
        val normalized = if (lang.equals("en", ignoreCase = true)) "en" else "fi"
        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putString("demo_language", normalized)
            .apply()
    }

    fun resetDemoCalendarMonth(context: Context) {
        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .remove("demo_cal_year")
            .remove("demo_cal_month")
            .apply()
    }""",
        "DemoModeHelper:resetDemoCalendarMonth",
    )

    # 2. HTML-suojaus demoleimausten historiaan
    text = replace_once(
        text,
        r'''                """<tr>
                    <td>${p[0]}</td>
                    <td><strong>${p[1]}</strong></td>
                    <td style="color:$typeColor;font-weight:700;">$dirLabel</td>
                </tr>"""''',
        r'''                val safeDate = android.text.TextUtils.htmlEncode(p[0])
                val safeTime = android.text.TextUtils.htmlEncode(p[1])
                """<tr>
                    <td>$safeDate</td>
                    <td><strong>$safeTime</strong></td>
                    <td style="color:$typeColor;font-weight:700;">$dirLabel</td>
                </tr>"""''',
        "DemoModeHelper:html_encode_stamps",
    )

    # 3. Demokalenteriin kuukauden selaus (◀ / ▶), keskitys, vuorovärien luku kerran silmukan ulkopuolella ja hyppyvalitsin
    text = replace_once(
        text,
        r"""    fun getDemoShiftsHtml(context: Context): String {
        val en = isEnglish(context)
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val variant = prefs.getInt("demo_shift_variant", 0)
        val today = LocalDate.now()
        val ym = YearMonth.from(today)""",
        r"""    fun getDemoShiftsHtml(context: Context): String {
        val en = isEnglish(context)
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val variant = prefs.getInt("demo_shift_variant", 0)
        val today = LocalDate.now()
        val savedYear = prefs.getInt("demo_cal_year", today.year)
        val savedMonth = prefs.getInt("demo_cal_month", today.monthValue).coerceIn(1, 12)
        val ym = try {
            YearMonth.of(savedYear, savedMonth)
        } catch (_: Exception) {
            YearMonth.from(today)
        }
        val prevYm = ym.minusMonths(1)
        val nextYm = ym.plusMonths(1)
        val isCurrentMonth = (ym.year == today.year && ym.monthValue == today.monthValue)""",
        "DemoModeHelper:demo_ym_navigation",
    )

    text = replace_once(
        text,
        r"""        val weeksHtml = StringBuilder()
        var cursor = gridStart""",
        r"""        val mRgb = prefs.getInt("color_morning_rgb", SettingsDialogHelper.DEFAULT_MORNING_RGB)
        val eRgb = prefs.getInt("color_evening_rgb", SettingsDialogHelper.DEFAULT_EVENING_RGB)
        val nRgb = prefs.getInt("color_night_rgb", SettingsDialogHelper.DEFAULT_NIGHT_RGB)
        val timePairRegex = Regex("(\\d{1,2}):(\\d{2})\\s*-\\s*(\\d{1,2}):(\\d{2})")

        val weeksHtml = StringBuilder()
        var cursor = gridStart""",
        "DemoModeHelper:hoist_shift_colors",
    )

    text = replace_once(
        text,
        r"""                    else -> {
                        val mRgb = prefs.getInt("color_morning_rgb", SettingsDialogHelper.DEFAULT_MORNING_RGB)
                        val eRgb = prefs.getInt("color_evening_rgb", SettingsDialogHelper.DEFAULT_EVENING_RGB)
                        val nRgb = prefs.getInt("color_night_rgb", SettingsDialogHelper.DEFAULT_NIGHT_RGB)
                        val tm = Regex("(\\d{1,2}):(\\d{2})\\s*-\\s*(\\d{1,2}):(\\d{2})").find(item.times)
                        val chosenRgb = if (tm != null) {""",
        r"""                    else -> {
                        val tm = timePairRegex.find(item.times)
                        val chosenRgb = if (tm != null) {""",
        "DemoModeHelper:use_hoisted_shift_colors",
    )

    text = replace_once(
        text,
        r'''        val extraCss = """
            .calendar-heading {
                display: flex;
                justify-content: space-between;
                align-items: center;
                background-color: #182332;
                border: 1px solid #2A394A;
                border-radius: 12px;
                padding: 8px 12px;
                margin-bottom: 12px;
            }
            .monthSelector {
                display: flex;
                align-items: center;
                gap: 10px;
            }
            #monthText {
                color: #F1F5F9;
                font-size: 17px;
                font-weight: 600;
                margin: 0;
            }
            .nav-arrow {
                color: #38BDF8;
                font-size: 15px;
                user-select: none;
            }''',
        r'''        val extraCss = """
            .calendar-heading {
                display: flex;
                flex-direction: column;
                align-items: center;
                background-color: #182332;
                border: 1px solid #2A394A;
                border-radius: 12px;
                padding: 10px 12px;
                margin-bottom: 12px;
                gap: 8px;
            }
            .demo-top-meta {
                width: 100%;
                display: flex;
                justify-content: flex-end;
                align-items: center;
                gap: 6px;
            }
            .monthSelector {
                width: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 12px;
            }
            #monthText {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                color: #F1F5F9;
                font-size: 18px;
                font-weight: 700;
                margin: 0;
                background-color: #111923;
                border: 1px solid #2A394A;
                border-radius: 10px;
                padding: 6px 14px;
                cursor: pointer;
                user-select: none;
            }
            #monthText::after {
                content: "▾";
                color: #38BDF8;
                font-size: 14px;
            }
            .nav-arrow {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 42px;
                height: 38px;
                background-color: #233040;
                border: 1px solid #37475A;
                border-radius: 10px;
                color: #38BDF8;
                font-size: 18px;
                cursor: pointer;
                user-select: none;
            }
            .nav-arrow:active {
                background-color: #2A394A;
                border-color: #38BDF8;
            }''',
        "DemoModeHelper:centered_demo_month_heading",
    )

    text = replace_once(
        text,
        r'''                <div class="calendar-heading">
                    <div class="monthSelector">
                        <span class="nav-arrow">◀</span>
                        <span id="monthText">$monthTitle</span>
                        <span class="nav-arrow">▶</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:6px;">
                        ${langSwitchHtml(en)}
                        <span class="badge badge-ok">DEMO</span>
                    </div>
                </div>''',
        r'''                <div class="calendar-heading">
                    <div class="demo-top-meta">
                        ${if (!isCurrentMonth) """<button type="button" class="btn" style="padding:4px 10px;font-size:11px;" onclick="DemoBridge.selectMonth(${today.year}, ${today.monthValue})">${if (en) "Today" else "Tänään"}</button>""" else ""}
                        ${langSwitchHtml(en)}
                        <span class="badge badge-ok">DEMO</span>
                    </div>
                    <div class="monthSelector">
                        <button type="button" class="nav-arrow" onclick="DemoBridge.selectMonth(${prevYm.year}, ${prevYm.monthValue})">◀</button>
                        <span id="monthText" onclick="openDemoMonthJump()">$monthTitle</span>
                        <button type="button" class="nav-arrow" onclick="DemoBridge.selectMonth(${nextYm.year}, ${nextYm.monthValue})">▶</button>
                    </div>
                </div>''',
        "DemoModeHelper:interactive_month_controls",
    )

    text = replace_once(
        text,
        r"""                    </div>
                </div>
            </div>
        </body>
        </html>""",
        r"""                    </div>
                </div>
            </div>
            <script>
                function openDemoMonthJump() {
                    var existing = document.getElementById('vv-demo-jump-modal');
                    if (existing) existing.remove();
                    var activeYear = ${ym.year};
                    var activeMonth = ${ym.monthValue};
                    var curRealYear = ${today.year};
                    var curRealMonth = ${today.monthValue};
                    var selectedYear = activeYear;
                    var isEn = ${if (en) "true" else "false"};
                    var shortMonths = isEn
                        ? ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                        : ['Tammi', 'Helmi', 'Maalis', 'Huhti', 'Touko', 'Kesä', 'Heinä', 'Elo', 'Syys', 'Loka', 'Marras', 'Joulu'];

                    var backdrop = document.createElement('div');
                    backdrop.id = 'vv-demo-jump-modal';
                    backdrop.style.cssText = 'position:fixed;inset:0;z-index:1250;background:rgba(6,11,19,0.78);display:flex;align-items:center;justify-content:center;padding:16px;';

                    var card = document.createElement('div');
                    card.style.cssText = 'width:100%;max-width:340px;background:#182332;border:1px solid #38BDF8;border-radius:14px;padding:16px;box-shadow:0 16px 36px rgba(0,0,0,0.65);color:#F1F5F9;';

                    var title = document.createElement('div');
                    title.style.cssText = 'font-size:12px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:#38BDF8;margin-bottom:10px;text-align:center;';
                    title.textContent = isEn ? 'Jump to month & year' : 'Siirry kuukauteen ja vuoteen';
                    card.appendChild(title);

                    var yearRow = document.createElement('div');
                    yearRow.style.cssText = 'display:flex;align-items:center;justify-content:space-between;background:#111923;border:1px solid #2A394A;border-radius:10px;padding:6px 10px;margin-bottom:12px;';

                    var btnPrevY = document.createElement('button');
                    btnPrevY.type = 'button';
                    btnPrevY.textContent = '◀';
                    btnPrevY.style.cssText = 'width:38px;height:34px;background:#233040;color:#38BDF8;border:1px solid #37475A;border-radius:8px;font-size:16px;font-weight:700;';

                    var yearLbl = document.createElement('span');
                    yearLbl.style.cssText = 'font-size:18px;font-weight:700;color:#F1F5F9;';

                    var btnNextY = document.createElement('button');
                    btnNextY.type = 'button';
                    btnNextY.textContent = '▶';
                    btnNextY.style.cssText = 'width:38px;height:34px;background:#233040;color:#38BDF8;border:1px solid #37475A;border-radius:8px;font-size:16px;font-weight:700;';

                    yearRow.appendChild(btnPrevY);
                    yearRow.appendChild(yearLbl);
                    yearRow.appendChild(btnNextY);
                    card.appendChild(yearRow);

                    var grid = document.createElement('div');
                    grid.style.cssText = 'display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px;';
                    card.appendChild(grid);

                    function renderGrid() {
                        yearLbl.textContent = String(selectedYear);
                        grid.innerHTML = '';
                        for (var i = 0; i < 12; i++) {
                            (function(mVal, mName) {
                                var b = document.createElement('button');
                                b.type = 'button';
                                b.textContent = mName;
                                var sel = (selectedYear === activeYear && mVal === activeMonth);
                                var cur = (selectedYear === curRealYear && mVal === curRealMonth);
                                b.style.cssText = 'padding:10px 4px;border-radius:8px;font-size:13px;font-weight:600;background:' + (sel ? '#1982C4' : '#111923') + ';border:1px solid ' + ((sel || cur) ? '#38BDF8' : '#2A394A') + ';color:' + (sel ? '#FFFFFF' : '#E2E8F0') + ';';
                                b.onclick = function() {
                                    backdrop.remove();
                                    DemoBridge.selectMonth(selectedYear, mVal);
                                };
                                grid.appendChild(b);
                            })(i + 1, shortMonths[i]);
                        }
                    }

                    btnPrevY.onclick = function() { selectedYear -= 1; renderGrid(); };
                    btnNextY.onclick = function() { selectedYear += 1; renderGrid(); };

                    var foot = document.createElement('div');
                    foot.style.cssText = 'display:flex;gap:8px;';

                    var btnNow = document.createElement('button');
                    btnNow.type = 'button';
                    btnNow.textContent = isEn ? 'Current month' : 'Nykyinen kuukausi';
                    btnNow.style.cssText = 'flex:1;padding:10px;background:#233040;color:#38BDF8;border:1px solid #37475A;border-radius:8px;font-size:13px;font-weight:600;';
                    btnNow.onclick = function() {
                        backdrop.remove();
                        DemoBridge.selectMonth(curRealYear, curRealMonth);
                    };

                    var btnClose = document.createElement('button');
                    btnClose.type = 'button';
                    btnClose.textContent = isEn ? 'Cancel' : 'Peruuta';
                    btnClose.style.cssText = 'flex:1;padding:10px;background:#233040;color:#CBD5E1;border:1px solid #37475A;border-radius:8px;font-size:13px;font-weight:600;';
                    btnClose.onclick = function() { backdrop.remove(); };

                    foot.appendChild(btnNow);
                    foot.appendChild(btnClose);
                    card.appendChild(foot);
                    backdrop.appendChild(card);
                    backdrop.addEventListener('click', function(ev) { if (ev.target === backdrop) backdrop.remove(); });
                    document.body.appendChild(backdrop);
                    renderGrid();
                }
            </script>
        </body>
        </html>""",
        "DemoModeHelper:demo_month_jump_modal",
    )

    text = replace_once(
        text,
        r"""        @JavascriptInterface
        fun setLanguage(lang: String) {
            setDemoLanguage(context, lang)
            onReloadNeeded()
        }""",
        r"""        @JavascriptInterface
        fun setLanguage(lang: String) {
            setDemoLanguage(context, lang)
            onReloadNeeded()
        }

        @JavascriptInterface
        fun selectMonth(year: Int, month: Int) {
            val safeYear = year.coerceIn(2000, 2100)
            val safeMonth = month.coerceIn(1, 12)
            context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                .edit()
                .putInt("demo_cal_year", safeYear)
                .putInt("demo_cal_month", safeMonth)
                .apply()
            onReloadNeeded()
        }""",
        "DemoModeHelper:bridge_selectMonth",
    )
    return text


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Kalenterin kuukausiotsikon keskitys, isommat selausnapit, kuukausi/vuosi-hyppyvalitsin, väärän salasanan lukituksen esto ja optimoinnit"
    )
    parser.add_argument("--root", default=".", help="Projektin juurikansio")
    parser.add_argument("--dry-run", action="store_true", help="Tarkista muutokset kirjoittamatta tiedostoja")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    patch_plan = [
        ("build.gradle.kts", 'applicationId = "com.numeron_vuorovahti"', bump_version),
        ("BackgroundAuthHelper.kt", "object BackgroundAuthHelper", patch_background_auth_helper),
        ("SettingsDialogHelper.kt", "object SettingsDialogHelper", patch_settings_dialog_helper),
        ("MainActivity.kt", "class MainActivity", patch_main_activity),
        ("DemoModeHelper.kt", "object DemoModeHelper", patch_demo_mode_helper),
    ]

    staged_writes: list[tuple[Path, str]] = []

    for filename, marker, patch_fn in patch_plan:
        path = find_file(root, filename, marker)
        raw_text = path.read_bytes().decode("utf-8")
        eol = "\r\n" if "\r\n" in raw_text else "\n"
        normalized = raw_text.replace("\r\n", "\n")

        patched = patch_fn(normalized)
        if patched == normalized:
            raise RuntimeError(f"[{filename}] Tiedostoon ei tullut muutoksia.")

        staged_writes.append((path, patched.replace("\n", eol)))
        print(f"OK: {path.relative_to(root)}")

    if args.dry_run:
        print(f"\nDRY-RUN OK: {len(staged_writes)} tiedostoa valmiina, mitään ei kirjoitettu.")
        return 0

    for path, final_text in staged_writes:
        path.write_text(final_text, encoding="utf-8")

    print(f"\nVALMIS: {len(staged_writes)} tiedostoa päivitetty onnistuneesti.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"VIRHE: {exc}", file=sys.stderr)
        sys.exit(1)
