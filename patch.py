#!/usr/bin/env python3
"""
Numeron Vuorovahti – automaattinen korjauspatch (patch.py)
Suorita projektin juurihakemistossa (missä app/src/main/java/fi/numeron/vuorovahti sijaitsee).
"""

from pathlib import Path


def find_source_dir() -> Path:
    candidates = [
        Path("app/src/main/java/fi/numeron/vuorovahti"),
        Path("src/main/java/fi/numeron/vuorovahti"),
        Path("."),
    ]
    for c in candidates:
        if c.exists() and any(c.glob("*.kt")):
            return c
    raise FileNotFoundError("Kotlin-lähdekoodihakemistoa ei löytynyt.")


def read_kt(path: Path) -> tuple[str, str]:
    """Lukee tiedoston sellaisenaan, tunnistaa rivinvaihtotyypin ja normalisoi sisäisesti LF:ksi."""
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    normalized = raw.replace("\r\n", "\n")
    return normalized, newline


def write_kt(path: Path, content: str, newline: str) -> None:
    """Kirjoittaa tiedoston takaisin alkuperäisellä rivinvaihtotyypillä (LF tai CRLF)."""
    normalized = content.replace("\r\n", "\n")
    if newline == "\r\n":
        normalized = normalized.replace("\n", "\r\n")
    path.write_bytes(normalized.encode("utf-8"))


def replace_once(content: str, old: str, new: str, label: str) -> str:
    old_lf = old.replace("\r\n", "\n")
    new_lf = new.replace("\r\n", "\n")
    if new_lf in content:
        print(f"  [OK - jo sovellettu] {label}")
        return content
    if old_lf not in content:
        print(f"  [VAROITUS - kohdetta ei löytynyt] {label}")
        return content
    print(f"  [PÄIVITETTY] {label}")
    return content.replace(old_lf, new_lf, 1)


def patch_secure_credential_manager(src_dir: Path) -> None:
    path = src_dir / "SecureCredentialManager.kt"
    if not path.exists():
        return
    print(f"Käsitellään {path.name}...")
    text, nl = read_kt(path)

    old = (
        "    fun saveCredentials(context: Context, username: String, password: String) {\n"
        "        getEncryptedPrefs(context)?.edit()?.apply {\n"
        "            putString(KEY_USERNAME, username)\n"
        "            putString(KEY_PASSWORD, password)\n"
        "            apply()\n"
        "        }"
    )
    new = (
        "    fun saveCredentials(context: Context, username: String, password: String) {\n"
        "        getEncryptedPrefs(context)?.edit()?.apply {\n"
        "            if (username.isEmpty()) remove(KEY_USERNAME) else putString(KEY_USERNAME, username)\n"
        "            if (password.isEmpty()) remove(KEY_PASSWORD) else putString(KEY_PASSWORD, password)\n"
        "            apply()\n"
        "        }"
    )
    text = replace_once(text, old, new, "Tyhjien tunnusten poisto saveCredentials-metodissa")
    write_kt(path, text, nl)


def patch_support_billing_helper(src_dir: Path) -> None:
    path = src_dir / "SupportBillingHelper.kt"
    if not path.exists():
        return
    print(f"Käsitellään {path.name}...")
    text, nl = read_kt(path)

    old = (
        "            billingClient.consumeAsync(consumeParams) { billingResult, _ ->\n"
        "                if (isDestroyed) return@consumeAsync\n"
        "                if (billingResult.responseCode == BillingClient.BillingResponseCode.OK) {\n"
        '                    postStatus("Lämmin kiitos tuestasi! ☕", true)\n'
        "                }\n"
        "            }"
    )
    new = (
        "            billingClient.consumeAsync(consumeParams) { billingResult, _ ->\n"
        "                if (isDestroyed) return@consumeAsync\n"
        "                if (billingResult.responseCode == BillingClient.BillingResponseCode.OK) {\n"
        '                    postStatus("Lämmin kiitos tuestasi! ☕", true)\n'
        "                } else {\n"
        '                    postStatus("Tuki rekisteröitiin, mutta kuittaus viivästyi (koodi ${billingResult.responseCode}).", false)\n'
        "                }\n"
        "            }"
    )
    text = replace_once(text, old, new, "consumeAsync-virhetilan tilaviesti")
    write_kt(path, text, nl)


