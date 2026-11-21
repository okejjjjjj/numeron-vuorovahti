import os
import sys

OLD_PUNCH_CSS = r'''            #punchButton {
                background-color: #2E7D32 !important;
                border-color: #2E7D32 !important;
                color: #FFFFFF !important;
                border-radius: 10px !important;
                padding: 12px !important;
                margin-top: 16px !important;
                font-weight: 700 !important;
            }'''

NEW_PUNCH_CSS = r'''            #punchButton {
                background-color: #2E7D32 !important;
                border-color: #2E7D32 !important;
                color: #FFFFFF !important;
                border-radius: 10px !important;
                padding: 12px !important;
                margin-top: 16px !important;
                font-weight: 700 !important;
            }
            #punchButton.vv-punch-in {
                background-color: #15803D !important;
                border-color: #22C55E !important;
                color: #FFFFFF !important;
            }
            #punchButton.vv-punch-out {
                background-color: #B91C1C !important;
                border-color: #F87171 !important;
                color: #FFFFFF !important;
            }
            .vv-stamp-badge {
                display: inline-block !important;
                padding: 2px 10px !important;
                border-radius: 999px !important;
                font-size: 12px !important;
                font-weight: 700 !important;
                letter-spacing: 0.02em !important;
            }
            .vv-stamp-badge.vv-stamp-in {
                background-color: rgba(22, 163, 74, 0.22) !important;
                border: 1px solid rgba(74, 222, 128, 0.45) !important;
                color: #4ADE80 !important;
            }
            .vv-stamp-badge.vv-stamp-out {
                background-color: rgba(220, 38, 38, 0.22) !important;
                border: 1px solid rgba(248, 113, 113, 0.45) !important;
                color: #F87171 !important;
            }'''

OLD_ABSENCE_CSS = r'''            .month-item.absence {
                display: none !important;
            }'''

NEW_ABSENCE_CSS = r'''            .month-item.absence, .month-item.dummy-item {
                display: none !important;
            }'''

OLD_TODAY_JS = r'''                        // Vapaapäivät / poissaolot jätetään yhdelle riville
                        if (/^(ei\s+(työ)?vuoroa|vapaa|vapaapäivä|arkipyhävapaa|arkipyhä|vuosiloma|sairausloma|poissaolo)/i.test(cleaned)) {
                            return { location: capFirst(cleaned), shiftName: '', role: '' };
                        }'''

NEW_TODAY_JS = r'''                        // Vapaapäivät / poissaolot jätetään yhdelle riville
                        if (/^(ei\s+suunniteltuja\s+töitä|ei\s+(työ)?vuoroa|vapaa|vapaapäivä|arkipyhävapaa|arkipyhä|viikkolepo|viikkovapaa|tasausvapaa|saldovapaa|pekkanen|pekkaspäivä|vuosiloma|sairaus|hoitovapaa|poissaolo)(?=$|[\s,.:;!?()\-–—])/i.test(cleaned)) {
                            return { location: capFirst(cleaned), shiftName: '', role: '' };
                        }'''

OLD_TODAY_VER = r'''                        if (existingWp && nameEl.getAttribute('data-formatted-for') === 'v2:' + rawText) {
                            return;
                        }
                        nameEl.setAttribute('data-raw-shift', rawText);
                        nameEl.setAttribute('data-formatted-for', 'v2:' + rawText);'''

