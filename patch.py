#!/usr/bin/env python3
"""
patch.py — Korjaa Numeron-sovelluksen WebView-näkymät ja poistaa alkuperäisen
vaalean sivun välähdyksen latauksen yhteydessä sekä kasvattaa versionumeroa
pienin pykälin.

Korjaukset:
1. Poistaa vaalean sivun välähdyksen (FOUC): asettaa WebView'n taustavärin tummaksi
   (#0F172A) ja injektoi tyylit jo onPageStarted- ja onPageCommitVisible-vaiheissa
   ennen ensimmäistä piirtoa.
2. Leimaussivu: piilottaa tyhjän ylälaatikon ja muotoilee TÄNÄÄN-osion siistiksi
   vaaleammaksi laatikoksi (#334155) selkeällä kontrastilla.
3. Kalenterisivu: estää kuukausi- ja listanäkymän ruudukkoa nousemasta Tänään- ja
   Näkymä-nappien päälle.
4. Toiveet-pudotusvalikot ja kalenterilistan valkoiset vuorokortit tummiksi.
5. Kirjautumislomakkeen visuaalinen piilotus ilman display:none -estoa + 5 s varamekanismi.
6. Versionumeron kasvatus +1 / pienimmällä patch-askeleella.

Käyttö:
    python3 patch.py
    python3 patch.py --subpatch   # (valinnainen) 4. tason versionName (esim. 1.4.2 -> 1.4.2.1)
"""

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Optional


CSS_ADDITION = """            /* 1. Leimaussivun tyhjät ylälaatikot piiloon */
            .alert:empty, .messageBox:empty, .infoBox:empty, .statusBox:empty,
            .mobileHeader:empty, .punchHeader:empty, .mobileInfoDiv:empty {
                display: none !important;
            }

            /* 2. Toiveet-sivun Kendo / Select2 -pudotusvalikot tummiksi */
            .k-animation-container, .k-popup, .k-list-container, .k-list-scroller, ul.k-list,
            .select2-dropdown, .select2-results, .chosen-drop, .chosen-results, .ui-menu, .ui-selectmenu-menu {
                background-color: #1E293B !important;
                background-image: none !important;
                color: #F1F5F9 !important;
                border-color: #334155 !important;
            }
            .k-list-filter {
                background-color: #1E293B !important;
                padding: 6px !important;
            }
            .k-list-filter > input, .k-list-filter .k-textbox, .select2-search__field, .chosen-search input {
                background-color: #0F172A !important;
                color: #F1F5F9 !important;
                border: 1px solid #38BDF8 !important;
            }
            ul.k-list > li.k-item, .k-item, .select2-results__option, .chosen-results li, .ui-menu-item, select option {
                background-color: #1E293B !important;
                color: #F1F5F9 !important;
            }
            ul.k-list > li.k-item.k-state-hover, ul.k-list > li.k-item.k-state-focused, ul.k-list > li.k-item.k-state-selected,
            .k-state-selected, .k-state-focused, .select2-results__option--highlighted, .chosen-results li.highlighted {
                background-color: #0284C7 !important;
                color: #FFFFFF !important;
            }

            /* 3. Kalenterinäkymän Tänään- ja Näkymä-napit näkyviin ruudukon yläpuolelle */
            .mobileAddDiv, .calendarHeaderButtons, .weekNavButtons {
                display: flex !important;
                flex-direction: row !important;
                align-items: center !important;
                justify-content: space-between !important;
                gap: 10px !important;
                width: 100% !important;
                box-sizing: border-box !important;
                background-color: transparent !important;
                background-image: none !important;
                margin: 8px 0 12px 0 !important;
                padding: 4px 0 !important;
                height: auto !important;
                min-height: 44px !important;
                max-height: none !important;
                position: relative !important;
                top: 0 !important;
                bottom: auto !important;
                transform: none !important;
                overflow: visible !important;
                z-index: 50 !important;
            }
            .mobileAddDiv + div, .mobileAddDiv + table, .mobileAddDiv + section,
            .calendarHeaderButtons + div, .weekNavButtons + div {
                position: relative !important;
                top: 0 !important;
                margin-top: 8px !important;
                transform: none !important;
                z-index: 10 !important;
            }
            .mobileAddButton, .filterButton, .todayButton, .viewButton {
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                color: #38BDF8 !important;
                background-color: #1E293B !important;
                border: 1px solid #334155 !important;
                border-radius: 8px !important;
                height: 40px !important;
                min-height: 40px !important;
                padding: 0 14px !important;
                margin: 0 !important;
                line-height: 1.2 !important;
                position: relative !important;
                top: 0 !important;
                transform: none !important;
                overflow: visible !important;
                z-index: 51 !important;
            }

            /* 4. Listanäkymän valkoiset vuorokortit ja valkoiset häivytyspalkit */
            .eventItem, .shiftItem, .shiftCard, .calendarEvent, .mobileEvent, .workShiftCard, .fc-event,
            div[style*="background-color: rgb(255, 255, 255)"], div[style*="background-color:#fff"], div[style*="background-color: #fff"],
            div[style*="background: rgb(255, 255, 255)"], div[style*="background:#fff"], div[style*="background: #fff"] {
                background-color: #1E293B !important;
                background-image: none !important;
                color: #F1F5F9 !important;
                border-color: #334155 !important;
            }
            .eventItem *, .shiftItem *, .shiftCard *, .calendarEvent *, .mobileEvent *, .workShiftCard * {
                color: #F1F5F9 !important;
            }"""


