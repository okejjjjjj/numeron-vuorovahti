import os
import sys

OLD_WORK_CSS = '''            .month-item.work .itemName {
                display: none !important;
            }'''

NEW_WORK_AND_ABSENCE_CSS = '''            .month-item.work .itemName {
                display: none !important;
            }
            td.month-day.has-spanning-absence {
                overflow: visible !important;
            }
            td.month-day:not(.has-spanning-absence) {
                overflow: hidden !important;
            }
            .month-item.absence {
                display: none !important;
            }
            .month-item.absence.vuorovahti-visible {
                display: block !important;
                position: relative !important;
                z-index: 5 !important;
                box-sizing: border-box !important;
                border-radius: 5px !important;
                padding: 3px 6px !important;
                margin-bottom: 2px !important;
                font-size: 11px !important;
                font-weight: 600 !important;
                line-height: 1.25 !important;
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
                color: #FFFFFF !important;
            }
            .month-item.absence.vuorovahti-visible .itemName {
                display: inline !important;
                color: inherit !important;
                white-space: nowrap !important;
            }
            .month-item.absence.vuorovahti-visible .itemTimes {
                display: none !important;
            }
            .month-item.absence.vuorovahti-vacation {
                background-color: #15803D !important;
                border: 1px solid #22C55E !important;
                color: #FFFFFF !important;
            }
            .month-item.absence.vuorovahti-sick {
                background-color: #B91C1C !important;
                border: 1px solid #F87171 !important;
                color: #FFFFFF !important;
            }
            .month-item.absence.vuorovahti-other {
                background-color: #334155 !important;
                border: 1px solid #64748B !important;
                color: #F1F5F9 !important;
            }'''

OLD_JS_ANCHOR = '''                // === SUORA "LISÄÄ TOIVE TÄLLE PÄIVÄLLE" -OIKOPOLKU KALENTERIPÄIVÄSTÄ ==='''

