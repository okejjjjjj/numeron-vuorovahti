import pathlib
import re

target_file = pathlib.Path("app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt")
content = target_file.read_text(encoding="utf-8")

# 1. Lisätään Bitmap-import, jos puuttuu
if "import android.graphics.Bitmap" not in content:
    content = content.replace(
        "import android.graphics.Color",
        "import android.graphics.Bitmap\nimport android.graphics.Color"
    )

# 2. Päivitetään navigateToTab + lisätään fadeWebViewOut / fadeWebViewIn
new_navigate_block = '''    private fun fadeWebViewOut() {
        webView.animate().cancel()
        webView.alpha = 0f
    }

    private fun fadeWebViewIn() {
        webView.animate()
            .alpha(1f)
            .setDuration(180L)
            .start()
    }

    private fun navigateToTab(tab: Tab) {
        currentTab = tab
        updateDemoBanner()

        when (tab) {
            Tab.STAMP -> setActiveTab(btnNavStamp)
            Tab.REQUESTS -> setActiveTab(btnNavRequests)
            Tab.SHIFTS -> setActiveTab(btnNavShifts)
        }

        fadeWebViewOut()

        if (DemoModeHelper.isDemoEnabled(this)) {
            val html = when (tab) {
                Tab.STAMP -> DemoModeHelper.getDemoStampingHtml(this)
                Tab.REQUESTS -> DemoModeHelper.getDemoRequestsHtml(this)
                Tab.SHIFTS -> DemoModeHelper.getDemoShiftsHtml(this)
            }
            webView.loadDataWithBaseURL("https://demo.local/", html, "text/html", "UTF-8", null)
        } else {
            val baseUrl = getBaseUrl()
            val url = when (tab) {
                Tab.STAMP -> "$baseUrl/WorktimeStamping"
                Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
                Tab.SHIFTS -> "$baseUrl/Calendar/Month"
            }
            webView.loadUrl(url)
        }
    }'''

content, n_nav = re.subn(
    r'    private fun navigateToTab\(tab: Tab\) \{.*?\n    \}',
    new_navigate_block,
    content,
    count=1,
    flags=re.DOTALL
)
assert n_nav == 1, "navigateToTab-lohkoa ei löytynyt"

# 3. Päivitetään setupWebView (poistetaan clearCache, lisätään onPageStarted fadeOut & viivästetty fadeIn)
new_setup_webview = '''    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        webView.setBackgroundColor(Color.parseColor("#0F1722"))
        (webView.parent as? View)?.setBackgroundColor(Color.parseColor("#0F1722"))

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            userAgentString = WebSettings.getDefaultUserAgent(this@MainActivity)
        }

        webView.addJavascriptInterface(
            DemoModeHelper.DemoJsBridge(
                context = this,
                onReloadNeeded = { runOnUiThread { navigateToTab(currentTab) } },
                onSyncRequested = { runOnUiThread { startCalendarSync() } },
                onManageChangesRequested = { runOnUiThread { CalendarChangeTracker.showManageChangesDialog(this) } }
            ),
            "DemoBridge"
        )

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)

        webView.webViewClient = object : WebViewClient() {

            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                super.onPageStarted(view, url, favicon)
                fadeWebViewOut()
            }

            override fun shouldInterceptRequest(
                view: WebView?,
                request: WebResourceRequest?
            ): WebResourceResponse? {
                val url = request?.url?.toString()?.lowercase()
                    ?: return super.shouldInterceptRequest(view, request)

                val blockedCssPatterns = listOf(
                    "/content/css/cssvisma",
                    "/content/css/login.css",
                    "/content/css/calendar.css",
                    "/content/css/buttons.css",
                    "/bundles/cssworktimestamping",
                    "/content/css/worktimestamping.css",
                    "/content/css/listlayout.css",
                    "fonts.googleapis.com"
                )

                if (blockedCssPatterns.any { url.contains(it) }) {
                    return WebResourceResponse(
                        "text/css",
                        "UTF-8",
                        ByteArrayInputStream(ByteArray(0))
                    )
                }

                return super.shouldInterceptRequest(view, request)
            }

            override fun onPageCommitVisible(view: WebView?, url: String?) {
                super.onPageCommitVisible(view, url)
                if (url != null && !url.startsWith("https://demo.local/")) {
                    injectDarkTheme(view)
                }
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                if (url == null) return

                if (url.startsWith("https://demo.local/")) {
                    handleDemoAutoStamp()
                    fadeWebViewIn()
                    return
                }

                injectDarkTheme(view)

                when {
                    url.contains("/Login/Login", ignoreCase = true) -> handleAutoLogin()
                    url.contains("/WorktimeStamping", ignoreCase = true) -> {
                        setActiveTab(btnNavStamp)
                        handleStampingPage()
                    }
                    url.contains("/PersonRequests", ignoreCase = true) -> {
                        setActiveTab(btnNavRequests)
                    }
                    url.contains("/Calendar", ignoreCase = true) -> {
                        setActiveTab(btnNavShifts)
                        handleCalendarPage()
                    }
                }

                view?.postDelayed({
                    fadeWebViewIn()
                }, 70L)
            }
        }
    }'''