JS_BODY = """            (function() {
                var cssText = `$css`;

                function ensureThemeStyle() {
                    var root = document.head || document.documentElement;
                    if (!root) return false;
                    var style = document.getElementById('custom-numeron-theme');
                    if (!style) {
                        style = document.createElement('style');
                        style.id = 'custom-numeron-theme';
                        style.type = 'text/css';
                        root.appendChild(style);
                    }
                    if (style.textContent !== cssText) {
                        style.textContent = cssText;
                    }
                    return true;
                }

                // Kiinnitä tyylit välittömästi ennen kuin <body> ehtii piirtyä (estää vaalean välähdyksen)
                if (!ensureThemeStyle()) {
                    var earlyObs = new MutationObserver(function() {
                        if (ensureThemeStyle()) {
                            earlyObs.disconnect();
                        }
                    });
                    earlyObs.observe(document, { childList: true, subtree: true });
                }

                // Piilotetaan lomake vain visuaalisesti (ei display:none, jotta automaattikirjautuminen ja lomakkeen lähetys toimivat)
                if ($hasCreds && document.getElementById('LoginForm')) {
                    var form = document.getElementById('LoginForm');
                    if (form && !form.dataset.hiddenByTheme) {
                        form.dataset.hiddenByTheme = 'true';
                        form.style.opacity = '0';
                        form.style.height = '0';
                        form.style.overflow = 'hidden';
                        form.style.pointerEvents = 'none';

                        var msg = document.createElement('div');
                        msg.id = 'custom-login-msg';
                        msg.style.cssText = 'text-align:center; padding: 32px 12px; color: #38BDF8; font-size: 16px; font-weight: bold;';
                        msg.innerText = 'Kirjaudutaan sisään...';
                        form.parentNode.insertBefore(msg, form);

                        setTimeout(function() {
                            var f = document.getElementById('LoginForm');
                            var m = document.getElementById('custom-login-msg');
                            if (f) {
                                f.style.opacity = '';
                                f.style.height = '';
                                f.style.overflow = '';
                                f.style.pointerEvents = '';
                                delete f.dataset.hiddenByTheme;
                            }
                            if (m) m.remove();
                        }, 5000);
                    }
                }

                function fixDynamicLayoutAndTheme() {
                    ensureThemeStyle();
                    if (!document.body) return;

                    var nodes = document.querySelectorAll('div, ul, section, header');
                    for (var i = 0; i < nodes.length; i++) {
                        var el = nodes[i];
                        var cs = window.getComputedStyle(el);

                        // Poista valkoiset liukuväripalkit (kalenterilistan yläreunan häivytys)
                        if (cs.backgroundImage && cs.backgroundImage.indexOf('gradient') !== -1 &&
                            (cs.backgroundImage.indexOf('255, 255, 255') !== -1 || cs.backgroundImage.indexOf('#fff') !== -1)) {
                            el.style.setProperty('background-image', 'none', 'important');
                            el.style.setProperty('background-color', 'transparent', 'important');
                        }

                        // Muuta dynaamisesti luodut valkoiset kortit ja pudotuslistat tummiksi
                        if (cs.backgroundColor === 'rgb(255, 255, 255)') {
                            el.style.setProperty('background-color', '#1E293B', 'important');
                            el.style.setProperty('color', '#F1F5F9', 'important');
                            el.style.setProperty('border-color', '#334155', 'important');
                        }

                        // Piilota tyhjät yläreunan pillerilaatikot (vaikka sisällä olisi tyhjä span/div)
                        var rawText = (el.innerText || el.textContent || '').trim();
                        if (rawText === '' &&
                            el.offsetHeight > 0 && el.offsetHeight <= 60 && el.offsetWidth > 120 &&
                            !el.querySelector('input, select, textarea, button, img, svg, canvas')) {
                            el.style.setProperty('display', 'none', 'important');
                        }
                    }

                    // Korosta leimaussivun "Tänään"-osio siistiksi vaaleammaksi laatikoksi
                    var all = document.querySelectorAll('div, span, p, label, h1, h2, h3, h4');
                    for (var j = 0; j < all.length; j++) {
                        var lbl = (all[j].innerText || all[j].textContent || '').trim().toLowerCase();
                        if (lbl === 'tänään' && all[j].children.length === 0 && all[j].parentElement) {
                            var box = all[j].parentElement;
                            // Jos parent sisältää vain pelkän otsikon, noustaan yhtä tasoa ylemmäs jotta myös sisältörivi mahtuu laatikkoon
                            var boxText = (box.innerText || box.textContent || '').trim().toLowerCase();
                            if (boxText === 'tänään' && box.parentElement) {
                                box = box.parentElement;
                            }
                            if (box && box.tagName !== 'BODY' && !box.dataset.styledToday) {
                                box.dataset.styledToday = 'true';
                                box.style.setProperty('display', 'block', 'important');
                                box.style.setProperty('background-color', '#334155', 'important');
                                box.style.setProperty('border', '1px solid #64748B', 'important');
                                box.style.setProperty('border-radius', '12px', 'important');
                                box.style.setProperty('padding', '12px 14px', 'important');
                                box.style.setProperty('margin', '0 0 14px 0', 'important');
                                box.style.setProperty('color', '#F8FAFC', 'important');
                                all[j].style.setProperty('color', '#BAE6FD', 'important');
                                all[j].style.setProperty('font-weight', '700', 'important');
                            }
                        }
                    }

                    // Estä kalenteriruudukkoa/listaa peittämästä Tänään- ja Näkymä-nappeja
                    var btnRow = document.querySelector('.mobileAddDiv, .calendarHeaderButtons, .weekNavButtons');
                    if (!btnRow) {
                        var btns = document.querySelectorAll('button, a, div, span');
                        for (var k = 0; k < btns.length; k++) {
                            var bt = (btns[k].innerText || btns[k].textContent || '').trim();
                            if ((bt === 'Näkymä' || bt === 'Tänään') && btns[k].children.length === 0 && btns[k].parentElement) {
                                var cand = btns[k].parentElement;
                                if (cand && cand.offsetHeight > 0 && cand.offsetHeight < 90 && cand.parentElement) {
                                    btnRow = cand.parentElement.offsetHeight < 90 ? cand.parentElement : cand;
                                    break;
                                }
                            }
                        }
                    }
                    if (btnRow) {
                        btnRow.style.setProperty('display', 'flex', 'important');
                        btnRow.style.setProperty('flex-direction', 'row', 'important');
                        btnRow.style.setProperty('align-items', 'center', 'important');
                        btnRow.style.setProperty('justify-content', 'space-between', 'important');
                        btnRow.style.setProperty('position', 'relative', 'important');
                        btnRow.style.setProperty('top', '0px', 'important');
                        btnRow.style.setProperty('margin', '8px 0 12px 0', 'important');
                        btnRow.style.setProperty('height', 'auto', 'important');
                        btnRow.style.setProperty('min-height', '44px', 'important');
                        btnRow.style.setProperty('overflow', 'visible', 'important');
                        btnRow.style.setProperty('z-index', '50', 'important');

                        var next = btnRow.nextElementSibling;
                        if (next) {
                            next.style.setProperty('position', 'relative', 'important');
                            next.style.setProperty('top', '0px', 'important');
                            next.style.setProperty('margin-top', '8px', 'important');
                            next.style.setProperty('transform', 'none', 'important');
                            next.style.setProperty('z-index', '10', 'important');
                        }
                    }
                }

                fixDynamicLayoutAndTheme();
                if (!window._numeronThemeObserver) {
                    window._numeronThemeObserver = new MutationObserver(function() {
                        fixDynamicLayoutAndTheme();
                    });
                    var target = document.body || document.documentElement;
                    if (target) {
                        window._numeronThemeObserver.observe(target, { childList: true, subtree: true });
                    }
                }
            })();"""

