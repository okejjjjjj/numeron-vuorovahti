import os
import sys

OLD_STYLE_INJECT = r'''        val safeCss = css.replace("\\", "\\\\").replace("'", "\\'")
        val js = """
            (function() {
                var style = document.getElementById('custom-dark-theme');
                if (!style) {
                    style = document.createElement('style');
                    style.id = 'custom-dark-theme';
                    (document.head || document.documentElement).appendChild(style);
                    style.textContent = '$safeCss';
                }'''

NEW_STYLE_INJECT = r'''        val safeCss = css
            .replace("\r", " ")
            .replace("\n", " ")
            .replace("\\", "\\\\")
            .replace("'", "\\'")
        val js = """
            (function() {
                var style = document.getElementById('custom-dark-theme');
                if (!style) {
                    style = document.createElement('style');
                    style.id = 'custom-dark-theme';
                }
                var targetParent = document.head || document.documentElement;
                if (targetParent && style.parentNode !== targetParent) {
                    targetParent.appendChild(style);
                }
                if (style.textContent !== '$safeCss') {
                    style.textContent = '$safeCss';
                }'''

OLD_NESTED_STAMP = r'''                        if (existingWp && nameEl.getAttribute('data-formatted-for') === 'v3:' + rawText) {
                            return;
                        }
                        nameEl.setAttribute('data-raw-shift', rawText);
                        nameEl.setAttribute('data-formatted-for', 'v3:' + rawText);

                // === SISÄÄN / ULOS -LEIMAUKSEN VÄRIKOODAUS ===
                (function setupStampingColorCoding() {
                    function applyStampingColors() {
                        var btn = document.getElementById('punchButton');
                        if (btn) {
                            var btnTxt = (btn.innerText || btn.textContent || '').toLowerCase();
                            if (btnTxt.indexOf('ulos') !== -1 || btnTxt.indexOf('out') !== -1) {
                                btn.classList.remove('vv-punch-in');
                                btn.classList.add('vv-punch-out');
                            } else if (btnTxt.indexOf('sisään') !== -1 || btnTxt.indexOf('in') !== -1) {
                                btn.classList.remove('vv-punch-out');
                                btn.classList.add('vv-punch-in');
                            }
                        }

                        var rows = document.querySelectorAll('#table-latest-stamps tr');
                        for (var i = 0; i < rows.length; i++) {
                            var cells = rows[i].querySelectorAll('td');
                            if (!cells || cells.length === 0) continue;
                            for (var j = 0; j < cells.length; j++) {
                                var cell = cells[j];
                                var raw = (cell.textContent || '').replace(/\s+/g, ' ').trim();
                                var lower = raw.toLowerCase();
                                if (lower === 'sisään' || lower === 'in' || lower === 'ulos' || lower === 'out') {
                                    var isIn = (lower === 'sisään' || lower === 'in');
                                    var badge = cell.querySelector('.vv-stamp-badge');
                                    if (!badge) {
                                        cell.textContent = '';
                                        badge = document.createElement('span');
                                        badge.className = 'vv-stamp-badge';
                                        cell.appendChild(badge);
                                    }
                                    badge.textContent = raw;
                                    badge.classList.toggle('vv-stamp-in', isIn);
                                    badge.classList.toggle('vv-stamp-out', !isIn);
                                }
                            }
                        }
                    }

                    applyStampingColors();
                    if (!window._stampingColorObserverInstalled && document.body && typeof MutationObserver !== 'undefined') {
                        window._stampingColorObserverInstalled = true;
                        var stampObs = new MutationObserver(function() {
                            applyStampingColors();
                        });
                        stampObs.observe(document.body, { childList: true, subtree: true, characterData: true });
                    }
                })();'''

NEW_UNNESTED_HEAD = r'''                        if (existingWp && nameEl.getAttribute('data-formatted-for') === 'v3:' + rawText) {
                            return;
                        }
                        nameEl.setAttribute('data-raw-shift', rawText);
                        nameEl.setAttribute('data-formatted-for', 'v3:' + rawText);'''

