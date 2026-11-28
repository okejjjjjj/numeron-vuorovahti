package fi.numeron.vuorovahti

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import kotlin.math.abs

data class PlannedDayBaseline(
    val minutes: Int,
    val startText: String,
    val endText: String
)

data class PeriodBaseline(
    val periodStart: LocalDate,
    val periodEnd: LocalDate,
    val plannedDays: Map<LocalDate, PlannedDayBaseline>,
    val capturedMonths: Set<String>,
    val manualOverride: Boolean = false,
    val updatedAtMs: Long = System.currentTimeMillis()
) {
    fun requiredMonths(): Set<String> {
        val m1 = YearMonth.from(periodStart).toString()
        val m2 = YearMonth.from(periodEnd).toString()
        return if (m1 == m2) setOf(m1) else setOf(m1, m2)
    }

    fun isComplete(): Boolean {
        return requiredMonths().all { it in capturedMonths } &&
            plannedDays.values.any { it.minutes > 0 }
    }

    fun totalPlannedMinutes(): Int = plannedDays.values.sumOf { it.minutes }
}

data class DayBalanceInfo(
    val date: LocalDate,
    val plannedMinutes: Int,
    val plannedStartText: String,
    val plannedEndText: String,
    val actualMinutes: Int,
    val effectiveMinutes: Int,
    val diffMinutes: Int,
    val isCreditedSick: Boolean,
    val isCreditedOtherAbsence: Boolean
)

data class PeriodBalanceResult(
    val periodStart: LocalDate,
    val periodEnd: LocalDate,
    val baseline: PeriodBaseline,
    val plannedMinutes: Int,
    val effectiveMinutes: Int,
    val diffMinutes: Int,
    val creditedSickDays: Int,
    val creditedSickMinutes: Int,
    val dayDetails: Map<LocalDate, DayBalanceInfo>
)

object PeriodBalanceManager {

    const val PREF_ENABLED = "period_balance_tracking_enabled"
    private const val FILE_NAME = "vv_period_baselines.json"
    private const val PERIOD_DAYS = 21L

    private val lock = Any()
    private var loaded: Boolean = false
    private val baselines = LinkedHashMap<LocalDate, PeriodBaseline>()

    @Volatile
    var version: Long = 0L
        private set

    fun isEnabled(context: Context): Boolean {
        return context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .getBoolean(PREF_ENABLED, true)
    }

    fun resolveAnchorMonday(context: Context): LocalDate {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val raw = prefs.getString("shift_period_anchor_iso", "2026-12-28").orEmpty().trim()
        val parsed = try {
            LocalDate.parse(raw)
        } catch (_: Exception) {
            LocalDate.of(2026, 12, 28)
        }
        return parsed.with(DayOfWeek.MONDAY)
    }

    fun getPeriodBoundsForDate(context: Context, date: LocalDate): Pair<LocalDate, LocalDate> {
        val anchor = resolveAnchorMonday(context)
        val monday = date.with(DayOfWeek.MONDAY)
        val daysFromAnchor = ChronoUnit.DAYS.between(anchor, monday)
        val periodIdx = Math.floorDiv(daysFromAnchor, PERIOD_DAYS)
        val start = anchor.plusDays(periodIdx * PERIOD_DAYS)
        val end = start.plusDays(PERIOD_DAYS - 1L)
        return start to end
    }

    private fun storageFile(context: Context): File = File(context.applicationContext.filesDir, FILE_NAME)