JS_REPLACEMENT = (
    '        view?.setBackgroundColor(android.graphics.Color.parseColor("#0F172A"))\n'
    '        val js = """\n' + JS_BODY + '\n        """.trimIndent()'
)


def backup_file(path: Path) -> Path:
    bak = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, bak)
    return bak


def find_main_activity() -> Optional[Path]:
    default = Path("app/src/main/java/fi/oma/numeron/MainActivity.kt")
    if default.exists():
        return default
    matches = list(Path(".").rglob("MainActivity.kt"))
    return matches[0] if matches else None


def ensure_early_theme_hooks(content: str, changes: list) -> str:
    """
    Varmistaa, että:
    1. WebView'n taustaväri asetetaan tummaksi (#0F172A), jotta latauksen aikana ei näy valkoista välähdystä.
    2. Teemafunktiota kutsutaan myös onPageStarted- ja onPageCommitVisible-vaiheissa ennen sivun ensimmäistä piirtoa.
    """
    # Etsi teemafunktion nimi (funktio, joka sisältää 'custom-numeron-theme')
    fn_match = re.search(
        r"fun\s+(\w+)\s*\(\s*view\s*:\s*WebView\?\s*\)[^{]*\{(?:(?!\n\s*(?:private\s+|override\s+)?fun\s).)*?custom-numeron-theme",
        content,
        re.DOTALL,
    )
    if not fn_match:
        return content

    theme_fn = fn_match.group(1)

    # 1. Lisää setBackgroundColor WebView-alustukseen, jos puuttuu
    if "0F172A" not in content.split("custom-numeron-theme")[0]:
        wv_init = re.compile(r"(\bwebView\.settings\.javaScriptEnabled\s*=\s*true)")
        if wv_init.search(content):
            content = wv_init.sub(
                r'\1\n        webView.setBackgroundColor(android.graphics.Color.parseColor("#0F172A"))',
                content,
                count=1,
            )
            changes.append("WebView: taustaväri asetettu #0F172A (estää valkoisen välähdyksen)")

    # 2. Lisää kutsu onPageStarted-metodiin, jos sitä ei vielä ole
    ops_pattern = re.compile(
        r"(override\s+fun\s+onPageStarted\s*\([^)]*\)\s*\{)([^\}]*)",
        re.DOTALL,
    )
    ops_match = ops_pattern.search(content)
    if ops_match and f"{theme_fn}(view)" not in ops_match.group(2):
        replacement = (
            f"{ops_match.group(1)}\n"
            f'                view?.setBackgroundColor(android.graphics.Color.parseColor("#0F172A"))\n'
            f"                {theme_fn}(view)"
            f"{ops_match.group(2)}"
        )
        content = content[: ops_match.start()] + replacement + content[ops_match.end() :]
        changes.append(f"WebViewClient: {theme_fn}(view) lisätty onPageStarted-vaiheeseen")

    # 3. Lisää onPageCommitVisible-ylikirjoitus, jos puuttuu
    if "onPageCommitVisible" not in content:
        opf_pattern = re.compile(r"(override\s+fun\s+onPageFinished\s*\()")
        if opf_pattern.search(content):
            commit_hook = (
                "override fun onPageCommitVisible(view: WebView?, url: String?) {\n"
                "                super.onPageCommitVisible(view, url)\n"
                f"                {theme_fn}(view)\n"
                "            }\n\n            "
            )
            content = opf_pattern.sub(commit_hook + r"\1", content, count=1)
            changes.append(f"WebViewClient: lisätty onPageCommitVisible -> {theme_fn}(view) (estää FOUC-välähdyksen)")

    return content


