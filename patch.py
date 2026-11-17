#!/usr/bin/env python3
import os
import re


# ==============================================================================
# PYSYVÄ OSIO: Versionumeron automaattinen nosto (+1)
# ==============================================================================
def bump_version_code():
    gradle_path = "app/build.gradle.kts"
    if not os.path.exists(gradle_path):
        print(f"Ohitetaan: {gradle_path} ei löytynyt.")
        return

    with open(gradle_path, "r", encoding="utf-8") as f:
        content = f.read()

    def increment(match):
        old_code = int(match.group(1))
        new_code = old_code + 1
        print(f"Päivitetään versionCode: {old_code} -> {new_code}")
        return f"versionCode = {new_code}"

    updated, count = re.subn(r"versionCode\s*=\s*(\d+)", increment, content, count=1)
    if count > 0:
        with open(gradle_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated)


# ==============================================================================
# === POISTETTAVA KORJAUSOSIO ALKAA (Poista kun muutokset on ajettu) ===
# ==============================================================================
def replace_idempotent(content: str, old: str, new: str, label: str) -> str:
    if new in content:
        return content
    if old not in content:
        raise RuntimeError(f"Hakulohkoa ei löytynyt ({label})")
    return content.replace(old, new, 1)


def fix_webview_pages():
    main_path = "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt"
    with open(main_path, "r", encoding="utf-8") as f:
        main = f.read()
    orig_main = main

    old_kendo_css = """            .k-grid-header th.k-header, .k-grid-header th.k-header > .k-link {
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
            .k-list-container, .k-list, .k-dropdown, .k-dropdown-wrap, .k-picker-wrap, select, .k-animation-container {
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
            }
            .k-list .k-item:hover, .k-list .k-state-focused, .k-list .k-state-selected {
                background-color: #2A394A !important;
                color: #FFFFFF !important;
            }"""

    new_kendo_css = """            .k-grid {
                overflow-x: auto !important;
            }
            .k-grid-content {
                overflow-x: auto !important;
                -webkit-overflow-scrolling: touch !important;
            }
            .k-grid-header th.k-header,
            .k-grid-header th.k-header .k-link,
            .k-grid-header th.k-header .k-column-title,
            .k-grid-header th.k-header .k-grid-header-menu,
            .k-grid-header th.k-header .k-icon {
                background-color: #233040 !important;
                color: #F1F5F9 !important;
                border-color: #2A394A !important;
            }
            .k-grid-header th.k-header {
                padding: 10px 8px !important;
            }
            .k-checkbox,
            .k-grid input[type="checkbox"] {
                background-color: #111923 !important;
                border: 1px solid #38BDF8 !important;
                border-radius: 4px !important;
                width: 18px !important;
                height: 18px !important;
                appearance: auto !important;
                -webkit-appearance: checkbox !important;
            }
            .k-checkbox:checked {
                background-color: #1982C4 !important;
                border-color: #38BDF8 !important;
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
            .k-widget, .k-dropdown-wrap, .k-picker-wrap, .k-numeric-wrap, .k-select, .k-input,
            .k-picker, .k-dropdownlist, .k-input-inner, .k-input-value-text,
            .k-pager-wrap .k-link, .k-pager-info {
                background-color: #111923 !important;
                color: #F1F5F9 !important;
                border-color: #37475A !important;
            }
            .k-pager-wrap .k-picker,
            .k-pager-wrap .k-dropdownlist {
                min-width: 68px !important;
                height: 34px !important;
                display: inline-flex !important;
                align-items: center !important;
            }
            .k-pager-wrap .k-input-inner {
                padding: 4px 8px !important;
                display: flex !important;
                align-items: center !important;
            }
            .k-pager-wrap .k-input-value-text {
                color: #F1F5F9 !important;
                font-size: 13px !important;
                visibility: visible !important;
                opacity: 1 !important;
            }
            .k-input-button {
                background-color: #233040 !important;
                color: #F1F5F9 !important;
                border-left: 1px solid #37475A !important;
            }
            .k-list-container, .k-list, .k-dropdown, .k-dropdown-wrap, .k-picker-wrap,
            select, .k-animation-container, .k-popup, .k-list-ul, .k-calendar, .k-time-list-wrapper {
                background-color: #182332 !important;
                color: #F1F5F9 !important;
                border: 1px solid #2A394A !important;
            }
            .k-calendar-header, .k-calendar-view, .k-calendar td, .k-calendar th {
                background-color: #182332 !important;
                color: #F1F5F9 !important;
                border-color: #2A394A !important;
            }
            .k-calendar td.k-selected .k-link, .k-calendar td.k-state-selected .k-link {
                background-color: #1982C4 !important;
                color: #FFFFFF !important;
            }
            .k-list .k-item, .k-list-item, .k-time-list .k-item {
                color: #F1F5F9 !important;
                background-color: #182332 !important;
                padding: 10px 12px !important;
            }
            .k-list .k-item:hover, .k-list .k-state-focused, .k-list .k-state-selected,
            .k-list-item:hover, .k-list-item.k-hover, .k-list-item.k-selected, .k-list-item.k-focus {
                background-color: #2A394A !important;
                color: #FFFFFF !important;
            }

            /* === SELECT2 & TOIVEEN MUOKKAUS (/PersonRequests/Edit) === */
            .select2-container {
                width: 100% !important;
            }
            .select2-container--default .select2-selection--single {
                background-color: #111923 !important;
                border: 1px solid #37475A !important;
                border-radius: 8px !important;
                height: 40px !important;
                display: flex !important;
                align-items: center !important;
            }
            .select2-container--default .select2-selection--single .select2-selection__rendered {
                color: #F1F5F9 !important;
                line-height: 38px !important;
                padding-left: 12px !important;
                padding-right: 30px !important;
            }
            .select2-container--default .select2-selection--single .select2-selection__placeholder {
                color: #64748B !important;
            }
            .select2-container--default .select2-selection--single .select2-selection__arrow {
                height: 38px !important;
                right: 8px !important;
            }
            .select2-container--default .select2-selection--single .select2-selection__arrow b {
                border-color: #94A3B8 transparent transparent transparent !important;
            }
            .select2-dropdown {
                background-color: #182332 !important;
                border: 1px solid #37475A !important;
                border-radius: 8px !important;
                color: #F1F5F9 !important;
            }
            .select2-search--dropdown .select2-search__field {
                background-color: #111923 !important;
                color: #F1F5F9 !important;
                border: 1px solid #37475A !important;
                border-radius: 6px !important;
            }
            .select2-results__option {
                background-color: #182332 !important;
                color: #F1F5F9 !important;
                padding: 10px 12px !important;
            }
            .select2-container--default .select2-results__option--highlighted[aria-selected],
            .select2-container--default .select2-results__option--highlighted {
                background-color: #1982C4 !important;
                color: #FFFFFF !important;
            }
            .select2-container--default .select2-results__option[aria-selected="true"] {
                background-color: #233040 !important;
                color: #38BDF8 !important;
            }
            #FullDaySwitch,
            #SeriesRequestSwitch {
                min-width: 54px !important;
                height: 28px !important;
                border-radius: 14px !important;
                position: relative !important;
            }
            #FullDaySwitch:not(.active),
            #SeriesRequestSwitch:not(.active) {
                background-color: #233040 !important;
                border-color: #475569 !important;
            }
            #FullDaySwitch.active,
            #SeriesRequestSwitch.active {
                background-color: #1982C4 !important;
                border-color: #38BDF8 !important;
            }
            .input-group-addon {
                background-color: #233040 !important;
                border: 1px solid #37475A !important;
                color: #38BDF8 !important;
                border-radius: 0 8px 8px 0 !important;
            }
            .vismaicon-datepicker::before {
                content: "📅" !important;
                font-style: normal !important;
            }
            .vismaicon-time::before {
                content: "🕒" !important;
                font-style: normal !important;
            }
            hr {
                border-top: 1px solid #2A394A !important;
            }
            .editPageContainer table {
                width: 100% !important;
            }
            .editPageContainer td {
                padding-right: 6px !important;
            }
            #InfoTextArea {
                width: 100% !important;
            }
            .FooterPanel {
                display: flex !important;
                flex-direction: column !important;
                gap: 8px !important;
            }
            .FooterPanel .SubmitButton:not(.hidden) {
                width: 100% !important;
                margin: 0 !important;
                padding: 12px !important;
            }"""

    main = replace_idempotent(main, old_kendo_css, new_kendo_css, "Kendo & Select2 CSS")

    old_forgot_css = """            #forgotStampPanel {
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

    new_forgot_css = """            #forgotStampPanel,
            #forgotStampPanel.minimized,
            #forgotStampPanel[style*="top: 100%"],
            #forgotStampPanel[style*="top:100%"] {
                display: none !important;
            }
            #forgotStampPanel[style*="top:"]:not(.minimized):not([style*="top: 100%"]):not([style*="top:100%"]),
            #forgotStampPanel.force-open {
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
            }
            .drw-fog-of-war.showing {
                display: block !important;
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                right: 0 !important;
                bottom: 0 !important;
                background-color: rgba(0, 0, 0, 0.65) !important;
                z-index: 1040 !important;
            }"""

    main = replace_idempotent(main, old_forgot_css, new_forgot_css, "forgotStampPanel CSS")

    old_js_tail = """                if (!window._sessionWatchInstalled) {
                    window._sessionWatchInstalled = true;
                    setInterval(function() {
                        var modal = document.getElementById('session-expired-modal');
                        if (modal && (modal.classList.contains('in') || modal.classList.contains('show') || modal.style.display === 'block')) {
                            window.location.href = '/Login/Login';
                        }
                    }, 300);
                }"""

    new_js_tail = """                if (!window._sessionWatchInstalled) {
                    window._sessionWatchInstalled = true;
                    setInterval(function() {
                        var modal = document.getElementById('session-expired-modal');
                        if (modal && (modal.classList.contains('in') || modal.classList.contains('show') || modal.style.display === 'block')) {
                            window.location.href = '/Login/Login';
                        }
                    }, 300);
                }
                if (!window._forgotStampHelperInstalled) {
                    window._forgotStampHelperInstalled = true;
                    document.addEventListener('click', function(e) {
                        var btn = e.target && e.target.closest('#forgottenStampButton');
                        if (btn) {
                            setTimeout(function() {
                                var panel = document.getElementById('forgotStampPanel');
                                if (panel) {
                                    var topVal = panel.style.top || '';
                                    if (panel.classList.contains('minimized') || !topVal || topVal === '100%') {
                                        panel.classList.remove('minimized');
                                        panel.classList.add('force-open');
                                        panel.style.top = '0px';
                                    }
                                }
                            }, 350);
                        }
                        var cancelBtn = e.target && e.target.closest('#cancelPunchForgottenButton, #cancelPunchForgottenButtonHeader');
                        if (cancelBtn) {
                            var panel = document.getElementById('forgotStampPanel');
                            if (panel) {
                                panel.classList.remove('force-open');
                                panel.classList.add('minimized');
                                panel.style.top = '100%';
                            }
                        }
                    }, true);
                }"""

    main = replace_idempotent(main, old_js_tail, new_js_tail, "forgotStampPanel JS fallback")

    if main != orig_main:
        with open(main_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(main)
        print(f"Päivitetty: {main_path}")
    else:
        print(f"Jo ajan tasalla: {main_path}")
# ==============================================================================
# === POISTETTAVA KORJAUSOSIO PÄÄTTYY ===
# ==============================================================================


if __name__ == "__main__":
    bump_version_code()
    fix_webview_pages()