    private fun ensureLoadedLocked(context: Context) {
        if (loaded) return
        loaded = true
        try {
            val file = storageFile(context)
            if (!file.exists()) return
            val root = JSONObject(file.readText(Charsets.UTF_8))
            val arr = root.optJSONArray("periods") ?: return
            baselines.clear()
            for (i in 0 until arr.length()) {
                val obj = arr.optJSONObject(i) ?: continue
                val start = try {
                    LocalDate.parse(obj.optString("periodStart", ""))
                } catch (_: Exception) {
                    continue
                }
                val end = try {
                    LocalDate.parse(obj.optString("periodEnd", ""))
                } catch (_: Exception) {
                    start.plusDays(PERIOD_DAYS - 1L)
                }
                val months = mutableSetOf<String>()
                val mArr = obj.optJSONArray("capturedMonths")
                if (mArr != null) {
                    for (j in 0 until mArr.length()) {
                        val m = mArr.optString(j, "").trim()
                        if (m.isNotEmpty()) months.add(m)
                    }
                }
                val daysMap = LinkedHashMap<LocalDate, PlannedDayBaseline>()
                val dArr = obj.optJSONArray("plannedDays")
                if (dArr != null) {
                    for (j in 0 until dArr.length()) {
                        val dObj = dArr.optJSONObject(j) ?: continue
                        val dDate = try {
                            LocalDate.parse(dObj.optString("date", ""))
                        } catch (_: Exception) {
                            continue
                        }
                        val mins = dObj.optInt("minutes", 0)
                        if (mins > 0) {
                            daysMap[dDate] = PlannedDayBaseline(
                                minutes = mins,
                                startText = dObj.optString("startText", ""),
                                endText = dObj.optString("endText", "")
                            )
                        }
                    }
                }
                baselines[start] = PeriodBaseline(
                    periodStart = start,
                    periodEnd = end,
                    plannedDays = daysMap,
                    capturedMonths = months,
                    manualOverride = obj.optBoolean("manualOverride", false),
                    updatedAtMs = obj.optLong("updatedAtMs", 0L)
                )
            }
        } catch (_: Exception) {
        }
    }

    private fun persistLocked(context: Context) {
        try {
            // Siivotaan yli 180 pv sitten päättyneet vanhat pohjasuunnitelmat
            val cutoff = LocalDate.now().minusDays(180)
            val staleKeys = baselines.values.filter { it.periodEnd.isBefore(cutoff) }.map { it.periodStart }
            for (k in staleKeys) baselines.remove(k)

            val root = JSONObject()
            val arr = JSONArray()
            for (b in baselines.values.sortedBy { it.periodStart }) {
                val obj = JSONObject().apply {
                    put("periodStart", b.periodStart.toString())
                    put("periodEnd", b.periodEnd.toString())
                    put("manualOverride", b.manualOverride)
                    put("updatedAtMs", b.updatedAtMs)
                }
                val mArr = JSONArray()
                for (m in b.capturedMonths.sorted()) mArr.put(m)
                obj.put("capturedMonths", mArr)

                val dArr = JSONArray()
                for ((date, entry) in b.plannedDays.entries.sortedBy { it.key }) {
                    dArr.put(
                        JSONObject().apply {
                            put("date", date.toString())
                            put("minutes", entry.minutes)
                            put("startText", entry.startText)
                            put("endText", entry.endText)
                        }
                    )
                }
                obj.put("plannedDays", dArr)
                arr.put(obj)
            }
            root.put("periods", arr)
            storageFile(context).writeText(root.toString(), Charsets.UTF_8)
        } catch (_: Exception) {
        }
    }

    fun getBaseline(context: Context, periodStart: LocalDate): PeriodBaseline? {
        return synchronized(lock) {
            ensureLoadedLocked(context)
            baselines[periodStart]
        }
    }

    private fun shiftDurationMinutes(shift: CalendarDisplayShift): Int {
        return if (shift.endMinutes >= shift.startMinutes) {
            shift.endMinutes - shift.startMinutes
        } else {
            (24 * 60 - shift.startMinutes) + shift.endMinutes
        }
    }

    private fun summarizeDayShifts(shifts: List<CalendarDisplayShift>): PlannedDayBaseline? {
        if (shifts.isEmpty()) return null
        val total = shifts.sumOf { shiftDurationMinutes(it) }
        if (total <= 0) return null
        val first = shifts.minByOrNull { it.startMinutes } ?: shifts.first()
        val last = shifts.maxByOrNull { it.startMinutes } ?: shifts.last()
        return PlannedDayBaseline(
            minutes = total,
            startText = first.startText,
            endText = last.endText
        )
    }