def patch_main_activity(path: Path) -> bool:
    content = path.read_text(encoding="utf-8")
    original = content
    changes = []

    # 1. Korvaa aiempi CSS-lohko (joko aiemman patch.py:n tai alkuperäisen .mobileAddDiv-lohkon)
    prev_patch_css = re.compile(
        r"[ \t]*/\* 1\. Leimaussivun tyhjät ylälaatikot piiloon \*/.*?\.workShiftCard \* \{\s*color: #F1F5F9 !important;\s*\}",
        re.DOTALL,
    )
    orig_css_pattern = re.compile(
        r"[ \t]*\.mobileAddDiv\s*\{.*?\}\s*\.mobileAddButton,\s*\.filterButton\s*\{.*?\}",
        re.DOTALL,
    )

    if prev_patch_css.search(content):
        content = prev_patch_css.sub(CSS_ADDITION, content, count=1)
        changes.append("CSS: päivitetty leimaussivun, kalenterinappien ja Kendo-valikoiden tyylit")
    elif orig_css_pattern.search(content):
        content = orig_css_pattern.sub(CSS_ADDITION, content, count=1)
        changes.append("CSS: korvattu .mobileAddDiv ja lisätty teemakorjaukset")
    else:
        trim_pattern = re.compile(r'([ \t]*"""\.trimIndent\(\)\.replace\("\\n",\s*" "\))')
        if trim_pattern.search(content) and "fixDynamicLayoutAndTheme" not in content:
            content = trim_pattern.sub(CSS_ADDITION + r"\n\1", content, count=1)
            changes.append("CSS: lisätty puuttuvat tyylisäännöt ennen .trimIndent()")

    # 2. Korvaa val js = """ ... """.trimIndent() -lohko
    js_block_pattern = re.compile(
        r'(?:[ \t]*view\?\.setBackgroundColor\([^\n]*\)\n)?[ \t]*val js\s*=\s*""".*?custom-numeron-theme.*?"""\.trimIndent\(\)',
        re.DOTALL,
    )
    if js_block_pattern.search(content):
        content = js_block_pattern.sub(JS_REPLACEMENT, content, count=1)
        changes.append("JS: varhainen tyylikiinnitys + Tänään-laatikon korjaus + kalenterinappien nosto")
    else:
        print(f"[VAROITUS] Tiedostosta {path} ei löytynyt 'val js = \"\"\" ... custom-numeron-theme' -lohkoa.")

    # 3. Varmista aikaiset WebViewClient-hookit välähdyksen estämiseksi
    content = ensure_early_theme_hooks(content, changes)

    if content == original:
        print(f"[INFO] {path}: Ei muutettavaa (mahdollisesti jo päivitetty).")
        return False

    bak = backup_file(path)
    path.write_text(content, encoding="utf-8")
    print(f"[OK] Päivitetty {path} (varmuuskopio: {bak}):")
    for c in changes:
        print(f"     - {c}")
    return True


