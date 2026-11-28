package fi.numeron.vuorovahti

import android.content.Context
import android.webkit.CookieManager
import org.json.JSONObject
import java.net.URL

/**
 * Kevyt natiivi evästevarasto HTTP-kutsuille ilman Chromium/WebView CookieManagerin käynnistystä.
 * Evästeet synkronoidaan CookieManageriin vasta kun WebView todella avataan.
 */
object SessionCookieStore {

    private const val KEY_HOST = "vv_session_cookie_host"
    private const val KEY_JSON = "vv_session_cookie_json"
    private const val PREF_WEBVIEW_CLEAR = "webview_cookies_need_clear"

    private val lock = Any()
    private var loadedFromDisk: Boolean = false
    private var cachedHost: String = ""
    private val cachedCookies = LinkedHashMap<String, String>()

    @Volatile
    var sessionEpoch: Long = 0L
        private set

    private fun normalizeHost(baseUrl: String): String {
        val clean = baseUrl.trim()
        if (clean.isEmpty()) return ""
        return try {
            val u = URL(clean)
            val portPart = if (u.port > 0 && u.port != u.defaultPort) ":${u.port}" else ""
            "${u.host.lowercase()}$portPart"
        } catch (_: Exception) {
            clean.trimEnd('/').lowercase()
        }
    }

    private fun ensureLoadedLocked(context: Context) {
        if (loadedFromDisk) return
        loadedFromDisk = true
        try {
            val enc = SecureCredentialManager.getSharedEncryptedPrefs(context) ?: return
            val host = enc.getString(KEY_HOST, "").orEmpty()
            val rawJson = enc.getString(KEY_JSON, "").orEmpty()
            if (host.isNotEmpty() && rawJson.startsWith("{")) {
                val obj = JSONObject(rawJson)
                cachedHost = host
                cachedCookies.clear()
                val keys = obj.keys()
                while (keys.hasNext()) {
                    val k = keys.next()
                    val v = obj.optString(k, "")
                    if (k.isNotBlank() && v.isNotEmpty()) {
                        cachedCookies[k] = v
                    }
                }
            }
        } catch (_: Exception) {
        }
    }

    private fun persistLocked(context: Context) {
        try {
            val enc = SecureCredentialManager.getSharedEncryptedPrefs(context) ?: return
            if (cachedHost.isEmpty() || cachedCookies.isEmpty()) {
                enc.edit().remove(KEY_HOST).remove(KEY_JSON).apply()
            } else {
                val obj = JSONObject()
                for ((k, v) in cachedCookies) {
                    obj.put(k, v)
                }
                enc.edit()
                    .putString(KEY_HOST, cachedHost)
                    .putString(KEY_JSON, obj.toString())
                    .apply()
            }
        } catch (_: Exception) {
        }
    }

    fun getCookieHeader(context: Context, baseUrl: String): String? {
        val host = normalizeHost(baseUrl)
        if (host.isEmpty()) return null
        return synchronized(lock) {
            ensureLoadedLocked(context)
            if (cachedHost != host || cachedCookies.isEmpty()) return@synchronized null
            cachedCookies.entries.joinToString("; ") { "${it.key}=${it.value}" }
        }
    }

    fun getCookieMap(context: Context, baseUrl: String): MutableMap<String, String> {
        val host = normalizeHost(baseUrl)
        if (host.isEmpty()) return LinkedHashMap()
        return synchronized(lock) {
            ensureLoadedLocked(context)
            if (cachedHost != host || cachedCookies.isEmpty()) {
                LinkedHashMap()
            } else {
                LinkedHashMap(cachedCookies)
            }
        }
    }

    fun replaceAll(context: Context, baseUrl: String, cookies: Map<String, String>) {
        val host = normalizeHost(baseUrl)
        if (host.isEmpty()) return
        synchronized(lock) {
            ensureLoadedLocked(context)
            val filtered = LinkedHashMap<String, String>()
            for ((k, v) in cookies) {
                if (k.isNotBlank() && v.isNotEmpty()) {
                    filtered[k] = v
                }
            }
            if (cachedHost == host && cachedCookies == filtered) return
            cachedHost = host
            cachedCookies.clear()
            cachedCookies.putAll(filtered)
            persistLocked(context)
        }
    }

