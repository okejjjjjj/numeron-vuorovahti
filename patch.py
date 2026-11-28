#!/usr/bin/env python3
"""
Numeron Vuorovahti (V2) – Viimeisten löysien optimointi (patch_perf2.py):
1. Keystore / EncryptedSharedPreferences pois pääsäikeeltä:
   - DemoModeHelper.isDemoEnabled() lukee tavallisen NumeronPrefs/demo_mode-lipun ilman Keystore-avausta UI-säikeellä
   - SecureCredentialManager välimuistittaa tunnukset muistiin ensimmäisen IO-luvun jälkeen
   - QuickStampActivity siirtää tunnus- ja esto-tarkistukset Dispatchers.IO-säikeeseen -> kortti piirtyy 0 ms viiveellä
2. Kolminkertainen Jsoup.parse() -> yksi jäsennys per kuukausisivu (NumeronParser, MainActivity, ShiftReminderReceiver)
3. ShiftReminderReceiver.syncRequestsAndNotify() yhdistetty NumeronApiClient.fetchRequests()-rajapintaan:
   - Poistaa ~140 riviä päällekkäistä HTTP/JSON-koodia ja päivittää samalla Toiveet-natiivilistan välimuistin
4. app/build.gradle.kts: resourceConfigurations += listOf("fi", "en") karsii turhat kielikäännökset paketista ja nostaa versionCode +1
"""

import re
import sys
from pathlib import Path

SECURE_CREDENTIAL_MANAGER_KT = 'package fi.numeron.vuorovahti\n\nimport android.content.Context\nimport android.content.SharedPreferences\nimport androidx.security.crypto.EncryptedSharedPreferences\nimport androidx.security.crypto.MasterKey\n\nobject SecureCredentialManager {\n\n    private const val PREFS_FILE = "secure_numeron_prefs"\n    private const val KEY_USERNAME = "secure_username"\n    private const val KEY_PASSWORD = "secure_password"\n\n    @Volatile\n    private var cachedEncryptedPrefs: SharedPreferences? = null\n    @Volatile\n    private var credentialsLoaded: Boolean = false\n    @Volatile\n    private var cachedUsername: String? = null\n    @Volatile\n    private var cachedPassword: String? = null\n\n    internal fun getSharedEncryptedPrefs(context: Context): SharedPreferences? = getEncryptedPrefs(context)\n\n    private fun getEncryptedPrefs(context: Context): SharedPreferences? {\n        cachedEncryptedPrefs?.let { return it }\n        return synchronized(this) {\n            cachedEncryptedPrefs?.let { return@synchronized it }\n            val appCtx = context.applicationContext\n            fun createPrefs(): SharedPreferences {\n                val masterKey = MasterKey.Builder(appCtx, MasterKey.DEFAULT_MASTER_KEY_ALIAS)\n                    .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)\n                    .build()\n                return EncryptedSharedPreferences.create(\n                    appCtx,\n                    PREFS_FILE,\n                    masterKey,\n                    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,\n                    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM\n                )\n            }\n            try {\n                createPrefs().also { cachedEncryptedPrefs = it }\n            } catch (_: Exception) {\n                try {\n                    appCtx.deleteSharedPreferences(PREFS_FILE)\n                    val ks = java.security.KeyStore.getInstance("AndroidKeyStore")\n                    ks.load(null)\n                    if (ks.containsAlias(MasterKey.DEFAULT_MASTER_KEY_ALIAS)) {\n                        ks.deleteEntry(MasterKey.DEFAULT_MASTER_KEY_ALIAS)\n                    }\n                    createPrefs().also { cachedEncryptedPrefs = it }\n                } catch (_: Exception) {\n                    null\n                }\n            }\n        }\n    }\n\n    private fun migrateLegacyIfNeeded(context: Context) {\n        val legacyPrefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n        val legacyUser = legacyPrefs.getString("username", null)\n        val legacyPass = legacyPrefs.getString("password", null)\n        if (!legacyUser.isNullOrEmpty() || !legacyPass.isNullOrEmpty()) {\n            val enc = getEncryptedPrefs(context)\n            if (enc != null) {\n                enc.edit().apply {\n                    if (!legacyUser.isNullOrEmpty() && enc.getString(KEY_USERNAME, null).isNullOrEmpty()) {\n                        putString(KEY_USERNAME, legacyUser)\n                    }\n                    if (!legacyPass.isNullOrEmpty() && enc.getString(KEY_PASSWORD, null).isNullOrEmpty()) {\n                        putString(KEY_PASSWORD, legacyPass)\n                    }\n                    apply()\n                }\n                legacyPrefs.edit().remove("username").remove("password").apply()\n            }\n        }\n    }\n\n    private fun ensureCredentialsLoaded(context: Context) {\n        if (credentialsLoaded) return\n        synchronized(this) {\n            if (credentialsLoaded) return\n            migrateLegacyIfNeeded(context)\n            val enc = getEncryptedPrefs(context)\n            val legacyPrefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n            val u = enc?.getString(KEY_USERNAME, null)?.takeIf { it.isNotEmpty() }\n                ?: legacyPrefs.getString("username", null)?.takeIf { it.isNotEmpty() }\n            val p = enc?.getString(KEY_PASSWORD, null)?.takeIf { it.isNotEmpty() }\n                ?: legacyPrefs.getString("password", null)?.takeIf { it.isNotEmpty() }\n            cachedUsername = u\n            cachedPassword = p\n            credentialsLoaded = true\n        }\n    }\n\n    fun saveCredentials(context: Context, username: String, password: String) {\n        synchronized(this) {\n            cachedUsername = username.takeIf { it.isNotEmpty() }\n            cachedPassword = password.takeIf { it.isNotEmpty() }\n            credentialsLoaded = true\n        }\n        getEncryptedPrefs(context)?.edit()?.apply {\n            if (username.isEmpty()) remove(KEY_USERNAME) else putString(KEY_USERNAME, username)\n            if (password.isEmpty()) remove(KEY_PASSWORD) else putString(KEY_PASSWORD, password)\n            apply()\n        }\n        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n            .edit()\n            .remove("username")\n            .remove("password")\n            .apply()\n    }\n\n    fun getUsername(context: Context): String? {\n        ensureCredentialsLoaded(context)\n        return cachedUsername\n    }\n\n    fun getPassword(context: Context): String? {\n        ensureCredentialsLoaded(context)\n        return cachedPassword\n    }\n\n    fun clearCredentials(context: Context) {\n        synchronized(this) {\n            cachedUsername = null\n            cachedPassword = null\n            credentialsLoaded = true\n        }\n        getEncryptedPrefs(context)?.edit()?.clear()?.apply()\n        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE).edit()\n            .remove("username")\n            .remove("password")\n            .putBoolean("demo_mode", true)\n            .apply()\n    }\n}\n'