NEW_JS_BLOCK = r'''                // === KALENTERIN POISSAOLOJEN SIISTINTÄ JA LOMAPALKKIEN YHDISTÄMINEN ===
                (function setupCalendarCleanup() {
                    var ignoreRegex = /^(vapaa|vapaapäivä|arkipyhä|arkipyhävapaa|viikkolepo|viikkovapaa|tasausvapaa|saldovapaa|pekkanen|pekkaspäivä|ei\s+(suunniteltuja\s+töitä|(työ)?vuoroa))\b/i;
                    var sickRegex = /sairaus|hoitovapaa/i;
                    var vacationRegex = /loma|säästövapaa|lomarahavapaa/i;

                    function classifyAbsence(title) {
                        var t = (title || '').replace(/\s+/g, ' ').trim();
                        if (!t || ignoreRegex.test(t)) return 'ignore';
                        if (sickRegex.test(t)) return 'sick';
                        if (vacationRegex.test(t)) return 'vacation';
                        return 'other';
                    }

                    function getAbsenceTitle(el) {
                        var nameEl = el.querySelector('.itemName');
                        var raw = nameEl ? (nameEl.textContent || '') : (el.textContent || '');
                        return raw.replace(/\s+/g, ' ').trim();
                    }

                    function parseDeclaredSpan(el) {
                        var styleAttr = el.getAttribute('style') || '';
                        var m = styleAttr.match(/width\s*:\s*(\d+(?:\.\d+)?)%/i);
                        if (!m) return 1;
                        var pct = parseFloat(m[1]);
                        if (isNaN(pct) || pct <= 120) return 1;
                        return Math.max(1, Math.round(pct / 100));
                    }

                    function cleanMonthTable() {
                        var rows = document.querySelectorAll('table.month-table tr');
                        if (!rows || rows.length === 0) return;

                        for (var r = 0; r < rows.length; r++) {
                            var cells = rows[r].querySelectorAll('td.month-day');
                            if (!cells || cells.length === 0) continue;

                            var hasUnprocessed = false;
                            for (var c0 = 0; c0 < cells.length; c0++) {
                                if (cells[c0].querySelector('.month-item.absence:not([data-vv-done])')) {
                                    hasUnprocessed = true;
                                    break;
                                }
                            }
                            if (!hasUnprocessed) continue;

                            var cellEntries = [];
                            for (var c = 0; c < cells.length; c++) {
                                cells[c].classList.remove('has-spanning-absence');
                                var items = cells[c].querySelectorAll('.month-item.absence');
                                var visibleList = [];
                                for (var i = 0; i < items.length; i++) {
                                    var el = items[i];
                                    el.setAttribute('data-vv-done', '1');
                                    var title = getAbsenceTitle(el);
                                    var kind = classifyAbsence(title);
                                    if (kind === 'ignore') {
                                        el.classList.remove('vuorovahti-visible', 'vuorovahti-vacation', 'vuorovahti-sick', 'vuorovahti-other');
                                        el.style.display = 'none';
                                    } else {
                                        visibleList.push({
                                            el: el,
                                            title: title,
                                            kind: kind,
                                            declaredSpan: parseDeclaredSpan(el),
                                            consumed: false
                                        });
                                    }
                                }
                                cellEntries.push(visibleList);
                            }

                            for (var col = 0; col < cells.length; col++) {
                                var list = cellEntries[col];
                                for (var idx = 0; idx < list.length; idx++) {
                                    var entry = list[idx];
                                    if (entry.consumed) continue;
                                    entry.consumed = true;

                                    var maxPossible = cells.length - col;
                                    var span = Math.min(maxPossible, entry.declaredSpan);

                                    var nextCol = col + 1;
                                    while (nextCol < cells.length) {
                                        var nextList = cellEntries[nextCol];
                                        var matchIdx = -1;
                                        for (var n = 0; n < nextList.length; n++) {
                                            if (!nextList[n].consumed && nextList[n].title.toLowerCase() === entry.title.toLowerCase()) {
                                                matchIdx = n;
                                                break;
                                            }
                                        }
                                        if (matchIdx !== -1) {
                                            nextList[matchIdx].consumed = true;
                                            nextList[matchIdx].el.classList.remove('vuorovahti-visible', 'vuorovahti-vacation', 'vuorovahti-sick', 'vuorovahti-other');
                                            nextList[matchIdx].el.style.display = 'none';
                                            if ((nextCol - col + 1) > span) {
                                                span = nextCol - col + 1;
                                            }
                                            nextCol++;
                                        } else {
                                            break;
                                        }
                                    }

                                    for (var k = col + 1; k < col + span; k++) {
                                        var kList = cellEntries[k];
                                        for (var m = 0; m < kList.length; m++) {
                                            if (!kList[m].consumed && kList[m].title.toLowerCase() === entry.title.toLowerCase()) {
                                                kList[m].consumed = true;
                                                kList[m].el.classList.remove('vuorovahti-visible', 'vuorovahti-vacation', 'vuorovahti-sick', 'vuorovahti-other');
                                                kList[m].el.style.display = 'none';
                                            }
                                        }
                                        var firstWork = cells[k].querySelector('.month-item.work');
                                        if (firstWork) {
                                            firstWork.style.marginTop = '23px';
                                        }
                                    }

                                    var targetEl = entry.el;
                                    targetEl.classList.add('vuorovahti-visible');
                                    targetEl.classList.remove('vuorovahti-vacation', 'vuorovahti-sick', 'vuorovahti-other');
                                    if (entry.kind === 'sick') {
                                        targetEl.classList.add('vuorovahti-sick');
                                    } else if (entry.kind === 'vacation') {
                                        targetEl.classList.add('vuorovahti-vacation');
                                    } else {
                                        targetEl.classList.add('vuorovahti-other');
                                    }
                                    targetEl.setAttribute('title', entry.title);

                                    if (span > 1) {
                                        cells[col].classList.add('has-spanning-absence');
                                        targetEl.style.width = 'calc(' + (span * 100) + '% + ' + ((span - 1) * 5) + 'px)';
                                    } else {
                                        targetEl.style.width = '100%';
                                    }
                                }
                            }
                        }
                    }

                    function cleanListView() {
                        var containers = document.querySelectorAll('.schedule-item-container.schedule-item-absence:not([data-vv-done])');
                        for (var i = 0; i < containers.length; i++) {
                            var box = containers[i];
                            box.setAttribute('data-vv-done', '1');
                            var heading = box.querySelector('.schedule-item-description-heading');
                            var title = heading ? (heading.textContent || '').replace(/\s+/g, ' ').trim() : '';
                            var kind = classifyAbsence(title);
                            if (kind === 'ignore') {
                                box.style.display = 'none';
                            } else if (kind === 'sick') {
                                box.style.setProperty('background-color', '#3F1D24', 'important');
                                box.style.setProperty('border-left-color', '#EF4444', 'important');
                            } else if (kind === 'vacation') {
                                box.style.setProperty('background-color', '#122B22', 'important');
                                box.style.setProperty('border-left-color', '#22C55E', 'important');
                            }
                        }
                    }

                    function runCalendarCleanup() {
                        cleanMonthTable();
                        cleanListView();
                    }

                    runCalendarCleanup();
                    if (!window._calendarCleanupObserver && document.body && typeof MutationObserver !== 'undefined') {
                        window._calendarCleanupObserver = true;
                        var calObs = new MutationObserver(function() {
                            runCalendarCleanup();
                        });
                        calObs.observe(document.body, { childList: true, subtree: true });
                    }
                })();

                // === SUORA "LISÄÄ TOIVE TÄLLE PÄIVÄLLE" -OIKOPOLKU KALENTERIPÄIVÄSTÄ ==='''


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

    if "setupCalendarCleanup" in src:
        print(f"Ei muutoksia (jo päivitetty): {main_path}")
        return

    if OLD_WORK_CSS not in src:
        print("VIRHE: .month-item.work CSS-lohkoa ei löytynyt odotetussa muodossa.")
        sys.exit(1)

    if OLD_JS_ANCHOR not in src:
        print("VIRHE: Kalenterin JS-ankkuria ei löytynyt odotetussa muodossa.")
        sys.exit(1)

    src = src.replace(OLD_WORK_CSS, NEW_WORK_AND_ABSENCE_CSS, 1)
    src = src.replace(OLD_JS_ANCHOR, NEW_JS_BLOCK, 1)

    with open(main_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)

    print(f"Päivitetty: {main_path}")


if __name__ == "__main__":
    main()
