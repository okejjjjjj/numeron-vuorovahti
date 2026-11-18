#!/usr/bin/env python3
import pathlib
import re
import sys

def find_file(candidates):
    for c in candidates:
        p = pathlib.Path(c)
        if p.exists():
            return p
    return None

def main():
    main_act_path = find_file([
        "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt",
        "MainActivity.kt",
        "MainActivity.kt.txt"
    ])
    if not main_act_path:
        print("Virhe: MainActivity.kt-tiedostoa ei löytynyt.", file=sys.stderr)
        sys.exit(1)

    content = main_act_path.read_text(encoding="utf-8")
    original = content

    # 1. Päivitetään TÄNÄÄN-osion CSS-tyylit
    old_shift_css = """            .punching-shift-name {
                font-size: 16px !important;
                font-weight: 600 !important;
                color: #F1F5F9 !important;
            }"""

    new_shift_css = """            .punching-shift-times {
                display: block !important;
                font-size: 24px !important;
                font-weight: 700 !important;
                color: #FFFFFF !important;
                line-height: 1.25 !important;
                margin-bottom: 6px !important;
            }
            .punching-shift-name {
                display: block !important;
                font-size: 16px !important;
                font-weight: 600 !important;
                color: #38BDF8 !important;
                line-height: 1.3 !important;
            }
            .punching-shift-workplace {
                display: block !important;
                font-size: 16px !important;
                font-weight: 600 !important;
                color: #38BDF8 !important;
                line-height: 1.3 !important;
                margin-bottom: 2px !important;
            }
            .punching-shift-role {
                display: block !important;
                font-size: 14px !important;
                font-weight: 500 !important;
                color: #CBD5E1 !important;
                line-height: 1.3 !important;
            }"""

    if ".punching-shift-workplace" not in content and old_shift_css in content:
        content = content.replace(old_shift_css, new_shift_css, 1)

    # 2. NumeronParser.parseShiftText-logiikkaa vastaava JS-muotoilu TÄNÄÄN-osiolle
    new_js_block = """                // === TÄNÄÄN-OSION MUOTOILU KOLMELLE RIVILLE ===
                (function formatTodayShiftBox() {
                    function capFirst(str) {
                        if (!str) return '';
                        return str.charAt(0).toUpperCase() + str.slice(1);
                    }

                    function parseShiftText(rawName) {
                        var cleaned = (rawName || '').trim().replace(/^\d+\s*/, '').trim();
                        if (!cleaned) return { location: '', shiftName: '', role: '' };

                        // Vapaapäivät / poissaolot jätetään yhdelle riville
                        if (/^(ei\s+(työ)?vuoroa|vapaa|vapaapäivä|vuosiloma|sairausloma|poissaolo)/i.test(cleaned)) {
                            return { location: capFirst(cleaned), shiftName: '', role: '' };
                        }

                        var tokens = cleaned.split(/\s+/).filter(function(t) { return t.length > 0; });
                        if (tokens.length === 0) return { location: '', shiftName: '', role: '' };

                        var shiftKeywords = {
                            'aamu': true, 'aamuvuoro': true,
                            'ilta': true, 'iltavuoro': true,
                            'yö': true, 'yövuoro': true,
                            'päivä': true, 'päivävuoro': true,
                            'väli': true, 'välivuoro': true
                        };

                        var firstKwIdx = -1;
                        for (var i = 0; i < tokens.length; i++) {
                            if (shiftKeywords[tokens[i].toLowerCase()]) {
                                firstKwIdx = i;
                                break;
                            }
                        }

                        if (firstKwIdx !== -1) {
                            var location = tokens.slice(0, firstKwIdx).join(' ');
                            var remainder = tokens.slice(firstKwIdx);
                            var lastKwOffset = -1;
                            for (var j = remainder.length - 1; j >= 0; j--) {
                                if (shiftKeywords[remainder[j].toLowerCase()]) {
                                    lastKwOffset = j;
                                    break;
                                }
                            }
                            var shiftName = capFirst(remainder.slice(0, lastKwOffset + 1).join(' '));
                            var role = capFirst(remainder.slice(lastKwOffset + 1).join(' '));
                            return { location: location, shiftName: shiftName, role: role };
                        } else if (tokens.length >= 2) {
                            var roleOnly = capFirst(tokens[tokens.length - 1]);
                            var locOnly = tokens.slice(0, tokens.length - 1).join(' ');
                            return { location: locOnly, shiftName: '', role: roleOnly };
                        } else {
                            return { location: cleaned, shiftName: '', role: '' };
                        }
                    }

                    function applyShiftFormat() {
                        var container = document.querySelector('.punching-shift-container');
                        if (!container) return;
                        var nameEl = container.querySelector('.punching-shift-name');
                        if (!nameEl) return;

                        var existingWp = nameEl.querySelector('.punching-shift-workplace');
                        var rawText = existingWp
                            ? (nameEl.getAttribute('data-raw-shift') || '')
                            : (nameEl.textContent || '').replace(/\s+/g, ' ').trim();
                        if (!rawText) return;

                        if (existingWp && nameEl.getAttribute('data-formatted-for') === 'v2:' + rawText) {
                            return;
                        }
                        nameEl.setAttribute('data-raw-shift', rawText);
                        nameEl.setAttribute('data-formatted-for', 'v2:' + rawText);

                        var parsed = parseShiftText(rawText);
                        var thirdLine = [parsed.shiftName, parsed.role]
                            .filter(function(s) { return s && s.length > 0; })
                            .join(' • ');

                        nameEl.textContent = '';
                        if (parsed.location) {
                            var wpSpan = document.createElement('span');
                            wpSpan.className = 'punching-shift-workplace';
                            wpSpan.textContent = parsed.location;
                            nameEl.appendChild(wpSpan);
                        }

                        if (thirdLine) {
                            var roleSpan = document.createElement('span');
                            roleSpan.className = 'punching-shift-role';
                            roleSpan.textContent = thirdLine;
                            nameEl.appendChild(roleSpan);
                        }
                    }

                    applyShiftFormat();
                    if (!window._todayShiftObserverInstalled) {
                        window._todayShiftObserverInstalled = true;
                        var target = document.querySelector('.punching-shift-container') || document.body;
                        if (target && typeof MutationObserver !== 'undefined') {
                            var obs = new MutationObserver(function() {
                                applyShiftFormat();
                            });
                            obs.observe(target, { childList: true, subtree: true, characterData: true });
                        }
                    }
                })();"""

    existing_block_re = re.compile(
        r"                // === TÄNÄÄN-OSION MUOTOILU KOLMELLE RIVILLE ===.*?\n                \}\)\(\);",
        re.DOTALL
    )

    if existing_block_re.search(content):
        content = existing_block_re.sub(lambda _: new_js_block, content, count=1)
    else:
        js_anchor = "                if (!window._sessionWatchInstalled) {"
        if js_anchor in content:
            content = content.replace(js_anchor, new_js_block + "\n\n" + js_anchor, 1)
        else:
            print("Varoitus: JS-ankkuria ei löytynyt.", file=sys.stderr)

    if content != original:
        main_act_path.write_text(content, encoding="utf-8")
        print(f"Päivitetty onnistuneesti (NumeronParser-pohjainen Tänään-muotoilu): {main_act_path}")
    else:
        print("Ei muutoksia tehtävänä tai korjaus oli jo lisätty.")

    # 3. Nostetaan versionCode yhdellä pykälällä
    gradle_path = find_file([
        "app/build.gradle.kts",
        "app/build.gradle",
        "build.gradle.kts",
        "build.gradle.kts.txt"
    ])
    if gradle_path and content != original:
        g_content = gradle_path.read_text(encoding="utf-8")
        vc_match = re.search(r'versionCode\s*=\s*(\d+)', g_content)
        if vc_match:
            old_code = int(vc_match.group(1))
            new_code = old_code + 1
            g_content = g_content.replace(f"versionCode = {old_code}", f"versionCode = {new_code}", 1)
            gradle_path.write_text(g_content, encoding="utf-8")
            print(f"Nostettu versionCode: {old_code} -> {new_code} ({gradle_path})")

if __name__ == "__main__":
    main()
