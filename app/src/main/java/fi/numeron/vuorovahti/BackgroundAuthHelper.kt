package fi.numeron.vuorovahti

import android.content.Context
import android.webkit.CookieManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.jsoup.Jsoup
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

object BackgroundAuthHelper {

    suspend fun ensureAuthenticatedSession(context: Context): Boolean = withContext(Dispatchers.IO) {
        if (DemoModeHelper.isDemoEnabled(context)) return@withContext false

        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        val username = SecureCredentialManager.getUsername(context).orEmpty()
        val password = SecureCredentialManager.getPassword(context).orEmpty()

        if (baseUrl.isBlank() || username.isBlank() || password.isBlank()) {
            return@withContext false
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

            // 2. Lähetä kirjautumislomake
            val loginResp = executeRequest(
                urlString = postUrl,
                method = "POST",
                cookieStore = cookieStore,
                postBody = encodedBody
            ) ?: return@withContext false

            val stillOnLogin = Jsoup.parse(loginResp.body)
                .selectFirst("#LoginForm, input[type=password]") != null
            if (stillOnLogin || cookieStore.isEmpty()) {
                return@withContext false
            }

            // 3. Tallenna evästeet Androidin jaettuun CookieManageriin
            val cm = CookieManager.getInstance()
            cm.setAcceptCookie(true)
            val secureAttr = if (baseUrl.startsWith("https://", ignoreCase = true)) "; Secure" else ""
            cookieStore.forEach { (name, value) ->
                cm.setCookie(baseUrl, "$name=$value; Path=/$secureAttr")
            }
            cm.flush()

            true
        } catch (_: Exception) {
            false
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
        maxRedirects: Int = 5
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
                    currentUrl = if (location.startsWith("http")) {
                        location
                    } else {
                        URL(URL(currentUrl), location).toString()
                    }
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
        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) return@withContext null

        val cookieStore = mutableMapOf<String, String>()
        fun loadFromCookieManager() {
            cookieStore.clear()
            val raw = CookieManager.getInstance().getCookie(baseUrl).orEmpty()
            raw.split(";").forEach { part ->
                val trimmed = part.trim()
                val eq = trimmed.indexOf('=')
                if (eq > 0) {
                    cookieStore[trimmed.substring(0, eq).trim()] = trimmed.substring(eq + 1).trim()
                }
            }
        }

        loadFromCookieManager()
        if (cookieStore.isEmpty()) {
            if (!ensureAuthenticatedSession(context)) return@withContext null
            loadFromCookieManager()
        }

        val results = mutableListOf<String>()
        var reauthed = false

        for (targetUrl in urls) {
            var res = executeRequest(targetUrl, "GET", cookieStore) ?: return@withContext null
            val needsLogin = res.finalUrl.contains("/Login", ignoreCase = true) ||
                res.body.contains("id="LoginForm"", ignoreCase = true)

            if (needsLogin && !reauthed) {
                reauthed = true
                if (!ensureAuthenticatedSession(context)) return@withContext null
                loadFromCookieManager()
                res = executeRequest(targetUrl, "GET", cookieStore) ?: return@withContext null
            }

            if (res.statusCode !in 200..299 ||
                res.finalUrl.contains("/Login", ignoreCase = true) ||
                res.body.contains("id="LoginForm"", ignoreCase = true)
            ) {
                return@withContext null
            }
            results.add(res.body)
        }

        results
    }
}
