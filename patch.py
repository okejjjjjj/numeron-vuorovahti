import os
import sys


def find_file(filename):
    default_path = os.path.join("app", "src", "main", "java", "fi", "numeron", "vuorovahti", filename)
    if os.path.isfile(default_path):
        return default_path
    for root, _, files in os.walk("."):
        if filename in files:
            return os.path.join(root, filename)
    return None


def patch_background_auth_helper():
    path = find_file("BackgroundAuthHelper.kt")
    if not path:
        print("VIRHE: BackgroundAuthHelper.kt ei löytynyt.")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    old_imports = """import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.jsoup.Jsoup
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder"""

    new_imports = """import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import org.jsoup.Jsoup
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.concurrent.ConcurrentHashMap"""

    if old_imports in src:
        src = src.replace(old_imports, new_imports, 1)

    old_login_post = """            // 2. Lähetä kirjautumislomake
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
            }"""

    new_login_post = """            // 2. Lähetä kirjautumislomake (pysäytetään 302-ohjaukseen ilman raskaan kohdesivun latausta)
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
            if (stillOnLogin || cookieStore.isEmpty()) {
                return@withContext false
            }"""

    if old_login_post in src:
        src = src.replace(old_login_post, new_login_post, 1)

    old_exec = """    private fun executeRequest(
        urlString: String,
        method: String,
        cookieStore: MutableMap<String, String>,
        postBody: String? = null,
        maxRedirects: Int = 5
    ): HttpResult? {"""

    new_exec = """    private fun executeRequest(
        urlString: String,
        method: String,
        cookieStore: MutableMap<String, String>,
        postBody: String? = null,
        maxRedirects: Int = 5,
        stopAfterRedirect: Boolean = false
    ): HttpResult? {"""

    if old_exec in src:
        src = src.replace(old_exec, new_exec, 1)

    old_redirect = """                if (code in 300..399) {
                    val location = conn.getHeaderField("Location") ?: return null
                    currentUrl = if (location.startsWith("http")) {
                        location
                    } else {
                        URL(URL(currentUrl), location).toString()
                    }
                    currentMethod = "GET"
                    currentBody = null
                }"""

    new_redirect = """                if (code in 300..399) {
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
                }"""

    if old_redirect in src:
        src = src.replace(old_redirect, new_redirect, 1)

    old_fetch = """    suspend fun fetchAuthenticatedPages(context: Context, urls: List<String>): List<String>? = withContext(Dispatchers.IO) {
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
                res.body.contains("id=\\"LoginForm\\"", ignoreCase = true)

            if (needsLogin && !reauthed) {
                reauthed = true
                if (!ensureAuthenticatedSession(context)) return@withContext null
                loadFromCookieManager()
                res = executeRequest(targetUrl, "GET", cookieStore) ?: return@withContext null
            }

            if (res.statusCode !in 200..299 ||
                res.finalUrl.contains("/Login", ignoreCase = true) ||
                res.body.contains("id=\\"LoginForm\\"", ignoreCase = true)
            ) {
                return@withContext null
            }
            results.add(res.body)
        }

        results
    }"""

    new_fetch = """    suspend fun fetchAuthenticatedPages(context: Context, urls: List<String>): List<String>? = withContext(Dispatchers.IO) {
        if (urls.isEmpty()) return@withContext emptyList()
        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) return@withContext null

        fun readCookiesFromManager(): Map<String, String> {
            val map = mutableMapOf<String, String>()
            val raw = CookieManager.getInstance().getCookie(baseUrl).orEmpty()
            raw.split(";").forEach { part ->
                val trimmed = part.trim()
                val eq = trimmed.indexOf('=')
                if (eq > 0) {
                    map[trimmed.substring(0, eq).trim()] = trimmed.substring(eq + 1).trim()
                }
            }
            return map
        }

        fun persistUpdatedCookies(updated: Map<String, String>, original: Map<String, String>) {
            if (updated == original) return
            val cm = CookieManager.getInstance()
            val secureAttr = if (baseUrl.startsWith("https://", ignoreCase = true)) "; Secure" else ""
            updated.forEach { (k, v) ->
                if (original[k] != v) {
                    cm.setCookie(baseUrl, "$k=$v; Path=/$secureAttr")
                }
            }
            cm.flush()
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
                res.body.contains("id=\\"LoginForm\\"", ignoreCase = true)
        }

        if (anyNeedsLogin) {
            if (!ensureAuthenticatedSession(context)) return@withContext null
            cookies = readCookiesFromManager()
            responses = fetchAllParallel(cookies)
        }

        val bodies = ArrayList<String>(responses.size)
        for (res in responses) {
            if (res == null ||
                res.statusCode !in 200..299 ||
                res.finalUrl.contains("/Login", ignoreCase = true) ||
                res.body.contains("id=\\"LoginForm\\"", ignoreCase = true)
            ) {
                return@withContext null
            }
            bodies.add(res.body)
        }

        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putLong("last_valid_session_ms", System.currentTimeMillis())
            .apply()

        bodies
    }"""

    if old_fetch in src:
        src = src.replace(old_fetch, new_fetch, 1)

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    print(f"Päivitetty: {path}")


