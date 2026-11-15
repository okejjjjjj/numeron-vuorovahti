#!/usr/bin/env python3
import os
import re
import shutil
import sys
from pathlib import Path


# ==============================================================================
# 1. VERSIONUMERON NOSTO (pienin pykälin +1)
# ==============================================================================
def bump_gradle_version() -> None:
    candidates = [
        Path("app/build.gradle.kts"),
        Path("app/build.gradle"),
        Path("build.gradle.kts"),
        Path("build.gradle"),
    ]
    gradle_path = next((p for p in candidates if p.is_file()), None)
    if gradle_path is None:
        for root, _, files in os.walk("."):
            for fname in ("build.gradle.kts", "build.gradle"):
                if fname in files:
                    p = Path(root) / fname
                    if "versionCode" in p.read_text(encoding="utf-8", errors="ignore"):
                        gradle_path = p
                        break
            if gradle_path is not None:
                break

    if gradle_path is None:
        raise FileNotFoundError("build.gradle(.kts) -tiedostoa ei löytynyt.")

    text = gradle_path.read_text(encoding="utf-8")

    vc_match = re.search(r"(\bversionCode\s*=?\s*)(\d+)", text)
    if not vc_match:
        raise ValueError(f"versionCode-kenttää ei löytynyt tiedostosta {gradle_path}")

    old_code = int(vc_match.group(2))
    new_code = old_code + 1
    text = text[: vc_match.start(2)] + str(new_code) + text[vc_match.end(2) :]

    vn_match = re.search(r'(\bversionName\s*=?\s*")([^"]+)(")', text)
    if vn_match:
        old_name = vn_match.group(2)
        parts = old_name.split(".")
        if parts[-1].isdigit():
            parts[-1] = str(int(parts[-1]) + 1)
            new_name = ".".join(parts)
        else:
            new_name = f"{old_name}.1"
        text = text[: vn_match.start(2)] + new_name + text[vn_match.end(2) :]
        print(f"[VERSION] {gradle_path}: versionCode {old_code} -> {new_code}, versionName {old_name} -> {new_name}")
    else:
        print(f"[VERSION] {gradle_path}: versionCode {old_code} -> {new_code}")

    gradle_path.write_text(text, encoding="utf-8")


# ==============================================================================
# 2. MAINACTIVITY.KT MUOKKAUKSET
# ==============================================================================
def find_main_activity() -> Path:
    default_path = Path("app/src/main/java/fi/oma/numeron/MainActivity.kt")
    if default_path.is_file():
        return default_path
    for root, _, files in os.walk("."):
        if "MainActivity.kt" in files:
            return Path(root) / "MainActivity.kt"
    raise FileNotFoundError("MainActivity.kt -tiedostoa ei löytynyt.")


def apply_exact_patch(content: str, label: str, old: str, new: str) -> str:
    count = content.count(old)
    if count == 0:
        raise ValueError(f"[VIRHE] Kohtaa ei löytynyt: {label}")
    if count > 1:
        raise ValueError(f"[VIRHE] Kohta löytyi {count} kertaa (pitää olla uniikki): {label}")
    print(f"[OK] {label}")
    return content.replace(old, new, 1)


