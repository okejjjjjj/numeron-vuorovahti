from pathlib import Path

TARGET = Path("app/src/main/java/fi/oma/numeron/MainActivity.kt")


def replace_exact(content: str, old: str, new: str, label: str) -> str:
    count = content.count(old)
    assert count == 1, f"Odotettiin täsmälleen 1 osumaa kohdalle '{label}', löytyi {count}"
    return content.replace(old, new, 1)


def main() -> None:
    if not TARGET.exists():
        # Fallback jos ajetaan suoraan samasta hakemistosta
        alt = Path("MainActivity.kt")
        if alt.exists():
            target_path = alt
        else:
            raise FileNotFoundError(f"Tiedostoa {TARGET} ei löytynyt.")
    else:
        target_path = TARGET

    code = target_path.read_text(encoding="utf-8")

    # 1. Poista taustakuva, piilota evästebanneri ja siisti kirjautumiskortti sekä lomakekentät
    old_css_block = """            :root { color-scheme: dark; }
            html, body {
                background-color: #0F172A !important;
                color: #E2E8F0 !important;
                font-family: sans-serif !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            a { color: #38BDF8; }
            nav.navbar, nav.loginnav, .loginnav, footer, img[src*="visma"],
            .container > h1.clear, .container-fluid > h1.clear, h1.clear,
            #wfm-modal-div:empty, .alert:empty, .messageBox:empty, .infoBox:empty, .statusBox:empty,
            #mobile_AddButton, #mobileViewDropdown, .whitebox hr {
                display: none !important;
            }
            .container, .container-fluid, .content-container {
                width: 100% !important;
                max-width: 100% !important;
                padding: 14px 10px 24px 10px !important;
                margin: 0 !important;
                background-color: #0F172A !important;
            }
            .blurbox { background: transparent !important; text-align: center !important; }
            .blurbox h1 { color: #38BDF8 !important; font-size: 20px !important; font-weight: bold !important; margin: 4px 0 14px 0 !important; }
            .whitebox, .panel, .panel-default, .well, .list-group-item,
            .modal-content, .popover, .popover-content, .popover-title, .tooltip-inner {
                background-color: #1E293B !important;
                background-image: none !important;
                border: 1px solid #334155 !important;
                border-radius: 14px !important;
                box-shadow: none !important;
                color: #E2E8F0 !important;
            }"""

    new_css_block = """            :root { color-scheme: dark; }
            html, body {
                background: #0F172A !important;
                background-color: #0F172A !important;
                background-image: none !important;
                color: #E2E8F0 !important;
                font-family: sans-serif !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            a { color: #38BDF8; }
            nav.navbar, nav.loginnav, .loginnav, footer, img[src*="visma"],
            .container > h1.clear, .container-fluid > h1.clear, h1.clear,
            #wfm-modal-div:empty, .alert:empty, .messageBox:empty, .infoBox:empty, .statusBox:empty,
            #mobile_AddButton, #mobileViewDropdown, .whitebox hr,
            #cookieConsent, .cookie-consent, .cookie-banner, #cookie-banner, .cc-window, .cc-banner {
                display: none !important;
            }
            .container, .container-fluid, .content-container {
                width: 100% !important;
                max-width: 100% !important;
                padding: 14px 10px 24px 10px !important;
                margin: 0 !important;
                background-color: #0F172A !important;
            }
            .content {
                float: none !important;
                width: 100% !important;
                max-width: 440px !important;
                margin: 0 auto !important;
                padding: 24px 14px !important;
                position: static !important;
                top: auto !important;
                left: auto !important;
                transform: none !important;
            }
            .blurbox {
                background: transparent !important;
                background-color: transparent !important;
                background-image: none !important;
                backdrop-filter: none !important;
                -webkit-backdrop-filter: none !important;
                border: none !important;
                box-shadow: none !important;
                padding: 12px 0 8px 0 !important;
                margin: 0 !important;
                text-align: center !important;
            }
            .blurbox h1 {
                color: #38BDF8 !important;
                font-size: 24px !important;
                font-weight: bold !important;
                margin: 0 0 14px 0 !important;
                text-shadow: none !important;
            }
            .whitebox, .panel, .panel-default, .well, .list-group-item,
            .modal-content, .popover, .popover-content, .popover-title, .tooltip-inner {
                background-color: #1E293B !important;
                background-image: none !important;
                border: 1px solid #334155 !important;
                border-radius: 14px !important;
                box-shadow: none !important;
                color: #E2E8F0 !important;
            }
            .whitebox {
                padding: 20px 18px !important;
                margin: 0 !important;
                min-height: 0 !important;
                height: auto !important;
            }
            #LoginForm .form-group { margin: 0 0 14px 0 !important; }
            #LoginForm .control-label {
                display: block !important;
                width: 100% !important;
                float: none !important;
                text-align: left !important;
                padding: 0 0 6px 2px !important;
                margin: 0 !important;
                font-size: 13px !important;
            }
            #LoginForm .col-sm-7, #LoginForm .col-sm-offset-4 {
                width: 100% !important;
                float: none !important;
                margin-left: 0 !important;
                padding: 0 !important;
            }
            #LoginForm .form-control {
                height: 44px !important;
                font-size: 16px !important;
                padding: 10px 12px !important;
            }
            #LoginForm .pull-left, #LoginForm .pull-right {
                float: none !important;
                display: block !important;
                text-align: center !important;
                margin: 6px 0 !important;
                font-size: 13px !important;
            }
            #LoginForm input[type="submit"] {
                height: 46px !important;
                font-size: 15px !important;
                margin-top: 12px !important;
            }
            .validation-summary-errors, .field-validation-error {
                background-color: #450A0A !important;
                border: 1px solid #EF4444 !important;
                border-radius: 10px !important;
                color: #FCA5A5 !important;
                padding: 10px 12px !important;
                margin-bottom: 12px !important;
                font-size: 13px !important;
                display: block !important;
            }
            .validation-summary-errors ul { margin: 0 !important; padding-left: 18px !important; }"""

    code = replace_exact(code, old_css_block, new_css_block, "injectCleanTheme CSS")

    # 2. Evästebannerin automaattinen kuittaus + LoginFormin piilotus vain kun virhettä ei ole
    old_theme_js = """                attachTheme();
                if (!window._numeronThemeObserver) {
                    window._numeronThemeObserver = new MutationObserver(function() {
                        attachTheme();
                    });
                    window._numeronThemeObserver.observe(document, { childList: true, subtree: true });
                }
                if ($hasCreds) {
                    var form = document.getElementById('LoginForm');
                    if (form && !form.dataset.hiddenByTheme) {
                        form.dataset.hiddenByTheme = 'true';
                        form.style.cssText = 'opacity:0;height:0;overflow:hidden;pointer-events:none;';
                        var msg = document.createElement('div');
                        msg.id = 'custom-login-msg';
                        msg.style.cssText = 'text-align:center;padding:32px 12px;color:#38BDF8;font-size:16px;font-weight:bold;';
                        msg.innerText = 'Kirjaudutaan sisään...';
                        form.parentNode.insertBefore(msg, form);
                        setTimeout(function() {
                            var f = document.getElementById('LoginForm');
                            var m = document.getElementById('custom-login-msg');
                            if (f) {
                                f.style.cssText = '';
                                delete f.dataset.hiddenByTheme;
                            }
                            if (m) m.remove();
                        }, 5000);
                    }
                }"""

    new_theme_js = """                function dismissCookieBanner() {
                    var btns = document.querySelectorAll('button, a, input[type="button"], input[type="submit"]');
                    for (var i = 0; i < btns.length; i++) {
                        var b = btns[i];
                        var t = (b.innerText || b.value || '').trim().toLowerCase();
                        if (t === 'hyväksy' || t === 'hyväksy evästeet' || t === 'accept') {
                            var box = b.closest('div, section, aside, footer, header, nav');
                            var boxTxt = box ? (box.innerText || '').toLowerCase() : '';
                            if (boxTxt.indexOf('eväste') !== -1 || boxTxt.indexOf('cookie') !== -1) {
                                if (!b.dataset.cookieClicked) {
                                    b.dataset.cookieClicked = '1';
                                    b.click();
                                }
                                if (box && box !== document.body && !box.querySelector('#LoginForm')) {
                                    box.style.setProperty('display', 'none', 'important');
                                }
                            }
                        }
                    }
                }
                attachTheme();
                dismissCookieBanner();
                if (!window._numeronThemeObserver) {
                    window._numeronThemeObserver = new MutationObserver(function() {
                        attachTheme();
                        dismissCookieBanner();
                    });
                    window._numeronThemeObserver.observe(document, { childList: true, subtree: true });
                }
                if ($hasCreds) {
                    var errEl = document.querySelector('.validation-summary-errors, .field-validation-error, .alert-danger');
                    var hasLoginError = errEl && (errEl.innerText || '').trim().length > 0;
                    var form = document.getElementById('LoginForm');
                    if (form && !hasLoginError && !form.dataset.hiddenByTheme) {
                        form.dataset.hiddenByTheme = 'true';
                        form.style.cssText = 'opacity:0;height:0;overflow:hidden;pointer-events:none;';
                        var msg = document.createElement('div');
                        msg.id = 'custom-login-msg';
                        msg.style.cssText = 'text-align:center;padding:24px 12px;';
                        msg.innerHTML = '<div style="color:#38BDF8;font-size:16px;font-weight:bold;margin-bottom:6px;">Kirjaudutaan sisään...</div><div style="color:#94A3B8;font-size:13px;">Yhdistetään OmaNumeron-palveluun</div>';
                        form.parentNode.insertBefore(msg, form);
                        setTimeout(function() {
                            var f = document.getElementById('LoginForm');
                            var m = document.getElementById('custom-login-msg');
                            if (f) {
                                f.style.cssText = '';
                                delete f.dataset.hiddenByTheme;
                            }
                            if (m) m.remove();
                        }, 5000);
                    }
                }"""

    code = replace_exact(code, old_theme_js, new_theme_js, "injectCleanTheme JS")

    # 3. Estä automaattikirjautumisen silmukka virheellisillä tunnuksilla ja tuplalähetys
    old_autologin_tail = """                if (!passEl) return "NO_LOGIN_FORM";
                if (userEl) setNativeValue(userEl, '$safeU');
                setNativeValue(passEl, '$safeP');
                var submitBtn = document.querySelector('input[type="submit"], button[type="submit"], button[id*="login" i], button[name*="login" i], input[id*="SignIn" i]');
                if (submitBtn && submitBtn.offsetParent !== null) { submitBtn.click(); return "SUBMITTED"; }
                if (passEl.form) { passEl.form.submit(); return "SUBMITTED"; }
                return "FILLED";"""

    new_autologin_tail = """                if (!passEl) return "NO_LOGIN_FORM";
                var errEl = document.querySelector('.validation-summary-errors, .field-validation-error, .alert-danger');
                if (errEl && (errEl.innerText || '').trim().length > 0) return "LOGIN_ERROR";
                var nowTs = Date.now();
                if (window._numeronAutoLoginTs && (nowTs - window._numeronAutoLoginTs) < 4000) return "SUBMIT_COOLDOWN";
                window._numeronAutoLoginTs = nowTs;
                if (userEl) setNativeValue(userEl, '$safeU');
                setNativeValue(passEl, '$safeP');
                var submitBtn = document.querySelector('input[type="submit"], button[type="submit"], button[id*="login" i], button[name*="login" i], input[id*="SignIn" i]');
                if (submitBtn && submitBtn.offsetParent !== null) {
                    submitBtn.disabled = false;
                    submitBtn.click();
                    return "SUBMITTED";
                }
                if (passEl.form) { passEl.form.submit(); return "SUBMITTED"; }
                return "FILLED";"""

    code = replace_exact(code, old_autologin_tail, new_autologin_tail, "tryAutoLoginIfNeeded")

    target_path.write_text(code, encoding="utf-8")
    print(f"OK: {target_path} päivitetty onnistuneesti.")


if __name__ == "__main__":
    main()