def patch_numeron_parser():
    path = find_file("NumeronParser.kt")
    if not path:
        print("VIRHE: NumeronParser.kt ei löytynyt.")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    old_imports = """import java.time.format.DateTimeFormatter
import kotlin.math.roundToInt"""

    new_imports = """import java.time.format.DateTimeFormatter
import java.util.concurrent.Callable
import java.util.concurrent.Executors
import kotlin.math.roundToInt"""

    if old_imports in src:
        src = src.replace(old_imports, new_imports, 1)

    old_loop = """        val commentsMap = mutableMapOf<Pair<LocalDate, LocalTime?>, String>()
        val cleanBase = baseUrl.trimEnd('/')
        for (sampleDate in weekSampleDates) {
            val listUrl = "$cleanBase/Calendar/List?date=${sampleDate.monthValue}%2F${sampleDate.dayOfMonth}%2F${sampleDate.year}%2000%3A00%3A00"
            val listHtml = fetchHtmlWithCookies(listUrl, cookieHeader) ?: continue
            commentsMap.putAll(parseListCommentsHtml(listHtml))
        }"""

    new_loop = """        val commentsMap = mutableMapOf<Pair<LocalDate, LocalTime?>, String>()
        val cleanBase = baseUrl.trimEnd('/')
        if (weekSampleDates.size == 1) {
            val sampleDate = weekSampleDates.first()
            val listUrl = "$cleanBase/Calendar/List?date=${sampleDate.monthValue}%2F${sampleDate.dayOfMonth}%2F${sampleDate.year}%2000%3A00%3A00"
            val listHtml = fetchHtmlWithCookies(listUrl, cookieHeader)
            if (listHtml != null) {
                commentsMap.putAll(parseListCommentsHtml(listHtml))
            }
        } else {
            val pool = Executors.newFixedThreadPool(weekSampleDates.size.coerceAtMost(4))
            try {
                val tasks = weekSampleDates.map { sampleDate ->
                    Callable {
                        val listUrl = "$cleanBase/Calendar/List?date=${sampleDate.monthValue}%2F${sampleDate.dayOfMonth}%2F${sampleDate.year}%2000%3A00%3A00"
                        val listHtml = fetchHtmlWithCookies(listUrl, cookieHeader)
                        if (listHtml != null) parseListCommentsHtml(listHtml) else emptyMap()
                    }
                }
                for (future in pool.invokeAll(tasks)) {
                    try {
                        commentsMap.putAll(future.get())
                    } catch (_: Exception) {
                    }
                }
            } finally {
                pool.shutdown()
            }
        }"""

    if old_loop in src:
        src = src.replace(old_loop, new_loop, 1)

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    print(f"Päivitetty: {path}")


