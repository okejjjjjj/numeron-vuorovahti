import sys
from pathlib import Path

TARGET_FILE = Path("app/src/main/java/fi/oma/numeron/MainActivity.kt")

def main():
    if not TARGET_FILE.exists():
        print(f"Virhe: Tiedostoa '{TARGET_FILE}' ei löytynyt.")
        sys.exit(1)

    content = TARGET_FILE.read_text(encoding="utf-8")
    original_content = content

    # 1. Varmistetaan consecutiveEmptyPages-laskuri
    if "private var consecutiveEmptyPages = 0" not in content:
        target_vars = """    private var pagesRemainingToSync = 0
    private var totalFoundInBatch = 0"""
        replacement_vars = """    private var pagesRemainingToSync = 0
    private var consecutiveEmptyPages = 0
    private var totalFoundInBatch = 0"""
        if target_vars not in content:
            raise RuntimeError("Kohdetta 'pagesRemainingToSync' ei löytynyt.")
        content = content.replace(target_vars, replacement_vars, 1)

    if "consecutiveEmptyPages = 0" not in content:
        target_reset = """    private fun resetSyncBatch(pages: Int) {
        pagesRemainingToSync = pages"""
        replacement_reset = """    private fun resetSyncBatch(pages: Int) {
        pagesRemainingToSync = pages
        consecutiveEmptyPages = 0"""
        if target_reset not in content:
            raise RuntimeError("Kohdetta 'resetSyncBatch' ei löytynyt.")
        content = content.replace(target_reset, replacement_reset, 1)

    # 2. Päivitetään extractShiftsFromPage JS-suodatus: poistetaan toiveet (.request) ja vapaat (.opportunity)
    # myös luettelonäkymän riveiltä (tr, .list-item, .schedule-item jne.)
    js_filter_snippet = """                    (function() {
                        function isIgnoredText(str) {
                            if (!str) return false;
                            var low = str.toLowerCase();
                            return low.indexOf('toive') !== -1 ||
                                   low.indexOf('vapaa') !== -1 ||
                                   /\\bvp\\b/.test(low) ||
                                   low.indexOf('ei käytettävissä') !== -1;
                        }"""

    if "function isIgnoredText(str)" not in content:
        target_js_start = """                webView.evaluateJavascript(\"\"\"
                    (function() {"""
        if target_js_start not in content:
            raise RuntimeError("Kohdetta 'webView.evaluateJavascript' ei löytynyt.")
        content = content.replace(target_js_start, '                webView.evaluateJavascript("""\n' + js_filter_snippet, 1)

        # Suodatetaan luettelonäkymän rivit pageTextistä
        target_page_text = """var pageText = document.body.innerText || "";"""
        replacement_page_text = """var bodyClone = document.body.cloneNode(true);
                        var badEls = bodyClone.querySelectorAll('.request, .opportunity, .schedule-item-request, .schedule-item-opportunity, .month-item.request, .month-item.opportunity, [class*="request"], [class*="opportunity"], [class*="wish"]');
                        for (var b = 0; b < badEls.length; b++) badEls[b].remove();
                        var rows = bodyClone.querySelectorAll('tr, .list-row, .schedule-row, .day-row');
                        for (var r = 0; r < rows.length; r++) {
                            if (isIgnoredText(rows[r].innerText)) rows[r].remove();
                        }
                        var pageText = bodyClone.innerText || "";"""
        if target_page_text not in content:
            raise RuntimeError("Kohdetta 'var pageText' ei löytynyt.")
        content = content.replace(target_page_text, replacement_page_text, 1)

    # 3. Tiukennetaan Kotlin-puolen suodatusta: toiveet eivät koskaan päädy kalenteriin eivätkä nosta found-laskuria
    if "private fun isIgnoredEntry(text: String): Boolean" not in content:
        target_list_block = """    private fun processListBlock(calId: Long, d: Int, m: Int, y: Int, block: String, fmt: DateTimeFormatter, vacationDays: MutableList<LocalDate>): Pair<Int, Int> {"""
        replacement_list_block = """    private fun isIgnoredEntry(text: String): Boolean {
        val low = text.lowercase()
        return low.contains("toive") ||
            low.contains("vapaa") ||
            Regex(\"\"\"\\bvp\\b\"\"\").containsMatchIn(low) ||
            low.contains("ei käytettävissä") ||
            low.contains("vapaa vuoro")
    }

    private fun processListBlock(calId: Long, d: Int, m: Int, y: Int, block: String, fmt: DateTimeFormatter, vacationDays: MutableList<LocalDate>): Pair<Int, Int> {
        val cleanLines = block.lines().filter { !isIgnoredEntry(it) }
        val filteredBlock = cleanLines.joinToString("\\n").trim()
        if (filteredBlock.isEmpty()) return Pair(0, 0)
"""
        if target_list_block not in content:
            raise RuntimeError("Kohdetta 'processListBlock' ei löytynyt.")
        content = content.replace(target_list_block, replacement_list_block, 1)
        content = content.replace("block.lowercase()", "filteredBlock.lowercase()", 1)
        content = content.replace(".findAll(block).toList()", ".findAll(filteredBlock).toList()", 1)
        content = content.replace("else block.length", "else filteredBlock.length", 1)
        content = content.replace("block.substring(", "filteredBlock.substring(", 2)

    # Suodatetaan myös insertOrUpdateEvent-tasolla viimeisenä lukkona, ettei "Toive" voi koskaan tallentua
    target_insert_guard = """    private fun insertOrUpdateEvent(calId: Long, dateStr: String, startStr: String, endStr: String, details: String, fmt: DateTimeFormatter): Boolean {"""
    replacement_insert_guard = """    private fun insertOrUpdateEvent(calId: Long, dateStr: String, startStr: String, endStr: String, details: String, fmt: DateTimeFormatter): Boolean {
        if (isIgnoredEntry(details)) return false"""
    if "if (isIgnoredEntry(details)) return false" not in content:
        if target_insert_guard not in content:
            raise RuntimeError("Kohdetta 'insertOrUpdateEvent' ei löytynyt.")
        content = content.replace(target_insert_guard, replacement_insert_guard, 1)

    # 4. Varmistetaan keskeytys 3 tyhjän jakson jälkeen (ei työvuoroja eikä lomia)
    if "consecutiveEmptyPages >= 3" not in content:
        target_process_cb = """                val (found, added) = parseAndInsertCalendar(cellsJson, pageText, currentUrl, calId)
                totalFoundInBatch += found
                totalAddedInBatch += added

                if (pagesRemainingToSync > 0) {"""
        replacement_process_cb = """                val (found, added) = parseAndInsertCalendar(cellsJson, pageText, currentUrl, calId)
                totalFoundInBatch += found
                totalAddedInBatch += added

                if (found == 0) {
                    consecutiveEmptyPages++
                } else {
                    consecutiveEmptyPages = 0
                }

                if (consecutiveEmptyPages >= 3) {
                    pagesRemainingToSync = 0
                    finishCalendarSyncBatch(calId, "Haku keskeytetty (3 tyhjää jaksoa ilman työvuoroja tai lomaa). Tarkistettu $totalFoundInBatch merkintää:")
                } else if (pagesRemainingToSync > 0) {"""
        if target_process_cb not in content:
            raise RuntimeError("Kohdetta 'parseAndInsertCalendar' kutsua ei löytynyt.")
        content = content.replace(target_process_cb, replacement_process_cb, 1)

    # 5. Lisätään paluu kuukausinäkymään finishCalendarSyncBatch-metodiin
    switch_to_month_js = """        webView.post {
            webView.evaluateJavascript(
                \"\"\"
                (function() {
                    var btns = document.querySelectorAll('a, button, li, span, div[role="button"]');
                    for (var i = 0; i < btns.length; i++) {
                        var t = (btns[i].innerText || "").trim().toLowerCase();
                        if (t === 'kuukausi' || t === 'month' || t === 'kuukausinäkymä') {
                            btns[i].click();
                            return "clicked_month";
                        }
                    }
                    return "month_not_found";
                })();
                \"\"\".trimIndent(),
                null
            )
        }"""

    if "clicked_month" not in content:
        target_finish = """    private fun finishCalendarSyncBatch(calId: Long, prefixMsg: String) {"""
        replacement_finish = """    private fun finishCalendarSyncBatch(calId: Long, prefixMsg: String) {
$switch_to_month_js"""
        if target_finish not in content:
            raise RuntimeError("Kohdetta 'finishCalendarSyncBatch' ei löytynyt.")
        content = content.replace(target_finish, replacement_finish, 1)

    if content == original_content:
        print("Tiedosto on jo ajan tasalla, muutoksia ei tarvittu.")
        sys.exit(0)

    backup_file = TARGET_FILE.with_suffix(TARGET_FILE.suffix + ".bak")
    backup_file.write_text(original_content, encoding="utf-8")
    TARGET_FILE.write_text(content, encoding="utf-8")

    print(f"Päivitys onnistui! Varmuuskopio tallennettu tiedostoon '{backup_file}'.")

if __name__ == "__main__":
    main()