NEW_TODAY_VER = r'''                        if (existingWp && nameEl.getAttribute('data-formatted-for') === 'v3:' + rawText) {
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

OLD_IGNORE_REGEX = r'''                    var ignoreRegex = /^(vapaa|vapaapäivä|arkipyhä|arkipyhävapaa|viikkolepo|viikkovapaa|tasausvapaa|saldovapaa|pekkanen|pekkaspäivä|ei\s+(suunniteltuja\s+töitä|(työ)?vuoroa))\b/i;'''

NEW_IGNORE_REGEX = r'''                    var ignoreRegex = /^(vapaa|vapaapäivä|arkipyhä|arkipyhävapaa|viikkolepo|viikkovapaa|tasausvapaa|saldovapaa|pekkanen|pekkaspäivä|ei\s+(suunniteltuja\s+töitä|(työ)?vuoroa))(?=$|[\s,.:;!?()\-–—])/i;'''

OLD_CELL_LOOP = r'''                            var cellEntries = [];
                            for (var c = 0; c < cells.length; c++) {
                                cells[c].classList.remove('has-spanning-absence');'''

NEW_CELL_LOOP = r'''                            var cellEntries = [];
                            for (var c = 0; c < cells.length; c++) {
                                cells[c].classList.remove('has-spanning-absence');
                                var dummies = cells[c].querySelectorAll('.month-item.dummy-item');
                                for (var d = 0; d < dummies.length; d++) {
                                    dummies[d].style.display = 'none';
                                }'''

OLD_RECEIVER_PARSE = r'''                val parsed = pages.map { NumeronParser.parseCalendarHtml(it) }
                if (parsed.any { it == null }) {
                    null
                } else {
                    NumeronParser.mergeConsecutiveLeaves(parsed.filterNotNull().flatten())
                }'''

NEW_RECEIVER_PARSE = r'''                val parsed = pages.map { NumeronParser.parseCalendarHtml(it) }
                if (parsed.any { it == null }) {
                    null
                } else {
                    val cookies = try {
                        CookieManager.getInstance().getCookie(baseUrl)
                    } catch (_: Exception) {
                        null
                    }
                    val enriched = NumeronParser.enrichShiftsWithListComments(
                        baseUrl = baseUrl,
                        cookieHeader = cookies,
                        htmlPages = pages,
                        shifts = parsed.filterNotNull().flatten()
                    )
                    NumeronParser.mergeConsecutiveLeaves(enriched)
                }'''


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
    receiver_path = find_file("ShiftReminderReceiver.kt")

    if not main_path or not receiver_path:
        print("VIRHE: MainActivity.kt tai ShiftReminderReceiver.kt ei löytynyt.")
        sys.exit(1)

    with open(main_path, "r", encoding="utf-8") as f:
        main_src = f.read()

    replacements = [
        ("Leimauspainikkeen ja taulukon CSS", OLD_PUNCH_CSS, NEW_PUNCH_CSS),
        ("Kalenterin dummy-item-piilotus", OLD_ABSENCE_CSS, NEW_ABSENCE_CSS),
        ("Tänään-osion työttömän päivän regex", OLD_TODAY_JS, NEW_TODAY_JS),
        ("Leimausnäkymän värikoodaus-skripti", OLD_TODAY_VER, NEW_TODAY_VER),
        ("Vapaapäivien ääkkös-sanaraja", OLD_IGNORE_REGEX, NEW_IGNORE_REGEX),
        ("Kalenterisolujen dummy-item-siivous", OLD_CELL_LOOP, NEW_CELL_LOOP),
    ]

    main_changed = False
    for label, old, new in replacements:
        if new in main_src:
            continue
        if old not in main_src:
            print(f"VAROITUS: Kohtaa '{label}' ei löytynyt tiedostosta MainActivity.kt.")
            continue
        main_src = main_src.replace(old, new, 1)
        main_changed = True

    if main_changed:
        with open(main_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(main_src)
        print(f"Päivitetty: {main_path}")
    else:
        print(f"Ei muutoksia (jo päivitetty): {main_path}")

    with open(receiver_path, "r", encoding="utf-8") as f:
        rec_src = f.read()

    if "enrichShiftsWithListComments" not in rec_src:
        if OLD_RECEIVER_PARSE not in rec_src:
            print("VIRHE: ShiftReminderReceiver.kt parsintalohkoa ei löytynyt.")
            sys.exit(1)
        rec_src = rec_src.replace(OLD_RECEIVER_PARSE, NEW_RECEIVER_PARSE, 1)
        with open(receiver_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(rec_src)
        print(f"Päivitetty: {receiver_path}")
    else:
        print(f"Ei muutoksia (jo päivitetty): {receiver_path}")


if __name__ == "__main__":
    main()