def step_version_name(ver: str, subpatch: bool = False) -> str:
    parts = ver.strip().split(".")
    if not all(p.isdigit() for p in parts):
        return ver

    nums = [int(p) for p in parts]
    if len(nums) == 2:
        nums.append(1)
    elif len(nums) == 3:
        if subpatch:
            nums.append(1)
        else:
            nums[-1] += 1
    else:
        nums[-1] += 1

    return ".".join(str(n) for n in nums)


def patch_gradle_file(path: Path, subpatch: bool = False) -> bool:
    content = path.read_text(encoding="utf-8")
    original = content
    changes = []

    def shrink_vc_step(match: re.Match) -> str:
        prefix, op, num_str = match.group(1), match.group(2), match.group(3)
        if int(num_str) > 1:
            changes.append(f"versionCode-askel pienennetty: {op} {num_str} -> {op} 1")
            return f"{prefix}{op} 1"
        return match.group(0)

    content = re.sub(
        r"(versionCode\s*=?\s*[^\n]*?)([*+])\s*([2-9]\d*|1\d+)",
        shrink_vc_step,
        content,
    )

    def bump_static_vc(match: re.Match) -> str:
        prefix, num_str = match.group(1), match.group(2)
        old_vc = int(num_str)
        new_vc = old_vc + 1
        changes.append(f"versionCode: {old_vc} -> {new_vc} (+1)")
        return f"{prefix}{new_vc}"

    content = re.sub(
        r"(versionCode\s*(?:=\s*|\s+))(\d+)\b",
        bump_static_vc,
        content,
        count=1,
    )

    def bump_vn(match: re.Match) -> str:
        prefix, quote, old_vn = match.group(1), match.group(2), match.group(3)
        new_vn = step_version_name(old_vn, subpatch=subpatch)
        if new_vn != old_vn:
            changes.append(f"versionName: {old_vn} -> {new_vn}")
        return f"{prefix}{quote}{new_vn}{quote}"

    content = re.sub(
        r'(versionName\s*(?:=\s*|\s+))(["\'])(\d+(?:\.\d+)+)\2',
        bump_vn,
        content,
        count=1,
    )

    if content == original:
        return False

    bak = backup_file(path)
    path.write_text(content, encoding="utf-8")
    print(f"[OK] Päivitetty {path} (varmuuskopio: {bak}):")
    for c in changes:
        print(f"     - {c}")
    return True


