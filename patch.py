import pathlib, re

ma_path = pathlib.Path("app/src/main/java/fi/oma/numeron/MainActivity.kt")
ma = ma_path.read_text(encoding="utf-8")

# 1. Kasvatetaan kelaus 3 sivusta 8 sivuun (nykyinen + 8 seuraavaa = 9 viikkoa)
ma = ma.replace("pagesRemainingToSync = 3", "pagesRemainingToSync = 8")
ma = ma.replace("pagesRemainingToSync = if (isDemoActive) 0 else 3", "pagesRemainingToSync = if (isDemoActive) 0 else 8")

# 2. Estetään kuukausiruudukkoa (processDayContent) lisäämästä reunasoluja poistolistalle
ma = re.sub(
    r'(private fun processDayContent\([^\n]+\n)\s*try \{ syncedDatesInBatch\.add\(LocalDate\.of\(y, m, d\)\) \} catch \(_: Exception\) \{\}\n',
    r'\1',
    ma
)

# 3. Päivitetään resolveMonthAndYear tunnistamaan viikkonumerot (esim. Vk 44 - Vk 53 ja vuodenvaihde)
old_resolve = "\n".join([
    '    private fun resolveMonthAndYear(pageText: String, currentUrl: String): Pair<Int, Int> {',
    '        val months = mapOf("tammikuu" to 1, "helmikuu" to 2, "maaliskuu" to 3, "huhtikuu" to 4, "toukokuu" to 5, "kesäkuu" to 6, "heinäkuu" to 7, "elokuu" to 8, "syyskuu" to 9, "lokakuu" to 10, "marraskuu" to 11, "joulukuu" to 12)',
    '        val mMatch = Regex("""(tammikuu|helmikuu|maaliskuu|huhtikuu|toukokuu|kesäkuu|heinäkuu|elokuu|syyskuu|lokakuu|marraskuu|joulukuu)\\s+(\\d{4})""", RegexOption.IGNORE_CASE).find(pageText)',
    '        if (mMatch != null) {',
    '            val m = months[mMatch.groupValues[1].lowercase()]',
    '            val y = mMatch.groupValues[2].toIntOrNull()',
    '            if (m != null && y != null) return Pair(m, y)',
    '        }',
    '        val wkYear = Regex("""Vk\\.?\\s*\\d{1,2}\\s*/\\s*(\\d{4})""", RegexOption.IGNORE_CASE).find(pageText)?.groupValues?.get(1)?.toIntOrNull()',
    '        val now = LocalDate.now()',
    '        val uri = try { Uri.parse(currentUrl) } catch (e: Exception) { null }',
    '        return Pair(uri?.getQueryParameter("month")?.toIntOrNull() ?: now.monthValue, uri?.getQueryParameter("year")?.toIntOrNull() ?: wkYear ?: now.year)',
    '    }'
])

new_resolve = "\n".join([
    '    private fun resolveMonthAndYear(pageText: String, currentUrl: String): Pair<Int, Int> {',
    '        val now = LocalDate.now()',
    '        val months = mapOf("tammikuu" to 1, "helmikuu" to 2, "maaliskuu" to 3, "huhtikuu" to 4, "toukokuu" to 5, "kesäkuu" to 6, "heinäkuu" to 7, "elokuu" to 8, "syyskuu" to 9, "lokakuu" to 10, "marraskuu" to 11, "joulukuu" to 12)',
    '        val mMatch = Regex("""(tammikuu|helmikuu|maaliskuu|huhtikuu|toukokuu|kesäkuu|heinäkuu|elokuu|syyskuu|lokakuu|marraskuu|joulukuu)\\s+(\\d{4})""", RegexOption.IGNORE_CASE).find(pageText)',
    '        if (mMatch != null) {',
    '            val m = months[mMatch.groupValues[1].lowercase()]',
    '            val y = mMatch.groupValues[2].toIntOrNull()',
    '            if (m != null && y != null) return Pair(m, y)',
    '        }',
    '        val wkSlashMatch = Regex("""(?:Vk|Viikko)\\.?\\s*(\\d{1,2})\\s*/\\s*(\\d{4})""", RegexOption.IGNORE_CASE).find(pageText)',
    '        if (wkSlashMatch != null) {',
    '            val wk = wkSlashMatch.groupValues[1].toIntOrNull() ?: 1',
    '            val yr = wkSlashMatch.groupValues[2].toIntOrNull() ?: now.year',
    '            val approxMonth = if (wk >= 48) 12 else if (wk <= 4) 1 else now.monthValue',
    '            return Pair(approxMonth, yr)',
    '        }',
    '        val wkOnlyMatch = Regex("""(?:Vk|Viikko)\\.?\\s*(\\d{1,2})\\b""", RegexOption.IGNORE_CASE).find(pageText)',
    '        if (wkOnlyMatch != null) {',
    '            val wk = wkOnlyMatch.groupValues[1].toIntOrNull() ?: 1',
    '            val inferredYear = if (now.monthValue >= 11 && wk <= 10) now.year + 1 else if (now.monthValue == 1 && wk >= 48) now.year - 1 else now.year',
    '            val approxMonth = if (wk >= 48) 12 else if (wk <= 4) 1 else now.monthValue',
    '            return Pair(approxMonth, inferredYear)',
    '        }',
    '        val uri = try { Uri.parse(currentUrl) } catch (e: Exception) { null }',
    '        return Pair(uri?.getQueryParameter("month")?.toIntOrNull() ?: now.monthValue, uri?.getQueryParameter("year")?.toIntOrNull() ?: now.year)',
    '    }'
])

if old_resolve in ma:
    ma = ma.replace(old_resolve, new_resolve)