    /**
     * Tallentaa automaattisesti pohjasuunnitelman VAIN vielä alkamattomille 3 viikon jaksoille
     * (periodStart > tänään). Kun jakso on alkanut, pohjaa ei enää muuteta automaattisesti.
     */
    fun recordMonthSnapshot(context: Context, monthData: MonthDisplayData) {
        if (!isEnabled(context) || DemoModeHelper.isDemoEnabled(context)) return

        val ym = try {
            YearMonth.of(monthData.year, monthData.month)
        } catch (_: Exception) {
            return
        }
        val monthKey = ym.toString()
        val firstOfMonth = ym.atDay(1)
        val lastOfMonth = ym.atEndOfMonth()
        val today = LocalDate.now()

        // Etsitään kaikki 3 viikon jaksot, jotka osuvat tähän kuukauteen
        val overlappingPeriods = LinkedHashSet<Pair<LocalDate, LocalDate>>()
        var cursor = firstOfMonth
        while (!cursor.isAfter(lastOfMonth)) {
            overlappingPeriods.add(getPeriodBoundsForDate(context, cursor))
            cursor = cursor.plusDays(7)
        }
        overlappingPeriods.add(getPeriodBoundsForDate(context, lastOfMonth))

        synchronized(lock) {
            ensureLoadedLocked(context)
            var changed = false

            for ((pStart, pEnd) in overlappingPeriods) {
                // Tärkeä sääntö: laskenta ja automaattitallennus alkaa VASTA alkamattomista listoista
                if (!pStart.isAfter(today)) continue

                val existing = baselines[pStart]
                if (existing != null && existing.manualOverride) continue

                val rangeStart = if (pStart.isAfter(firstOfMonth)) pStart else firstOfMonth
                val rangeEnd = if (pEnd.isBefore(lastOfMonth)) pEnd else lastOfMonth

                val monthPlanned = LinkedHashMap<LocalDate, PlannedDayBaseline>()
                var d = rangeStart
                while (!d.isAfter(rangeEnd)) {
                    val day = monthData.days[d]
                    if (day != null && day.shifts.isNotEmpty()) {
                        summarizeDayShifts(day.shifts)?.let { monthPlanned[d] = it }
                    }
                    d = d.plusDays(1)
                }

                // Kuukauden osuus tallennetaan jos jaksossa on vuoroja tässä kuukaudessa
                // TAI jakson toinen kuukausi on jo julkaistu (jolloin tämä osa koostuu vapaapäivistä)
                val otherMonthAlreadyCaptured = existing != null &&
                    existing.plannedDays.isNotEmpty() &&
                    existing.capturedMonths.any { it != monthKey }
                if (monthPlanned.isEmpty() && !otherMonthAlreadyCaptured) continue

                val mergedDays = LinkedHashMap<LocalDate, PlannedDayBaseline>()
                existing?.plannedDays?.forEach { (date, entry) ->
                    if (YearMonth.from(date) != ym) {
                        mergedDays[date] = entry
                    }
                }
                mergedDays.putAll(monthPlanned)

                val mergedMonths = LinkedHashSet<String>()
                existing?.capturedMonths?.let { mergedMonths.addAll(it) }
                mergedMonths.add(monthKey)

                if (existing == null || existing.plannedDays != mergedDays || existing.capturedMonths != mergedMonths) {
                    baselines[pStart] = PeriodBaseline(
                        periodStart = pStart,
                        periodEnd = pEnd,
                        plannedDays = mergedDays,
                        capturedMonths = mergedMonths,
                        manualOverride = false,
                        updatedAtMs = System.currentTimeMillis()
                    )
                    changed = true
                }
            }

            if (changed) {
                version++
                persistLocked(context)
            }
        }
    }

