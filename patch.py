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

    old_calendar_css = """            .calendar-body, .calendar-heading {
                background-color: #1E293B !important;
                box-shadow: none !important;
                border: 1px solid #334155 !important;
                border-radius: 14px !important;
                padding: 8px !important;
                margin-bottom: 10px !important;
            }
            .calendar-heading { display: flex !important; flex-wrap: wrap !important; align-items: center !important; justify-content: space-between !important; gap: 8px !important; padding: 10px !important; }
            .calendar-heading .monthSelector { display: contents !important; }
            .calendar-heading .monthSelector .panel-body {
                order: 1 !important;
                width: 100% !important;
                display: flex !important;
                align-items: center !important;
                justify-content: space-between !important;
                padding: 0 4px 4px 4px !important;
                margin: 0 !important;
                float: none !important;
            }
            #monthText { color: #F8FAFC !important; font-size: 18px !important; font-weight: bold !important; margin: 0 !important; }
            #pc_AddButton { order: 2 !important; width: 100% !important; display: flex !important; gap: 8px !important; margin: 0 !important; float: none !important; }
            #pc_AddButton > .btn-group, #pc_AddButton > .dropdown { flex: 1 !important; margin: 0 !important; display: block !important; }
            #pcAddButt, #pc_AddButton .filterButton {
                width: 100% !important;
                height: 36px !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                padding: 6px 10px !important;
                font-size: 13px !important;
            }
            #pcTodayButton, #pcViewDropdown { order: 3 !important; flex: 1 1 46% !important; display: block !important; margin: 0 !important; float: none !important; }
            #todayButt, #pcViewButt { width: 100% !important; max-width: none !important; min-width: 0 !important; height: 36px !important; padding: 6px 10px !important; font-size: 13px !important; }
            #pcViewDropdown .dropdown-menu { right: 0 !important; left: auto !important; }"""

    new_calendar_css = """            .calendar-body, .calendar-heading {
                background-color: #1E293B !important;
                box-shadow: none !important;
                border: 1px solid #334155 !important;
                border-radius: 14px !important;
                padding: 8px !important;
                margin-bottom: 10px !important;
                height: auto !important;
                min-height: 0 !important;
                max-height: none !important;
                overflow: visible !important;
            }
            .calendar-heading {
                display: flex !important;
                flex-wrap: wrap !important;
                align-items: center !important;
                justify-content: space-between !important;
                gap: 8px !important;
                padding: 10px !important;
                position: static !important;
            }
            .calendar-heading .monthSelector, .calendar-heading .weekSelector { display: contents !important; }
            .calendar-heading .monthSelector .panel-body, .calendar-heading .weekSelector .panel-body {
                order: 1 !important;
                width: 100% !important;
                height: auto !important;
                min-height: 0 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: space-between !important;
                padding: 0 4px 4px 4px !important;
                margin: 0 !important;
                float: none !important;
                position: static !important;
            }
            #monthText, #weekText, .calendar-heading .view-label {
                color: #F8FAFC !important;
                font-size: 18px !important;
                font-weight: bold !important;
                margin: 0 !important;
                line-height: 1.2 !important;
            }
            #pc_AddButton {
                order: 2 !important;
                width: 100% !important;
                height: auto !important;
                min-height: 0 !important;
                display: flex !important;
                gap: 8px !important;
                margin: 0 !important;
                float: none !important;
                position: static !important;
            }
            #pc_AddButton > .btn-group, #pc_AddButton > .dropdown {
                flex: 1 !important;
                margin: 0 !important;
                display: block !important;
                position: relative !important;
            }
            #pcAddButt, #pc_AddButton .filterButton {
                width: 100% !important;
                height: 36px !important;
                min-height: 36px !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                padding: 6px 10px !important;
                margin: 0 !important;
                font-size: 13px !important;
                line-height: 1.2 !important;
                position: static !important;
                top: auto !important;
            }
            #pcTodayButton, #pcViewDropdown {
                order: 3 !important;
                flex: 1 1 46% !important;
                height: auto !important;
                min-height: 0 !important;
                display: block !important;
                margin: 0 !important;
                float: none !important;
                position: relative !important;
                top: auto !important;
            }
            #todayButt, #pcViewButt {
                width: 100% !important;
                max-width: none !important;
                min-width: 0 !important;
                height: 36px !important;
                min-height: 36px !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                padding: 6px 10px !important;
                margin: 0 !important;
                font-size: 13px !important;
                line-height: 1.2 !important;
                position: static !important;
                top: auto !important;
            }
            #pcViewDropdown .dropdown-menu, #pc_AddButton .dropdown-menu {
                z-index: 1060 !important;
                top: 100% !important;
                margin-top: 4px !important;
            }
            #pcViewDropdown .dropdown-menu { right: 0 !important; left: auto !important; }
            #calendar-content {
                height: auto !important;
                min-height: 0 !important;
                max-height: none !important;
                overflow: visible !important;
                clear: both !important;
                position: static !important;
            }
            #calendar-content hr { border-color: #334155 !important; margin: 8px 0 !important; }
            #calendar-content .list-week-header, #calendar-content .week-header, #calendar-content h3, #calendar-content h4 {
                color: #38BDF8 !important;
                border-color: #334155 !important;
                background: transparent !important;
            }
            #calendar-content .list-day-header, #calendar-content .day-header, #calendar-content .list-date-header {
                color: #F8FAFC !important;
                background: transparent !important;
            }
            #calendar-content .list-item, #calendar-content .list-item-work, #calendar-content .list-item-content,
            #calendar-content .calendar-list-item, #calendar-content .schedule-item, #calendar-content .schedule-item-work,
            #calendar-content .list-day-item, #calendar-content .shift-item {
                background-color: #1E293B !important;
                background-image: none !important;
                color: #F1F5F9 !important;
                border-color: #334155 !important;
            }
            #calendar-content .list-item, #calendar-content .calendar-list-item, #calendar-content .schedule-item {
                border: 1px solid #334155 !important;
                border-left: 4px solid #0284C7 !important;
                border-radius: 12px !important;
                padding: 8px 10px !important;
                margin: 6px 0 !important;
            }
            #calendar-content .list-item *, #calendar-content .calendar-list-item *, #calendar-content .schedule-item * {
                color: #F1F5F9 !important;
                border-color: #334155 !important;
            }"""

    old_js_block = """                function attachTheme() {
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
                }
                if (!attachTheme()) {
                    var obs = new MutationObserver(function() {
                        if (attachTheme()) obs.disconnect();
                    });
                    obs.observe(document, { childList: true, subtree: true });
                }"""

    new_js_block = """                function fixCalendarListTheme() {
                    var rootEl = document.getElementById('calendar-content') || document.querySelector('.calendar-body');
                    if (!rootEl) return;
                    var nodes = rootEl.querySelectorAll('div, table, tbody, tr, td, section, article, ul, li');
                    for (var i = 0; i < nodes.length; i++) {
                        var el = nodes[i];
                        if (el.classList && (el.classList.contains('month-item') || el.classList.contains('month-day'))) continue;
                        var cs = window.getComputedStyle(el);
                        var bg = cs.backgroundColor;
                        var m = bg && bg.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\\)/);
                        if (m) {
                            var a = m[4] !== undefined ? parseFloat(m[4]) : 1;
                            if (a > 0.1 && parseInt(m[1], 10) > 205 && parseInt(m[2], 10) > 205 && parseInt(m[3], 10) > 205) {
                                el.style.setProperty('background-color', '#1E293B', 'important');
                                el.style.setProperty('background-image', 'none', 'important');
                                el.style.setProperty('border-color', '#334155', 'important');
                                if (el.offsetHeight >= 44 && el.offsetHeight <= 260 && el.offsetWidth > 180) {
                                    el.style.setProperty('border', '1px solid #334155', 'important');
                                    el.style.setProperty('border-left', '4px solid #0284C7', 'important');
                                    el.style.setProperty('border-radius', '12px', 'important');
                                }
                            }
                        }
                        var col = cs.color;
                        var cm = col && col.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                        if (cm) {
                            var r = parseInt(cm[1], 10), g = parseInt(cm[2], 10), b = parseInt(cm[3], 10);
                            if (r < 130 && g < 130 && b < 130) {
                                el.style.setProperty('color', '#E2E8F0', 'important');
                            }
                        }
                    }
                }
                function attachTheme() {
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
                    fixCalendarListTheme();
                    return true;
                }
                attachTheme();
                if (!window._numeronThemeObserver) {
                    window._numeronThemeObserver = new MutationObserver(function() {
                        attachTheme();
                    });
                    window._numeronThemeObserver.observe(document, { childList: true, subtree: true });
                }"""

    updated = False

    if old_calendar_css in content:
        content = content.replace(old_calendar_css, new_calendar_css, 1)
        updated = True
        print(f"[OK] Kalenteri- ja listanäkymän CSS päivitetty: {path}")
    elif "#calendar-content .schedule-item" in content:
        print(f"[INFO] Kalenteri- ja listanäkymän CSS oli jo ajan tasalla: {path}")
    else:
        print(f"[VIRHE] Kalenterin CSS-lohkoa ei löytynyt tiedostosta {path}")
        return False

    if old_js_block in content:
        content = content.replace(old_js_block, new_js_block, 1)
        updated = True
        print(f"[OK] fixCalendarListTheme() ja MutationObserver päivitetty: {path}")
    elif "fixCalendarListTheme()" in content:
        print(f"[INFO] JS-teemapäivitys oli jo ajan tasalla: {path}")
    else:
        print(f"[VIRHE] attachTheme()-lohkoa ei löytynyt tiedostosta {path}")
        return False

    if updated:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    return True

def bump_gradle_version(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    vc_pattern = re.compile(r'(\bversionCode\s*=?\s*)(\d+)')
    vc_match = vc_pattern.search(content)
    if not vc_match:
        print(f"[VAROITUS] versionCode-kenttää ei löytynyt tiedostosta {path}")
        return False

    old_vc = int(vc_match.group(2))
    new_vc = old_vc + 1
    content = vc_pattern.sub(rf'\g<1>{new_vc}', content, count=1)

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