# 4. Suojataan parseListView: lisätään sivun päivämäärät poistolistalle (syncedDatesInBatch)
#    VAIN jos sivulta oikeasti löytyi vähintään yksi työvuoro tai loma (found > 0).
#    Lisäksi päätellään vuosi oikein, kun selaillaan marraskuusta tammikuulle.
old_year_line = "val yr = rawYr ?: if (targetMonth == 12 && mo == 1) targetYear + 1 else if (targetMonth == 1 && mo == 12) targetYear - 1 else targetYear"
new_year_line = "val yr = rawYr ?: if (mo < LocalDate.now().monthValue - 1 && LocalDate.now().monthValue >= 10) LocalDate.now().year + 1 else if (targetMonth == 12 && mo == 1) targetYear + 1 else if (targetMonth == 1 && mo == 12) targetYear - 1 else targetYear"
ma = ma.replace(old_year_line, new_year_line)

# Otetaan processListBlockista suora syncedDatesInBatch.add pois ja tehdään se ehdollisesti parseListViewissä
ma = re.sub(
    r'(private fun processListBlock\([^\n]+\n)\s*try \{ syncedDatesInBatch\.add\(LocalDate\.of\(y, m, d\)\) \} catch \(_: Exception\) \{\}\n',
    r'\1',
    ma
)

old_parse_list_loop = "\n".join([
    '                val res = processListBlock(calId, d, mo, yr, pageText.substring(sIdx, eIdx).trim(), fmt, vacationDays)',
    '                found += res.first; added += res.second',
    '            }',
    '            added += saveGroupedVacations(calId, vacationDays)',
    '            if (found > 0) return Pair(found, added)'
])

new_parse_list_loop = "\n".join([
    '                val res = processListBlock(calId, d, mo, yr, pageText.substring(sIdx, eIdx).trim(), fmt, vacationDays)',
    '                found += res.first; added += res.second',
    '            }',
    '            if (found > 0) {',
    '                for (i in matches.indices) {',
    '                    val m = matches[i]',
    '                    val d = (m.groupValues[1].ifEmpty { m.groupValues[4] }).toIntOrNull() ?: continue',
    '                    val mo = (m.groupValues[2].ifEmpty { m.groupValues[5] }).toIntOrNull() ?: continue',
    '                    val rawYr = (m.groupValues[3].ifEmpty { m.groupValues[6] }).toIntOrNull()',
    '                    val yr = rawYr ?: if (mo < LocalDate.now().monthValue - 1 && LocalDate.now().monthValue >= 10) LocalDate.now().year + 1 else if (targetMonth == 12 && mo == 1) targetYear + 1 else if (targetMonth == 1 && mo == 12) targetYear - 1 else targetYear',
    '                    try { syncedDatesInBatch.add(LocalDate.of(yr, mo, d)) } catch (_: Exception) {}',
    '                }',
    '            }',
    '            added += saveGroupedVacations(calId, vacationDays)',
    '            if (found > 0) return Pair(found, added)'
])

if old_parse_list_loop in ma:
    ma = ma.replace(old_parse_list_loop, new_parse_list_loop)

# 5. Estetään taustasynkkaa (triggerSilentDailySyncIfNeeded) ajamasta reconcileRemovedShifts-poistoa
#    vajaalla datalla, ja varmistetaan että reconcileRemovedShifts vaatii vähintään 5 luettua päivää ja found > 0
ma = ma.replace(
    "reconcileRemovedShifts(calId)\n                                              VuorovahtiHelper.saveLastSyncStatus",
    "VuorovahtiHelper.saveLastSyncStatus"
)
ma = ma.replace(
    "reconcileRemovedShifts(calId)\n                                      VuorovahtiHelper.saveLastSyncStatus",
    "VuorovahtiHelper.saveLastSyncStatus"
)

ma = re.sub(
    r'private fun reconcileRemovedShifts\(calId: Long\): Int \{\s*(?:if \(syncedDatesInBatch\.isEmpty\(\)\) return 0)?\s*(?:if \(syncedDatesInBatch\.size < 5\) return 0)?',
    'private fun reconcileRemovedShifts(calId: Long): Int {\n        if (syncedDatesInBatch.size < 5 || totalFoundInBatch == 0) return 0',
    ma
)

# 6. Varmistetaan, että ilmoituksen klikkaus avaa aina yhteenvetoikkunan (sekä onResume että handleIncomingIntent)
if "private var pendingSummaryDialog = false" not in ma:
    ma = ma.replace(
        "private var pendingAutoStamp = false",
        "private var pendingSummaryDialog = false\n    private var pendingAutoStamp = false"
    )

# Päivitetään handleIncomingIntent asettamaan pendingSummaryDialog = true
ma = re.sub(
    r'if \(intent\?\.getBooleanExtra\("OPEN_SYNC_SUMMARY", false\) == true[^\{]*\{[^\}]*\}',
    'if (intent?.getBooleanExtra("OPEN_SYNC_SUMMARY", false) == true) {\n            intent.removeExtra("OPEN_SYNC_SUMMARY")\n            pendingSummaryDialog = true\n        }',
    ma
)

# Näytetään dialogi onResume-metodissa heti kun aktiviteetti on näkyvissä
if "if (pendingSummaryDialog)" not in ma:
    ma = ma.replace(
        "super.onResume()",
        "super.onResume()\n        if (pendingSummaryDialog) {\n            pendingSummaryDialog = false\n            webView.postDelayed({ showSyncSummaryDialog() }, 300)\n        }"
    )

ma_path.write_text(ma, encoding="utf-8")
print("MainActivity.kt paivitetty: 9 viikon kelaus, vuodenvaihteen viikkotuki, poistosuoja ja yhteenvetoikkuna!")