def patch_settings_dialog_helper(src_dir: Path) -> None:
    path = src_dir / "SettingsDialogHelper.kt"
    if not path.exists():
        return
    print(f"Käsitellään {path.name}...")
    text, nl = read_kt(path)

    old_rem = "            val reminderMins = editReminder.text.toString().toIntOrNull() ?: 30"
    new_rem = "            val reminderMins = (editReminder.text.toString().toIntOrNull() ?: 30).coerceIn(1, 240)"
    text = replace_once(text, old_rem, new_rem, "Muistutusminuuttien rajaus (1..240 min)")

    old_apply = (
        "                .apply {\n"
        '                    if (selectedCal != null) putLong("calendar_id", selectedCal.id)\n'
        "                }\n"
        "                .apply()"
    )
    new_apply = (
        '                .also { if (selectedCal != null) it.putLong("calendar_id", selectedCal.id) }\n'
        "                .apply()"
    )
    text = replace_once(text, old_apply, new_apply, "SharedPreferences kaksois-apply siivous")

    old_focus = (
        "        rootContainer.viewTreeObserver.addOnWindowFocusChangeListener { hasFocus ->\n"
        "            if (hasFocus) {\n"
        "                refreshSystemPermissionStates()\n"
        "            }\n"
        "        }\n\n"
        "        dialog.setOnDismissListener { billingHelper.destroy() }"
    )
    new_focus = (
        "        val focusListener = android.view.ViewTreeObserver.OnWindowFocusChangeListener { hasFocus ->\n"
        "            if (hasFocus) {\n"
        "                refreshSystemPermissionStates()\n"
        "            }\n"
        "        }\n"
        "        rootContainer.viewTreeObserver.addOnWindowFocusChangeListener(focusListener)\n\n"
        "        dialog.setOnDismissListener {\n"
        "            rootContainer.viewTreeObserver.removeOnWindowFocusChangeListener(focusListener)\n"
        "            billingHelper.destroy()\n"
        "        }"
    )
    text = replace_once(text, old_focus, new_focus, "OnWindowFocusChangeListener poisto dialogin sulkeutuessa")
    write_kt(path, text, nl)


def patch_demo_mode_helper(src_dir: Path) -> None:
    path = src_dir / "DemoModeHelper.kt"
    if not path.exists():
        return
    print(f"Käsitellään {path.name}...")
    text, nl = read_kt(path)

    old = (
        '                    item.isAbsence -> """\n'
        '                        <div class="month-item absence">\n'
        '                            <span class="itemTimes">${item.times}</span>\n'
        '                        </div>\n'
        '                    """.trimIndent()'
    )
    new = (
        '                    item.isAbsence -> """\n'
        '                        <div class="month-item absence">\n'
        '                            <span class="itemName">${item.label}</span>\n'
        '                            <span class="itemTimes">${item.times}</span>\n'
        '                        </div>\n'
        '                    """.trimIndent()'
    )
    text = replace_once(text, old, new, "Demokalenterin poissaolo-elementin .itemName lisäys")
    write_kt(path, text, nl)


