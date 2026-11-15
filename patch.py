#!/usr/bin/env python3
"""
Päivittää MainActivity.kt-tiedoston Visma Numeronin kalenterisynkronoinnin:
1. Nostaa sivutuserän (resetSyncBatch) 8 -> 12 viikkoon (koko joulukuu + tammikuun alku).
2. Korjaa luettelonäkymään vaihdon (#go-to-list a / #go-to-list-mobile a).
3. Lisää Visma Numeronin .nextButton / .vismaicon-arrow-right-circle -nuolinapit.
4. Päivittää myös hiljaisen päiväsynkronoinnin (triggerSilentDailySyncIfNeeded) seuraava-napin.
"""

import shutil
import sys
from pathlib import Path


def find_main_activity(custom_path: str | None = None) -> Path:
    if custom_path:
        p = Path(custom_path)
        if p.is_file():
            return p
        raise FileNotFoundError(f"Tiedostoa ei löytynyt: {p}")

    candidates = [
        Path("MainActivity.kt"),
        Path("app/src/main/java/fi/oma/numeron/MainActivity.kt"),
    ]
    for c in candidates:
        if c.is_file():
            return c

    for found in Path(".").rglob("MainActivity.kt"):
        return found

    raise FileNotFoundError(
        "MainActivity.kt-tiedostoa ei löytynyt. Anna polku parametrina: python3 patch.py polku/MainActivity.kt"
    )