def find_file(filename: str) -> Path | None:
    candidates = [
        Path("app/src/main/java/fi/numeron/vuorovahti") / filename,
        Path("src/main/java/fi/numeron/vuorovahti") / filename,
        Path("app") / filename,
        Path(filename),
    ]
    for c in candidates:
        if c.exists():
            return c
    for p in Path(".").rglob(filename):
        if ".git" not in p.parts and "build" not in p.parts:
            return p
    return None


def read_text_keep_nl(path: Path) -> tuple[str, str]:
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def write_text_keep_nl(path: Path, content: str, newline: str) -> None:
    normalized = content.replace("\r\n", "\n")
    if newline == "\r\n":
        normalized = normalized.replace("\n", "\r\n")
    path.write_bytes(normalized.encode("utf-8"))


def replace_once(content: str, old: str, new: str, label: str) -> str:
    if new and new in content:
        print(f"  [OK - jo sovellettu] {label}")
        return content
    if old not in content:
        print(f"  [VAROITUS - kohdetta ei löytynyt] {label}")
        return content
    print(f"  [PÄIVITETTY] {label}")
    return content.replace(old, new, 1)


def patch_secure_credential_manager(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    target = SECURE_CREDENTIAL_MANAGER_KT.strip() + "\n"
    if text.strip() == target.strip():
        print("  [OK - jo ajantasalla] SecureCredentialManager.kt (muistivälimuisti)")
        return False
    write_text_keep_nl(path, target, nl)
    print("  [PÄIVITETTY] SecureCredentialManager.kt (in-memory-välimuisti + demo_mode-synkka)")
    return True


def patch_demo_mode_helper(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    old_is_demo = """    fun isDemoEnabled(context: Context): Boolean {
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
    }"""

    new_is_demo = """    fun isDemoEnabled(context: Context): Boolean {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val org = (prefs.getString("org_raw_input", "") ?: "").trim()
        val serverUrl = (prefs.getString("server_url", "") ?: "").trim()

        if (org.isEmpty() && serverUrl.isEmpty()) {
            return true
        }
        if (UrlNormalizer.isDemoInput(org) || UrlNormalizer.isDemoInput(serverUrl)) {
            return true
        }
        if (prefs.contains("demo_mode")) {
            return prefs.getBoolean("demo_mode", true)
        }
        val user = (SecureCredentialManager.getUsername(context) ?: "").trim()
        val pass = SecureCredentialManager.getPassword(context) ?: ""
        val demo = user.isEmpty() || pass.isEmpty() || isDemoCredentials(org.ifEmpty { serverUrl }, user, pass)
        prefs.edit().putBoolean("demo_mode", demo).apply()
        return demo
    }"""

    text = replace_once(
        text,
        old_is_demo,
        new_is_demo,
        "DemoModeHelper.isDemoEnabled ei avaa Keystorea pääsäikeellä"
    )
    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_quick_stamp_activity(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    if "import kotlinx.coroutines.withContext\n" not in text:
        text = replace_once(
            text,
            "import kotlinx.coroutines.launch\n",
            "import kotlinx.coroutines.launch\nimport kotlinx.coroutines.withContext\n",
            "Lisätty withContext-import QuickStampActivity.kt:hen"
        )
    else:
        print("  [OK - jo sovellettu] withContext-import QuickStampActivity.kt:ssä")

    old_cred_block = """        val baseUrl = UrlNormalizer.getSavedBaseUrl(this)
        val user = SecureCredentialManager.getUsername(this).orEmpty()
        val pass = SecureCredentialManager.getPassword(this).orEmpty()

        if (baseUrl.isEmpty() || user.isEmpty() || pass.isEmpty()) {
            showFinalState(
                title = "Tunnukset puuttuvat",
                subtitle = "Tarkista kirjautuminen sovelluksesta",
                badgeText = "!",
                badgeFillHex = "#3B2810",
                badgeStrokeHex = "#F59E0B",
                badgeTextHex = "#FBBF24",
                closeDelayMs = 1700L
            )
            return
        }

        scheduleTimeout(22_000L)

        if (BackgroundAuthHelper.isCredentialBlocked(this)) {
            showFinalState(
                title = if (en) "Login failed" else "Kirjautuminen epäonnistui",
                subtitle = if (en) "Check username and password in Settings" else "Tarkista käyttäjätunnus ja salasana asetuksista",
                badgeText = "!",
                badgeFillHex = "#3B181E",
                badgeStrokeHex = "#EF4444",
                badgeTextHex = "#F87171",
                closeDelayMs = 1700L
            )
            return
        }

        activeJob = scope.launch {
            val wantIn = !isEnding"""

    new_cred_block = """        val baseUrl = UrlNormalizer.getSavedBaseUrl(this)
        if (baseUrl.isEmpty()) {
            showFinalState(
                title = if (en) "Credentials missing" else "Tunnukset puuttuvat",
                subtitle = if (en) "Check login in the app" else "Tarkista kirjautuminen sovelluksesta",
                badgeText = "!",
                badgeFillHex = "#3B2810",
                badgeStrokeHex = "#F59E0B",
                badgeTextHex = "#FBBF24",
                closeDelayMs = 1700L
            )
            return
        }

        scheduleTimeout(22_000L)

        activeJob = scope.launch {
            val (hasCredentials, isBlocked) = withContext(Dispatchers.IO) {
                val u = SecureCredentialManager.getUsername(this@QuickStampActivity).orEmpty()
                val p = SecureCredentialManager.getPassword(this@QuickStampActivity).orEmpty()
                val blocked = if (u.isNotEmpty() && p.isNotEmpty()) {
                    BackgroundAuthHelper.isCredentialBlocked(this@QuickStampActivity)
                } else {
                    false
                }
                (u.isNotEmpty() && p.isNotEmpty()) to blocked
            }
            if (isCompleted) return@launch

            if (!hasCredentials) {
                showFinalState(
                    title = if (en) "Credentials missing" else "Tunnukset puuttuvat",
                    subtitle = if (en) "Check login in the app" else "Tarkista kirjautuminen sovelluksesta",
                    badgeText = "!",
                    badgeFillHex = "#3B2810",
                    badgeStrokeHex = "#F59E0B",
                    badgeTextHex = "#FBBF24",
                    closeDelayMs = 1700L
                )
                return@launch
            }

            if (isBlocked) {
                showFinalState(
                    title = if (en) "Login failed" else "Kirjautuminen epäonnistui",
                    subtitle = if (en) "Check username and password in Settings" else "Tarkista käyttäjätunnus ja salasana asetuksista",
                    badgeText = "!",
                    badgeFillHex = "#3B181E",
                    badgeStrokeHex = "#EF4444",
                    badgeTextHex = "#F87171",
                    closeDelayMs = 1700L
                )
                return@launch
            }

            val wantIn = !isEnding"""

    text = replace_once(
        text,
        old_cred_block,
        new_cred_block,
        "QuickStampActivity tarkistaa tunnukset ja eston IO-säikeessä"
    )

    old_fb_check = "if (result.fallbackToWebView && !BackgroundAuthHelper.isCredentialBlocked(this@QuickStampActivity)) {"
    new_fb_check = "val blockedNow = if (result.fallbackToWebView) withContext(Dispatchers.IO) { BackgroundAuthHelper.isCredentialBlocked(this@QuickStampActivity) } else true\n                    if (result.fallbackToWebView && !blockedNow) {"
    text = replace_once(
        text,
        old_fb_check,
        new_fb_check,
        "QuickStampActivity varapolun estotarkistus IO-säikeessä"
    )

    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_numeron_parser(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    # 1. parseCalendarHtml -> delegoi parseCalendarDoc(doc)-metodille
    old_cal_sig = """    fun parseCalendarHtml(html: String): List<WorkShift>? {
        val doc = Jsoup.parse(html)"""
    new_cal_sig = """    fun parseCalendarHtml(html: String): List<WorkShift>? = parseCalendarDoc(Jsoup.parse(html))

    fun parseCalendarDoc(doc: org.jsoup.nodes.Document): List<WorkShift>? {"""
    text = replace_once(text, old_cal_sig, new_cal_sig, "NumeronParser.parseCalendarDoc(Document)")

    # 2. enrichShiftsWithListComments -> jaettu enrichShiftsWithListCommentsFromCircleDates
    old_enrich_sig = """    fun enrichShiftsWithListComments(
        baseUrl: String,
        cookieHeader: String?,
        htmlPages: List<String>,
        shifts: List<WorkShift>
    ): List<WorkShift> {
        if (baseUrl.isBlank() || shifts.isEmpty()) return shifts

        val circleDates = htmlPages.flatMapTo(mutableSetOf()) { extractCircleDates(it) }
        if (circleDates.isEmpty()) return shifts"""
    new_enrich_sig = """    fun enrichShiftsWithListComments(
        baseUrl: String,
        cookieHeader: String?,
        htmlPages: List<String>,
        shifts: List<WorkShift>
    ): List<WorkShift> {
        if (baseUrl.isBlank() || shifts.isEmpty()) return shifts
        val circleDates = htmlPages.flatMapTo(mutableSetOf()) { extractCircleDates(it) }
        return enrichShiftsWithListCommentsFromCircleDates(baseUrl, cookieHeader, circleDates, shifts)
    }

    fun enrichShiftsWithListCommentsFromCircleDates(
        baseUrl: String,
        cookieHeader: String?,
        circleDates: Set<LocalDate>,
        shifts: List<WorkShift>
    ): List<WorkShift> {
        if (baseUrl.isBlank() || shifts.isEmpty() || circleDates.isEmpty()) return shifts"""
    text = replace_once(
        text,
        old_enrich_sig,
        new_enrich_sig,
        "NumeronParser.enrichShiftsWithListCommentsFromCircleDates()"
    )

    # 3. parseMonthForDisplay -> delegoi parseMonthForDisplayDoc(doc)-metodille
    old_disp_sig = """    fun parseMonthForDisplay(html: String): MonthDisplayData? {
        val doc = Jsoup.parse(html)"""
    new_disp_sig = """    fun parseMonthForDisplay(html: String): MonthDisplayData? = parseMonthForDisplayDoc(Jsoup.parse(html))

    fun parseMonthForDisplayDoc(doc: org.jsoup.nodes.Document): MonthDisplayData? {"""
    text = replace_once(text, old_disp_sig, new_disp_sig, "NumeronParser.parseMonthForDisplayDoc(Document)")

    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_main_activity(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    old_sync_parse = """            pagesToParse.forEach { html ->
                NumeronParser.parseMonthForDisplay(html)?.let { displayData ->
                    NumeronApiClient.saveMonthDisplayCache(this@MainActivity, displayData)
                }
            }
            val parsedPages = pagesToParse.map { NumeronParser.parseCalendarHtml(it) }
            if (parsedPages.any { it == null }) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(
                        this@MainActivity,
                        if (DemoModeHelper.isEnglish(this@MainActivity)) "Failed to read shifts – calendar was not modified" else "Työvuorojen luku epäonnistui – kalenteria ei muutettu",
                        Toast.LENGTH_LONG
                    ).show()
                }
                return@launch
            }
            val baseUrl = getBaseUrl()
            val cookies = SessionCookieStore.getCookieHeader(this@MainActivity, baseUrl)
            val rawShifts = NumeronParser.enrichShiftsWithListComments(
                baseUrl = baseUrl,
                cookieHeader = cookies,
                htmlPages = pagesToParse,
                shifts = parsedPages.filterNotNull().flatten()
            )"""

    new_sync_parse = """            val parsedDocs = pagesToParse.map { org.jsoup.Jsoup.parse(it) }
            val circleDates = mutableSetOf<LocalDate>()
            parsedDocs.forEach { doc ->
                val displayData = NumeronParser.parseMonthForDisplayDoc(doc)
                if (displayData != null) {
                    NumeronApiClient.saveMonthDisplayCache(this@MainActivity, displayData)
                    displayData.days.values.forEach { day ->
                        if (day.hasCommentCircle) circleDates.add(day.date)
                    }
                } else {
                    circleDates.addAll(NumeronParser.extractCircleDatesFromDoc(doc))
                }
            }
            val parsedPages = parsedDocs.map { NumeronParser.parseCalendarDoc(it) }
            if (parsedPages.any { it == null }) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(
                        this@MainActivity,
                        if (DemoModeHelper.isEnglish(this@MainActivity)) "Failed to read shifts – calendar was not modified" else "Työvuorojen luku epäonnistui – kalenteria ei muutettu",
                        Toast.LENGTH_LONG
                    ).show()
                }
                return@launch
            }
            val baseUrl = getBaseUrl()
            val cookies = SessionCookieStore.getCookieHeader(this@MainActivity, baseUrl)
            val rawShifts = NumeronParser.enrichShiftsWithListCommentsFromCircleDates(
                baseUrl = baseUrl,
                cookieHeader = cookies,
                circleDates = circleDates,
                shifts = parsedPages.filterNotNull().flatten()
            )"""

    text = replace_once(
        text,
        old_sync_parse,
        new_sync_parse,
        "MainActivity.processSyncedCalendarPages jäsentää jokaisen sivun vain kerran"
    )

    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_shift_reminder_receiver(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    # 1. Poistetaan käyttämättömäksi jäävä JSONObject-import
    if "import org.json.JSONObject\n" in text:
        text = text.replace("import org.json.JSONObject\n", "", 1)
        print("  [PÄIVITETTY] Poistettu käyttämätön JSONObject-import ShiftReminderReceiver.kt:stä")
    else:
        print("  [OK - jo sovellettu] JSONObject-import poistettu ShiftReminderReceiver.kt:stä")

    # 2. Korvataan päällekkäinen toiveiden haku- ja JSON-koodi NumeronApiClient.fetchRequests()-kutsulla
    new_req_block = """        suspend fun syncRequestsAndNotify(context: Context, baseUrl: String): Int {
            if (baseUrl.isBlank()) return 0
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val result = NumeronApiClient.fetchRequests(context, "active")
            val items = result.items
            if (items == null || result.fromCache) {
                prefs.edit()
                    .putString("last_requests_check_status", if (result.fromCache) "CACHE_ONLY" else "FETCH_FAILED")
                    .apply()
                return 0
            }
            return checkRequestUpdates(context, items)
        }

        private fun checkRequestUpdates(context: Context, items: List<PersonRequestItem>): Int {
            var sentCount = 0
            try {
                val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                val notifiedIds = prefs.getStringSet("notified_request_ids", emptySet())?.toMutableSet() ?: mutableSetOf()
                val baselineInitialized = prefs.getBoolean("requests_baseline_initialized", false) || notifiedIds.isNotEmpty()
                val nowMs = System.currentTimeMillis()
                val dateFmt = java.time.format.DateTimeFormatter.ofPattern("dd.MM.yyyy")
                val en = DemoModeHelper.isEnglish(context)
                var changed = false
                var processedFound = 0

                for (item in items) {
                    val statusId = item.statusCode
                    if (item.id > 0 && (statusId == 50 || statusId == 80 || statusId == 40)) {
                        processedFound++
                        val key = "${item.id}_$statusId"
                        if (!notifiedIds.contains(key)) {
                            notifiedIds.add(key)
                            changed = true
                            val approvedMs = item.approvedDateMs
                            val approvedRecently = approvedMs != null && (nowMs - approvedMs) in 0L..(24L * 60L * 60L * 1000L)
                            if (baselineInitialized || approvedRecently) {
                                val dateStr = item.dateFrom?.format(dateFmt).orEmpty()
                                val bodyText = if (dateStr.isNotEmpty()) "${item.type} ($dateStr)" else item.type
                                showRequestDecisionNotification(
                                    context,
                                    if (en) "Request processed: ${item.statusDescription}" else "Toive käsitelty: ${item.statusDescription}",
                                    bodyText,
                                    item.id
                                )
                                sentCount++
                            }
                        }
                    }
                }
                prefs.edit().apply {
                    putString("last_requests_check_status", "OK:${items.size}/$processedFound")
                    if (changed || !baselineInitialized) {
                        putStringSet("notified_request_ids", notifiedIds)
                        putBoolean("requests_baseline_initialized", true)
                    }
                }.apply()
            } catch (_: Exception) {
            }
            return sentCount
        }"""

    if "suspend fun syncRequestsAndNotify(" in text:
        print("  [OK - jo sovellettu] ShiftReminderReceiver.syncRequestsAndNotify käyttää NumeronApiClientia")
    else:
        m_req = re.search(
            r"        fun syncRequestsAndNotify\(context: Context, baseUrl: String\): Int \{.*?\n        \}(?=\n    \}\n\})",
            text,
            re.S
        )
        if m_req:
            text = text[:m_req.start()] + new_req_block + text[m_req.end():]
            print("  [PÄIVITETTY] ShiftReminderReceiver.syncRequestsAndNotify yhdistetty NumeronApiClient.fetchRequests()-rajapintaan")
        else:
            print("  [VAROITUS - kohdetta ei löytynyt] ShiftReminderReceiver.syncRequestsAndNotify")

    # 3. BackgroundSyncWorker: yksi Jsoup.parse() per kuukausisivu
    old_worker_parse = """                pages.forEach { html ->
                    NumeronParser.parseMonthForDisplay(html)?.let { displayData ->
                        NumeronApiClient.saveMonthDisplayCache(appContext, displayData)
                    }
                }
                val parsed = pages.map { NumeronParser.parseCalendarHtml(it) }
                if (parsed.any { it == null }) {
                    null
                } else {
                    val cookies = SessionCookieStore.getCookieHeader(appContext, baseUrl)
                    val enriched = NumeronParser.enrichShiftsWithListComments(
                        baseUrl = baseUrl,
                        cookieHeader = cookies,
                        htmlPages = pages,
                        shifts = parsed.filterNotNull().flatten()
                    )
                    NumeronParser.mergeConsecutiveLeaves(enriched)
                }"""

    new_worker_parse = """                val docs = pages.map { org.jsoup.Jsoup.parse(it) }
                val circleDates = mutableSetOf<LocalDate>()
                docs.forEach { doc ->
                    val displayData = NumeronParser.parseMonthForDisplayDoc(doc)
                    if (displayData != null) {
                        NumeronApiClient.saveMonthDisplayCache(appContext, displayData)
                        displayData.days.values.forEach { day ->
                            if (day.hasCommentCircle) circleDates.add(day.date)
                        }
                    } else {
                        circleDates.addAll(NumeronParser.extractCircleDatesFromDoc(doc))
                    }
                }
                val parsed = docs.map { NumeronParser.parseCalendarDoc(it) }
                if (parsed.any { it == null }) {
                    null
                } else {
                    val cookies = SessionCookieStore.getCookieHeader(appContext, baseUrl)
                    val enriched = NumeronParser.enrichShiftsWithListCommentsFromCircleDates(
                        baseUrl = baseUrl,
                        cookieHeader = cookies,
                        circleDates = circleDates,
                        shifts = parsed.filterNotNull().flatten()
                    )
                    NumeronParser.mergeConsecutiveLeaves(enriched)
                }"""

    text = replace_once(
        text,
        old_worker_parse,
        new_worker_parse,
        "BackgroundSyncWorker jäsentää jokaisen kuukausisivun vain kerran"
    )

    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_build_gradle(path: Path, should_bump_version: bool) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    if 'resourceConfigurations += listOf("fi", "en")' in text:
        print('  [OK - jo sovellettu] resourceConfigurations += listOf("fi", "en")')
    else:
        m_vname = re.search(r'(        versionName = "[^"]+"\n)', text)
        if m_vname:
            text = (
                text[:m_vname.end()]
                + '        resourceConfigurations += listOf("fi", "en")\n'
                + text[m_vname.end():]
            )
            print('  [PÄIVITETTY] Lisätty resourceConfigurations += listOf("fi", "en")')
        else:
            print("  [VAROITUS] versionName-riviä ei löytynyt build.gradle.kts:stä")

    if should_bump_version:
        m_code = re.search(r"versionCode\s*=\s*(\d+)", text)
        if m_code:
            old_code = int(m_code.group(1))
            new_code = old_code + 1
            text = text[:m_code.start()] + f"versionCode = {new_code}" + text[m_code.end():]
            print(f"  [PÄIVITETTY] versionCode {old_code} -> {new_code}")

        m_name = re.search(r'versionName\s*=\s*"(\d+)\.(\d+)\.(\d+)"', text)
        if m_name:
            maj, minor, patch_num = int(m_name.group(1)), int(m_name.group(2)), int(m_name.group(3))
            old_name = f"{maj}.{minor}.{patch_num}"
            new_name = f"{maj}.{minor}.{patch_num + 1}"
            text = text[:m_name.start()] + f'versionName = "{new_name}"' + text[m_name.end():]
            print(f'  [PÄIVITETTY] versionName "{old_name}" -> "{new_name}"')
    else:
        print("  [OK - jo sovellettu] versiota ei koroteta toistuvassa ajossa")

    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def main() -> int:
    changed = 0

    gr_path = find_file("build.gradle.kts")
    already_applied = False
    if gr_path is not None:
        gr_txt, _ = read_text_keep_nl(gr_path)
        already_applied = 'resourceConfigurations += listOf("fi", "en")' in gr_txt

    for filename, fn in [
        ("SecureCredentialManager.kt", patch_secure_credential_manager),
        ("DemoModeHelper.kt", patch_demo_mode_helper),
        ("QuickStampActivity.kt", patch_quick_stamp_activity),
        ("NumeronParser.kt", patch_numeron_parser),
        ("MainActivity.kt", patch_main_activity),
        ("ShiftReminderReceiver.kt", patch_shift_reminder_receiver),
    ]:
        p = find_file(filename)
        if p is None:
            print(f"[EI LÖYTYNYT] {filename}")
            continue
        print(f"Käsitellään: {p}")
        if fn(p):
            changed += 1

    if gr_path is not None:
        print(f"Käsitellään: {gr_path}")
        if patch_build_gradle(gr_path, should_bump_version=(not already_applied)):
            changed += 1
    else:
        print("[EI LÖYTYNYT] build.gradle.kts")

    print(f"\nValmis! Muokattuja tiedostoja: {changed}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