def patch_background_auth_helper(src_dir: Path) -> None:
    path = src_dir / "BackgroundAuthHelper.kt"
    if not path.exists():
        return
    print(f"Käsitellään {path.name}...")
    text, nl = read_kt(path)

    old_imports = (
        "import kotlinx.coroutines.coroutineScope\n"
        "import kotlinx.coroutines.withContext"
    )
    new_imports = (
        "import kotlinx.coroutines.coroutineScope\n"
        "import kotlinx.coroutines.sync.Mutex\n"
        "import kotlinx.coroutines.sync.withLock\n"
        "import kotlinx.coroutines.withContext"
    )
    text = replace_once(text, old_imports, new_imports, "Mutex-importit BackgroundAuthHelperiin")

    old_lock = "    private val cookieSyncLock = Any()"
    new_lock = (
        "    private val cookieSyncLock = Any()\n"
        "    private val authMutex = Mutex()"
    )
    text = replace_once(text, old_lock, new_lock, "authMutex-kentän lisäys")

    old_fn = (
        "    suspend fun ensureAuthenticatedSession(context: Context): Boolean = withContext(Dispatchers.IO) {\n"
        "        if (DemoModeHelper.isDemoEnabled(context)) return@withContext false\n\n"
        "        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n"
        "        val username = SecureCredentialManager.getUsername(context).orEmpty()\n"
        "        val password = SecureCredentialManager.getPassword(context).orEmpty()\n\n"
        "        if (baseUrl.isBlank() || username.isBlank() || password.isBlank()) {\n"
        "            return@withContext false\n"
        "        }\n\n"
        "        val nowMs = System.currentTimeMillis()\n"
        "        val cachedCookies = try {\n"
        "            CookieManager.getInstance().getCookie(baseUrl)\n"
        "        } catch (_: Exception) {\n"
        "            null\n"
        "        }\n"
        "        if (!cachedCookies.isNullOrBlank() &&\n"
        "            baseUrl == lastAuthBaseUrl &&\n"
        "            (nowMs - lastAuthSuccessMs) < 90_000L\n"
        "        ) {\n"
        "            return@withContext true\n"
        "        }"
    )

    new_fn = (
        "    suspend fun ensureAuthenticatedSession(context: Context): Boolean = withContext(Dispatchers.IO) {\n"
        "        if (DemoModeHelper.isDemoEnabled(context)) return@withContext false\n\n"
        "        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n"
        "        val username = SecureCredentialManager.getUsername(context).orEmpty()\n"
        "        val password = SecureCredentialManager.getPassword(context).orEmpty()\n\n"
        "        if (baseUrl.isBlank() || username.isBlank() || password.isBlank()) {\n"
        "            return@withContext false\n"
        "        }\n\n"
        "        authMutex.withLock {\n"
        "            val nowMs = System.currentTimeMillis()\n"
        "            val cachedCookies = try {\n"
        "                CookieManager.getInstance().getCookie(baseUrl)\n"
        "            } catch (_: Exception) {\n"
        "                null\n"
        "            }\n"
        "            if (!cachedCookies.isNullOrBlank() &&\n"
        "                baseUrl == lastAuthBaseUrl &&\n"
        "                (nowMs - lastAuthSuccessMs) < 90_000L\n"
        "            ) {\n"
        "                return@withLock true\n"
        "            }"
    )

    text = replace_once(text, old_fn, new_fn, "ensureAuthenticatedSession suojaus authMutex-lukolla (alku)")

    old_end = (
        "            lastAuthBaseUrl = baseUrl\n"
        "            lastAuthSuccessMs = System.currentTimeMillis()\n\n"
        "            true\n"
        "        } catch (_: Exception) {\n"
        "            false\n"
        "        }\n"
        "    }"
    )
    new_end = (
        "            lastAuthBaseUrl = baseUrl\n"
        "            lastAuthSuccessMs = System.currentTimeMillis()\n\n"
        "            true\n"
        "        } catch (_: Exception) {\n"
        "            false\n"
        "        }\n"
        "        }\n"
        "    }"
    )
    text = replace_once(text, old_end, new_end, "ensureAuthenticatedSession suojaus authMutex-lukolla (loppu)")
    write_kt(path, text, nl)


