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
    val isAllDayLeave: Boolean = false
)

object NumeronParser {

    private val finnishMonths = mapOf(
        "tammikuu" to 1, "helmikuu" to 2, "maaliskuu" to 3, "huhtikuu" to 4,
        "toukokuu" to 5, "kesäkuu" to 6, "heinäkuu" to 7, "elokuu" to 8,
        "syyskuu" to 9, "lokakuu" to 10, "marraskuu" to 11, "joulukuu" to 12
    )

    fun parseCalendarHtml(html: String): List<WorkShift> {
        val doc = Jsoup.parse(html)
        val shifts = mutableListOf<WorkShift>()

        val monthHeader = doc.selectFirst("#monthText")?.text()?.trim()?.lowercase() ?: return emptyList()
        val parts = monthHeader.split(" ")
        if (parts.size < 2) return emptyList()

        val currentMonth = finnishMonths[parts[0]] ?: return emptyList()
        val currentYear = parts[1].toIntOrNull() ?: return emptyList()
        val today = LocalDate.now()

        val dayCells = doc.select("table.month-table td.month-day")
        for (cell in dayCells) {
            if (cell.hasClass("past-day") || cell.hasClass("day-different-month")) continue

            val dayNum = cell.selectFirst(".dayNum")?.text()?.trim()?.toIntOrNull() ?: continue
            val date = LocalDate.of(currentYear, currentMonth, dayNum)

            if (date.isBefore(today)) continue

            cell.select(".month-item.work").forEach { item ->
                val timesText = item.selectFirst(".itemTimes")?.text()?.trim() ?: ""
                val nameText = item.selectFirst(".itemName")?.text()?.trim() ?: "Työvuoro"

                val timeParts = timesText.split("-").map { it.trim() }
                if (timeParts.size == 2) {
                    val startTime = LocalTime.parse(timeParts[0], DateTimeFormatter.ofPattern("H:mm"))
                    val endTime = LocalTime.parse(timeParts[1], DateTimeFormatter.ofPattern("H:mm"))

                    var endDate = date
                    if (endTime.isBefore(startTime)) {
                        endDate = date.plusDays(1)
                    }

                    shifts.add(
                        WorkShift(
                            title = nameText,
                            start = LocalDateTime.of(date, startTime),
                            end = LocalDateTime.of(endDate, endTime),
                            isAllDayLeave = false
                        )
                    )
                }
            }

            cell.select(".month-item.absence").forEach { item ->
                val nameText = item.selectFirst(".itemName")?.text()?.trim() ?: "Loma / Poissaolo"
                shifts.add(
                    WorkShift(
                        title = nameText,
                        start = date.atStartOfDay(),
                        end = date.plusDays(1).atStartOfDay(),
                        isAllDayLeave = true
                    )
                )
            }
        }

        return mergeConsecutiveLeaves(shifts)
    }

    private fun mergeConsecutiveLeaves(rawShifts: List<WorkShift>): List<WorkShift> {
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
