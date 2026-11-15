import sys
from pathlib import Path

TARGET_FILE = Path("app/src/main/java/fi/oma/numeron/MainActivity.kt")

def main():
    if not TARGET_FILE.exists():
        print(f"Virhe: Tiedostoa '{TARGET_FILE}' ei löytynyt.")
        sys.exit(1)

    content = TARGET_FILE.read_text(encoding="utf-8")
    original_content = content

    # 1. Suodatetaan toiveet ja vapaat vuorot pois bodyText-keräyksessä (extractShiftsFromPage)
    target_body_text = 'var bodyText = document.body ? document.body.innerText : "";'
    replacement_body_text = """function isIgnoredRowText(str) {
                    if (!str) return false;
                    var low = str.toLowerCase();
                    return low.indexOf('toive') !== -1 ||
                           low.indexOf('toivottu') !== -1 ||
                           low.indexOf('vapaa') !== -1 ||
                           /\\bvp\\b/.test(low) ||
                           low.indexOf('ei käytettävissä') !== -1;
                }
                var bodyText = "";
                if (document.body) {
                    var bodyClone = document.body.cloneNode(true);
                    var uiChrome = bodyClone.querySelectorAll('nav, #pc_AddButton, #mobile_AddButton, #pcViewDropdown, #mobileViewDropdown, .dropdown-menu');
                    for (var u = 0; u < uiChrome.length; u++) uiChrome[u].remove();
                    var badEls = bodyClone.querySelectorAll('.request, .opportunity, .schedule-item-request, .schedule-item-opportunity, .month-item.request, .month-item.opportunity, [class*="request" i], [class*="opportunity" i], [class*="wish" i]');
                    for (var b = 0; b < badEls.length; b++) badEls[b].remove();
                    var rows = bodyClone.querySelectorAll('tr, .list-item, .schedule-item, .calendar-list-item, .list-day-item');
                    for (var r = 0; r < rows.length; r++) {
                        if (isIgnoredRowText(rows[r].innerText)) rows[r].remove();
                    }
                    bodyText = bodyClone.innerText || "";
                }"""

    if "function isIgnoredRowText(str)" not in content:
        if target_body_text not in content:
            raise RuntimeError("Kohdetta 'var bodyText = document.body' ei löytynyt.")
        content = content.replace(target_body_text, replacement_body_text, 1)

    # 2. Tiukennetaan Kotlin-puolen isIgnoredEntry + lukitaan saveWorkShift
    target_ignored_fn = """    private fun isIgnoredEntry(text: String): Boolean {
        val low = text.lowercase()
        return low.contains("toive") ||
            low.contains("vapaa") ||
            Regex(\"\"\"\\bvp\\b\"\"\").containsMatchIn(low) ||
            low.contains("ei käytettävissä") ||
            low.contains("vapaa vuoro")
    }"""

    replacement_ignored_fn = """    private fun isIgnoredEntry(text: String): Boolean {
        val low = text.lowercase()
        return low.contains("toive") ||
            low.contains("toivottu") ||
            low.contains("vapaa") ||
            Regex(\"\"\"\\bvp\\b\"\"\").containsMatchIn(low) ||
            low.contains("ei käytettävissä") ||
            low.contains("vapaa vuoro")
    }"""

    if target_ignored_fn in content:
        content = content.replace(target_ignored_fn, replacement_ignored_fn, 1)

    target_save_shift = """    private fun saveWorkShift(calId: Long, dateStr: String, startStr: String, endStr: String, raw: String, fmt: DateTimeFormatter): Boolean {
        return try {"""
    replacement_save_shift = """    private fun saveWorkShift(calId: Long, dateStr: String, startStr: String, endStr: String, raw: String, fmt: DateTimeFormatter): Boolean {
        if (isIgnoredEntry(raw)) return false
        return try {"""

    if "if (isIgnoredEntry(raw)) return false" not in content:
        if target_save_shift not in content:
            raise RuntimeError("Kohdetta 'saveWorkShift' ei löytynyt.")
        content = content.replace(target_save_shift, replacement_save_shift, 1)

    # 3. Selkeytetään keskeytysilmoitus 3 viikon (jakson) jälkeen
    target_empty_msg = 'finishCalendarSyncBatch(calId, "Haku keskeytetty (3 tyhjää jaksoa). Tarkistettu $totalFoundInBatch merkintää:")'
    replacement_empty_msg = 'finishCalendarSyncBatch(calId, "Haku keskeytetty (3 viikkoa ilman työvuoroja tai lomaa). Tarkistettu $totalFoundInBatch merkintää:")'
    if target_empty_msg in content:
        content = content.replace(target_empty_msg, replacement_empty_msg, 1)

    # 4. Palataan automaattisesti kuukausinäkymään haun loputtua
    target_finish_batch = """    private fun finishCalendarSyncBatch(calId: Long, toastPrefix: String) {
        totalRemovedInBatch += reconcileRemovedShifts(calId)"""

    replacement_finish_batch = """    private fun switchBackToMonthView() {
        if (!::webView.isInitialized || isDemoActive) return
        webView.post {
            webView.evaluateJavascript(
                \"\"\"
                (function() {
                    var directMonth = document.querySelector('#go-to-month a, #go-to-month-mobile a, a[href*="/Calendar/Month" i]');
                    if (directMonth && directMonth.href && directMonth.href.indexOf('#') === -1) {
                        window.location.href = directMonth.href;
                        return "MONTH_NAVIGATED";
                    }
                    var selects = document.querySelectorAll('select');
                    for (var s = 0; s < selects.length; s++) {
                        for (var o = 0; o < selects[s].options.length; o++) {
                            var optTxt = (selects[s].options[o].text || "").toLowerCase();
                            if (optTxt.indexOf('kuukausi') !== -1 || optTxt.indexOf('month') !== -1) {
                                selects[s].selectedIndex = o;
                                selects[s].dispatchEvent(new Event('change', { bubbles: true }));
                                return "MONTH_SELECTED";
                            }
                        }
                    }
                    var btns = document.querySelectorAll('a, button, li, span');
                    for (var i = 0; i < btns.length; i++) {
                        var t = (btns[i].innerText || "").trim().toLowerCase();
                        if (t === 'kuukausi' || t === 'month' || t === 'kuukausinäkymä') {
                            btns[i].click();
                            return "MONTH_CLICKED";
                        }
                    }
                    window.location.href = '/Calendar/Month';
                    return "MONTH_FALLBACK";
                })();
                \"\"\".trimIndent(),
                null
            )
        }
    }

    private fun finishCalendarSyncBatch(calId: Long, toastPrefix: String) {
        totalRemovedInBatch += reconcileRemovedShifts(calId)
        switchBackToMonthView()"""

    if "private fun switchBackToMonthView()" not in content:
        if target_finish_batch not in content:
            raise RuntimeError("Kohdetta 'finishCalendarSyncBatch' ei löytynyt.")
        content = content.replace(target_finish_batch, replacement_finish_batch, 1)

    if content == original_content:
        print("Tiedosto on jo ajan tasalla, muutoksia ei tarvittu.")
        sys.exit(0)

    backup_file = TARGET_FILE.with_suffix(TARGET_FILE.suffix + ".bak")
    backup_file.write_text(original_content, encoding="utf-8")
    TARGET_FILE.write_text(content, encoding="utf-8")

    print(f"Päivitys onnistui! Varmuuskopio tallennettu tiedostoon '{backup_file}'.")

if __name__ == "__main__":
    main()