    fun mergeFromSetCookieHeaders(
        context: Context,
        baseUrl: String,
        rawHeaders: Collection<String>
    ) {
        if (rawHeaders.isEmpty()) return
        val host = normalizeHost(baseUrl)
        if (host.isEmpty()) return
        synchronized(lock) {
            ensureLoadedLocked(context)
            if (cachedHost.isNotEmpty() && cachedHost != host) {
                cachedCookies.clear()
            }
            cachedHost = host
            var changed = false
            for (raw in rawHeaders) {
                val lower = raw.lowercase()
                val pair = raw.substringBefore(";").trim()
                val eqIdx = pair.indexOf('=')
                if (eqIdx <= 0) continue
                val name = pair.substring(0, eqIdx).trim()
                val value = pair.substring(eqIdx + 1).trim()
                val isExpired = value.isEmpty() || lower.contains("max-age=0")
                if (isExpired) {
                    if (cachedCookies.remove(name) != null) changed = true
                } else if (cachedCookies[name] != value) {
                    cachedCookies[name] = value
                    changed = true
                }
            }
            if (changed) {
                persistLocked(context)
            }
        }
    }

    fun clear(context: Context) {
        synchronized(lock) {
            loadedFromDisk = true
            cachedHost = ""
            cachedCookies.clear()
            persistLocked(context)
            sessionEpoch++
        }
        try {
            context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                .edit()
                .putBoolean(PREF_WEBVIEW_CLEAR, true)
                .apply()
        } catch (_: Exception) {
        }
    }

    /**
     * Kutsutaan VAIN kun WebView oikeasti avataan.
     */
    fun syncToWebViewCookieManager(context: Context, baseUrl: String) {
        if (baseUrl.isBlank()) return
        try {
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val cm = CookieManager.getInstance()
            cm.setAcceptCookie(true)
            if (prefs.getBoolean(PREF_WEBVIEW_CLEAR, false)) {
                cm.removeAllCookies(null)
                prefs.edit().putBoolean(PREF_WEBVIEW_CLEAR, false).apply()
            }
            val cookies = getCookieMap(context, baseUrl)
            val secureAttr = if (baseUrl.startsWith("https://", ignoreCase = true)) "; Secure" else ""
            for ((name, value) in cookies) {
                cm.setCookie(baseUrl, "$name=$value; Path=/$secureAttr")
            }
            cm.flush()
        } catch (_: Exception) {
        }
    }

    /**
     * Kutsutaan VAIN kun WebView on jo käynnissä (tuo WebView'n päivitetyt evästeet natiivipuolelle).
     */
    fun importFromWebViewCookieManager(context: Context, baseUrl: String) {
        if (baseUrl.isBlank()) return
        try {
            val raw = CookieManager.getInstance().getCookie(baseUrl).orEmpty()
            if (raw.isBlank()) return
            val parsed = LinkedHashMap<String, String>()
            raw.split(";").forEach { part ->
                val trimmed = part.trim()
                val eq = trimmed.indexOf('=')
                if (eq > 0) {
                    val k = trimmed.substring(0, eq).trim()
                    val v = trimmed.substring(eq + 1).trim()
                    if (k.isNotBlank() && v.isNotEmpty()) {
                        parsed[k] = v
                    }
                }
            }
            if (parsed.isNotEmpty()) {
                val host = normalizeHost(baseUrl)
                synchronized(lock) {
                    ensureLoadedLocked(context)
                    if (cachedHost.isNotEmpty() && cachedHost != host) {
                        cachedCookies.clear()
                    }
                    cachedHost = host
                    var changed = false
                    for ((k, v) in parsed) {
                        if (cachedCookies[k] != v) {
                            cachedCookies[k] = v
                            changed = true
                        }
                    }
                    if (changed) {
                        persistLocked(context)
                    }
                }
            }
        } catch (_: Exception) {
        }
    }
}