OLD_TODAY_END = r'''                    applyShiftFormat();
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
                })();'''

NEW_TODAY_END_WITH_STAMP = r'''                    applyShiftFormat();
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
                })();

                // === SISÄÄN / ULOS -LEIMAUKSEN VÄRIKOODAUS ===
                try {
                    (function setupStampingColorCoding() {
                        function applyStampingColors() {
                            var btn = document.getElementById('punchButton');
                            if (btn) {
                                var btnTxt = (btn.innerText || btn.textContent || '').toLowerCase();
                                if (btnTxt.indexOf('ulos') !== -1 || btnTxt.indexOf('out') !== -1) {
                                    btn.classList.remove('vv-punch-in');
                                    btn.classList.add('vv-punch-out');
                                } else if (btnTxt.indexOf('sisään') !== -1 || btnTxt.indexOf('in') !== -1) {
                                    btn.classList.remove('vv-punch-out');
                                    btn.classList.add('vv-punch-in');
                                }
                            }

                            var rows = document.querySelectorAll('#table-latest-stamps tr');
                            for (var i = 0; i < rows.length; i++) {
                                var cells = rows[i].querySelectorAll('td');
                                if (!cells || cells.length === 0) continue;
                                for (var j = 0; j < cells.length; j++) {
                                    var cell = cells[j];
                                    var raw = (cell.textContent || '').replace(/\s+/g, ' ').trim();
                                    var lower = raw.toLowerCase();
                                    if (lower === 'sisään' || lower === 'in' || lower === 'ulos' || lower === 'out') {
                                        var isIn = (lower === 'sisään' || lower === 'in');
                                        var badge = cell.querySelector('.vv-stamp-badge');
                                        if (!badge) {
                                            cell.textContent = '';
                                            badge = document.createElement('span');
                                            badge.className = 'vv-stamp-badge';
                                            cell.appendChild(badge);
                                        }
                                        badge.textContent = raw;
                                        badge.classList.toggle('vv-stamp-in', isIn);
                                        badge.classList.toggle('vv-stamp-out', !isIn);
                                    }
                                }
                            }
                        }

                        applyStampingColors();
                        if (!window._stampingColorObserverInstalled && document.body && typeof MutationObserver !== 'undefined') {
                            window._stampingColorObserverInstalled = true;
                            var stampObs = new MutationObserver(function() {
                                applyStampingColors();
                            });
                            stampObs.observe(document.body, { childList: true, subtree: true, characterData: true });
                        }
                    })();
                } catch (_e) {}'''


def find_file(filename):
    default_path = os.path.join("app", "src", "main", "java", "fi", "numeron", "vuorovahti", filename)
    if os.path.isfile(default_path):
        return default_path
    for root, _, files in os.walk("."):
        if filename in files:
            return os.path.join(root, filename)
    return None


def main():
    main_path = find_file("MainActivity.kt")
    if not main_path:
        print("VIRHE: MainActivity.kt ei löytynyt.")
        sys.exit(1)

    with open(main_path, "r", encoding="utf-8") as f:
        src = f.read()

    changed = False
    for label, old, new in [
        ("Tyylielementin päivitys", OLD_STYLE_INJECT, NEW_STYLE_INJECT),
        ("Sisäkkäisen leimausvärikoodauksen poisto", OLD_NESTED_STAMP, NEW_UNNESTED_HEAD),
        ("Leimausvärikoodauksen siirto ylätasolle", OLD_TODAY_END, NEW_TODAY_END_WITH_STAMP),
    ]:
        if new in src:
            continue
        if old not in src:
            print(f"VAROITUS: Kohtaa '{label}' ei löytynyt.")
            continue
        src = src.replace(old, new, 1)
        changed = True

    if changed:
        with open(main_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(src)
        print(f"Päivitetty: {main_path}")
    else:
        print(f"Ei muutoksia (jo päivitetty): {main_path}")


if __name__ == "__main__":
    main()