def patch_main_activity():
    path = find_file("MainActivity.kt")
    if not path:
        print("VIRHE: MainActivity.kt ei löytynyt.")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    # 1. Varmistetaan navigateToTab-lohko ankkureilla (toimii riippumatta aiemmasta patchista)
    nav_start_marker = "        if (DemoModeHelper.isDemoEnabled(this)) {"
    nav_end_marker = "                if (existingCookies.isNullOrBlank() || sessionAgeMs > maxSessionAgeMs) {"
    nav_replacement = """        if (DemoModeHelper.isDemoEnabled(this)) {
            startSnapshotTransition {
                val html = when (tab) {
                    Tab.STAMP -> DemoModeHelper.getDemoStampingHtml(this)
                    Tab.REQUESTS -> DemoModeHelper.getDemoRequestsHtml(this)
                    Tab.SHIFTS -> DemoModeHelper.getDemoShiftsHtml(this)
                }
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
            val now = LocalDate.now()
            val url = when (tab) {
                Tab.STAMP -> "$baseUrl/WorktimeStamping"
                Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
                Tab.SHIFTS -> "$baseUrl/Calendar/Month?month=${now.monthValue}&year=${now.year}"
            }
            startSnapshotTransition {
                val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                val lastSessionMs = prefs.getLong("last_valid_session_ms", 0L)
                val sessionAgeMs = System.currentTimeMillis() - lastSessionMs
                val existingCookies = CookieManager.getInstance().getCookie(baseUrl)
                val isAutoStamping = (pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT)
                val maxSessionAgeMs = if (isAutoStamping) 10L * 60 * 1000L else 25L * 60 * 1000L

"""

    s_idx = src.find(nav_start_marker)
    e_idx = src.find(nav_end_marker, s_idx) if s_idx != -1 else -1
    if s_idx != -1 and e_idx != -1:
        src = src[:s_idx] + nav_replacement + src[e_idx:]

    # 2. Kevyt rinnakkainen kalenterisynkronointi WebView-latauksen sijaan
    old_sync = """        pendingAction = Action.SYNC_CALENDAR
        syncStep = 0
        collectedCalendarHtml.clear()
        val now = LocalDate.now()
        val baseUrl = getBaseUrl()
        webView.loadUrl("$baseUrl/Calendar/Month?month=${now.monthValue}&year=${now.year}")"""

    new_sync = """        val baseUrl = getBaseUrl()
        if (baseUrl.isBlank()) {
            val en = DemoModeHelper.isEnglish(this)
            Toast.makeText(
                this,
                if (en) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista",
                Toast.LENGTH_LONG
            ).show()
            return
        }

        val now = LocalDate.now()
        val nextMonth = now.plusMonths(1)
        val urls = listOf(
            "$baseUrl/Calendar/Month?month=${now.monthValue}&year=${now.year}",
            "$baseUrl/Calendar/Month?month=${nextMonth.monthValue}&year=${nextMonth.year}"
        )

        val enStart = DemoModeHelper.isEnglish(this)
        Toast.makeText(
            this,
            if (enStart) "Syncing shifts..." else "Synkronoidaan työvuoroja...",
            Toast.LENGTH_SHORT
        ).show()

        scope.launch {
            val fetchedPages = BackgroundAuthHelper.fetchAuthenticatedPages(this@MainActivity, urls)
            if (fetchedPages != null && fetchedPages.size == 2) {
                processSyncedCalendarPages(fetchedPages)
            } else {
                pendingAction = Action.SYNC_CALENDAR
                syncStep = 0
                collectedCalendarHtml.clear()
                webView.loadUrl(urls[0])
            }
        }"""

    if old_sync in src:
        src = src.replace(old_sync, new_sync, 1)

    # 3. WebChromeClient + InfraDashboard-uudelleenohjaus shouldOverrideUrlLoading-vaiheessa
    old_settings_apply = """        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            userAgentString = WebSettings.getDefaultUserAgent(this@MainActivity)
        }"""

    new_settings_apply = """        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            userAgentString = WebSettings.getDefaultUserAgent(this@MainActivity)
        }
        webView.webChromeClient = android.webkit.WebChromeClient()"""

    if "webChromeClient" not in src and old_settings_apply in src:
        src = src.replace(old_settings_apply, new_settings_apply, 1)

    old_override = """                    if (isInternal) {
                        startSnapshotTransition()
                        return false
                    }"""

    new_override = """                    if (isInternal) {
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

    if "view?.loadUrl(resolveResumeUrl(getBaseUrl()))" not in src and old_override in src:
        src = src.replace(old_override, new_override, 1)

    # 4. Korjataan "Lisää unohtunut leimaus" -paneelin CSS ja "Näytä lisää" -toiminto leimaussivulla
    old_forgot_css = """            #forgotStampPanel,
            #forgotStampPanel.minimized,
            #forgotStampPanel[style*="top: 100%"],
            #forgotStampPanel[style*="top:100%"] {
                display: none !important;
            }
            #forgotStampPanel[style*="top:"]:not(.minimized):not([style*="top: 100%"]):not([style*="top:100%"]),
            #forgotStampPanel.force-open {"""

    new_forgot_css = """            #forgotStampPanel:not(.force-open) {
                display: none !important;
            }
            #forgotStampPanel.force-open {"""

    if old_forgot_css in src:
        src = src.replace(old_forgot_css, new_forgot_css, 1)

    old_forgot_js = """                if (!window._forgotStampHelperInstalled) {
                    window._forgotStampHelperInstalled = true;
                    document.addEventListener('click', function(e) {
                        var btn = e.target && e.target.closest('#forgottenStampButton');
                        if (btn) {
                            var panel = document.getElementById('forgotStampPanel');
                            if (panel) {
                                panel.classList.remove('minimized');
                                panel.classList.add('force-open');
                            }
                        }
                        var cancelBtn = e.target && e.target.closest('#cancelPunchForgottenButton, #cancelPunchForgottenButtonHeader');
                        if (cancelBtn) {
                            var panel = document.getElementById('forgotStampPanel');
                            if (panel) {
                                panel.classList.remove('force-open');
                                panel.classList.add('minimized');
                            }
                        }
                    }, true);
                }"""

    new_forgot_js = """                if (!window._forgotStampHelperInstalled) {
                    window._forgotStampHelperInstalled = true;

                    function getForgotPanel() {
                        return document.getElementById('forgotStampPanel') || document.querySelector('[id*="forgotStampPanel" i], [id*="ForgotStampPanel" i]');
                    }

                    function openForgotPanel() {
                        var panel = getForgotPanel();
                        if (panel) {
                            panel.classList.remove('minimized', 'hidden', 'hide');
                            panel.classList.add('force-open');
                            panel.style.top = '10%';
                            panel.style.display = 'block';
                        }
                        var fog = document.querySelector('.drw-fog-of-war');
                        if (fog) {
                            fog.classList.add('showing');
                            fog.style.display = 'block';
                        }
                    }

                    function closeForgotPanel() {
                        var panel = getForgotPanel();
                        if (panel) {
                            panel.classList.remove('force-open');
                            panel.classList.add('minimized');
                            panel.style.top = '100%';
                            panel.style.display = 'none';
                        }
                        var fog = document.querySelector('.drw-fog-of-war');
                        if (fog) {
                            fog.classList.remove('showing');
                            fog.style.display = 'none';
                        }
                    }

                    function isForgotOpenTrigger(el) {
                        if (!el) return false;
                        if (el.closest('#forgotStampPanel')) return false;
                        if (el.closest('#forgottenStampButton, #punchForgottenButton, [id*="forgotten" i], [id*="ForgotStamp" i]')) return true;
                        var clickable = el.closest('button, a, [role="button"]');
                        if (!clickable) return false;
                        var txt = (clickable.innerText || clickable.textContent || '').toLowerCase();
                        return txt.indexOf('unohtunut leimaus') !== -1 || txt.indexOf('forgotten stamp') !== -1;
                    }

                    function revealHiddenStampRows() {
                        var hiddenRows = document.querySelectorAll('#table-latest-stamps tr.hidden, #table-latest-stamps tr.hide, #table-latest-stamps tr[style*="display: none"], #table-latest-stamps tr[style*="display:none"]');
                        for (var i = 0; i < hiddenRows.length; i++) {
                            hiddenRows[i].classList.remove('hidden', 'hide');
                            hiddenRows[i].style.display = 'table-row';
                        }
                    }

                    function isShowMoreTrigger(el) {
                        if (!el) return false;
                        var clickable = el.closest('button, a, [role="button"]');
                        if (!clickable) return false;
                        var id = (clickable.id || '').toLowerCase();
                        if (id.indexOf('more') !== -1 || id.indexOf('lisaa') !== -1) return true;
                        var txt = (clickable.innerText || clickable.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                        return txt === 'näytä lisää' || txt === 'show more' || txt.indexOf('näytä lisää') !== -1 || txt.indexOf('show more') !== -1;
                    }

                    document.addEventListener('click', function(e) {
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
                        }
                    }, true);

                    function watchStampPageDom() {
                        var panel = getForgotPanel();
                        if (panel && !panel._vvWatched && typeof MutationObserver !== 'undefined') {
                            panel._vvWatched = true;
                            var pObs = new MutationObserver(function() {
                                var st = panel.getAttribute('style') || '';
                                var isTop100 = /top\\s*:\\s*100%/i.test(st);
                                if (!isTop100 && !panel.classList.contains('minimized') && st.indexOf('top:') !== -1) {
                                    panel.classList.add('force-open');
                                } else if (isTop100) {
                                    panel.classList.remove('force-open');
                                }
                            });
                            pObs.observe(panel, { attributes: true, attributeFilter: ['style', 'class'] });
                        }
                        var stampTbl = document.getElementById('table-latest-stamps');
                        if (stampTbl && !stampTbl._vvWatched && typeof MutationObserver !== 'undefined') {
                            stampTbl._vvWatched = true;
                            new MutationObserver(revealHiddenStampRows).observe(stampTbl, { childList: true, subtree: true });
                        }
                    }
                    watchStampPageDom();
                    if (document.body && typeof MutationObserver !== 'undefined') {
                        new MutationObserver(watchStampPageDom).observe(document.body, { childList: true, subtree: true });
                    }
                }

                // === AJAX- JA FETCH-ISTUNTOVALVONTA LEIMAUSSIVUN HAUILLE ("NÄYTÄ LISÄÄ" YM.) ===
                if (!window._ajaxSessionGuardInstalled) {
                    window._ajaxSessionGuardInstalled = true;
                    function triggerSessionRefreshOnce() {
                        if (window._sessionExpiredHandled) return;
                        window._sessionExpiredHandled = true;
                        if (window.SessionBridge && typeof window.SessionBridge.onSessionExpired === 'function') {
                            window.SessionBridge.onSessionExpired();
                        }
                    }
                    if (window.XMLHttpRequest) {
                        var origOpen = XMLHttpRequest.prototype.open;
                        var origSend = XMLHttpRequest.prototype.send;
                        XMLHttpRequest.prototype.open = function(method, url) {
                            this._vvUrl = url ? String(url) : '';
                            return origOpen.apply(this, arguments);
                        };
                        XMLHttpRequest.prototype.send = function() {
                            this.addEventListener('load', function() {
                                try {
                                    var respUrl = (this.responseURL || '').toLowerCase();
                                    var bodyText = (typeof this.responseText === 'string') ? this.responseText : '';
                                    var redirectedToLogin = respUrl.indexOf('/login') !== -1 || bodyText.indexOf('id="LoginForm"') !== -1;
                                    if (this.status === 401 || this.status === 403 || redirectedToLogin) {
                                        triggerSessionRefreshOnce();
                                    }
                                } catch (_err) {}
                            });
                            return origSend.apply(this, arguments);
                        };
                    }
                    if (typeof window.fetch === 'function') {
                        var origFetch = window.fetch;
                        window.fetch = function() {
                            return origFetch.apply(this, arguments).then(function(response) {
                                try {
                                    var rUrl = (response && response.url ? response.url : '').toLowerCase();
                                    if (response && (response.status === 401 || response.status === 403 || rUrl.indexOf('/login') !== -1)) {
                                        triggerSessionRefreshOnce();
                                    }
                                } catch (_err) {}
                                return response;
                            });
                        };
                    }
                }"""

    if old_forgot_js in src:
        src = src.replace(old_forgot_js, new_forgot_js, 1)

    # 5. Yhtenäistetään kalenterisivujen käsittely
    old_cal_handler = """    private fun handleCalendarPage() {
        if (pendingAction != Action.SYNC_CALENDAR) return

        webView.evaluateJavascript("document.documentElement.outerHTML") { rawHtml ->
            if (rawHtml == null || rawHtml == "null") return@evaluateJavascript
            val unescapedHtml = JSONTokener(rawHtml).nextValue() as? String ?: return@evaluateJavascript
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

                scope.launch(Dispatchers.IO) {
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
                    val cookies = try {
                        CookieManager.getInstance().getCookie(baseUrl)
                    } catch (_: Exception) {
                        null
                    }
                    val rawShifts = NumeronParser.enrichShiftsWithListComments(
                        baseUrl = baseUrl,
                        cookieHeader = cookies,
                        htmlPages = pagesToParse,
                        shifts = parsedPages.filterNotNull().flatten()
                    )
                    val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                    val syncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
                    val calId = if (syncCalendar) CalendarSyncHelper.getTargetCalendarId(this@MainActivity) else null
                    val allShifts = NumeronParser.mergeConsecutiveLeaves(rawShifts)
                    CalendarSyncHelper.saveCachedShifts(this@MainActivity, allShifts)

                    val changes = if (syncCalendar && calId != null) {
                        CalendarSyncHelper.syncShiftsToCalendar(this@MainActivity, calId, allShifts)
                    } else {
                        prefs.edit().putLong("last_calendar_sync_ms", System.currentTimeMillis()).apply()
                        emptyList()
                    }
                    CalendarSyncHelper.scheduleShiftReminders(this@MainActivity, calId)

                    withContext(Dispatchers.Main) {
                        val en = DemoModeHelper.isEnglish(this@MainActivity)
                        if (syncCalendar && calId == null) {
                            Toast.makeText(
                                this@MainActivity,
                                if (en) "Shifts fetched (${allShifts.size}), but no calendar is selected" else "Vuorot haettu (${allShifts.size} kpl), mutta kalenteria ei ole valittu",
                                Toast.LENGTH_LONG
                            ).show()
                        } else if (changes.isNotEmpty()) {
                            Toast.makeText(
                                this@MainActivity,
                                if (en) "Calendar updated: ${CalendarChangeTracker.formatSummary(changes)}" else "Kalenteria päivitetty: ${CalendarChangeTracker.formatSummary(changes)}",
                                Toast.LENGTH_LONG
                            ).show()
                            CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                        } else {
                            val msg = if (syncCalendar) {
                                if (en) "Calendar is up to date (${allShifts.size} shifts)" else "Kalenteri on ajan tasalla (${allShifts.size} vuoroa)"
                            } else {
                                if (en) "Shifts and reminders updated (${allShifts.size} shifts)" else "Työvuorot ja muistutukset päivitetty (${allShifts.size} vuoroa)"
                            }
                            Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                        }
                    }
                }
            }
        }
    }"""

    new_cal_handler = """    private fun handleCalendarPage() {
        if (pendingAction != Action.SYNC_CALENDAR) return

        webView.evaluateJavascript("document.documentElement.outerHTML") { rawHtml ->
            if (rawHtml == null || rawHtml == "null") return@evaluateJavascript
            val unescapedHtml = JSONTokener(rawHtml).nextValue() as? String ?: return@evaluateJavascript
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
    }

    private fun processSyncedCalendarPages(pagesToParse: List<String>) {
        scope.launch(Dispatchers.IO) {
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
            val cookies = try {
                CookieManager.getInstance().getCookie(baseUrl)
            } catch (_: Exception) {
                null
            }
            val rawShifts = NumeronParser.enrichShiftsWithListComments(
                baseUrl = baseUrl,
                cookieHeader = cookies,
                htmlPages = pagesToParse,
                shifts = parsedPages.filterNotNull().flatten()
            )
            val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val syncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
            val calId = if (syncCalendar) CalendarSyncHelper.getTargetCalendarId(this@MainActivity) else null
            val allShifts = NumeronParser.mergeConsecutiveLeaves(rawShifts)
            CalendarSyncHelper.saveCachedShifts(this@MainActivity, allShifts)

            val changes = if (syncCalendar && calId != null) {
                CalendarSyncHelper.syncShiftsToCalendar(this@MainActivity, calId, allShifts)
            } else {
                prefs.edit().putLong("last_calendar_sync_ms", System.currentTimeMillis()).apply()
                emptyList()
            }
            CalendarSyncHelper.scheduleShiftReminders(this@MainActivity, calId)

            withContext(Dispatchers.Main) {
                val en = DemoModeHelper.isEnglish(this@MainActivity)
                if (syncCalendar && calId == null) {
                    Toast.makeText(
                        this@MainActivity,
                        if (en) "Shifts fetched (${allShifts.size}), but no calendar is selected" else "Vuorot haettu (${allShifts.size} kpl), mutta kalenteria ei ole valittu",
                        Toast.LENGTH_LONG
                    ).show()
                } else if (changes.isNotEmpty()) {
                    Toast.makeText(
                        this@MainActivity,
                        if (en) "Calendar updated: ${CalendarChangeTracker.formatSummary(changes)}" else "Kalenteria päivitetty: ${CalendarChangeTracker.formatSummary(changes)}",
                        Toast.LENGTH_LONG
                    ).show()
                    CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                } else {
                    val msg = if (syncCalendar) {
                        if (en) "Calendar is up to date (${allShifts.size} shifts)" else "Kalenteri on ajan tasalla (${allShifts.size} vuoroa)"
                    } else {
                        if (en) "Shifts and reminders updated (${allShifts.size} shifts)" else "Työvuorot ja muistutukset päivitetty (${allShifts.size} vuoroa)"
                    }
                    Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                }
            }
        }
    }"""

    if "private fun processSyncedCalendarPages(" not in src and old_cal_handler in src:
        src = src.replace(old_cal_handler, new_cal_handler, 1)

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    print(f"Päivitetty: {path}")


def main():
    patch_background_auth_helper()
    patch_numeron_parser()
    patch_main_activity()


if __name__ == "__main__":
    main()
