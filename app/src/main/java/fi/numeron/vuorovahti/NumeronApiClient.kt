package fi.numeron.vuorovahti

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.jsoup.Jsoup
import java.io.File
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

data class PersonRequestItem(
    val id: Int,
    val type: String,
    val dateFrom: LocalDate?,
    val dateTo: LocalDate?,
    val timeFromText: String,
    val timeToText: String,
    val info: String,
    val statusCode: Int,
    val statusDescription: String,
    val belongsToSeries: Boolean,
    val approvedBy: String,
    val approvedDateMs: Long?
)

data class RequestsFetchResult(
    val items: List<PersonRequestItem>?,
    val fromCache: Boolean = false,
    val errorMessage: String? = null
)

data class StampReasonCode(
    val id: Int,
    val label: String
)

data class StampHistoryRow(
    val rowId: String,
    val dayText: String,
    val timeText: String,
    val directionText: String,
    val isIn: Boolean,
    val typeText: String
)

data class StampingPageState(
    val shiftTimes: String,
    val shiftWorkplace: String,
    val shiftDetails: String,
    val nextDirection: String,
    val punchButtonText: String,
    val defaultReasonCode: Int,
    val reasonCodes: List<StampReasonCode>,
    val latestStamps: List<StampHistoryRow>,
    val hasMoreStamps: Boolean,
    val currentTake: Int,
    val verificationToken: String,
    val saveStampUrl: String,
    val validateStampSaveUrl: String,
    val getMoreStampsUrl: String,
    val fromCache: Boolean = false
)

sealed class StampSubmitResult {
    data class Success(
        val updatedState: StampingPageState?,
        val directionUsed: String,
        val serverMessage: String = ""
    ) : StampSubmitResult()

    data class AlreadyInDirection(val nextDirection: String) : StampSubmitResult()
    data class ValidationRejected(val message: String) : StampSubmitResult()
    data class Failed(val message: String, val fallbackToWebView: Boolean = false) : StampSubmitResult()
}

object NumeronApiClient {

    private val MAX_SESSION_REGEX = Regex("maxSessionTimeInMilliseconds\\s*=\\s*(\\d+)")
    private val DOTNET_DATE_REGEX = Regex("/Date\\((-?\\d+)\\)/")
    private const val MOBILE_UA =
        "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

    private data class SimpleHttpResponse(
        val statusCode: Int,
        val body: String,
        val location: String = ""
    )

    fun extractAndSaveMaxSessionTime(context: Context, html: String) {
        if (html.isEmpty()) return
        val match = MAX_SESSION_REGEX.find(html) ?: return
        val expiryMs = match.groupValues[1].toLongOrNull() ?: return
        val nowMs = System.currentTimeMillis()
        if (expiryMs > nowMs) {
            context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                .edit()
                .putLong("server_session_expiry_ms", expiryMs)
                .putLong("last_valid_session_ms", nowMs)
                .apply()
        }
    }

    fun isSessionLikelyValid(
        context: Context,
        baseUrl: String,
        isAutoStamping: Boolean = false
    ): Boolean {
        if (baseUrl.isBlank()) return false
        val existingCookies = SessionCookieStore.getCookieHeader(context, baseUrl)
        if (existingCookies.isNullOrBlank()) return false

        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val nowMs = System.currentTimeMillis()
        val serverExpiryMs = prefs.getLong("server_session_expiry_ms", 0L)
        if (serverExpiryMs > 0L) {
            val bufferMs = if (isAutoStamping) 15L * 60_000L else 10L * 60_000L
            return nowMs < (serverExpiryMs - bufferMs)
        }

        val lastSessionMs = prefs.getLong("last_valid_session_ms", 0L)
        val maxAgeMs = if (isAutoStamping) 10L * 60_000L else 4L * 60L * 60_000L
        return lastSessionMs > 0L && (nowMs - lastSessionMs) <= maxAgeMs
    }

    private fun resolveAbsoluteUrl(baseUrl: String, pathOrUrl: String): String {
        val clean = pathOrUrl.trim()
        if (clean.startsWith("http://", ignoreCase = true) || clean.startsWith("https://", ignoreCase = true)) {
            return clean
        }
        return baseUrl.trimEnd('/') + if (clean.startsWith("/")) clean else "/$clean"
    }

    private fun formEncode(params: List<Pair<String, String>>): String {
        return params.joinToString("&") { (k, v) ->
            "${URLEncoder.encode(k, "UTF-8")}=${URLEncoder.encode(v, "UTF-8")}"
        }
    }

    private fun executeAjaxPost(
        context: Context,
        baseUrl: String,
        urlString: String,
        body: String,
        accept: String,
        refererPath: String = "/WorktimeStamping"
    ): SimpleHttpResponse? {
        var conn: HttpURLConnection? = null
        return try {
            val cookies = SessionCookieStore.getCookieHeader(context, baseUrl)
            if (cookies.isNullOrBlank()) return null

            val origin = try {
                val u = URL(baseUrl)
                val portPart = if (u.port > 0 && u.port != u.defaultPort) ":${u.port}" else ""
                "${u.protocol}://${u.host}$portPart"
            } catch (_: Exception) {
                baseUrl.trimEnd('/')
            }

            conn = (URL(urlString).openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                instanceFollowRedirects = false
                setRequestProperty("Cookie", cookies)
                setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
                setRequestProperty("Accept", accept)
                setRequestProperty("X-Requested-With", "XMLHttpRequest")
                setRequestProperty("Origin", origin)
                setRequestProperty("Referer", resolveAbsoluteUrl(baseUrl, refererPath))
                setRequestProperty("User-Agent", MOBILE_UA)
                doOutput = true
                connectTimeout = 15_000
                readTimeout = 15_000
            }

            OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { writer ->
                writer.write(body)
                writer.flush()
            }

            val code = conn.responseCode
            val location = conn.getHeaderField("Location").orEmpty()
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()

            // Päivitetään mahdolliset Set-Cookie-otsikot natiiviin SessionCookieStoreen
            val setCookies = conn.headerFields
                .filterKeys { it != null && it.equals("Set-Cookie", ignoreCase = true) }
                .values
                .flatten()
            SessionCookieStore.mergeFromSetCookieHeaders(context, baseUrl, setCookies)

            SimpleHttpResponse(statusCode = code, body = text, location = location)
        } catch (_: Exception) {
            null
        } finally {
            conn?.disconnect()
        }
    }