def patch_calendar_change_tracker(src_dir: Path) -> None:
    path = src_dir / "CalendarChangeTracker.kt"
    if not path.exists():
        return
    print(f"Käsitellään {path.name}...")
    text, nl = read_kt(path)

    old_merge = (
        "        for (item in newChanges) {\n"
        "            if (item.eventId != null) {\n"
        "                existing.removeAll { it.eventId == item.eventId }\n"
        "            }\n"
        "            existing.add(item)\n"
        "        }"
    )
    new_merge = (
        "        for (item in newChanges) {\n"
        "            if (item.eventId != null) {\n"
        "                existing.removeAll { it.eventId == item.eventId }\n"
        "            } else if (item.type == ChangeType.REMOVED) {\n"
        "                existing.removeAll {\n"
        "                    it.type == ChangeType.REMOVED &&\n"
        "                        it.calendarId == item.calendarId &&\n"
        "                        it.title == item.title &&\n"
        "                        it.startMs == item.startMs &&\n"
        "                        it.endMs == item.endMs\n"
        "                }\n"
        "            }\n"
        "            existing.add(item)\n"
        "        }"
    )
    text = replace_once(text, old_merge, new_merge, "REMOVED-tapahtumien duplikaattien esto mergeChanges-metodissa")

    old_revert = (
        "                btnRevert.setOnClickListener {\n"
        "                    btnRevert.isEnabled = false\n"
        "                    java.util.concurrent.Executors.newSingleThreadExecutor().execute {\n"
        "                        val ok = revertSingleChangeAndSave(context, item)\n"
        "                        android.os.Handler(android.os.Looper.getMainLooper()).post {\n"
        "                            if (ok) {\n"
        '                                Toast.makeText(context, "Muutos peruttu: ${item.title}", Toast.LENGTH_SHORT).show()\n'
        "                                dialogRef?.dismiss()\n"
        "                                onChanged?.invoke()\n"
        "                                showManageChangesDialog(context, onChanged)\n"
        "                            } else {\n"
        "                                btnRevert.isEnabled = true\n"
        '                                Toast.makeText(context, "Muutoksen peruminen epäonnistui", Toast.LENGTH_SHORT).show()\n'
        "                            }\n"
        "                        }\n"
        "                    }\n"
        "                \n"
        "}"
    )
    new_revert = (
        "                btnRevert.setOnClickListener {\n"
        "                    btnRevert.isEnabled = false\n"
        "                    val appCtx = context.applicationContext\n"
        "                    java.util.concurrent.Executors.newSingleThreadExecutor().execute {\n"
        "                        val ok = revertSingleChangeAndSave(appCtx, item)\n"
        "                        android.os.Handler(android.os.Looper.getMainLooper()).post {\n"
        "                            val act = context as? android.app.Activity\n"
        "                            if (act != null && (act.isFinishing || act.isDestroyed)) return@post\n"
        "                            if (ok) {\n"
        '                                Toast.makeText(appCtx, "Muutos peruttu: ${item.title}", Toast.LENGTH_SHORT).show()\n'
        "                                if (dialogRef?.isShowing == true) {\n"
        "                                    dialogRef?.dismiss()\n"
        "                                }\n"
        "                                onChanged?.invoke()\n"
        "                                showManageChangesDialog(context, onChanged)\n"
        "                            } else {\n"
        "                                btnRevert.isEnabled = true\n"
        '                                Toast.makeText(appCtx, "Muutoksen peruminen epäonnistui", Toast.LENGTH_SHORT).show()\n'
        "                            }\n"
        "                        }\n"
        "                    }\n"
        "                }"
    )
    text = replace_once(text, old_revert, new_revert, "Dialogin ja Activity-elinkaaren tarkistus btnRevert-kuuntelijassa")
    write_kt(path, text, nl)


