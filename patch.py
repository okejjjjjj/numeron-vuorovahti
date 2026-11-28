#!/usr/bin/env python3
"""
Numeron Vuorovahti (V2) – Vanhentuneen koodin siivous (patch_cleanup_fi.py):
- DemoModeHelper.kt: poistetaan vanhat WebView-HTML-generaattorit & DemoJsBridge
- MainActivity.kt: poistetaan käyttämättömät WebView-metodit (handleDemoAutoStamp, handleStampingPage,
  verifyStampAndClose, inFlightStampAction, DemoJsBridge, demo.local) & tiivistetään injectDarkTheme()
  vain WebView-lomakeoverlayn tarpeisiin
- QuickStampActivity.kt: poistetaan käyttämätön parseJsonResult-kopio & käyttämätön JSONTokener-import
  (piilotettu WebView-varapolku säilytetään turvaverkkona)
- app/build.gradle.kts: versionCode 126 -> 127, versionName "3.2.184" -> "3.2.185"
"""

import re
import sys
from pathlib import Path

CLEAN_DEMO_MODE_HELPER_KT = 'package fi.numeron.vuorovahti\n\nimport android.content.Context\nimport java.time.LocalDate\nimport java.time.LocalDateTime\nimport java.time.LocalTime\nimport java.util.Locale\n\nobject DemoModeHelper {\n\n    fun isDemoCredentials(org: String, user: String, pass: String): Boolean {\n        val cleanOrg = org.trim().trimEnd(\'/\')\n        val isDemoOrg = cleanOrg.equals("demo", ignoreCase = true) ||\n            cleanOrg.equals("demo.numeronwfm.com", ignoreCase = true) ||\n            cleanOrg.equals("https://demo.numeronwfm.com", ignoreCase = true)\n        return isDemoOrg &&\n            user.trim().equals("demo", ignoreCase = true) &&\n            pass.trim().equals("demo", ignoreCase = true)\n    }\n\n    fun isDemoEnabled(context: Context): Boolean {\n        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n        val org = (prefs.getString("org_raw_input", "") ?: "").trim()\n        val serverUrl = (prefs.getString("server_url", "") ?: "").trim()\n        val user = (SecureCredentialManager.getUsername(context) ?: "").trim()\n        val pass = SecureCredentialManager.getPassword(context) ?: ""\n\n        if (user.isEmpty() || pass.isEmpty() || (org.isEmpty() && serverUrl.isEmpty())) {\n            return true\n        }\n        if (UrlNormalizer.isDemoInput(org) || UrlNormalizer.isDemoInput(serverUrl)) {\n            return true\n        }\n        return isDemoCredentials(org.ifEmpty { serverUrl }, user, pass)\n    }\n\n    fun isEnglish(context: Context): Boolean {\n        if (isDemoEnabled(context)) {\n            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n            when (prefs.getString("demo_language", null)) {\n                "en" -> return true\n                "fi" -> return false\n            }\n        }\n        val sysLang = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.N) {\n            context.resources.configuration.locales.get(0)?.language ?: Locale.getDefault().language\n        } else {\n            @Suppress("DEPRECATION")\n            context.resources.configuration.locale?.language ?: Locale.getDefault().language\n        }\n        return !sysLang.equals("fi", ignoreCase = true)\n    }\n\n    fun setDemoLanguage(context: Context, lang: String) {\n        val normalized = if (lang.equals("en", ignoreCase = true)) "en" else "fi"\n        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n            .edit()\n            .putString("demo_language", normalized)\n            .apply()\n    }\n\n    fun generateDemoWorkShifts(context: Context): List<WorkShift> {\n        val en = isEnglish(context)\n        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n        val variant = prefs.getInt("demo_shift_variant", 0)\n        val today = LocalDate.now()\n\n        val shiftTitle = if (en) "Work Shift" else "Työvuoro"\n        val unitName = if (en) "Central Care Unit Helmi" else "Keskusyksikkö Helmi"\n        val morningDesc = if (en) "Morning • Nurse" else "Aamu • Hoitaja"\n        val eveningDesc = if (en) "Evening • Nurse" else "Ilta • Hoitaja"\n        val nightDesc = if (en) "Night • Nurse" else "Yö • Hoitaja"\n        val leaveTitle = if (en) "Annual Leave (Demo)" else "Vuosiloma (Demo)"\n\n        return if (variant % 2 == 0) {\n            listOf(\n                WorkShift(shiftTitle, LocalDateTime.of(today.plusDays(1), LocalTime.of(7, 0)), LocalDateTime.of(today.plusDays(1), LocalTime.of(15, 0)), false, unitName, morningDesc),\n                WorkShift(shiftTitle, LocalDateTime.of(today.plusDays(2), LocalTime.of(13, 0)), LocalDateTime.of(today.plusDays(2), LocalTime.of(21, 0)), false, unitName, eveningDesc),\n                WorkShift(shiftTitle, LocalDateTime.of(today.plusDays(3), LocalTime.of(21, 0)), LocalDateTime.of(today.plusDays(4), LocalTime.of(7, 0)), false, unitName, nightDesc),\n                WorkShift(leaveTitle, today.plusDays(5).atStartOfDay(), today.plusDays(7).atStartOfDay(), true)\n            )\n        } else {\n            listOf(\n                WorkShift(shiftTitle, LocalDateTime.of(today.plusDays(1), LocalTime.of(13, 0)), LocalDateTime.of(today.plusDays(1), LocalTime.of(21, 0)), false, unitName, eveningDesc),\n                WorkShift(shiftTitle, LocalDateTime.of(today.plusDays(2), LocalTime.of(13, 0)), LocalDateTime.of(today.plusDays(2), LocalTime.of(21, 0)), false, unitName, eveningDesc),\n                WorkShift(shiftTitle, LocalDateTime.of(today.plusDays(4), LocalTime.of(7, 0)), LocalDateTime.of(today.plusDays(4), LocalTime.of(15, 0)), false, unitName, morningDesc),\n                WorkShift(leaveTitle, today.plusDays(5).atStartOfDay(), today.plusDays(7).atStartOfDay(), true)\n            )\n        }\n    }\n}\n'

