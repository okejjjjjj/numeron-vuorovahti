import os
import re
import sys

TARGET_FILE = "MainActivity.kt"

def main():
    if not os.path.exists(TARGET_FILE):
        print(f"Virhe: Tiedostoa '{TARGET_FILE}' ei löytynyt nykyisestä hakemistosta.")
        sys.exit(1)

    with open(TARGET_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    original_content = content

    # 1. Lisätään consecutiveEmptyPages-laskuri kenttiin ja resetSyncBatch-metodiin
    target_vars = """    private var pagesRemainingToSync = 0
    private var totalFoundInBatch = 0
    private var totalAddedInBatch = 0
    private var totalRemovedInBatch = 0"""

    replacement_vars = """    private var pagesRemainingToSync = 0
    private var consecutiveEmptyPages = 0
    private var totalFoundInBatch = 0
    private var totalAddedInBatch = 0
    private var totalRemovedInBatch = 0"""

    if target_vars not in content:
        raise RuntimeError("Kohdetta 'pagesRemainingToSync' ei löytynyt.")
    content = content.replace(target_vars, replacement_vars, 1)

    target_reset = """    private fun resetSyncBatch(pages: Int) {
        pagesRemainingToSync = pages
        totalFoundInBatch = 0
        totalAddedInBatch = 0
        totalRemovedInBatch = 0
        syncedDatesInBatch.clear()
        syncChangesList.clear()
        syncedShiftRangesInBatch.clear()
    }"""

    replacement_reset = """    private fun resetSyncBatch(pages: Int) {
        pagesRemainingToSync = pages
        consecutiveEmptyPages = 0
        totalFoundInBatch = 0
        totalAddedInBatch = 0
        totalRemovedInBatch = 0
        syncedDatesInBatch.clear()
        syncChangesList.clear()
        syncedShiftRangesInBatch.clear()
    }"""

    if target_reset not in content:
        raise RuntimeError("Kohdetta 'resetSyncBatch' ei löytynyt.")
    content = content.replace(target_reset, replacement_reset, 1)

    # 2. Näytetään peittoikkuna edistymispalkilla myös manuaalisessa synkronoinnissa (piilotetaan sivunvaihto)
    target_check_perm = """    private fun checkPermissionsAndSync() {
        val missing = getRequiredPermissions().filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 100)
        } else {
            resetSyncBatch(if (isDemoActive) 0 else 12)
            extractShiftsFromPage(forceList = true)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        VuorovahtiHelper.ensureRemindersFromCalendar(this)
        if (requestCode == 100) {
            val r = ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CALENDAR) == PackageManager.PERMISSION_GRANTED
            val w = ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_CALENDAR) == PackageManager.PERMISSION_GRANTED
            if (r && w) {
                resetSyncBatch(if (isDemoActive) 0 else 12)
                extractShiftsFromPage(forceList = true)
            }
        }
    }"""

    replacement_check_perm = """    private fun startManualForegroundSync() {
        isBackgroundListSync = true
        resetSyncBatch(if (isDemoActive) 0 else 12)
        showStampOverlay("Synkronoidaan kalenteria", "Haetaan työvuoroja ja lomia taustalla...")
        extractShiftsFromPage(forceList = true)
    }

    private fun checkPermissionsAndSync() {
        val missing = getRequiredPermissions().filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 100)
        } else {
            startManualForegroundSync()
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        VuorovahtiHelper.ensureRemindersFromCalendar(this)
        if (requestCode == 100) {
            val r = ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CALENDAR) == PackageManager.PERMISSION_GRANTED
            val w = ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_CALENDAR) == PackageManager.PERMISSION_GRANTED
            if (r && w) {
                startManualForegroundSync()
            }
        }
    }"""

    if target_check_perm not in content:
        raise RuntimeError("Kohdetta 'checkPermissionsAndSync' ei löytynyt.")
    content = content.replace(target_check_perm, replacement_check_perm, 1)

    # 3. Suodatetaan toiveet (.request) ja vapaat vuorot (.opportunity) pois HTML-solujen keräyksessä
    target_cells_js = """                        var extra = [];
                        var ch = td.querySelectorAll('[title], [data-original-title]');
                        for (var c = 0; c < ch.length; c++) {
                            var ti = ch[c].getAttribute('title') || ch[c].getAttribute('data-original-title');
                            if (ti) extra.push(ti);
                        }
                        cells.push({ text: (td.innerText || "").trim(), isOther: isOther, extra: extra.join(" | ") });"""

    replacement_cells_js = """                        var dayNumEl = td.querySelector('.dayNum');
                        var dayNum = dayNumEl ? (dayNumEl.innerText || "").trim() : "";
                        var validItems = td.querySelectorAll('.month-item.work, .month-item.absence, .schedule-item-work, .schedule-item-absence');
                        var cellText = "";
                        if (dayNum && (validItems.length > 0 || td.querySelector('.month-day-content'))) {
                            var lines = [dayNum];
                            for (var v = 0; v < validItems.length; v++) {
                                var it = validItems[v];
                                if (it.classList.contains('hidden-items-box')) continue;
                                var tStr = (it.innerText || "").trim().replace(/\\s+/g, ' ');
                                if (tStr) lines.push(tStr);
                            }
                            cellText = lines.join("\\n");
                        } else {
                            var clone = td.cloneNode(true);
                            var ignored = clone.querySelectorAll('.request, .opportunity, .schedule-item-request, .schedule-item-opportunity, .hidden-items-box');
                            for (var ig = 0; ig < ignored.length; ig++) ignored[ig].remove();
                            cellText = (clone.innerText || "").trim();
                        }
                        var extra = [];
                        var ch = td.querySelectorAll('.work [title], .absence [title], .work [data-original-title], .absence [data-original-title]');
                        for (var c = 0; c < ch.length; c++) {
                            var ti = ch[c].getAttribute('title') || ch[c].getAttribute('data-original-title');
                            if (ti) extra.push(ti);
                        }
                        cells.push({ text: cellText, isOther: isOther, extra: extra.join(" | ") });"""

    if target_cells_js not in content:
        raise RuntimeError("Kohdetta 'cells.push' JS-lohkosta ei löytynyt.")
    content = content.replace(target_cells_js, replacement_cells_js, 1)

    # 4. Päivitetään processCalendarData: keskeytys 3 tyhjän viikon/jakson jälkeen + edistymisteksti
    target_process_cb = """                val (found, added) = parseAndInsertCalendar(cellsJson, pageText, currentUrl, calId)
                totalFoundInBatch += found
                totalAddedInBatch += added

                if (pagesRemainingToSync > 0) {
                    pagesRemainingToSync--
                    if (isBackgroundListSync) {
                        showStampOverlay("Haetaan uutta työvuorolistaa", "Tarkistetaan tulevia viikkoja... (muutoksia $totalAddedInBatch)")
                    }
                    clickNextCalendarPeriod(calId)
                } else {
                    finishCalendarSyncBatch(calId, "Tarkistettu $totalFoundInBatch merkintää:")
                }"""

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
                    finishCalendarSyncBatch(calId, "Haku keskeytetty (3 tyhjää jaksoa). Tarkistettu $totalFoundInBatch merkintää:")
                } else if (pagesRemainingToSync > 0) {
                    pagesRemainingToSync--
                    if (isBackgroundListSync || stampOverlay.visibility == View.VISIBLE) {
                        val checkedCount = 12 - pagesRemainingToSync
                        showStampOverlay(
                            "Synkronoidaan kalenteria",
                            "Tarkistetaan jaksoa $checkedCount / 12...\\nLöydetty $totalFoundInBatch merkintää (muutoksia $totalAddedInBatch)"
                        )
                    }
                    clickNextCalendarPeriod(calId)
                } else {
                    finishCalendarSyncBatch(calId, "Tarkistettu $totalFoundInBatch merkintää:")
                }"""

    if target_process_cb not in content:
        raise RuntimeError("Kohdetta 'processCalendarData' ei löytynyt.")
    content = content.replace(target_process_cb, replacement_process_cb, 1)

    # 5. Suodatetaan luettelonäkymästä vapaapäivät ja toiveet pois
    target_list_block = """    private fun processListBlock(calId: Long, d: Int, m: Int, y: Int, block: String, fmt: DateTimeFormatter, vacationDays: MutableList<LocalDate>): Pair<Int, Int> {
        if (block.lowercase().let { it.contains("vuosiloma") || it.contains("loma") || Regex(\"\"\"\\bvl\\b\"\"\").containsMatchIn(it) }) {
            try {
                vacationDays.add(LocalDate.of(y, m, d))
            } catch (_: Exception) {}
            return Pair(1, 0)
        }"""

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

        if (filteredBlock.lowercase().let { it.contains("vuosiloma") || it.contains("loma") || Regex(\"\"\"\\bvl\\b\"\"\").containsMatchIn(it) }) {
            try {
                vacationDays.add(LocalDate.of(y, m, d))
            } catch (_: Exception) {}
            return Pair(1, 0)
        }"""

    if target_list_block not in content:
        raise RuntimeError("Kohdetta 'processListBlock' ei löytynyt.")
    content = content.replace(target_list_block, replacement_list_block, 1)

    # Korvataan block -> filteredBlock processListBlockin loppuosassa
    content = content.replace(
        """        val sMatches = Regex(\"\"\"(\\d{1,2}[:.]\\d{2})[\\s\\t]*[-–][\\s\\t]*(\\d{1,2}[:.]\\d{2})\"\"\").findAll(block).toList()
        if (sMatches.isNotEmpty()) {
            var added = 0
            for (idx in sMatches.indices) {
                val sMatch = sMatches[idx]
                val s = sMatch.groupValues[1].trim().replace('.', ':')
                val e = sMatch.groupValues[2].trim().replace('.', ':')
                val nextStart = if (idx + 1 < sMatches.size) sMatches[idx + 1].range.first else block.length
                val after = block.substring(sMatch.range.last + 1, nextStart).trim()
                val details = if (after.isNotEmpty()) after else block.substring(0, sMatch.range.first).trim()""",
        """        val sMatches = Regex(\"\"\"(\\d{1,2}[:.]\\d{2})[\\s\\t]*[-–][\\s\\t]*(\\d{1,2}[:.]\\d{2})\"\"\").findAll(filteredBlock).toList()
        if (sMatches.isNotEmpty()) {
            var added = 0
            for (idx in sMatches.indices) {
                val sMatch = sMatches[idx]
                val s = sMatch.groupValues[1].trim().replace('.', ':')
                val e = sMatch.groupValues[2].trim().replace('.', ':')
                val nextStart = if (idx + 1 < sMatches.size) sMatches[idx + 1].range.first else filteredBlock.length
                val after = filteredBlock.substring(sMatch.range.last + 1, nextStart).trim()
                val details = if (after.isNotEmpty()) after else filteredBlock.substring(0, sMatch.range.first).trim()""",
        1
    )

    # 6. Päivitetään extractLocAndDesc: poistetaan epäolennainen alkuosa ja laitetaan sijainti EVENT_LOCATIONiin
    target_loc_desc = """    private fun extractLocAndDesc(startStr: String, raw: String): Pair<String, String> {
        val lines = raw.lines().map { it.trim() }.filter {
            it.length > 2 && !it.equals("Uusi", true) && !it.equals("Lisää uusi", true) &&
                !it.equals("Valinnat", true) && !it.startsWith("Vk", true) &&
                !it.startsWith("Viikko", true) && !Regex(\"\"\"^\\d{1,2}$\"\"\").matches(it)
        }
        if (lines.size >= 2) {
            val codeLine = lines.firstOrNull { Regex(\"\"\"^\\d{3,5}\\b\"\"\").containsMatchIn(it) }
            val roleLine = lines.firstOrNull { it != codeLine }
            return Pair(codeLine ?: lines[0], roleLine ?: lines[1])
        } else if (lines.size == 1) {
            return Pair(lines[0], lines[0])
        }
        val h = startStr.substringBefore(":").toIntOrNull() ?: 7
        return Pair("", if (h < 11) "Aamuvuoro" else if (h < 18) "Iltavuoro" else "Yövuoro")
    }"""

    replacement_loc_desc = """    private fun extractLocAndDesc(startStr: String, raw: String): Pair<String, String> {
        val lines = raw.lines().map { it.trim() }.filter {
            it.length > 2 &&
                !it.equals("Uusi", true) &&
                !it.equals("Lisää uusi", true) &&
                !it.equals("Valinnat", true) &&
                !it.startsWith("Vk", true) &&
                !it.startsWith("Viikko", true) &&
                !Regex(\"\"\"^\\d{1,2}$\"\"\").matches(it) &&
                !isIgnoredEntry(it)
        }

        val h = startStr.substringBefore(":").toIntOrNull() ?: 7
        val fallbackDesc = if (h < 11) "Aamuvuoro" else if (h < 18) "Iltavuoro" else "Yövuoro"

        if (lines.isEmpty()) {
            return Pair("", fallbackDesc)
        }

        // Poistetaan rivin alusta epäolennaiset prosentti-/kustannusnumerot (esim. "90 ", "60 ", "30")
        val cleaned = lines[0]
            .replace(Regex(\"\"\"^\\d{1,4}\\s*(?=[A-ZÅÄÖ])\"\"\"), "")
            .replace(Regex(\"\"\"\\s+\"\"\"), " ")
            .trim()

        // Erotetaan työn suoritussijainti (esim. "Outokumpu Onni") ja vuoron kuvaus ("ilta hoitaja", "aamu hoitaja")
        val shiftSplitRegex = Regex(
            \"\"\"^(.*?)\\s+((?:aamu|ilta|yö|päivä|väli|pitkä|tupla|viikonloppu|ilta\\s+välivuoro|aamu\\s+välivuoro).*)$\"\"\",
            RegexOption.IGNORE_CASE
        )
        val match = shiftSplitRegex.find(cleaned)
        if (match != null) {
            val location = match.groupValues[1].trim().trim(',', '-', ':')
            val roleDesc = match.groupValues[2].trim().replaceFirstChar {
                if (it.isLowerCase()) it.titlecase(Locale.getDefault()) else it.toString()
            }
            return Pair(location, roleDesc.ifEmpty { fallbackDesc })
        }

        // Jos rivillä ei ole erillistä vuorokuvausta, tulkitaan teksti sijainniksi jos se alkaa isolla kirjaimella
        if (cleaned.isNotEmpty() && cleaned[0].isUpperCase()) {
            val secondLineDesc = lines.getOrNull(1)?.takeIf { it.isNotBlank() } ?: fallbackDesc
            return Pair(cleaned, secondLineDesc)
        }

        return Pair("", cleaned.ifEmpty { fallbackDesc })
    }"""

    if target_loc_desc not in content:
        raise RuntimeError("Kohdetta 'extractLocAndDesc' ei löytynyt.")
    content = content.replace(target_loc_desc, replacement_loc_desc, 1)

    # 7. Päivitetään updateEvent tyhjentämään vanha epäolennainen sijainti jos uusi sijainti on tyhjä
    target_update_ev = """        val textChanged = (loc.isNotEmpty() && (curLoc != loc || curDesc != desc))
        val colorMissing = (curColor != targetColor)

        if (!timeChanged && !textChanged && !colorMissing) return false

        val v = ContentValues().apply {
            put(CalendarContract.Events.TITLE, "Työvuoro")
            put(CalendarContract.Events.DTSTART, sMs)
            put(CalendarContract.Events.DTEND, eMs)
            if (loc.isNotEmpty()) put(CalendarContract.Events.EVENT_LOCATION, loc)
            if (desc.isNotEmpty()) put(CalendarContract.Events.DESCRIPTION, desc)
            applyColorWithFallback(this, calId, desc.ifEmpty { "Työvuoro" }, startHour)
        }"""

    replacement_update_ev = """        val textChanged = (curLoc != loc || (desc.isNotEmpty() && curDesc != desc))
        val colorMissing = (curColor != targetColor)

        if (!timeChanged && !textChanged && !colorMissing) return false

        val v = ContentValues().apply {
            put(CalendarContract.Events.TITLE, "Työvuoro")
            put(CalendarContract.Events.DTSTART, sMs)
            put(CalendarContract.Events.DTEND, eMs)
            put(CalendarContract.Events.EVENT_LOCATION, loc)
            if (desc.isNotEmpty()) put(CalendarContract.Events.DESCRIPTION, desc)
            applyColorWithFallback(this, calId, desc.ifEmpty { "Työvuoro" }, startHour)
        }"""

    if target_update_ev not in content:
        raise RuntimeError("Kohdetta 'updateEvent' ei löytynyt.")
    content = content.replace(target_update_ev, replacement_update_ev, 1)

    if content == original_content:
        print("Muutoksia ei tehty.")
        sys.exit(1)

    backup_file = TARGET_FILE + ".bak"
    with open(backup_file, "w", encoding="utf-8") as f:
        f.write(original_content)

    with open(TARGET_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Päivitys onnistui! Varmuuskopio tallennettu tiedostoon '{backup_file}'.")

if __name__ == "__main__":
    main()