def patch_numeron_parser(src_dir: Path) -> None:
    path = src_dir / "NumeronParser.kt"
    if not path.exists():
        return
    print(f"Käsitellään {path.name}...")
    text, nl = read_kt(path)

    old = (
        "        workShifts.add(currentLeave)\n"
        "        return workShifts"
    )
    new = (
        "        workShifts.add(currentLeave)\n"
        "        return workShifts.sortedBy { it.start }"
    )
    text = replace_once(text, old, new, "Yhdistettyjen lomien ja vuorojen aikajärjestys mergeConsecutiveLeaves-metodissa")
    write_kt(path, text, nl)


def patch_url_normalizer(src_dir: Path) -> None:
    path = src_dir / "UrlNormalizer.kt"
    if not path.exists():
        return
    print(f"Käsitellään {path.name}...")
    text, nl = read_kt(path)

    old = (
        "        // Jos käyttäjä syötti oman custom-domainin protokollalla, säilytetään polun kirjainkoko\n"
        '        if ((lower.startsWith("http://") || lower.startsWith("https://")) && !isNumeronHost) {\n'
        "            return trimmed.trimEnd('/')\n"
        "        }\n\n"
        "        // Jos käyttäjä syötti oman domainin ilman protokollaa (esim. wfm.yritys.fi)\n"
        '        if (!isNumeronHost && !trimmed.contains(" ") && trimmed.substringBefore("/").contains(".")) {\n'
        '            return "https://${trimmed.trimEnd(\'/\')}"\n'
        "        }"
    )
    new = (
        "        // Jos käyttäjä syötti oman custom-domainin protokollalla, säilytetään polun kirjainkoko\n"
        '        if ((lower.startsWith("http://") || lower.startsWith("https://")) && !isNumeronHost) {\n'
        '            val hostPart = trimmed.substringAfter("://").substringBefore("/").substringBefore("?")\n'
        '            if (hostPart.isBlank() || !hostPart.contains(".")) return ""\n'
        "            return trimmed.trimEnd('/')\n"
        "        }\n\n"
        "        // Jos käyttäjä syötti oman domainin ilman protokollaa (esim. wfm.yritys.fi)\n"
        '        if (!isNumeronHost && !trimmed.contains(" ") && trimmed.substringBefore("/").contains(".")) {\n'
        '            val hostPart = trimmed.substringBefore("/").substringBefore("?")\n'
        '            if (hostPart.startsWith(".") || hostPart.endsWith(".")) return ""\n'
        '            return "https://${trimmed.trimEnd(\'/\')}"\n'
        "        }"
    )
    text = replace_once(text, old, new, "Custom-domainin host-validointi UrlNormalizerissa")
    write_kt(path, text, nl)


def patch_quick_stamp_activity(src_dir: Path) -> None:
    path = src_dir / "QuickStampActivity.kt"
    if not path.exists():
        alt = src_dir / "QuickStampActivity_2.kt"
        if alt.exists():
            path = alt
        else:
            return
    print(f"Käsitellään {path.name}...")
    text, nl = read_kt(path)

    old_new_intent = (
        "        if (intent != null) {\n"
        "            isCompleted = false\n"
        "            sessionRetried = false\n"
        "            activeJob?.cancel()\n"
        "            cancelTimeout()\n"
        "            destroyHiddenWebView()\n"
        "            resetToLoadingUi()\n"
        "            processIntent(intent)\n"
        "        }"
    )
    new_new_intent = (
        "        if (intent != null) {\n"
        "            isCompleted = false\n"
        "            sessionRetried = false\n"
        "            activeJob?.cancel()\n"
        "            mainHandler.removeCallbacksAndMessages(null)\n"
        "            cancelTimeout()\n"
        "            destroyHiddenWebView()\n"
        "            resetToLoadingUi()\n"
        "            processIntent(intent)\n"
        "        }"
    )
    text = replace_once(text, old_new_intent, new_new_intent, "Kaikkien mainHandler-ajastusten tyhjennys onNewIntentissä")

    old_destroy = (
        "    override fun onDestroy() {\n"
        "        cancelTimeout()"
    )
    new_destroy = (
        "    override fun onDestroy() {\n"
        "        isCompleted = true\n"
        "        activeJob?.cancel()\n"
        "        mainHandler.removeCallbacksAndMessages(null)\n"
        "        cancelTimeout()"
    )
    text = replace_once(text, old_destroy, new_destroy, "Tilalipun ja handlerin siivous QuickStampActivity.onDestroyssa")
    write_kt(path, text, nl)