    fun saveManualBaseline(
        context: Context,
        periodStart: LocalDate,
        periodEnd: LocalDate,
        combinedDayMap: Map<LocalDate, CalendarDisplayDay>
    ): Boolean {
        val planned = LinkedHashMap<LocalDate, PlannedDayBaseline>()
        var d = periodStart
        while (!d.isAfter(periodEnd)) {
            val day = combinedDayMap[d]
            if (day != null && day.shifts.isNotEmpty()) {
                summarizeDayShifts(day.shifts)?.let { planned[d] = it }
            }
            d = d.plusDays(1)
        }
        if (planned.isEmpty()) return false

        val reqMonths = LinkedHashSet<String>().apply {
            add(YearMonth.from(periodStart).toString())
            add(YearMonth.from(periodEnd).toString())
        }
        synchronized(lock) {
            ensureLoadedLocked(context)
            baselines[periodStart] = PeriodBaseline(
                periodStart = periodStart,
                periodEnd = periodEnd,
                plannedDays = planned,
                capturedMonths = reqMonths,
                manualOverride = true,
                updatedAtMs = System.currentTimeMillis()
            )
            version++
            persistLocked(context)
        }
        return true
    }

    fun removeBaseline(context: Context, periodStart: LocalDate) {
        synchronized(lock) {
            ensureLoadedLocked(context)
            if (baselines.remove(periodStart) != null) {
                version++
                persistLocked(context)
            }
        }
    }

    fun computePeriodBalance(
        context: Context,
        periodStart: LocalDate,
        periodEnd: LocalDate,
        combinedDayMap: Map<LocalDate, CalendarDisplayDay>,
        availableMonths: Set<String>
    ): PeriodBalanceResult? {
        if (!isEnabled(context) || DemoModeHelper.isDemoEnabled(context)) return null
        val baseline = getBaseline(context, periodStart) ?: return null
        if (!baseline.isComplete()) return null

        val reqMonths = baseline.requiredMonths()
        if (!reqMonths.all { it in availableMonths }) return null

        val today = LocalDate.now()
        val now = LocalDateTime.now()

        var totalPlanned = 0
        var totalEffective = 0
        var creditedSickDays = 0
        var creditedSickMinutes = 0
        val dayDetails = LinkedHashMap<LocalDate, DayBalanceInfo>()

        var d = periodStart
        while (!d.isAfter(periodEnd)) {
            val plannedEntry = baseline.plannedDays[d]
            val plannedMin = plannedEntry?.minutes ?: 0
            val currentDay = combinedDayMap[d]
            val shifts = currentDay?.shifts.orEmpty()
            val actualMin = shifts.sumOf { shiftDurationMinutes(it) }
            val hasSick = currentDay?.absences?.any { it.kind == "sick" } == true
            val hasOtherAbsence = currentDay?.absences?.any { it.kind != "sick" } == true

            var effectiveMin: Int
            var isCreditedSick = false
            var isCreditedOther = false

            if (hasSick && plannedMin > 0) {
                effectiveMin = maxOf(actualMin, plannedMin)
                if (actualMin < plannedMin) {
                    isCreditedSick = true
                    creditedSickDays++
                    creditedSickMinutes += (plannedMin - actualMin)
                }
            } else if (hasOtherAbsence && plannedMin > 0 && actualMin < plannedMin) {
                effectiveMin = plannedMin
                isCreditedOther = true
            } else if (d == today && plannedMin > 0 && actualMin < plannedMin) {
                // Keskeneräisestä kuluvasta päivästä ei lasketa miinusta ennen vuoron päättymistä
                val plannedEnd = parsePlannedEndDateTime(d, plannedEntry)
                effectiveMin = if (plannedEnd == null || now.isBefore(plannedEnd)) plannedMin else actualMin
            } else {
                effectiveMin = actualMin
            }

            val diff = effectiveMin - plannedMin
            totalPlanned += plannedMin
            totalEffective += effectiveMin

            if (plannedMin > 0 || actualMin > 0 || isCreditedSick || isCreditedOther) {
                dayDetails[d] = DayBalanceInfo(
                    date = d,
                    plannedMinutes = plannedMin,
                    plannedStartText = plannedEntry?.startText.orEmpty(),
                    plannedEndText = plannedEntry?.endText.orEmpty(),
                    actualMinutes = actualMin,
                    effectiveMinutes = effectiveMin,
                    diffMinutes = diff,
                    isCreditedSick = isCreditedSick,
                    isCreditedOtherAbsence = isCreditedOther
                )
            }
            d = d.plusDays(1)
        }

        return PeriodBalanceResult(
            periodStart = periodStart,
            periodEnd = periodEnd,
            baseline = baseline,
            plannedMinutes = totalPlanned,
            effectiveMinutes = totalEffective,
            diffMinutes = totalEffective - totalPlanned,
            creditedSickDays = creditedSickDays,
            creditedSickMinutes = creditedSickMinutes,
            dayDetails = dayDetails
        )
    }