    private fun executeAjaxGet(
        context: Context,
        baseUrl: String,
        urlString: String,
        refererPath: String = "/WorktimeStamping"
    ): SimpleHttpResponse? {
        var conn: HttpURLConnection? = null
        return try {
            val cookies = SessionCookieStore.getCookieHeader(context, baseUrl)
            if (cookies.isNullOrBlank()) return null

            conn = (URL(urlString).openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                instanceFollowRedirects = false
                setRequestProperty("Cookie", cookies)
                setRequestProperty("Accept", "text/html, */*; q=0.01")
                setRequestProperty("X-Requested-With", "XMLHttpRequest")
                setRequestProperty("Referer", resolveAbsoluteUrl(baseUrl, refererPath))
                setRequestProperty("User-Agent", MOBILE_UA)
                connectTimeout = 15_000
                readTimeout = 15_000
            }

            val code = conn.responseCode
            val location = conn.getHeaderField("Location").orEmpty()
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            SimpleHttpResponse(statusCode = code, body = text, location = location)
        } catch (_: Exception) {
            null
        } finally {
            conn?.disconnect()
        }
    }

    private fun isSessionExpiredResponse(resp: SimpleHttpResponse?): Boolean {
        if (resp == null) return false
        if (resp.statusCode == 401 || resp.statusCode == 403) return true
        if (resp.statusCode in 300..399 && resp.location.contains("/Login", ignoreCase = true)) return true
        if (resp.body.contains("id=\"LoginForm\"", ignoreCase = true)) return true
        return false
    }

    // =========================================================================
    // TYÖAIKALEIMAUS (Vaihe 4)
    // =========================================================================

    suspend fun fetchStampingState(
        context: Context,
        forceRefreshSession: Boolean = false
    ): StampingPageState? = withContext(Dispatchers.IO) {
        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) return@withContext null
        if (BackgroundAuthHelper.isCredentialBlocked(context)) return@withContext null

        if (forceRefreshSession) {
            if (!BackgroundAuthHelper.ensureAuthenticatedSession(context, forceRefresh = true)) {
                return@withContext null
            }
        }