content, n_setup = re.subn(
    r'    @SuppressLint\("SetJavaScriptEnabled"\)\s+private fun setupWebView\(\) \{.*?\n        \}\n    \}',
    new_setup_webview,
    content,
    count=1,
    flags=re.DOTALL
)
assert n_setup == 1, "setupWebView-lohkoa ei löytynyt"

# 4. Päivitetään injectDarkTheme kattamaan myös /Calendar/List-näkymä
new_inject_dark_theme = '''    private fun injectDarkTheme(view: WebView?) {
        val css = """
            /* === 1. PERUSRUNKO JA PIILOTETTAVAT ELEMENTIT === */
            html, body {
                background-color: #0F1722 !important;
                background-image: none !important;
                color: #F1F5F9 !important;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            header, nav.navbar, footer, .footer, .copyright, .loginnav, .bottom-nav, .fade-in-box, .fade-out-box {
                display: none !important;
            }
            .container, .container-fluid {
                padding: 12px !important;
                width: 100% !important;
                max-width: 100% !important;
            }
            h1, h2, h3, h4, .h1, .h2, .h3, .h4 {
                color: #F1F5F9 !important;
                font-size: 20px !important;
                font-weight: 600 !important;
                margin-top: 4px !important;
                margin-bottom: 12px !important;
            }
            label, span, p, div {
                color: inherit;
            }
            a {
                color: #38BDF8 !important;
            }

            /* === 2. KORTIT, PANEELIT JA SYÖTTÖKENTÄT === */
            .panel, .panel-default, .whitebox, .card, .stamping-box, .box, .panel-footer, .form-actions {
                background-color: #182332 !important;
                border: 1px solid #2A394A !important;
                border-radius: 12px !important;
                color: #F1F5F9 !important;
                box-shadow: none !important;
                margin-bottom: 14px !important;
            }
            .panel-body {
                padding: 14px !important;
            }
            .panel-heading, .modal-header, .modal-footer {
                background-color: #1E293B !important;
                border-color: #2A394A !important;
                color: #F1F5F9 !important;
            }
            .modal-content {
                background-color: #182332 !important;
                border: 1px solid #37475A !important;
                color: #F1F5F9 !important;
            }
            input, select, textarea, .form-control, .k-textbox {
                background-color: #111923 !important;
                color: #FFFFFF !important;
                border: 1px solid #37475A !important;
                border-radius: 8px !important;
                box-shadow: none !important;
            }
            input[type="checkbox"], input[type="radio"] {
                accent-color: #1982C4 !important;
                width: 18px !important;
                height: 18px !important;
            }
            input::placeholder, textarea::placeholder {
                color: #64748B !important;
            }

            /* === 3. PAINIKKEET JA PUDOTUSVALIKOT === */
            .btn, .btn-default {
                background-color: #233040 !important;
                color: #F1F5F9 !important;
                border: 1px solid #37475A !important;
                border-radius: 8px !important;
                padding: 8px 14px !important;
                font-weight: 500 !important;
            }
            .btn-primary {
                background-color: #1982C4 !important;
                border-color: #1982C4 !important;
                color: #FFFFFF !important;
                font-weight: 600 !important;
            }
            .btn-text, .btn-link {
                background-color: transparent !important;
                border: none !important;
                color: #38BDF8 !important;
                padding: 6px 0 !important;
            }
            .dropdown-menu {
                background-color: #1E293B !important;
                border: 1px solid #37475A !important;
                border-radius: 8px !important;
            }
            .dropdown-menu > li > a {
                color: #F1F5F9 !important;
                padding: 8px 14px !important;
            }
            .dropdown-menu > li > a:hover, .dropdown-menu > li > a:focus {
                background-color: #2A394A !important;
                color: #FFFFFF !important;
            }
            .dropdown-header {
                color: #94A3B8 !important;
            }

            /* === 4. KIRJAUTUMISSIVU === */
            .content {
                padding: 16px !important;
                float: none !important;
                margin: 0 auto !important;
            }
            .blurbox h1 {
                text-align: center !important;
                font-size: 28px !important;
                font-weight: 700 !important;
                margin: 28px 0 20px 0 !important;
                color: #F1F5F9 !important;
            }
            .whitebox {
                padding: 20px !important;
                margin: 0 auto !important;
            }
            .whitebox img, .whitebox hr {
                display: none !important;
            }
            #LoginForm .form-group {
                margin-bottom: 14px !important;
            }
            #LoginForm .pull-left, #LoginForm .pull-right {
                margin-bottom: 12px !important;
                font-size: 13px !important;
            }
            #LoginForm input[type="submit"] {
                margin-top: 8px !important;
                padding: 12px !important;
                font-size: 16px !important;
            }

            /* === 5. TYÖAIKALEIMAUS === */
            .punching-balance-overview-container {
                display: none !important;
            }
            .punching-shift-caption, .previous-stamps-caption, .punching-caption {
                display: block !important;
                font-size: 12px !important;
                text-transform: uppercase !important;
                letter-spacing: 0.05em !important;
                color: #94A3B8 !important;
                margin-bottom: 6px !important;
                font-weight: 600 !important;
            }
            .punching-shift-name {
                font-size: 16px !important;
                font-weight: 600 !important;
                color: #F1F5F9 !important;
            }
            .punching-reason-code-label, .punching-stamp-comment-label, .forgotten-stamp-labels {
                color: #CBD5E1 !important;
                font-size: 13px !important;
                margin-top: 10px !important;
                margin-bottom: 4px !important;
            }
            .punch-reason-code-selector .btn, #dropdownMenu1, #dropdownMenu2, #dropdownMenuStampDirection {
                width: 100% !important;
                display: flex !important;
                justify-content: space-between !important;
                align-items: center !important;
                background-color: #111923 !important;
            }
            #punchButton {
                background-color: #2E7D32 !important;
                border-color: #2E7D32 !important;
                color: #FFFFFF !important;
                border-radius: 10px !important;
                padding: 12px !important;
                margin-top: 16px !important;
                font-weight: 700 !important;
            }
            .nav-tabs-wts {
                list-style: none !important;
                padding: 0 !important;
                margin: 0 0 10px 0 !important;
                border-bottom: 1px solid #2A394A !important;
                display: flex !important;
            }
            .nav-tabs-wts > li > a {
                display: inline-block !important;
                padding: 8px 14px !important;
                color: #F1F5F9 !important;
                border-bottom: 2px solid #2196F3 !important;
                text-decoration: none !important;
                font-weight: 600 !important;
            }
            #table-latest-stamps, .table {
                background-color: transparent !important;
                color: #F1F5F9 !important;
                margin-bottom: 8px !important;
            }
            #table-latest-stamps td, .table td, .table th {
                background-color: transparent !important;
                border-top: 1px solid #2A394A !important;
                color: #F1F5F9 !important;
                padding: 10px 6px !important;
            }
            #table-latest-stamps tr:hover td {
                background-color: #233040 !important;
            }
            #forgotStampPanel {
                display: none !important;
            }
            #forgotStampPanel[style*="top: 0"], #forgotStampPanel[style*="top:0"] {
                display: block !important;
                position: fixed !important;
                left: 8px !important;
                right: 8px !important;
                bottom: 8px !important;
                top: auto !important;
                z-index: 1050 !important;
                max-height: 88vh !important;
                overflow-y: auto !important;
            }

            /* === 6. TOIVEET & KENDO UI === */
            label[for="filterOptions"] {
                color: #F1F5F9 !important;
                margin-right: 6px !important;
            }
            .fixed-menu-bar {
                display: flex !important;
                flex-wrap: wrap !important;
                gap: 8px !important;
                align-items: center !important;
            }
            .k-grid, .k-grid-header, .k-grid-content, .k-pager-wrap {
                background-color: #182332 !important;
                color: #F1F5F9 !important;
                border-color: #2A394A !important;
            }
            .k-grid-header th.k-header, .k-grid-header th.k-header > .k-link {
                background-color: #233040 !important;
                color: #F1F5F9 !important;
                border-color: #2A394A !important;
                padding: 10px 8px !important;
            }
            .k-grid tr {
                background-color: #182332 !important;
                color: #F1F5F9 !important;
            }
            .k-grid tr.k-alt {
                background-color: #131C28 !important;
            }
            .k-grid td {
                border-color: #2A394A !important;
                color: #F1F5F9 !important;
                padding: 10px 8px !important;
            }
            .k-grid tr:hover td {
                background-color: #233040 !important;
                color: #FFFFFF !important;
            }
            .k-grid tr.k-state-selected td {
                background-color: #1982C4 !important;
                color: #FFFFFF !important;
            }
            .k-widget, .k-dropdown-wrap, .k-picker-wrap, .k-numeric-wrap, .k-select, .k-input, .k-pager-wrap .k-link, .k-pager-info {
                background-color: #111923 !important;
                color: #F1F5F9 !important;
                border-color: #37475A !important;
            }
            .k-list-container, .k-list, .k-calendar, .k-calendar .k-header {
                background-color: #1E293B !important;
                color: #F1F5F9 !important;
                border-color: #37475A !important;
            }
            .k-list .k-item:hover, .k-list .k-state-focused, .k-list .k-state-selected {
                background-color: #2A394A !important;
                color: #FFFFFF !important;
            }

            /* === 7. KALENTERI: YLÄPALKKI JA KUUKAUSINÄKYMÄ === */
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
            }
            .month-table {
                width: 100% !important;
                table-layout: fixed !important;
                border-collapse: collapse !important;
                background-color: #182332 !important;
            }
            .month-week-days td {
                background-color: #233040 !important;
                color: #CBD5E1 !important;
                font-weight: 600 !important;
                font-size: 12px !important;
                padding: 6px 2px !important;
                border: 1px solid #2A394A !important;
                text-align: center !important;
            }
            .month-week-number {
                width: 26px !important;
                background-color: #131C28 !important;
                color: #64748B !important;
                font-size: 11px !important;
                text-align: center !important;
                vertical-align: top !important;
                padding-top: 6px !important;
                border: 1px solid #2A394A !important;
            }
            td.month-day {
                background-color: #182332 !important;
                border: 1px solid #2A394A !important;
                vertical-align: top !important;
                height: 68px !important;
                padding: 2px !important;
            }
            td.month-day.past-day, td.month-day.day-different-month {
                background-color: #121A24 !important;
            }
            td.month-day.todayTd {
                background-color: #1E3A5F !important;
                border: 1px solid #38BDF8 !important;
            }
            .month-day-header {
                margin-bottom: 2px !important;
            }
            .dayNum {
                color: #F1F5F9 !important;
                font-size: 12px !important;
                font-weight: 600 !important;
                padding-left: 3px !important;
            }
            td.day-different-month .dayNum {
                color: #64748B !important;
            }
            .month-item.work {
                background-color: #0284C7 !important;
                color: #FFFFFF !important;
                border-radius: 4px !important;
                padding: 2px 3px !important;
                margin-bottom: 2px !important;
                font-size: 11px !important;
                line-height: 1.2 !important;
            }
            .month-item.work .itemTimes {
                display: block !important;
                color: #FFFFFF !important;
                font-weight: 600 !important;
            }
            .month-item.work .itemName {
                display: none !important;
            }

            /* === 8. KALENTERI: LUETTELONÄKYMÄ (/Calendar/List) === */
            #calendar-content {
                height: auto !important;
                overflow-y: visible !important;
            }
            .schedule-week-separator {
                margin: 14px 0 8px 0 !important;
                padding: 4px 2px !important;
                border-bottom: 1px solid #2A394A !important;
            }
            .schedule-week-separator-text {
                color: #38BDF8 !important;
                font-size: 13px !important;
                font-weight: 700 !important;
                text-transform: uppercase !important;
                letter-spacing: 0.05em !important;
            }
            .schedule-day-container {
                background-color: #182332 !important;
                border: 1px solid #2A394A !important;
                border-radius: 12px !important;
                padding: 12px !important;
                margin-bottom: 10px !important;
            }
            .schedule-day-information {
                display: flex !important;
                align-items: center !important;
                margin-bottom: 8px !important;
                padding-bottom: 6px !important;
                border-bottom: 1px solid #233040 !important;
            }
            .schedule-day {
                color: #94A3B8 !important;
                font-size: 12px !important;
                font-weight: 700 !important;
                letter-spacing: 0.04em !important;
            }
            .schedule-day-date {
                color: #F1F5F9 !important;
                font-size: 14px !important;
                font-weight: 700 !important;
            }
            .schedule-item-container {
                display: flex !important;
                align-items: stretch !important;
                background-color: #111923 !important;
                border: 1px solid #2A394A !important;
                border-left: 4px solid #0284C7 !important;
                border-radius: 8px !important;
                padding: 10px !important;
                margin-bottom: 8px !important;
            }
            .schedule-item-container.schedule-item-absence {
                border-left-color: #F59E0B !important;
            }
            .schedule-item-container.schedule-item-request {
                border-left-color: #8B5CF6 !important;
            }
            .schedule-item-container.schedule-item-opportunity {
                border-left-color: #10B981 !important;
            }
            .schedule-item-color-bar, .schedule-item-icon-td, .clear-float {
                display: none !important;
            }
            .schedule-item-content {
                width: 100% !important;
            }
            .schedule-item-body {
                display: flex !important;
                flex-direction: column !important;
                gap: 4px !important;
            }
            .schedule-item-times {
                color: #38BDF8 !important;
                font-size: 15px !important;
                font-weight: 700 !important;
            }
            .schedule-item-description-table {
                width: 100% !important;
            }
            .schedule-item-description-heading {
                color: #F1F5F9 !important;
                font-size: 14px !important;
                font-weight: 600 !important;
            }
            .schedule-item-description-subheading {
                color: #94A3B8 !important;
                font-size: 12px !important;
                margin-top: 2px !important;
            }
            .schedule-day-content > div[style*="max-height"] {
                max-height: none !important;
                margin-top: 6px !important;
            }
            .schedule-add-button {
                display: inline-block !important;
                color: #38BDF8 !important;
                font-size: 13px !important;
                font-weight: 600 !important;
                padding: 4px 0 !important;
                cursor: pointer !important;
            }
            .schedule-add-options {
                margin-top: 6px !important;
                display: flex !important;
                gap: 8px !important;
            }
            .schedule-option-link {
                background-color: #233040 !important;
                border: 1px solid #37475A !important;
                border-radius: 6px !important;
                padding: 6px 10px !important;
                font-size: 13px !important;
                text-decoration: none !important;
            }
            .mobileAddDiv {
                display: flex !important;
                justify-content: space-between !important;
                align-items: center !important;
                margin-top: 10px !important;
                padding: 4px 0 !important;
            }
            .mobileAddButton, .filterButton {
                background-color: #233040 !important;
                color: #F1F5F9 !important;
                border: 1px solid #37475A !important;
                border-radius: 8px !important;
                padding: 8px 14px !important;
                text-decoration: none !important;
                display: inline-block !important;
            }
            #mobileViewDropdown {
                margin-top: 8px !important;
            }
        """.trimIndent().replace("\n", " ")

        val js = """
            (function() {
                var style = document.getElementById('custom-dark-theme');
                if (!style) {
                    style = document.createElement('style');
                    style.id = 'custom-dark-theme';
                    document.head.appendChild(style);
                }
                style.innerHTML = '$css';
            })();
        """.trimIndent()
        view?.evaluateJavascript(js, null)
    }'''

content, n_inject = re.subn(
    r'    private fun injectDarkTheme\(view: WebView\?\) \{.*?\n    \}',
    new_inject_dark_theme,
    content,
    count=1,
    flags=re.DOTALL
)
assert n_inject == 1, "injectDarkTheme-lohkoa ei löytynyt"

target_file.write_text(content, encoding="utf-8")
print("MainActivity.kt päivitetty onnistuneesti!")