def create_stamping_web_helper(src_dir: Path) -> None:
    target = src_dir / "StampingWebHelper.kt"
    if target.exists():
        print(f"  [OK - jo olemassa] {target.name}")
        return
    print(f"Luodaan jaettu apuluokka {target.name}...")
    code = (
        "package fi.numeron.vuorovahti\n\n"
        "import org.json.JSONObject\n"
        "import org.json.JSONTokener\n\n"
        "/**\n"
        " * Jaettu JS- ja tilantarkistuslogiikka MainActivitylle ja QuickStampActivitylle.\n"
        " */\n"
        "object StampingWebHelper {\n\n"
        '    fun buildClickStampJs(targetLower: String): String = """\n'
        "        (function() {\n"
        "            var btn = document.getElementById('punchButton');\n"
        "            if (!btn) return JSON.stringify({ status: 'NO_BUTTON' });\n"
        "            var btnText = (btn.innerText || btn.textContent || '').trim();\n"
        "            if (!btnText) return JSON.stringify({ status: 'NO_BUTTON' });\n"
        "            var firstRow = '';\n"
        "            var rowEl = document.querySelector('#table-latest-stamps tbody tr, #table-latest-stamps tr');\n"
        "            if (rowEl) {\n"
        "                firstRow = (rowEl.innerText || rowEl.textContent || '').replace(/\\s+/g, ' ').trim();\n"
        "            }\n"
        "            if (btnText.toLowerCase().indexOf('$targetLower') !== -1) {\n"
        "                btn.click();\n"
        "                return JSON.stringify({ status: 'CLICKED', btn: btnText, row: firstRow });\n"
        "            } else {\n"
        "                return JSON.stringify({ status: 'WRONG_DIRECTION', btn: btnText, row: firstRow });\n"
        "            }\n"
        "        })();\n"
        '    """.trimIndent()\n\n'
        '    fun buildVerifyStampJs(): String = """\n'
        "        (function() {\n"
        "            var expired = false;\n"
        '            var modals = document.querySelectorAll(\'#session-expired-modal, #sessionExpiredModal, #SessionExpiredModal, .modal, [role="dialog"]\');\n'
        "            for (var i = 0; i < modals.length; i++) {\n"
        "                var m = modals[i];\n"
        "                var st = window.getComputedStyle(m);\n"
        "                var vis = (m.offsetParent !== null) || (st && st.display !== 'none' && st.visibility !== 'hidden');\n"
        "                if (vis) {\n"
        "                    var t = (m.innerText || m.textContent || '').toLowerCase();\n"
        "                    if (m.id === 'session-expired-modal' || m.id === 'sessionExpiredModal' || t.indexOf('istunto vanhentunut') !== -1 || t.indexOf('session expired') !== -1) {\n"
        "                        expired = true;\n"
        "                        break;\n"
        "                    }\n"
        "                }\n"
        "            }\n"
        "            if (window.location.pathname.toLowerCase().indexOf('/login') !== -1) {\n"
        "                expired = true;\n"
        "            }\n"
        "            var btn = document.getElementById('punchButton');\n"
        "            var btnText = btn ? (btn.innerText || btn.textContent || '').trim() : '';\n"
        "            var rowEl = document.querySelector('#table-latest-stamps tbody tr, #table-latest-stamps tr');\n"
        "            var firstRow = rowEl ? (rowEl.innerText || rowEl.textContent || '').replace(/\\s+/g, ' ').trim() : '';\n"
        "            return JSON.stringify({ btn: btnText, row: firstRow, expired: expired });\n"
        "        })();\n"
        '    """.trimIndent()\n\n'
        "    fun parseJsonResult(rawResult: String?): JSONObject? {\n"
        "        return try {\n"
        '            if (rawResult != null && rawResult != "null") {\n'
        "                val unescaped = JSONTokener(rawResult).nextValue() as? String\n"
        "                if (unescaped != null) JSONObject(unescaped) else null\n"
        "            } else {\n"
        "                null\n"
        "            }\n"
        "        } catch (_: Exception) {\n"
        "            null\n"
        "        }\n"
        "    }\n\n"
        "    fun isStampConfirmed(\n"
        "        targetLower: String,\n"
        "        beforeBtn: String,\n"
        "        beforeRow: String,\n"
        "        nowBtn: String,\n"
        "        nowRow: String\n"
        "    ): Boolean {\n"
        "        val buttonFlipped = nowBtn.isNotEmpty() && nowBtn != beforeBtn &&\n"
        "            nowBtn.lowercase().indexOf(targetLower) == -1\n"
        "        val rowUpdated = nowRow.isNotEmpty() && nowRow != beforeRow\n"
        "        return buttonFlipped || rowUpdated\n"
        "    }\n"
        "}\n"
    )
    write_kt(target, code, "\n")


