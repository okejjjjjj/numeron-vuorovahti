#!/usr/bin/env python3
import os

def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    normalized = content.replace("\r\n", "\n")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(normalized)
    print(f"Päivitetty: {path}")

main_path = "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt"
if os.path.exists(main_path):
    with open(main_path, "r", encoding="utf-8") as f:
        code = f.read()

    # 1. Lisätään splash onCreate-vaiheeseen
    old_on_create = """        setupWebView()
        setupBottomBar()
        handleIncomingIntent(intent)"""

    new_on_create = """        setupWebView()
        setupBottomBar()
        handleIncomingIntent(intent)

        // Näytetään heti käynnistyksessä splash-ruutu "Kirjaudutaan..."
        startSnapshotTransition()"""

    if old_on_create in code:
        code = code.replace(old_on_create, new_on_create)

    # 2. Tyhjennetään evästeet onDestroyssa (kirjaudutaan ulos suljettaessa)
    old_ondestroy = """    override fun onDestroy() {
        super.onDestroy()
        scope.cancel()
    }"""

    new_ondestroy = """    override fun onDestroy() {
        super.onDestroy()
        try {
            CookieManager.getInstance().removeAllCookies(null)
            CookieManager.getInstance().flush()
        } catch (_: Exception) {}
        scope.cancel()
    }"""

    if old_ondestroy in code:
        code = code.replace(old_ondestroy, new_ondestroy)

    # 3. Korjataan #forgotStampPanel CSS
    target_forgot_panel = """            #forgotStampPanel {
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
            }"""

    replacement_forgot_panel = """            #forgotStampPanel {
                display: none !important;
            }
            #forgotStampPanel[style*="top: 0"], #forgotStampPanel[style*="top:0"], #forgotStampPanel[style*="display: block"], #forgotStampPanel[style*="display:block"] {
                display: block !important;
                position: fixed !important;
                left: 12px !important;
                right: 12px !important;
                bottom: 12px !important;
                top: auto !important;
                z-index: 1050 !important;
                background-color: #182332 !important;
                border: 1px solid #2A394A !important;
                border-radius: 14px !important;
                padding: 16px !important;
                box-shadow: 0 10px 25px rgba(0,0,0,0.5) !important;
                max-height: 85vh !important;
                overflow-y: auto !important;
                color: #F1F5F9 !important;
            }"""

    if target_forgot_panel in code:
        code = code.replace(target_forgot_panel, replacement_forgot_panel)

    # 4. Korjataan Kendo UI / Visman pudotusvalikoiden ja listojen tyylit
    kendo_css_target = """.k-list-container, .k-list, .k-calendar, .k-calendar .k-header {
                background-color: #1E293B !important;
                color: #F1F5F9 !important;
                border-color: #37475A !important;
            }"""

    kendo_css_replacement = """.k-list-container, .k-list, .k-dropdown, .k-dropdown-wrap, .k-picker-wrap, select, .k-animation-container {
                background-color: #182332 !important;
                color: #F1F5F9 !important;
                border: 1px solid #2A394A !important;
            }
            .k-list .k-item {
                color: #F1F5F9 !important;
                background-color: #182332 !important;
                padding: 10px 12px !important;
            }
            .k-list .k-item:hover, .k-list .k-state-selected, .k-list .k-state-focused {
                background-color: #233040 !important;
                color: #38BDF8 !important;
            }"""

    if kendo_css_target in code:
        code = code.replace(kendo_css_target, kendo_css_replacement)

    write_file(main_path, code)
    print("Kaikki korjaukset viety MainActivity.kt-tiedostoon onnistuneesti!")
