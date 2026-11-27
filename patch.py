#!/usr/bin/env python3
"""
Numeron Vuorovahti – Vaiheet 1–4: Täysin natiivi käyttöliittymä + suora HTTP-leimaus + laiska WebView (patch.py)
- Vaihe 1: Laiska WebView, NumeronApiClient, tarkka maxSessionTimeInMilliseconds-istuntoaika, eligibility-esto
- Vaihe 2: Natiivi Vuorot-kuukausikalenteri (välimuisti + offline + taustahaku + päivän yksityiskohdat + kommentit)
- Vaihe 3: Natiivi Toiveet-lista (suora POST /PersonRequests/Read + välimuisti + laiska WebView muokkaukseen/lisäykseen)
- Vaihe 4: Natiivi Leimaus-näkymä (NativeStampView) + suora HTTP-pikaleimaus (ValidateStampSave + SaveStamp) myös ilmoituksista (QuickStampActivity)
- Toimii sekä alkuperäisen main-haaran että Vaiheet 1–3 sisältävän V2-haaran päällä (idempotentti).
- Versiokoodin korotus: versionCode -> 125, versionName -> "3.2.183"
"""

import sys
from pathlib import Path


def find_file(filename: str) -> Path | None:
    candidates = [
        Path("app/src/main/java/fi/numeron/vuorovahti") / filename,
        Path("src/main/java/fi/numeron/vuorovahti") / filename,
        Path("app/src/main/res/layout") / filename,
        Path("src/main/res/layout") / filename,
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


def write_new_file(path: Path, content: str, label: str) -> bool:
    normalized = content.replace("\r\n", "\n").lstrip("\n")
    if path.exists():
        existing, nl = read_text_keep_nl(path)
        if existing == normalized:
            print(f"  [OK - jo ajantasalla] {label} ({path})")
            return False
        write_text_keep_nl(path, normalized, nl)
        print(f"  [PÄIVITETTY] {label} ({path})")
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(normalized.encode("utf-8"))
    print(f"  [LUOTU] {label} ({path})")
    return True


def replace_once(content: str, old: str, new: str, label: str) -> str:
    if new in content:
        print(f"  [OK - jo sovellettu] {label}")
        return content
    if old not in content:
        print(f"  [VAROITUS - kohdetta ei löytynyt] {label}")
        return content
    print(f"  [PÄIVITETTY] {label}")
    return content.replace(old, new, 1)


def replace_any(content: str, olds: list[str], new: str, label: str) -> str:
    if new in content:
        print(f"  [OK - jo sovellettu] {label}")
        return content
    for old in olds:
        if old in content:
            print(f"  [PÄIVITETTY] {label}")
            return content.replace(old, new, 1)
    print(f"  [VAROITUS - kohdetta ei löytynyt] {label}")
    return content

NUMERON_API_CLIENT_KT = 'package fi.numeron.vuorovahti\n\nimport android.content.Context\nimport android.webkit.CookieManager\nimport kotlinx.coroutines.Dispatchers\nimport kotlinx.coroutines.withContext\nimport org.json.JSONArray\nimport org.json.JSONObject\nimport org.jsoup.Jsoup\nimport java.io.File\nimport java.io.OutputStreamWriter\nimport java.net.HttpURLConnection\nimport java.net.URL\nimport java.net.URLEncoder\nimport java.time.Instant\nimport java.time.LocalDate\nimport java.time.ZoneId\n\ndata class PersonRequestItem(\n    val id: Int,\n    val type: String,\n    val dateFrom: LocalDate?,\n    val dateTo: LocalDate?,\n    val timeFromText: String,\n    val timeToText: String,\n    val info: String,\n    val statusCode: Int,\n    val statusDescription: String,\n    val belongsToSeries: Boolean,\n    val approvedBy: String,\n    val approvedDateMs: Long?\n)\n\ndata class RequestsFetchResult(\n    val items: List<PersonRequestItem>?,\n    val fromCache: Boolean = false,\n    val errorMessage: String? = null\n)\n\ndata class StampReasonCode(\n    val id: Int,\n    val label: String\n)\n\ndata class StampHistoryRow(\n    val rowId: String,\n    val dayText: String,\n    val timeText: String,\n    val directionText: String,\n    val isIn: Boolean,\n    val typeText: String\n)\n\ndata class StampingPageState(\n    val shiftTimes: String,\n    val shiftWorkplace: String,\n    val shiftDetails: String,\n    val nextDirection: String,\n    val punchButtonText: String,\n    val defaultReasonCode: Int,\n    val reasonCodes: List<StampReasonCode>,\n    val latestStamps: List<StampHistoryRow>,\n    val hasMoreStamps: Boolean,\n    val currentTake: Int,\n    val verificationToken: String,\n    val saveStampUrl: String,\n    val validateStampSaveUrl: String,\n    val getMoreStampsUrl: String,\n    val fromCache: Boolean = false\n)\n\nsealed class StampSubmitResult {\n    data class Success(\n        val updatedState: StampingPageState?,\n        val directionUsed: String,\n        val serverMessage: String = ""\n    ) : StampSubmitResult()\n\n    data class AlreadyInDirection(val nextDirection: String) : StampSubmitResult()\n    data class ValidationRejected(val message: String) : StampSubmitResult()\n    data class Failed(val message: String, val fallbackToWebView: Boolean = false) : StampSubmitResult()\n}\n\nobject NumeronApiClient {\n\n    private val MAX_SESSION_REGEX = Regex("maxSessionTimeInMilliseconds\\\\s*=\\\\s*(\\\\d+)")\n    private val DOTNET_DATE_REGEX = Regex("/Date\\\\((-?\\\\d+)\\\\)/")\n    private const val MOBILE_UA =\n        "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"\n\n    private data class SimpleHttpResponse(\n        val statusCode: Int,\n        val body: String,\n        val location: String = ""\n    )\n\n    fun extractAndSaveMaxSessionTime(context: Context, html: String) {\n        if (html.isEmpty()) return\n        val match = MAX_SESSION_REGEX.find(html) ?: return\n        val expiryMs = match.groupValues[1].toLongOrNull() ?: return\n        val nowMs = System.currentTimeMillis()\n        if (expiryMs > nowMs) {\n            context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n                .edit()\n                .putLong("server_session_expiry_ms", expiryMs)\n                .putLong("last_valid_session_ms", nowMs)\n                .apply()\n        }\n    }\n\n    fun isSessionLikelyValid(\n        context: Context,\n        baseUrl: String,\n        isAutoStamping: Boolean = false\n    ): Boolean {\n        if (baseUrl.isBlank()) return false\n        val existingCookies = try {\n            CookieManager.getInstance().getCookie(baseUrl)\n        } catch (_: Exception) {\n            null\n        }\n        if (existingCookies.isNullOrBlank()) return false\n\n        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n        val nowMs = System.currentTimeMillis()\n        val serverExpiryMs = prefs.getLong("server_session_expiry_ms", 0L)\n        if (serverExpiryMs > 0L) {\n            val bufferMs = if (isAutoStamping) 15L * 60_000L else 10L * 60_000L\n            return nowMs < (serverExpiryMs - bufferMs)\n        }\n\n        val lastSessionMs = prefs.getLong("last_valid_session_ms", 0L)\n        val maxAgeMs = if (isAutoStamping) 10L * 60_000L else 4L * 60L * 60_000L\n        return lastSessionMs > 0L && (nowMs - lastSessionMs) <= maxAgeMs\n    }\n\n    private fun resolveAbsoluteUrl(baseUrl: String, pathOrUrl: String): String {\n        val clean = pathOrUrl.trim()\n        if (clean.startsWith("http://", ignoreCase = true) || clean.startsWith("https://", ignoreCase = true)) {\n            return clean\n        }\n        return baseUrl.trimEnd(\'/\') + if (clean.startsWith("/")) clean else "/$clean"\n    }\n\n    private fun formEncode(params: List<Pair<String, String>>): String {\n        return params.joinToString("&") { (k, v) ->\n            "${URLEncoder.encode(k, "UTF-8")}=${URLEncoder.encode(v, "UTF-8")}"\n        }\n    }\n\n    private fun executeAjaxPost(\n        baseUrl: String,\n        urlString: String,\n        body: String,\n        accept: String,\n        refererPath: String = "/WorktimeStamping"\n    ): SimpleHttpResponse? {\n        var conn: HttpURLConnection? = null\n        return try {\n            val cookies = CookieManager.getInstance().getCookie(baseUrl)\n            if (cookies.isNullOrBlank()) return null\n\n            val origin = try {\n                val u = URL(baseUrl)\n                val portPart = if (u.port > 0 && u.port != u.defaultPort) ":${u.port}" else ""\n                "${u.protocol}://${u.host}$portPart"\n            } catch (_: Exception) {\n                baseUrl.trimEnd(\'/\')\n            }\n\n            conn = (URL(urlString).openConnection() as HttpURLConnection).apply {\n                requestMethod = "POST"\n                instanceFollowRedirects = false\n                setRequestProperty("Cookie", cookies)\n                setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")\n                setRequestProperty("Accept", accept)\n                setRequestProperty("X-Requested-With", "XMLHttpRequest")\n                setRequestProperty("Origin", origin)\n                setRequestProperty("Referer", resolveAbsoluteUrl(baseUrl, refererPath))\n                setRequestProperty("User-Agent", MOBILE_UA)\n                doOutput = true\n                connectTimeout = 15_000\n                readTimeout = 15_000\n            }\n\n            OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { writer ->\n                writer.write(body)\n                writer.flush()\n            }\n\n            val code = conn.responseCode\n            val location = conn.getHeaderField("Location").orEmpty()\n            val stream = if (code in 200..299) conn.inputStream else conn.errorStream\n            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()\n\n            // Päivitetään mahdolliset Set-Cookie-otsikot CookieManageriin\n            val cm = CookieManager.getInstance()\n            val secureAttr = if (baseUrl.startsWith("https://", ignoreCase = true)) "; Secure" else ""\n            conn.headerFields\n                .filterKeys { it != null && it.equals("Set-Cookie", ignoreCase = true) }\n                .values\n                .flatten()\n                .forEach { rawCookie ->\n                    val pair = rawCookie.substringBefore(";").trim()\n                    if (pair.contains("=")) {\n                        cm.setCookie(baseUrl, "$pair; Path=/$secureAttr")\n                    }\n                }\n\n            SimpleHttpResponse(statusCode = code, body = text, location = location)\n        } catch (_: Exception) {\n            null\n        } finally {\n            conn?.disconnect()\n        }\n    }\n\n    private fun executeAjaxGet(\n        baseUrl: String,\n        urlString: String,\n        refererPath: String = "/WorktimeStamping"\n    ): SimpleHttpResponse? {\n        var conn: HttpURLConnection? = null\n        return try {\n            val cookies = CookieManager.getInstance().getCookie(baseUrl)\n            if (cookies.isNullOrBlank()) return null\n\n            conn = (URL(urlString).openConnection() as HttpURLConnection).apply {\n                requestMethod = "GET"\n                instanceFollowRedirects = false\n                setRequestProperty("Cookie", cookies)\n                setRequestProperty("Accept", "text/html, */*; q=0.01")\n                setRequestProperty("X-Requested-With", "XMLHttpRequest")\n                setRequestProperty("Referer", resolveAbsoluteUrl(baseUrl, refererPath))\n                setRequestProperty("User-Agent", MOBILE_UA)\n                connectTimeout = 15_000\n                readTimeout = 15_000\n            }\n\n            val code = conn.responseCode\n            val location = conn.getHeaderField("Location").orEmpty()\n            val stream = if (code in 200..299) conn.inputStream else conn.errorStream\n            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()\n            SimpleHttpResponse(statusCode = code, body = text, location = location)\n        } catch (_: Exception) {\n            null\n        } finally {\n            conn?.disconnect()\n        }\n    }\n\n    private fun isSessionExpiredResponse(resp: SimpleHttpResponse?): Boolean {\n        if (resp == null) return false\n        if (resp.statusCode == 401 || resp.statusCode == 403) return true\n        if (resp.statusCode in 300..399 && resp.location.contains("/Login", ignoreCase = true)) return true\n        if (resp.body.contains("id=\\"LoginForm\\"", ignoreCase = true)) return true\n        return false\n    }\n\n    // =========================================================================\n    // TYÖAIKALEIMAUS (Vaihe 4)\n    // =========================================================================\n\n    suspend fun fetchStampingState(\n        context: Context,\n        forceRefreshSession: Boolean = false\n    ): StampingPageState? = withContext(Dispatchers.IO) {\n        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n        if (baseUrl.isBlank()) return@withContext null\n        if (BackgroundAuthHelper.isCredentialBlocked(context)) return@withContext null\n\n        if (forceRefreshSession) {\n            if (!BackgroundAuthHelper.ensureAuthenticatedSession(context, forceRefresh = true)) {\n                return@withContext null\n            }\n        }\n\n        val url = "$baseUrl/WorktimeStamping"\n        val html = BackgroundAuthHelper.fetchAuthenticatedPages(context, listOf(url))?.firstOrNull()\n            ?: return@withContext null\n        extractAndSaveMaxSessionTime(context, html)\n        val parsed = parseStampingHtml(html) ?: return@withContext null\n        saveCachedStampingState(context, parsed)\n        parsed\n    }\n\n    suspend fun fetchMoreStamps(\n        context: Context,\n        take: Int,\n        getMoreStampsUrlPath: String = "/WorktimeStamping/GetMoreStamps"\n    ): Pair<List<StampHistoryRow>, Boolean>? = withContext(Dispatchers.IO) {\n        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n        if (baseUrl.isBlank()) return@withContext null\n        val target = resolveAbsoluteUrl(baseUrl, getMoreStampsUrlPath) + "?take=$take"\n\n        var resp = executeAjaxGet(baseUrl, target)\n        if (isSessionExpiredResponse(resp)) {\n            if (BackgroundAuthHelper.ensureAuthenticatedSession(context, forceRefresh = true)) {\n                resp = executeAjaxGet(baseUrl, target)\n            }\n        }\n        if (resp == null || resp.statusCode != 200 || resp.body.isBlank()) return@withContext null\n        parseLatestStampsFragment(resp.body)\n    }\n\n    suspend fun performDirectStamp(\n        context: Context,\n        currentState: StampingPageState?,\n        reasonCodeId: Int? = null,\n        comment: String = "",\n        expectedDirection: String? = null,\n        onStatusUpdate: ((String) -> Unit)? = null\n    ): StampSubmitResult = withContext(Dispatchers.IO) {\n        val en = DemoModeHelper.isEnglish(context)\n        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n        if (baseUrl.isBlank()) {\n            return@withContext StampSubmitResult.Failed(\n                if (en) "Organization not configured" else "Organisaatiotunnus puuttuu"\n            )\n        }\n        if (BackgroundAuthHelper.isCredentialBlocked(context)) {\n            return@withContext StampSubmitResult.Failed(\n                if (en) "Check username and password in Settings" else "Tarkista käyttäjätunnus ja salasana asetuksista"\n            )\n        }\n\n        // Haetaan tuore tila jos sitä ei ole tai token puuttuu tai kyse on automaattileimauksesta\n        var state = currentState\n        if (state == null || state.verificationToken.isBlank() || state.fromCache || expectedDirection != null) {\n            if (!isSessionLikelyValid(context, baseUrl, isAutoStamping = expectedDirection != null)) {\n                onStatusUpdate?.invoke(if (en) "Signing in…" else "Kirjaudutaan sisään…")\n                BackgroundAuthHelper.ensureAuthenticatedSession(context)\n            }\n            onStatusUpdate?.invoke(if (en) "Checking stamp status…" else "Haetaan leimaustilaa…")\n            state = fetchStampingState(context, forceRefreshSession = false)\n                ?: fetchStampingState(context, forceRefreshSession = true)\n        }\n\n        if (state == null) {\n            return@withContext StampSubmitResult.Failed(\n                if (en) "Could not load time stamping" else "Leimaussivun lataus epäonnistui",\n                fallbackToWebView = true\n            )\n        }\n\n        if (state.nextDirection != "IN" && state.nextDirection != "OUT") {\n            return@withContext StampSubmitResult.Failed(\n                if (en) "Could not detect stamp direction" else "Leimaussuuntaa ei tunnistettu",\n                fallbackToWebView = true\n            )\n        }\n\n        if (expectedDirection != null && !state.nextDirection.equals(expectedDirection, ignoreCase = true)) {\n            return@withContext StampSubmitResult.AlreadyInDirection(state.nextDirection)\n        }\n\n        val eventType = state.nextDirection\n        val effectiveReasonCode = reasonCodeId ?: state.defaultReasonCode\n        val validateUrl = resolveAbsoluteUrl(baseUrl, state.validateStampSaveUrl)\n        val saveUrl = resolveAbsoluteUrl(baseUrl, state.saveStampUrl)\n\n        suspend fun attemptValidateAndSave(activeState: StampingPageState): Pair<StampSubmitResult?, Boolean> {\n            val token = activeState.verificationToken\n            if (token.isBlank()) {\n                return StampSubmitResult.Failed(\n                    if (en) "Security token missing" else "Turvatunniste puuttuu",\n                    fallbackToWebView = true\n                ) to false\n            }\n\n            // 1. ValidateStampSave (sama kutsu kuin jsWorktimeStampingissa)\n            val validateBody = formEncode(\n                listOf(\n                    "__RequestVerificationToken" to token,\n                    "eventType" to eventType,\n                    "reasonCodeId" to effectiveReasonCode.toString(),\n                    "forgottenStampTime" to "",\n                    "stampComment" to comment,\n                    "stampId" to "0"\n                )\n            )\n            val valResp = executeAjaxPost(\n                baseUrl = baseUrl,\n                urlString = validateUrl,\n                body = validateBody,\n                accept = "application/json, text/javascript, */*; q=0.01"\n            )\n            if (isSessionExpiredResponse(valResp)) {\n                return null to true\n            }\n            if (valResp == null || valResp.statusCode != 200) {\n                return StampSubmitResult.Failed(\n                    if (en) "Stamp validation failed" else "Leimauksen tarkistus epäonnistui",\n                    fallbackToWebView = true\n                ) to false\n            }\n\n            val trimmedVal = valResp.body.trim()\n            if (trimmedVal.startsWith("{")) {\n                try {\n                    val obj = JSONObject(trimmedVal)\n                    if (obj.has("success") && !obj.optBoolean("success", true)) {\n                        val msg = obj.optString("message", "").trim()\n                            .ifEmpty { if (en) "Stamping is not allowed right now." else "Leimaus ei ole juuri nyt sallittu." }\n                        return StampSubmitResult.ValidationRejected(msg) to false\n                    }\n                } catch (_: Exception) {\n                }\n            }\n\n            // 2. SaveStamp\n            val dirLabel = if (en) {\n                if (eventType == "IN") "In" else "Out"\n            } else {\n                if (eventType == "IN") "Sisään" else "Ulos"\n            }\n            onStatusUpdate?.invoke(if (en) "Sending stamp ($dirLabel)…" else "Lähetetään leimaus ($dirLabel)…")\n\n            val saveBody = formEncode(\n                listOf(\n                    "__RequestVerificationToken" to token,\n                    "eventType" to eventType,\n                    "reasonCodeId" to effectiveReasonCode.toString(),\n                    "stampComment" to comment\n                )\n            )\n            val saveResp = executeAjaxPost(\n                baseUrl = baseUrl,\n                urlString = saveUrl,\n                body = saveBody,\n                accept = "text/html, */*; q=0.01"\n            )\n            if (isSessionExpiredResponse(saveResp)) {\n                return null to true\n            }\n            if (saveResp == null || saveResp.statusCode != 200 || saveResp.body.isBlank()) {\n                return StampSubmitResult.Failed(\n                    if (en) "Could not save stamp" else "Leimauksen tallennus epäonnistui",\n                    fallbackToWebView = true\n                ) to false\n            }\n\n            // Varmistetaan vastaus-HTML:stä että leimaussuunta vaihtui\n            val oppositeDir = if (eventType == "IN") "OUT" else "IN"\n            val controls = parseBottomContainerFragment(saveResp.body)\n            val confirmedByFlip = controls != null && controls.nextDirection.equals(oppositeDir, ignoreCase = true)\n\n            val refreshedMore = fetchMoreStamps(\n                context = context,\n                take = activeState.currentTake.coerceAtLeast(6),\n                getMoreStampsUrlPath = activeState.getMoreStampsUrl\n            )\n            val newRows = refreshedMore?.first ?: activeState.latestStamps\n            val newHasMore = refreshedMore?.second ?: activeState.hasMoreStamps\n            val beforeTopId = activeState.latestStamps.firstOrNull()?.rowId.orEmpty()\n            val afterTopId = newRows.firstOrNull()?.rowId.orEmpty()\n            val confirmedByRow = afterTopId.isNotEmpty() && afterTopId != beforeTopId\n\n            if (confirmedByFlip || confirmedByRow) {\n                val merged = activeState.copy(\n                    nextDirection = controls?.nextDirection ?: oppositeDir,\n                    punchButtonText = controls?.punchButtonText ?: activeState.punchButtonText,\n                    defaultReasonCode = controls?.defaultReasonCode ?: activeState.defaultReasonCode,\n                    reasonCodes = controls?.reasonCodes?.takeIf { it.isNotEmpty() } ?: activeState.reasonCodes,\n                    latestStamps = newRows,\n                    hasMoreStamps = newHasMore,\n                    fromCache = false\n                )\n                saveCachedStampingState(context, merged)\n                try {\n                    CookieManager.getInstance().flush()\n                } catch (_: Exception) {\n                }\n                context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n                    .edit()\n                    .putLong("last_valid_session_ms", System.currentTimeMillis())\n                    .apply()\n                return StampSubmitResult.Success(merged, eventType) to false\n            }\n\n            // Haetaan mahdollinen palvelimen virheilmoitus (GetAlertMessages)\n            val alertMsg = fetchAlertMessageText(baseUrl)\n            if (!alertMsg.isNullOrBlank()) {\n                return StampSubmitResult.ValidationRejected(alertMsg) to false\n            }\n\n            // Viimeinen varmistus koko sivun uudelleenhakuna\n            val verifiedFresh = fetchStampingState(context, forceRefreshSession = false)\n            if (verifiedFresh != null) {\n                val freshTopId = verifiedFresh.latestStamps.firstOrNull()?.rowId.orEmpty()\n                if (verifiedFresh.nextDirection.equals(oppositeDir, ignoreCase = true) ||\n                    (freshTopId.isNotEmpty() && freshTopId != beforeTopId)\n                ) {\n                    return StampSubmitResult.Success(verifiedFresh, eventType) to false\n                }\n            }\n\n            return StampSubmitResult.Failed(\n                if (en) "Could not confirm stamp automatically" else "Leimausta ei voitu vahvistaa automaattisesti",\n                fallbackToWebView = false\n            ) to false\n        }\n\n        val (firstResult, needsReauth) = attemptValidateAndSave(state)\n        if (firstResult != null) return@withContext firstResult\n\n        if (needsReauth) {\n            onStatusUpdate?.invoke(if (en) "Refreshing session…" else "Uusitaan istuntoa…")\n            val freshState = fetchStampingState(context, forceRefreshSession = true)\n            if (freshState != null) {\n                if (expectedDirection != null && !freshState.nextDirection.equals(expectedDirection, ignoreCase = true)) {\n                    return@withContext StampSubmitResult.AlreadyInDirection(freshState.nextDirection)\n                }\n                val (retryResult, _) = attemptValidateAndSave(freshState)\n                if (retryResult != null) return@withContext retryResult\n            }\n        }\n\n        StampSubmitResult.Failed(\n            if (en) "Session expired – please try again" else "Istunto vanhentunut – kokeile uudelleen",\n            fallbackToWebView = true\n        )\n    }\n\n    suspend fun performQuickStamp(\n        context: Context,\n        wantIn: Boolean,\n        onStatusUpdate: ((String) -> Unit)? = null\n    ): StampSubmitResult {\n        val expectedDir = if (wantIn) "IN" else "OUT"\n        return performDirectStamp(\n            context = context,\n            currentState = null,\n            reasonCodeId = null,\n            comment = "",\n            expectedDirection = expectedDir,\n            onStatusUpdate = onStatusUpdate\n        )\n    }\n\n    private fun fetchAlertMessageText(baseUrl: String): String? {\n        val resp = executeAjaxGet(baseUrl, resolveAbsoluteUrl(baseUrl, "/WorktimeStamping/GetAlertMessages"))\n        if (resp == null || resp.statusCode != 200 || resp.body.isBlank()) return null\n        val doc = Jsoup.parseBodyFragment(resp.body)\n        val texts = doc.select(".alert").map { el ->\n            el.select("button.close").remove()\n            el.text().replace(Regex("\\\\s+"), " ").trim()\n        }.filter { it.isNotEmpty() }\n        return if (texts.isEmpty()) null else texts.joinToString("\\n")\n    }\n\n    private data class BottomControlsData(\n        val nextDirection: String,\n        val punchButtonText: String,\n        val defaultReasonCode: Int,\n        val reasonCodes: List<StampReasonCode>\n    )\n\n    private fun parseBottomContainerFragment(htmlFragment: String): BottomControlsData? {\n        val doc = Jsoup.parseBodyFragment(htmlFragment)\n        val btn = doc.selectFirst("#punchButton")\n        val btnText = btn?.text()?.replace(Regex("\\\\s+"), " ")?.trim().orEmpty()\n        var nextDir = doc.selectFirst("[data-next-stamp-direction]")\n            ?.attr("data-next-stamp-direction")\n            ?.trim()\n            ?.uppercase()\n            .orEmpty()\n        if (nextDir != "IN" && nextDir != "OUT") {\n            val lower = btnText.lowercase()\n            nextDir = when {\n                lower.contains("ulos") || Regex("\\\\bout\\\\b").containsMatchIn(lower) -> "OUT"\n                lower.contains("sisään") || Regex("\\\\bin\\\\b").containsMatchIn(lower) -> "IN"\n                else -> ""\n            }\n        }\n        if (nextDir.isEmpty() && btnText.isEmpty()) return null\n\n        val defaultRc = btn?.attr("data-default-reason-code")?.trim()?.toIntOrNull() ?: 0\n        val reasonCodes = mutableListOf<StampReasonCode>()\n        doc.select(".punch-reason-code-selector ul.dropdown-menu li a[data-reason-code-id]").forEach { a ->\n            val rcId = a.attr("data-reason-code-id").trim().toIntOrNull() ?: return@forEach\n            val label = a.text().replace(Regex("\\\\s+"), " ").trim()\n            if (label.isNotEmpty() && reasonCodes.none { it.id == rcId }) {\n                reasonCodes.add(StampReasonCode(rcId, label))\n            }\n        }\n        return BottomControlsData(\n            nextDirection = nextDir,\n            punchButtonText = btnText,\n            defaultReasonCode = defaultRc,\n            reasonCodes = reasonCodes\n        )\n    }\n\n    private fun parseLatestStampsFragment(htmlFragment: String): Pair<List<StampHistoryRow>, Boolean> {\n        val doc = Jsoup.parseBodyFragment(htmlFragment)\n        val rows = mutableListOf<StampHistoryRow>()\n        doc.select("#table-latest-stamps tbody tr, #table-latest-stamps tr").forEach { tr ->\n            val rowId = tr.selectFirst("input[name^=RowID_]")?.attr("value")?.trim()\n                ?: tr.selectFirst("td.punching-rowid-col")?.text()?.trim()\n                ?: ""\n            val dayText = tr.selectFirst("td.punching-day-col")?.text()?.replace(Regex("\\\\s+"), " ")?.trim().orEmpty()\n            val timeText = tr.selectFirst("td.punching-times-col")?.text()?.replace(Regex("\\\\s+"), " ")?.trim().orEmpty()\n            val dirText = tr.selectFirst("td.punching-direction-col")?.text()?.replace(Regex("\\\\s+"), " ")?.trim().orEmpty()\n            val typeText = tr.selectFirst("td.punching-type-col")?.text()?.replace(Regex("\\\\s+"), " ")?.trim().orEmpty()\n\n            if (dayText.isNotEmpty() || timeText.isNotEmpty() || dirText.isNotEmpty()) {\n                val lowerDir = dirText.lowercase()\n                val isIn = lowerDir == "sisään" || lowerDir == "in" || lowerDir.startsWith("sisään")\n                rows.add(\n                    StampHistoryRow(\n                        rowId = rowId,\n                        dayText = dayText,\n                        timeText = timeText,\n                        directionText = dirText,\n                        isIn = isIn,\n                        typeText = typeText\n                    )\n                )\n            }\n        }\n        val hasMore = doc.selectFirst("#showMoreStampsButton") != null\n        return rows to hasMore\n    }\n\n    fun parseStampingHtml(html: String): StampingPageState? {\n        if (html.isBlank()) return null\n        val doc = Jsoup.parse(html)\n        if (doc.selectFirst("#LoginForm") != null) return null\n\n        val controls = parseBottomContainerFragment(\n            doc.selectFirst("#bottomContainer")?.outerHtml() ?: html\n        ) ?: return null\n\n        val shiftTimes = doc.selectFirst(".punching-shift-times")?.text()?.replace(Regex("\\\\s+"), " ")?.trim().orEmpty()\n        val shiftRawName = doc.selectFirst(".punching-shift-name")?.text()?.replace(Regex("\\\\s+"), " ")?.trim().orEmpty()\n        val (workplace, details) = NumeronParser.formatShiftBannerLines(shiftRawName)\n\n        val (stamps, hasMore) = parseLatestStampsFragment(\n            doc.selectFirst("#latestStampsContainer")?.outerHtml() ?: html\n        )\n        val token = doc.selectFirst("input[name=__RequestVerificationToken]")?.attr("value")?.trim().orEmpty()\n        val saveUrl = doc.selectFirst("#SaveStampUrl")?.attr("value")?.trim().orEmpty()\n            .ifEmpty { "/WorktimeStamping/SaveStamp" }\n        val validateUrl = doc.selectFirst("#ValidateStampSaveUrl")?.attr("value")?.trim().orEmpty()\n            .ifEmpty { "/WorktimeStamping/ValidateStampSave" }\n        val moreUrl = doc.selectFirst("#GetMoreStampsUrl")?.attr("value")?.trim().orEmpty()\n            .ifEmpty { "/WorktimeStamping/GetMoreStamps" }\n\n        return StampingPageState(\n            shiftTimes = shiftTimes,\n            shiftWorkplace = workplace,\n            shiftDetails = details,\n            nextDirection = controls.nextDirection,\n            punchButtonText = controls.punchButtonText,\n            defaultReasonCode = controls.defaultReasonCode,\n            reasonCodes = controls.reasonCodes,\n            latestStamps = stamps,\n            hasMoreStamps = hasMore,\n            currentTake = stamps.size.coerceAtLeast(6),\n            verificationToken = token,\n            saveStampUrl = saveUrl,\n            validateStampSaveUrl = validateUrl,\n            getMoreStampsUrl = moreUrl,\n            fromCache = false\n        )\n    }\n\n    private fun stampingCacheFile(context: Context): File = File(context.cacheDir, "vv_stamping_state.json")\n\n    fun saveCachedStampingState(context: Context, state: StampingPageState) {\n        try {\n            val root = JSONObject().apply {\n                put("shiftTimes", state.shiftTimes)\n                put("shiftWorkplace", state.shiftWorkplace)\n                put("shiftDetails", state.shiftDetails)\n                put("nextDirection", state.nextDirection)\n                put("punchButtonText", state.punchButtonText)\n                put("defaultReasonCode", state.defaultReasonCode)\n                put("hasMoreStamps", state.hasMoreStamps)\n                put("currentTake", state.currentTake)\n                put("saveStampUrl", state.saveStampUrl)\n                put("validateStampSaveUrl", state.validateStampSaveUrl)\n                put("getMoreStampsUrl", state.getMoreStampsUrl)\n                put("savedAt", System.currentTimeMillis())\n            }\n            val rcArr = JSONArray()\n            for (rc in state.reasonCodes) {\n                rcArr.put(JSONObject().apply {\n                    put("id", rc.id)\n                    put("label", rc.label)\n                })\n            }\n            root.put("reasonCodes", rcArr)\n\n            val stArr = JSONArray()\n            for (row in state.latestStamps) {\n                stArr.put(JSONObject().apply {\n                    put("rowId", row.rowId)\n                    put("dayText", row.dayText)\n                    put("timeText", row.timeText)\n                    put("directionText", row.directionText)\n                    put("isIn", row.isIn)\n                    put("typeText", row.typeText)\n                })\n            }\n            root.put("latestStamps", stArr)\n            stampingCacheFile(context).writeText(root.toString(), Charsets.UTF_8)\n        } catch (_: Exception) {\n        }\n    }\n\n    fun loadCachedStampingState(context: Context): StampingPageState? {\n        return try {\n            val file = stampingCacheFile(context)\n            if (!file.exists()) return null\n            val root = JSONObject(file.readText(Charsets.UTF_8))\n\n            val reasonCodes = mutableListOf<StampReasonCode>()\n            val rcArr = root.optJSONArray("reasonCodes")\n            if (rcArr != null) {\n                for (i in 0 until rcArr.length()) {\n                    val o = rcArr.optJSONObject(i) ?: continue\n                    reasonCodes.add(StampReasonCode(o.optInt("id", 0), o.optString("label", "")))\n                }\n            }\n\n            val stamps = mutableListOf<StampHistoryRow>()\n            val stArr = root.optJSONArray("latestStamps")\n            if (stArr != null) {\n                for (i in 0 until stArr.length()) {\n                    val o = stArr.optJSONObject(i) ?: continue\n                    stamps.add(\n                        StampHistoryRow(\n                            rowId = o.optString("rowId", ""),\n                            dayText = o.optString("dayText", ""),\n                            timeText = o.optString("timeText", ""),\n                            directionText = o.optString("directionText", ""),\n                            isIn = o.optBoolean("isIn", false),\n                            typeText = o.optString("typeText", "")\n                        )\n                    )\n                }\n            }\n\n            StampingPageState(\n                shiftTimes = root.optString("shiftTimes", ""),\n                shiftWorkplace = root.optString("shiftWorkplace", ""),\n                shiftDetails = root.optString("shiftDetails", ""),\n                nextDirection = root.optString("nextDirection", ""),\n                punchButtonText = root.optString("punchButtonText", ""),\n                defaultReasonCode = root.optInt("defaultReasonCode", 0),\n                reasonCodes = reasonCodes,\n                latestStamps = stamps,\n                hasMoreStamps = root.optBoolean("hasMoreStamps", false),\n                currentTake = root.optInt("currentTake", 6),\n                verificationToken = "",\n                saveStampUrl = root.optString("saveStampUrl", "/WorktimeStamping/SaveStamp"),\n                validateStampSaveUrl = root.optString("validateStampSaveUrl", "/WorktimeStamping/ValidateStampSave"),\n                getMoreStampsUrl = root.optString("getMoreStampsUrl", "/WorktimeStamping/GetMoreStamps"),\n                fromCache = true\n            )\n        } catch (_: Exception) {\n            null\n        }\n    }\n\n    // =========================================================================\n    // KALENTERI JA TOIVEET (Vaiheet 1–3)\n    // =========================================================================\n\n    suspend fun fetchMonthCalendarHtml(context: Context, year: Int, month: Int): String? =\n        withContext(Dispatchers.IO) {\n            val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n            if (baseUrl.isBlank()) return@withContext null\n            val url = "$baseUrl/Calendar/Month?month=$month&year=$year"\n            val html = BackgroundAuthHelper.fetchAuthenticatedPages(context, listOf(url))?.firstOrNull()\n            if (html != null) {\n                extractAndSaveMaxSessionTime(context, html)\n            }\n            html\n        }\n\n    suspend fun fetchRequests(context: Context, filter: String = "active"): RequestsFetchResult =\n        withContext(Dispatchers.IO) {\n            val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n            if (baseUrl.isBlank()) {\n                return@withContext RequestsFetchResult(null, errorMessage = "Organisaatio puuttuu")\n            }\n            if (BackgroundAuthHelper.isCredentialBlocked(context)) {\n                return@withContext RequestsFetchResult(null, errorMessage = "Tarkista tunnukset asetuksista")\n            }\n\n            if (!isSessionLikelyValid(context, baseUrl, isAutoStamping = false)) {\n                BackgroundAuthHelper.ensureAuthenticatedSession(context)\n            }\n\n            var json = executeRequestsPost(baseUrl, filter)\n            if (json == null) {\n                val reauthed = BackgroundAuthHelper.ensureAuthenticatedSession(context, forceRefresh = true)\n                if (reauthed) {\n                    json = executeRequestsPost(baseUrl, filter)\n                }\n            }\n\n            if (json == null) {\n                val cached = loadCachedRequests(context, filter)\n                return@withContext if (cached != null) {\n                    RequestsFetchResult(cached, fromCache = true, errorMessage = "Näytetään välimuisti")\n                } else {\n                    RequestsFetchResult(null, errorMessage = "Toiveiden haku epäonnistui")\n                }\n            }\n\n            val parsed = parseRequestsJson(context, json)\n            if (parsed != null) {\n                saveCachedRequestsJson(context, filter, json)\n                context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n                    .edit()\n                    .putLong("last_valid_session_ms", System.currentTimeMillis())\n                    .apply()\n                RequestsFetchResult(parsed, fromCache = false)\n            } else {\n                RequestsFetchResult(null, errorMessage = "Vastauksen lukeminen epäonnistui")\n            }\n        }\n\n    private fun executeRequestsPost(baseUrl: String, filter: String): String? {\n        val safeFilter = when (filter) {\n            "old", "removed" -> filter\n            else -> "active"\n        }\n        val resp = executeAjaxPost(\n            baseUrl = baseUrl,\n            urlString = "$baseUrl/PersonRequests/Read",\n            body = "sort=&page=1&pageSize=100&group=&filter=&selectedFilter=$safeFilter",\n            accept = "application/json, text/javascript, */*; q=0.01",\n            refererPath = "/PersonRequests/List"\n        ) ?: return null\n        if (resp.statusCode != 200) return null\n        return if (resp.body.trim().startsWith("{")) resp.body else null\n    }\n\n    fun parseRequestsJson(context: Context, jsonStr: String): List<PersonRequestItem>? {\n        return try {\n            val root = JSONObject(jsonStr)\n            val dataArray = root.optJSONArray("data") ?: root.optJSONArray("Data") ?: return emptyList()\n            val en = DemoModeHelper.isEnglish(context)\n            val list = ArrayList<PersonRequestItem>(dataArray.length())\n\n            for (i in 0 until dataArray.length()) {\n                val item = dataArray.optJSONObject(i) ?: continue\n                val id = item.optInt("Id", -1).let { if (it > 0) it else item.optInt("RowId", -1) }\n                if (id <= 0) continue\n\n                val rawStatus = item.optString("Status", "").trim().toIntOrNull()\n                    ?: item.optString("StatusId", "").trim().toIntOrNull()\n                    ?: item.optInt("Status", -1).let { if (it > 0) it else item.optInt("StatusId", -1) }\n                val rawDesc = item.optString("StatusDescription", "").trim()\n                val statusCode = resolveStatusCode(rawStatus, rawDesc)\n                val statusDesc = rawDesc.ifEmpty { fallbackStatusLabel(statusCode, en) }\n\n                val type = item.optString("Type", if (en) "Request" else "Toive").trim()\n                val dateFrom = parseLocalDate(item.optString("DateFrom", ""))\n                val dateTo = parseLocalDate(item.optString("DateTo", ""))\n                val timeFromText = parseTimeSpan(item.optJSONObject("TimeFromTimeSpan"))\n                val timeToText = parseTimeSpan(item.optJSONObject("TimeToTimeSpan"))\n                val info = item.optString("Info", "").let { if (it.equals("null", true)) "" else it.trim() }\n                val belongsToSeries = item.optBoolean("BelongsToSeries", false)\n                val approvedBy = item.optString("ApprovedBy", "").let { if (it.equals("null", true)) "" else it.trim() }\n                val approvedDateMs = parseDotNetDateMs(item.optString("ApprovedDate", ""))\n\n                list.add(\n                    PersonRequestItem(\n                        id = id,\n                        type = type,\n                        dateFrom = dateFrom,\n                        dateTo = dateTo,\n                        timeFromText = timeFromText,\n                        timeToText = timeToText,\n                        info = info,\n                        statusCode = statusCode,\n                        statusDescription = statusDesc,\n                        belongsToSeries = belongsToSeries,\n                        approvedBy = approvedBy,\n                        approvedDateMs = approvedDateMs\n                    )\n                )\n            }\n            list\n        } catch (_: Exception) {\n            null\n        }\n    }\n\n    private fun resolveStatusCode(rawStatus: Int, statusDesc: String): Int {\n        if (rawStatus == 10 || rawStatus == 40 || rawStatus == 50 || rawStatus == 80) return rawStatus\n        val lower = statusDesc.trim().lowercase()\n        if (lower.isEmpty()) return rawStatus\n        return when {\n            lower.contains("odottaa") || lower.contains("pending") || lower.contains("waiting") || lower.contains("väntar") -> 10\n            lower.contains("osittain") || lower.contains("partial") || lower.contains("delvis") -> 40\n            lower.contains("hylätty") || lower.contains("reject") || lower.contains("denied") || lower.contains("avslag") -> 80\n            lower.contains("hyväksytty") || lower.contains("approved") || lower.contains("godkänd") -> 50\n            else -> rawStatus\n        }\n    }\n\n    private fun fallbackStatusLabel(statusId: Int, en: Boolean): String = when (statusId) {\n        10 -> if (en) "Pending" else "Odottaa käsittelyä"\n        40 -> if (en) "Partially approved" else "Osittain hyväksytty"\n        50 -> if (en) "Approved" else "Hyväksytty"\n        80 -> if (en) "Rejected" else "Hylätty"\n        else -> ""\n    }\n\n    private fun parseDotNetDateMs(raw: String): Long? {\n        val match = DOTNET_DATE_REGEX.find(raw.trim()) ?: return null\n        return match.groupValues[1].toLongOrNull()\n    }\n\n    private fun parseLocalDate(raw: String): LocalDate? {\n        val trimmed = raw.trim()\n        if (trimmed.isEmpty() || trimmed.equals("null", ignoreCase = true)) return null\n        val ms = parseDotNetDateMs(trimmed)\n        if (ms != null) {\n            return Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).toLocalDate()\n        }\n        val iso = Regex("^(\\\\d{4}-\\\\d{2}-\\\\d{2})").find(trimmed)?.groupValues?.get(1)\n        if (iso != null) {\n            return try {\n                LocalDate.parse(iso)\n            } catch (_: Exception) {\n                null\n            }\n        }\n        return null\n    }\n\n    private fun parseTimeSpan(obj: JSONObject?): String {\n        if (obj == null) return ""\n        val hours = obj.optInt("Hours", 0)\n        val minutes = obj.optInt("Minutes", 0)\n        if (hours == 0 && minutes == 0) return ""\n        return String.format("%02d:%02d", hours, minutes)\n    }\n\n    private fun requestsCacheFile(context: Context, filter: String): File {\n        val safe = when (filter) {\n            "old", "removed" -> filter\n            else -> "active"\n        }\n        return File(context.cacheDir, "vv_requests_$safe.json")\n    }\n\n    private fun saveCachedRequestsJson(context: Context, filter: String, json: String) {\n        try {\n            requestsCacheFile(context, filter).writeText(json, Charsets.UTF_8)\n        } catch (_: Exception) {\n        }\n    }\n\n    fun loadCachedRequests(context: Context, filter: String): List<PersonRequestItem>? {\n        return try {\n            val file = requestsCacheFile(context, filter)\n            if (!file.exists()) return null\n            parseRequestsJson(context, file.readText(Charsets.UTF_8))\n        } catch (_: Exception) {\n            null\n        }\n    }\n\n    private fun monthCacheFile(context: Context, year: Int, month: Int): File {\n        return File(context.cacheDir, "vv_month_${year}_${month}.json")\n    }\n\n    fun saveMonthDisplayCache(context: Context, data: MonthDisplayData) {\n        try {\n            val root = JSONObject().apply {\n                put("year", data.year)\n                put("month", data.month)\n                put("savedAt", System.currentTimeMillis())\n            }\n            val daysArr = JSONArray()\n            for ((date, day) in data.days) {\n                val dObj = JSONObject().apply {\n                    put("date", date.toString())\n                    put("hasCommentCircle", day.hasCommentCircle)\n                }\n                val shiftsArr = JSONArray()\n                for (s in day.shifts) {\n                    shiftsArr.put(\n                        JSONObject().apply {\n                            put("startText", s.startText)\n                            put("endText", s.endText)\n                            put("startMinutes", s.startMinutes)\n                            put("endMinutes", s.endMinutes)\n                            put("location", s.location)\n                            put("shiftName", s.shiftName)\n                            put("role", s.role)\n                            put("rawTitle", s.rawTitle)\n                        }\n                    )\n                }\n                dObj.put("shifts", shiftsArr)\n\n                val absArr = JSONArray()\n                for (a in day.absences) {\n                    absArr.put(\n                        JSONObject().apply {\n                            put("title", a.title)\n                            put("kind", a.kind)\n                            put("spanDays", a.spanDays)\n                        }\n                    )\n                }\n                dObj.put("absences", absArr)\n\n                val reqArr = JSONArray()\n                for (r in day.requests) {\n                    reqArr.put(r.title)\n                }\n                dObj.put("requests", reqArr)\n\n                daysArr.put(dObj)\n            }\n            root.put("days", daysArr)\n            monthCacheFile(context, data.year, data.month).writeText(root.toString(), Charsets.UTF_8)\n        } catch (_: Exception) {\n        }\n    }\n\n    fun loadMonthDisplayCache(context: Context, year: Int, month: Int): MonthDisplayData? {\n        return try {\n            val file = monthCacheFile(context, year, month)\n            if (!file.exists()) return null\n            val root = JSONObject(file.readText(Charsets.UTF_8))\n            val daysArr = root.optJSONArray("days") ?: return null\n            val map = mutableMapOf<LocalDate, CalendarDisplayDay>()\n\n            for (i in 0 until daysArr.length()) {\n                val dObj = daysArr.optJSONObject(i) ?: continue\n                val date = try {\n                    LocalDate.parse(dObj.optString("date", ""))\n                } catch (_: Exception) {\n                    continue\n                }\n                val hasCircle = dObj.optBoolean("hasCommentCircle", false)\n\n                val shifts = mutableListOf<CalendarDisplayShift>()\n                val sArr = dObj.optJSONArray("shifts")\n                if (sArr != null) {\n                    for (j in 0 until sArr.length()) {\n                        val s = sArr.optJSONObject(j) ?: continue\n                        shifts.add(\n                            CalendarDisplayShift(\n                                startText = s.optString("startText", ""),\n                                endText = s.optString("endText", ""),\n                                startMinutes = s.optInt("startMinutes", 0),\n                                endMinutes = s.optInt("endMinutes", 0),\n                                location = s.optString("location", ""),\n                                shiftName = s.optString("shiftName", ""),\n                                role = s.optString("role", ""),\n                                rawTitle = s.optString("rawTitle", "")\n                            )\n                        )\n                    }\n                }\n\n                val absences = mutableListOf<CalendarDisplayAbsence>()\n                val aArr = dObj.optJSONArray("absences")\n                if (aArr != null) {\n                    for (j in 0 until aArr.length()) {\n                        val a = aArr.optJSONObject(j) ?: continue\n                        absences.add(\n                            CalendarDisplayAbsence(\n                                title = a.optString("title", ""),\n                                kind = a.optString("kind", "other"),\n                                spanDays = a.optInt("spanDays", 1)\n                            )\n                        )\n                    }\n                }\n\n                val requests = mutableListOf<CalendarDisplayRequest>()\n                val rArr = dObj.optJSONArray("requests")\n                if (rArr != null) {\n                    for (j in 0 until rArr.length()) {\n                        val t = rArr.optString(j, "")\n                        if (t.isNotEmpty()) requests.add(CalendarDisplayRequest(t))\n                    }\n                }\n\n                map[date] = CalendarDisplayDay(\n                    date = date,\n                    shifts = shifts,\n                    absences = absences,\n                    requests = requests,\n                    hasCommentCircle = hasCircle\n                )\n            }\n            MonthDisplayData(year = year, month = month, days = map)\n        } catch (_: Exception) {\n            null\n        }\n    }\n\n    fun buildMonthDisplayFromCachedShifts(\n        shifts: List<WorkShift>,\n        year: Int,\n        month: Int\n    ): MonthDisplayData? {\n        val targetYm = java.time.YearMonth.of(year, month)\n        val firstDay = targetYm.atDay(1)\n        val lastDay = targetYm.atEndOfMonth()\n\n        val shiftsByDate = mutableMapOf<LocalDate, MutableList<CalendarDisplayShift>>()\n        val absencesByDate = mutableMapOf<LocalDate, MutableList<CalendarDisplayAbsence>>()\n        var matchedAny = false\n\n        for (shift in shifts) {\n            if (shift.isAllDayLeave) {\n                var d = shift.start.toLocalDate()\n                val endExcl = shift.end.toLocalDate()\n                val kind = when {\n                    shift.title.contains("sairaus", true) || shift.title.contains("hoitovapaa", true) -> "sick"\n                    shift.title.contains("loma", true) || shift.title.contains("säästövapaa", true) -> "vacation"\n                    else -> "other"\n                }\n                while (d.isBefore(endExcl)) {\n                    if (!d.isBefore(firstDay) && !d.isAfter(lastDay)) {\n                        matchedAny = true\n                        val list = absencesByDate.getOrPut(d) { mutableListOf() }\n                        if (list.none { it.title.equals(shift.title, true) }) {\n                            list.add(CalendarDisplayAbsence(shift.title, kind, 1))\n                        }\n                    }\n                    d = d.plusDays(1)\n                }\n            } else {\n                val d = shift.start.toLocalDate()\n                if (!d.isBefore(firstDay) && !d.isAfter(lastDay)) {\n                    matchedAny = true\n                    val startText = String.format("%d:%02d", shift.start.hour, shift.start.minute)\n                    val endText = String.format("%d:%02d", shift.end.hour, shift.end.minute)\n                    val startMin = shift.start.hour * 60 + shift.start.minute\n                    val endMin = shift.end.hour * 60 + shift.end.minute\n                    val list = shiftsByDate.getOrPut(d) { mutableListOf() }\n                    list.add(\n                        CalendarDisplayShift(\n                            startText = startText,\n                            endText = endText,\n                            startMinutes = startMin,\n                            endMinutes = endMin,\n                            location = shift.location,\n                            shiftName = shift.title.takeUnless { it.equals("Työvuoro", true) }.orEmpty(),\n                            role = shift.description.lineSequence().firstOrNull().orEmpty(),\n                            rawTitle = shift.title\n                        )\n                    )\n                }\n            }\n        }\n\n        if (!matchedAny) return null\n        val allDates = (shiftsByDate.keys + absencesByDate.keys)\n        val dayMap = mutableMapOf<LocalDate, CalendarDisplayDay>()\n        for (d in allDates) {\n            dayMap[d] = CalendarDisplayDay(\n                date = d,\n                shifts = shiftsByDate[d].orEmpty(),\n                absences = absencesByDate[d].orEmpty(),\n                requests = emptyList(),\n                hasCommentCircle = false\n            )\n        }\n        return MonthDisplayData(year = year, month = month, days = dayMap)\n    }\n}\n'

NATIVE_STAMP_VIEW_KT = 'package fi.numeron.vuorovahti\n\nimport android.content.Context\nimport android.graphics.Color\nimport android.graphics.Typeface\nimport android.graphics.drawable.GradientDrawable\nimport android.text.InputFilter\nimport android.util.TypedValue\nimport android.view.Gravity\nimport android.view.View\nimport android.widget.Button\nimport android.widget.EditText\nimport android.widget.FrameLayout\nimport android.widget.LinearLayout\nimport android.widget.ProgressBar\nimport android.widget.ScrollView\nimport android.widget.TextView\nimport android.widget.Toast\nimport androidx.appcompat.app.AlertDialog\nimport kotlinx.coroutines.CoroutineScope\nimport kotlinx.coroutines.Job\nimport kotlinx.coroutines.launch\nimport java.time.LocalDate\nimport java.time.LocalTime\nimport java.time.format.DateTimeFormatter\n\nclass NativeStampView(\n    private val context: Context,\n    private val scope: CoroutineScope,\n    private val onOpenForgottenStampWeb: () -> Unit,\n    private val onOpenEditStampWeb: (rowId: String) -> Unit,\n    private val onOpenSettings: () -> Unit\n) : LinearLayout(context) {\n\n    private var currentState: StampingPageState? = null\n    private var selectedReasonCodeId: Int = 0\n    private var isSubmitting: Boolean = false\n    private var loadJob: Job? = null\n\n    private val txtTodayCaption: TextView\n    private val btnRefresh: Button\n    private val progressBar: ProgressBar\n    private val txtStatus: TextView\n    private val txtShiftTimes: TextView\n    private val txtShiftWorkplace: TextView\n    private val txtShiftDetails: TextView\n\n    private val txtStampCaption: TextView\n    private val txtReasonLabel: TextView\n    private val btnReasonSelector: Button\n    private val txtCommentLabel: TextView\n    private val editComment: EditText\n    private val btnPunch: Button\n    private val btnForgotten: Button\n\n    private val txtLatestCaption: TextView\n    private val stampsListContainer: LinearLayout\n    private val btnShowMore: Button\n\n    init {\n        orientation = VERTICAL\n        setBackgroundColor(Color.parseColor("#0F1722"))\n\n        val scroll = ScrollView(context).apply {\n            isFillViewport = true\n        }\n        val content = LinearLayout(context).apply {\n            orientation = VERTICAL\n            setPadding(dp(12), dp(12), dp(12), dp(12))\n        }\n\n        // === KORTTI 1: TÄNÄÄN ===\n        val todayCard = LinearLayout(context).apply {\n            orientation = VERTICAL\n            background = roundedBg("#182332", "#2A394A", 12f)\n            setPadding(dp(14), dp(12), dp(14), dp(14))\n        }\n\n        val todayTopRow = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n            gravity = Gravity.CENTER_VERTICAL\n        }\n\n        txtTodayCaption = TextView(context).apply {\n            setTextColor(Color.parseColor("#94A3B8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)\n            setTypeface(null, Typeface.BOLD)\n            letterSpacing = 0.06f\n        }\n        todayTopRow.addView(txtTodayCaption, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))\n\n        progressBar = ProgressBar(context, null, android.R.attr.progressBarStyleSmall).apply {\n            isIndeterminate = true\n            visibility = View.GONE\n        }\n        todayTopRow.addView(progressBar, LayoutParams(dp(18), dp(18)))\n\n        txtStatus = TextView(context).apply {\n            setTextColor(Color.parseColor("#94A3B8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)\n            setPadding(dp(6), 0, dp(8), 0)\n        }\n        todayTopRow.addView(txtStatus, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))\n\n        btnRefresh = Button(context).apply {\n            text = "↻"\n            setTextColor(Color.parseColor("#38BDF8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)\n            background = roundedBg("#233040", "#37475A", 8f)\n            setPadding(0, 0, 0, 0)\n            minHeight = 0\n            minimumHeight = dp(32)\n            setOnClickListener { loadState(forceNetwork = true) }\n        }\n        todayTopRow.addView(btnRefresh, LayoutParams(dp(36), dp(32)))\n\n        todayCard.addView(todayTopRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        txtShiftTimes = TextView(context).apply {\n            setTextColor(Color.WHITE)\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 24f)\n            setTypeface(null, Typeface.BOLD)\n            setPadding(0, dp(6), 0, dp(2))\n        }\n        todayCard.addView(txtShiftTimes, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        txtShiftWorkplace = TextView(context).apply {\n            setTextColor(Color.parseColor("#38BDF8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)\n            setTypeface(null, Typeface.BOLD)\n            setPadding(0, dp(2), 0, 0)\n        }\n        todayCard.addView(txtShiftWorkplace, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        txtShiftDetails = TextView(context).apply {\n            setTextColor(Color.parseColor("#CBD5E1"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)\n            setPadding(0, dp(2), 0, 0)\n        }\n        todayCard.addView(txtShiftDetails, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        content.addView(\n            todayCard,\n            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                bottomMargin = dp(12)\n            }\n        )\n\n        // === KORTTI 2: LEIMAUS ===\n        val stampCard = LinearLayout(context).apply {\n            orientation = VERTICAL\n            background = roundedBg("#182332", "#2A394A", 12f)\n            setPadding(dp(14), dp(12), dp(14), dp(12))\n        }\n\n        txtStampCaption = TextView(context).apply {\n            setTextColor(Color.parseColor("#94A3B8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)\n            setTypeface(null, Typeface.BOLD)\n            letterSpacing = 0.06f\n            setPadding(0, 0, 0, dp(8))\n        }\n        stampCard.addView(txtStampCaption, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        txtReasonLabel = TextView(context).apply {\n            setTextColor(Color.parseColor("#CBD5E1"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n            setPadding(0, 0, 0, dp(4))\n        }\n        stampCard.addView(txtReasonLabel, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        btnReasonSelector = Button(context).apply {\n            isAllCaps = false\n            gravity = Gravity.START or Gravity.CENTER_VERTICAL\n            setTextColor(Color.parseColor("#F1F5F9"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)\n            background = roundedBg("#111923", "#37475A", 8f)\n            setPadding(dp(12), dp(10), dp(12), dp(10))\n            setOnClickListener { showReasonCodeDialog() }\n        }\n        stampCard.addView(\n            btnReasonSelector,\n            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                bottomMargin = dp(10)\n            }\n        )\n\n        txtCommentLabel = TextView(context).apply {\n            setTextColor(Color.parseColor("#CBD5E1"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n            setPadding(0, 0, 0, dp(4))\n        }\n        stampCard.addView(txtCommentLabel, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        editComment = EditText(context).apply {\n            setTextColor(Color.WHITE)\n            setHintTextColor(Color.parseColor("#64748B"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)\n            background = roundedBg("#111923", "#37475A", 8f)\n            setPadding(dp(12), dp(10), dp(12), dp(10))\n            isSingleLine = true\n            filters = arrayOf(InputFilter.LengthFilter(255))\n        }\n        stampCard.addView(\n            editComment,\n            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                bottomMargin = dp(14)\n            }\n        )\n\n        btnPunch = Button(context).apply {\n            isAllCaps = false\n            setTextColor(Color.WHITE)\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)\n            setTypeface(null, Typeface.BOLD)\n            background = roundedBg("#15803D", "#22C55E", 10f)\n            setPadding(dp(12), dp(14), dp(12), dp(14))\n            setOnClickListener { handlePunchClick() }\n        }\n        stampCard.addView(btnPunch, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        btnForgotten = Button(context).apply {\n            isAllCaps = false\n            setTextColor(Color.parseColor("#38BDF8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)\n            setTypeface(null, Typeface.BOLD)\n            setBackgroundColor(Color.TRANSPARENT)\n            gravity = Gravity.START or Gravity.CENTER_VERTICAL\n            setPadding(0, dp(10), dp(8), dp(2))\n            minHeight = 0\n            minimumHeight = dp(36)\n            setOnClickListener {\n                val en = DemoModeHelper.isEnglish(context)\n                if (DemoModeHelper.isDemoEnabled(context)) {\n                    Toast.makeText(\n                        context,\n                        if (en) "Demo mode: Missing stamp form is disabled" else "Demotila: Puuttuvan leimauksen lisäys ei ole käytössä demossa",\n                        Toast.LENGTH_SHORT\n                    ).show()\n                } else {\n                    onOpenForgottenStampWeb()\n                }\n            }\n        }\n        stampCard.addView(btnForgotten, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))\n\n        content.addView(\n            stampCard,\n            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                bottomMargin = dp(12)\n            }\n        )\n\n        // === KORTTI 3: VIIMEISIMMÄT LEIMAUKSET ===\n        val historyCard = LinearLayout(context).apply {\n            orientation = VERTICAL\n            background = roundedBg("#182332", "#2A394A", 12f)\n            setPadding(dp(14), dp(12), dp(14), dp(10))\n        }\n\n        txtLatestCaption = TextView(context).apply {\n            setTextColor(Color.parseColor("#94A3B8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)\n            setTypeface(null, Typeface.BOLD)\n            letterSpacing = 0.06f\n            setPadding(0, 0, 0, dp(8))\n        }\n        historyCard.addView(txtLatestCaption, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        stampsListContainer = LinearLayout(context).apply {\n            orientation = VERTICAL\n        }\n        historyCard.addView(stampsListContainer, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        btnShowMore = Button(context).apply {\n            isAllCaps = false\n            setTextColor(Color.parseColor("#38BDF8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)\n            setTypeface(null, Typeface.BOLD)\n            setBackgroundColor(Color.TRANSPARENT)\n            gravity = Gravity.START or Gravity.CENTER_VERTICAL\n            setPadding(0, dp(8), dp(8), dp(2))\n            minHeight = 0\n            minimumHeight = dp(36)\n            visibility = View.GONE\n            setOnClickListener { loadMoreStamps() }\n        }\n        historyCard.addView(btnShowMore, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))\n\n        content.addView(historyCard, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n        scroll.addView(content, FrameLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n        addView(scroll, LayoutParams(LayoutParams.MATCH_PARENT, 0, 1f))\n    }\n\n    fun onShow(forceNetwork: Boolean = false) {\n        updateLocalizedLabels()\n        loadState(forceNetwork = forceNetwork)\n    }\n\n    fun refreshFromNetwork() {\n        updateLocalizedLabels()\n        loadState(forceNetwork = true)\n    }\n\n    fun performAutoStamp(wantIn: Boolean, onFinished: () -> Unit) {\n        updateLocalizedLabels()\n        val en = DemoModeHelper.isEnglish(context)\n        if (DemoModeHelper.isDemoEnabled(context)) {\n            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n            val currentlyIn = prefs.getBoolean("demo_stamped_in", false)\n            val dirLabel = if (en) (if (wantIn) "In" else "Out") else (if (wantIn) "Sisään" else "Ulos")\n            if (wantIn != currentlyIn) {\n                recordDemoStamp(wantIn)\n                Toast.makeText(\n                    context,\n                    if (en) "Demo mode: Clocked $dirLabel" else "Demotila: Leimattu ($dirLabel)",\n                    Toast.LENGTH_SHORT\n                ).show()\n            } else {\n                Toast.makeText(\n                    context,\n                    if (en) "Demo mode: Already clocked $dirLabel" else "Demotila: Olet jo leimannut tilaan $dirLabel",\n                    Toast.LENGTH_SHORT\n                ).show()\n            }\n            loadState(forceNetwork = false)\n            postDelayed(onFinished, 1200L)\n            return\n        }\n\n        val expectedDir = if (wantIn) "IN" else "OUT"\n        val dirLabel = if (en) (if (wantIn) "In" else "Out") else (if (wantIn) "Sisään" else "Ulos")\n        setControlsBusy(true, if (en) "Stamping ($dirLabel)…" else "Leimataan ($dirLabel)…")\n\n        scope.launch {\n            val res = NumeronApiClient.performDirectStamp(\n                context = context,\n                currentState = null,\n                reasonCodeId = null,\n                comment = "",\n                expectedDirection = expectedDir,\n                onStatusUpdate = { msg -> post { txtStatus.text = msg } }\n            )\n            setControlsBusy(false, "")\n            when (res) {\n                is StampSubmitResult.Success -> {\n                    res.updatedState?.let {\n                        currentState = it\n                        selectedReasonCodeId = it.defaultReasonCode\n                        renderState(it)\n                    }\n                    Toast.makeText(\n                        context,\n                        if (en) "Stamp confirmed ($dirLabel)" else "Leimaus vahvistettu ($dirLabel)",\n                        Toast.LENGTH_SHORT\n                    ).show()\n                    postDelayed(onFinished, 1200L)\n                }\n                is StampSubmitResult.AlreadyInDirection -> {\n                    Toast.makeText(\n                        context,\n                        if (en) "Already clocked $dirLabel" else "Olet jo leimannut tilaan: $dirLabel",\n                        Toast.LENGTH_LONG\n                    ).show()\n                    loadState(forceNetwork = true)\n                    postDelayed(onFinished, 1400L)\n                }\n                is StampSubmitResult.ValidationRejected -> {\n                    Toast.makeText(context, res.message, Toast.LENGTH_LONG).show()\n                    loadState(forceNetwork = true)\n                }\n                is StampSubmitResult.Failed -> {\n                    Toast.makeText(context, res.message, Toast.LENGTH_LONG).show()\n                    loadState(forceNetwork = true)\n                }\n            }\n        }\n    }\n\n    private fun updateLocalizedLabels() {\n        val en = DemoModeHelper.isEnglish(context)\n        txtTodayCaption.text = if (en) "TODAY" else "TÄNÄÄN"\n        txtStampCaption.text = if (en) "TIME STAMPING" else "LEIMAUS"\n        txtReasonLabel.text = if (en) "Reason code" else "Syykoodi"\n        txtCommentLabel.text = if (en) "Comment" else "Lisätiedot"\n        editComment.hint = if (en) "Write a note if needed" else "Kirjoita selite tarvittaessa"\n        btnForgotten.text = if (en) "+ Add missing stamp" else "+ Lisää puuttuva leimaus"\n        txtLatestCaption.text = if (en) "LATEST STAMPS" else "VIIMEISIMMÄT LEIMAUKSET"\n        btnShowMore.text = if (en) "Show more" else "Näytä lisää"\n    }\n\n    private fun loadState(forceNetwork: Boolean) {\n        val en = DemoModeHelper.isEnglish(context)\n        loadJob?.cancel()\n\n        if (DemoModeHelper.isDemoEnabled(context)) {\n            progressBar.visibility = View.GONE\n            txtStatus.text = "Demo"\n            val demoState = buildDemoState()\n            currentState = demoState\n            selectedReasonCodeId = demoState.defaultReasonCode\n            renderState(demoState)\n            return\n        }\n\n        // 1. Näytetään heti paikallinen välimuisti (0 ms viive)\n        val cached = NumeronApiClient.loadCachedStampingState(context)\n        if (cached != null) {\n            if (currentState == null) {\n                currentState = cached\n                selectedReasonCodeId = cached.defaultReasonCode\n            }\n            renderState(currentState ?: cached)\n        }\n\n        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n        if (baseUrl.isBlank()) {\n            progressBar.visibility = View.GONE\n            txtStatus.text = ""\n            txtShiftTimes.text = if (en) "Welcome" else "Tervetuloa"\n            txtShiftWorkplace.text = if (en) "Set organization ID in Settings" else "Aseta organisaatiotunnus asetuksista"\n            txtShiftDetails.visibility = View.GONE\n            btnPunch.isEnabled = false\n            btnPunch.text = if (en) "Open Settings" else "Avaa asetukset"\n            btnPunch.setOnClickListener { onOpenSettings() }\n            return\n        }\n\n        btnPunch.setOnClickListener { handlePunchClick() }\n\n        if (BackgroundAuthHelper.isCredentialBlocked(context)) {\n            progressBar.visibility = View.GONE\n            txtStatus.text = if (en) "Check login" else "Tarkista tunnukset"\n            Toast.makeText(\n                context,\n                if (en) "Login failed – please check username and password in Settings"\n                else "Kirjautuminen epäonnistui – tarkista käyttäjätunnus ja salasana asetuksista",\n                Toast.LENGTH_LONG\n            ).show()\n            return\n        }\n\n        progressBar.visibility = View.VISIBLE\n        txtStatus.text = if (cached != null && !forceNetwork) {\n            if (en) "Updating…" else "Päivitetään…"\n        } else {\n            if (en) "Loading…" else "Ladataan…"\n        }\n\n        loadJob = scope.launch {\n            val fresh = NumeronApiClient.fetchStampingState(context, forceRefreshSession = false)\n            progressBar.visibility = View.GONE\n            if (fresh != null) {\n                currentState = fresh\n                selectedReasonCodeId = fresh.defaultReasonCode\n                txtStatus.text = ""\n                renderState(fresh)\n            } else {\n                txtStatus.text = if (cached != null) {\n                    if (en) "Offline cache" else "Välimuisti"\n                } else {\n                    if (en) "Load failed" else "Lataus epäonnistui"\n                }\n            }\n        }\n    }\n\n    private fun renderState(state: StampingPageState) {\n        val en = DemoModeHelper.isEnglish(context)\n\n        if (state.shiftTimes.isNotEmpty()) {\n            txtShiftTimes.visibility = View.VISIBLE\n            txtShiftTimes.text = state.shiftTimes\n        } else {\n            txtShiftTimes.visibility = View.GONE\n        }\n\n        if (state.shiftWorkplace.isNotEmpty()) {\n            txtShiftWorkplace.visibility = View.VISIBLE\n            txtShiftWorkplace.text = state.shiftWorkplace\n        } else if (state.shiftTimes.isEmpty()) {\n            txtShiftWorkplace.visibility = View.VISIBLE\n            txtShiftWorkplace.text = if (en) "No scheduled shift today" else "Ei suunniteltua työvuoroa tänään"\n        } else {\n            txtShiftWorkplace.visibility = View.GONE\n        }\n\n        if (state.shiftDetails.isNotEmpty()) {\n            txtShiftDetails.visibility = View.VISIBLE\n            txtShiftDetails.text = state.shiftDetails\n        } else {\n            txtShiftDetails.visibility = View.GONE\n        }\n\n        val activeRc = state.reasonCodes.firstOrNull { it.id == selectedReasonCodeId }\n            ?: state.reasonCodes.firstOrNull()\n        val rcLabel = activeRc?.label ?: (if (en) "Normal working time" else "Normaali työaika")\n        btnReasonSelector.text = "$rcLabel  ▾"\n\n        val isOutNext = state.nextDirection.equals("OUT", ignoreCase = true)\n        btnPunch.isEnabled = !isSubmitting && (state.nextDirection == "IN" || state.nextDirection == "OUT")\n        btnPunch.text = state.punchButtonText.ifEmpty {\n            if (en) {\n                if (isOutNext) "Clock Out" else "Clock In"\n            } else {\n                if (isOutNext) "Leimaa Ulos" else "Leimaa Sisään"\n            }\n        }\n        btnPunch.background = if (isOutNext) {\n            roundedBg("#B91C1C", "#F87171", 10f)\n        } else {\n            roundedBg("#15803D", "#22C55E", 10f)\n        }\n\n        renderStampsTable(state.latestStamps)\n        btnShowMore.visibility = if (state.hasMoreStamps) View.VISIBLE else View.GONE\n    }\n\n    private fun renderStampsTable(rows: List<StampHistoryRow>) {\n        stampsListContainer.removeAllViews()\n        val en = DemoModeHelper.isEnglish(context)\n        val isDemo = DemoModeHelper.isDemoEnabled(context)\n\n        if (rows.isEmpty()) {\n            stampsListContainer.addView(\n                TextView(context).apply {\n                    text = if (en) "No recent stamps" else "Ei viimeisimpiä leimauksia"\n                    setTextColor(Color.parseColor("#94A3B8"))\n                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)\n                    setPadding(0, dp(6), 0, dp(6))\n                }\n            )\n            return\n        }\n\n        for (i in rows.indices) {\n            val row = rows[i]\n            if (i > 0) {\n                val divider = View(context).apply {\n                    setBackgroundColor(Color.parseColor("#2A394A"))\n                }\n                stampsListContainer.addView(divider, LayoutParams(LayoutParams.MATCH_PARENT, 1))\n            }\n\n            val rowView = LinearLayout(context).apply {\n                orientation = HORIZONTAL\n                gravity = Gravity.CENTER_VERTICAL\n                setPadding(dp(4), dp(10), dp(4), dp(10))\n                if (!isDemo && row.rowId.isNotEmpty()) {\n                    setOnClickListener { onOpenEditStampWeb(row.rowId) }\n                }\n            }\n\n            val dayTv = TextView(context).apply {\n                text = row.dayText\n                setTextColor(Color.parseColor("#E2E8F0"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)\n            }\n            rowView.addView(dayTv, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1.2f))\n\n            val timeTv = TextView(context).apply {\n                text = row.timeText\n                setTextColor(Color.WHITE)\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14.5f)\n                setTypeface(null, Typeface.BOLD)\n            }\n            rowView.addView(timeTv, LayoutParams(0, LayoutParams.WRAP_CONTENT, 0.8f))\n\n            val badgeBg = if (row.isIn) "#122B22" else "#3F1D24"\n            val badgeBorder = if (row.isIn) "#22C55E" else "#F87171"\n            val badgeFg = if (row.isIn) "#4ADE80" else "#F87171"\n            val dirBadge = TextView(context).apply {\n                text = row.directionText\n                setTextColor(Color.parseColor(badgeFg))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)\n                setTypeface(null, Typeface.BOLD)\n                background = roundedBg(badgeBg, badgeBorder, 99f)\n                setPadding(dp(10), dp(3), dp(10), dp(3))\n            }\n            rowView.addView(dirBadge, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))\n\n            if (!isDemo && row.rowId.isNotEmpty()) {\n                val arrow = TextView(context).apply {\n                    text = "›"\n                    setTextColor(Color.parseColor("#64748B"))\n                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)\n                    setPadding(dp(10), 0, dp(2), 0)\n                }\n                rowView.addView(arrow, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))\n            }\n\n            stampsListContainer.addView(rowView, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n        }\n    }\n\n    private fun showReasonCodeDialog() {\n        val codes = currentState?.reasonCodes.orEmpty()\n        if (codes.isEmpty()) return\n        val en = DemoModeHelper.isEnglish(context)\n        val labels = codes.map { it.label }.toTypedArray()\n        val checkedIdx = codes.indexOfFirst { it.id == selectedReasonCodeId }.coerceAtLeast(0)\n\n        AlertDialog.Builder(context)\n            .setTitle(if (en) "Select reason code" else "Valitse syykoodi")\n            .setSingleChoiceItems(labels, checkedIdx) { dialog, which ->\n                val chosen = codes[which]\n                selectedReasonCodeId = chosen.id\n                btnReasonSelector.text = "${chosen.label}  ▾"\n                dialog.dismiss()\n            }\n            .setNegativeButton(if (en) "Cancel" else "Peruuta", null)\n            .show()\n    }\n\n    private fun handlePunchClick() {\n        if (isSubmitting) return\n        val en = DemoModeHelper.isEnglish(context)\n\n        if (DemoModeHelper.isDemoEnabled(context)) {\n            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n            val currentlyIn = prefs.getBoolean("demo_stamped_in", false)\n            val wantIn = !currentlyIn\n            recordDemoStamp(wantIn)\n            editComment.setText("")\n            val dirLabel = if (en) (if (wantIn) "In" else "Out") else (if (wantIn) "Sisään" else "Ulos")\n            Toast.makeText(\n                context,\n                if (en) "Demo stamp recorded ($dirLabel)" else "Demoleimaus tallennettu ($dirLabel)",\n                Toast.LENGTH_SHORT\n            ).show()\n            loadState(forceNetwork = false)\n            return\n        }\n\n        val state = currentState\n        val comment = editComment.text?.toString()?.trim().orEmpty()\n        setControlsBusy(true, if (en) "Recording stamp…" else "Lähetetään leimausta…")\n\n        scope.launch {\n            val result = NumeronApiClient.performDirectStamp(\n                context = context,\n                currentState = state,\n                reasonCodeId = selectedReasonCodeId,\n                comment = comment,\n                expectedDirection = null,\n                onStatusUpdate = { msg -> post { txtStatus.text = msg } }\n            )\n            setControlsBusy(false, "")\n\n            when (result) {\n                is StampSubmitResult.Success -> {\n                    editComment.setText("")\n                    val dirLabel = if (en) {\n                        if (result.directionUsed == "IN") "In" else "Out"\n                    } else {\n                        if (result.directionUsed == "IN") "Sisään" else "Ulos"\n                    }\n                    result.updatedState?.let {\n                        currentState = it\n                        selectedReasonCodeId = it.defaultReasonCode\n                        renderState(it)\n                    }\n                    Toast.makeText(\n                        context,\n                        if (en) "Stamp confirmed ($dirLabel)" else "Leimaus vahvistettu ($dirLabel)",\n                        Toast.LENGTH_SHORT\n                    ).show()\n                }\n                is StampSubmitResult.AlreadyInDirection -> {\n                    loadState(forceNetwork = true)\n                }\n                is StampSubmitResult.ValidationRejected -> {\n                    AlertDialog.Builder(context)\n                        .setTitle(if (en) "Stamp not saved" else "Leimausta ei tallennettu")\n                        .setMessage(result.message)\n                        .setPositiveButton("OK", null)\n                        .show()\n                    loadState(forceNetwork = true)\n                }\n                is StampSubmitResult.Failed -> {\n                    Toast.makeText(context, result.message, Toast.LENGTH_LONG).show()\n                    loadState(forceNetwork = true)\n                }\n            }\n        }\n    }\n\n    private fun loadMoreStamps() {\n        val state = currentState ?: return\n        val en = DemoModeHelper.isEnglish(context)\n        val nextTake = state.currentTake + 6\n        btnShowMore.isEnabled = false\n        progressBar.visibility = View.VISIBLE\n        txtStatus.text = if (en) "Loading more…" else "Haetaan lisää…"\n\n        scope.launch {\n            val res = NumeronApiClient.fetchMoreStamps(context, nextTake, state.getMoreStampsUrl)\n            progressBar.visibility = View.GONE\n            btnShowMore.isEnabled = true\n            txtStatus.text = ""\n\n            if (res != null) {\n                val (newRows, hasMore) = res\n                val updated = state.copy(\n                    latestStamps = newRows,\n                    hasMoreStamps = hasMore,\n                    currentTake = newRows.size.coerceAtLeast(nextTake)\n                )\n                currentState = updated\n                NumeronApiClient.saveCachedStampingState(context, updated)\n                renderState(updated)\n            } else {\n                Toast.makeText(\n                    context,\n                    if (en) "Could not load more stamps" else "Lisäleimausten haku epäonnistui",\n                    Toast.LENGTH_SHORT\n                ).show()\n            }\n        }\n    }\n\n    private fun setControlsBusy(busy: Boolean, statusMsg: String) {\n        isSubmitting = busy\n        btnPunch.isEnabled = !busy\n        btnReasonSelector.isEnabled = !busy\n        editComment.isEnabled = !busy\n        progressBar.visibility = if (busy) View.VISIBLE else View.GONE\n        txtStatus.text = statusMsg\n    }\n\n    private fun buildDemoState(): StampingPageState {\n        val en = DemoModeHelper.isEnglish(context)\n        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n        val isIn = prefs.getBoolean("demo_stamped_in", false)\n        val yest = LocalDate.now().minusDays(1).format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))\n        val defaultHist = "$yest | 14:30 | Ulos\\n$yest | 07:00 | Sisään"\n        val rawHist = prefs.getString("demo_stamp_history", defaultHist) ?: defaultHist\n        val todayStr = LocalDate.now().format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))\n\n        val rows = rawHist.lineSequence()\n            .map { it.trim() }\n            .filter { it.isNotEmpty() }\n            .mapNotNull { line ->\n                val parts = line.split("|").map { it.trim() }\n                if (parts.size < 3) return@mapNotNull null\n                val dayDisplay = if (parts[0] == todayStr) (if (en) "Today" else "Tänään") else parts[0]\n                val isRowIn = parts[2].equals("Sisään", true) || parts[2].equals("In", true)\n                val dirLabel = if (en) (if (isRowIn) "In" else "Out") else (if (isRowIn) "Sisään" else "Ulos")\n                StampHistoryRow("", dayDisplay, parts[1], dirLabel, isRowIn, "")\n            }\n            .toList()\n\n        return StampingPageState(\n            shiftTimes = "07:00 - 14:30",\n            shiftWorkplace = if (en) "Demo Ward A" else "Demo-osasto A",\n            shiftDetails = if (en) "Morning shift • Nurse" else "Aamuvuoro • Hoitaja",\n            nextDirection = if (isIn) "OUT" else "IN",\n            punchButtonText = if (en) {\n                if (isIn) "Clock Out" else "Clock In"\n            } else {\n                if (isIn) "Leimaa Ulos" else "Leimaa Sisään"\n            },\n            defaultReasonCode = 0,\n            reasonCodes = listOf(\n                StampReasonCode(0, if (en) "Normal working time" else "Normaali työaika"),\n                StampReasonCode(7, if (en) "Work matter" else "Työasia")\n            ),\n            latestStamps = rows,\n            hasMoreStamps = false,\n            currentTake = rows.size,\n            verificationToken = "",\n            saveStampUrl = "",\n            validateStampSaveUrl = "",\n            getMoreStampsUrl = "",\n            fromCache = false\n        )\n    }\n\n    private fun recordDemoStamp(wantIn: Boolean) {\n        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n        val nowDate = LocalDate.now().format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))\n        val nowTime = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))\n        val yest = LocalDate.now().minusDays(1).format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))\n        val defaultHistory = "$yest | 14:30 | Ulos\\n$yest | 07:00 | Sisään"\n        val oldHistory = prefs.getString("demo_stamp_history", defaultHistory) ?: defaultHistory\n        val dirFi = if (wantIn) "Sisään" else "Ulos"\n        val newHistory = "$nowDate | $nowTime | $dirFi\\n$oldHistory"\n        prefs.edit()\n            .putBoolean("demo_stamped_in", wantIn)\n            .putString("demo_stamp_history", newHistory)\n            .apply()\n    }\n\n    private fun roundedBg(fillHex: String, strokeHex: String, radiusDp: Float): GradientDrawable {\n        return GradientDrawable().apply {\n            shape = GradientDrawable.RECTANGLE\n            cornerRadius = dp(radiusDp.toInt()).toFloat()\n            setColor(Color.parseColor(fillHex))\n            setStroke(dp(1), Color.parseColor(strokeHex))\n        }\n    }\n\n    private fun dp(value: Int): Int {\n        return TypedValue.applyDimension(\n            TypedValue.COMPLEX_UNIT_DIP,\n            value.toFloat(),\n            resources.displayMetrics\n        ).toInt()\n    }\n}\n'

NATIVE_SHIFTS_VIEW_KT = 'package fi.numeron.vuorovahti\n\nimport android.content.Context\nimport android.graphics.Color\nimport android.graphics.Typeface\nimport android.graphics.drawable.GradientDrawable\nimport android.text.TextUtils\nimport android.util.TypedValue\nimport android.view.Gravity\nimport android.view.View\nimport android.webkit.CookieManager\nimport android.widget.Button\nimport android.widget.FrameLayout\nimport android.widget.LinearLayout\nimport android.widget.ProgressBar\nimport android.widget.ScrollView\nimport android.widget.TextView\nimport androidx.appcompat.app.AlertDialog\nimport kotlinx.coroutines.CoroutineScope\nimport kotlinx.coroutines.Dispatchers\nimport kotlinx.coroutines.Job\nimport kotlinx.coroutines.launch\nimport kotlinx.coroutines.withContext\nimport java.net.URLEncoder\nimport java.time.DayOfWeek\nimport java.time.LocalDate\nimport java.time.YearMonth\nimport java.time.format.DateTimeFormatter\nimport java.time.temporal.WeekFields\n\nclass NativeShiftsView(\n    private val context: Context,\n    private val scope: CoroutineScope,\n    private val onOpenWebUrl: (url: String, title: String) -> Unit\n) : LinearLayout(context) {\n\n    private var displayedMonth: YearMonth = YearMonth.now()\n    private var currentData: MonthDisplayData? = null\n    private var loadJob: Job? = null\n\n    private val txtMonthTitle: TextView\n    private val btnPrev: Button\n    private val btnNext: Button\n    private val btnToday: Button\n    private val btnRefresh: Button\n    private val progressBar: ProgressBar\n    private val txtStatus: TextView\n    private val gridContainer: LinearLayout\n\n    private val fiMonths = arrayOf(\n        "Tammikuu", "Helmikuu", "Maaliskuu", "Huhtikuu", "Toukokuu", "Kesäkuu",\n        "Heinäkuu", "Elokuu", "Syyskuu", "Lokakuu", "Marraskuu", "Joulukuu"\n    )\n    private val enMonths = arrayOf(\n        "January", "February", "March", "April", "May", "June",\n        "July", "August", "September", "October", "November", "December"\n    )\n    private val fiShortMonths = arrayOf(\n        "Tammi", "Helmi", "Maalis", "Huhti", "Touko", "Kesä",\n        "Heinä", "Elo", "Syys", "Loka", "Marras", "Joulu"\n    )\n    private val enShortMonths = arrayOf(\n        "Jan", "Feb", "Mar", "Apr", "May", "Jun",\n        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"\n    )\n\n    init {\n        orientation = VERTICAL\n        setBackgroundColor(Color.parseColor("#0F1722"))\n        setPadding(dp(8), dp(8), dp(8), dp(4))\n\n        // Yläkortti: kuukausivalitsin + pikapainikkeet\n        val headerCard = LinearLayout(context).apply {\n            orientation = VERTICAL\n            background = roundedBg("#182332", "#2A394A", 12f)\n            setPadding(dp(10), dp(10), dp(10), dp(8))\n        }\n\n        val navRow = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n            gravity = Gravity.CENTER_VERTICAL\n        }\n\n        btnPrev = Button(context).apply {\n            text = "◀"\n            setTextColor(Color.parseColor("#38BDF8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)\n            background = roundedBg("#233040", "#37475A", 10f)\n            setPadding(0, 0, 0, 0)\n            setOnClickListener {\n                displayedMonth = displayedMonth.minusMonths(1)\n                loadMonth(forceNetwork = true)\n            }\n        }\n        navRow.addView(btnPrev, LayoutParams(dp(44), dp(38)))\n\n        txtMonthTitle = TextView(context).apply {\n            setTextColor(Color.parseColor("#F1F5F9"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)\n            setTypeface(null, Typeface.BOLD)\n            gravity = Gravity.CENTER\n            background = roundedBg("#111923", "#2A394A", 10f)\n            setPadding(dp(12), dp(7), dp(12), dp(7))\n            setOnClickListener { showMonthJumpDialog() }\n        }\n        navRow.addView(\n            txtMonthTitle,\n            LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f).apply {\n                marginStart = dp(10)\n                marginEnd = dp(10)\n            }\n        )\n\n        btnNext = Button(context).apply {\n            text = "▶"\n            setTextColor(Color.parseColor("#38BDF8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)\n            background = roundedBg("#233040", "#37475A", 10f)\n            setPadding(0, 0, 0, 0)\n            setOnClickListener {\n                displayedMonth = displayedMonth.plusMonths(1)\n                loadMonth(forceNetwork = true)\n            }\n        }\n        navRow.addView(btnNext, LayoutParams(dp(44), dp(38)))\n\n        headerCard.addView(navRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        val actionRow = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n            gravity = Gravity.CENTER_VERTICAL\n            setPadding(0, dp(8), 0, 0)\n        }\n\n        btnToday = Button(context).apply {\n            isAllCaps = false\n            setTextColor(Color.parseColor("#E2E8F0"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)\n            background = roundedBg("#233040", "#37475A", 8f)\n            setPadding(dp(12), dp(4), dp(12), dp(4))\n            minHeight = 0\n            minimumHeight = dp(32)\n            setOnClickListener {\n                displayedMonth = YearMonth.now()\n                loadMonth(forceNetwork = true)\n            }\n        }\n        actionRow.addView(btnToday, LayoutParams(LayoutParams.WRAP_CONTENT, dp(32)))\n\n        btnRefresh = Button(context).apply {\n            isAllCaps = false\n            setTextColor(Color.parseColor("#38BDF8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)\n            background = roundedBg("#233040", "#37475A", 8f)\n            setPadding(dp(12), dp(4), dp(12), dp(4))\n            minHeight = 0\n            minimumHeight = dp(32)\n            setOnClickListener { loadMonth(forceNetwork = true) }\n        }\n        actionRow.addView(\n            btnRefresh,\n            LayoutParams(LayoutParams.WRAP_CONTENT, dp(32)).apply {\n                marginStart = dp(8)\n            }\n        )\n\n        val spacer = View(context)\n        actionRow.addView(spacer, LayoutParams(0, 1, 1f))\n\n        progressBar = ProgressBar(context, null, android.R.attr.progressBarStyleSmall).apply {\n            isIndeterminate = true\n            visibility = View.GONE\n        }\n        actionRow.addView(progressBar, LayoutParams(dp(18), dp(18)))\n\n        txtStatus = TextView(context).apply {\n            setTextColor(Color.parseColor("#94A3B8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)\n            setPadding(dp(6), 0, 0, 0)\n        }\n        actionRow.addView(txtStatus, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))\n\n        headerCard.addView(actionRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n        addView(\n            headerCard,\n            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                bottomMargin = dp(8)\n            }\n        )\n\n        val scroll = ScrollView(context).apply {\n            isFillViewport = true\n        }\n        gridContainer = LinearLayout(context).apply {\n            orientation = VERTICAL\n        }\n        scroll.addView(gridContainer, FrameLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n        addView(scroll, LayoutParams(LayoutParams.MATCH_PARENT, 0, 1f))\n    }\n\n    fun onShow(forceNetwork: Boolean = false) {\n        updateLocalizedLabels()\n        loadMonth(forceNetwork = forceNetwork)\n    }\n\n    fun refreshFromCacheAndNetwork() {\n        updateLocalizedLabels()\n        loadMonth(forceNetwork = true)\n    }\n\n    private fun updateLocalizedLabels() {\n        val en = DemoModeHelper.isEnglish(context)\n        val monthName = (if (en) enMonths else fiMonths)[displayedMonth.monthValue - 1]\n        txtMonthTitle.text = "$monthName ${displayedMonth.year} ▾"\n        btnToday.text = if (en) "Today" else "Tänään"\n        btnRefresh.text = if (en) "↻ Refresh" else "↻ Päivitä"\n    }\n\n    private fun loadMonth(forceNetwork: Boolean) {\n        val ym = displayedMonth\n        val en = DemoModeHelper.isEnglish(context)\n        updateLocalizedLabels()\n        loadJob?.cancel()\n\n        if (DemoModeHelper.isDemoEnabled(context)) {\n            progressBar.visibility = View.GONE\n            txtStatus.text = if (en) "Demo" else "Demo"\n            val demoShifts = DemoModeHelper.generateDemoWorkShifts(context)\n            currentData = NumeronApiClient.buildMonthDisplayFromCachedShifts(demoShifts, ym.year, ym.monthValue)\n                ?: MonthDisplayData(ym.year, ym.monthValue, emptyMap())\n            renderCalendarGrid()\n            return\n        }\n\n        // 1. Näytetään heti välimuistista (0 ms viive)\n        val cachedMonth = NumeronApiClient.loadMonthDisplayCache(context, ym.year, ym.monthValue)\n        val fallbackCached = if (cachedMonth == null) {\n            CalendarSyncHelper.loadCachedShifts(context)?.let {\n                NumeronApiClient.buildMonthDisplayFromCachedShifts(it, ym.year, ym.monthValue)\n            }\n        } else {\n            null\n        }\n\n        currentData = cachedMonth ?: fallbackCached ?: MonthDisplayData(ym.year, ym.monthValue, emptyMap())\n        renderCalendarGrid()\n\n        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n        if (baseUrl.isBlank()) {\n            progressBar.visibility = View.GONE\n            txtStatus.text = if (en) "Set organization in Settings" else "Aseta organisaatio asetuksista"\n            return\n        }\n\n        if (!forceNetwork && cachedMonth != null) {\n            // Haetaan silti taustalla tuore data hiljaisesti\n            txtStatus.text = if (en) "Updating..." else "Päivitetään..."\n        } else {\n            txtStatus.text = if (en) "Loading..." else "Ladataan..."\n        }\n        progressBar.visibility = View.VISIBLE\n\n        loadJob = scope.launch {\n            val html = NumeronApiClient.fetchMonthCalendarHtml(context, ym.year, ym.monthValue)\n            if (ym != displayedMonth) return@launch\n\n            progressBar.visibility = View.GONE\n            if (html != null) {\n                val parsed = withContext(Dispatchers.Default) {\n                    NumeronParser.parseMonthForDisplay(html)\n                }\n                if (parsed != null) {\n                    withContext(Dispatchers.IO) {\n                        NumeronApiClient.saveMonthDisplayCache(context, parsed)\n                    }\n                    currentData = parsed\n                    txtStatus.text = ""\n                    renderCalendarGrid()\n                    return@launch\n                }\n            }\n\n            txtStatus.text = if (cachedMonth != null || fallbackCached != null) {\n                if (en) "Offline cache" else "Välimuisti"\n            } else {\n                if (en) "Could not load" else "Lataus epäonnistui"\n            }\n        }\n    }\n\n    private fun renderCalendarGrid() {\n        gridContainer.removeAllViews()\n        val en = DemoModeHelper.isEnglish(context)\n        val ym = displayedMonth\n        val today = LocalDate.now()\n        val dayMap = currentData?.days.orEmpty()\n\n        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n        val morningRgb = prefs.getInt("color_morning_rgb", SettingsDialogHelper.DEFAULT_MORNING_RGB)\n        val eveningRgb = prefs.getInt("color_evening_rgb", SettingsDialogHelper.DEFAULT_EVENING_RGB)\n        val nightRgb = prefs.getInt("color_night_rgb", SettingsDialogHelper.DEFAULT_NIGHT_RGB)\n\n        // Otsikkorivi: Vko + Ma..Su\n        val headerRow = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n        }\n        val dayHeaders = if (en) {\n            arrayOf("Wk", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")\n        } else {\n            arrayOf("Vko", "Ma", "Ti", "Ke", "To", "Pe", "La", "Su")\n        }\n        for (i in dayHeaders.indices) {\n            val tv = TextView(context).apply {\n                text = dayHeaders[i]\n                gravity = Gravity.CENTER\n                setTextColor(Color.parseColor("#CBD5E1"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, if (i == 0) 10f else 11.5f)\n                setTypeface(null, Typeface.BOLD)\n                background = cellBg("#233040", "#2A394A")\n                setPadding(dp(1), dp(6), dp(1), dp(6))\n            }\n            val lp = if (i == 0) LayoutParams(dp(26), LayoutParams.WRAP_CONTENT) else LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f)\n            headerRow.addView(tv, lp)\n        }\n        gridContainer.addView(headerRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        val firstOfMonth = ym.atDay(1)\n        val lastOfMonth = ym.atEndOfMonth()\n        val startMonday = firstOfMonth.with(DayOfWeek.MONDAY)\n        val endSunday = lastOfMonth.with(DayOfWeek.SUNDAY)\n\n        var weekStart = startMonday\n        val weekFields = WeekFields.ISO\n\n        while (!weekStart.isAfter(endSunday)) {\n            val row = LinearLayout(context).apply {\n                orientation = HORIZONTAL\n                minimumHeight = dp(72)\n            }\n\n            // Viikkonumero\n            val weekNum = weekStart.get(weekFields.weekOfWeekBasedYear())\n            val wkTv = TextView(context).apply {\n                text = weekNum.toString()\n                gravity = Gravity.TOP or Gravity.CENTER_HORIZONTAL\n                setTextColor(Color.parseColor("#64748B"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 10f)\n                background = cellBg("#131C28", "#2A394A")\n                setPadding(dp(1), dp(5), dp(1), dp(4))\n            }\n            row.addView(wkTv, LayoutParams(dp(26), LayoutParams.MATCH_PARENT))\n\n            for (offset in 0..6) {\n                val date = weekStart.plusDays(offset.toLong())\n                val isCurrentMonth = (date.monthValue == ym.monthValue && date.year == ym.year)\n                val isToday = (date == today)\n                val isPast = date.isBefore(today)\n                val dayData = dayMap[date]\n\n                val cellBgColor = when {\n                    isToday -> "#1E3A5F"\n                    !isCurrentMonth || isPast -> "#121A24"\n                    else -> "#182332"\n                }\n                val cellBorderColor = if (isToday) "#38BDF8" else "#2A394A"\n\n                val cell = LinearLayout(context).apply {\n                    orientation = VERTICAL\n                    background = cellBg(cellBgColor, cellBorderColor)\n                    setPadding(dp(2), dp(2), dp(2), dp(3))\n                    minimumHeight = dp(72)\n                    if (isCurrentMonth) {\n                        setOnClickListener { showDayDetailsDialog(date, dayData) }\n                    }\n                }\n\n                // Päivänumero + kommenttipallukka\n                val topRow = LinearLayout(context).apply {\n                    orientation = HORIZONTAL\n                    gravity = Gravity.CENTER_VERTICAL\n                }\n                val numTv = TextView(context).apply {\n                    text = date.dayOfMonth.toString()\n                    setTextColor(\n                        if (!isCurrentMonth) Color.parseColor("#64748B")\n                        else if (isToday) Color.parseColor("#38BDF8")\n                        else Color.parseColor("#F1F5F9")\n                    )\n                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)\n                    setTypeface(null, Typeface.BOLD)\n                    setPadding(dp(2), 0, 0, dp(1))\n                }\n                topRow.addView(numTv, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))\n\n                if (dayData?.hasCommentCircle == true) {\n                    val dot = View(context).apply {\n                        background = GradientDrawable().apply {\n                            shape = GradientDrawable.OVAL\n                            setColor(Color.parseColor("#F59E0B"))\n                        }\n                    }\n                    topRow.addView(\n                        dot,\n                        LayoutParams(dp(6), dp(6)).apply {\n                            marginEnd = dp(2)\n                        }\n                    )\n                }\n                cell.addView(topRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n                // Poissaolot (loma, sairaus, koulutus/muu)\n                dayData?.absences?.forEach { abs ->\n                    val (bgHex, fgHex) = when (abs.kind) {\n                        "vacation" -> "#15803D" to "#FFFFFF"\n                        "sick" -> "#B91C1C" to "#FFFFFF"\n                        else -> "#334155" to "#F1F5F9"\n                    }\n                    val badge = TextView(context).apply {\n                        text = abs.title\n                        setTextColor(Color.parseColor(fgHex))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 9.5f)\n                        setTypeface(null, Typeface.BOLD)\n                        maxLines = 1\n                        ellipsize = TextUtils.TruncateAt.END\n                        background = roundedBg(bgHex, bgHex, 4f)\n                        setPadding(dp(3), dp(1), dp(3), dp(1))\n                    }\n                    cell.addView(\n                        badge,\n                        LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                            bottomMargin = dp(2)\n                        }\n                    )\n                }\n\n                // Työvuorot asetusten värikoodeilla\n                dayData?.shifts?.forEach { shift ->\n                    val bgRgb = pickShiftRgb(shift, morningRgb, eveningRgb, nightRgb)\n                    val fgColor = contrastColor(bgRgb)\n                    val label = "${shift.startText}\\n${shift.endText}"\n                    val badge = TextView(context).apply {\n                        text = label\n                        setTextColor(fgColor)\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 10f)\n                        setTypeface(null, Typeface.BOLD)\n                        gravity = Gravity.CENTER\n                        maxLines = 2\n                        background = GradientDrawable().apply {\n                            shape = GradientDrawable.RECTANGLE\n                            cornerRadius = dp(4).toFloat()\n                            setColor(bgRgb)\n                        }\n                        setPadding(dp(2), dp(2), dp(2), dp(2))\n                    }\n                    cell.addView(\n                        badge,\n                        LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                            bottomMargin = dp(2)\n                        }\n                    )\n                }\n\n                // Toiveet\n                dayData?.requests?.forEach { req ->\n                    val badge = TextView(context).apply {\n                        text = req.title\n                        setTextColor(Color.parseColor("#EDE9FE"))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 9.5f)\n                        setTypeface(null, Typeface.BOLD)\n                        maxLines = 1\n                        ellipsize = TextUtils.TruncateAt.END\n                        background = roundedBg("#2E1F47", "#8B5CF6", 4f)\n                        setPadding(dp(3), dp(1), dp(3), dp(1))\n                    }\n                    cell.addView(\n                        badge,\n                        LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                            bottomMargin = dp(2)\n                        }\n                    )\n                }\n\n                row.addView(cell, LayoutParams(0, LayoutParams.MATCH_PARENT, 1f))\n            }\n\n            gridContainer.addView(row, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n            weekStart = weekStart.plusWeeks(1)\n        }\n    }\n\n    private fun showDayDetailsDialog(date: LocalDate, dayData: CalendarDisplayDay?) {\n        val en = DemoModeHelper.isEnglish(context)\n        val fiWeekdays = arrayOf("Ma", "Ti", "Ke", "To", "Pe", "La", "Su")\n        val enWeekdays = arrayOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")\n        val dowStr = (if (en) enWeekdays else fiWeekdays)[date.dayOfWeek.value - 1]\n        val dateStr = date.format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))\n\n        val root = LinearLayout(context).apply {\n            orientation = VERTICAL\n            setBackgroundColor(Color.parseColor("#182332"))\n            setPadding(dp(18), dp(16), dp(18), dp(14))\n        }\n\n        val titleTv = TextView(context).apply {\n            text = "$dowStr $dateStr"\n            setTextColor(Color.parseColor("#F1F5F9"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)\n            setTypeface(null, Typeface.BOLD)\n        }\n        root.addView(titleTv)\n\n        val contentBox = LinearLayout(context).apply {\n            orientation = VERTICAL\n            setPadding(0, dp(10), 0, dp(10))\n        }\n\n        var hasAny = false\n        dayData?.shifts?.forEach { shift ->\n            hasAny = true\n            val card = LinearLayout(context).apply {\n                orientation = VERTICAL\n                background = roundedBg("#111923", "#2A394A", 10f)\n                setPadding(dp(12), dp(10), dp(12), dp(10))\n            }\n            card.addView(\n                TextView(context).apply {\n                    text = "${shift.startText} – ${shift.endText}"\n                    setTextColor(Color.parseColor("#38BDF8"))\n                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)\n                    setTypeface(null, Typeface.BOLD)\n                }\n            )\n            if (shift.location.isNotEmpty()) {\n                card.addView(\n                    TextView(context).apply {\n                        text = shift.location\n                        setTextColor(Color.parseColor("#F1F5F9"))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)\n                        setTypeface(null, Typeface.BOLD)\n                        setPadding(0, dp(2), 0, 0)\n                    }\n                )\n            }\n            val sub = listOf(shift.shiftName, shift.role).filter { it.isNotBlank() }.joinToString(" • ")\n            if (sub.isNotEmpty()) {\n                card.addView(\n                    TextView(context).apply {\n                        text = sub\n                        setTextColor(Color.parseColor("#CBD5E1"))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n                        setPadding(0, dp(2), 0, 0)\n                    }\n                )\n            }\n            contentBox.addView(\n                card,\n                LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                    bottomMargin = dp(8)\n                }\n            )\n        }\n\n        dayData?.absences?.forEach { abs ->\n            hasAny = true\n            val borderHex = when (abs.kind) {\n                "vacation" -> "#22C55E"\n                "sick" -> "#F87171"\n                else -> "#64748B"\n            }\n            val tv = TextView(context).apply {\n                text = abs.title\n                setTextColor(Color.parseColor("#F1F5F9"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)\n                setTypeface(null, Typeface.BOLD)\n                background = roundedBg("#111923", borderHex, 8f)\n                setPadding(dp(12), dp(9), dp(12), dp(9))\n            }\n            contentBox.addView(\n                tv,\n                LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                    bottomMargin = dp(8)\n                }\n            )\n        }\n\n        dayData?.requests?.forEach { req ->\n            hasAny = true\n            val tv = TextView(context).apply {\n                text = (if (en) "Request: " else "Toive: ") + req.title\n                setTextColor(Color.parseColor("#EDE9FE"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)\n                background = roundedBg("#2E1F47", "#8B5CF6", 8f)\n                setPadding(dp(12), dp(9), dp(12), dp(9))\n            }\n            contentBox.addView(\n                tv,\n                LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                    bottomMargin = dp(8)\n                }\n            )\n        }\n\n        if (!hasAny) {\n            contentBox.addView(\n                TextView(context).apply {\n                    text = if (en) "No scheduled shifts" else "Ei merkittyjä vuoroja"\n                    setTextColor(Color.parseColor("#94A3B8"))\n                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)\n                }\n            )\n        }\n\n        val commentTv = TextView(context).apply {\n            setTextColor(Color.parseColor("#FDE68A"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n            background = roundedBg("#2A2210", "#F59E0B", 8f)\n            setPadding(dp(10), dp(8), dp(10), dp(8))\n            visibility = if (dayData?.hasCommentCircle == true && !DemoModeHelper.isDemoEnabled(context)) View.VISIBLE else View.GONE\n            text = if (en) "Loading shift comment..." else "Haetaan vuorokommenttia..."\n        }\n        contentBox.addView(\n            commentTv,\n            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                bottomMargin = dp(8)\n            }\n        )\n\n        root.addView(contentBox)\n\n        val dialog = AlertDialog.Builder(context)\n            .setView(root)\n            .create()\n\n        if (!DemoModeHelper.isDemoEnabled(context)) {\n            val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n            val btnRow = LinearLayout(context).apply {\n                orientation = HORIZONTAL\n            }\n            val isoDate = date.toString()\n            val listDateParam = URLEncoder.encode("${date.monthValue}/${date.dayOfMonth}/${date.year} 00:00:00", "UTF-8")\n\n            val btnAddReq = Button(context).apply {\n                text = if (en) "+ Add Request" else "+ Lisää toive"\n                isAllCaps = false\n                setTextColor(Color.WHITE)\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)\n                setTypeface(null, Typeface.BOLD)\n                background = roundedBg("#1982C4", "#38BDF8", 8f)\n                setOnClickListener {\n                    dialog.dismiss()\n                    if (baseUrl.isNotBlank()) {\n                        onOpenWebUrl(\n                            "$baseUrl/PersonRequests/Edit?calendarView=Month&returnValue=$isoDate",\n                            if (en) "New request ($dateStr)" else "Uusi toive ($dateStr)"\n                        )\n                    }\n                }\n            }\n            btnRow.addView(\n                btnAddReq,\n                LayoutParams(0, dp(40), 1f).apply {\n                    marginEnd = dp(8)\n                }\n            )\n\n            val btnOpenDay = Button(context).apply {\n                text = if (en) "Open day" else "Avaa päivä"\n                isAllCaps = false\n                setTextColor(Color.parseColor("#E2E8F0"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)\n                background = roundedBg("#233040", "#37475A", 8f)\n                setOnClickListener {\n                    dialog.dismiss()\n                    if (baseUrl.isNotBlank()) {\n                        onOpenWebUrl(\n                            "$baseUrl/Calendar/List?date=$listDateParam",\n                            dateStr\n                        )\n                    }\n                }\n            }\n            btnRow.addView(btnOpenDay, LayoutParams(0, dp(40), 1f))\n            root.addView(btnRow)\n\n            if (dayData?.hasCommentCircle == true && baseUrl.isNotBlank()) {\n                scope.launch {\n                    val comment = withContext(Dispatchers.IO) {\n                        val cookies = try {\n                            CookieManager.getInstance().getCookie(baseUrl)\n                        } catch (_: Exception) {\n                            null\n                        }\n                        NumeronParser.fetchDayComments(baseUrl, cookies, date)\n                    }\n                    if (dialog.isShowing) {\n                        if (!comment.isNullOrBlank()) {\n                            commentTv.text = (if (en) "Note: " else "Huomio: ") + comment\n                            commentTv.visibility = View.VISIBLE\n                        } else {\n                            commentTv.visibility = View.GONE\n                        }\n                    }\n                }\n            }\n        }\n\n        val btnClose = Button(context).apply {\n            text = if (en) "Close" else "Sulje"\n            isAllCaps = false\n            setTextColor(Color.parseColor("#CBD5E1"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n            background = roundedBg("#233040", "#37475A", 8f)\n            setOnClickListener { dialog.dismiss() }\n        }\n        root.addView(\n            btnClose,\n            LayoutParams(LayoutParams.MATCH_PARENT, dp(38)).apply {\n                topMargin = dp(8)\n            }\n        )\n\n        dialog.window?.setBackgroundDrawable(GradientDrawable().apply {\n            cornerRadius = dp(14).toFloat()\n            setColor(Color.parseColor("#182332"))\n            setStroke(dp(1), Color.parseColor("#38BDF8"))\n        })\n        dialog.show()\n    }\n\n    private fun showMonthJumpDialog() {\n        val en = DemoModeHelper.isEnglish(context)\n        val shortNames = if (en) enShortMonths else fiShortMonths\n        var selectedYear = displayedMonth.year\n        val realNow = YearMonth.now()\n\n        val root = LinearLayout(context).apply {\n            orientation = VERTICAL\n            setBackgroundColor(Color.parseColor("#182332"))\n            setPadding(dp(16), dp(16), dp(16), dp(14))\n        }\n\n        root.addView(\n            TextView(context).apply {\n                text = if (en) "JUMP TO MONTH & YEAR" else "SIIRRY KUUKAUTEEN JA VUOTEEN"\n                setTextColor(Color.parseColor("#38BDF8"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)\n                setTypeface(null, Typeface.BOLD)\n                gravity = Gravity.CENTER\n                setPadding(0, 0, 0, dp(10))\n            }\n        )\n\n        val yearRow = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n            gravity = Gravity.CENTER_VERTICAL\n            background = roundedBg("#111923", "#2A394A", 10f)\n            setPadding(dp(8), dp(6), dp(8), dp(6))\n        }\n\n        val yearLabel = TextView(context).apply {\n            text = selectedYear.toString()\n            setTextColor(Color.parseColor("#F1F5F9"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)\n            setTypeface(null, Typeface.BOLD)\n            gravity = Gravity.CENTER\n        }\n\n        val gridHost = LinearLayout(context).apply {\n            orientation = VERTICAL\n            setPadding(0, dp(12), 0, dp(12))\n        }\n\n        val dialog = AlertDialog.Builder(context)\n            .setView(root)\n            .create()\n\n        fun renderMonths() {\n            yearLabel.text = selectedYear.toString()\n            gridHost.removeAllViews()\n            for (r in 0..3) {\n                val mRow = LinearLayout(context).apply {\n                    orientation = HORIZONTAL\n                }\n                for (c in 0..2) {\n                    val mVal = r * 3 + c + 1\n                    val isSelected = (selectedYear == displayedMonth.year && mVal == displayedMonth.monthValue)\n                    val isCurrent = (selectedYear == realNow.year && mVal == realNow.monthValue)\n                    val bgHex = if (isSelected) "#1982C4" else "#111923"\n                    val borderHex = if (isSelected || isCurrent) "#38BDF8" else "#2A394A"\n                    val btn = Button(context).apply {\n                        text = shortNames[mVal - 1]\n                        isAllCaps = false\n                        setTextColor(if (isSelected) Color.WHITE else Color.parseColor("#E2E8F0"))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n                        setTypeface(null, Typeface.BOLD)\n                        background = roundedBg(bgHex, borderHex, 8f)\n                        setOnClickListener {\n                            dialog.dismiss()\n                            displayedMonth = YearMonth.of(selectedYear, mVal)\n                            loadMonth(forceNetwork = true)\n                        }\n                    }\n                    mRow.addView(\n                        btn,\n                        LayoutParams(0, dp(40), 1f).apply {\n                            setMargins(dp(3), dp(3), dp(3), dp(3))\n                        }\n                    )\n                }\n                gridHost.addView(mRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n            }\n        }\n\n        val btnPrevYear = Button(context).apply {\n            text = "◀"\n            setTextColor(Color.parseColor("#38BDF8"))\n            background = roundedBg("#233040", "#37475A", 8f)\n            setOnClickListener {\n                selectedYear -= 1\n                renderMonths()\n            }\n        }\n        val btnNextYear = Button(context).apply {\n            text = "▶"\n            setTextColor(Color.parseColor("#38BDF8"))\n            background = roundedBg("#233040", "#37475A", 8f)\n            setOnClickListener {\n                selectedYear += 1\n                renderMonths()\n            }\n        }\n\n        yearRow.addView(btnPrevYear, LayoutParams(dp(42), dp(36)))\n        yearRow.addView(yearLabel, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))\n        yearRow.addView(btnNextYear, LayoutParams(dp(42), dp(36)))\n\n        root.addView(yearRow)\n        root.addView(gridHost)\n\n        val footer = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n        }\n        val btnNow = Button(context).apply {\n            text = if (en) "Current month" else "Nykyinen kuukausi"\n            isAllCaps = false\n            setTextColor(Color.parseColor("#38BDF8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n            background = roundedBg("#233040", "#37475A", 8f)\n            setOnClickListener {\n                dialog.dismiss()\n                displayedMonth = YearMonth.now()\n                loadMonth(forceNetwork = true)\n            }\n        }\n        val btnCancel = Button(context).apply {\n            text = if (en) "Cancel" else "Peruuta"\n            isAllCaps = false\n            setTextColor(Color.parseColor("#CBD5E1"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n            background = roundedBg("#233040", "#37475A", 8f)\n            setOnClickListener { dialog.dismiss() }\n        }\n        footer.addView(btnNow, LayoutParams(0, dp(38), 1f).apply { marginEnd = dp(8) })\n        footer.addView(btnCancel, LayoutParams(0, dp(38), 1f))\n        root.addView(footer)\n\n        renderMonths()\n        dialog.window?.setBackgroundDrawable(GradientDrawable().apply {\n            cornerRadius = dp(14).toFloat()\n            setColor(Color.parseColor("#182332"))\n            setStroke(dp(1), Color.parseColor("#38BDF8"))\n        })\n        dialog.show()\n    }\n\n    private fun pickShiftRgb(\n        shift: CalendarDisplayShift,\n        morningRgb: Int,\n        eveningRgb: Int,\n        nightRgb: Int\n    ): Int {\n        val crossesMidnight = shift.endMinutes < shift.startMinutes\n        return when {\n            crossesMidnight || shift.startMinutes >= 20 * 60 || shift.startMinutes < 4 * 60 -> nightRgb\n            shift.startMinutes >= 11 * 60 + 30 -> eveningRgb\n            else -> morningRgb\n        }\n    }\n\n    private fun contrastColor(rgb: Int): Int {\n        val lum = 0.299 * Color.red(rgb) + 0.587 * Color.green(rgb) + 0.114 * Color.blue(rgb)\n        return if (lum > 150.0) Color.parseColor("#0F1722") else Color.WHITE\n    }\n\n    private fun roundedBg(fillHex: String, strokeHex: String, radiusDp: Float): GradientDrawable {\n        return GradientDrawable().apply {\n            shape = GradientDrawable.RECTANGLE\n            cornerRadius = dp(radiusDp.toInt()).toFloat()\n            setColor(Color.parseColor(fillHex))\n            setStroke(dp(1), Color.parseColor(strokeHex))\n        }\n    }\n\n    private fun cellBg(fillHex: String, strokeHex: String): GradientDrawable {\n        return GradientDrawable().apply {\n            shape = GradientDrawable.RECTANGLE\n            setColor(Color.parseColor(fillHex))\n            setStroke(1, Color.parseColor(strokeHex))\n        }\n    }\n\n    private fun dp(value: Int): Int {\n        return TypedValue.applyDimension(\n            TypedValue.COMPLEX_UNIT_DIP,\n            value.toFloat(),\n            resources.displayMetrics\n        ).toInt()\n    }\n}\n'

NATIVE_REQUESTS_VIEW_KT = 'package fi.numeron.vuorovahti\n\nimport android.content.Context\nimport android.graphics.Color\nimport android.graphics.Typeface\nimport android.graphics.drawable.GradientDrawable\nimport android.util.TypedValue\nimport android.view.Gravity\nimport android.view.View\nimport android.widget.Button\nimport android.widget.FrameLayout\nimport android.widget.LinearLayout\nimport android.widget.ProgressBar\nimport android.widget.ScrollView\nimport android.widget.TextView\nimport android.widget.Toast\nimport kotlinx.coroutines.CoroutineScope\nimport kotlinx.coroutines.Job\nimport kotlinx.coroutines.launch\nimport java.time.Instant\nimport java.time.LocalDate\nimport java.time.ZoneId\nimport java.time.format.DateTimeFormatter\n\nclass NativeRequestsView(\n    private val context: Context,\n    private val scope: CoroutineScope,\n    private val onOpenWebUrl: (url: String, title: String) -> Unit\n) : LinearLayout(context) {\n\n    private var currentFilter: String = "active"\n    private var loadJob: Job? = null\n\n    private val txtTitle: TextView\n    private val btnAdd: Button\n    private val btnRefresh: Button\n    private val btnFilterActive: Button\n    private val btnFilterOld: Button\n    private val btnFilterRemoved: Button\n    private val progressBar: ProgressBar\n    private val txtStatus: TextView\n    private val listContainer: LinearLayout\n\n    private val dateFmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")\n    private val dateTimeFmt = DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm")\n\n    init {\n        orientation = VERTICAL\n        setBackgroundColor(Color.parseColor("#0F1722"))\n        setPadding(dp(10), dp(10), dp(10), dp(4))\n\n        val topCard = LinearLayout(context).apply {\n            orientation = VERTICAL\n            background = roundedBg("#182332", "#2A394A", 12f)\n            setPadding(dp(12), dp(10), dp(12), dp(10))\n        }\n\n        val titleRow = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n            gravity = Gravity.CENTER_VERTICAL\n        }\n\n        txtTitle = TextView(context).apply {\n            setTextColor(Color.parseColor("#F1F5F9"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)\n            setTypeface(null, Typeface.BOLD)\n        }\n        titleRow.addView(txtTitle, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))\n\n        btnRefresh = Button(context).apply {\n            text = "↻"\n            setTextColor(Color.parseColor("#38BDF8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)\n            background = roundedBg("#233040", "#37475A", 8f)\n            setPadding(0, 0, 0, 0)\n            setOnClickListener { loadRequests(forceNetwork = true) }\n        }\n        titleRow.addView(\n            btnRefresh,\n            LayoutParams(dp(40), dp(36)).apply {\n                marginEnd = dp(8)\n            }\n        )\n\n        btnAdd = Button(context).apply {\n            isAllCaps = false\n            setTextColor(Color.WHITE)\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)\n            setTypeface(null, Typeface.BOLD)\n            background = roundedBg("#1982C4", "#38BDF8", 8f)\n            setPadding(dp(14), dp(4), dp(14), dp(4))\n            minHeight = 0\n            minimumHeight = dp(36)\n            setOnClickListener { openNewRequest() }\n        }\n        titleRow.addView(btnAdd, LayoutParams(LayoutParams.WRAP_CONTENT, dp(36)))\n        topCard.addView(titleRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        // Suodatinpainikkeet\n        val filterRow = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n            setPadding(0, dp(10), 0, 0)\n        }\n\n        btnFilterActive = makeFilterButton("active")\n        btnFilterOld = makeFilterButton("old")\n        btnFilterRemoved = makeFilterButton("removed")\n\n        filterRow.addView(btnFilterActive, LayoutParams(0, dp(34), 1f).apply { marginEnd = dp(6) })\n        filterRow.addView(btnFilterOld, LayoutParams(0, dp(34), 1f).apply { marginEnd = dp(6) })\n        filterRow.addView(btnFilterRemoved, LayoutParams(0, dp(34), 1f))\n        topCard.addView(filterRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        // Tilapalkki\n        val statusRow = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n            gravity = Gravity.CENTER_VERTICAL\n            setPadding(0, dp(8), 0, 0)\n        }\n        progressBar = ProgressBar(context, null, android.R.attr.progressBarStyleSmall).apply {\n            isIndeterminate = true\n            visibility = View.GONE\n        }\n        statusRow.addView(progressBar, LayoutParams(dp(16), dp(16)))\n\n        txtStatus = TextView(context).apply {\n            setTextColor(Color.parseColor("#94A3B8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)\n            setPadding(dp(6), 0, 0, 0)\n        }\n        statusRow.addView(txtStatus, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))\n        topCard.addView(statusRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        addView(\n            topCard,\n            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                bottomMargin = dp(8)\n            }\n        )\n\n        val scroll = ScrollView(context).apply {\n            isFillViewport = true\n        }\n        listContainer = LinearLayout(context).apply {\n            orientation = VERTICAL\n        }\n        scroll.addView(listContainer, FrameLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n        addView(scroll, LayoutParams(LayoutParams.MATCH_PARENT, 0, 1f))\n    }\n\n    private fun makeFilterButton(filterKey: String): Button {\n        return Button(context).apply {\n            isAllCaps = false\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)\n            setPadding(dp(6), dp(2), dp(6), dp(2))\n            minHeight = 0\n            minimumHeight = dp(34)\n            setOnClickListener {\n                if (currentFilter != filterKey) {\n                    currentFilter = filterKey\n                    updateFilterStyles()\n                    loadRequests(forceNetwork = true)\n                }\n            }\n        }\n    }\n\n    fun onShow(forceNetwork: Boolean = false) {\n        updateLocalizedLabels()\n        updateFilterStyles()\n        loadRequests(forceNetwork = forceNetwork)\n    }\n\n    fun refreshAfterWebEdit() {\n        updateLocalizedLabels()\n        loadRequests(forceNetwork = true)\n    }\n\n    private fun updateLocalizedLabels() {\n        val en = DemoModeHelper.isEnglish(context)\n        txtTitle.text = if (en) "Requests" else "Toiveet"\n        btnAdd.text = if (en) "+ Add" else "+ Lisää"\n        btnFilterActive.text = if (en) "Active" else "Aktiiviset"\n        btnFilterOld.text = if (en) "All / Old" else "Myös vanhat"\n        btnFilterRemoved.text = if (en) "Removed" else "Poistetut"\n    }\n\n    private fun updateFilterStyles() {\n        val pairs = listOf(\n            "active" to btnFilterActive,\n            "old" to btnFilterOld,\n            "removed" to btnFilterRemoved\n        )\n        for ((key, btn) in pairs) {\n            val selected = (key == currentFilter)\n            btn.background = roundedBg(\n                if (selected) "#1982C4" else "#111923",\n                if (selected) "#38BDF8" else "#2A394A",\n                8f\n            )\n            btn.setTextColor(if (selected) Color.WHITE else Color.parseColor("#CBD5E1"))\n            btn.setTypeface(null, if (selected) Typeface.BOLD else Typeface.NORMAL)\n        }\n    }\n\n    private fun openNewRequest() {\n        val en = DemoModeHelper.isEnglish(context)\n        if (DemoModeHelper.isDemoEnabled(context)) {\n            Toast.makeText(\n                context,\n                if (en) "Demo mode: Adding requests is disabled" else "Demotila: Toiveen lisäys ei ole käytössä demossa",\n                Toast.LENGTH_SHORT\n            ).show()\n            return\n        }\n        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n        if (baseUrl.isBlank()) {\n            Toast.makeText(\n                context,\n                if (en) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista",\n                Toast.LENGTH_LONG\n            ).show()\n            return\n        }\n        onOpenWebUrl("$baseUrl/PersonRequests/Edit", if (en) "New request" else "Uusi toive")\n    }\n\n    private fun loadRequests(forceNetwork: Boolean) {\n        val filter = currentFilter\n        val en = DemoModeHelper.isEnglish(context)\n        loadJob?.cancel()\n\n        if (DemoModeHelper.isDemoEnabled(context)) {\n            progressBar.visibility = View.GONE\n            txtStatus.text = if (en) "Demo mode" else "Demotila"\n            val today = LocalDate.now()\n            val demoItems = listOf(\n                PersonRequestItem(\n                    id = 1,\n                    type = if (en) "Day off" else "Vapaapäivä",\n                    dateFrom = today.plusDays(10),\n                    dateTo = today.plusDays(10),\n                    timeFromText = "",\n                    timeToText = "",\n                    info = if (en) "Family event" else "Perhejuhla",\n                    statusCode = 50,\n                    statusDescription = if (en) "Approved" else "Hyväksytty",\n                    belongsToSeries = false,\n                    approvedBy = "esimies@organisaatio.fi",\n                    approvedDateMs = System.currentTimeMillis() - 3600_000L * 5\n                ),\n                PersonRequestItem(\n                    id = 2,\n                    type = if (en) "Morning shift" else "Aamuvuoro",\n                    dateFrom = today.plusDays(14),\n                    dateTo = today.plusDays(14),\n                    timeFromText = "",\n                    timeToText = "",\n                    info = "",\n                    statusCode = 10,\n                    statusDescription = if (en) "Pending" else "Odottaa käsittelyä",\n                    belongsToSeries = false,\n                    approvedBy = "",\n                    approvedDateMs = null\n                )\n            )\n            renderRequests(if (filter == "removed") emptyList() else demoItems)\n            return\n        }\n\n        // 1. Näytetään heti paikallinen välimuisti\n        val cached = NumeronApiClient.loadCachedRequests(context, filter)\n        if (cached != null) {\n            renderRequests(cached)\n        }\n\n        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n        if (baseUrl.isBlank()) {\n            progressBar.visibility = View.GONE\n            txtStatus.text = if (en) "Set organization in Settings" else "Aseta organisaatio asetuksista"\n            return\n        }\n\n        progressBar.visibility = View.VISIBLE\n        txtStatus.text = if (cached != null && !forceNetwork) {\n            if (en) "Updating..." else "Päivitetään..."\n        } else {\n            if (en) "Loading requests..." else "Haetaan toiveita..."\n        }\n\n        loadJob = scope.launch {\n            val result = NumeronApiClient.fetchRequests(context, filter)\n            if (filter != currentFilter) return@launch\n            progressBar.visibility = View.GONE\n\n            if (result.items != null) {\n                renderRequests(result.items)\n                txtStatus.text = if (result.fromCache) {\n                    if (en) "Offline cache (${result.items.size})" else "Välimuisti (${result.items.size} kpl)"\n                } else {\n                    if (en) "${result.items.size} requests" else "${result.items.size} toivetta"\n                }\n            } else {\n                txtStatus.text = result.errorMessage ?: (if (en) "Failed to load" else "Haku epäonnistui")\n                if (cached == null) {\n                    renderRequests(emptyList())\n                }\n            }\n        }\n    }\n\n    private fun renderRequests(items: List<PersonRequestItem>) {\n        listContainer.removeAllViews()\n        val en = DemoModeHelper.isEnglish(context)\n\n        if (items.isEmpty()) {\n            val emptyCard = TextView(context).apply {\n                text = if (en) "No requests in this view." else "Ei toiveita tässä näkymässä."\n                setTextColor(Color.parseColor("#94A3B8"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)\n                gravity = Gravity.CENTER\n                background = roundedBg("#182332", "#2A394A", 12f)\n                setPadding(dp(16), dp(24), dp(16), dp(24))\n            }\n            listContainer.addView(emptyCard, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n            return\n        }\n\n        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n        val isDemo = DemoModeHelper.isDemoEnabled(context)\n\n        for (item in items) {\n            val card = LinearLayout(context).apply {\n                orientation = VERTICAL\n                background = roundedBg("#182332", "#2A394A", 12f)\n                setPadding(dp(14), dp(12), dp(14), dp(12))\n                setOnClickListener {\n                    if (isDemo) {\n                        Toast.makeText(\n                            context,\n                            if (en) "Demo mode: Editing is disabled" else "Demotila: Muokkaus ei ole käytössä demossa",\n                            Toast.LENGTH_SHORT\n                        ).show()\n                    } else if (baseUrl.isNotBlank()) {\n                        onOpenWebUrl("$baseUrl/PersonRequests/Edit/${item.id}", item.type)\n                    }\n                }\n            }\n\n            // Ylärivi: tyyppi + tilabadge\n            val topRow = LinearLayout(context).apply {\n                orientation = HORIZONTAL\n                gravity = Gravity.CENTER_VERTICAL\n            }\n\n            val typeTv = TextView(context).apply {\n                text = item.type\n                setTextColor(Color.parseColor("#F1F5F9"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 15.5f)\n                setTypeface(null, Typeface.BOLD)\n            }\n            topRow.addView(typeTv, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))\n\n            val (badgeBg, badgeBorder, badgeFg) = when (item.statusCode) {\n                50 -> Triple("#0F2E26", "#22C55E", "#4ADE80")\n                40 -> Triple("#3B2810", "#F59E0B", "#FBBF24")\n                80 -> Triple("#3F1D24", "#EF4444", "#F87171")\n                else -> Triple("#1E3A5F", "#38BDF8", "#7DD3FC")\n            }\n\n            val statusTv = TextView(context).apply {\n                text = item.statusDescription\n                setTextColor(Color.parseColor(badgeFg))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)\n                setTypeface(null, Typeface.BOLD)\n                background = roundedBg(badgeBg, badgeBorder, 99f)\n                setPadding(dp(10), dp(3), dp(10), dp(3))\n            }\n            topRow.addView(\n                statusTv,\n                LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT).apply {\n                    marginStart = dp(8)\n                }\n            )\n            card.addView(topRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n            // Päivämäärä ja kellonaika\n            val dateLine = buildString {\n                if (item.dateFrom != null) {\n                    append(item.dateFrom.format(dateFmt))\n                    if (item.dateTo != null && item.dateTo != item.dateFrom) {\n                        append(" – ")\n                        append(item.dateTo.format(dateFmt))\n                    }\n                }\n                if (item.timeFromText.isNotEmpty() || item.timeToText.isNotEmpty()) {\n                    if (isNotEmpty()) append("  •  ")\n                    append(item.timeFromText)\n                    if (item.timeToText.isNotEmpty()) {\n                        append("–")\n                        append(item.timeToText)\n                    }\n                }\n                if (item.belongsToSeries) {\n                    if (isNotEmpty()) append("  •  ")\n                    append(if (en) "Recurring" else "Jatkuva")\n                }\n            }\n\n            if (dateLine.isNotEmpty()) {\n                card.addView(\n                    TextView(context).apply {\n                        text = dateLine\n                        setTextColor(Color.parseColor("#38BDF8"))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)\n                        setTypeface(null, Typeface.BOLD)\n                        setPadding(0, dp(6), 0, 0)\n                    }\n                )\n            }\n\n            if (item.info.isNotEmpty()) {\n                card.addView(\n                    TextView(context).apply {\n                        text = item.info\n                        setTextColor(Color.parseColor("#CBD5E1"))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n                        setPadding(0, dp(4), 0, 0)\n                    }\n                )\n            }\n\n            // Käsittelijä ja käsittelyaika\n            val metaParts = mutableListOf<String>()\n            if (item.approvedDateMs != null && item.approvedDateMs > 0L) {\n                val dtStr = Instant.ofEpochMilli(item.approvedDateMs)\n                    .atZone(ZoneId.systemDefault())\n                    .toLocalDateTime()\n                    .format(dateTimeFmt)\n                metaParts.add(dtStr)\n            }\n            if (item.approvedBy.isNotEmpty()) {\n                metaParts.add(item.approvedBy)\n            }\n            if (metaParts.isNotEmpty()) {\n                card.addView(\n                    TextView(context).apply {\n                        text = metaParts.joinToString(" • ")\n                        setTextColor(Color.parseColor("#94A3B8"))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)\n                        setPadding(0, dp(6), 0, 0)\n                    }\n                )\n            }\n\n            listContainer.addView(\n                card,\n                LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                    bottomMargin = dp(8)\n                }\n            )\n        }\n    }\n\n    private fun roundedBg(fillHex: String, strokeHex: String, radiusDp: Float): GradientDrawable {\n        return GradientDrawable().apply {\n            shape = GradientDrawable.RECTANGLE\n            cornerRadius = dp(radiusDp.toInt()).toFloat()\n            setColor(Color.parseColor(fillHex))\n            setStroke(dp(1), Color.parseColor(strokeHex))\n        }\n    }\n\n    private fun dp(value: Int): Int {\n        return TypedValue.applyDimension(\n            TypedValue.COMPLEX_UNIT_DIP,\n            value.toFloat(),\n            resources.displayMetrics\n        ).toInt()\n    }\n}\n'

NEW_ACTIVITY_MAIN_XML = '<?xml version="1.0" encoding="utf-8"?>\n<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"\n    android:layout_width="match_parent"\n    android:layout_height="match_parent"\n    android:orientation="vertical"\n    android:background="#0F1722">\n\n    <TextView\n        android:id="@+id/bannerDemoMode"\n        android:layout_width="match_parent"\n        android:layout_height="wrap_content"\n        android:background="#D97706"\n        android:text="DEMOTILA AKTIIVINEN – Kokeile leimausta, vuoroja ja ilmoituksia"\n        android:textColor="#FFFFFF"\n        android:textSize="12sp"\n        android:textStyle="bold"\n        android:gravity="center"\n        android:paddingVertical="4dp"\n        android:visibility="gone" />\n\n    <FrameLayout\n        android:id="@+id/contentContainer"\n        android:layout_width="match_parent"\n        android:layout_height="0dp"\n        android:layout_weight="1"\n        android:background="#0F1722">\n\n        <LinearLayout\n            android:id="@+id/webViewHost"\n            android:layout_width="match_parent"\n            android:layout_height="match_parent"\n            android:orientation="vertical"\n            android:background="#0F1722"\n            android:visibility="gone">\n\n            <LinearLayout\n                android:id="@+id/webOverlayHeader"\n                android:layout_width="match_parent"\n                android:layout_height="46dp"\n                android:orientation="horizontal"\n                android:gravity="center_vertical"\n                android:paddingHorizontal="10dp"\n                android:background="#182332"\n                android:visibility="gone">\n\n                <Button\n                    android:id="@+id/btnWebOverlayBack"\n                    android:layout_width="wrap_content"\n                    android:layout_height="34dp"\n                    android:minHeight="0dp"\n                    android:paddingHorizontal="12dp"\n                    android:background="@drawable/nav_btn_inactive"\n                    android:text="← Takaisin"\n                    android:textAllCaps="false"\n                    android:textColor="#38BDF8"\n                    android:textStyle="bold"\n                    android:textSize="13sp" />\n\n                <TextView\n                    android:id="@+id/txtWebOverlayTitle"\n                    android:layout_width="0dp"\n                    android:layout_height="wrap_content"\n                    android:layout_weight="1"\n                    android:layout_marginStart="10dp"\n                    android:textColor="#F1F5F9"\n                    android:textSize="14sp"\n                    android:textStyle="bold"\n                    android:maxLines="1"\n                    android:ellipsize="end" />\n            </LinearLayout>\n\n            <FrameLayout\n                android:id="@+id/webViewSlot"\n                android:layout_width="match_parent"\n                android:layout_height="0dp"\n                android:layout_weight="1"\n                android:background="#0F1722" />\n        </LinearLayout>\n\n        <FrameLayout\n            android:id="@+id/nativeStampContainer"\n            android:layout_width="match_parent"\n            android:layout_height="match_parent"\n            android:background="#0F1722"\n            android:visibility="gone" />\n\n        <FrameLayout\n            android:id="@+id/nativeShiftsContainer"\n            android:layout_width="match_parent"\n            android:layout_height="match_parent"\n            android:background="#0F1722"\n            android:visibility="gone" />\n\n        <FrameLayout\n            android:id="@+id/nativeRequestsContainer"\n            android:layout_width="match_parent"\n            android:layout_height="match_parent"\n            android:background="#0F1722"\n            android:visibility="gone" />\n    </FrameLayout>\n\n    <LinearLayout\n        android:layout_width="match_parent"\n        android:layout_height="60dp"\n        android:orientation="horizontal"\n        android:padding="6dp"\n        android:background="#0B111A"\n        android:gravity="center_vertical">\n\n        <Button\n            android:id="@+id/btnNavStamp"\n            android:layout_width="0dp"\n            android:layout_height="match_parent"\n            android:layout_weight="1.3"\n            android:layout_marginEnd="4dp"\n            android:background="@drawable/nav_btn_active"\n            android:text="Leimaus"\n            android:textAllCaps="false"\n            android:textColor="#FFFFFF"\n            android:textStyle="bold"\n            android:textSize="13sp" />\n\n        <Button\n            android:id="@+id/btnNavRequests"\n            android:layout_width="0dp"\n            android:layout_height="match_parent"\n            android:layout_weight="1.2"\n            android:layout_marginEnd="4dp"\n            android:background="@drawable/nav_btn_inactive"\n            android:text="Toiveet"\n            android:textAllCaps="false"\n            android:textColor="#E0E6ED"\n            android:textSize="13sp" />\n\n        <Button\n            android:id="@+id/btnNavShifts"\n            android:layout_width="0dp"\n            android:layout_height="match_parent"\n            android:layout_weight="1.2"\n            android:layout_marginEnd="4dp"\n            android:background="@drawable/nav_btn_inactive"\n            android:text="Vuorot"\n            android:textAllCaps="false"\n            android:textColor="#E0E6ED"\n            android:textSize="13sp" />\n\n        <Button\n            android:id="@+id/btnNavSettings"\n            android:layout_width="0dp"\n            android:layout_height="match_parent"\n            android:layout_weight="0.8"\n            android:layout_marginEnd="4dp"\n            android:background="@drawable/nav_btn_inactive"\n            android:text="⚙"\n            android:textColor="#E0E6ED"\n            android:textSize="18sp" />\n\n        <Button\n            android:id="@+id/btnNavClose"\n            android:layout_width="0dp"\n            android:layout_height="match_parent"\n            android:layout_weight="0.8"\n            android:background="@drawable/nav_btn_close"\n            android:text="✕"\n            android:textColor="#FFFFFF"\n            android:textSize="16sp" />\n    </LinearLayout>\n</LinearLayout>\n'

NUMERON_PARSER_ADDITION = '\n\ndata class CalendarDisplayShift(\n    val startText: String,\n    val endText: String,\n    val startMinutes: Int,\n    val endMinutes: Int,\n    val location: String,\n    val shiftName: String,\n    val role: String,\n    val rawTitle: String\n)\n\ndata class CalendarDisplayAbsence(\n    val title: String,\n    val kind: String,\n    val spanDays: Int = 1\n)\n\ndata class CalendarDisplayRequest(\n    val title: String\n)\n\ndata class CalendarDisplayDay(\n    val date: LocalDate,\n    val shifts: List<CalendarDisplayShift>,\n    val absences: List<CalendarDisplayAbsence>,\n    val requests: List<CalendarDisplayRequest>,\n    val hasCommentCircle: Boolean = false\n)\n\ndata class MonthDisplayData(\n    val year: Int,\n    val month: Int,\n    val days: Map<LocalDate, CalendarDisplayDay>\n)\n'

NUMERON_PARSER_METHODS = '\n    private fun isDisplayIgnoredAbsence(nameText: String): Boolean {\n        val lower = nameText.trim().lowercase()\n        return lower == "vapaa" ||\n            lower.startsWith("vapaapäivä") ||\n            lower.startsWith("arkipyhä") ||\n            lower.startsWith("viikkolepo") ||\n            lower.startsWith("viikkovapaa") ||\n            lower.startsWith("tasausvapaa") ||\n            lower.startsWith("saldovapaa") ||\n            lower.startsWith("pekkanen") ||\n            lower.startsWith("pekkaspäivä") ||\n            lower.startsWith("ei suunniteltuja töitä") ||\n            lower == "ei työvuoroa" ||\n            lower == "ei vuoroa"\n    }\n\n    private fun classifyDisplayAbsence(nameText: String): String {\n        val lower = nameText.trim().lowercase()\n        return when {\n            lower.contains("sairaus") || lower.contains("hoitovapaa") -> "sick"\n            lower.contains("loma") || lower.contains("säästövapaa") || lower.contains("lomarahavapaa") -> "vacation"\n            else -> "other"\n        }\n    }\n\n    fun parseMonthForDisplay(html: String): MonthDisplayData? {\n        val doc = Jsoup.parse(html)\n        val monthHeader = doc.selectFirst("#monthText")?.text()?.trim()?.lowercase() ?: return null\n        val parts = monthHeader.split(Regex("\\\\s+"))\n        if (parts.size < 2) return null\n\n        val currentMonth = finnishMonths[parts[0]] ?: return null\n        val currentYear = parts[1].toIntOrNull() ?: return null\n        val dayCells = doc.select("table.month-table td.month-day")\n        if (dayCells.isEmpty()) return null\n\n        val shiftsByDate = mutableMapOf<LocalDate, MutableList<CalendarDisplayShift>>()\n        val absencesByDate = mutableMapOf<LocalDate, MutableList<CalendarDisplayAbsence>>()\n        val requestsByDate = mutableMapOf<LocalDate, MutableList<CalendarDisplayRequest>>()\n        val circleDates = mutableSetOf<LocalDate>()\n        val timeFmt = DateTimeFormatter.ofPattern("H:mm")\n\n        for (cell in dayCells) {\n            if (cell.hasClass("day-different-month")) continue\n            val dayNum = cell.selectFirst(".dayNum")?.text()?.trim()?.toIntOrNull() ?: continue\n            val date = try {\n                LocalDate.of(currentYear, currentMonth, dayNum)\n            } catch (_: Exception) {\n                continue\n            }\n\n            if (cell.selectFirst(".circle") != null) {\n                circleDates.add(date)\n            }\n\n            // Poissaolot (säilyttää lomat, sairauslomat ja koulutukset/muut)\n            cell.select(".month-item.absence").forEach { item ->\n                val nameText = item.selectFirst(".itemName")?.text()?.trim() ?: return@forEach\n                if (nameText.isEmpty() || isDisplayIgnoredAbsence(nameText)) return@forEach\n                val kind = classifyDisplayAbsence(nameText)\n                val spanDays = parseAbsenceSpanDays(item.attr("style"))\n                for (offset in 0 until spanDays) {\n                    val targetDate = date.plusDays(offset.toLong())\n                    if (targetDate.monthValue == currentMonth && targetDate.year == currentYear) {\n                        val list = absencesByDate.getOrPut(targetDate) { mutableListOf() }\n                        if (list.none { it.title.equals(nameText, ignoreCase = true) }) {\n                            list.add(CalendarDisplayAbsence(nameText, kind, if (offset == 0) spanDays else 1))\n                        }\n                    }\n                }\n            }\n\n            // Työvuorot (sekä menneet että tulevat koko kuukaudelta)\n            cell.select(".month-item.work").forEach { item ->\n                val timesText = item.selectFirst(".itemTimes")?.text()?.trim() ?: ""\n                val rawNameText = item.selectFirst(".itemName")?.text()?.trim() ?: ""\n                val timeParts = timesText.split("-").map { it.trim() }\n                if (timeParts.size == 2) {\n                    val startTime = try {\n                        LocalTime.parse(timeParts[0], timeFmt)\n                    } catch (_: Exception) {\n                        return@forEach\n                    }\n                    val endTime = try {\n                        LocalTime.parse(timeParts[1], timeFmt)\n                    } catch (_: Exception) {\n                        return@forEach\n                    }\n                    val parsed = parseShiftText(rawNameText)\n                    val list = shiftsByDate.getOrPut(date) { mutableListOf() }\n                    list.add(\n                        CalendarDisplayShift(\n                            startText = String.format("%d:%02d", startTime.hour, startTime.minute),\n                            endText = String.format("%d:%02d", endTime.hour, endTime.minute),\n                            startMinutes = startTime.hour * 60 + startTime.minute,\n                            endMinutes = endTime.hour * 60 + endTime.minute,\n                            location = parsed.location,\n                            shiftName = parsed.shiftName,\n                            role = parsed.role,\n                            rawTitle = rawNameText\n                        )\n                    )\n                }\n            }\n\n            // Toiveet kalenterissa\n            cell.select(".month-item.request").forEach { item ->\n                val title = (item.selectFirst(".itemName")?.text() ?: item.text()).replace(Regex("\\\\s+"), " ").trim()\n                if (title.isNotEmpty()) {\n                    val list = requestsByDate.getOrPut(date) { mutableListOf() }\n                    if (list.none { it.title.equals(title, ignoreCase = true) }) {\n                        list.add(CalendarDisplayRequest(title))\n                    }\n                }\n            }\n        }\n\n        val allDates = (shiftsByDate.keys + absencesByDate.keys + requestsByDate.keys + circleDates)\n        val dayMap = mutableMapOf<LocalDate, CalendarDisplayDay>()\n        for (d in allDates) {\n            dayMap[d] = CalendarDisplayDay(\n                date = d,\n                shifts = shiftsByDate[d].orEmpty(),\n                absences = absencesByDate[d].orEmpty(),\n                requests = requestsByDate[d].orEmpty(),\n                hasCommentCircle = d in circleDates\n            )\n        }\n        return MonthDisplayData(year = currentYear, month = currentMonth, days = dayMap)\n    }\n\n    fun fetchDayComments(baseUrl: String, cookieHeader: String?, date: LocalDate): String? {\n        if (baseUrl.isBlank()) return null\n        val cleanBase = baseUrl.trimEnd(\'/\')\n        val listUrl = "$cleanBase/Calendar/List?date=${date.monthValue}%2F${date.dayOfMonth}%2F${date.year}%2000%3A00%3A00"\n        val html = fetchHtmlWithCookies(listUrl, cookieHeader) ?: return null\n        val parsed = parseListCommentsHtml(html)\n        val comments = parsed.entries\n            .filter { it.key.first == date }\n            .map { it.value.trim() }\n            .filter { it.isNotEmpty() }\n            .distinct()\n        return if (comments.isEmpty()) null else comments.joinToString("\\n")\n    }\n'

NUMERON_PARSER_BANNER_METHOD = '\n    fun formatShiftBannerLines(rawName: String): Pair<String, String> {\n        val parsed = parseShiftText(rawName)\n        val details = listOf(parsed.shiftName, parsed.role)\n            .filter { it.isNotBlank() }\n            .joinToString(" • ")\n        return parsed.location to details\n    }\n'


def patch_calendar_sync_helper(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text
    text = replace_once(
        text,
        "    private fun loadCachedShifts(context: Context): List<WorkShift>? {",
        "    fun loadCachedShifts(context: Context): List<WorkShift>? {",
        "CalendarSyncHelper.loadCachedShifts julkiseksi natiivikalenterille"
    )
    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_background_auth_helper(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text
    old_block = (
        "            bodies.add(res.body)\n"
        "        }\n\n"
        '        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)'
    )
    new_block = (
        "            NumeronApiClient.extractAndSaveMaxSessionTime(context, res.body)\n"
        "            bodies.add(res.body)\n"
        "        }\n\n"
        '        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)'
    )
    text = replace_once(
        text,
        old_block,
        new_block,
        "BackgroundAuthHelper tallentaa maxSessionTimeInMilliseconds-ajan haetuista sivuista"
    )
    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_numeron_parser(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    old_data_anchor = (
        "data class WorkShift(\n"
        "    val title: String,\n"
        "    val start: LocalDateTime,\n"
        "    val end: LocalDateTime,\n"
        "    val isAllDayLeave: Boolean = false,\n"
        '    val location: String = "",\n'
        '    val description: String = ""\n'
        ")"
    )
    new_data_anchor = old_data_anchor + NUMERON_PARSER_ADDITION
    text = replace_once(
        text,
        old_data_anchor,
        new_data_anchor,
        "Lisätty MonthDisplayData- ja CalendarDisplay*-tietoluokat NumeronParser.kt:hen"
    )

    old_tail_v1 = (
        "        workShifts.add(currentLeave)\n"
        "        return workShifts.sortedBy { it.start }\n"
        "    }\n"
        "}"
    )
    new_tail_v4 = (
        "        workShifts.add(currentLeave)\n"
        "        return workShifts.sortedBy { it.start }\n"
        "    }\n"
        + NUMERON_PARSER_METHODS
        + NUMERON_PARSER_BANNER_METHOD
        + "}"
    )
    old_tail_v3 = (
        "        return if (comments.isEmpty()) null else comments.joinToString(\"\\n\")\n"
        "    }\n"
        "}"
    )
    new_tail_v3_to_v4 = (
        "        return if (comments.isEmpty()) null else comments.joinToString(\"\\n\")\n"
        "    }\n"
        + NUMERON_PARSER_BANNER_METHOD
        + "}"
    )

    if "fun formatShiftBannerLines(" in text:
        print("  [OK - jo sovellettu] NumeronParser display- ja banner-metodit")
    elif old_tail_v3 in text:
        text = replace_once(
            text,
            old_tail_v3,
            new_tail_v3_to_v4,
            "Lisätty formatShiftBannerLines NumeronParser.kt:hen"
        )
    else:
        text = replace_once(
            text,
            old_tail_v1,
            new_tail_v4,
            "Lisätty parseMonthForDisplay, fetchDayComments ja formatShiftBannerLines NumeronParser.kt:hen"
        )

    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_activity_main_xml(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    target = NEW_ACTIVITY_MAIN_XML.strip() + "\n"
    if text.strip() == target.strip():
        print("  [OK - jo sovellettu] activity_main.xml (laiska WebView + kaikki 3 natiivisäiliötä)")
        return False
    write_text_keep_nl(path, target, nl)
    print("  [PÄIVITETTY] activity_main.xml (webViewHost + nativeStamp/Shifts/Requests)")
    return True


def patch_build_gradle(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text
    if "versionCode = 125" in text:
        print("  [OK - jo sovellettu] build.gradle.kts versionCode 125")
        return False
    text = replace_any(
        text,
        ["versionCode = 124", "versionCode = 123"],
        "versionCode = 125",
        "versionCode -> 125"
    )
    text = replace_any(
        text,
        ['versionName = "3.2.182"', 'versionName = "3.2.181"'],
        'versionName = "3.2.183"',
        'versionName -> "3.2.183"'
    )
    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_quick_stamp_activity(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    old_quick_flow = """        activeJob = scope.launch {
            val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val lastSessionMs = prefs.getLong("last_valid_session_ms", 0L)
            val sessionAgeMs = System.currentTimeMillis() - lastSessionMs
            val existingCookies = CookieManager.getInstance().getCookie(baseUrl)

            if (existingCookies.isNullOrBlank() || sessionAgeMs > 10L * 60 * 1000L) {
                statusText.text = "Kirjaudutaan sisään…"
                val ok = BackgroundAuthHelper.ensureAuthenticatedSession(this@QuickStampActivity)
                if (ok) {
                    prefs.edit().putLong("last_valid_session_ms", System.currentTimeMillis()).apply()
                }
            }

            if (!isCompleted) {
                statusText.text = if (en) "Opening time stamping…" else "Avataan työaikaleimaus…"
                startHiddenStampingWebView(baseUrl, wantIn = !isEnding, targetText = targetText)
            }
        }"""

    new_quick_flow = """        if (BackgroundAuthHelper.isCredentialBlocked(this)) {
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
            val wantIn = !isEnding
            val result = NumeronApiClient.performQuickStamp(
                context = this@QuickStampActivity,
                wantIn = wantIn,
                onStatusUpdate = { msg ->
                    runOnUiThread {
                        if (!isCompleted) statusText.text = msg
                    }
                }
            )
            if (isCompleted) return@launch

            when (result) {
                is StampSubmitResult.Success -> {
                    val nowTime = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
                    showFinalState(
                        title = if (en) "Stamp confirmed" else "Leimaus vahvistettu",
                        subtitle = if (en) "$targetText • at $nowTime" else "$targetText • klo $nowTime",
                        badgeText = "✓",
                        badgeFillHex = "#0F2E26",
                        badgeStrokeHex = "#10B981",
                        badgeTextHex = "#34D399",
                        closeDelayMs = 1150L
                    )
                }
                is StampSubmitResult.AlreadyInDirection -> {
                    showFinalState(
                        title = if (en) "Not stamped" else "Ei leimattu",
                        subtitle = if (en) "Already clocked $targetText" else "Olet jo leimannut tilaan: $targetText",
                        badgeText = "!",
                        badgeFillHex = "#1E3A5F",
                        badgeStrokeHex = "#38BDF8",
                        badgeTextHex = "#7DD3FC",
                        closeDelayMs = 1400L
                    )
                }
                is StampSubmitResult.ValidationRejected -> {
                    showFinalState(
                        title = if (en) "Stamp rejected" else "Leimausta ei hyväksytty",
                        subtitle = result.message,
                        badgeText = "!",
                        badgeFillHex = "#3B2810",
                        badgeStrokeHex = "#F59E0B",
                        badgeTextHex = "#FBBF24",
                        closeDelayMs = 2000L
                    )
                }
                is StampSubmitResult.Failed -> {
                    if (result.fallbackToWebView && !BackgroundAuthHelper.isCredentialBlocked(this@QuickStampActivity)) {
                        statusText.text = if (en) "Opening time stamping…" else "Avataan työaikaleimaus…"
                        startHiddenStampingWebView(baseUrl, wantIn = wantIn, targetText = targetText)
                    } else {
                        showFinalState(
                            title = if (en) "Stamp failed" else "Leimaus epäonnistui",
                            subtitle = result.message,
                            badgeText = "!",
                            badgeFillHex = "#3B181E",
                            badgeStrokeHex = "#EF4444",
                            badgeTextHex = "#F87171",
                            closeDelayMs = 1700L
                        )
                    }
                }
            }
        }"""

    text = replace_once(
        text,
        old_quick_flow,
        new_quick_flow,
        "QuickStampActivity käyttää suoraa HTTP-pikaleimausta (WebView vain varapolkuna)"
    )

    old_amp = 'if (url.contains("amplitude.com") || url.endsWith(".css") || url.contains("/content/css/")) {'
    new_amp = 'if (url.contains("amplitude") || url.contains("eligibility.") || url.endsWith(".css") || url.contains("/content/css/")) {'
    text = replace_once(
        text,
        old_amp,
        new_amp,
        "QuickStampActivity varapolun amplitude- ja eligibility-esto"
    )

    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_main_activity(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    # 1. Kentät: tukee sekä v1 (alkuperäinen) että v3 (Vaiheet 1-3)
    old_fields_v1 = """    private lateinit var webView: WebView
    private lateinit var bannerDemoMode: TextView
    private lateinit var btnNavStamp: Button
    private lateinit var btnNavRequests: Button
    private lateinit var btnNavShifts: Button
    private lateinit var btnNavSettings: Button
    private lateinit var btnNavClose: Button"""

    old_fields_v3 = """    private var webView: WebView? = null
    private lateinit var webViewHost: android.widget.LinearLayout
    private lateinit var webOverlayHeader: android.widget.LinearLayout
    private lateinit var btnWebOverlayBack: Button
    private lateinit var txtWebOverlayTitle: TextView
    private lateinit var webViewSlot: FrameLayout
    private lateinit var nativeShiftsContainer: FrameLayout
    private lateinit var nativeRequestsContainer: FrameLayout
    private var nativeShiftsView: NativeShiftsView? = null
    private var nativeRequestsView: NativeRequestsView? = null
    private var isWebOverlayOpen: Boolean = false
    private var pendingOverlayUrl: String? = null

    private lateinit var bannerDemoMode: TextView"""

    new_fields_v4 = """    private var webView: WebView? = null
    private lateinit var webViewHost: android.widget.LinearLayout
    private lateinit var webOverlayHeader: android.widget.LinearLayout
    private lateinit var btnWebOverlayBack: Button
    private lateinit var txtWebOverlayTitle: TextView
    private lateinit var webViewSlot: FrameLayout
    private lateinit var nativeStampContainer: FrameLayout
    private lateinit var nativeShiftsContainer: FrameLayout
    private lateinit var nativeRequestsContainer: FrameLayout
    private var nativeStampView: NativeStampView? = null
    private var nativeShiftsView: NativeShiftsView? = null
    private var nativeRequestsView: NativeRequestsView? = null
    private var isWebOverlayOpen: Boolean = false
    private var pendingOverlayUrl: String? = null
    private var pendingOverlayAction: String? = null

    private lateinit var bannerDemoMode: TextView"""

    if new_fields_v4 in text:
        print("  [OK - jo sovellettu] Laiska WebView ja kaikkien 3 natiivisäiliön kentät")
    elif old_fields_v3 in text:
        text = replace_once(text, old_fields_v3, new_fields_v4, "Lisätty nativeStampContainer, nativeStampView ja pendingOverlayAction")
    else:
        text = replace_once(
            text,
            old_fields_v1,
            new_fields_v4 + "\n    private lateinit var btnNavStamp: Button\n    private lateinit var btnNavRequests: Button\n    private lateinit var btnNavShifts: Button\n    private lateinit var btnNavSettings: Button\n    private lateinit var btnNavClose: Button",
            "Laiska WebView ja kaikkien 3 natiivisäiliön kentät"
        )

    # 2. onCreate
    old_oncreate_v1 = """        webView = findViewById(R.id.webView)
        bannerDemoMode = findViewById(R.id.bannerDemoMode)
        btnNavStamp = findViewById(R.id.btnNavStamp)
        btnNavRequests = findViewById(R.id.btnNavRequests)
        btnNavShifts = findViewById(R.id.btnNavShifts)
        btnNavSettings = findViewById(R.id.btnNavSettings)
        btnNavClose = findViewById(R.id.btnNavClose)

        setupWebView()
        setupBottomBar()
        setupBackNavigation()
        handleIncomingIntent(intent)

        // Näytetään heti käynnistyksessä splash-ruutu "Kirjaudutaan..."
        startSnapshotTransition()

        if (intent?.getBooleanExtra("OPEN_REQUESTS", false) == true) {
            intent.removeExtra("OPEN_REQUESTS")
            navigateToTab(Tab.REQUESTS)
        } else {
            navigateToTab(Tab.STAMP)
        }"""

    old_oncreate_v3 = """        webViewHost = findViewById(R.id.webViewHost)
        webOverlayHeader = findViewById(R.id.webOverlayHeader)
        btnWebOverlayBack = findViewById(R.id.btnWebOverlayBack)
        txtWebOverlayTitle = findViewById(R.id.txtWebOverlayTitle)
        webViewSlot = findViewById(R.id.webViewSlot)
        nativeShiftsContainer = findViewById(R.id.nativeShiftsContainer)
        nativeRequestsContainer = findViewById(R.id.nativeRequestsContainer)"""

    new_oncreate_v4_head = """        webViewHost = findViewById(R.id.webViewHost)
        webOverlayHeader = findViewById(R.id.webOverlayHeader)
        btnWebOverlayBack = findViewById(R.id.btnWebOverlayBack)
        txtWebOverlayTitle = findViewById(R.id.txtWebOverlayTitle)
        webViewSlot = findViewById(R.id.webViewSlot)
        nativeStampContainer = findViewById(R.id.nativeStampContainer)
        nativeShiftsContainer = findViewById(R.id.nativeShiftsContainer)
        nativeRequestsContainer = findViewById(R.id.nativeRequestsContainer)"""

    new_oncreate_v4_full = new_oncreate_v4_head + """

        bannerDemoMode = findViewById(R.id.bannerDemoMode)
        btnNavStamp = findViewById(R.id.btnNavStamp)
        btnNavRequests = findViewById(R.id.btnNavRequests)
        btnNavShifts = findViewById(R.id.btnNavShifts)
        btnNavSettings = findViewById(R.id.btnNavSettings)
        btnNavClose = findViewById(R.id.btnNavClose)

        btnWebOverlayBack.setOnClickListener {
            closeWebOverlay(refreshNative = true)
        }

        setupBottomBar()
        setupBackNavigation()
        handleIncomingIntent(intent)

        if (intent?.getBooleanExtra("OPEN_REQUESTS", false) == true) {
            intent.removeExtra("OPEN_REQUESTS")
            navigateToTab(Tab.REQUESTS)
        } else {
            navigateToTab(Tab.STAMP)
        }"""

    if new_oncreate_v4_head in text:
        print("  [OK - jo sovellettu] onCreate alustaa nativeStampContainerin")
    elif old_oncreate_v3 in text:
        text = replace_once(text, old_oncreate_v3, new_oncreate_v4_head, "onCreate alustaa nativeStampContainerin")
    else:
        text = replace_once(text, old_oncreate_v1, new_oncreate_v4_full, "onCreate alustaa natiivisäiliöt ja jättää WebView:n laiskaksi")

    # 3. ensureWebView / ensureNative*View / openWebOverlayUrl / closeWebOverlay
    old_resume_v1 = """    private fun resolveResumeUrl(baseUrl: String): String {
        return when {
            pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> "$baseUrl/WorktimeStamping"
            pendingAction == Action.SYNC_CALENDAR -> "$baseUrl/Calendar/Month"
            currentTab == Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
            currentTab == Tab.SHIFTS -> "$baseUrl/Calendar/Month"
            else -> "$baseUrl/WorktimeStamping"
        }
    }"""

    old_overlay_methods_v3 = """    private fun ensureNativeShiftsView(): NativeShiftsView {
        nativeShiftsView?.let { return it }
        val v = NativeShiftsView(
            context = this,
            scope = scope,
            onOpenWebUrl = { url, title -> openWebOverlayUrl(url, title) }
        )
        nativeShiftsContainer.removeAllViews()
        nativeShiftsContainer.addView(
            v,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        nativeShiftsView = v
        return v
    }

    private fun ensureNativeRequestsView(): NativeRequestsView {
        nativeRequestsView?.let { return it }
        val v = NativeRequestsView(
            context = this,
            scope = scope,
            onOpenWebUrl = { url, title -> openWebOverlayUrl(url, title) }
        )
        nativeRequestsContainer.removeAllViews()
        nativeRequestsContainer.addView(
            v,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        nativeRequestsView = v
        return v
    }

    private fun openWebOverlayUrl(url: String, title: String) {
        val baseUrl = getBaseUrl()
        val en = DemoModeHelper.isEnglish(this)
        if (baseUrl.isBlank()) {
            Toast.makeText(
                this,
                if (en) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista",
                Toast.LENGTH_LONG
            ).show()
            return
        }
        isWebOverlayOpen = true
        pendingOverlayUrl = url
        dashboardRedirectCount = 0
        isAutoSubmittingLogin = false
        val token = ++navigationToken
        navigateJob?.cancel()

        btnWebOverlayBack.text = if (en) "← Back" else "← Takaisin"
        txtWebOverlayTitle.text = title
        webOverlayHeader.visibility = View.VISIBLE
        nativeShiftsContainer.visibility = View.GONE
        nativeRequestsContainer.visibility = View.GONE
        webViewHost.visibility = View.VISIBLE

        val wv = ensureWebView()
        startSnapshotTransition {
            if (token != navigationToken) return@startSnapshotTransition
            if (!NumeronApiClient.isSessionLikelyValid(this, baseUrl, isAutoStamping = false)) {
                navigateJob = scope.launch {
                    try {
                        BackgroundAuthHelper.ensureAuthenticatedSession(this@MainActivity)
                    } catch (_: Exception) {
                    }
                    if (token == navigationToken && isWebOverlayOpen && !isFinishing && !isDestroyed) {
                        wv.stopLoading()
                        wv.loadUrl(url)
                    }
                }
            } else {
                wv.stopLoading()
                wv.loadUrl(url)
            }
        }
    }

    private fun closeWebOverlay(refreshNative: Boolean) {
        isWebOverlayOpen = false
        pendingOverlayUrl = null
        isAutoSubmittingLogin = false
        endSnapshotTransition()
        webOverlayHeader.visibility = View.GONE
        webView?.stopLoading()

        when (currentTab) {
            Tab.SHIFTS -> {
                webViewHost.visibility = View.GONE
                nativeRequestsContainer.visibility = View.GONE
                nativeShiftsContainer.visibility = View.VISIBLE
                if (refreshNative) {
                    ensureNativeShiftsView().refreshFromCacheAndNetwork()
                }
            }
            Tab.REQUESTS -> {
                webViewHost.visibility = View.GONE
                nativeShiftsContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.VISIBLE
                if (refreshNative) {
                    ensureNativeRequestsView().refreshAfterWebEdit()
                }
            }
            Tab.STAMP -> {
                nativeShiftsContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.GONE
                webViewHost.visibility = View.VISIBLE
            }
        }
    }"""

    new_overlay_methods_v4 = """    private fun ensureNativeStampView(): NativeStampView {
        nativeStampView?.let { return it }
        val v = NativeStampView(
            context = this,
            scope = scope,
            onOpenForgottenStampWeb = {
                val baseUrl = getBaseUrl()
                val en = DemoModeHelper.isEnglish(this)
                if (baseUrl.isNotBlank()) {
                    openWebOverlayUrl(
                        url = "$baseUrl/WorktimeStamping",
                        title = if (en) "Missing stamp" else "Puuttuva leimaus",
                        overlayAction = "FORGOTTEN"
                    )
                }
            },
            onOpenEditStampWeb = { rowId ->
                val baseUrl = getBaseUrl()
                val en = DemoModeHelper.isEnglish(this)
                if (baseUrl.isNotBlank()) {
                    openWebOverlayUrl(
                        url = "$baseUrl/WorktimeStamping",
                        title = if (en) "Edit stamp" else "Muokkaa leimausta",
                        overlayAction = "EDIT:$rowId"
                    )
                }
            },
            onOpenSettings = { btnNavSettings.performClick() }
        )
        nativeStampContainer.removeAllViews()
        nativeStampContainer.addView(
            v,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        nativeStampView = v
        return v
    }

    private fun ensureNativeShiftsView(): NativeShiftsView {
        nativeShiftsView?.let { return it }
        val v = NativeShiftsView(
            context = this,
            scope = scope,
            onOpenWebUrl = { url, title -> openWebOverlayUrl(url, title) }
        )
        nativeShiftsContainer.removeAllViews()
        nativeShiftsContainer.addView(
            v,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        nativeShiftsView = v
        return v
    }

    private fun ensureNativeRequestsView(): NativeRequestsView {
        nativeRequestsView?.let { return it }
        val v = NativeRequestsView(
            context = this,
            scope = scope,
            onOpenWebUrl = { url, title -> openWebOverlayUrl(url, title) }
        )
        nativeRequestsContainer.removeAllViews()
        nativeRequestsContainer.addView(
            v,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        nativeRequestsView = v
        return v
    }

    private fun openWebOverlayUrl(url: String, title: String, overlayAction: String? = null) {
        val baseUrl = getBaseUrl()
        val en = DemoModeHelper.isEnglish(this)
        if (baseUrl.isBlank()) {
            Toast.makeText(
                this,
                if (en) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista",
                Toast.LENGTH_LONG
            ).show()
            return
        }
        isWebOverlayOpen = true
        pendingOverlayUrl = url
        pendingOverlayAction = overlayAction
        dashboardRedirectCount = 0
        isAutoSubmittingLogin = false
        val token = ++navigationToken
        navigateJob?.cancel()

        btnWebOverlayBack.text = if (en) "← Back" else "← Takaisin"
        txtWebOverlayTitle.text = title
        webOverlayHeader.visibility = View.VISIBLE
        nativeStampContainer.visibility = View.GONE
        nativeShiftsContainer.visibility = View.GONE
        nativeRequestsContainer.visibility = View.GONE
        webViewHost.visibility = View.VISIBLE

        val wv = ensureWebView()
        startSnapshotTransition {
            if (token != navigationToken) return@startSnapshotTransition
            if (!NumeronApiClient.isSessionLikelyValid(this, baseUrl, isAutoStamping = false)) {
                navigateJob = scope.launch {
                    try {
                        BackgroundAuthHelper.ensureAuthenticatedSession(this@MainActivity)
                    } catch (_: Exception) {
                    }
                    if (token == navigationToken && isWebOverlayOpen && !isFinishing && !isDestroyed) {
                        wv.stopLoading()
                        wv.loadUrl(url)
                    }
                }
            } else {
                wv.stopLoading()
                wv.loadUrl(url)
            }
        }
    }

    private fun closeWebOverlay(refreshNative: Boolean) {
        isWebOverlayOpen = false
        pendingOverlayUrl = null
        pendingOverlayAction = null
        isAutoSubmittingLogin = false
        endSnapshotTransition()
        webOverlayHeader.visibility = View.GONE
        webView?.stopLoading()
        webViewHost.visibility = View.GONE

        when (currentTab) {
            Tab.STAMP -> {
                nativeShiftsContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.GONE
                nativeStampContainer.visibility = View.VISIBLE
                if (refreshNative) {
                    ensureNativeStampView().refreshFromNetwork()
                }
            }
            Tab.SHIFTS -> {
                nativeStampContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.GONE
                nativeShiftsContainer.visibility = View.VISIBLE
                if (refreshNative) {
                    ensureNativeShiftsView().refreshFromCacheAndNetwork()
                }
            }
            Tab.REQUESTS -> {
                nativeStampContainer.visibility = View.GONE
                nativeShiftsContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.VISIBLE
                if (refreshNative) {
                    ensureNativeRequestsView().refreshAfterWebEdit()
                }
            }
        }
    }"""

    new_resume_v4_from_v1 = """    private fun resolveResumeUrl(baseUrl: String): String {
        val overlayUrl = pendingOverlayUrl
        return when {
            isWebOverlayOpen && !overlayUrl.isNullOrBlank() -> overlayUrl
            pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> "$baseUrl/WorktimeStamping"
            pendingAction == Action.SYNC_CALENDAR -> "$baseUrl/Calendar/Month"
            currentTab == Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
            currentTab == Tab.SHIFTS -> "$baseUrl/Calendar/Month"
            else -> "$baseUrl/WorktimeStamping"
        }
    }

    private fun ensureWebView(): WebView {
        webView?.let { return it }
        val wv = WebView(this)
        webViewSlot.removeAllViews()
        webViewSlot.addView(
            wv,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        webView = wv
        setupWebView(wv)
        return wv
    }

""" + new_overlay_methods_v4

    if "private fun ensureNativeStampView()" in text:
        print("  [OK - jo sovellettu] ensureNativeStampView ja overlay-hallinta")
    elif old_overlay_methods_v3 in text:
        text = replace_once(text, old_overlay_methods_v3, new_overlay_methods_v4, "Lisätty ensureNativeStampView ja päivitetty overlay-hallinta")
    else:
        text = replace_once(text, old_resume_v1, new_resume_v4_from_v1, "Lisätty ensureWebView, ensureNative*View ja open/closeWebOverlay")

    # 4. Transition overlay (jos alkuperäisestä v1:stä)
    old_overlay = """        rootContent.addView(overlay, FrameLayout.LayoutParams(webView.width, webView.height))
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

    private fun recycleSnapshotBitmap() {
        snapshotView?.setImageDrawable(null)
        snapshotView?.visibility = View.GONE
        try {
            snapshotBitmap?.let {
                if (!it.isRecycled) it.recycle()
            }
        } catch (_: Exception) {}
        snapshotBitmap = null
    }

    private fun startSnapshotTransition(onReady: (() -> Unit)? = null) {
        val overlay = ensureTransitionOverlay()
        overlay.animate().cancel()
        webView.removeCallbacks(transitionFallbackRunnable)
        webView.postDelayed(transitionFallbackRunnable, 6500L)

        if (!isTransitionActive) {
            isTransitionActive = true
            recycleSnapshotBitmap()

            if (webView.width > 0 && webView.height > 0 && webView.alpha > 0.5f) {
                try {
                    val bitmap = Bitmap.createBitmap(webView.width, webView.height, Bitmap.Config.RGB_565)
                    val canvas = Canvas(bitmap)
                    webView.draw(canvas)
                    snapshotBitmap = bitmap
                    snapshotView?.setImageBitmap(bitmap)
                    snapshotView?.visibility = View.VISIBLE
                } catch (_: Exception) {
                    recycleSnapshotBitmap()
                }
            }

            overlay.alpha = 1f
            overlay.visibility = View.VISIBLE
            webView.alpha = 0f
            webView.post { syncOverlayBoundsToWebView(overlay) }

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
        isTransitionActive = false"""

    new_overlay = """        rootContent.addView(overlay, FrameLayout.LayoutParams(webViewSlot.width, webViewSlot.height))
        syncOverlayBoundsToWebView(overlay)
        webViewSlot.post { syncOverlayBoundsToWebView(overlay) }
        transitionOverlay = overlay
        return overlay
    }

    private fun syncOverlayBoundsToWebView(overlay: FrameLayout) {
        if (webViewSlot.width <= 0 || webViewSlot.height <= 0) return
        val rootContent = findViewById<View>(android.R.id.content)
        val webLoc = IntArray(2)
        val rootLoc = IntArray(2)
        webViewSlot.getLocationInWindow(webLoc)
        rootContent.getLocationInWindow(rootLoc)

        val lp = overlay.layoutParams as FrameLayout.LayoutParams
        lp.width = webViewSlot.width
        lp.height = webViewSlot.height
        lp.leftMargin = webLoc[0] - rootLoc[0]
        lp.topMargin = webLoc[1] - rootLoc[1]
        overlay.layoutParams = lp
    }

    private fun recycleSnapshotBitmap() {
        snapshotView?.setImageDrawable(null)
        snapshotView?.visibility = View.GONE
        try {
            snapshotBitmap?.let {
                if (!it.isRecycled) it.recycle()
            }
        } catch (_: Exception) {}
        snapshotBitmap = null
    }

    private fun startSnapshotTransition(onReady: (() -> Unit)? = null) {
        val overlay = ensureTransitionOverlay()
        overlay.animate().cancel()
        webViewSlot.removeCallbacks(transitionFallbackRunnable)
        webViewSlot.postDelayed(transitionFallbackRunnable, 6500L)

        val wv = webView
        if (!isTransitionActive) {
            isTransitionActive = true
            recycleSnapshotBitmap()

            if (wv != null && wv.width > 0 && wv.height > 0 && wv.alpha > 0.5f && webViewHost.visibility == View.VISIBLE) {
                try {
                    val bitmap = Bitmap.createBitmap(wv.width, wv.height, Bitmap.Config.RGB_565)
                    val canvas = Canvas(bitmap)
                    wv.draw(canvas)
                    snapshotBitmap = bitmap
                    snapshotView?.setImageBitmap(bitmap)
                    snapshotView?.visibility = View.VISIBLE
                } catch (_: Exception) {
                    recycleSnapshotBitmap()
                }
            }

            overlay.alpha = 1f
            overlay.visibility = View.VISIBLE
            wv?.alpha = 0f
            webViewSlot.post { syncOverlayBoundsToWebView(overlay) }

            if (onReady != null) {
                webViewSlot.post { onReady() }
            }
        } else {
            onReady?.invoke()
        }
    }

    private fun endSnapshotTransition() {
        webViewSlot.removeCallbacks(transitionFallbackRunnable)
        webView?.alpha = 1f
        isTransitionActive = false"""

    text = replace_once(text, old_overlay, new_overlay, "Siirtymäverho sidottu webViewSlot-säiliöön")

    # 5. navigateToTab: KAIKKI 3 päävälilehteä (STAMP, REQUESTS, SHIFTS) natiiveja!
    old_nav_v1 = """    private fun navigateToTab(tab: Tab) {
        currentTab = tab
        dashboardRedirectCount = 0
        isAutoSubmittingLogin = false
        val token = ++navigationToken
        navigateJob?.cancel()
        updateDemoBanner()

        when (tab) {
            Tab.STAMP -> setActiveTab(btnNavStamp)
            Tab.REQUESTS -> setActiveTab(btnNavRequests)
            Tab.SHIFTS -> setActiveTab(btnNavShifts)
        }

        if (DemoModeHelper.isDemoEnabled(this)) {
            if (tab == Tab.SHIFTS) {
                DemoModeHelper.resetDemoCalendarMonth(this)
            }
            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition
                val html = when (tab) {
                    Tab.STAMP -> DemoModeHelper.getDemoStampingHtml(this)
                    Tab.REQUESTS -> DemoModeHelper.getDemoRequestsHtml(this)
                    Tab.SHIFTS -> DemoModeHelper.getDemoShiftsHtml(this)
                }
                webView.stopLoading()
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
            }
            val now = LocalDate.now()
            val url = when (tab) {
                Tab.STAMP -> "$baseUrl/WorktimeStamping"
                Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
                Tab.SHIFTS -> "$baseUrl/Calendar/Month?month=${now.monthValue}&year=${now.year}"
            }
            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition
                navigateJob?.cancel()
                val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                val lastSessionMs = prefs.getLong("last_valid_session_ms", 0L)
                val sessionAgeMs = System.currentTimeMillis() - lastSessionMs
                val existingCookies = CookieManager.getInstance().getCookie(baseUrl)
                val isAutoStamping = (pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT)
                val maxSessionAgeMs = if (isAutoStamping) 10L * 60 * 1000L else 4L * 60 * 60 * 1000L

                if (existingCookies.isNullOrBlank() || sessionAgeMs > maxSessionAgeMs) {
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
                } else {
                    webView.stopLoading()
                    webView.loadUrl(url)
                }
            }
        }
    }"""

    old_nav_v3 = """    private fun navigateToTab(tab: Tab) {
        currentTab = tab
        isWebOverlayOpen = false
        pendingOverlayUrl = null
        dashboardRedirectCount = 0
        isAutoSubmittingLogin = false
        val token = ++navigationToken
        navigateJob?.cancel()
        updateDemoBanner()

        when (tab) {
            Tab.STAMP -> setActiveTab(btnNavStamp)
            Tab.REQUESTS -> setActiveTab(btnNavRequests)
            Tab.SHIFTS -> setActiveTab(btnNavShifts)
        }

        if (tab == Tab.SHIFTS) {
            endSnapshotTransition()
            webView?.stopLoading()
            webOverlayHeader.visibility = View.GONE
            webViewHost.visibility = View.GONE
            nativeRequestsContainer.visibility = View.GONE
            nativeShiftsContainer.visibility = View.VISIBLE
            ensureNativeShiftsView().onShow(forceNetwork = false)
            return
        }

        if (tab == Tab.REQUESTS) {
            endSnapshotTransition()
            webView?.stopLoading()
            webOverlayHeader.visibility = View.GONE
            webViewHost.visibility = View.GONE
            nativeShiftsContainer.visibility = View.GONE
            nativeRequestsContainer.visibility = View.VISIBLE
            ensureNativeRequestsView().onShow(forceNetwork = false)
            return
        }

        nativeShiftsContainer.visibility = View.GONE
        nativeRequestsContainer.visibility = View.GONE
        webOverlayHeader.visibility = View.GONE
        webViewHost.visibility = View.VISIBLE
        val wv = ensureWebView()

        if (DemoModeHelper.isDemoEnabled(this)) {
            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition
                val html = DemoModeHelper.getDemoStampingHtml(this)
                wv.stopLoading()
                wv.loadDataWithBaseURL("https://demo.local/", html, "text/html", "UTF-8", null)
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
            }
            val url = "$baseUrl/WorktimeStamping"
            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition
                navigateJob?.cancel()
                val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                val isAutoStamping = (pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT)

                if (!NumeronApiClient.isSessionLikelyValid(this, baseUrl, isAutoStamping)) {
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
                                wv.stopLoading()
                                wv.loadUrl(url)
                            }
                        }
                    }
                } else {
                    wv.stopLoading()
                    wv.loadUrl(url)
                }
            }
        }
    }"""

    new_nav_v4 = """    private fun navigateToTab(tab: Tab) {
        currentTab = tab
        isWebOverlayOpen = false
        pendingOverlayUrl = null
        pendingOverlayAction = null
        dashboardRedirectCount = 0
        isAutoSubmittingLogin = false
        navigationToken++
        navigateJob?.cancel()
        updateDemoBanner()

        when (tab) {
            Tab.STAMP -> setActiveTab(btnNavStamp)
            Tab.REQUESTS -> setActiveTab(btnNavRequests)
            Tab.SHIFTS -> setActiveTab(btnNavShifts)
        }

        endSnapshotTransition()
        webView?.stopLoading()
        webOverlayHeader.visibility = View.GONE
        webViewHost.visibility = View.GONE

        when (tab) {
            Tab.STAMP -> {
                nativeShiftsContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.GONE
                nativeStampContainer.visibility = View.VISIBLE
                val stampView = ensureNativeStampView()
                if (pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT) {
                    val wantIn = (pendingAction == Action.STAMP_IN)
                    pendingAction = Action.NONE
                    stampView.performAutoStamp(wantIn) {
                        if (!isFinishing && !isDestroyed) finishAndRemoveTask()
                    }
                } else {
                    stampView.onShow(forceNetwork = false)
                }
            }
            Tab.SHIFTS -> {
                nativeStampContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.GONE
                nativeShiftsContainer.visibility = View.VISIBLE
                ensureNativeShiftsView().onShow(forceNetwork = false)
            }
            Tab.REQUESTS -> {
                nativeStampContainer.visibility = View.GONE
                nativeShiftsContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.VISIBLE
                ensureNativeRequestsView().onShow(forceNetwork = false)
            }
        }
    }"""

    text = replace_any(
        text,
        [old_nav_v3, old_nav_v1],
        new_nav_v4,
        "navigateToTab käyttää natiiveja Leimaus-, Vuorot- ja Toiveet-näkymiä (WebView ei käynnisty arjessa)"
    )

    # 6. setupBackNavigation
    old_back_v1 = """    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(
            this,
            object : androidx.activity.OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    if (::webView.isInitialized && webView.canGoBack()) {
                        startSnapshotTransition()
                        webView.goBack()
                    } else {
                        isEnabled = false
                        onBackPressedDispatcher.onBackPressed()
                    }
                }
            }
        )
    }"""

    old_back_v3 = """    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(
            this,
            object : androidx.activity.OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    if (isWebOverlayOpen) {
                        closeWebOverlay(refreshNative = true)
                        return
                    }
                    val wv = webView
                    if (currentTab == Tab.STAMP && wv != null && wv.canGoBack()) {
                        startSnapshotTransition()
                        wv.goBack()
                    } else {
                        isEnabled = false
                        onBackPressedDispatcher.onBackPressed()
                    }
                }
            }
        )
    }"""

    new_back_v4 = """    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(
            this,
            object : androidx.activity.OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    if (isWebOverlayOpen) {
                        closeWebOverlay(refreshNative = true)
                        return
                    }
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        )
    }"""

    text = replace_any(
        text,
        [old_back_v3, old_back_v1],
        new_back_v4,
        "Takaisin-näppäin sulkee lomake-overlayn ja palaa natiivinäkymään"
    )

    # 7. startCalendarSync WebView-varapolku
    old_sync_fb = """                pendingAction = Action.SYNC_CALENDAR
                syncStep = 0
                collectedCalendarHtml.clear()
                webView.loadUrl(urls[0])"""

    new_sync_fb = """                pendingAction = Action.SYNC_CALENDAR
                syncStep = 0
                collectedCalendarHtml.clear()
                ensureWebView().loadUrl(urls[0])"""

    text = replace_once(text, old_sync_fb, new_sync_fb, "startCalendarSync varapolku käyttää ensureWebView()")

    # 8. setupWebView(wv: WebView)
    old_setup_wv = """    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        webView.setBackgroundColor(Color.parseColor("#0F1722"))
        (webView.parent as? View)?.setBackgroundColor(Color.parseColor("#0F1722"))

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            userAgentString = WebSettings.getDefaultUserAgent(this@MainActivity)
        }
        webView.webChromeClient = android.webkit.WebChromeClient()

        webView.addJavascriptInterface(
            DemoModeHelper.DemoJsBridge(
                context = this,
                onReloadNeeded = { runOnUiThread { navigateToTab(currentTab) } },
                onSyncRequested = { runOnUiThread { startCalendarSync() } },
                onManageChangesRequested = { runOnUiThread { CalendarChangeTracker.showManageChangesDialog(this) } }
            ),
            "DemoBridge"
        )

        webView.addJavascriptInterface(
            object {
                @android.webkit.JavascriptInterface
                fun onSessionExpired() {
                    runOnUiThread {
                        handleWebSessionExpired()
                    }
                }

                @android.webkit.JavascriptInterface
                fun onSessionExpiringSoon() {
                    runOnUiThread {
                        handleWebSessionExpiringSoon()
                    }
                }
            },
            "SessionBridge"
        )

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)

        webView.webViewClient = object : WebViewClient() {"""

    new_setup_wv = """    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView(wv: WebView) {
        wv.setBackgroundColor(Color.parseColor("#0F1722"))
        (wv.parent as? View)?.setBackgroundColor(Color.parseColor("#0F1722"))

        wv.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            userAgentString = WebSettings.getDefaultUserAgent(this@MainActivity)
        }
        wv.webChromeClient = android.webkit.WebChromeClient()

        wv.addJavascriptInterface(
            DemoModeHelper.DemoJsBridge(
                context = this,
                onReloadNeeded = { runOnUiThread { navigateToTab(currentTab) } },
                onSyncRequested = { runOnUiThread { startCalendarSync() } },
                onManageChangesRequested = { runOnUiThread { CalendarChangeTracker.showManageChangesDialog(this) } }
            ),
            "DemoBridge"
        )

        wv.addJavascriptInterface(
            object {
                @android.webkit.JavascriptInterface
                fun onSessionExpired() {
                    runOnUiThread {
                        handleWebSessionExpired()
                    }
                }

                @android.webkit.JavascriptInterface
                fun onSessionExpiringSoon() {
                    runOnUiThread {
                        handleWebSessionExpiringSoon()
                    }
                }
            },
            "SessionBridge"
        )

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(wv, true)

        wv.webViewClient = object : WebViewClient() {"""

    text = replace_once(text, old_setup_wv, new_setup_wv, "setupWebView(wv) alustaa laiskasti luodun WebView:n")

    # 9. shouldOverrideUrlLoading
    old_override = """                    if (isInternal) {
                        if (request?.isForMainFrame == true &&
                            url.contains("/InfraDashboard", ignoreCase = true) &&
                            dashboardRedirectCount < 2
                        ) {
                            dashboardRedirectCount++
                            startSnapshotTransition()
                            view?.loadUrl(resolveResumeUrl(getBaseUrl()))
                            return true
                        }
                        startSnapshotTransition()
                        return false
                    }"""

    new_override = """                    if (isInternal) {
                        if (request?.isForMainFrame == true &&
                            isWebOverlayOpen &&
                            pendingAction != Action.SYNC_CALENDAR &&
                            (url.contains("/PersonRequests/List", ignoreCase = true) ||
                                url.contains("/Calendar/Month", ignoreCase = true))
                        ) {
                            closeWebOverlay(refreshNative = true)
                            return true
                        }
                        if (request?.isForMainFrame == true &&
                            url.contains("/InfraDashboard", ignoreCase = true) &&
                            dashboardRedirectCount < 2
                        ) {
                            dashboardRedirectCount++
                            startSnapshotTransition()
                            view?.loadUrl(resolveResumeUrl(getBaseUrl()))
                            return true
                        }
                        startSnapshotTransition()
                        return false
                    }"""

    text = replace_once(text, old_override, new_override, "Lomake-overlay sulkeutuu automaattisesti paluussa listaan/kalenteriin")

    # 10. shouldInterceptRequest eligibility-esto
    old_amp = '                if (url.contains("amplitude")) {'
    new_amp = '                if (url.contains("amplitude") || url.contains("eligibility.")) {'
    text = replace_once(text, old_amp, new_amp, "Estetty myös eligibility.-seurantakutsu")

    # 11. onPageFinished: tukee sekä v1 että v3 + lisää puuttuvan/muokattavan leimauksen automaattiavauksen overlayssa
    old_finished_v1 = """                injectDarkTheme(view, forceDomInit = true)
                CookieManager.getInstance().flush()
                if (!url.contains("/Login/", ignoreCase = true) && !url.contains("/InfraDashboard", ignoreCase = true)) {
                    dashboardRedirectCount = 0
                }
                if (!url.contains("/Login/", ignoreCase = true)) {
                    webLoginAttemptFingerprint = ""
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                }

                when {
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
                    }
                    url.contains("/InfraDashboard", ignoreCase = true) && dashboardRedirectCount < 2 -> {
                        dashboardRedirectCount++
                        startSnapshotTransition()
                        webView.loadUrl(resolveResumeUrl(getBaseUrl()))
                        return
                    }
                    url.contains("/WorktimeStamping", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        setActiveTab(btnNavStamp)
                        handleStampingPage()
                    }
                    url.contains("/PersonRequests", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        setActiveTab(btnNavRequests)
                    }
                    url.contains("/Calendar", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        setActiveTab(btnNavShifts)
                        handleCalendarPage()
                    }
                    pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> {
                        isAutoSubmittingLogin = false
                        webView.loadUrl("${getBaseUrl()}/WorktimeStamping")
                        return
                    }
                    else -> {
                        isAutoSubmittingLogin = false
                    }
                }"""

    old_finished_v3_stamp = """                    url.contains("/WorktimeStamping", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        if (!isWebOverlayOpen) setActiveTab(btnNavStamp)
                        handleStampingPage()
                    }"""

    new_finished_v4_stamp = """                    url.contains("/WorktimeStamping", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        if (!isWebOverlayOpen) setActiveTab(btnNavStamp)
                        val action = pendingOverlayAction
                        if (isWebOverlayOpen && action != null) {
                            pendingOverlayAction = null
                            view?.postDelayed({
                                if (action == "FORGOTTEN") {
                                    view.evaluateJavascript(
                                        "(function(){ try { if (typeof window.reloadForgottenStampPane === 'function') window.reloadForgottenStampPane(); if (typeof window.openForgottenStampPane === 'function') window.openForgottenStampPane(); var b = document.getElementById('forgottenStampButton'); if (b) b.click(); } catch(e){} })();",
                                        null
                                    )
                                } else if (action.startsWith("EDIT:")) {
                                    val rowId = action.removePrefix("EDIT:").filter { it.isDigit() }
                                    if (rowId.isNotEmpty()) {
                                        view.evaluateJavascript(
                                            "(function(){ try { if (typeof window.getStampEditModal === 'function') window.getStampEditModal($rowId); } catch(e){} })();",
                                            null
                                        )
                                    }
                                }
                            }, 250L)
                        } else {
                            handleStampingPage()
                        }
                    }"""

    new_finished_v4_full = """                if (isWebOverlayOpen &&
                    pendingAction != Action.SYNC_CALENDAR &&
                    (url.contains("/PersonRequests/List", ignoreCase = true) ||
                        url.contains("/Calendar/Month", ignoreCase = true))
                ) {
                    closeWebOverlay(refreshNative = true)
                    return
                }

                injectDarkTheme(view, forceDomInit = true)
                if (url.contains("/Login/", ignoreCase = true) ||
                    url.contains("/WorktimeStamping", ignoreCase = true) ||
                    isAutoSubmittingLogin
                ) {
                    CookieManager.getInstance().flush()
                }
                if (!url.contains("/Login/", ignoreCase = true) && !url.contains("/InfraDashboard", ignoreCase = true)) {
                    dashboardRedirectCount = 0
                }
                if (!url.contains("/Login/", ignoreCase = true)) {
                    webLoginAttemptFingerprint = ""
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                }

                when {
                    url.contains("/Login/LogOff", ignoreCase = true) -> {
                        isAutoSubmittingLogin = true
                        startSnapshotTransition()
                        wv.loadUrl("${getBaseUrl()}/Login/Login")
                        return
                    }
                    url.contains("/Login/Login", ignoreCase = true) -> {
                        isAutoSubmittingLogin = true
                        startSnapshotTransition()
                        handleAutoLogin()
                        return
                    }
                    url.contains("/InfraDashboard", ignoreCase = true) && dashboardRedirectCount < 2 -> {
                        dashboardRedirectCount++
                        startSnapshotTransition()
                        wv.loadUrl(resolveResumeUrl(getBaseUrl()))
                        return
                    }
""" + new_finished_v4_stamp + """
                    url.contains("/PersonRequests", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        if (!isWebOverlayOpen) setActiveTab(btnNavRequests)
                    }
                    url.contains("/Calendar", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        if (!isWebOverlayOpen) setActiveTab(btnNavShifts)
                        handleCalendarPage()
                    }
                    pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> {
                        isAutoSubmittingLogin = false
                        wv.loadUrl("${getBaseUrl()}/WorktimeStamping")
                        return
                    }
                    else -> {
                        isAutoSubmittingLogin = false
                    }
                }"""

    if 'if (action == "FORGOTTEN")' in text:
        print("  [OK - jo sovellettu] onPageFinished overlay-toiminnot (FORGOTTEN / EDIT)")
    elif old_finished_v3_stamp in text:
        text = replace_once(text, old_finished_v3_stamp, new_finished_v4_stamp, "onPageFinished puuttuvan/muokattavan leimauksen automaattiavaus")
    else:
        text = replace_once(text, old_finished_v1, new_finished_v4_full, "onPageFinished päivitetty overlay-paluulle, automaattiavaukselle ja rajatulle flush-kutsulle")

    # 12. Null-turvalliset WebView-kutsut (jos v1:stä)
    old_demo_stamp = """            if (wantIn != currentlyIn) {
                webView.evaluateJavascript("DemoBridge.toggleStamp()", null)
                webView.postDelayed({ finishAndRemoveTask() }, 1200L)
            } else {
                val en = DemoModeHelper.isEnglish(this)
                val stateStr = if (en) (if (wantIn) "In" else "Out") else (if (wantIn) "Sisään" else "Ulos")
                val msg = if (en) "Demo mode: Already clocked $stateStr" else "Demotila: Olet jo leimannut tilaan $stateStr"
                Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
                webView.postDelayed({ finishAndRemoveTask() }, 1200L)
            }"""

    new_demo_stamp = """            if (wantIn != currentlyIn) {
                webView?.evaluateJavascript("DemoBridge.toggleStamp()", null)
                webViewSlot.postDelayed({ finishAndRemoveTask() }, 1200L)
            } else {
                val en = DemoModeHelper.isEnglish(this)
                val stateStr = if (en) (if (wantIn) "In" else "Out") else (if (wantIn) "Sisään" else "Ulos")
                val msg = if (en) "Demo mode: Already clocked $stateStr" else "Demotila: Olet jo leimannut tilaan $stateStr"
                Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
                webViewSlot.postDelayed({ finishAndRemoveTask() }, 1200L)
            }"""

    text = replace_once(text, old_demo_stamp, new_demo_stamp, "handleDemoAutoStamp null-turvalliseksi")

    old_autologin_eval = """        webView.evaluateJavascript(js) { res ->
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
        }"""

    new_autologin_eval = """        val wv = webView ?: return
        wv.evaluateJavascript(js) { res ->
            if (res?.contains("SUBMITTED") == true) {
                webLoginAttemptFingerprint = fp
            } else if (res?.contains("WAITING") == true) {
                if (attempt < 15) {
                    wv.postDelayed({ handleAutoLogin(attempt + 1) }, 300L)
                } else {
                    isAutoSubmittingLogin = false
                    endSnapshotTransition()
                }
            }
        }"""

    text = replace_once(text, old_autologin_eval, new_autologin_eval, "handleAutoLogin null-turvalliseksi")

    old_expired_load = """                    val targetUrl = resolveResumeUrl(baseUrl)
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
                }"""

    new_expired_load = """                    val targetUrl = resolveResumeUrl(baseUrl)
                    ensureWebView().loadUrl(targetUrl)
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
                    ensureWebView().loadUrl("$baseUrl/Login/Login")
                }"""

    text = replace_once(text, old_expired_load, new_expired_load, "handleWebSessionExpired käyttää ensureWebView()")

    old_stamp_page = """        webView.evaluateJavascript(StampingWebHelper.buildClickStampJs(wantIn)) { rawResult ->
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
        }"""

    new_stamp_page = """        val wv = webView ?: return
        wv.evaluateJavascript(StampingWebHelper.buildClickStampJs(wantIn)) { rawResult ->
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
                    wv.postDelayed({ finishAndRemoveTask() }, 1500L)
                }
                status == "NO_BUTTON" && attempt < 10 -> {
                    wv.postDelayed({ handleStampingPage(attempt + 1) }, 300L)
                }
                else -> {
                    pendingAction = Action.NONE
                }
            }
        }"""

    text = replace_once(text, old_stamp_page, new_stamp_page, "handleStampingPage null-turvalliseksi")

    old_verify = """        webView.postDelayed({
            if (isFinishing || isDestroyed) return@postDelayed
            webView.evaluateJavascript(StampingWebHelper.buildVerifyStampJs()) { rawResult ->"""

    new_verify = """        val wv = webView ?: return
        wv.postDelayed({
            if (isFinishing || isDestroyed) return@postDelayed
            wv.evaluateJavascript(StampingWebHelper.buildVerifyStampJs()) { rawResult ->"""

    text = replace_once(text, old_verify, new_verify, "verifyStampAndClose alku null-turvalliseksi")

    old_verify_close = """                    inFlightStampAction = Action.NONE
                    CookieManager.getInstance().flush()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)"""

    new_verify_close = """                    inFlightStampAction = Action.NONE
                    CookieManager.getInstance().flush()
                    wv.postDelayed({ finishAndRemoveTask() }, 1500L)"""

    text = replace_once(text, old_verify_close, new_verify_close, "verifyStampAndClose loppu null-turvalliseksi")

    old_handle_cal = """    private fun handleCalendarPage() {
        if (pendingAction != Action.SYNC_CALENDAR) return

        webView.evaluateJavascript("document.documentElement.outerHTML") { rawHtml ->
            if (rawHtml == null || rawHtml == "null") {
                pendingAction = Action.NONE
                collectedCalendarHtml.clear()
                return@evaluateJavascript
            }
            val unescapedHtml = try {
                JSONTokener(rawHtml).nextValue() as? String
            } catch (_: Exception) {
                null
            } ?: run {
                pendingAction = Action.NONE
                collectedCalendarHtml.clear()
                return@evaluateJavascript
            }
            collectedCalendarHtml.add(unescapedHtml)

            if (syncStep == 0) {
                syncStep = 1
                val nextMonth = LocalDate.now().plusMonths(1)
                val baseUrl = getBaseUrl()
                webView.loadUrl("$baseUrl/Calendar/Month?month=${nextMonth.monthValue}&year=${nextMonth.year}")
            } else {
                pendingAction = Action.NONE
                val pagesToParse = collectedCalendarHtml.toList()
                collectedCalendarHtml.clear()
                processSyncedCalendarPages(pagesToParse)
            }
        }
    }"""

    new_handle_cal = """    private fun handleCalendarPage() {
        if (pendingAction != Action.SYNC_CALENDAR) return
        val wv = webView ?: return

        wv.evaluateJavascript("document.documentElement.outerHTML") { rawHtml ->
            if (rawHtml == null || rawHtml == "null") {
                pendingAction = Action.NONE
                collectedCalendarHtml.clear()
                return@evaluateJavascript
            }
            val unescapedHtml = try {
                JSONTokener(rawHtml).nextValue() as? String
            } catch (_: Exception) {
                null
            } ?: run {
                pendingAction = Action.NONE
                collectedCalendarHtml.clear()
                return@evaluateJavascript
            }
            collectedCalendarHtml.add(unescapedHtml)

            if (syncStep == 0) {
                syncStep = 1
                val nextMonth = LocalDate.now().plusMonths(1)
                val baseUrl = getBaseUrl()
                wv.loadUrl("$baseUrl/Calendar/Month?month=${nextMonth.monthValue}&year=${nextMonth.year}")
            } else {
                pendingAction = Action.NONE
                val pagesToParse = collectedCalendarHtml.toList()
                collectedCalendarHtml.clear()
                processSyncedCalendarPages(pagesToParse)
            }
        }
    }"""

    text = replace_once(text, old_handle_cal, new_handle_cal, "handleCalendarPage null-turvalliseksi")

    old_proc_sync = """            val parsedPages = pagesToParse.map { NumeronParser.parseCalendarHtml(it) }"""
    new_proc_sync = """            pagesToParse.forEach { html ->
                NumeronParser.parseMonthForDisplay(html)?.let { displayData ->
                    NumeronApiClient.saveMonthDisplayCache(this@MainActivity, displayData)
                }
            }
            val parsedPages = pagesToParse.map { NumeronParser.parseCalendarHtml(it) }"""
    text = replace_once(text, old_proc_sync, new_proc_sync, "Manuaalisynkka päivittää natiivikalenterin kuukausivälimuistin")

    old_proc_ui = """            withContext(Dispatchers.Main) {
                if (isFinishing || isDestroyed) return@withContext
                val en = DemoModeHelper.isEnglish(this@MainActivity)"""
    new_proc_ui = """            withContext(Dispatchers.Main) {
                if (isFinishing || isDestroyed) return@withContext
                if (currentTab == Tab.SHIFTS && !isWebOverlayOpen) {
                    nativeShiftsView?.onShow(forceNetwork = false)
                } else if (currentTab == Tab.REQUESTS && !isWebOverlayOpen) {
                    nativeRequestsView?.refreshAfterWebEdit()
                }
                val en = DemoModeHelper.isEnglish(this@MainActivity)"""
    text = replace_once(text, old_proc_ui, new_proc_ui, "Manuaalisynkka päivittää aktiivisen natiivinäkymän")

    old_life = """    override fun onPause() {
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
    }

    override fun onDestroy() {
        navigateJob?.cancel()
        webView.removeCallbacks(transitionFallbackRunnable)
        recycleSnapshotBitmap()
        try {
            CookieManager.getInstance().flush()
        } catch (_: Exception) {}
        try {
            (webView.parent as? ViewGroup)?.removeView(webView)
            webView.stopLoading()
            webView.destroy()
        } catch (_: Exception) {}
        scope.cancel()
        super.onDestroy()
    }"""

    new_life = """    override fun onPause() {
        try {
            webView?.onPause()
        } catch (_: Exception) {}
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        try {
            webView?.onResume()
        } catch (_: Exception) {}
    }

    override fun onDestroy() {
        navigateJob?.cancel()
        webViewSlot.removeCallbacks(transitionFallbackRunnable)
        recycleSnapshotBitmap()
        try {
            if (webView != null) {
                CookieManager.getInstance().flush()
            }
        } catch (_: Exception) {}
        try {
            webView?.let { wv ->
                (wv.parent as? ViewGroup)?.removeView(wv)
                wv.stopLoading()
                wv.destroy()
            }
            webView = null
        } catch (_: Exception) {}
        scope.cancel()
        super.onDestroy()
    }"""

    text = replace_once(text, old_life, new_life, "onPause/onResume/onDestroy null-turvallisiksi")

    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def main() -> int:
    changed = 0

    ma_path = find_file("MainActivity.kt")
    if ma_path is None:
        print("[VIRHE] MainActivity.kt ei löytynyt!")
        return 1

    kt_dir = ma_path.parent
    print(f"Kotlin-hakemisto: {kt_dir}")

    if write_new_file(kt_dir / "NumeronApiClient.kt", NUMERON_API_CLIENT_KT, "NumeronApiClient.kt"):
        changed += 1
    if write_new_file(kt_dir / "NativeStampView.kt", NATIVE_STAMP_VIEW_KT, "NativeStampView.kt"):
        changed += 1
    if write_new_file(kt_dir / "NativeShiftsView.kt", NATIVE_SHIFTS_VIEW_KT, "NativeShiftsView.kt"):
        changed += 1
    if write_new_file(kt_dir / "NativeRequestsView.kt", NATIVE_REQUESTS_VIEW_KT, "NativeRequestsView.kt"):
        changed += 1

    for filename, fn in [
        ("CalendarSyncHelper.kt", patch_calendar_sync_helper),
        ("BackgroundAuthHelper.kt", patch_background_auth_helper),
        ("NumeronParser.kt", patch_numeron_parser),
        ("activity_main.xml", patch_activity_main_xml),
        ("MainActivity.kt", patch_main_activity),
        ("QuickStampActivity.kt", patch_quick_stamp_activity),
        ("build.gradle.kts", patch_build_gradle),
    ]:
        p = find_file(filename)
        if p is None:
            print(f"[EI LÖYTYNYT] {filename}")
            continue
        print(f"Käsitellään: {p}")
        if fn(p):
            changed += 1

    print(f"\nValmis! Luotuja/muokattuja tiedostoja: {changed}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