    /**
     * Laskee parhaillaan meneillään olevan 3 viikon jakson saldon välimuistista (kutsu IO-säikeessä).
     */
    fun computeCurrentPeriodBalance(context: Context): PeriodBalanceResult? {
        if (!isEnabled(context) || DemoModeHelper.isDemoEnabled(context)) return null
        val today = LocalDate.now()
        val (pStart, pEnd) = getPeriodBoundsForDate(context, today)
        val baseline = getBaseline(context, pStart) ?: return null
        if (!baseline.isComplete()) return null

        val yms = linkedSetOf(YearMonth.from(pStart), YearMonth.from(pEnd))
        val combined = LinkedHashMap<LocalDate, CalendarDisplayDay>()
        val availableMonths = LinkedHashSet<String>()

        for (ym in yms) {
            val cached = NumeronApiClient.loadMonthDisplayCache(context, ym.year, ym.monthValue)
            if (cached != null) {
                availableMonths.add(ym.toString())
                combined.putAll(cached.days)
            }
        }
        return computePeriodBalance(context, pStart, pEnd, combined, availableMonths)
    }

    private fun parsePlannedEndDateTime(date: LocalDate, entry: PlannedDayBaseline?): LocalDateTime? {
        if (entry == null || entry.endText.isBlank()) return null
        val fmt = DateTimeFormatter.ofPattern("H:mm")
        return try {
            val sTime = if (entry.startText.isNotBlank()) LocalTime.parse(entry.startText.trim(), fmt) else null
            val eTime = LocalTime.parse(entry.endText.trim(), fmt)
            val endDate = if (sTime != null && eTime.isBefore(sTime)) date.plusDays(1) else date
            LocalDateTime.of(endDate, eTime)
        } catch (_: Exception) {
            null
        }
    }

    fun formatSignedHours(diffMinutes: Int, en: Boolean): String {
        val sep = if (en) "." else ","
        if (diffMinutes == 0) return "±0${sep}0 h"
        val sign = if (diffMinutes > 0) "+" else "−"
        val absMin = abs(diffMinutes)
        if (absMin < 60 && absMin % 6 != 0) {
            return if (en) "${sign}${absMin}m" else "${sign}${absMin} min"
        }
        val hoursStr = String.format("%.1f", absMin / 60.0).replace(".", sep)
        return "$sign$hoursStr h"
    }

    fun formatSignedExact(diffMinutes: Int, en: Boolean): String {
        if (diffMinutes == 0) return if (en) "±0m" else "±0 min"
        val sign = if (diffMinutes > 0) "+" else "−"
        val absMin = abs(diffMinutes)
        val h = absMin / 60
        val m = absMin % 60
        return when {
            h > 0 && m > 0 -> if (en) "${sign}${h}h ${m}m" else "${sign}${h} h ${m} min"
            h > 0 -> if (en) "${sign}${h}h" else "${sign}${h} h"
            else -> if (en) "${sign}${m}m" else "${sign}${m} min"
        }
    }

    fun formatHoursDecimal(totalMinutes: Int, en: Boolean): String {
        val sep = if (en) "." else ","
        return String.format("%.1f", totalMinutes / 60.0).replace(".", sep)
    }
}