def patch_workflow_files() -> bool:
    updated_any = False
    wf_files = sorted(Path(".github/workflows").glob("*.y*ml")) if Path(".github/workflows").exists() else []

    for wf in wf_files:
        content = wf.read_text(encoding="utf-8")
        original = content
        changes = []

        replacements = [
            (r"\$2\s*=\s*\$2\s*\+\s*1", "$NF = $NF + 1", "awk: minor ($2+1) -> viimeinen osa ($NF+1)"),
            (r"\$2\+\+", "$NF++", "awk: minor ($2++) -> viimeinen osa ($NF++)"),
            (r"parts\[1\]\s*\+=\s*1", "parts[-1] += 1", "python: parts[1] += 1 -> parts[-1] += 1"),
            (r"parts\[1\]\s*\+\s*1", "parts[-1] + 1", "python: parts[1] + 1 -> parts[-1] + 1"),
            (r"MINOR=\$\(\(MINOR\s*\+\s*1\)\)", "PATCH=$((PATCH + 1))", "shell: MINOR+1 -> PATCH+1"),
            (r"(versionCode[^\n]*?)([*+])\s*([2-9]\d*|1\d+)", r"\g<1>\g<2> 1", "workflow: versionCode-askel -> 1"),
        ]

        for pat, rep, desc in replacements:
            new_content, count = re.subn(pat, rep, content)
            if count > 0:
                content = new_content
                changes.append(desc)

        if content != original:
            bak = backup_file(wf)
            wf.write_text(content, encoding="utf-8")
            print(f"[OK] Päivitetty {wf} (varmuuskopio: {bak}):")
            for c in changes:
                print(f"     - {c}")
            updated_any = True

    return updated_any


def main() -> int:
    parser = argparse.ArgumentParser(description="Numeron-sovelluksen UI-, FOUC- ja versiopäivitys")
    parser.add_argument(
        "--subpatch",
        action="store_true",
        help="Lisää 4. tason versionNameen (esim. 1.2.3 -> 1.2.3.1) 3-osaisen patch-kasvatuksen sijaan",
    )
    args = parser.parse_args()

    any_patched = False

    main_kt = find_main_activity()
    if main_kt:
        if patch_main_activity(main_kt):
            any_patched = True
    else:
        print("[VIRHE] MainActivity.kt-tiedostoa ei löytynyt. Aja skripti projektin juurikansiossa.")

    for gf in [Path("app/build.gradle.kts"), Path("app/build.gradle"), Path("gradle.properties")]:
        if gf.exists() and patch_gradle_file(gf, subpatch=args.subpatch):
            any_patched = True

    if patch_workflow_files():
        any_patched = True

    if not any_patched:
        print("[VALMIS] Ei uusia muutoksia tehtäväksi.")
    else:
        print("[VALMIS] Kaikki päivitykset tehty.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
