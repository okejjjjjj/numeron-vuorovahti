import os
import re
import sys

def find_file(preferred_paths, filename):
    for p in preferred_paths:
        if os.path.isfile(p):
            return p
    for root, _, files in os.walk("."):
        if ".git" in root or "build" in root.split(os.sep):
            continue
        if filename in files:
            return os.path.join(root, filename)
    return None

def patch_main_activity(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    old_css_block = """            .nav-tabs-wts { border-bottom: 1px solid #334155 !important; }
            .nav-tabs-wts > li.active > a { background-color: transparent !important; color: #38BDF8 !important; border-bottom: 2px solid #38BDF8 !important; }
            .table, .table > tbody > tr > td, .table > tbody > tr > th, .table-active, .table-active > td {
                background: transparent !important;
                background-color: transparent !important;
                color: #E2E8F0 !important;
            }
            #table-latest-stamps tr { border-bottom: 1px solid #334155 !important; }
            #table-latest-stamps tr:hover td, #table-latest-stamps tr:active td { background-color: #334155 !important; color: #FFFFFF !important; }
            #table-latest-stamps td { border: none !important; padding: 10px 6px !important; }"""

    new_css_block = """            #panel-body-tabs, .punching-events-container-header, .punching-events-caption,
            .tab-content-wts, .tab-pane-wts, #latestStampsContainer, .punching-bottom-container,
            .punching-previous-stamps, .punching-previous-stamps-container-header, .punching-show-more-button {
                background: transparent !important;
                background-color: transparent !important;
                color: #E2E8F0 !important;
            }
            .nav-tabs-wts { border-bottom: 1px solid #334155 !important; background: transparent !important; }
            .nav-tabs-wts > li > a, .wts-tab-item > a {
                background: transparent !important;
                background-color: transparent !important;
                color: #94A3B8 !important;
                border: none !important;
            }
            .nav-tabs-wts > li.active > a, .nav-tabs-wts > li.active > a:focus, .nav-tabs-wts > li.active > a:hover {
                background: transparent !important;
                background-color: transparent !important;
                color: #38BDF8 !important;
                border: none !important;
                border-bottom: 2px solid #38BDF8 !important;
            }
            .table, .table > tbody, .table > tbody > tr, .table > tbody > tr > td, .table > tbody > tr > th,
            .table-active, .table-active > tbody > tr, .table-active > tbody > tr > td, .table-active > td,
            #table-latest-stamps, #table-latest-stamps tbody, #table-latest-stamps tr, #table-latest-stamps td {
                background: transparent !important;
                background-color: transparent !important;
                background-image: none !important;
                color: #E2E8F0 !important;
            }
            #table-latest-stamps tr { border-bottom: 1px solid #334155 !important; }
            #table-latest-stamps tr:hover, #table-latest-stamps tr:hover td,
            #table-latest-stamps tr:active, #table-latest-stamps tr:active td {
                background-color: #334155 !important;
                color: #FFFFFF !important;
            }
            #table-latest-stamps td { border: none !important; padding: 10px 6px !important; }
            .visma-icon-arrow-next-icon { filter: invert(0.85) brightness(1.2) !important; }"""

    old_attach_block = """                function attachTheme() {
                    var root = document.head || document.documentElement;
                    if (!root) return false;
                    var style = document.getElementById('custom-numeron-theme');
                    if (!style) {
                        style = document.createElement('style');
                        style.id = 'custom-numeron-theme';
                        style.textContent = cssText;
                        root.appendChild(style);
                    }
                    return true;
                }"""

    new_attach_block = """                function attachTheme() {
                    var root = document.documentElement || document.head;
                    if (!root) return false;
                    var style = document.getElementById('custom-numeron-theme');
                    if (!style) {
                        style = document.createElement('style');
                        style.id = 'custom-numeron-theme';
                        style.textContent = cssText;
                    }
                    if (style.parentNode !== root || root.lastElementChild !== style) {
                        root.appendChild(style);
                    }
                    return true;
                }"""

    updated = False

    if old_css_block in content:
        content = content.replace(old_css_block, new_css_block, 1)
        updated = True
        print(f"[OK] CSS-säännöt päivitetty: {path}")
    elif ".visma-icon-arrow-next-icon" in content:
        print(f"[INFO] CSS-säännöt olivat jo ajan tasalla: {path}")
    else:
        print(f"[VIRHE] CSS-kohtaa ei löytynyt tiedostosta {path}")
        return False

    if old_attach_block in content:
        content = content.replace(old_attach_block, new_attach_block, 1)
        updated = True
        print(f"[OK] attachTheme() päivitetty: {path}")
    elif "root.lastElementChild !== style" in content:
        print(f"[INFO] attachTheme() oli jo ajan tasalla: {path}")
    else:
        print(f"[VIRHE] attachTheme()-kohtaa ei löytynyt tiedostosta {path}")
        return False

    if updated:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    return True

def bump_gradle_version(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Korottaa versionCode-arvoa +1 (esim. versionCode = 14 -> 15 tai versionCode 14 -> 15)
    vc_pattern = re.compile(r'(\bversionCode\s*=?\s*)(\d+)')
    vc_match = vc_pattern.search(content)
    if not vc_match:
        print(f"[VAROITUS] versionCode-kenttää ei löytynyt tiedostosta {path}")
        return False

    old_vc = int(vc_match.group(2))
    new_vc = old_vc + 1
    content = vc_pattern.sub(rf'\g<1>{new_vc}', content, count=1)

    # Korottaa versionName-merkkijonon viimeistä numeroa +1 (esim. "1.4.2" -> "1.4.3")
    vn_pattern = re.compile(r'(\bversionName\s*=?\s*["\'])([^"\']+)(["\'])')
    vn_match = vn_pattern.search(content)
    vn_info = ""
    if vn_match:
        old_vn = vn_match.group(2)
        num_parts = re.search(r'(\d+)([^\d]*)$', old_vn)
        if num_parts:
            bumped_num = int(num_parts.group(1)) + 1
            new_vn = old_vn[:num_parts.start(1)] + str(bumped_num) + num_parts.group(2)
            content = vn_pattern.sub(rf'\g<1>{new_vn}\g<3>', content, count=1)
            vn_info = f", versionName: {old_vn} -> {new_vn}"

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[OK] Versionumero päivitetty ({path}): versionCode {old_vc} -> {new_vc}{vn_info}")
    return True

def main():
    main_kt = find_file(
        [
            "app/src/main/java/fi/oma/numeron/MainActivity.kt",
            "MainActivity.kt",
        ],
        "MainActivity.kt",
    )
    if not main_kt:
        print("[VIRHE] MainActivity.kt-tiedostoa ei löytynyt.")
        sys.exit(1)

    if not patch_main_activity(main_kt):
        sys.exit(1)

    gradle_file = find_file(
        [
            "app/build.gradle.kts",
            "app/build.gradle",
            "build.gradle.kts",
            "build.gradle",
        ],
        "build.gradle.kts",
    ) or find_file(["app/build.gradle", "build.gradle"], "build.gradle")

    if gradle_file:
        bump_gradle_version(gradle_file)
    else:
        print("[VAROITUS] app/build.gradle(.kts) ei löytynyt – versionCode jäi päivittämättä.")

if __name__ == "__main__":
    main()
