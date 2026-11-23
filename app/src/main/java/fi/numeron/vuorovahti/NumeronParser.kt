package fi.numeron.vuorovahti

import org.jsoup.Jsoup
import java.net.HttpURLConnection
import java.net.URL
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.Callable
import java.util.concurrent.Executors
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
        "syyskuu" to 9, "lokakuu" to 10, "marraskuu" to 11, "joulukuu" to 12,
        "january" to 1, "february" to 2, "march" to 3, "april" to 4,
        "may" to 5, "june" to 6, "july" to 7, "august" to 8,
        "september" to 9, "october" to 10, "november" to 11, "december" to 12,
        "januari" to 1, "februari" to 2, "mars" to 3, "maj" to 5,
        "juni" to 6, "juli" to 7, "augusti" to 8, "oktober" to 10
    )

    private data class ParsedShiftText(
        val location: String,
        val shiftName: String,
        val role: String
    )

    private fun parseShiftText(rawName: String): ParsedShiftText {
        val cleaned = rawName.trim().replace(Regex("^\\d+\\s*"), "").trim()
        if (cleaned.isEmpty()) {
            return ParsedShiftText(location = "", shiftName = "", role = "")
        }
        val noWorkRegex = Regex(
            "^(ei\\s+suunniteltuja\\s+töitä|ei\\s+(työ)?vuoroa|vapaa|vapaapäivä|arkipyhävapaa|arkipyhä|viikkolepo|viikkovapaa|tasausvapaa|saldovapaa|pekkanen|pekkaspäivä|vuosiloma|sairaus|hoitovapaa|poissaolo)",
            RegexOption.IGNORE_CASE
        )
        if (noWorkRegex.containsMatchIn(cleaned)) {
            val formatted = cleaned.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
            return ParsedShiftText(location = formatted, shiftName = "", role = "")
        }
        val tokens = cleaned.split(Regex("\\s+")).filter { it.isNotBlank() }
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
        val match = Regex("width\\s*:\\s*(\\d+(?:\\.\\d+)?)%", RegexOption.IGNORE_CASE).find(styleAttr)
        val pct = match?.groupValues?.getOrNull(1)?.toDoubleOrNull() ?: return 1
        return (pct / 100.0).roundToInt().coerceAtLeast(1)
    }

    private fun isIgnoredDayOffOrSick(nameText: String): Boolean {
        val lower = nameText.trim().lowercase()
        return lower == "vapaa" ||
            lower.startsWith("vapaapäivä") ||
            lower.startsWith("arkipyhä") ||
            lower.startsWith("viikkolepo") ||
            lower.startsWith("viikkovapaa") ||
            lower.startsWith("tasausvapaa") ||
            lower.startsWith("saldovapaa") ||
            lower.startsWith("pekkanen") ||
            lower.startsWith("pekkaspäivä") ||
            lower.startsWith("ei suunniteltuja töitä") ||
            lower == "ei työvuoroa" ||
            lower == "ei vuoroa" ||
            lower.contains("sairaus")
    }

    private fun isTrainingAbsence(nameText: String): Boolean {
        return nameText.contains("koulutus", ignoreCase = true)
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
                        val targetDate = date.plusDays(offset.toLong())
                        if (targetDate.monthValue == currentMonth && targetDate.year == currentYear) {
                            trainingTitleByDate[targetDate] = nameText
                        }
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

        val yesterday = today.minusDays(1)
        val allowPrevMonthOverflow = today.dayOfMonth == 1 &&
            currentYear == today.year &&
            currentMonth == today.monthValue
        val prevMonthYm = java.time.YearMonth.of(currentYear, currentMonth).minusMonths(1)

        for (cell in dayCells) {
            val dayNum = cell.selectFirst(".dayNum")?.text()?.trim()?.toIntOrNull() ?: continue
            val date = if (cell.hasClass("day-different-month")) {
                if (!allowPrevMonthOverflow || dayNum < 20 || dayNum > prevMonthYm.lengthOfMonth()) continue
                val overflowDate = prevMonthYm.atDay(dayNum)
                if (overflowDate != yesterday) continue
                overflowDate
            } else {
                try {
                    LocalDate.of(currentYear, currentMonth, dayNum)
                } catch (_: Exception) {
                    continue
                }
            }

            // Sallitaan eilinen yövuorojen varalta, jotka päättyvät tänään nykyhetken jälkeen
            if (date.isBefore(yesterday)) continue

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

    fun extractCircleDates(html: String): Set<LocalDate> = extractCircleDatesFromDoc(Jsoup.parse(html))

    fun extractCircleDatesFromDoc(doc: org.jsoup.nodes.Document): Set<LocalDate> {
        val monthHeader = doc.selectFirst("#monthText")?.text()?.trim()?.lowercase() ?: return emptySet()
        val parts = monthHeader.split(Regex("\\s+"))
        if (parts.size < 2) return emptySet()

        val currentMonth = finnishMonths[parts[0]] ?: return emptySet()
        val currentYear = parts[1].toIntOrNull() ?: return emptySet()

        val result = mutableSetOf<LocalDate>()
        for (cell in doc.select("table.month-table td.month-day")) {
            if (cell.hasClass("day-different-month")) continue
            if (cell.selectFirst(".circle") == null) continue
            val dayNum = cell.selectFirst(".dayNum")?.text()?.trim()?.toIntOrNull() ?: continue
            try {
                result.add(LocalDate.of(currentYear, currentMonth, dayNum))
            } catch (_: Exception) {
            }
        }
        return result
    }

    fun parseListCommentsHtml(listHtml: String): Map<Pair<LocalDate, LocalTime?>, String> {
        val doc = Jsoup.parse(listHtml)
        val comments = mutableMapOf<Pair<LocalDate, LocalTime?>, String>()
        val timeFormatter = DateTimeFormatter.ofPattern("H:mm")

        for (dayContainer in doc.select("div.schedule-day-container[date]")) {
            val dateAttr = dayContainer.attr("date").trim()
            val dateParts = dateAttr.split("-")
            if (dateParts.size != 3) continue
            val month = dateParts[0].toIntOrNull() ?: continue
            val day = dateParts[1].toIntOrNull() ?: continue
            val year = dateParts[2].toIntOrNull() ?: continue
            val date = try {
                LocalDate.of(year, month, day)
            } catch (_: Exception) {
                continue
            }

            val workItems = dayContainer.select(".schedule-item-container.schedule-item-work")
            for (workItem in workItems) {
                val commentParts = workItem.select(".schedule-item-comment")
                    .map { it.text().replace(Regex("\\s+"), " ").trim() }
                    .filter { it.isNotEmpty() }
                if (commentParts.isEmpty()) continue

                val commentText = commentParts.joinToString("; ")
                val timesText = workItem.selectFirst(".schedule-item-times")?.text()?.trim() ?: ""
                val startToken = timesText.split("-").firstOrNull()?.trim() ?: ""
                val startTime = try {
                    if (startToken.isNotEmpty()) LocalTime.parse(startToken, timeFormatter) else null
                } catch (_: Exception) {
                    null
                }

                if (startTime != null) {
                    comments[date to startTime] = commentText
                }
                if (workItems.size == 1) {
                    comments[date to null] = commentText
                }
            }
        }
        return comments
    }

    private fun fetchHtmlWithCookies(targetUrl: String, cookieHeader: String?): String? {
        var conn: HttpURLConnection? = null
        return try {
            conn = (URL(targetUrl).openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 10_000
                readTimeout = 10_000
                instanceFollowRedirects = true
                if (!cookieHeader.isNullOrBlank()) {
                    setRequestProperty("Cookie", cookieHeader)
                }
                setRequestProperty(
                    "User-Agent",
                    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
                )
            }
            if (conn.responseCode in 200..299) {
                conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            } else {
                null
            }
        } catch (_: Exception) {
            null
        } finally {
            conn?.disconnect()
        }
    }

    fun enrichShiftsWithListComments(
        baseUrl: String,
        cookieHeader: String?,
        htmlPages: List<String>,
        shifts: List<WorkShift>
    ): List<WorkShift> {
        if (baseUrl.isBlank() || shifts.isEmpty()) return shifts

        val circleDates = htmlPages.flatMapTo(mutableSetOf()) { extractCircleDates(it) }
        if (circleDates.isEmpty()) return shifts

        val relevantDates = shifts
            .filter { !it.isAllDayLeave && it.start.toLocalDate() in circleDates }
            .mapTo(mutableSetOf()) { it.start.toLocalDate() }
        if (relevantDates.isEmpty()) return shifts

        val weekSampleDates = relevantDates
            .groupBy { it.with(DayOfWeek.MONDAY) }
            .values
            .map { it.first() }

        val commentsMap = mutableMapOf<Pair<LocalDate, LocalTime?>, String>()
        val cleanBase = baseUrl.trimEnd('/')
        if (weekSampleDates.size == 1) {
            val sampleDate = weekSampleDates.first()
            val listUrl = "$cleanBase/Calendar/List?date=${sampleDate.monthValue}%2F${sampleDate.dayOfMonth}%2F${sampleDate.year}%2000%3A00%3A00"
            val listHtml = fetchHtmlWithCookies(listUrl, cookieHeader)
            if (listHtml != null) {
                commentsMap.putAll(parseListCommentsHtml(listHtml))
            }
        } else {
            val pool = Executors.newFixedThreadPool(weekSampleDates.size.coerceAtMost(4))
            try {
                val tasks = weekSampleDates.map { sampleDate ->
                    Callable {
                        val listUrl = "$cleanBase/Calendar/List?date=${sampleDate.monthValue}%2F${sampleDate.dayOfMonth}%2F${sampleDate.year}%2000%3A00%3A00"
                        val listHtml = fetchHtmlWithCookies(listUrl, cookieHeader)
                        if (listHtml != null) parseListCommentsHtml(listHtml) else emptyMap()
                    }
                }
                for (future in pool.invokeAll(tasks)) {
                    try {
                        commentsMap.putAll(future.get())
                    } catch (_: Exception) {
                    }
                }
            } finally {
                pool.shutdown()
            }
        }

        if (commentsMap.isEmpty()) return shifts

        return shifts.map { shift ->
            if (shift.isAllDayLeave) {
                shift
            } else {
                val shiftDate = shift.start.toLocalDate()
                val shiftTime = shift.start.toLocalTime()
                val comment = commentsMap[shiftDate to shiftTime] ?: commentsMap[shiftDate to null]
                if (!comment.isNullOrBlank() && !shift.description.contains(comment, ignoreCase = true)) {
                    val newDesc = if (shift.description.isNotBlank()) {
                        "${shift.description}\n$comment"
                    } else {
                        comment
                    }
                    shift.copy(description = newDesc)
                } else {
                    shift
                }
            }
        }
    }

    fun mergeConsecutiveLeaves(rawShifts: List<WorkShift>): List<WorkShift> {
        val workShifts = rawShifts.filter { !it.isAllDayLeave }.toMutableList()
        val leaves = rawShifts.filter { it.isAllDayLeave }
            .sortedWith(compareBy<WorkShift> { it.title }.thenBy { it.start })

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
        return workShifts.sortedBy { it.start }
    }
}
