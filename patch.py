import os
import sys

PARSER_CONTENT = '''package fi.numeron.vuorovahti

import org.jsoup.Jsoup
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import kotlin.math.roundToInt

data class WorkShift(
    val title: String,
    val start: LocalDateTime,
    val end: LocalDateTime,
    val isAllDayLeave: Boolean = false,
    val location: String = "",
    val description: String = ""
)

object NumeronParser {

    private val finnishMonths = mapOf(
        "tammikuu" to 1, "helmikuu" to 2, "maaliskuu" to 3, "huhtikuu" to 4,
        "toukokuu" to 5, "kesäkuu" to 6, "heinäkuu" to 7, "elokuu" to 8,
        "syyskuu" to 9, "lokakuu" to 10, "marraskuu" to 11, "joulukuu" to 12
    )

    private data class ParsedShiftText(
        val location: String,
        val shiftName: String,
        val role: String
    )

    private fun parseShiftText(rawName: String): ParsedShiftText {
        val cleaned = rawName.trim().replace(Regex("^\\\\d+\\\\s*"), "").trim()
        if (cleaned.isEmpty()) {
            return ParsedShiftText(location = "", shiftName = "", role = "")
        }
        val noWorkRegex = Regex(
            "^(ei\\\\s+suunniteltuja\\\\s+töitä|ei\\\\s+(työ)?vuoroa|vapaa|vapaapäivä|arkipyhävapaa|arkipyhä|vuosiloma|sairausloma|poissaolo)",
            RegexOption.IGNORE_CASE
        )
        if (noWorkRegex.containsMatchIn(cleaned)) {
            val formatted = cleaned.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
            return ParsedShiftText(location = formatted, shiftName = "", role = "")
        }
        val tokens = cleaned.split(Regex("\\\\s+")).filter { it.isNotBlank() }
        if (tokens.isEmpty()) {
            return ParsedShiftText(location = "", shiftName = "", role = "")
        }

        val kShiftIdx = tokens.indexOfFirst { it.equals("k-vuoro", ignoreCase = true) }
        if (kShiftIdx != -1) {
            val location = tokens.filterIndexed { index, _ -> index != kShiftIdx }.joinToString(" ")
            return ParsedShiftText(location = location, shiftName = "", role = "K-vuoro")
        }

        val shiftKeywords = setOf(
            "aamu", "aamuvuoro",
            "ilta", "iltavuoro",
            "yö", "yövuoro",
            "päivä", "päivävuoro",
            "väli", "välivuoro"
        )

        val firstKwIdx = tokens.indexOfFirst { it.lowercase() in shiftKeywords }
        return if (firstKwIdx != -1) {
            val location = tokens.subList(0, firstKwIdx).joinToString(" ")
            val remainder = tokens.subList(firstKwIdx, tokens.size)
            val lastKwOffset = remainder.indexOfLast { it.lowercase() in shiftKeywords }
            val shiftName = remainder.subList(0, lastKwOffset + 1).joinToString(" ")
                .replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
            val role = remainder.subList(lastKwOffset + 1, remainder.size).joinToString(" ")
                .replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
            ParsedShiftText(location = location, shiftName = shiftName, role = role)
        } else if (tokens.size >= 2) {
            val role = tokens.last().replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
            val location = tokens.dropLast(1).joinToString(" ")
            ParsedShiftText(location = location, shiftName = "", role = role)
        } else {
            ParsedShiftText(location = cleaned, shiftName = "", role = "")
        }
    }

    private fun parseAbsenceSpanDays(styleAttr: String): Int {
        val match = Regex("width\\\\s*:\\\\s*(\\\\d+(?:\\\\.\\\\d+)?)%", RegexOption.IGNORE_CASE).find(styleAttr)
        val pct = match?.groupValues?.getOrNull(1)?.toDoubleOrNull() ?: return 1
        return (pct / 100.0).roundToInt().coerceAtLeast(1)
    }

    private fun isIgnoredDayOffOrSick(nameText: String): Boolean {
        val lower = nameText.trim().lowercase()
        return lower == "vapaa" ||
            lower.startsWith("vapaapäivä") ||
            lower.startsWith("arkipyhä") ||
            lower.startsWith("sairaus")
    }

    private fun isTrainingAbsence(nameText: String): Boolean {
        return nameText.contains("koulutus", ignoreCase = true)
    }

    fun parseCalendarHtml(html: String): List<WorkShift>? {
        val doc = Jsoup.parse(html)
        val shifts = mutableListOf<WorkShift>()

        val monthHeader = doc.selectFirst("#monthText")?.text()?.trim()?.lowercase() ?: return null
        val parts = monthHeader.split(Regex("\\\\s+"))
        if (parts.size < 2) return null

        val currentMonth = finnishMonths[parts[0]] ?: return null
        val currentYear = parts[1].toIntOrNull() ?: return null
        val now = LocalDateTime.now()
        val today = now.toLocalDate()

        val dayCells = doc.select("table.month-table td.month-day")
        if (dayCells.isEmpty()) return null

        val trainingTitleByDate = mutableMapOf<LocalDate, String>()
        val matchedTrainingDates = mutableSetOf<LocalDate>()

        for (cell in dayCells) {
            if (cell.hasClass("day-different-month")) continue

            val dayNum = cell.selectFirst(".dayNum")?.text()?.trim()?.toIntOrNull() ?: continue
            val date = LocalDate.of(currentYear, currentMonth, dayNum)

            cell.select(".month-item.absence").forEach { item ->
                val nameText = item.selectFirst(".itemName")?.text()?.trim() ?: return@forEach
                if (nameText.isEmpty() || isIgnoredDayOffOrSick(nameText)) return@forEach

                val spanDays = parseAbsenceSpanDays(item.attr("style"))

                if (isTrainingAbsence(nameText)) {
                    for (offset in 0 until spanDays) {
                        trainingTitleByDate[date.plusDays(offset.toLong())] = nameText
                    }
                } else {
                    val leaveStart = date.atStartOfDay()
                    val leaveEnd = date.plusDays(spanDays.toLong()).atStartOfDay()
                    if (!leaveEnd.isAfter(now)) return@forEach

                    shifts.add(
                        WorkShift(
                            title = nameText,
                            start = leaveStart,
                            end = leaveEnd,
                            isAllDayLeave = true,
                            location = "",
                            description = ""
                        )
                    )
                }
            }
        }

        for (cell in dayCells) {
            if (cell.hasClass("day-different-month")) continue

            val dayNum = cell.selectFirst(".dayNum")?.text()?.trim()?.toIntOrNull() ?: continue
            val date = LocalDate.of(currentYear, currentMonth, dayNum)

            // Sallitaan eilinen yövuorojen varalta, jotka päättyvät tänään nykyhetken jälkeen
            if (date.isBefore(today.minusDays(1))) continue

            val trainingTitle = trainingTitleByDate[date]

            cell.select(".month-item.work").forEach { item ->
                val timesText = item.selectFirst(".itemTimes")?.text()?.trim() ?: ""
                val rawNameText = item.selectFirst(".itemName")?.text()?.trim() ?: ""

                val timeParts = timesText.split("-").map { it.trim() }
                if (timeParts.size == 2) {
                    val startTime = try {
                        LocalTime.parse(timeParts[0], DateTimeFormatter.ofPattern("H:mm"))
                    } catch (_: Exception) {
                        return@forEach
                    }
                    val endTime = try {
                        LocalTime.parse(timeParts[1], DateTimeFormatter.ofPattern("H:mm"))
                    } catch (_: Exception) {
                        return@forEach
                    }

                    val startDateTime = LocalDateTime.of(date, startTime)
                    var endDate = date
                    if (endTime.isBefore(startTime)) {
                        endDate = date.plusDays(1)
                    }
                    val endDateTime = LocalDateTime.of(endDate, endTime)

                    if (trainingTitle != null) {
                        matchedTrainingDates.add(date)
                    }

                    // Huomioidaan tulevat sekä parhaillaan meneillään olevat työvuorot
                    if (!endDateTime.isAfter(now)) return@forEach

                    val parsed = parseShiftText(rawNameText)
                    val comment = listOf(parsed.shiftName, parsed.role)
                        .filter { it.isNotBlank() }
                        .joinToString(" • ")

                    shifts.add(
                        WorkShift(
                            title = trainingTitle ?: "Työvuoro",
                            start = startDateTime,
                            end = endDateTime,
                            isAllDayLeave = false,
                            location = parsed.location,
                            description = comment
                        )
                    )
                }
            }
        }

        for ((date, trainingTitle) in trainingTitleByDate) {
            if (date in matchedTrainingDates) continue
            val leaveStart = date.atStartOfDay()
            val leaveEnd = date.plusDays(1).atStartOfDay()
            if (!leaveEnd.isAfter(now)) continue

            shifts.add(
                WorkShift(
                    title = trainingTitle,
                    start = leaveStart,
                    end = leaveEnd,
                    isAllDayLeave = true,
                    location = "",
                    description = ""
                )
            )
        }

        return shifts
    }

    fun mergeConsecutiveLeaves(rawShifts: List<WorkShift>): List<WorkShift> {
        val workShifts = rawShifts.filter { !it.isAllDayLeave }.toMutableList()
        val leaves = rawShifts.filter { it.isAllDayLeave }.sortedBy { it.start }

        if (leaves.isEmpty()) return workShifts

        var currentLeave = leaves.first()
        for (i in 1 until leaves.size) {
            val next = leaves[i]
            if (next.title == currentLeave.title && !next.start.toLocalDate().isAfter(currentLeave.end.toLocalDate())) {
                val mergedEnd = if (next.end.isAfter(currentLeave.end)) next.end else currentLeave.end
                currentLeave = currentLeave.copy(end = mergedEnd)
            } else {
                workShifts.add(currentLeave)
                currentLeave = next
            }
        }
        workShifts.add(currentLeave)
        return workShifts
    }
}
'''

