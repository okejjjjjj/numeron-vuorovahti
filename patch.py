#!/usr/bin/env python3
"""
patch.py — Päivittää Numeron-sovelluksen WebView-teeman/kirjautumiskorjaukset
sekä muuttaa versionumeron kasvatuksen yhden pykälän pienemmille askelille.

Käyttö:
    python3 patch.py
    python3 patch.py --subpatch   # (valinnainen) lisää 4. tason versionNameen (esim. 1.2.3 -> 1.2.3.1)
"""

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Optional


CSS_ADDITION = """            /* 1. Leimaussivun tyhjät ylälaatikot piiloon */
            .alert:empty, .messageBox:empty, .infoBox:empty, .statusBox:empty,
            .mobileHeader:empty, .punchHeader:empty {
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

            /* 3. Kalenterinäkymän Tänään- ja Näkymä-napit samalle riville ja päällimmäiseksi */
            .mobileAddDiv, .calendarHeaderButtons, .weekNavButtons {
                display: flex !important;
                flex-direction: row !important;
                align-items: center !important;
                justify-content: space-between !important;
                gap: 8px !important;
                background-color: transparent !important;
                background-image: none !important;
                margin: 8px 0 10px 0 !important;
                padding: 4px 2px !important;
                height: auto !important;
                min-height: 44px !important;
                overflow: visible !important;
                position: relative !important;
                z-index: 30 !important;
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
                overflow: visible !important;
                z-index: 31 !important;
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
                var styleId = 'custom-numeron-theme';
                var style = document.getElementById(styleId);
                if (!style) {
                    style = document.createElement('style');
                    style.id = styleId;
                    style.type = 'text/css';
                    (document.head || document.documentElement).appendChild(style);
                }
                style.innerHTML = `$css`;

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

                        // Varamekanismi: palautetaan lomake näkyviin 5 s kuluttua, jos kirjautuminen ei etene
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

                function fixDynamicLightBoxes() {
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

                        // Piilota leimaussivun tyhjät yläreunan pillerilaatikot
                        if (el.children.length === 0 && el.textContent.trim() === '' &&
                            el.offsetHeight > 0 && el.offsetHeight < 42 && el.offsetWidth > 150) {
                            el.style.setProperty('display', 'none', 'important');
                        }
                    }

                    // Korosta "TÄNÄÄN"-osio siistiksi vaaleaksi laatikoksi leimaussivulla
                    var all = document.querySelectorAll('div, span, p, label');
                    for (var j = 0; j < all.length; j++) {
                        if (all[j].textContent.trim() === 'TÄNÄÄN' && all[j].parentElement) {
                            var box = all[j].parentElement;
                            if (!box.dataset.styledToday) {
                                box.dataset.styledToday = 'true';
                                box.style.setProperty('background-color', '#334155', 'important');
                                box.style.setProperty('border', '1px solid #475569', 'important');
                                box.style.setProperty('border-radius', '12px', 'important');
                                box.style.setProperty('padding', '10px 14px', 'important');
                                box.style.setProperty('margin-bottom', '12px', 'important');
                            }
                        }
                    }
                }

                fixDynamicLightBoxes();
                if (!window._numeronThemeObserver) {
                    window._numeronThemeObserver = new MutationObserver(function() {
                        fixDynamicLightBoxes();
                    });
                    window._numeronThemeObserver.observe(document.body, { childList: true, subtree: true });
                }
            })();"""

JS_REPLACEMENT = '        val js = """\n' + JS_BODY + '\n        """.trimIndent()'


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


def patch_main_activity(path: Path) -> bool:
    content = path.read_text(encoding="utf-8")
    original = content
    changes = []

    # 1. Korvaa vanha .mobileAddDiv + .mobileAddButton, .filterButton -lohko
    old_css_pattern = re.compile(
        r"[ \t]*\.mobileAddDiv\s*\{.*?\}\s*\.mobileAddButton,\s*\.filterButton\s*\{.*?\}",
        re.DOTALL,
    )
    if old_css_pattern.search(content):
        content = old_css_pattern.sub(CSS_ADDITION, content, count=1)
        changes.append("CSS: leimaussivun ylälaatikko, Kendo-valikot, kalenterinapit ja vuorokortit")
    else:
        trim_pattern = re.compile(r'([ \t]*"""\.trimIndent\(\)\.replace\("\\n",\s*" "\))')
        if trim_pattern.search(content) and "fixDynamicLightBoxes" not in content:
            content = trim_pattern.sub(CSS_ADDITION + r"\n\1", content, count=1)
            changes.append("CSS: lisätty puuttuvat tyylisäännöt ennen .trimIndent()")

    # 2. Korvaa val js = """ ... """.trimIndent() -lohko
    js_block_pattern = re.compile(
        r'[ \t]*val js\s*=\s*""".*?style\.innerHTML\s*=\s*`\$css`;.*?"""\.trimIndent\(\)',
        re.DOTALL,
    )
    if js_block_pattern.search(content):
        content = js_block_pattern.sub(JS_REPLACEMENT, content, count=1)
        changes.append("JS: kirjautumislomakkeen visuaalinen piilotus + 5s varamekanismi + fixDynamicLightBoxes()")
    else:
        print(f"[VAROITUS] Tiedostosta {path} ei löytynyt 'val js = \"\"\" ... style.innerHTML = `$css`;' -lohkoa.")

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
    """
    Kasvattaa versionNamea pykälän pienemmällä askeleella:
    - 2-osainen (esim. "1.4") -> 3-osainen ("1.4.1")
    - 3-osainen (esim. "1.4.0" tai "1.4.2") -> kasvattaa viimeistä (patch) osaa +1 ("1.4.1" / "1.4.3"),
      tai --subpatch-tilassa lisää 4. osan ("1.4.2.1")
    - 4-osainen (esim. "1.4.2.1") -> kasvattaa 4. osaa +1 ("1.4.2.2")
    """
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

    # 1. Pienennä dynaamisen versionCoden kerroin / askel -> 1 (esim. * 10 -> * 1, + 10 -> + 1)
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

    # 2. Jos versionCode on staattinen kokonaisluku, kasvata +1
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

    # 3. Kasvata versionNamea pykälän pienemmällä askeleella
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


def patch_workflow_files(subpatch: bool = False) -> bool:
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
    parser = argparse.ArgumentParser(description="Numeron-sovelluksen UI- ja versiopäivitys")
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

    gradle_candidates = [
        Path("app/build.gradle.kts"),
        Path("app/build.gradle"),
        Path("gradle.properties"),
    ]
    for gf in gradle_candidates:
        if gf.exists():
            if patch_gradle_file(gf, subpatch=args.subpatch):
                any_patched = True

    if patch_workflow_files(subpatch=args.subpatch):
        any_patched = True

    if not any_patched:
        print("[VALMIS] Ei uusia muutoksia tehtäväksi.")
    else:
        print("[VALMIS] Kaikki päivitykset tehty.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