def patch_main_activity(src_dir: Path) -> None:
    path = src_dir / "MainActivity.kt"
    if not path.exists():
        alt = src_dir / "MainActivity_2.kt"
        if alt.exists():
            path = alt
        else:
            return
    print(f"Käsitellään {path.name}...")
    text, nl = read_kt(path)

    old_destroy = (
        "    override fun onDestroy() {\n"
        "        recycleSnapshotBitmap()"
    )
    new_destroy = (
        "    override fun onDestroy() {\n"
        "        navigateJob?.cancel()\n"
        "        webView.removeCallbacks(transitionFallbackRunnable)\n"
        "        recycleSnapshotBitmap()"
    )
    text = replace_once(text, old_destroy, new_destroy, "navigateJob ja transitionFallbackRunnable siivous onDestroyssa")

    old_verify = (
        "                val buttonFlipped = nowBtn.isNotEmpty() && nowBtn != beforeBtn &&\n"
        "                    nowBtn.lowercase().indexOf(targetLower) == -1\n"
        "                val rowUpdated = nowRow.isNotEmpty() && nowRow != beforeRow\n\n"
        "                if (buttonFlipped || rowUpdated) {"
    )
    new_verify = (
        "                if (StampingWebHelper.isStampConfirmed(targetLower, beforeBtn, beforeRow, nowBtn, nowRow)) {"
    )
    text = replace_once(text, old_verify, new_verify, "Jaetun StampingWebHelper.isStampConfirmed käyttö MainActivityssa")

    write_kt(path, text, nl)


def main() -> None:
    src_dir = find_source_dir()
    print(f"Kohdehakemisto: {src_dir.resolve()}")
    print()
    patch_secure_credential_manager(src_dir)
    patch_support_billing_helper(src_dir)
    patch_settings_dialog_helper(src_dir)
    patch_demo_mode_helper(src_dir)
    patch_background_auth_helper(src_dir)
    patch_calendar_change_tracker(src_dir)
    patch_numeron_parser(src_dir)
    patch_url_normalizer(src_dir)
    create_stamping_web_helper(src_dir)
    patch_quick_stamp_activity(src_dir)
    patch_main_activity(src_dir)
    print()
    print("Valmis! Muista kasvattaa build.gradle(.kts) versionCode-arvoa yhdellä pienellä askeleella ennen Play Store -julkaisua.")


if __name__ == "__main__":
    main()