SLIM_INJECT_DARK_THEME_KT = '    private fun injectDarkTheme(view: WebView?, forceDomInit: Boolean = false) {\n        val currentUrl = view?.url\n        val nowMs = System.currentTimeMillis()\n        if (!forceDomInit && !currentUrl.isNullOrEmpty() && currentUrl == lastThemedUrl && (nowMs - lastThemedAtMs) < 1500L) {\n            return\n        }\n        lastThemedUrl = currentUrl\n        lastThemedAtMs = nowMs\n\n        val themePrefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n        val morningRgb = themePrefs.getInt("color_morning_rgb", SettingsDialogHelper.DEFAULT_MORNING_RGB)\n        val eveningRgb = themePrefs.getInt("color_evening_rgb", SettingsDialogHelper.DEFAULT_EVENING_RGB)\n        val nightRgb = themePrefs.getInt("color_night_rgb", SettingsDialogHelper.DEFAULT_NIGHT_RGB)\n        fun rgbToHex(rgb: Int): String = String.format("#%06X", 0xFFFFFF and rgb)\n        val morningBg = rgbToHex(morningRgb)\n        val eveningBg = rgbToHex(eveningRgb)\n        val nightBg = rgbToHex(nightRgb)\n        val colorCacheKey = "$morningBg|$eveningBg|$nightBg"\n\n        val safeCss = cachedSafeDarkCss ?: """\n            /* === 1. PERUSRUNKO JA PIILOTETTAVAT ELEMENTIT === */\n            html, body {\n                background-color: #0F1722 !important;\n                background-image: none !important;\n                color: #F1F5F9 !important;\n                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;\n                margin: 0 !important;\n                padding: 0 !important;\n            }\n            header, nav.navbar, footer, .footer, .copyright, .loginnav, .bottom-nav, .fade-in-box, .fade-out-box {\n                display: none !important;\n            }\n            .container, .container-fluid {\n                padding: 12px !important;\n                width: 100% !important;\n                max-width: 100% !important;\n            }\n            h1, h2, h3, h4, .h1, .h2, .h3, .h4 {\n                color: #F1F5F9 !important;\n                font-size: 20px !important;\n                font-weight: 600 !important;\n                margin-top: 4px !important;\n                margin-bottom: 12px !important;\n            }\n            .container h1, .container-fluid h1, .container .h1, .container-fluid .h1 {\n                display: none !important;\n            }\n            label, span, p, div { color: inherit; }\n            a { color: #38BDF8 !important; }\n            hr { border-top: 1px solid #2A394A !important; }\n\n            /* === 2. KORTIT, SYÖTTÖKENTÄT, PAINIKKEET JA MODAALIT === */\n            .panel, .panel-default, .whitebox, .card, .box, .panel-footer, .form-actions {\n                background-color: #182332 !important;\n                border: 1px solid #2A394A !important;\n                border-radius: 12px !important;\n                color: #F1F5F9 !important;\n                box-shadow: none !important;\n                margin-bottom: 14px !important;\n            }\n            .panel-body { padding: 14px !important; }\n            .panel-heading, .modal-header, .modal-footer {\n                background-color: #1E293B !important;\n                border-color: #2A394A !important;\n                color: #F1F5F9 !important;\n            }\n            .modal-content {\n                background-color: #182332 !important;\n                border: 1px solid #37475A !important;\n                color: #F1F5F9 !important;\n            }\n            input, select, textarea, .form-control, .k-textbox {\n                background-color: #111923 !important;\n                color: #FFFFFF !important;\n                border: 1px solid #37475A !important;\n                border-radius: 8px !important;\n                box-shadow: none !important;\n            }\n            input[type="checkbox"], input[type="radio"] {\n                accent-color: #1982C4 !important;\n                width: 18px !important;\n                height: 18px !important;\n            }\n            input::placeholder, textarea::placeholder { color: #64748B !important; }\n            .btn, .btn-default {\n                background-color: #233040 !important;\n                color: #F1F5F9 !important;\n                border: 1px solid #37475A !important;\n                border-radius: 8px !important;\n                padding: 8px 14px !important;\n                font-weight: 500 !important;\n            }\n            .btn-primary {\n                background-color: #1982C4 !important;\n                border-color: #1982C4 !important;\n                color: #FFFFFF !important;\n                font-weight: 600 !important;\n            }\n            .btn-text, .btn-link {\n                background-color: transparent !important;\n                border: none !important;\n                color: #38BDF8 !important;\n                padding: 6px 0 !important;\n            }\n            .dropdown-menu {\n                background-color: #1E293B !important;\n                border: 1px solid #37475A !important;\n                border-radius: 8px !important;\n            }\n            .dropdown-menu > li > a {\n                color: #F1F5F9 !important;\n                padding: 8px 14px !important;\n            }\n            .dropdown-menu > li > a:hover, .dropdown-menu > li > a:focus {\n                background-color: #2A394A !important;\n                color: #FFFFFF !important;\n            }\n            .dropdown-header { color: #94A3B8 !important; }\n            .alert-danger { background-color: #3F1D24 !important; border-color: #DC2626 !important; color: #FEE2E2 !important; }\n            .alert-warning { background-color: #3B2810 !important; border-color: #F59E0B !important; color: #FEF3C7 !important; }\n            .alert-success { background-color: #0F2E26 !important; border-color: #10B981 !important; color: #D1FAE5 !important; }\n            .alert-info { background-color: #1E3A5F !important; border-color: #38BDF8 !important; color: #E0F2FE !important; }\n            .modal-header .close, .alert .close, button.close {\n                color: #F1F5F9 !important;\n                text-shadow: none !important;\n                opacity: 0.85 !important;\n            }\n\n            /* === 3. KIRJAUTUMISSIVU (/Login/Login) === */\n            .content { padding: 16px !important; float: none !important; margin: 0 auto !important; }\n            .blurbox h1 {\n                display: block !important;\n                text-align: center !important;\n                font-size: 28px !important;\n                font-weight: 700 !important;\n                margin: 28px 0 20px 0 !important;\n                color: #F1F5F9 !important;\n            }\n            .whitebox { padding: 20px !important; margin: 0 auto !important; }\n            .whitebox img, .whitebox hr { display: none !important; }\n            #LoginForm .form-group { margin-bottom: 14px !important; }\n            #LoginForm .pull-left, #LoginForm .pull-right { margin-bottom: 12px !important; font-size: 13px !important; }\n            #LoginForm input[type="submit"] { margin-top: 8px !important; padding: 12px !important; font-size: 16px !important; }\n\n            /* === 4. PUUTTUVA / MUOKATTAVA LEIMAUS (#forgotStampPanel & KENDO PICKER) === */\n            .forgotten-stamp-labels {\n                color: #CBD5E1 !important;\n                font-size: 13px !important;\n                margin-top: 10px !important;\n                margin-bottom: 4px !important;\n            }\n            #dropdownMenu2, #dropdownMenuStampDirection {\n                width: 100% !important;\n                display: flex !important;\n                justify-content: space-between !important;\n                align-items: center !important;\n                background-color: #111923 !important;\n            }\n            #forgotStampPanel:not(.force-open) { display: none !important; }\n            #forgotStampPanel.force-open {\n                display: block !important;\n                position: fixed !important;\n                left: 12px !important;\n                right: 12px !important;\n                bottom: 12px !important;\n                top: auto !important;\n                z-index: 1050 !important;\n                background-color: #182332 !important;\n                border: 1px solid #2A394A !important;\n                border-radius: 14px !important;\n                padding: 16px !important;\n                box-shadow: 0 10px 25px rgba(0,0,0,0.5) !important;\n                max-height: 85vh !important;\n                overflow-y: auto !important;\n                color: #F1F5F9 !important;\n            }\n            .drw-fog-of-war.showing {\n                display: block !important;\n                position: fixed !important;\n                inset: 0 !important;\n                background-color: rgba(0, 0, 0, 0.65) !important;\n                z-index: 1040 !important;\n            }\n            #waitPunch, .fog-of-war-punch, #wait, .container .fog-of-war { display: none !important; }\n            .k-widget, .k-dropdown-wrap, .k-picker-wrap, .k-numeric-wrap, .k-select, .k-input,\n            .k-picker, .k-dropdownlist, .k-input-inner, .k-input-value-text {\n                background-color: #111923 !important;\n                color: #F1F5F9 !important;\n                border-color: #37475A !important;\n            }\n            .k-input-button {\n                background-color: #233040 !important;\n                color: #F1F5F9 !important;\n                border-left: 1px solid #37475A !important;\n            }\n            .k-list-container, .k-list, .k-animation-container, .k-popup, .k-list-ul, .k-calendar, .k-time-list-wrapper {\n                background-color: #182332 !important;\n                color: #F1F5F9 !important;\n                border: 1px solid #2A394A !important;\n            }\n            .k-calendar-header, .k-calendar-view, .k-calendar td, .k-calendar th {\n                background-color: #182332 !important;\n                color: #F1F5F9 !important;\n                border-color: #2A394A !important;\n            }\n            .k-calendar td.k-selected .k-link, .k-calendar td.k-state-selected .k-link {\n                background-color: #1982C4 !important;\n                color: #FFFFFF !important;\n            }\n            .k-list .k-item, .k-list-item, .k-time-list .k-item {\n                color: #F1F5F9 !important;\n                background-color: #182332 !important;\n                padding: 10px 12px !important;\n            }\n            .k-list .k-item:hover, .k-list .k-state-focused, .k-list .k-state-selected,\n            .k-list-item:hover, .k-list-item.k-hover, .k-list-item.k-selected, .k-list-item.k-focus {\n                background-color: #2A394A !important;\n                color: #FFFFFF !important;\n            }\n\n            /* === 5. TOIVEEN LISÄYS JA MUOKKAUS (/PersonRequests/Edit) === */\n            .select2-container { width: 100% !important; }\n            .select2-container--default .select2-selection--single {\n                background-color: #111923 !important;\n                border: 1px solid #37475A !important;\n                border-radius: 8px !important;\n                height: 40px !important;\n                display: flex !important;\n                align-items: center !important;\n            }\n            .select2-container--default .select2-selection--single .select2-selection__rendered {\n                color: #F1F5F9 !important;\n                line-height: 38px !important;\n                padding-left: 12px !important;\n                padding-right: 30px !important;\n            }\n            .select2-container--default .select2-selection--single .select2-selection__placeholder { color: #64748B !important; }\n            .select2-container--default .select2-selection--single .select2-selection__arrow { height: 38px !important; right: 8px !important; }\n            .select2-container--default .select2-selection--single .select2-selection__arrow b { border-color: #94A3B8 transparent transparent transparent !important; }\n            .select2-dropdown {\n                background-color: #182332 !important;\n                border: 1px solid #37475A !important;\n                border-radius: 8px !important;\n                color: #F1F5F9 !important;\n            }\n            .select2-search--dropdown .select2-search__field {\n                background-color: #111923 !important;\n                color: #F1F5F9 !important;\n                border: 1px solid #37475A !important;\n                border-radius: 6px !important;\n            }\n            .select2-results__option { background-color: #182332 !important; color: #F1F5F9 !important; padding: 10px 12px !important; }\n            .select2-container--default .select2-results__option--highlighted[aria-selected],\n            .select2-container--default .select2-results__option--highlighted { background-color: #1982C4 !important; color: #FFFFFF !important; }\n            .select2-container--default .select2-results__option[aria-selected="true"] { background-color: #233040 !important; color: #38BDF8 !important; }\n            #FullDaySwitch, #SeriesRequestSwitch {\n                min-width: 54px !important;\n                height: 28px !important;\n                border-radius: 14px !important;\n                position: relative !important;\n            }\n            #FullDaySwitch:not(.active), #SeriesRequestSwitch:not(.active) { background-color: #233040 !important; border-color: #475569 !important; }\n            #FullDaySwitch.active, #SeriesRequestSwitch.active { background-color: #1982C4 !important; border-color: #38BDF8 !important; }\n            #FullDaySwitch::after, #SeriesRequestSwitch::after {\n                content: "" !important;\n                position: absolute !important;\n                top: 3px !important;\n                left: 4px !important;\n                width: 20px !important;\n                height: 20px !important;\n                border-radius: 50% !important;\n                background-color: #F1F5F9 !important;\n                transition: left 0.15s ease !important;\n            }\n            #FullDaySwitch.active::after, #SeriesRequestSwitch.active::after { left: 28px !important; }\n            .bootstrap-datetimepicker-widget, .bootstrap-datetimepicker-widget.dropdown-menu {\n                background-color: #182332 !important;\n                color: #F1F5F9 !important;\n                border: 1px solid #37475A !important;\n            }\n            .bootstrap-datetimepicker-widget table td, .bootstrap-datetimepicker-widget table th {\n                color: #F1F5F9 !important;\n                background-color: transparent !important;\n            }\n            .bootstrap-datetimepicker-widget table td.day:hover,\n            .bootstrap-datetimepicker-widget table td.hour:hover,\n            .bootstrap-datetimepicker-widget table td.minute:hover,\n            .bootstrap-datetimepicker-widget table th:hover { background-color: #2A394A !important; color: #FFFFFF !important; }\n            .bootstrap-datetimepicker-widget table td.active,\n            .bootstrap-datetimepicker-widget table td.active:hover { background-color: #1982C4 !important; color: #FFFFFF !important; }\n            .bootstrap-datetimepicker-widget table td.old,\n            .bootstrap-datetimepicker-widget table td.new { color: #64748B !important; }\n            .input-group-addon {\n                background-color: #233040 !important;\n                border: 1px solid #37475A !important;\n                color: #38BDF8 !important;\n                border-radius: 0 8px 8px 0 !important;\n            }\n            .vismaicon-datepicker::before { content: "📅" !important; font-style: normal !important; }\n            .vismaicon-time::before { content: "🕒" !important; font-style: normal !important; }\n            .editPageContainer table { width: 100% !important; }\n            .editPageContainer td { padding-right: 6px !important; }\n            #InfoTextArea { width: 100% !important; }\n            .FooterPanel { display: flex !important; flex-direction: column !important; gap: 8px !important; }\n            .FooterPanel .SubmitButton:not(.hidden) { width: 100% !important; margin: 0 !important; padding: 12px !important; }\n\n            /* === 6. KALENTERIN PÄIVÄLUETTELO (/Calendar/List) === */\n            .schedule-content #calendar-content {\n                height: calc(100vh - 115px) !important;\n                overflow-y: auto !important;\n                -webkit-overflow-scrolling: touch !important;\n            }\n            .schedule-week-separator { margin: 14px 0 8px 0 !important; padding: 4px 2px !important; border-bottom: 1px solid #2A394A !important; }\n            .schedule-week-separator-text { color: #38BDF8 !important; font-size: 13px !important; font-weight: 700 !important; text-transform: uppercase !important; letter-spacing: 0.05em !important; }\n            .schedule-day-container { background-color: #182332 !important; border: 1px solid #2A394A !important; border-radius: 12px !important; padding: 12px !important; margin-bottom: 10px !important; }\n            .schedule-day-information { display: flex !important; align-items: center !important; margin-bottom: 8px !important; padding-bottom: 6px !important; border-bottom: 1px solid #233040 !important; }\n            .schedule-day { color: #94A3B8 !important; font-size: 12px !important; font-weight: 700 !important; letter-spacing: 0.04em !important; }\n            .schedule-day-date { color: #F1F5F9 !important; font-size: 14px !important; font-weight: 700 !important; }\n            .schedule-item-container {\n                display: flex !important;\n                align-items: stretch !important;\n                background-color: #111923 !important;\n                border: 1px solid #2A394A !important;\n                border-left: 4px solid #0284C7 !important;\n                border-radius: 8px !important;\n                padding: 10px !important;\n                margin-bottom: 8px !important;\n            }\n            .schedule-item-container.schedule-item-absence { border-left-color: #F59E0B !important; }\n            .schedule-item-container.schedule-item-request { border-left-color: #8B5CF6 !important; }\n            .schedule-item-container.schedule-item-opportunity { border-left-color: #10B981 !important; }\n            .schedule-item-color-bar, .schedule-item-icon-td, .clear-float { display: none !important; }\n            .schedule-item-content { width: 100% !important; }\n            .schedule-item-body { display: flex !important; flex-direction: column !important; gap: 4px !important; }\n            .schedule-item-times { color: #38BDF8 !important; font-size: 15px !important; font-weight: 700 !important; }\n            .schedule-item-description-table { width: 100% !important; }\n            .schedule-item-description-heading { color: #F1F5F9 !important; font-size: 14px !important; font-weight: 600 !important; }\n            .schedule-item-description-subheading { color: #94A3B8 !important; font-size: 12px !important; margin-top: 2px !important; }\n            .schedule-day-content > div[style*="max-height"] { max-height: none !important; margin-top: 6px !important; }\n            .schedule-add-button { display: inline-block !important; color: #38BDF8 !important; font-size: 13px !important; font-weight: 600 !important; padding: 4px 0 !important; cursor: pointer !important; }\n            .schedule-add-options { margin-top: 6px !important; display: flex !important; gap: 8px !important; }\n            .schedule-option-link { background-color: #233040 !important; border: 1px solid #37475A !important; border-radius: 6px !important; padding: 6px 10px !important; font-size: 13px !important; text-decoration: none !important; }\n            .mobileAddDiv { display: flex !important; justify-content: space-between !important; align-items: center !important; margin-top: 10px !important; padding: 4px 0 !important; }\n            .mobileAddButton, .filterButton {\n                background-color: #233040 !important;\n                color: #F1F5F9 !important;\n                border: 1px solid #37475A !important;\n                border-radius: 8px !important;\n                padding: 8px 14px !important;\n                text-decoration: none !important;\n                display: inline-block !important;\n            }\n            #mobileViewDropdown { margin-top: 8px !important; }\n        """.trimIndent()\n            .replace("\\r", " ")\n            .replace("\\n", " ")\n            .replace("\\\\", "\\\\\\\\")\n            .replace("\'", "\\\\\'")\n            .also { cachedSafeDarkCss = it }\n\n        val js = """\n            (function() {\n                var style = document.getElementById(\'custom-dark-theme\');\n                if (!style) {\n                    style = document.createElement(\'style\');\n                    style.id = \'custom-dark-theme\';\n                }\n                var targetParent = document.head || document.documentElement;\n                if (targetParent && style.parentNode !== targetParent) {\n                    targetParent.appendChild(style);\n                }\n                if (style.getAttribute(\'data-vv-colors\') !== \'$colorCacheKey\' || !style.textContent) {\n                    style.setAttribute(\'data-vv-colors\', \'$colorCacheKey\');\n                    style.textContent = \'$safeCss\';\n                }\n\n                // === ISTUNNON VANHENEMISEN VALVONTA ===\n                if (!window._sessionWatchInstalled) {\n                    window._sessionWatchInstalled = true;\n                    function checkSessionModal() {\n                        if (window._sessionExpiredHandled) return;\n                        var expired = false;\n                        var soonModal = null;\n                        var candidates = document.querySelectorAll(\'#session-expired-modal, #sessionExpiredModal, #SessionExpiredModal, #session-expiring-soon-modal, .modal, [role="dialog"]\');\n                        for (var i = 0; i < candidates.length; i++) {\n                            var m = candidates[i];\n                            var st = window.getComputedStyle(m);\n                            var vis = (m.offsetParent !== null) || (st && st.display !== \'none\' && st.visibility !== \'hidden\' && parseFloat(st.opacity || \'1\') > 0);\n                            if (!vis) continue;\n                            var txt = (m.innerText || m.textContent || \'\').toLowerCase();\n                            if (m.id === \'session-expired-modal\' || m.id === \'sessionExpiredModal\' || txt.indexOf(\'istunto vanhentunut\') !== -1 || txt.indexOf(\'session expired\') !== -1) {\n                                expired = true;\n                                break;\n                            }\n                            if (m.id === \'session-expiring-soon-modal\' || txt.indexOf(\'istunto päättyy pian\') !== -1) {\n                                soonModal = m;\n                            }\n                        }\n                        if (expired) {\n                            window._sessionExpiredHandled = true;\n                            if (window.SessionBridge && typeof window.SessionBridge.onSessionExpired === \'function\') {\n                                window.SessionBridge.onSessionExpired();\n                            } else {\n                                window.location.href = \'/Login/Login\';\n                            }\n                        } else if (soonModal && !window._sessionExpiringHandled) {\n                            window._sessionExpiringHandled = true;\n                            try {\n                                if (typeof window.HideSessionExpirationSoonNotify === \'function\') {\n                                    window.HideSessionExpirationSoonNotify();\n                                }\n                                if (window.jQuery) {\n                                    window.jQuery(soonModal).modal(\'hide\');\n                                } else {\n                                    soonModal.style.display = \'none\';\n                                }\n                            } catch (_err) {}\n                            if (window.SessionBridge && typeof window.SessionBridge.onSessionExpiringSoon === \'function\') {\n                                window.SessionBridge.onSessionExpiringSoon();\n                            }\n                        }\n                    }\n                    window._vvCheckSessionModal = checkSessionModal;\n                    checkSessionModal();\n                }\n                if (window._vvCheckSessionModal && document.body && !document.body._vvSessionObs && typeof MutationObserver !== \'undefined\') {\n                    document.body._vvSessionObs = true;\n                    new MutationObserver(window._vvCheckSessionModal).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: [\'style\', \'class\'] });\n                }\n\n                // === PUUTTUVAN / MUOKATTAVAN LEIMAUKSEN PANEELIN TUKI ===\n                if (!window._forgotStampHelperInstalled) {\n                    window._forgotStampHelperInstalled = true;\n                    function getForgotPanel() {\n                        return document.getElementById(\'forgotStampPanel\') || document.querySelector(\'[id*="forgotStampPanel" i], [id*="ForgotStampPanel" i]\');\n                    }\n                    function openForgotPanel() {\n                        var panel = getForgotPanel();\n                        if (panel) {\n                            panel.classList.remove(\'minimized\', \'hidden\', \'hide\');\n                            panel.classList.add(\'force-open\');\n                            panel.style.top = \'10%\';\n                            panel.style.display = \'block\';\n                        }\n                        var fog = document.querySelector(\'.drw-fog-of-war\');\n                        if (fog) {\n                            fog.classList.add(\'showing\');\n                            fog.style.display = \'block\';\n                        }\n                    }\n                    function closeForgotPanel() {\n                        var panel = getForgotPanel();\n                        if (panel) {\n                            panel.classList.remove(\'force-open\');\n                            panel.classList.add(\'minimized\');\n                            panel.style.top = \'100%\';\n                            panel.style.display = \'none\';\n                        }\n                        var fog = document.querySelector(\'.drw-fog-of-war\');\n                        if (fog) {\n                            fog.classList.remove(\'showing\');\n                            fog.style.display = \'none\';\n                        }\n                    }\n                    document.addEventListener(\'click\', function(e) {\n                        var openBtn = e.target && e.target.closest(\'#forgottenStampButton, #table-latest-stamps tbody tr\');\n                        if (openBtn && !e.target.closest(\'#forgotStampPanel\')) {\n                            openForgotPanel();\n                            setTimeout(openForgotPanel, 80);\n                            setTimeout(openForgotPanel, 250);\n                            return;\n                        }\n                        var cancelBtn = e.target && e.target.closest(\'#cancelPunchForgottenButton, #cancelPunchForgottenButtonHeader, .drw-fog-of-war\');\n                        if (cancelBtn) {\n                            closeForgotPanel();\n                        }\n                    }, true);\n                    window._vvOpenForgotPanel = openForgotPanel;\n                }\n\n                // === AJAX- JA FETCH-ISTUNTOVALVONTA ===\n                if (!window._ajaxSessionGuardInstalled) {\n                    window._ajaxSessionGuardInstalled = true;\n                    function triggerSessionRefreshOnce() {\n                        if (window._sessionExpiredHandled) return;\n                        window._sessionExpiredHandled = true;\n                        if (window.SessionBridge && typeof window.SessionBridge.onSessionExpired === \'function\') {\n                            window.SessionBridge.onSessionExpired();\n                        }\n                    }\n                    if (window.XMLHttpRequest) {\n                        var origSend = XMLHttpRequest.prototype.send;\n                        XMLHttpRequest.prototype.send = function() {\n                            this.addEventListener(\'load\', function() {\n                                try {\n                                    var respUrl = (this.responseURL || \'\').toLowerCase();\n                                    var bodyText = (typeof this.responseText === \'string\') ? this.responseText : \'\';\n                                    if (this.status === 401 || this.status === 403 || respUrl.indexOf(\'/login\') !== -1 || bodyText.indexOf(\'id="LoginForm"\') !== -1) {\n                                        triggerSessionRefreshOnce();\n                                    }\n                                } catch (_err) {}\n                            });\n                            return origSend.apply(this, arguments);\n                        };\n                    }\n                    if (typeof window.fetch === \'function\') {\n                        var origFetch = window.fetch;\n                        window.fetch = function() {\n                            return origFetch.apply(this, arguments).then(function(response) {\n                                try {\n                                    var rUrl = (response && response.url ? response.url : \'\').toLowerCase();\n                                    if (response && (response.status === 401 || response.status === 403 || rUrl.indexOf(\'/login\') !== -1)) {\n                                        triggerSessionRefreshOnce();\n                                    }\n                                } catch (_err) {}\n                                return response;\n                            });\n                        };\n                    }\n                }\n\n                // === PÄIVÄLUETTELON (/Calendar/List) SIISTINTÄ JA VÄRIKOODAUS ===\n                if (window.location.pathname.toLowerCase().indexOf(\'/calendar/list\') !== -1) {\n                    var ignoreRegex = /^(vapaa|vapaapäivä|arkipyhä|arkipyhävapaa|viikkolepo|viikkovapaa|tasausvapaa|saldovapaa|pekkanen|pekkaspäivä|ei\\s+(suunniteltuja\\s+töitä|(työ)?vuoroa))(?=$|[\\s,.:;!?()\\-–—])/i;\n                    function styleListView() {\n                        var absBoxes = document.querySelectorAll(\'.schedule-item-container.schedule-item-absence:not([data-vv-done])\');\n                        for (var i = 0; i < absBoxes.length; i++) {\n                            var box = absBoxes[i];\n                            box.setAttribute(\'data-vv-done\', \'1\');\n                            var heading = box.querySelector(\'.schedule-item-description-heading\');\n                            var title = heading ? (heading.textContent || \'\').replace(/\\s+/g, \' \').trim() : \'\';\n                            if (!title || ignoreRegex.test(title)) {\n                                box.style.display = \'none\';\n                            } else if (/sairaus|hoitovapaa/i.test(title)) {\n                                box.style.setProperty(\'background-color\', \'#3F1D24\', \'important\');\n                                box.style.setProperty(\'border-left-color\', \'#EF4444\', \'important\');\n                            } else if (/loma|säästövapaa|lomarahavapaa/i.test(title)) {\n                                box.style.setProperty(\'background-color\', \'#122B22\', \'important\');\n                                box.style.setProperty(\'border-left-color\', \'#22C55E\', \'important\');\n                            }\n                        }\n                        var workBoxes = document.querySelectorAll(\'.schedule-item-container.schedule-item-work\');\n                        for (var j = 0; j < workBoxes.length; j++) {\n                            var ltEl = workBoxes[j].querySelector(\'.schedule-item-times\');\n                            var m = (ltEl ? (ltEl.textContent || \'\') : \'\').match(/(\\d{1,2}):(\\d{2})\\s*[-–—]\\s*(\\d{1,2}):(\\d{2})/);\n                            if (m) {\n                                var sMin = parseInt(m[1], 10) * 60 + parseInt(m[2], 10);\n                                var eMin = parseInt(m[3], 10) * 60 + parseInt(m[4], 10);\n                                var col = (eMin < sMin || sMin >= 20 * 60 || sMin < 4 * 60) ? \'$nightBg\' : (sMin >= 11 * 60 + 30 ? \'$eveningBg\' : \'$morningBg\');\n                                workBoxes[j].style.setProperty(\'border-left-color\', col, \'important\');\n                            }\n                        }\n                    }\n                    styleListView();\n                }\n            })();\n        """.trimIndent()\n\n        view?.evaluateJavascript(js, null)\n    }'