MAIN_OLD_BLOCK = '''                        // Vapaapäivät / poissaolot jätetään yhdelle riville
                        if (/^(ei\\s+(työ)?vuoroa|vapaa|vapaapäivä|vuosiloma|sairausloma|poissaolo)/i.test(cleaned)) {
                            return { location: capFirst(cleaned), shiftName: '', role: '' };
                        }

                        var tokens = cleaned.split(/\\s+/).filter(function(t) { return t.length > 0; });
                        if (tokens.length === 0) return { location: '', shiftName: '', role: '' };'''

MAIN_NEW_BLOCK = '''                        // Vapaapäivät / poissaolot jätetään yhdelle riville
                        if (/^(ei\\s+(työ)?vuoroa|vapaa|vapaapäivä|arkipyhävapaa|arkipyhä|vuosiloma|sairausloma|poissaolo)/i.test(cleaned)) {
                            return { location: capFirst(cleaned), shiftName: '', role: '' };
                        }

                        var tokens = cleaned.split(/\\s+/).filter(function(t) { return t.length > 0; });
                        if (tokens.length === 0) return { location: '', shiftName: '', role: '' };

                        var kShiftIdx = -1;
                        for (var k = 0; k < tokens.length; k++) {
                            if (tokens[k].toLowerCase() === 'k-vuoro') {
                                kShiftIdx = k;
                                break;
                            }
                        }
                        if (kShiftIdx !== -1) {
                            var kLoc = tokens.filter(function(_, idx) { return idx !== kShiftIdx; }).join(' ');
                            return { location: kLoc, shiftName: '', role: 'K-vuoro' };
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
    parser_path = find_file("NumeronParser.kt")
    if not parser_path:
        print("VIRHE: NumeronParser.kt ei löytynyt.")
        sys.exit(1)

    with open(parser_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(PARSER_CONTENT)
    print(f"Päivitetty: {parser_path}")

    main_path = find_file("MainActivity.kt")
    if not main_path:
        print("VIRHE: MainActivity.kt ei löytynyt.")
        sys.exit(1)

    with open(main_path, "r", encoding="utf-8") as f:
        main_src = f.read()

    if MAIN_NEW_BLOCK in main_src:
        print(f"Ei muutoksia (jo päivitetty): {main_path}")
    elif MAIN_OLD_BLOCK in main_src:
        main_src = main_src.replace(MAIN_OLD_BLOCK, MAIN_NEW_BLOCK, 1)
        with open(main_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(main_src)
        print(f"Päivitetty: {main_path}")
    else:
        print("VIRHE: MainActivity.kt:n parseShiftText-lohkoa ei löytynyt odotetussa muodossa.")
        sys.exit(1)


if __name__ == "__main__":
    main()