def replace_exact(content: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if old in content:
        return content.replace(old, new, 1), True
    if new in content:
        print(f"[OK - jo päivitetty] {label}")
        return content, False
    raise RuntimeError(f"[VIRHE] Odotettua koodilohkoa ei löytynyt: {label}")


def main() -> None:
    target = find_main_activity(sys.argv[1] if len(sys.argv) > 1 else None)
    backup = target.with_suffix(target.suffix + ".bak")
    shutil.copy2(target, backup)

    content = target.read_text(encoding="utf-8")
    changes = 0

    # 1. resetSyncBatch(8) -> resetSyncBatch(12)
    batch_replacements = [
        (
            '        } else if (quickAction == "ACTION_SYNC") {\n'
            '            intent.removeExtra("quick_action")\n'
            '            isBackgroundListSync = true\n'
            '            forceListOnNextCalendarLoad = true\n'
            '            resetSyncBatch(8)',
            '        } else if (quickAction == "ACTION_SYNC") {\n'
            '            intent.removeExtra("quick_action")\n'
            '            isBackgroundListSync = true\n'
            '            forceListOnNextCalendarLoad = true\n'
            '            resetSyncBatch(12)',
            "ACTION_SYNC batch 8 -> 12",
        ),
        (
            '        if (intent.getBooleanExtra("AUTO_SYNC_NEW_LIST", false)) {\n'
            '            intent.removeExtra("AUTO_SYNC_NEW_LIST")\n'
            '            isBackgroundListSync = true\n'
            '            forceListOnNextCalendarLoad = true\n'
            '            resetSyncBatch(8)',
            '        if (intent.getBooleanExtra("AUTO_SYNC_NEW_LIST", false)) {\n'
            '            intent.removeExtra("AUTO_SYNC_NEW_LIST")\n'
            '            isBackgroundListSync = true\n'
            '            forceListOnNextCalendarLoad = true\n'
            '            resetSyncBatch(12)',
            "AUTO_SYNC_NEW_LIST batch 8 -> 12",
        ),
        (
            '        } else {\n'
            '            resetSyncBatch(if (isDemoActive) 0 else 8)\n'
            '            extractShiftsFromPage(forceList = true)\n'
            '        }',
            '        } else {\n'
            '            resetSyncBatch(if (isDemoActive) 0 else 12)\n'
            '            extractShiftsFromPage(forceList = true)\n'
            '        }',
            "checkPermissionsAndSync batch 8 -> 12",
        ),
        (
            '            if (r && w) {\n'
            '                resetSyncBatch(if (isDemoActive) 0 else 8)\n'
            '                extractShiftsFromPage(forceList = true)\n'
            '            }',
            '            if (r && w) {\n'
            '                resetSyncBatch(if (isDemoActive) 0 else 12)\n'
            '                extractShiftsFromPage(forceList = true)\n'
            '            }',
            "onRequestPermissionsResult batch 8 -> 12",
        ),
    ]

    for old, new, label in batch_replacements:
        content, changed = replace_exact(content, old, new, label)
        if changed:
            print(f"[PÄIVITETTY] {label}")
            changes += 1

    # 2. Luettelonäkymään vaihto extractShiftsFromPage-funktiossa
    old_switch_list = (
        '                var bodyText = document.body ? document.body.innerText : "";\n'
        '                var isGrid = /Vk\\.?\\s+Ma\\s+Ti\\s+Ke/i.test(bodyText);\n'
        '                if ($forceList && isGrid) {\n'
        '                    var selects = document.querySelectorAll(\'select\');\n'
        '                    for (var s = 0; s < selects.length; s++) {\n'
        '                        for (var o = 0; o < selects[s].options.length; o++) {\n'
        '                            var optTxt = (selects[s].options[o].text || "").toLowerCase();\n'
        '                            if (optTxt.indexOf(\'luettelo\') !== -1 || optTxt.indexOf(\'lista\') !== -1 || optTxt.indexOf(\'list\') !== -1) {\n'
        '                                selects[s].selectedIndex = o;\n'
        '                                selects[s].dispatchEvent(new Event(\'change\', { bubbles: true }));\n'
        '                                return "SWITCHED_TO_LIST";\n'
        '                            }\n'
        '                        }\n'
        '                    }\n'
        '                    var links = document.querySelectorAll(\'a, li, button, span, div\');\n'
        '                    for (var i = 0; i < links.length; i++) {\n'
        '                        var t = (links[i].innerText || "").trim().toLowerCase();\n'
        '                        var href = (links[i].getAttribute && links[i].getAttribute(\'href\')) || "";\n'
        '                        if (t === \'luettelo\' || t === \'lista\' || href.toLowerCase().indexOf(\'/calendar/list\') !== -1 || href.toLowerCase().indexOf(\'view=list\') !== -1) {\n'
        '                            links[i].click();\n'
        '                            return "SWITCHED_TO_LIST";\n'
        '                        }\n'
        '                    }\n'
        '                }'
    )

    new_switch_list = (
        '                var bodyText = document.body ? document.body.innerText : "";\n'
        '                var pathLower = (window.location.pathname || "").toLowerCase();\n'
        '                var isListPage = pathLower.indexOf(\'/calendar/list\') !== -1 || pathLower.indexOf(\'demo_shifts\') !== -1;\n'
        '                var isGrid = /Vk\\.?\\s+Ma\\s+Ti\\s+Ke/i.test(bodyText) || document.querySelector(\'.month-table\') !== null;\n'
        '                if ($forceList && !isListPage && isGrid) {\n'
        '                    var directListLink = document.querySelector(\'#go-to-list a, #go-to-list-mobile a, a[href*="/Calendar/List" i]\');\n'
        '                    if (directListLink) {\n'
        '                        if (directListLink.href && directListLink.href.indexOf(\'#\') === -1) {\n'
        '                            window.location.href = directListLink.href;\n'
        '                        } else {\n'
        '                            directListLink.click();\n'
        '                        }\n'
        '                        return "SWITCHED_TO_LIST";\n'
        '                    }\n'
        '                    var selects = document.querySelectorAll(\'select\');\n'
        '                    for (var s = 0; s < selects.length; s++) {\n'
        '                        for (var o = 0; o < selects[s].options.length; o++) {\n'
        '                            var optTxt = (selects[s].options[o].text || "").toLowerCase();\n'
        '                            if (optTxt.indexOf(\'luettelo\') !== -1 || optTxt.indexOf(\'lista\') !== -1 || optTxt.indexOf(\'list\') !== -1) {\n'
        '                                selects[s].selectedIndex = o;\n'
        '                                selects[s].dispatchEvent(new Event(\'change\', { bubbles: true }));\n'
        '                                return "SWITCHED_TO_LIST";\n'
        '                            }\n'
        '                        }\n'
        '                    }\n'
        '                    var links = document.querySelectorAll(\'a, button\');\n'
        '                    for (var i = 0; i < links.length; i++) {\n'
        '                        var t = (links[i].innerText || "").trim().toLowerCase();\n'
        '                        var href = (links[i].getAttribute && links[i].getAttribute(\'href\')) || "";\n'
        '                        if (t === \'luettelo\' || t === \'lista\' || href.toLowerCase().indexOf(\'/calendar/list\') !== -1 || href.toLowerCase().indexOf(\'view=list\') !== -1) {\n'
        '                            if (links[i].href && links[i].href.indexOf(\'#\') === -1) {\n'
        '                                window.location.href = links[i].href;\n'
        '                            } else {\n'
        '                                links[i].click();\n'
        '                            }\n'
        '                            return "SWITCHED_TO_LIST";\n'
        '                        }\n'
        '                    }\n'
        '                }'
    )

    content, changed = replace_exact(
        content, old_switch_list, new_switch_list, "extractShiftsFromPage luettelonäkymään vaihto"
    )
    if changed:
        print("[PÄIVITETTY] extractShiftsFromPage luettelonäkymään vaihto")
        changes += 1

    # 3. Seuraava-painikkeen tunnistus clickNextCalendarPeriod-funktiossa
    old_next_period = (
        '    private fun clickNextCalendarPeriod(calId: Long) {\n'
        '        val js = """\n'
        '            (function() {\n'
        '                var nextSelectors = [\'a[title*="Seuraava" i]\', \'button[title*="Seuraava" i]\', \'.fa-chevron-right\', \'.fa-angle-right\', \'.glyphicon-chevron-right\', \'.icon-chevron-right\', \'.fc-next-button\'];\n'
        '                for (var s = 0; s < nextSelectors.length; s++) {\n'
        '                    var el = document.querySelector(nextSelectors[s]);\n'
        '                    if (el) { (el.closest(\'a, button, div, span\') || el).click(); return "NEXT_CLICKED"; }\n'
        '                }\n'
        '                var all = document.querySelectorAll(\'button, a, span\');\n'
        '                for (var i = 0; i < all.length; i++) {\n'
        '                    var t = (all[i].innerText || "").trim().toLowerCase();\n'
        '                    if (t === \'>\' || t === \'›\' || t === \'»\') { all[i].click(); return "NEXT_CLICKED"; }\n'
        '                }\n'
        '                return "NO_NEXT_BTN";\n'
        '            })();\n'
        '        """.trimIndent()'
    )

    new_next_period = (
        '    private fun clickNextCalendarPeriod(calId: Long) {\n'
        '        val js = """\n'
        '            (function() {\n'
        '                var nextSelectors = [\'a.nextButton\', \'.nextButton\', \'.vismaicon-arrow-right-circle\', \'a[title*="Seuraava" i]\', \'button[title*="Seuraava" i]\', \'.fa-chevron-right\', \'.fa-angle-right\', \'.glyphicon-chevron-right\', \'.icon-chevron-right\', \'.fc-next-button\'];\n'
        '                for (var s = 0; s < nextSelectors.length; s++) {\n'
        '                    var el = document.querySelector(nextSelectors[s]);\n'
        '                    if (el) {\n'
        '                        var clickable = el.closest(\'a, button\') || el;\n'
        '                        if (clickable.href && clickable.href.indexOf(\'#\') === -1 && !clickable.getAttribute(\'onclick\')) {\n'
        '                            window.location.href = clickable.href;\n'
        '                        } else {\n'
        '                            clickable.click();\n'
        '                        }\n'
        '                        return "NEXT_CLICKED";\n'
        '                    }\n'
        '                }\n'
        '                var all = document.querySelectorAll(\'button, a, span\');\n'
        '                for (var i = 0; i < all.length; i++) {\n'
        '                    var t = (all[i].innerText || "").trim().toLowerCase();\n'
        '                    if (t === \'>\' || t === \'›\' || t === \'»\') { all[i].click(); return "NEXT_CLICKED"; }\n'
        '                }\n'
        '                return "NO_NEXT_BTN";\n'
        '            })();\n'
        '        """.trimIndent()'
    )

    content, changed = replace_exact(
        content, old_next_period, new_next_period, "clickNextCalendarPeriod .nextButton-tunnistus"
    )
    if changed:
        print("[PÄIVITETTY] clickNextCalendarPeriod .nextButton-tunnistus")
        changes += 1

    # 4. Hiljaisen päiväsynkronoinnin seuraava-painike
    old_silent_next = (
        '                                    (function() {\n'
        '                                        var el = document.querySelector(\'a[title*="Seuraava" i], button[title*="Seuraava" i], .fa-chevron-right, .fc-next-button\');\n'
        '                                        if (el) { (el.closest(\'a, button, div, span\') || el).click(); return "NEXT"; }\n'
        '                                        return "NONE";\n'
        '                                    })();'
    )

    new_silent_next = (
        '                                    (function() {\n'
        '                                        var el = document.querySelector(\'a.nextButton, .nextButton, .vismaicon-arrow-right-circle, a[title*="Seuraava" i], button[title*="Seuraava" i], .fa-chevron-right, .fc-next-button\');\n'
        '                                        if (el) {\n'
        '                                            var clickable = el.closest(\'a, button\') || el;\n'
        '                                            if (clickable.href && clickable.href.indexOf(\'#\') === -1 && !clickable.getAttribute(\'onclick\')) {\n'
        '                                                window.location.href = clickable.href;\n'
        '                                            } else {\n'
        '                                                clickable.click();\n'
        '                                            }\n'
        '                                            return "NEXT";\n'
        '                                        }\n'
        '                                        return "NONE";\n'
        '                                    })();'
    )

    content, changed = replace_exact(
        content, old_silent_next, new_silent_next, "triggerSilentDailySyncIfNeeded .nextButton-tunnistus"
    )
    if changed:
        print("[PÄIVITETTY] triggerSilentDailySyncIfNeeded .nextButton-tunnistus")
        changes += 1

    if changes > 0:
        target.write_text(content, encoding="utf-8")
        print(f"\nValmis! Tehtiin {changes} päivitystä tiedostoon {target}.")
        print(f"Varmuuskopio tallennettu: {backup}")
    else:
        backup.unlink(missing_ok=True)
        print("\nTiedosto oli jo ajan tasalla, muutoksia ei tarvittu.")


if __name__ == "__main__":
    main()
