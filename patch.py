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


def main():
    path = find_file("MainActivity.kt")
    if not path:
        print("VIRHE: MainActivity.kt ei löytynyt.")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    old_nav = '''        if (DemoModeHelper.isDemoEnabled(this)) {
            startSnapshotTransition {
                webView.stopLoading()
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
            val url = when (tab) {
                Tab.STAMP -> "$baseUrl/WorktimeStamping"
                Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
                Tab.SHIFTS -> "$baseUrl/Calendar/Month"
            }
            startSnapshotTransition {
                webView.stopLoading()'''

    new_nav = '''        if (DemoModeHelper.isDemoEnabled(this)) {
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
            startSnapshotTransition {'''

    if old_nav not in src:
        print("VIRHE: navigateToTab-lohkoa ei löytynyt odotetussa muodossa.")
        sys.exit(1)

    src = src.replace(old_nav, new_nav, 1)

    old_err = '''            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: android.webkit.WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    endSnapshotTransition()
                }
            }'''

    new_err = '''            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: android.webkit.WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    endSnapshotTransition()
                    val code = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) error?.errorCode ?: 0 else 0
                    val desc = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) error?.description?.toString().orEmpty() else ""
                    if (code != android.webkit.WebViewClient.ERROR_UNKNOWN) {
                        Toast.makeText(this@MainActivity, "Sivun latausvirhe ($code): $desc", Toast.LENGTH_LONG).show()
                    }
                }
            }

            override fun onReceivedHttpError(
                view: WebView?,
                request: WebResourceRequest?,
                errorResponse: WebResourceResponse?
            ) {
                super.onReceivedHttpError(view, request, errorResponse)
                if (request?.isForMainFrame == true) {
                    endSnapshotTransition()
                    val status = errorResponse?.statusCode ?: 0
                    if (status >= 400) {
                        Toast.makeText(this@MainActivity, "Palvelinvirhe HTTP $status", Toast.LENGTH_LONG).show()
                    }
                }
            }'''

    if old_err in src:
        src = src.replace(old_err, new_err, 1)

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)

    print(f"Päivitetty: {path}")


if __name__ == "__main__":
    main()
