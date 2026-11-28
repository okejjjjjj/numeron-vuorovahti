package fi.numeron.vuorovahti

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.jsoup.Jsoup
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.concurrent.ConcurrentHashMap

object BackgroundAuthHelper {
    private val cookieSyncLock = Any()
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
            SessionCookieStore.clear(context)
        }
    }

    suspend fun ensureAuthenticatedSession(
        context: Context,
        forceRefresh: Boolean = false
    ): Boolean = withContext(Dispatchers.IO) {
        if (DemoModeHelper.isDemoEnabled(context)) return@withContext false

        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        val username = SecureCredentialManager.getUsername(context).orEmpty()
        val password = SecureCredentialManager.getPassword(context).orEmpty()

        if (baseUrl.isBlank() || username.isBlank() || password.isBlank()) {
            return@withContext false
        }
        if (isCredentialBlocked(context)) {
            return@withContext false
        }

        authMutex.withLock {
            if (isCredentialBlocked(context)) {
                return@withLock false
            }
            val nowMs = System.currentTimeMillis()
            val cachedCookies = SessionCookieStore.getCookieHeader(context, baseUrl)
            if (!forceRefresh &&
                !cachedCookies.isNullOrBlank() &&
                baseUrl == lastAuthBaseUrl &&
                (nowMs - lastAuthSuccessMs) < 90_000L
            ) {
                return@withLock true
            }

        val cookieStore = mutableMapOf<String, String>()

        try {
            // 1. Hae kirjautumissivu ja poimi lomake + __RequestVerificationToken
            val initial = executeRequest(
                urlString = "$baseUrl/Login/Login",
                method = "GET",
                cookieStore = cookieStore
            ) ?: return@withContext false

            val doc = Jsoup.parse(initial.body, initial.finalUrl)
            val form = doc.selectFirst("#LoginForm")
                ?: doc.selectFirst("form:has(input[type=password])")
                ?: return@withContext false

            val actionAttr = form.attr("action").ifBlank { initial.finalUrl }
            val postUrl = if (actionAttr.startsWith("http")) {
                actionAttr
            } else {
                URL(URL(initial.finalUrl), actionAttr).toString()
            }

            val formParams = mutableListOf<Pair<String, String>>()
            form.select("input[type=hidden]").forEach { input ->
                val name = input.attr("name")
                if (name.isNotBlank()) {
                    formParams.add(name to input.attr("value"))
                }
            }

            val userField = form.selectFirst("#Username, input[name=Username], input[type=text]")
                ?.attr("name")
                ?.ifBlank { "Username" } ?: "Username"
            val passField = form.selectFirst("#Password, input[name=Password], input[type=password]")
                ?.attr("name")
                ?.ifBlank { "Password" } ?: "Password"

            formParams.add(userField to username)
            formParams.add(passField to password)

            val encodedBody = formParams.joinToString("&") { (k, v) ->
                "${URLEncoder.encode(k, "UTF-8")}=${URLEncoder.encode(v, "UTF-8")}"
            }

            // 2. Lähetä kirjautumislomake (pysäytetään 302-ohjaukseen ilman raskaan kohdesivun latausta)
            val loginResp = executeRequest(
                urlString = postUrl,
                method = "POST",
                cookieStore = cookieStore,
                postBody = encodedBody,
                stopAfterRedirect = true
            ) ?: return@withContext false

            val stillOnLogin = if (loginResp.body.isNotEmpty()) {
                Jsoup.parse(loginResp.body).selectFirst("#LoginForm, input[type=password]") != null
            } else {
                loginResp.finalUrl.contains("/Login", ignoreCase = true)
            }
            if (loginResp.statusCode !in 200..399 || stillOnLogin || cookieStore.isEmpty()) {
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
            }

            // 3. Tallenna evästeet natiiviin SessionCookieStoreen (ilman Chromiumia)
            SessionCookieStore.replaceAll(context, baseUrl, cookieStore)
            lastAuthBaseUrl = baseUrl
            lastAuthSuccessMs = System.currentTimeMillis()

            true
        } catch (_: Exception) {
            false
        }
        }
    }

    private data class HttpResult(
        val finalUrl: String,
        val statusCode: Int,
        val body: String
    )

    private fun executeRequest(
        urlString: String,
        method: String,
        cookieStore: MutableMap<String, String>,
        postBody: String? = null,
        maxRedirects: Int = 5,
        stopAfterRedirect: Boolean = false
    ): HttpResult? {
        var currentUrl = urlString
        var currentMethod = method
        var currentBody = postBody

        repeat(maxRedirects + 1) {
            val conn = (URL(currentUrl).openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = false
                requestMethod = currentMethod
                connectTimeout = 15000
                readTimeout = 15000
                setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36")

                if (cookieStore.isNotEmpty()) {
                    val cookieHeader = cookieStore.entries.joinToString("; ") { "${it.key}=${it.value}" }
                    setRequestProperty("Cookie", cookieHeader)
                }

                if (currentMethod == "POST" && currentBody != null) {
                    doOutput = true
                    setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
                }
            }

            try {
                if (currentMethod == "POST" && currentBody != null) {
                    OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { it.write(currentBody) }
                }

                val code = conn.responseCode

                conn.headerFields
                    .filterKeys { it != null && it.equals("Set-Cookie", ignoreCase = true) }
                    .values
                    .flatten()
                    .forEach { rawCookie ->
                        val pair = rawCookie.substringBefore(";").trim()
                        val eqIndex = pair.indexOf('=')
                        if (eqIndex > 0) {
                            val name = pair.substring(0, eqIndex).trim()
                            val value = pair.substring(eqIndex + 1).trim()
                            if (value.isNotEmpty()) {
                                cookieStore[name] = value
                            } else {
                                cookieStore.remove(name)
                            }
                        }
                    }

                if (code in 300..399) {
                    val location = conn.getHeaderField("Location") ?: return null
                    val nextUrl = if (location.startsWith("http")) {
                        location
                    } else {
                        URL(URL(currentUrl), location).toString()
                    }
                    if (stopAfterRedirect && cookieStore.isNotEmpty() && !nextUrl.contains("/Login", ignoreCase = true)) {
                        return HttpResult(nextUrl, code, "")
                    }
                    currentUrl = nextUrl
                    currentMethod = "GET"
                    currentBody = null
                } else {
                    val stream = if (code in 200..299) conn.inputStream else conn.errorStream
                    val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
                    return HttpResult(currentUrl, code, text)
                }
            } finally {
                conn.disconnect()
            }
        }
        return null
    }

    fun testCredentials(baseUrl: String, username: String, password: String): Pair<Boolean, String> {
        val cookieStore = mutableMapOf<String, String>()
        return try {
            val initial = executeRequest(
                urlString = "$baseUrl/Login/Login",
                method = "GET",
                cookieStore = cookieStore
            ) ?: return false to "Yhteysvirhe: Organisaatiota '$baseUrl' ei löytynyt tai verkkoyhteys puuttuu."

            val doc = Jsoup.parse(initial.body, initial.finalUrl)
            val form = doc.selectFirst("#LoginForm")
                ?: doc.selectFirst("form:has(input[type=password])")
                ?: return false to "Virhe: Kirjautumislomaketta ei tunnistettu sivulta."

            val actionAttr = form.attr("action").ifBlank { initial.finalUrl }
            val postUrl = if (actionAttr.startsWith("http")) {
                actionAttr
            } else {
                URL(URL(initial.finalUrl), actionAttr).toString()
            }

            val formParams = mutableListOf<Pair<String, String>>()
            form.select("input[type=hidden]").forEach { input ->
                val name = input.attr("name")
                if (name.isNotBlank()) {
                    formParams.add(name to input.attr("value"))
                }
            }

            val userField = form.selectFirst("#Username, input[name=Username], input[type=text]")
                ?.attr("name")
                ?.ifBlank { "Username" } ?: "Username"
            val passField = form.selectFirst("#Password, input[name=Password], input[type=password]")
                ?.attr("name")
                ?.ifBlank { "Password" } ?: "Password"

            formParams.add(userField to username)
            formParams.add(passField to password)

            val encodedBody = formParams.joinToString("&") { (k, v) ->
                "${URLEncoder.encode(k, "UTF-8")}=${URLEncoder.encode(v, "UTF-8")}"
            }

            val loginResp = executeRequest(
                urlString = postUrl,
                method = "POST",
                cookieStore = cookieStore,
                postBody = encodedBody
            ) ?: return false to "Yhteysvirhe kirjautumisen aikana."

            if (loginResp.statusCode !in 200..399) {
                return false to "Palvelinvirhe kirjautumisessa (HTTP ${loginResp.statusCode})."
            }
            val respDoc = Jsoup.parse(loginResp.body)
            val stillOnLogin = respDoc.selectFirst("#LoginForm, input[type=password]") != null
            if (stillOnLogin || cookieStore.isEmpty()) {
                val errText = respDoc.selectFirst(".validation-summary-errors, .alert-danger")?.text()?.trim().orEmpty()
                if (errText.isNotEmpty()) {
                    false to "Kirjautuminen epäonnistui: $errText"
                } else {
                    false to "Virheellinen käyttäjätunnus tai salasana."
                }
            } else {
                true to "Yhteys ja tunnukset toimivat! ($baseUrl)"
            }
        } catch (e: Exception) {
            false to "Yhteysvirhe: ${e.message ?: "Palvelimeen ei saatu yhteyttä"}"
        }
    }

    suspend fun fetchAuthenticatedPages(context: Context, urls: List<String>): List<String>? = withContext(Dispatchers.IO) {
        if (urls.isEmpty()) return@withContext emptyList()
        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) return@withContext null

        fun readCookiesFromManager(): Map<String, String> {
            return SessionCookieStore.getCookieMap(context, baseUrl)
        }

        fun persistUpdatedCookies(updated: Map<String, String>, original: Map<String, String>) = synchronized(cookieSyncLock) {
            if (updated == original) return
            SessionCookieStore.replaceAll(context, baseUrl, updated)
        }

        suspend fun fetchAllParallel(baseCookies: Map<String, String>): List<HttpResult?> = coroutineScope {
            urls.map { targetUrl ->
                async(Dispatchers.IO) {
                    val localStore = ConcurrentHashMap(baseCookies)
                    val res = executeRequest(targetUrl, "GET", localStore)
                    if (res != null) {
                        persistUpdatedCookies(localStore, baseCookies)
                    }
                    res
                }
            }.awaitAll()
        }

        var cookies = readCookiesFromManager()
        if (cookies.isEmpty()) {
            if (!ensureAuthenticatedSession(context)) return@withContext null
            cookies = readCookiesFromManager()
        }

        var responses = fetchAllParallel(cookies)
        val anyNeedsLogin = responses.any { res ->
            res == null ||
                res.finalUrl.contains("/Login", ignoreCase = true) ||
                res.body.contains("id=\"LoginForm\"", ignoreCase = true)
        }

        if (anyNeedsLogin) {
            if (!ensureAuthenticatedSession(context, forceRefresh = true)) return@withContext null
            cookies = readCookiesFromManager()
            responses = fetchAllParallel(cookies)
        }

        val bodies = ArrayList<String>(responses.size)
        for (res in responses) {
            if (res == null ||
                res.statusCode !in 200..299 ||
                res.finalUrl.contains("/Login", ignoreCase = true) ||
                res.body.contains("id=\"LoginForm\"", ignoreCase = true)
            ) {
                return@withContext null
            }
            NumeronApiClient.extractAndSaveMaxSessionTime(context, res.body)
            bodies.add(res.body)
        }

        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putLong("last_valid_session_ms", System.currentTimeMillis())
            .apply()

        bodies
    }
}