        val url = "$baseUrl/WorktimeStamping"
        val html = BackgroundAuthHelper.fetchAuthenticatedPages(context, listOf(url))?.firstOrNull()
            ?: return@withContext null
        extractAndSaveMaxSessionTime(context, html)
        val parsed = parseStampingHtml(html) ?: return@withContext null
        saveCachedStampingState(context, parsed)
        parsed
    }

    suspend fun fetchMoreStamps(
        context: Context,
        take: Int,
        getMoreStampsUrlPath: String = "/WorktimeStamping/GetMoreStamps"
    ): Pair<List<StampHistoryRow>, Boolean>? = withContext(Dispatchers.IO) {
        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) return@withContext null
        val target = resolveAbsoluteUrl(baseUrl, getMoreStampsUrlPath) + "?take=$take"

        var resp = executeAjaxGet(context, baseUrl, target)
        if (isSessionExpiredResponse(resp)) {
            if (BackgroundAuthHelper.ensureAuthenticatedSession(context, forceRefresh = true)) {
                resp = executeAjaxGet(context, baseUrl, target)
            }
        }
        if (resp == null || resp.statusCode != 200 || resp.body.isBlank()) return@withContext null
        parseLatestStampsFragment(resp.body)
    }

    suspend fun performDirectStamp(
        context: Context,
        currentState: StampingPageState?,
        reasonCodeId: Int? = null,
        comment: String = "",
        expectedDirection: String? = null,
        onStatusUpdate: ((String) -> Unit)? = null
    ): StampSubmitResult = withContext(Dispatchers.IO) {
        val en = DemoModeHelper.isEnglish(context)
        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) {
            return@withContext StampSubmitResult.Failed(
                if (en) "Organization not configured" else "Organisaatiotunnus puuttuu"
            )
        }
        if (BackgroundAuthHelper.isCredentialBlocked(context)) {
            return@withContext StampSubmitResult.Failed(
                if (en) "Check username and password in Settings" else "Tarkista käyttäjätunnus ja salasana asetuksista"
            )
        }

        // Haetaan tuore tila jos sitä ei ole tai token puuttuu tai kyse on automaattileimauksesta
        var state = currentState
        if (state == null || state.verificationToken.isBlank() || state.fromCache || expectedDirection != null) {
            if (!isSessionLikelyValid(context, baseUrl, isAutoStamping = expectedDirection != null)) {
                onStatusUpdate?.invoke(if (en) "Signing in…" else "Kirjaudutaan sisään…")
                BackgroundAuthHelper.ensureAuthenticatedSession(context)
            }
            onStatusUpdate?.invoke(if (en) "Checking stamp status…" else "Haetaan leimaustilaa…")
            state = fetchStampingState(context, forceRefreshSession = false)
                ?: fetchStampingState(context, forceRefreshSession = true)
        }

        if (state == null) {
            return@withContext StampSubmitResult.Failed(
                if (en) "Could not load time stamping" else "Leimaussivun lataus epäonnistui",
                fallbackToWebView = true
            )
        }

        if (state.nextDirection != "IN" && state.nextDirection != "OUT") {
            return@withContext StampSubmitResult.Failed(
                if (en) "Could not detect stamp direction" else "Leimaussuuntaa ei tunnistettu",
                fallbackToWebView = true
            )
        }

        if (expectedDirection != null && !state.nextDirection.equals(expectedDirection, ignoreCase = true)) {
            return@withContext StampSubmitResult.AlreadyInDirection(state.nextDirection)
        }

        val eventType = state.nextDirection
        val effectiveReasonCode = reasonCodeId ?: state.defaultReasonCode
        val validateUrl = resolveAbsoluteUrl(baseUrl, state.validateStampSaveUrl)
        val saveUrl = resolveAbsoluteUrl(baseUrl, state.saveStampUrl)

        suspend fun attemptValidateAndSave(activeState: StampingPageState): Pair<StampSubmitResult?, Boolean> {
            val token = activeState.verificationToken
            if (token.isBlank()) {
                return StampSubmitResult.Failed(
                    if (en) "Security token missing" else "Turvatunniste puuttuu",
                    fallbackToWebView = true
                ) to false
            }

            // 1. ValidateStampSave (sama kutsu kuin jsWorktimeStampingissa)
            val validateBody = formEncode(
                listOf(
                    "__RequestVerificationToken" to token,
                    "eventType" to eventType,
                    "reasonCodeId" to effectiveReasonCode.toString(),
                    "forgottenStampTime" to "",
                    "stampComment" to comment,
                    "stampId" to "0"
                )
            )
            val valResp = executeAjaxPost(
                context = context,
                baseUrl = baseUrl,
                urlString = validateUrl,
                body = validateBody,
                accept = "application/json, text/javascript, */*; q=0.01"
            )
            if (isSessionExpiredResponse(valResp)) {
                return null to true
            }
            if (valResp == null || valResp.statusCode != 200) {
                return StampSubmitResult.Failed(
                    if (en) "Stamp validation failed" else "Leimauksen tarkistus epäonnistui",
                    fallbackToWebView = true
                ) to false
            }

            val trimmedVal = valResp.body.trim()
            if (trimmedVal.startsWith("{")) {
                try {
                    val obj = JSONObject(trimmedVal)
                    if (obj.has("success") && !obj.optBoolean("success", true)) {
                        val msg = obj.optString("message", "").trim()
                            .ifEmpty { if (en) "Stamping is not allowed right now." else "Leimaus ei ole juuri nyt sallittu." }
                        return StampSubmitResult.ValidationRejected(msg) to false
                    }
                } catch (_: Exception) {
                }
            }

            // 2. SaveStamp
            val dirLabel = if (en) {
                if (eventType == "IN") "In" else "Out"
            } else {
                if (eventType == "IN") "Sisään" else "Ulos"
            }
            onStatusUpdate?.invoke(if (en) "Sending stamp ($dirLabel)…" else "Lähetetään leimaus ($dirLabel)…")

            val saveBody = formEncode(
                listOf(
                    "__RequestVerificationToken" to token,
                    "eventType" to eventType,
                    "reasonCodeId" to effectiveReasonCode.toString(),
                    "stampComment" to comment
                )
            )
            val saveResp = executeAjaxPost(
                context = context,
                baseUrl = baseUrl,
                urlString = saveUrl,
                body = saveBody,
                accept = "text/html, */*; q=0.01"
            )
            if (isSessionExpiredResponse(saveResp)) {
                return null to true
            }
            if (saveResp == null || saveResp.statusCode != 200 || saveResp.body.isBlank()) {
                return StampSubmitResult.Failed(
                    if (en) "Could not save stamp" else "Leimauksen tallennus epäonnistui",
                    fallbackToWebView = true
                ) to false
            }

            // Varmistetaan vastaus-HTML:stä että leimaussuunta vaihtui
            val oppositeDir = if (eventType == "IN") "OUT" else "IN"
            val controls = parseBottomContainerFragment(saveResp.body)
            val confirmedByFlip = controls != null && controls.nextDirection.equals(oppositeDir, ignoreCase = true)

            val refreshedMore = fetchMoreStamps(
                context = context,
                take = activeState.currentTake.coerceAtLeast(6),
                getMoreStampsUrlPath = activeState.getMoreStampsUrl
            )
            val newRows = refreshedMore?.first ?: activeState.latestStamps
            val newHasMore = refreshedMore?.second ?: activeState.hasMoreStamps
            val beforeTopId = activeState.latestStamps.firstOrNull()?.rowId.orEmpty()
            val afterTopId = newRows.firstOrNull()?.rowId.orEmpty()
            val confirmedByRow = afterTopId.isNotEmpty() && afterTopId != beforeTopId

            if (confirmedByFlip || confirmedByRow) {
                val merged = activeState.copy(
                    nextDirection = controls?.nextDirection ?: oppositeDir,
                    punchButtonText = controls?.punchButtonText ?: activeState.punchButtonText,
                    defaultReasonCode = controls?.defaultReasonCode ?: activeState.defaultReasonCode,
                    reasonCodes = controls?.reasonCodes?.takeIf { it.isNotEmpty() } ?: activeState.reasonCodes,
                    latestStamps = newRows,
                    hasMoreStamps = newHasMore,
                    fromCache = false
                )
                saveCachedStampingState(context, merged)
                context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                    .edit()
                    .putLong("last_valid_session_ms", System.currentTimeMillis())
                    .apply()
                return StampSubmitResult.Success(merged, eventType) to false
            }

            // Haetaan mahdollinen palvelimen virheilmoitus (GetAlertMessages)
            val alertMsg = fetchAlertMessageText(context, baseUrl)
            if (!alertMsg.isNullOrBlank()) {
                return StampSubmitResult.ValidationRejected(alertMsg) to false
            }

            // Viimeinen varmistus koko sivun uudelleenhakuna
            val verifiedFresh = fetchStampingState(context, forceRefreshSession = false)
            if (verifiedFresh != null) {
                val freshTopId = verifiedFresh.latestStamps.firstOrNull()?.rowId.orEmpty()
                if (verifiedFresh.nextDirection.equals(oppositeDir, ignoreCase = true) ||
                    (freshTopId.isNotEmpty() && freshTopId != beforeTopId)
                ) {
                    return StampSubmitResult.Success(verifiedFresh, eventType) to false
                }
            }

            return StampSubmitResult.Failed(
                if (en) "Could not confirm stamp automatically" else "Leimausta ei voitu vahvistaa automaattisesti",
                fallbackToWebView = false
            ) to false
        }

        val (firstResult, needsReauth) = attemptValidateAndSave(state)
        if (firstResult != null) return@withContext firstResult

        if (needsReauth) {
            onStatusUpdate?.invoke(if (en) "Refreshing session…" else "Uusitaan istuntoa…")
            val freshState = fetchStampingState(context, forceRefreshSession = true)
            if (freshState != null) {
                if (expectedDirection != null && !freshState.nextDirection.equals(expectedDirection, ignoreCase = true)) {
                    return@withContext StampSubmitResult.AlreadyInDirection(freshState.nextDirection)
                }
                val (retryResult, _) = attemptValidateAndSave(freshState)
                if (retryResult != null) return@withContext retryResult
            }
        }

        StampSubmitResult.Failed(
            if (en) "Session expired – please try again" else "Istunto vanhentunut – kokeile uudelleen",
            fallbackToWebView = true
        )
    }

    suspend fun performQuickStamp(
        context: Context,
        wantIn: Boolean,
        onStatusUpdate: ((String) -> Unit)? = null
    ): StampSubmitResult {
        val expectedDir = if (wantIn) "IN" else "OUT"
        return performDirectStamp(
            context = context,
            currentState = null,
            reasonCodeId = null,
            comment = "",
            expectedDirection = expectedDir,
            onStatusUpdate = onStatusUpdate
        )
    }

    private fun fetchAlertMessageText(context: Context, baseUrl: String): String? {
        val resp = executeAjaxGet(context, baseUrl, resolveAbsoluteUrl(baseUrl, "/WorktimeStamping/GetAlertMessages"))
        if (resp == null || resp.statusCode != 200 || resp.body.isBlank()) return null
        val doc = Jsoup.parseBodyFragment(resp.body)
        val texts = doc.select(".alert").map { el ->
            el.select("button.close").remove()
            el.text().replace(Regex("\\s+"), " ").trim()
        }.filter { it.isNotEmpty() }
        return if (texts.isEmpty()) null else texts.joinToString("\n")
    }

    private data class BottomControlsData(
        val nextDirection: String,
        val punchButtonText: String,
        val defaultReasonCode: Int,
        val reasonCodes: List<StampReasonCode>
    )

    private fun parseBottomContainerFragment(htmlFragment: String): BottomControlsData? {
        val doc = Jsoup.parseBodyFragment(htmlFragment)
        val btn = doc.selectFirst("#punchButton")
        val btnText = btn?.text()?.replace(Regex("\\s+"), " ")?.trim().orEmpty()
        var nextDir = doc.selectFirst("[data-next-stamp-direction]")
            ?.attr("data-next-stamp-direction")
            ?.trim()
            ?.uppercase()
            .orEmpty()
        if (nextDir != "IN" && nextDir != "OUT") {
            val lower = btnText.lowercase()
            nextDir = when {
                lower.contains("ulos") || Regex("\\bout\\b").containsMatchIn(lower) -> "OUT"
                lower.contains("sisään") || Regex("\\bin\\b").containsMatchIn(lower) -> "IN"
                else -> ""
            }
        }
        if (nextDir.isEmpty() && btnText.isEmpty()) return null

        val defaultRc = btn?.attr("data-default-reason-code")?.trim()?.toIntOrNull() ?: 0
        val reasonCodes = mutableListOf<StampReasonCode>()
        doc.select(".punch-reason-code-selector ul.dropdown-menu li a[data-reason-code-id]").forEach { a ->
            val rcId = a.attr("data-reason-code-id").trim().toIntOrNull() ?: return@forEach
            val label = a.text().replace(Regex("\\s+"), " ").trim()
            if (label.isNotEmpty() && reasonCodes.none { it.id == rcId }) {
                reasonCodes.add(StampReasonCode(rcId, label))
            }
        }
        return BottomControlsData(
            nextDirection = nextDir,
            punchButtonText = btnText,
            defaultReasonCode = defaultRc,
            reasonCodes = reasonCodes
        )
    }

    private fun parseLatestStampsFragment(htmlFragment: String): Pair<List<StampHistoryRow>, Boolean> {
        val doc = Jsoup.parseBodyFragment(htmlFragment)
        val rows = mutableListOf<StampHistoryRow>()
        doc.select("#table-latest-stamps tbody tr, #table-latest-stamps tr").forEach { tr ->
            val rowId = tr.selectFirst("input[name^=RowID_]")?.attr("value")?.trim()
                ?: tr.selectFirst("td.punching-rowid-col")?.text()?.trim()
                ?: ""
            val dayText = tr.selectFirst("td.punching-day-col")?.text()?.replace(Regex("\\s+"), " ")?.trim().orEmpty()
            val timeText = tr.selectFirst("td.punching-times-col")?.text()?.replace(Regex("\\s+"), " ")?.trim().orEmpty()
            val dirText = tr.selectFirst("td.punching-direction-col")?.text()?.replace(Regex("\\s+"), " ")?.trim().orEmpty()
            val typeText = tr.selectFirst("td.punching-type-col")?.text()?.replace(Regex("\\s+"), " ")?.trim().orEmpty()

            if (dayText.isNotEmpty() || timeText.isNotEmpty() || dirText.isNotEmpty()) {
                val lowerDir = dirText.lowercase()
                val isIn = lowerDir == "sisään" || lowerDir == "in" || lowerDir.startsWith("sisään")
                rows.add(
                    StampHistoryRow(
                        rowId = rowId,
                        dayText = dayText,
                        timeText = timeText,
                        directionText = dirText,
                        isIn = isIn,
                        typeText = typeText
                    )
                )
            }
        }
        val hasMore = doc.selectFirst("#showMoreStampsButton") != null
        return rows to hasMore
    }

    fun parseStampingHtml(html: String): StampingPageState? {
        if (html.isBlank()) return null
        val doc = Jsoup.parse(html)
        if (doc.selectFirst("#LoginForm") != null) return null

        val controls = parseBottomContainerFragment(
            doc.selectFirst("#bottomContainer")?.outerHtml() ?: html
        ) ?: return null

        val shiftTimes = doc.selectFirst(".punching-shift-times")?.text()?.replace(Regex("\\s+"), " ")?.trim().orEmpty()
        val shiftRawName = doc.selectFirst(".punching-shift-name")?.text()?.replace(Regex("\\s+"), " ")?.trim().orEmpty()
        val (workplace, details) = NumeronParser.formatShiftBannerLines(shiftRawName)

        val (stamps, hasMore) = parseLatestStampsFragment(
            doc.selectFirst("#latestStampsContainer")?.outerHtml() ?: html
        )
        val token = doc.selectFirst("input[name=__RequestVerificationToken]")?.attr("value")?.trim().orEmpty()
        val saveUrl = doc.selectFirst("#SaveStampUrl")?.attr("value")?.trim().orEmpty()
            .ifEmpty { "/WorktimeStamping/SaveStamp" }
        val validateUrl = doc.selectFirst("#ValidateStampSaveUrl")?.attr("value")?.trim().orEmpty()
            .ifEmpty { "/WorktimeStamping/ValidateStampSave" }
        val moreUrl = doc.selectFirst("#GetMoreStampsUrl")?.attr("value")?.trim().orEmpty()
            .ifEmpty { "/WorktimeStamping/GetMoreStamps" }

        return StampingPageState(
            shiftTimes = shiftTimes,
            shiftWorkplace = workplace,
            shiftDetails = details,
            nextDirection = controls.nextDirection,
            punchButtonText = controls.punchButtonText,
            defaultReasonCode = controls.defaultReasonCode,
            reasonCodes = controls.reasonCodes,
            latestStamps = stamps,
            hasMoreStamps = hasMore,
            currentTake = stamps.size.coerceAtLeast(6),
            verificationToken = token,
            saveStampUrl = saveUrl,
            validateStampSaveUrl = validateUrl,
            getMoreStampsUrl = moreUrl,
            fromCache = false
        )
    }

    private fun stampingCacheFile(context: Context): File = File(context.cacheDir, "vv_stamping_state.json")

    fun saveCachedStampingState(context: Context, state: StampingPageState) {
        try {
            val root = JSONObject().apply {
                put("shiftTimes", state.shiftTimes)
                put("shiftWorkplace", state.shiftWorkplace)
                put("shiftDetails", state.shiftDetails)
                put("nextDirection", state.nextDirection)
                put("punchButtonText", state.punchButtonText)
                put("defaultReasonCode", state.defaultReasonCode)
                put("hasMoreStamps", state.hasMoreStamps)
                put("currentTake", state.currentTake)
                put("saveStampUrl", state.saveStampUrl)
                put("validateStampSaveUrl", state.validateStampSaveUrl)
                put("getMoreStampsUrl", state.getMoreStampsUrl)
                put("savedAt", System.currentTimeMillis())
            }
            val rcArr = JSONArray()
            for (rc in state.reasonCodes) {
                rcArr.put(JSONObject().apply {
                    put("id", rc.id)
                    put("label", rc.label)
                })
            }
            root.put("reasonCodes", rcArr)

            val stArr = JSONArray()
            for (row in state.latestStamps) {
                stArr.put(JSONObject().apply {
                    put("rowId", row.rowId)
                    put("dayText", row.dayText)
                    put("timeText", row.timeText)
                    put("directionText", row.directionText)
                    put("isIn", row.isIn)
                    put("typeText", row.typeText)
                })
            }
            root.put("latestStamps", stArr)
            stampingCacheFile(context).writeText(root.toString(), Charsets.UTF_8)
        } catch (_: Exception) {
        }
    }

    fun loadCachedStampingState(context: Context): StampingPageState? {
        return try {
            val file = stampingCacheFile(context)
            if (!file.exists()) return null
            val root = JSONObject(file.readText(Charsets.UTF_8))

            val reasonCodes = mutableListOf<StampReasonCode>()
            val rcArr = root.optJSONArray("reasonCodes")
            if (rcArr != null) {
                for (i in 0 until rcArr.length()) {
                    val o = rcArr.optJSONObject(i) ?: continue
                    reasonCodes.add(StampReasonCode(o.optInt("id", 0), o.optString("label", "")))
                }
            }

            val stamps = mutableListOf<StampHistoryRow>()
            val stArr = root.optJSONArray("latestStamps")
            if (stArr != null) {
                for (i in 0 until stArr.length()) {
                    val o = stArr.optJSONObject(i) ?: continue
                    stamps.add(
                        StampHistoryRow(
                            rowId = o.optString("rowId", ""),
                            dayText = o.optString("dayText", ""),
                            timeText = o.optString("timeText", ""),
                            directionText = o.optString("directionText", ""),
                            isIn = o.optBoolean("isIn", false),
                            typeText = o.optString("typeText", "")
                        )
                    )
                }
            }

            StampingPageState(
                shiftTimes = root.optString("shiftTimes", ""),
                shiftWorkplace = root.optString("shiftWorkplace", ""),
                shiftDetails = root.optString("shiftDetails", ""),
                nextDirection = root.optString("nextDirection", ""),
                punchButtonText = root.optString("punchButtonText", ""),
                defaultReasonCode = root.optInt("defaultReasonCode", 0),
                reasonCodes = reasonCodes,
                latestStamps = stamps,
                hasMoreStamps = root.optBoolean("hasMoreStamps", false),
                currentTake = root.optInt("currentTake", 6),
                verificationToken = "",
                saveStampUrl = root.optString("saveStampUrl", "/WorktimeStamping/SaveStamp"),
                validateStampSaveUrl = root.optString("validateStampSaveUrl", "/WorktimeStamping/ValidateStampSave"),
                getMoreStampsUrl = root.optString("getMoreStampsUrl", "/WorktimeStamping/GetMoreStamps"),
                fromCache = true
            )
        } catch (_: Exception) {
            null
        }
    }

    // =========================================================================
    // KALENTERI JA TOIVEET (Vaiheet 1–3)
    // =========================================================================

    suspend fun fetchMonthCalendarHtml(context: Context, year: Int, month: Int): String? =
        withContext(Dispatchers.IO) {
            val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
            if (baseUrl.isBlank()) return@withContext null
            val url = "$baseUrl/Calendar/Month?month=$month&year=$year"
            val html = BackgroundAuthHelper.fetchAuthenticatedPages(context, listOf(url))?.firstOrNull()
            if (html != null) {
                extractAndSaveMaxSessionTime(context, html)
            }
            html
        }

    suspend fun fetchRequests(context: Context, filter: String = "active"): RequestsFetchResult =
        withContext(Dispatchers.IO) {
            val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
            if (baseUrl.isBlank()) {
                return@withContext RequestsFetchResult(null, errorMessage = "Organisaatio puuttuu")
            }
            if (BackgroundAuthHelper.isCredentialBlocked(context)) {
                return@withContext RequestsFetchResult(null, errorMessage = "Tarkista tunnukset asetuksista")
            }

            if (!isSessionLikelyValid(context, baseUrl, isAutoStamping = false)) {
                BackgroundAuthHelper.ensureAuthenticatedSession(context)
            }

            var json = executeRequestsPost(context, baseUrl, filter)
            if (json == null) {
                val reauthed = BackgroundAuthHelper.ensureAuthenticatedSession(context, forceRefresh = true)
                if (reauthed) {
                    json = executeRequestsPost(context, baseUrl, filter)
                }
            }

            if (json == null) {
                val cached = loadCachedRequests(context, filter)
                return@withContext if (cached != null) {
                    RequestsFetchResult(cached, fromCache = true, errorMessage = "Näytetään välimuisti")
                } else {
                    RequestsFetchResult(null, errorMessage = "Toiveiden haku epäonnistui")
                }
            }

            val parsed = parseRequestsJson(context, json)
            if (parsed != null) {
                saveCachedRequestsJson(context, filter, json)
                context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                    .edit()
                    .putLong("last_valid_session_ms", System.currentTimeMillis())
                    .apply()
                RequestsFetchResult(parsed, fromCache = false)
            } else {
                RequestsFetchResult(null, errorMessage = "Vastauksen lukeminen epäonnistui")
            }
        }

    private fun executeRequestsPost(context: Context, baseUrl: String, filter: String): String? {
        val safeFilter = when (filter) {
            "old", "removed" -> filter
            else -> "active"
        }
        val resp = executeAjaxPost(
            context = context,
            baseUrl = baseUrl,
            urlString = "$baseUrl/PersonRequests/Read",
            body = "sort=&page=1&pageSize=100&group=&filter=&selectedFilter=$safeFilter",
            accept = "application/json, text/javascript, */*; q=0.01",
            refererPath = "/PersonRequests/List"
        ) ?: return null
        if (resp.statusCode != 200) return null
        return if (resp.body.trim().startsWith("{")) resp.body else null
    }

    fun parseRequestsJson(context: Context, jsonStr: String): List<PersonRequestItem>? {
        return try {
            val root = JSONObject(jsonStr)
            val dataArray = root.optJSONArray("data") ?: root.optJSONArray("Data") ?: return emptyList()
            val en = DemoModeHelper.isEnglish(context)
            val list = ArrayList<PersonRequestItem>(dataArray.length())

            for (i in 0 until dataArray.length()) {
                val item = dataArray.optJSONObject(i) ?: continue
                val id = item.optInt("Id", -1).let { if (it > 0) it else item.optInt("RowId", -1) }
                if (id <= 0) continue

                val rawStatus = item.optString("Status", "").trim().toIntOrNull()
                    ?: item.optString("StatusId", "").trim().toIntOrNull()
                    ?: item.optInt("Status", -1).let { if (it > 0) it else item.optInt("StatusId", -1) }
                val rawDesc = item.optString("StatusDescription", "").trim()
                val statusCode = resolveStatusCode(rawStatus, rawDesc)
                val statusDesc = rawDesc.ifEmpty { fallbackStatusLabel(statusCode, en) }

                val type = item.optString("Type", if (en) "Request" else "Toive").trim()
                val dateFrom = parseLocalDate(item.optString("DateFrom", ""))
                val dateTo = parseLocalDate(item.optString("DateTo", ""))
                val timeFromText = parseTimeSpan(item.optJSONObject("TimeFromTimeSpan"))
                val timeToText = parseTimeSpan(item.optJSONObject("TimeToTimeSpan"))
                val info = item.optString("Info", "").let { if (it.equals("null", true)) "" else it.trim() }
                val belongsToSeries = item.optBoolean("BelongsToSeries", false)
                val approvedBy = item.optString("ApprovedBy", "").let { if (it.equals("null", true)) "" else it.trim() }
                val approvedDateMs = parseDotNetDateMs(item.optString("ApprovedDate", ""))

                list.add(
                    PersonRequestItem(
                        id = id,
                        type = type,
                        dateFrom = dateFrom,
                        dateTo = dateTo,
                        timeFromText = timeFromText,
                        timeToText = timeToText,
                        info = info,
                        statusCode = statusCode,
                        statusDescription = statusDesc,
                        belongsToSeries = belongsToSeries,
                        approvedBy = approvedBy,
                        approvedDateMs = approvedDateMs
                    )
                )
            }
            list
        } catch (_: Exception) {
            null
        }
    }

    private fun resolveStatusCode(rawStatus: Int, statusDesc: String): Int {
        if (rawStatus == 10 || rawStatus == 40 || rawStatus == 50 || rawStatus == 80) return rawStatus
        val lower = statusDesc.trim().lowercase()
        if (lower.isEmpty()) return rawStatus
        return when {
            lower.contains("odottaa") || lower.contains("pending") || lower.contains("waiting") || lower.contains("väntar") -> 10
            lower.contains("osittain") || lower.contains("partial") || lower.contains("delvis") -> 40
            lower.contains("hylätty") || lower.contains("reject") || lower.contains("denied") || lower.contains("avslag") -> 80
            lower.contains("hyväksytty") || lower.contains("approved") || lower.contains("godkänd") -> 50
            else -> rawStatus
        }
    }

    private fun fallbackStatusLabel(statusId: Int, en: Boolean): String = when (statusId) {
        10 -> if (en) "Pending" else "Odottaa käsittelyä"
        40 -> if (en) "Partially approved" else "Osittain hyväksytty"
        50 -> if (en) "Approved" else "Hyväksytty"
        80 -> if (en) "Rejected" else "Hylätty"
        else -> ""
    }

    private fun parseDotNetDateMs(raw: String): Long? {
        val match = DOTNET_DATE_REGEX.find(raw.trim()) ?: return null
        return match.groupValues[1].toLongOrNull()
    }

    private fun parseLocalDate(raw: String): LocalDate? {
        val trimmed = raw.trim()
        if (trimmed.isEmpty() || trimmed.equals("null", ignoreCase = true)) return null
        val ms = parseDotNetDateMs(trimmed)
        if (ms != null) {
            return Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).toLocalDate()
        }
        val iso = Regex("^(\\d{4}-\\d{2}-\\d{2})").find(trimmed)?.groupValues?.get(1)
        if (iso != null) {
            return try {
                LocalDate.parse(iso)
            } catch (_: Exception) {
                null
            }
        }
        return null
    }

    private fun parseTimeSpan(obj: JSONObject?): String {
        if (obj == null) return ""
        val hours = obj.optInt("Hours", 0)
        val minutes = obj.optInt("Minutes", 0)
        if (hours == 0 && minutes == 0) return ""
        return String.format("%02d:%02d", hours, minutes)
    }

    private fun requestsCacheFile(context: Context, filter: String): File {
        val safe = when (filter) {
            "old", "removed" -> filter
            else -> "active"
        }
        return File(context.cacheDir, "vv_requests_$safe.json")
    }

    private fun saveCachedRequestsJson(context: Context, filter: String, json: String) {
        try {
            requestsCacheFile(context, filter).writeText(json, Charsets.UTF_8)
        } catch (_: Exception) {
        }
    }

    fun loadCachedRequests(context: Context, filter: String): List<PersonRequestItem>? {
        return try {
            val file = requestsCacheFile(context, filter)
            if (!file.exists()) return null
            parseRequestsJson(context, file.readText(Charsets.UTF_8))
        } catch (_: Exception) {
            null
        }
    }

    private fun monthCacheFile(context: Context, year: Int, month: Int): File {
        return File(context.cacheDir, "vv_month_${year}_${month}.json")
    }

    fun saveMonthDisplayCache(context: Context, data: MonthDisplayData) {
        try {
            val root = JSONObject().apply {
                put("year", data.year)
                put("month", data.month)
                put("savedAt", System.currentTimeMillis())
            }
            val daysArr = JSONArray()
            for ((date, day) in data.days) {
                val dObj = JSONObject().apply {
                    put("date", date.toString())
                    put("hasCommentCircle", day.hasCommentCircle)
                }
                val shiftsArr = JSONArray()
                for (s in day.shifts) {
                    shiftsArr.put(
                        JSONObject().apply {
                            put("startText", s.startText)
                            put("endText", s.endText)
                            put("startMinutes", s.startMinutes)
                            put("endMinutes", s.endMinutes)
                            put("location", s.location)
                            put("shiftName", s.shiftName)
                            put("role", s.role)
                            put("rawTitle", s.rawTitle)
                        }
                    )
                }
                dObj.put("shifts", shiftsArr)

                val absArr = JSONArray()
                for (a in day.absences) {
                    absArr.put(
                        JSONObject().apply {
                            put("title", a.title)
                            put("kind", a.kind)
                            put("spanDays", a.spanDays)
                        }
                    )
                }
                dObj.put("absences", absArr)

                val reqArr = JSONArray()
                for (r in day.requests) {
                    reqArr.put(r.title)
                }
                dObj.put("requests", reqArr)

                daysArr.put(dObj)
            }
            root.put("days", daysArr)
            monthCacheFile(context, data.year, data.month).writeText(root.toString(), Charsets.UTF_8)
        } catch (_: Exception) {
        }
    }

    fun loadMonthDisplayCache(context: Context, year: Int, month: Int): MonthDisplayData? {
        return try {
            val file = monthCacheFile(context, year, month)
            if (!file.exists()) return null
            val root = JSONObject(file.readText(Charsets.UTF_8))
            val daysArr = root.optJSONArray("days") ?: return null
            val map = mutableMapOf<LocalDate, CalendarDisplayDay>()

            for (i in 0 until daysArr.length()) {
                val dObj = daysArr.optJSONObject(i) ?: continue
                val date = try {
                    LocalDate.parse(dObj.optString("date", ""))
                } catch (_: Exception) {
                    continue
                }
                val hasCircle = dObj.optBoolean("hasCommentCircle", false)

                val shifts = mutableListOf<CalendarDisplayShift>()
                val sArr = dObj.optJSONArray("shifts")
                if (sArr != null) {
                    for (j in 0 until sArr.length()) {
                        val s = sArr.optJSONObject(j) ?: continue
                        shifts.add(
                            CalendarDisplayShift(
                                startText = s.optString("startText", ""),
                                endText = s.optString("endText", ""),
                                startMinutes = s.optInt("startMinutes", 0),
                                endMinutes = s.optInt("endMinutes", 0),
                                location = s.optString("location", ""),
                                shiftName = s.optString("shiftName", ""),
                                role = s.optString("role", ""),
                                rawTitle = s.optString("rawTitle", "")
                            )
                        )
                    }
                }

                val absences = mutableListOf<CalendarDisplayAbsence>()
                val aArr = dObj.optJSONArray("absences")
                if (aArr != null) {
                    for (j in 0 until aArr.length()) {
                        val a = aArr.optJSONObject(j) ?: continue
                        absences.add(
                            CalendarDisplayAbsence(
                                title = a.optString("title", ""),
                                kind = a.optString("kind", "other"),
                                spanDays = a.optInt("spanDays", 1)
                            )
                        )
                    }
                }

                val requests = mutableListOf<CalendarDisplayRequest>()
                val rArr = dObj.optJSONArray("requests")
                if (rArr != null) {
                    for (j in 0 until rArr.length()) {
                        val t = rArr.optString(j, "")
                        if (t.isNotEmpty()) requests.add(CalendarDisplayRequest(t))
                    }
                }

                map[date] = CalendarDisplayDay(
                    date = date,
                    shifts = shifts,
                    absences = absences,
                    requests = requests,
                    hasCommentCircle = hasCircle
                )
            }
            MonthDisplayData(year = year, month = month, days = map)
        } catch (_: Exception) {
            null
        }
    }

    fun buildMonthDisplayFromCachedShifts(
        shifts: List<WorkShift>,
        year: Int,
        month: Int
    ): MonthDisplayData? {
        val targetYm = java.time.YearMonth.of(year, month)
        val firstDay = targetYm.atDay(1)
        val lastDay = targetYm.atEndOfMonth()

        val shiftsByDate = mutableMapOf<LocalDate, MutableList<CalendarDisplayShift>>()
        val absencesByDate = mutableMapOf<LocalDate, MutableList<CalendarDisplayAbsence>>()
        var matchedAny = false

        for (shift in shifts) {
            if (shift.isAllDayLeave) {
                var d = shift.start.toLocalDate()
                val endExcl = shift.end.toLocalDate()
                val kind = when {
                    shift.title.contains("sairaus", true) || shift.title.contains("hoitovapaa", true) -> "sick"
                    shift.title.contains("loma", true) || shift.title.contains("säästövapaa", true) -> "vacation"
                    else -> "other"
                }
                while (d.isBefore(endExcl)) {
                    if (!d.isBefore(firstDay) && !d.isAfter(lastDay)) {
                        matchedAny = true
                        val list = absencesByDate.getOrPut(d) { mutableListOf() }
                        if (list.none { it.title.equals(shift.title, true) }) {
                            list.add(CalendarDisplayAbsence(shift.title, kind, 1))
                        }
                    }
                    d = d.plusDays(1)
                }
            } else {
                val d = shift.start.toLocalDate()
                if (!d.isBefore(firstDay) && !d.isAfter(lastDay)) {
                    matchedAny = true
                    val startText = String.format("%d:%02d", shift.start.hour, shift.start.minute)
                    val endText = String.format("%d:%02d", shift.end.hour, shift.end.minute)
                    val startMin = shift.start.hour * 60 + shift.start.minute
                    val endMin = shift.end.hour * 60 + shift.end.minute
                    val list = shiftsByDate.getOrPut(d) { mutableListOf() }
                    list.add(
                        CalendarDisplayShift(
                            startText = startText,
                            endText = endText,
                            startMinutes = startMin,
                            endMinutes = endMin,
                            location = shift.location,
                            shiftName = shift.title.takeUnless { it.equals("Työvuoro", true) }.orEmpty(),
                            role = shift.description.lineSequence().firstOrNull().orEmpty(),
                            rawTitle = shift.title
                        )
                    )
                }
            }
        }

        if (!matchedAny) return null
        val allDates = (shiftsByDate.keys + absencesByDate.keys)
        val dayMap = mutableMapOf<LocalDate, CalendarDisplayDay>()
        for (d in allDates) {
            dayMap[d] = CalendarDisplayDay(
                date = d,
                shifts = shiftsByDate[d].orEmpty(),
                absences = absencesByDate[d].orEmpty(),
                requests = emptyList(),
                hasCommentCircle = false
            )
        }
        return MonthDisplayData(year = year, month = month, days = dayMap)
    }

    fun getStampingCacheSavedAtMs(context: Context): Long {
        val file = stampingCacheFile(context)
        return if (file.exists()) file.lastModified() else 0L
    }

    fun getRequestsCacheSavedAtMs(context: Context, filter: String): Long {
        val file = requestsCacheFile(context, filter)
        return if (file.exists()) file.lastModified() else 0L
    }

    fun getMonthCacheSavedAtMs(context: Context, year: Int, month: Int): Long {
        val file = monthCacheFile(context, year, month)
        return if (file.exists()) file.lastModified() else 0L
    }
}