def patch_main_activity() -> None:
    ma_path = find_main_activity()
    original = ma_path.read_text(encoding="utf-8")
    updated = original

    # 1. Kendo DatePicker / TimePicker -kalenteripopupin tumma teema
    updated = apply_exact_patch(
        updated,
        "Kendo-kalenterivalikon tumma teema",
        """            .k-list .k-item, .k-column-menu .k-item, select option { background-color: #1E293B !important; color: #E2E8F0 !important; }
            .k-list .k-item:hover, .k-list .k-state-hover, .k-list .k-state-focused,
            .k-list .k-state-selected, .k-state-selected, .k-grid tr.k-state-selected td {
                background-color: #0284C7 !important;
                color: #FFFFFF !important;
            }""",
        """            .k-list .k-item, .k-column-menu .k-item, select option,
            .k-calendar .k-header, .k-calendar th, .k-calendar td, .k-calendar .k-link, .k-calendar .k-footer {
                background-color: #1E293B !important;
                color: #E2E8F0 !important;
                border-color: #334155 !important;
            }
            .k-list .k-item:hover, .k-list .k-state-hover, .k-list .k-state-focused,
            .k-list .k-state-selected, .k-state-selected, .k-grid tr.k-state-selected td,
            .k-calendar td.k-state-selected .k-link, .k-calendar td.k-state-hover .k-link {
                background-color: #0284C7 !important;
                color: #FFFFFF !important;
            }""",
    )

    # 2. Synkronointierän sivumäärä 3 jaksoon (3 viikkoa / jakso -> ~3 kk eteenpäin)
    updated = apply_exact_patch(
        updated,
        "ACTION_SYNC jaksojen määrä (3)",
        """        } else if (quickAction == "ACTION_SYNC") {
            intent.removeExtra("quick_action")
            isBackgroundListSync = true
            forceListOnNextCalendarLoad = true
            resetSyncBatch(8)
            showStampOverlay("Synkronoidaan työvuoroja", "Avataan kalenteria...")
            if (::webView.isInitialized) navigateWebView(urlCalendar)
        }""",
        """        } else if (quickAction == "ACTION_SYNC") {
            intent.removeExtra("quick_action")
            isBackgroundListSync = true
            forceListOnNextCalendarLoad = true
            resetSyncBatch(3)
            showStampOverlay("Synkronoidaan työvuoroja", "Avataan kalenteria...")
            if (::webView.isInitialized) navigateWebView(urlCalendar)
        }""",
    )

    updated = apply_exact_patch(
        updated,
        "AUTO_SYNC_NEW_LIST jaksojen määrä (3)",
        """        if (intent.getBooleanExtra("AUTO_SYNC_NEW_LIST", false)) {
            intent.removeExtra("AUTO_SYNC_NEW_LIST")
            isBackgroundListSync = true
            forceListOnNextCalendarLoad = true
            resetSyncBatch(8)
            showStampOverlay("Haetaan uutta työvuorolistaa", "Avataan kalenteria...")
            if (::webView.isInitialized) navigateWebView(urlCalendar)
        }""",
        """        if (intent.getBooleanExtra("AUTO_SYNC_NEW_LIST", false)) {
            intent.removeExtra("AUTO_SYNC_NEW_LIST")
            isBackgroundListSync = true
            forceListOnNextCalendarLoad = true
            resetSyncBatch(3)
            showStampOverlay("Haetaan uutta työvuorolistaa", "Avataan kalenteria...")
            if (::webView.isInitialized) navigateWebView(urlCalendar)
        }""",
    )

    # 3. Automaattileimauksen #punchButton ja data-next-stamp-direction tuki
    updated = apply_exact_patch(
        updated,
        "Automaattileimauksen #punchButton-tunnistus",
        """        val js = \"\"\"
            (function() {
                var passInputs = document.querySelectorAll('input[type="password"]');
                for (var p = 0; p < passInputs.length; p++) {
                    if (passInputs[p].offsetParent !== null) return "LOGIN_PAGE";
                }
                var btns = document.querySelectorAll('button, input[type="button"], input[type="submit"], a.btn');
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i].offsetParent === null) continue;
                    var txt = (btns[i].innerText || btns[i].value || "").trim().toLowerCase();
                    if (txt.indexOf('leimaa') !== -1 && txt.indexOf('$targetKeyword') !== -1) {
                        btns[i].click();
                        return "CLICKED:" + txt;
                    }
                }
                for (var j = 0; j < btns.length; j++) {
                    if (btns[j].offsetParent === null) continue;
                    var t = (btns[j].innerText || btns[j].value || "").trim().toLowerCase();
                    if (t.indexOf('leimaa') !== -1 && t.indexOf('$oppositeKeyword') !== -1) return "ALREADY_IN_TARGET_STATE";
                }
                return "WAITING";
            })();
        \"\"\".trimIndent()""",
        """        val expectedDir = if (pendingStampIsEnding) "OUT" else "IN"
        val js = \"\"\"
            (function() {
                var passInputs = document.querySelectorAll('input[type="password"]');
                for (var p = 0; p < passInputs.length; p++) {
                    if (passInputs[p].offsetParent !== null) return "LOGIN_PAGE";
                }
                var punchBtn = document.getElementById('punchButton');
                if (punchBtn && punchBtn.offsetParent !== null && !punchBtn.disabled) {
                    var pTxt = (punchBtn.innerText || punchBtn.value || "").trim().toLowerCase();
                    var dirEl = document.querySelector('[data-next-stamp-direction]');
                    var nextDir = dirEl ? (dirEl.getAttribute('data-next-stamp-direction') || "").toUpperCase() : "";
                    if (pTxt.indexOf('$targetKeyword') !== -1 || nextDir === '$expectedDir') {
                        punchBtn.click();
                        return "CLICKED:" + pTxt;
                    }
                    if (pTxt.indexOf('$oppositeKeyword') !== -1 || (nextDir !== '' && nextDir !== '$expectedDir')) {
                        return "ALREADY_IN_TARGET_STATE";
                    }
                }
                var btns = document.querySelectorAll('button, input[type="button"], input[type="submit"], a.btn');
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i].offsetParent === null || btns[i].disabled) continue;
                    var txt = (btns[i].innerText || btns[i].value || "").trim().toLowerCase();
                    if (txt.indexOf('leimaa') !== -1 && txt.indexOf('$targetKeyword') !== -1) {
                        btns[i].click();
                        return "CLICKED:" + txt;
                    }
                }
                for (var j = 0; j < btns.length; j++) {
                    if (btns[j].offsetParent === null) continue;
                    var t = (btns[j].innerText || btns[j].value || "").trim().toLowerCase();
                    if (t.indexOf('leimaa') !== -1 && t.indexOf('$oppositeKeyword') !== -1) return "ALREADY_IN_TARGET_STATE";
                }
                return "WAITING";
            })();
        \"\"\".trimIndent()""",
    )

    updated = apply_exact_patch(
        updated,
        "Leimauksen varmistus data-next-stamp-direction ja #punchButton avulla",
        """        val js = \"\"\"
            (function() {
                var btns = document.querySelectorAll('button, input[type="button"], input[type="submit"], a.btn');
                var targetStillVisible = false;
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i].offsetParent === null) continue;
                    var txt = (btns[i].innerText || btns[i].value || "").trim().toLowerCase();
                    if (txt.indexOf('leimaa') !== -1 && txt.indexOf('$oppositeKeyword') !== -1) return "VERIFIED_OPPOSITE";
                    if (txt.indexOf('leimaa') !== -1 && txt.indexOf('$targetKeyword') !== -1) targetStillVisible = true;
                }
                var bodyTxt = (document.body ? document.body.innerText : "").toLowerCase();
                if (bodyTxt.indexOf('onnistui') !== -1 || bodyTxt.indexOf('tallennettu') !== -1 || bodyTxt.indexOf('leimattu sisään') !== -1) return "VERIFIED_TEXT";
                if (!targetStillVisible && bodyTxt.indexOf('työaikaleimaus') !== -1) return "VERIFIED_GONE";
                return "PENDING";
            })();
        \"\"\".trimIndent()""",
        """        val flippedDir = if (pendingStampIsEnding) "IN" else "OUT"
        val js = \"\"\"
            (function() {
                var dirEl = document.querySelector('[data-next-stamp-direction]');
                if (dirEl && (dirEl.getAttribute('data-next-stamp-direction') || "").toUpperCase() === '$flippedDir') {
                    return "VERIFIED_DIR";
                }
                var punchBtn = document.getElementById('punchButton');
                if (punchBtn && punchBtn.offsetParent !== null) {
                    var pTxt = (punchBtn.innerText || "").trim().toLowerCase();
                    if (pTxt.indexOf('$oppositeKeyword') !== -1) return "VERIFIED_OPPOSITE";
                }
                var btns = document.querySelectorAll('button, input[type="button"], input[type="submit"], a.btn');
                var targetStillVisible = false;
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i].offsetParent === null) continue;
                    var txt = (btns[i].innerText || btns[i].value || "").trim().toLowerCase();
                    if (txt.indexOf('leimaa') !== -1 && txt.indexOf('$oppositeKeyword') !== -1) return "VERIFIED_OPPOSITE";
                    if (txt.indexOf('leimaa') !== -1 && txt.indexOf('$targetKeyword') !== -1) targetStillVisible = true;
                }
                if (document.querySelector('#bottomContainer .alert-success, .alert-success')) return "VERIFIED_ALERT";
                var bodyTxt = (document.body ? document.body.innerText : "").toLowerCase();
                if (bodyTxt.indexOf('onnistui') !== -1 || bodyTxt.indexOf('tallennettu') !== -1 || bodyTxt.indexOf('leimattu sisään') !== -1) return "VERIFIED_TEXT";
                if (!targetStillVisible && bodyTxt.indexOf('työaikaleimaus') !== -1) return "VERIFIED_GONE";
                return "PENDING";
            })();
        \"\"\".trimIndent()""",
    )

    # 4. Manuaalisen synkronoinnin jaksojen määrä (3)
    updated = apply_exact_patch(
        updated,
        "Manuaalisen synkronoinnin jaksojen määrä (3)",
        """        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 100)
        } else {
            resetSyncBatch(if (isDemoActive) 0 else 8)
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
                resetSyncBatch(if (isDemoActive) 0 else 8)
                extractShiftsFromPage(forceList = true)
            }
        }
    }""",
        """        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 100)
        } else {
            resetSyncBatch(if (isDemoActive) 0 else 3)
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
                resetSyncBatch(if (isDemoActive) 0 else 3)
                extractShiftsFromPage(forceList = true)
            }
        }
    }""",
    )

    # 5. Suora siirtyminen #go-to-list a -osoitteeseen kuukausinäkymästä
    updated = apply_exact_patch(
        updated,
        "Suora siirtyminen /Calendar/List-näkymään (#go-to-list a)",
        """        val js = \"\"\"
            (function() {
                var bodyText = document.body ? document.body.innerText : "";
                var isGrid = /Vk\.?\s+Ma\s+Ti\s+Ke/i.test(bodyText);
                if ($forceList && isGrid) {
                    var selects = document.querySelectorAll('select');
                    for (var s = 0; s < selects.length; s++) {
                        for (var o = 0; o < selects[s].options.length; o++) {
                            var optTxt = (selects[s].options[o].text || "").toLowerCase();
                            if (optTxt.indexOf('luettelo') !== -1 || optTxt.indexOf('lista') !== -1 || optTxt.indexOf('list') !== -1) {
                                selects[s].selectedIndex = o;
                                selects[s].dispatchEvent(new Event('change', { bubbles: true }));
                                return "SWITCHED_TO_LIST";
                            }
                        }
                    }
                    var links = document.querySelectorAll('a, li, button, span, div');
                    for (var i = 0; i < links.length; i++) {
                        var t = (links[i].innerText || "").trim().toLowerCase();
                        var href = (links[i].getAttribute && links[i].getAttribute('href')) || "";
                        if (t === 'luettelo' || t === 'lista' || href.toLowerCase().indexOf('/calendar/list') !== -1 || href.toLowerCase().indexOf('view=list') !== -1) {
                            links[i].click();
                            return "SWITCHED_TO_LIST";
                        }
                    }
                }""",
        """        val js = \"\"\"
            (function() {
                var bodyText = document.body ? document.body.innerText : "";
                var isGrid = document.querySelector('.month-table') !== null || /Vk\.?\s+Ma\s+Ti\s+Ke/i.test(bodyText);
                if ($forceList && isGrid) {
                    var listLink = document.querySelector('#go-to-list a, #go-to-list-mobile a, a[href*="/Calendar/List" i]');
                    if (listLink && listLink.getAttribute('href')) {
                        window.location.href = listLink.getAttribute('href');
                        return "SWITCHED_TO_LIST";
                    }
                    var selects = document.querySelectorAll('select');
                    for (var s = 0; s < selects.length; s++) {
                        for (var o = 0; o < selects[s].options.length; o++) {
                            var optTxt = (selects[s].options[o].text || "").toLowerCase();
                            if (optTxt.indexOf('luettelo') !== -1 || optTxt.indexOf('lista') !== -1 || optTxt.indexOf('list') !== -1) {
                                selects[s].selectedIndex = o;
                                selects[s].dispatchEvent(new Event('change', { bubbles: true }));
                                return "SWITCHED_TO_LIST";
                            }
                        }
                    }
                }""",
    )

    # 6. Visman .nextButton / .vismaicon-arrow-right-circle -painikkeen tuki
    updated = apply_exact_patch(
        updated,
        "Seuraava jakso -napin tunnistus (.nextButton / .vismaicon-arrow-right-circle)",
        """    private fun clickNextCalendarPeriod(calId: Long) {
        val js = \"\"\"
            (function() {
                var nextSelectors = ['a[title*="Seuraava" i]', 'button[title*="Seuraava" i]', '.fa-chevron-right', '.fa-angle-right', '.glyphicon-chevron-right', '.icon-chevron-right', '.fc-next-button'];
                for (var s = 0; s < nextSelectors.length; s++) {
                    var el = document.querySelector(nextSelectors[s]);
                    if (el) { (el.closest('a, button, div, span') || el).click(); return "NEXT_CLICKED"; }
                }
                var all = document.querySelectorAll('button, a, span');
                for (var i = 0; i < all.length; i++) {
                    var t = (all[i].innerText || "").trim().toLowerCase();
                    if (t === '>' || t === '›' || t === '»') { all[i].click(); return "NEXT_CLICKED"; }
                }
                return "NO_NEXT_BTN";
            })();
        \"\"\".trimIndent()""",
        """    private fun clickNextCalendarPeriod(calId: Long) {
        val js = \"\"\"
            (function() {
                var nextSelectors = [
                    'a.nextButton',
                    '.nextButton',
                    '.vismaicon-arrow-right-circle',
                    'a[title*="Seuraava" i]',
                    'button[title*="Seuraava" i]',
                    '.fa-chevron-right',
                    '.fa-angle-right',
                    '.glyphicon-chevron-right',
                    '.icon-chevron-right',
                    '.fc-next-button'
                ];
                for (var s = 0; s < nextSelectors.length; s++) {
                    var el = document.querySelector(nextSelectors[s]);
                    if (el) {
                        var target = el.closest('a, button, div, span') || el;
                        var href = target.getAttribute && target.getAttribute('href');
                        if (href && href !== '#' && href.indexOf('javascript:') !== 0) {
                            window.location.href = href;
                        } else {
                            target.click();
                        }
                        return "NEXT_CLICKED";
                    }
                }
                var all = document.querySelectorAll('button, a, span');
                for (var i = 0; i < all.length; i++) {
                    var t = (all[i].innerText || "").trim().toLowerCase();
                    if (t === '>' || t === '›' || t === '»') { all[i].click(); return "NEXT_CLICKED"; }
                }
                return "NO_NEXT_BTN";
            })();
        \"\"\".trimIndent()""",
    )

    # 7. Kuukausinäkymän päivien kirjaus syncedDatesInBatch-joukkoon poistettujen vuorojen siivousta varten
    updated = apply_exact_patch(
        updated,
        "Kuukausinäkymän päivien seuranta syncedDatesInBatch-joukossa",
        """                    if (isOther) continue
                    val res = processDayContent(calId, day, targetMonth, targetYear, txt, extra, fmt, vacationDays)
                    found += res.first
                    added += res.second""",
        """                    if (isOther) continue
                    try {
                        syncedDatesInBatch.add(LocalDate.of(targetYear, targetMonth, day))
                    } catch (_: Exception) {}
                    val res = processDayContent(calId, day, targetMonth, targetYear, txt, extra, fmt, vacationDays)
                    found += res.first
                    added += res.second""",
    )

    # 8. Vuoron nimen siivous (esim. "30Outokumpu Onni ilta hoitaja" -> sijainti + kuvaus) ja menneiden vuorojen/lomien ohitus
    updated = apply_exact_patch(
        updated,
        "Vuoron nimen etuliitteiden siivous ja menneiden vuorojen suodatus",
        """    private fun extractLocAndDesc(startStr: String, raw: String): Pair<String, String> {
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
    }

    private fun saveWorkShift(calId: Long, dateStr: String, startStr: String, endStr: String, raw: String, fmt: DateTimeFormatter): Boolean {
        return try {
            val sDt = LocalDateTime.parse("$dateStr $startStr", fmt)
            var eDt = LocalDateTime.parse("$dateStr $endStr", fmt)
            if (eDt.isBefore(sDt)) eDt = eDt.plusDays(1)
            val sMs = sDt.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            val eMs = eDt.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            if (eMs < System.currentTimeMillis()) return false""",
        """    private fun cleanShiftLabel(text: String): String {
        return text
            .replaceFirst(Regex(\"\"\"^\\d{1,3}\\s*(?=[A-ZÅÄÖa-zåäö])\"\"\"), "")
            .replace(Regex(\"\"\"\\s+\"\"\"), " ")
            .trim()
    }

    private fun extractLocAndDesc(startStr: String, raw: String): Pair<String, String> {
        val lines = raw.lines().map { cleanShiftLabel(it) }.filter {
            it.length > 2 && !it.equals("Uusi", true) && !it.equals("Lisää uusi", true) &&
                !it.equals("Valinnat", true) && !it.startsWith("Vk", true) &&
                !it.startsWith("Viikko", true) && !Regex(\"\"\"^\\d{1,2}$\"\"\").matches(it)
        }
        if (lines.size >= 2) {
            val codeLine = lines.firstOrNull { Regex(\"\"\"^\\d{3,5}\\b\"\"\").containsMatchIn(it) }
            val roleLine = lines.firstOrNull { it != codeLine }
            return Pair(codeLine ?: lines[0], roleLine ?: lines[1])
        } else if (lines.size == 1) {
            val full = lines[0]
            val roleMatch = Regex(
                \"\"\"^(.+?)\\s+((?:ilta\\s+välivuoro|aamu|ilta|yö|välivuoro)\\s+hoitaja.*)$\"\"\",
                RegexOption.IGNORE_CASE
            ).find(full)
            if (roleMatch != null) {
                val unit = roleMatch.groupValues[1].trim()
                return Pair(unit, full)
            }
            return Pair(full, full)
        }
        val h = startStr.substringBefore(":").toIntOrNull() ?: 7
        return Pair("", if (h < 11) "Aamuvuoro" else if (h < 18) "Iltavuoro" else "Yövuoro")
    }

    private fun saveWorkShift(calId: Long, dateStr: String, startStr: String, endStr: String, raw: String, fmt: DateTimeFormatter): Boolean {
        return try {
            val sDt = LocalDateTime.parse("$dateStr $startStr", fmt)
            var eDt = LocalDateTime.parse("$dateStr $endStr", fmt)
            if (eDt.isBefore(sDt)) eDt = eDt.plusDays(1)
            val sMs = sDt.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            val eMs = eDt.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            if (eMs <= System.currentTimeMillis()) return false""",
    )

    # 9. Menneiden lomajaksojen ohitus saveCleanVacationPeriod-funktiossa
    updated = apply_exact_patch(
        updated,
        "Menneiden lomajaksojen ohitus",
        """    private fun saveCleanVacationPeriod(calId: Long, startDate: LocalDate, endDate: LocalDate): Boolean {
        return try {
            var minStartMs = startDate.atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()""",
        """    private fun saveCleanVacationPeriod(calId: Long, startDate: LocalDate, endDate: LocalDate): Boolean {
        if (endDate.isBefore(LocalDate.now())) return false
        return try {
            var minStartMs = startDate.atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()""",
    )

    # 10. Taustasynkronoinnin (triggerSilentDailySyncIfNeeded) siirtyminen luettelonäkymään ja .nextButton-tuki
    updated = apply_exact_patch(
        updated,
        "Taustasynkronoinnin luettelonäkymä ja .nextButton-tuki",
        """                            if (silentPagesLeft > 0) {
                                silentPagesLeft--
                                bgWeb.evaluateJavascript(
                                    \"\"\"
                                    (function() {
                                        var el = document.querySelector('a[title*="Seuraava" i], button[title*="Seuraava" i], .fa-chevron-right, .fc-next-button');
                                        if (el) { (el.closest('a, button, div, span') || el).click(); return "NEXT"; }
                                        return "NONE";
                                    })();
                                    \"\"\".trimIndent()
                                ) { res ->
                                    if (res?.contains("NEXT") == true) {
                                        bgWeb.postDelayed({
                                            bgWeb.evaluateJavascript(
                                                \"\"\"
                                                var cells=[]; var tds=document.querySelectorAll("td"); for(var j=0;j<tds.length;j++){var td=tds[j]; var cls=(td.className||"").toLowerCase(); if(/week|vk|wk/.test(cls)) continue; cells.push({text:(td.innerText||"").trim(), isOther:/other|old|new|disabled|off|outside|gray|grey/.test(cls), extra:""});} AndroidSilentBridge.onSilentData(JSON.stringify(cells), document.body ? document.body.innerText : "", window.location.href);
                                                \"\"\".trimIndent(),
                                                null
                                            )
                                        }, 1500L)""",
        """                            if (silentPagesLeft > 0) {
                                silentPagesLeft--
                                bgWeb.evaluateJavascript(
                                    \"\"\"
                                    (function() {
                                        var el = document.querySelector('a.nextButton, .nextButton, .vismaicon-arrow-right-circle, a[title*="Seuraava" i], button[title*="Seuraava" i], .fa-chevron-right, .fc-next-button');
                                        if (el) {
                                            var target = el.closest('a, button, div, span') || el;
                                            var href = target.getAttribute && target.getAttribute('href');
                                            if (href && href !== '#' && href.indexOf('javascript:') !== 0) {
                                                window.location.href = href;
                                            } else {
                                                target.click();
                                            }
                                            return "NEXT";
                                        }
                                        return "NONE";
                                    })();
                                    \"\"\".trimIndent()
                                ) { res ->
                                    if (res?.contains("NEXT") == true) {
                                        bgWeb.postDelayed({
                                            bgWeb.evaluateJavascript(
                                                \"\"\"
                                                var cells=[]; var tds=document.querySelectorAll("td"); for(var j=0;j<tds.length;j++){var td=tds[j]; var cls=(td.className||"").toLowerCase(); if(/week|vk|wk/.test(cls)) continue; cells.push({text:(td.innerText||"").trim(), isOther:/other|old|new|disabled|off|outside|gray|grey/.test(cls), extra:""});} AndroidSilentBridge.onSilentData(JSON.stringify(cells), document.body ? document.body.innerText : "", window.location.href);
                                                \"\"\".trimIndent(),
                                                null
                                            )
                                        }, 1500L)""",
    )

    updated = apply_exact_patch(
        updated,
        "Taustasynkronoinnin automaattinen avaus luettelonäkymään",
        """                if (u.contains("/Calendar/", ignoreCase = true)) {
                    view?.postDelayed({
                        view.evaluateJavascript(
                            \"\"\"
                            (function() {
                                var cells = [];""",
        """                if (u.contains("/Calendar/", ignoreCase = true)) {
                    view?.postDelayed({
                        view.evaluateJavascript(
                            \"\"\"
                            (function() {
                                var isGrid = document.querySelector('.month-table') !== null;
                                if (isGrid) {
                                    var listLink = document.querySelector('#go-to-list a, #go-to-list-mobile a, a[href*="/Calendar/List" i]');
                                    if (listLink && listLink.getAttribute('href')) {
                                        window.location.href = listLink.getAttribute('href');
                                        return;
                                    }
                                }
                                var cells = [];""",
    )

    backup_path = ma_path.with_suffix(".kt.bak")
    shutil.copy2(ma_path, backup_path)
    ma_path.write_text(updated, encoding="utf-8")
    print