def find_file(filename: str) -> Path | None:
    candidates = [
        Path("app/src/main/java/fi/numeron/vuorovahti") / filename,
        Path("src/main/java/fi/numeron/vuorovahti") / filename,
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


def replace_once(content: str, old: str, new: str, label: str) -> str:
    if new and new in content and old not in content:
        print(f"  [OK - jo sovellettu] {label}")
        return content
    if old not in content:
        print(f"  [OK - jo poistettu] {label}")
        return content
    print(f"  [SIIVOTTU] {label}")
    return content.replace(old, new, 1)


def patch_demo_mode_helper(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    target = CLEAN_DEMO_MODE_HELPER_KT.strip() + "\n"
    if text.strip() == target.strip():
        print("  [OK - jo siivottu] DemoModeHelper.kt")
        return False
    write_text_keep_nl(path, target, nl)
    print(f"  [SIIVOTTU] DemoModeHelper.kt ({len(text.splitlines())} -> {len(target.splitlines())} riviä)")
    return True


def patch_main_activity(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    old_inflight_block = """        if (inFlightStampAction == Action.STAMP_IN || inFlightStampAction == Action.STAMP_OUT) {
            pendingAction = inFlightStampAction
            inFlightStampAction = Action.NONE
            Toast.makeText(this, if (DemoModeHelper.isEnglish(this)) "Session expired – re-authenticating and stamping..." else "Istunto vanhentunut – kirjaudutaan uudelleen ja leimataan...", Toast.LENGTH_SHORT).show()
        }

"""
    text = replace_once(text, old_inflight_block, "", "Poistettu inFlightStampAction-lohko handleWebSessionExpiredistä")
    text = replace_once(
        text,
        "    private var inFlightStampAction: Action = Action.NONE\n",
        "",
        "Poistettu käyttämätön inFlightStampAction-kenttä"
    )
    text = text.replace("            inFlightStampAction = Action.NONE\n", "")

    old_demo_bridge = """        wv.addJavascriptInterface(
            DemoModeHelper.DemoJsBridge(
                context = this,
                onReloadNeeded = { runOnUiThread { navigateToTab(currentTab) } },
                onSyncRequested = { runOnUiThread { startCalendarSync() } },
                onManageChangesRequested = { runOnUiThread { CalendarChangeTracker.showManageChangesDialog(this) } }
            ),
            "DemoBridge"
        )

"""
    text = replace_once(text, old_demo_bridge, "", "Poistettu DemoBridge-rekisteröinti WebView:stä")

    text = replace_once(
        text,
        '                    val isInternal = reqHost.equals("demo.local", ignoreCase = true) ||\n'
        '                        (!reqHost.isNullOrBlank() &&',
        '                    val isInternal = (!reqHost.isNullOrBlank() &&',
        "Poistettu demo.local-tarkistus shouldOverrideUrlLoadingista"
    )
    text = replace_once(
        text,
        '                if (url != null && !url.startsWith("https://demo.local/")) {',
        '                if (url != null) {',
        "Poistettu demo.local-tarkistus onPageCommitVisiblestä"
    )
    old_demo_finished = """                if (url.startsWith("https://demo.local/")) {
                    handleDemoAutoStamp()
                    endSnapshotTransition()
                    return
                }

"""
    text = replace_once(text, old_demo_finished, "", "Poistettu demo.local-haara onPageFinishedistä")

    old_stamp_else = """                        } else {
                            handleStampingPage()
                        }"""
    text = replace_once(text, old_stamp_else, "                        }", "Poistettu kuollut handleStampingPage()-kutsu")

    old_forgotten_js = "(function(){ try { if (typeof window.reloadForgottenStampPane === 'function') window.reloadForgottenStampPane(); if (typeof window.openForgottenStampPane === 'function') window.openForgottenStampPane(); var b = document.getElementById('forgottenStampButton'); if (b) b.click(); } catch(e){} })();"
    new_forgotten_js = "(function(){ try { if (typeof window.reloadForgottenStampPane === 'function') window.reloadForgottenStampPane(); if (typeof window.openForgottenStampPane === 'function') window.openForgottenStampPane(); if (typeof window._vvOpenForgotPanel === 'function') window._vvOpenForgotPanel(); var b = document.getElementById('forgottenStampButton'); if (b) b.click(); } catch(e){} })();"
    text = replace_once(text, old_forgotten_js, new_forgotten_js, "Varmistettu #forgotStampPanel-avaus overlayssa")

    m_demo = re.search(r"    private fun handleDemoAutoStamp\(\) \{.*?\n    \}\n\n", text, re.S)
    if m_demo:
        text = text[:m_demo.start()] + text[m_demo.end():]
        print("  [SIIVOTTU] Poistettu handleDemoAutoStamp()")
    else:
        print("  [OK - jo poistettu] handleDemoAutoStamp()")

    m_theme = re.search(
        r"    private fun injectDarkTheme\(view: WebView\?, forceDomInit: Boolean = false\) \{.*?\n    \}(?=\n\n    private fun handleAutoLogin)",
        text,
        re.S
    )
    if m_theme:
        if m_theme.group(0).strip() != SLIM_INJECT_DARK_THEME_KT.strip():
            old_len = len(m_theme.group(0).splitlines())
            new_len = len(SLIM_INJECT_DARK_THEME_KT.splitlines())
            text = text[:m_theme.start()] + SLIM_INJECT_DARK_THEME_KT + text[m_theme.end():]
            print(f"  [SIIVOTTU] Tiivistetty injectDarkTheme() ({old_len} -> {new_len} riviä)")
        else:
            print("  [OK - jo tiivistetty] injectDarkTheme()")
    else:
        print("  [VAROITUS] injectDarkTheme()-lohkoa ei löytynyt")

    m_stamping = re.search(
        r"    private fun handleStampingPage\(attempt: Int = 0\) \{.*?\n    \}\n\n    private fun verifyStampAndClose\(.*?\n    \}\n\n",
        text,
        re.S
    )
    if m_stamping:
        text = text[:m_stamping.start()] + text[m_stamping.end():]
        print("  [SIIVOTTU] Poistettu handleStampingPage() & verifyStampAndClose()")
    else:
        print("  [OK - jo poistettu] handleStampingPage() & verifyStampAndClose()")

    if text != orig:
        write_text_keep_nl(path, text, nl)
        print(f"  MainActivity.kt: {len(orig.splitlines())} -> {len(text.splitlines())} riviä")
        return True
    return False


def patch_quick_stamp_activity(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    text = replace_once(
        text,
        "import org.json.JSONTokener\n",
        "",
        "Poistettu käyttämätön JSONTokener-import"
    )

    old_dup = """    private fun parseJsonResult(rawResult: String?): JSONObject? {
        return try {
            if (rawResult != null && rawResult != "null") {
                val unescaped = JSONTokener(rawResult).nextValue() as? String
                if (unescaped != null) JSONObject(unescaped) else null
            } else {
                null
            }
        } catch (_: Exception) {
            null
        }
    }

"""
    text = replace_once(
        text,
        old_dup,
        "",
        "Poistettu käyttämätön parseJsonResult-kopio QuickStampActivity.kt:stä"
    )

    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_build_gradle(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text
    if "versionCode = 127" in text:
        print("  [OK - jo päivitetty] build.gradle.kts versionCode 127")
        return False
    text = replace_once(text, "versionCode = 126", "versionCode = 127", "versionCode 126 -> 127")
    text = replace_once(text, 'versionName = "3.2.184"', 'versionName = "3.2.185"', 'versionName "3.2.184" -> "3.2.185"')
    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def main() -> int:
    changed = 0
    for filename, fn in [
        ("DemoModeHelper.kt", patch_demo_mode_helper),
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

    print(f"\nValmis! Siivottuja tiedostoja: {changed}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
