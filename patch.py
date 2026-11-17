#!/usr/bin/env python3
import pathlib
import sys

def main():
    main_act_path = pathlib.Path("app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt")
    if not main_act_path.exists():
        # Kokeillaan myös juurihakemistoa
        alt = pathlib.Path("MainActivity.kt")
        if alt.exists():
            main_act_path = alt
        else:
            print(f"Virhe: Tiedostoa {main_act_path} ei löytynyt.", file=sys.stderr)
            sys.exit(1)

    content = main_act_path.read_text(encoding="utf-8")
    original = content

    # 1. Estetään amplitude.com-analytiikkapyynnöt shouldInterceptRequest-metodissa
    old_block_list = """                val blockedCssPatterns = listOf(
                    "/content/css/cssvisma",
                    "/content/css/login.css",
                    "/content/css/calendar.css",
                    "/content/css/buttons.css",
                    "/bundles/cssworktimestamping",
                    "/content/css/worktimestamping.css",
                    "/content/css/listlayout.css",
                    "fonts.googleapis.com"
                )"""

    new_block_list = """                if (url.contains("amplitude.com")) {
                    return WebResourceResponse(
                        "application/javascript",
                        "UTF-8",
                        ByteArrayInputStream(ByteArray(0))
                    )
                }

                val blockedCssPatterns = listOf(
                    "/content/css/cssvisma",
                    "/content/css/login.css",
                    "/content/css/calendar.css",
                    "/content/css/buttons.css",
                    "/bundles/cssworktimestamping",
                    "/content/css/worktimestamping.css",
                    "/content/css/listlayout.css",
                    "fonts.googleapis.com"
                )"""

    assert old_block_list in content, "Ei löydetty blockedCssPatterns-kohtaa"
    content = content.replace(old_block_list, new_block_list, 1)

    # 2. Näytetään saldo leimaussivun yläosassa ennen leimausnappia (ei lukitusrajaa)
    old_balance_css = """            /* === 5. TYÖAIKALEIMAUS === */
            .punching-balance-overview-container {
                display: none !important;
            }"""

    new_balance_css = """            /* === 5. TYÖAIKALEIMAUS === */
            #numeron-balance-card {
                background-color: #182332 !important;
                border: 1px solid #2A394A !important;
                border-radius: 12px !important;
                padding: 12px 14px !important;
                margin-bottom: 14px !important;
                display: flex !important;
                justify-content: space-between !important;
                align-items: center !important;
            }
            #numeron-balance-card .bal-label {
                font-size: 12px !important;
                text-transform: uppercase !important;
                letter-spacing: 0.05em !important;
                color: #94A3B8 !important;
                font-weight: 600 !important;
            }
            #numeron-balance-card .bal-value {
                font-size: 18px !important;
                font-weight: 700 !important;
                color: #38BDF8 !important;
            }
            .punching-balance-overview-container {
                display: none !important;
            }"""

    assert old_balance_css in content, "Ei löydetty punching-balance-overview-container CSS-kohtaa"
    content = content.replace(old_balance_css, new_balance_css, 1)

    # 3. Lisätään JS-injektioon:
    #    - Saldon haku /WorktimeStamping/GetPersonBalance -päätepisteestä ja sijoitus ennen leimausnappia
    #    - Kalenterin kuukausinäkymään suora "Lisää toive" -pikavalikko päiväsolun napautuksesta
    old_js_tail = """                        var cancelBtn = e.target && e.target.closest('#cancelPunchForgottenButton, #cancelPunchForgottenButtonHeader');
                        if (cancelBtn) {
                            var panel = document.getElementById('forgotStampPanel');
                            if (panel) {
                                panel.classList.remove('force-open');
                                panel.classList.add('minimized');
                                panel.style.top = '100%';
                            }
                        }
                    }, true);
                }
            })();"""

    new_js_tail = """                        var cancelBtn = e.target && e.target.closest('#cancelPunchForgottenButton, #cancelPunchForgottenButtonHeader');
                        if (cancelBtn) {
                            var panel = document.getElementById('forgotStampPanel');
                            if (panel) {
                                panel.classList.remove('force-open');
                                panel.classList.add('minimized');
                                panel.style.top = '100%';
                            }
                        }
                    }, true);
                }

                // === SALDO LEIMAUSSIVUN YLÄOSAAN ENNEN LEIMAUSNAPPIA ===
                if (window.location.pathname.toLowerCase().indexOf('/worktimestamping') !== -1 && !window._balanceLoaderInstalled) {
                    window._balanceLoaderInstalled = true;
                    var punchBtn = document.getElementById('punchButton');
                    var targetContainer = punchBtn ? (punchBtn.closest('.panel, .whitebox, .stamping-box, .card, form') || punchBtn.parentElement) : null;
                    if (targetContainer && !document.getElementById('numeron-balance-card')) {
                        var card = document.createElement('div');
                        card.id = 'numeron-balance-card';
                        card.innerHTML = '<span class="bal-label">Työaikasaldo</span><span class="bal-value" id="numeron-balance-val">Haetaan...</span>';
                        targetContainer.parentNode.insertBefore(card, targetContainer);

                        var tokenInput = document.querySelector('input[name="__RequestVerificationToken"]');
                        var token = tokenInput ? tokenInput.value : '';
                        fetch('/WorktimeStamping/GetPersonBalance', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                                'X-Requested-With': 'XMLHttpRequest'
                            },
                            body: '__RequestVerificationToken=' + encodeURIComponent(token)
                        })
                        .then(function(r) { return r.json(); })
                        .then(function(data) {
                            var valEl = document.getElementById('numeron-balance-val');
                            if (!valEl) return;
                            var raw = (data && (data.Balance || data.balance || data.FormattedBalance || data.formattedBalance || data.TotalBalance || data.totalBalance || data.Value || data.value));
                            if (raw === undefined || raw === null) {
                                // Jos kentän nimi vaihtelee, etsitään ensimmäinen saldoa muistuttava arvo
                                if (typeof data === 'string' || typeof data === 'number') {
                                    raw = data;
                                } else if (data && typeof data === 'object') {
                                    for (var k in data) {
                                        if (Object.prototype.hasOwnProperty.call(data, k) && k.toLowerCase().indexOf('balance') !== -1 && data[k] !== null) {
                                            raw = data[k];
                                            break;
                                        }
                                    }
                                }
                            }
                            if (raw !== undefined && raw !== null && String(raw).trim() !== '') {
                                var txt = String(raw).trim();
                                valEl.textContent = txt;
                                if (txt.indexOf('-') === 0) {
                                    valEl.style.color = '#F87171';
                                } else {
                                    valEl.style.color = '#34D399';
                                }
                            } else {
                                card.style.display = 'none';
                            }
                        })
                        .catch(function() {
                            var c = document.getElementById('numeron-balance-card');
                            if (c) c.style.display = 'none';
                        });
                    }
                }

                // === SUORA "LISÄÄ TOIVE TÄLLE PÄIVÄLLE" -OIKOPOLKU KALENTERIPÄIVÄSTÄ ===
                if (window.location.pathname.toLowerCase().indexOf('/calendar') !== -1 && !window._quickRequestInstalled) {
                    window._quickRequestInstalled = true;
                    var monthsFi = {
                        'tammikuu': 1, 'helmikuu': 2, 'maaliskuu': 3, 'huhtikuu': 4,
                        'toukokuu': 5, 'kesäkuu': 6, 'heinäkuu': 7, 'elokuu': 8,
                        'syyskuu': 9, 'lokakuu': 10, 'marraskuu': 11, 'joulukuu': 12
                    };
                    document.addEventListener('click', function(e) {
                        if (e.target && e.target.closest('a, button')) return;
                        var cell = e.target && e.target.closest('table.month-table td.month-day');
                        if (!cell || cell.classList.contains('day-different-month')) return;

                        var dayEl = cell.querySelector('.dayNum');
                        var monthHeader = document.getElementById('monthText');
                        if (!dayEl || !monthHeader) return;

                        var dayNum = parseInt((dayEl.textContent || '').trim(), 10);
                        var parts = (monthHeader.textContent || '').trim().toLowerCase().split(/\s+/);
                        if (!dayNum || parts.length < 2) return;

                        var mNum = monthsFi[parts[0]];
                        var yNum = parseInt(parts[1], 10);
                        if (!mNum || !yNum) return;

                        var isoDate = yNum + '-' + String(mNum).padStart(2, '0') + '-' + String(dayNum).padStart(2, '0');
                        var fiDate = String(dayNum).padStart(2, '0') + '.' + String(mNum).padStart(2, '0') + '.' + yNum;

                        var existing = document.getElementById('numeron-quick-req-bar');
                        if (existing) existing.remove();

                        var bar = document.createElement('div');
                        bar.id = 'numeron-quick-req-bar';
                        bar.style.cssText = 'position:fixed;left:12px;right:12px;bottom:14px;z-index:1100;background:#182332;border:1px solid #38BDF8;border-radius:12px;padding:12px 14px;display:flex;justify-content:space-between;align-items:center;box-shadow:0 8px 24px rgba(0,0,0,0.6);';
                        bar.innerHTML = '<span style="color:#F1F5F9;font-size:14px;font-weight:600;">' + fiDate + '</span>' +
                            '<div style="display:flex;gap:8px;">' +
                            '<button id="numeron-qr-close" type="button" style="background:#233040;color:#CBD5E1;border:1px solid #37475A;border-radius:8px;padding:8px 12px;font-size:13px;">Sulje</button>' +
                            '<a href="/PersonRequests/Edit?calendarView=Month&returnValue=' + isoDate + '" style="background:#1982C4;color:#FFFFFF !important;border-radius:8px;padding:8px 14px;font-size:13px;font-weight:600;text-decoration:none;">+ Lisää toive</a>' +
                            '</div>';
                        document.body.appendChild(bar);
                        document.getElementById('numeron-qr-close').onclick = function() { bar.remove(); };
                    }, false);
                }
            })();"""

    assert old_js_tail in content, "Ei löydetty injectDarkTheme JS-loppukohtaa"
    content = content.replace(old_js_tail, new_js_tail, 1)

    assert content != original, "Tiedostoon ei tullut muutoksia"
    main_act_path.write_text(content, encoding="utf-8")
    print(f"Päivitetty onnistuneesti: {main_act_path}")

if __name__ == "__main__":
    main()
