package fi.numeron.vuorovahti

import org.jsoup.Jsoup
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.format.DateTimeFormatter

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
        val cleaned = rawName.trim().replace(Regex("^\\d+\\s*"), "").trim()
        val tokens = cleaned.split(Regex("\\s+")).filter { it.isNotBlank() }
        if (tokens.isEmpty()) {
            return ParsedShiftText(location = "", shiftName = "", role = "")
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

    fun parseCalendarHtml(html: String): List<WorkShift>? {
        val doc = Jsoup.parse(html)
        val shifts = mutableListOf<WorkShift>()

        val monthHeader = doc.selectFirst("#monthText")?.text()?.trim()?.lowercase() ?: return null
        val parts = monthHeader.split(Regex("\\s+"))
        if (parts.size < 2) return null

        val currentMonth = finnishMonths[parts[0]] ?: return null
        val currentYear = parts[1].toIntOrNull() ?: return null
        val now = LocalDateTime.now()
        val today = now.toLocalDate()

        val dayCells = doc.select("table.month-table td.month-day")
        if (dayCells.isEmpty()) return null
        for (cell in dayCells) {
            if (cell.hasClass("past-day") || cell.hasClass("day-different-month")) continue

            val dayNum = cell.selectFirst(".dayNum")?.text()?.trim()?.toIntOrNull() ?: continue
            val date = LocalDate.of(currentYear, currentMonth, dayNum)

            if (date.isBefore(today)) continue

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
                    // Ei huomioida menneitä tai meneillään olevia vuoroja
                    if (!startDateTime.isAfter(now)) return@forEach

                    var endDate = date
                    if (endTime.isBefore(startTime)) {
                        endDate = date.plusDays(1)
                    }

                    val parsed = parseShiftText(rawNameText)
                    val comment = listOf(parsed.shiftName, parsed.role)
                        .filter { it.isNotBlank() }
                        .joinToString(" • ")

                    shifts.add(
                        WorkShift(
                            title = "Työvuoro",
                            start = startDateTime,
                            end = LocalDateTime.of(endDate, endTime),
                            isAllDayLeave = false,
                            location = parsed.location,
                            description = comment
                        )
                    )
                }
            }

            cell.select(".month-item.absence").forEach { item ->
                val nameText = item.selectFirst(".itemName")?.text()?.trim() ?: "Loma / Poissaolo"
                val leaveStart = date.atStartOfDay()
                if (!leaveStart.isAfter(now)) return@forEach

                shifts.add(
                    WorkShift(
                        title = nameText,
                        start = leaveStart,
                        end = date.plusDays(1).atStartOfDay(),
                        isAllDayLeave = true,
                        location = "",
                        description = ""
                    )
                )
            }
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
            if (next.title == currentLeave.title && next.start.toLocalDate() == currentLeave.end.toLocalDate()) {
                currentLeave = currentLeave.copy(end = next.end)
            } else {
                workShifts.add(currentLeave)
                currentLeave = next
            }
        }
        workShifts.add(currentLeave)
        return workShifts
    }
}
