#!/usr/bin/env python3
"""
Numeron Vuorovahti (V2) – Viereisten kuukausien vuorot himmennettynä (patch_adjacent_days.py):
- NativeShiftsView.kt:
  * Näyttää kalenteriruudukossa myös näkyvillä olevien edellisen ja seuraavan kuukauden päivien
    työvuorot, poissaolot, arkipyhät, toiveet ja huomiot himmennettynä (alpha = 0.45f)
  * Kuukausikooste (vuoromäärä, tunnit, aamu/ilta/yö, saldo) lasketaan edelleen vain aktiivisen kuukauden päivistä
  * Myös himmennettyjä päiviä voi napauttaa päivädialogin avaamiseksi ilman kuukauden vaihtoa
  * Esilataa hiljaisesti taustalla molemmat viereiset kuukaudet (seuraava + edellinen)
  * Yhdistää kuukausirajan yli jatkuvat lomapalkit saumattomasti (combinedMap)
- app/build.gradle.kts: versionCode +1 ja versionName +1 (idempotentti)
"""

import re
import sys
from pathlib import Path


def find_file(filename: str) -> Path | None:
    candidates = [
        Path("app/src/main/java/fi/numeron/vuorovahti") / filename,
        Path("src/main/java/fi/numeron/vuorovahti") / filename,
        Path("app") / filename,
        Path(filename),
    ]
    for c in candidates:
        if c.exists():
            return c
    for p in Path(".").rglob(filename):
        if ".git" not in p.parts and "build" not in p.parts:
            return p
    return None


def read_text_keep_nl(path: Path) -> tuple[str, str]:
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def write_text_keep_nl(path: Path, content: str, newline: str) -> None:
    normalized = content.replace("\r\n", "\n")
    if newline == "\r\n":
        normalized = normalized.replace("\n", "\r\n")
    path.write_bytes(normalized.encode("utf-8"))


def replace_once(content: str, old: str, new: str, label: str) -> str:
    if new in content and old not in content:
        print(f"  [OK - jo sovellettu] {label}")
        return content
    if old not in content:
        print(f"  [VAROITUS - kohdetta ei löytynyt] {label}")
        return content
    print(f"  [PÄIVITETTY] {label}")
    return content.replace(old, new, 1)


def patch_native_shifts_view(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    # 1. Tarkempi diff-vertailu viereisten kuukausien kartalle
    text = replace_once(
        text,
        "    private var lastRenderedAdjacentSize: Int = -1",
        "    private var lastRenderedAdjacentMap: Map<LocalDate, CalendarDisplayDay>? = null",
        "NativeShiftsView: lastRenderedAdjacentMap-kenttä"
    )

    old_render_if = """    private fun renderCalendarGridIfChanged(forceRender: Boolean = false) {
        val key = buildRenderKey()
        val data = currentData
        val adjSize = adjacentDayMap.size
        if (!forceRender && key == lastRenderedRenderKey && data == lastRenderedData && adjSize == lastRenderedAdjacentSize) {
            return
        }
        lastRenderedRenderKey = key
        lastRenderedData = data
        lastRenderedAdjacentSize = adjSize
        renderCalendarGrid()
    }"""

    new_render_if = """    private fun renderCalendarGridIfChanged(forceRender: Boolean = false) {
        val key = buildRenderKey()
        val data = currentData
        val adj = adjacentDayMap
        if (!forceRender && key == lastRenderedRenderKey && data == lastRenderedData && adj == lastRenderedAdjacentMap) {
            return
        }
        lastRenderedRenderKey = key
        lastRenderedData = data
        lastRenderedAdjacentMap = adj
        renderCalendarGrid()
    }"""

    text = replace_once(
        text,
        old_render_if,
        new_render_if,
        "NativeShiftsView: renderCalendarGridIfChanged vertaa viereisten kuukausien sisältöä"
    )

    # 2. Molempien viereisten kuukausien (seuraava + edellinen) hiljainen esilataus
    old_prefetch = """    private fun scheduleNextMonthPrefetch(baseYm: YearMonth) {
        if (DemoModeHelper.isDemoEnabled(context)) return
        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) return
        val nextYm = baseYm.plusMonths(1)
        val nowMs = System.currentTimeMillis()
        val existingMem = memoryMonths[nextYm]
        if (existingMem != null && (nowMs - existingMem.second) < 5L * 60_000L) return

        prefetchJob?.cancel()
        prefetchJob = scope.launch {
            val diskAgeOk = withContext(Dispatchers.IO) {
                val savedMs = NumeronApiClient.getMonthCacheSavedAtMs(context, nextYm.year, nextYm.monthValue)
                if (savedMs > 0L && (System.currentTimeMillis() - savedMs) < 10L * 60_000L) {
                    val diskData = NumeronApiClient.loadMonthDisplayCache(context, nextYm.year, nextYm.monthValue)
                    diskData to savedMs
                } else {
                    null
                }
            }
            if (diskAgeOk != null && diskAgeOk.first != null) {
                storeMemoryMonth(nextYm, diskAgeOk.first!!, diskAgeOk.second)
                if (displayedMonth == baseYm) {
                    val adjPair = withContext(Dispatchers.IO) { loadAdjacentMonthsCacheSync(baseYm) }
                    adjacentDayMap = adjPair.first
                    adjacentLoadedMonths = adjPair.second
                    renderCalendarGridIfChanged()
                }
                return@launch
            }

            val html = NumeronApiClient.fetchMonthCalendarHtml(context, nextYm.year, nextYm.monthValue)
                ?: return@launch
            val parsed = withContext(Dispatchers.Default) {
                NumeronParser.parseMonthForDisplay(html)
            } ?: return@launch
            withContext(Dispatchers.IO) {
                NumeronApiClient.saveMonthDisplayCache(context, parsed)
                PeriodBalanceManager.recordMonthSnapshot(context, parsed)
            }
            storeMemoryMonth(nextYm, parsed, System.currentTimeMillis())
            if (displayedMonth == baseYm) {
                val adjPair = withContext(Dispatchers.IO) { loadAdjacentMonthsCacheSync(baseYm) }
                adjacentDayMap = adjPair.first
                adjacentLoadedMonths = adjPair.second
                renderCalendarGridIfChanged()
            }
        }
    }"""

    new_prefetch = """    private fun scheduleNextMonthPrefetch(baseYm: YearMonth) {
        if (DemoModeHelper.isDemoEnabled(context)) return
        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) return

        val nowMs = System.currentTimeMillis()
        val targets = listOf(baseYm.plusMonths(1), baseYm.minusMonths(1)).filter { targetYm ->
            val existingMem = memoryMonths[targetYm]
            existingMem == null || (nowMs - existingMem.second) >= 5L * 60_000L
        }
        if (targets.isEmpty()) return

        prefetchJob?.cancel()
        prefetchJob = scope.launch {
            var anyUpdated = false
            for (targetYm in targets) {
                val diskAgeOk = withContext(Dispatchers.IO) {
                    val savedMs = NumeronApiClient.getMonthCacheSavedAtMs(context, targetYm.year, targetYm.monthValue)
                    if (savedMs > 0L && (System.currentTimeMillis() - savedMs) < 10L * 60_000L) {
                        val diskData = NumeronApiClient.loadMonthDisplayCache(context, targetYm.year, targetYm.monthValue)
                        diskData to savedMs
                    } else {
                        null
                    }
                }
                if (diskAgeOk != null && diskAgeOk.first != null) {
                    storeMemoryMonth(targetYm, diskAgeOk.first!!, diskAgeOk.second)
                    anyUpdated = true
                    continue
                }

                val html = NumeronApiClient.fetchMonthCalendarHtml(context, targetYm.year, targetYm.monthValue)
                    ?: continue
                val parsed = withContext(Dispatchers.Default) {
                    NumeronParser.parseMonthForDisplay(html)
                } ?: continue
                withContext(Dispatchers.IO) {
                    NumeronApiClient.saveMonthDisplayCache(context, parsed)
                    PeriodBalanceManager.recordMonthSnapshot(context, parsed)
                }
                storeMemoryMonth(targetYm, parsed, System.currentTimeMillis())
                anyUpdated = true
            }
            if (anyUpdated && displayedMonth == baseYm) {
                val adjPair = withContext(Dispatchers.IO) { loadAdjacentMonthsCacheSync(baseYm) }
                adjacentDayMap = adjPair.first
                adjacentLoadedMonths = adjPair.second
                renderCalendarGridIfChanged()
            }
        }
    }"""

    text = replace_once(
        text,
        old_prefetch,
        new_prefetch,
        "NativeShiftsView: esilataa sekä seuraavan että edellisen kuukauden taustalla"
    )

    # 2b. Poistetaan käyttämättömäksi jäävä dayMap-rivi renderCalendarGridista
    text = replace_once(
        text,
        "        val dayMap = currentData?.days.orEmpty()\n        val combinedMap = buildCombinedDayMap()",
        "        val combinedMap = buildCombinedDayMap()",
        "NativeShiftsView: poistettu käyttämätön dayMap-muuttuja"
    )

    # 3. Viereisten kuukausien päivien tiedot, himmennys (alpha = 0.45f) ja päivädialogi
    old_cell_block = """            for (offset in 0..6) {
                val date = weekStart.plusDays(offset.toLong())
                val isCurrentMonth = (date.monthValue == ym.monthValue && date.year == ym.year)
                val isToday = (date == today)
                val isPast = date.isBefore(today)
                val isWeekend = (offset == 5 || offset == 6)
                val holidayName = if (showHolidays && isCurrentMonth) FinnishHolidays.getHolidayName(date, en) else null
                val dayData = dayMap[date]
                val dayBalance = if (isCurrentMonth) periodBalance?.dayDetails?.get(date) else null
                if (isCurrentMonth && periodBalance != null) {
                    monthHasTrackedBalance = true
                    if (dayBalance != null) {
                        monthBalanceDiff += dayBalance.diffMinutes
                    }
                }
                val shortRestMins = if (showShortRest && isCurrentMonth) computeShortRestMinutes(date, combinedMap) else null

                if (isCurrentMonth && dayData != null) {
                    for (shift in dayData.shifts) {
                        shiftCount++
                        val dur = if (shift.endMinutes >= shift.startMinutes) {
                            shift.endMinutes - shift.startMinutes
                        } else {
                            (24 * 60 - shift.startMinutes) + shift.endMinutes
                        }
                        totalMinutes += dur
                        val crossesMidnight = shift.endMinutes < shift.startMinutes
                        when {
                            crossesMidnight || shift.startMinutes >= 20 * 60 || shift.startMinutes < 4 * 60 -> nightCount++
                            shift.startMinutes >= 11 * 60 + 30 -> eveningCount++
                            else -> morningCount++
                        }
                    }
                }

                val cellBgColor = when {
                    isToday -> UiStyleHelper.todayCellHex(context)
                    !isCurrentMonth -> UiStyleHelper.otherMonthCellHex(context)
                    holidayName != null -> UiStyleHelper.holidayCellHex(context)
                    isPast -> if (isWeekend) UiStyleHelper.pastWeekendCellHex(context) else UiStyleHelper.pastCellHex(context)
                    isWeekend -> UiStyleHelper.weekendCellHex(context)
                    else -> UiStyleHelper.cardHex(context)
                }
                val cellBorderColor = if (isToday) "#38BDF8" else borderHex

                val cell = LinearLayout(context).apply {
                    orientation = VERTICAL
                    background = if (isCurrentMonth) {
                        UiStyleHelper.rippleCellBg(context, cellBgColor, cellBorderColor)
                    } else {
                        UiStyleHelper.cellBg(context, cellBgColor, cellBorderColor)
                    }
                    setPadding(dp(2), dp(2), dp(2), dp(3))
                    minimumHeight = dp(72)
                    if (isCurrentMonth) {
                        setOnClickListener { showDayDetailsDialog(date, dayData, holidayName, shortRestMins, dayBalance) }
                    }
                }

                // Päivänumero + lyhyt lepoaika -merkki + kommenttipallukka
                val topRow = LinearLayout(context).apply {
                    orientation = HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                }
                val numTv = TextView(context).apply {
                    text = date.dayOfMonth.toString()
                    setTextColor(
                        when {
                            !isCurrentMonth -> Color.parseColor("#64748B")
                            isToday -> Color.parseColor("#38BDF8")
                            holidayName != null -> Color.parseColor("#F87171")
                            isWeekend -> Color.parseColor("#93C5FD")
                            else -> Color.parseColor("#F1F5F9")
                        }
                    )
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)
                    setTypeface(null, Typeface.BOLD)
                    setPadding(dp(2), 0, 0, dp(1))
                }
                topRow.addView(numTv, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))

                if (shortRestMins != null) {
                    val warnTv = TextView(context).apply {
                        text = "⚠"
                        setTextColor(Color.parseColor("#FBBF24"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 9.5f)
                        setPadding(0, 0, dp(2), 0)
                    }
                    topRow.addView(warnTv, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))
                }

                if (dayData?.hasCommentCircle == true) {
                    val dot = View(context).apply {
                        background = GradientDrawable().apply {
                            shape = GradientDrawable.OVAL
                            setColor(Color.parseColor("#F59E0B"))
                        }
                    }
                    topRow.addView(
                        dot,
                        LayoutParams(dp(6), dp(6)).apply {
                            marginEnd = dp(2)
                        }
                    )
                }
                cell.addView(topRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

                // Suomen arkipyhän nimi pienenä merkintänä
                if (holidayName != null) {
                    val holTv = TextView(context).apply {
                        text = holidayName
                        setTextColor(Color.parseColor("#FCA5A5"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 8.5f)
                        setTypeface(null, Typeface.BOLD)
                        maxLines = 1
                        ellipsize = TextUtils.TruncateAt.END
                        setPadding(dp(2), 0, dp(1), dp(1))
                    }
                    cell.addView(holTv, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
                }

                // Poissaolot (yhtenäiset lomapalkit peräkkäisille päiville)
                val prevDate = date.minusDays(1)
                val nextDate = date.plusDays(1)
                val prevAbsences = if (offset > 0) dayMap[prevDate]?.absences.orEmpty() else emptyList()
                val nextAbsences = if (offset < 6) dayMap[nextDate]?.absences.orEmpty() else emptyList()

                dayData?.absences?.forEach { absItem ->
                    if (absItem.kind == "sick" &&
                        dayBalance?.isCreditedSick == true &&
                        dayBalance.plannedStartText.isNotEmpty() &&
                        dayData.shifts.isEmpty()
                    ) {
                        val sickBox = LinearLayout(context).apply {
                            orientation = VERTICAL
                            gravity = Gravity.CENTER
                            background = UiStyleHelper.roundedBg(context, "#991B1B", "#F87171", 4f)
                            setPadding(dp(2), dp(2), dp(2), dp(2))
                        }
                        sickBox.addView(
                            TextView(context).apply {
                                text = "${dayBalance.plannedStartText}\\n${dayBalance.plannedEndText}"
                                setTextColor(Color.WHITE)
                                setTextSize(TypedValue.COMPLEX_UNIT_SP, 9.5f)
                                setTypeface(null, Typeface.BOLD)
                                gravity = Gravity.CENTER
                                maxLines = 2
                            },
                            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT)
                        )
                        sickBox.addView(
                            TextView(context).apply {
                                text = if (en) "SL cred." else "SL hyv."
                                setTextColor(Color.parseColor("#FECACA"))
                                setTextSize(TypedValue.COMPLEX_UNIT_SP, 8f)
                                setTypeface(null, Typeface.BOLD)
                                gravity = Gravity.CENTER
                                maxLines = 1
                            },
                            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT)
                        )
                        cell.addView(
                            sickBox,
                            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                                bottomMargin = dp(2)
                            }
                        )
                    } else {
                        val connectedLeft = prevAbsences.any { it.title.equals(absItem.title, ignoreCase = true) }
                        val connectedRight = nextAbsences.any { it.title.equals(absItem.title, ignoreCase = true) }
                        val (bgHex, fgHex) = when (absItem.kind) {
                            "vacation" -> "#15803D" to "#FFFFFF"
                            "sick" -> "#B91C1C" to "#FFFFFF"
                            else -> "#334155" to "#F1F5F9"
                        }
                        val r = dp(4).toFloat()
                        val rL = if (connectedLeft) 0f else r
                        val rR = if (connectedRight) 0f else r
                        val badge = TextView(context).apply {
                            text = if (connectedLeft) " " else absItem.title
                            setTextColor(Color.parseColor(fgHex))
                            setTextSize(TypedValue.COMPLEX_UNIT_SP, 9.5f)
                            setTypeface(null, Typeface.BOLD)
                            maxLines = 1
                            ellipsize = TextUtils.TruncateAt.END
                            background = GradientDrawable().apply {
                                shape = GradientDrawable.RECTANGLE
                                setColor(Color.parseColor(bgHex))
                                cornerRadii = floatArrayOf(rL, rL, rR, rR, rR, rR, rL, rL)
                            }
                            setPadding(if (connectedLeft) 0 else dp(3), dp(1), if (connectedRight) 0 else dp(3), dp(1))
                        }
                        cell.addView(
                            badge,
                            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                                bottomMargin = dp(2)
                            }
                        )
                    }
                }

                // Työvuorot asetusten värikoodeilla
                dayData?.shifts?.forEach { shift ->
                    val bgRgb = pickShiftRgb(shift, morningRgb, eveningRgb, nightRgb)
                    val fgColor = contrastColor(bgRgb)
                    val label = "${shift.startText}\\n${shift.endText}"
                    val badge = TextView(context).apply {
                        text = label
                        setTextColor(fgColor)
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 10f)
                        setTypeface(null, Typeface.BOLD)
                        gravity = Gravity.CENTER
                        maxLines = 2
                        background = GradientDrawable().apply {
                            shape = GradientDrawable.RECTANGLE
                            cornerRadius = dp(4).toFloat()
                            setColor(bgRgb)
                        }
                        setPadding(dp(2), dp(2), dp(2), dp(2))
                    }
                    cell.addView(
                        badge,
                        LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                            bottomMargin = dp(2)
                        }
                    )
                }

                // Toiveet
                dayData?.requests?.forEach { req ->
                    val badge = TextView(context).apply {
                        text = req.title
                        setTextColor(Color.parseColor("#EDE9FE"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 9.5f)
                        setTypeface(null, Typeface.BOLD)
                        maxLines = 1
                        ellipsize = TextUtils.TruncateAt.END
                        background = UiStyleHelper.roundedBg(context, "#2E1F47", "#8B5CF6", 4f)
                        setPadding(dp(3), dp(1), dp(3), dp(1))
                    }
                    cell.addView(
                        badge,
                        LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                            bottomMargin = dp(2)
                        }
                    )
                }

                row.addView(cell, LayoutParams(0, LayoutParams.MATCH_PARENT, 1f))
            }"""

    new_cell_block = """            for (offset in 0..6) {
                val date = weekStart.plusDays(offset.toLong())
                val isCurrentMonth = (date.monthValue == ym.monthValue && date.year == ym.year)
                val contentAlpha = if (isCurrentMonth) 1f else 0.45f
                val isToday = (date == today)
                val isPast = date.isBefore(today)
                val isWeekend = (offset == 5 || offset == 6)
                val holidayName = if (showHolidays) FinnishHolidays.getHolidayName(date, en) else null
                val dayData = combinedMap[date]
                val dayBalance = periodBalance?.dayDetails?.get(date)
                if (isCurrentMonth && periodBalance != null) {
                    monthHasTrackedBalance = true
                    if (dayBalance != null) {
                        monthBalanceDiff += dayBalance.diffMinutes
                    }
                }
                val shortRestMins = if (showShortRest) computeShortRestMinutes(date, combinedMap) else null

                if (isCurrentMonth && dayData != null) {
                    for (shift in dayData.shifts) {
                        shiftCount++
                        val dur = if (shift.endMinutes >= shift.startMinutes) {
                            shift.endMinutes - shift.startMinutes
                        } else {
                            (24 * 60 - shift.startMinutes) + shift.endMinutes
                        }
                        totalMinutes += dur
                        val crossesMidnight = shift.endMinutes < shift.startMinutes
                        when {
                            crossesMidnight || shift.startMinutes >= 20 * 60 || shift.startMinutes < 4 * 60 -> nightCount++
                            shift.startMinutes >= 11 * 60 + 30 -> eveningCount++
                            else -> morningCount++
                        }
                    }
                }

                val cellBgColor = when {
                    isToday -> UiStyleHelper.todayCellHex(context)
                    !isCurrentMonth -> UiStyleHelper.otherMonthCellHex(context)
                    holidayName != null -> UiStyleHelper.holidayCellHex(context)
                    isPast -> if (isWeekend) UiStyleHelper.pastWeekendCellHex(context) else UiStyleHelper.pastCellHex(context)
                    isWeekend -> UiStyleHelper.weekendCellHex(context)
                    else -> UiStyleHelper.cardHex(context)
                }
                val cellBorderColor = if (isToday) "#38BDF8" else borderHex

                val cell = LinearLayout(context).apply {
                    orientation = VERTICAL
                    background = UiStyleHelper.rippleCellBg(context, cellBgColor, cellBorderColor)
                    setPadding(dp(2), dp(2), dp(2), dp(3))
                    minimumHeight = dp(72)
                    setOnClickListener { showDayDetailsDialog(date, dayData, holidayName, shortRestMins, dayBalance) }
                }

                // Päivänumero + lyhyt lepoaika -merkki + kommenttipallukka
                val topRow = LinearLayout(context).apply {
                    orientation = HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                }
                val numTv = TextView(context).apply {
                    text = date.dayOfMonth.toString()
                    setTextColor(
                        when {
                            !isCurrentMonth && holidayName != null -> Color.parseColor("#8C4A52")
                            !isCurrentMonth && isWeekend -> Color.parseColor("#556B85")
                            !isCurrentMonth -> Color.parseColor("#64748B")
                            isToday -> Color.parseColor("#38BDF8")
                            holidayName != null -> Color.parseColor("#F87171")
                            isWeekend -> Color.parseColor("#93C5FD")
                            else -> Color.parseColor("#F1F5F9")
                        }
                    )
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)
                    setTypeface(null, Typeface.BOLD)
                    setPadding(dp(2), 0, 0, dp(1))
                }
                topRow.addView(numTv, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))

                if (shortRestMins != null) {
                    val warnTv = TextView(context).apply {
                        text = "⚠"
                        setTextColor(Color.parseColor("#FBBF24"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 9.5f)
                        setPadding(0, 0, dp(2), 0)
                        alpha = contentAlpha
                    }
                    topRow.addView(warnTv, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))
                }

                if (dayData?.hasCommentCircle == true) {
                    val dot = View(context).apply {
                        background = GradientDrawable().apply {
                            shape = GradientDrawable.OVAL
                            setColor(Color.parseColor("#F59E0B"))
                        }
                        alpha = contentAlpha
                    }
                    topRow.addView(
                        dot,
                        LayoutParams(dp(6), dp(6)).apply {
                            marginEnd = dp(2)
                        }
                    )
                }
                cell.addView(topRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

                // Suomen arkipyhän nimi pienenä merkintänä
                if (holidayName != null) {
                    val holTv = TextView(context).apply {
                        text = holidayName
                        setTextColor(Color.parseColor("#FCA5A5"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 8.5f)
                        setTypeface(null, Typeface.BOLD)
                        maxLines = 1
                        ellipsize = TextUtils.TruncateAt.END
                        setPadding(dp(2), 0, dp(1), dp(1))
                        alpha = contentAlpha
                    }
                    cell.addView(holTv, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
                }

                // Poissaolot (yhtenäiset lomapalkit peräkkäisille päiville myös kuukausirajan yli)
                val prevDate = date.minusDays(1)
                val nextDate = date.plusDays(1)
                val prevAbsences = if (offset > 0) combinedMap[prevDate]?.absences.orEmpty() else emptyList()
                val nextAbsences = if (offset < 6) combinedMap[nextDate]?.absences.orEmpty() else emptyList()

                dayData?.absences?.forEach { absItem ->
                    if (absItem.kind == "sick" &&
                        dayBalance?.isCreditedSick == true &&
                        dayBalance.plannedStartText.isNotEmpty() &&
                        dayData.shifts.isEmpty()
                    ) {
                        val sickBox = LinearLayout(context).apply {
                            orientation = VERTICAL
                            gravity = Gravity.CENTER
                            background = UiStyleHelper.roundedBg(context, "#991B1B", "#F87171", 4f)
                            setPadding(dp(2), dp(2), dp(2), dp(2))
                            alpha = contentAlpha
                        }
                        sickBox.addView(
                            TextView(context).apply {
                                text = "${dayBalance.plannedStartText}\\n${dayBalance.plannedEndText}"
                                setTextColor(Color.WHITE)
                                setTextSize(TypedValue.COMPLEX_UNIT_SP, 9.5f)
                                setTypeface(null, Typeface.BOLD)
                                gravity = Gravity.CENTER
                                maxLines = 2
                            },
                            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT)
                        )
                        sickBox.addView(
                            TextView(context).apply {
                                text = if (en) "SL cred." else "SL hyv."
                                setTextColor(Color.parseColor("#FECACA"))
                                setTextSize(TypedValue.COMPLEX_UNIT_SP, 8f)
                                setTypeface(null, Typeface.BOLD)
                                gravity = Gravity.CENTER
                                maxLines = 1
                            },
                            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT)
                        )
                        cell.addView(
                            sickBox,
                            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                                bottomMargin = dp(2)
                            }
                        )
                    } else {
                        val connectedLeft = prevAbsences.any { it.title.equals(absItem.title, ignoreCase = true) }
                        val connectedRight = nextAbsences.any { it.title.equals(absItem.title, ignoreCase = true) }
                        val (bgHex, fgHex) = when (absItem.kind) {
                            "vacation" -> "#15803D" to "#FFFFFF"
                            "sick" -> "#B91C1C" to "#FFFFFF"
                            else -> "#334155" to "#F1F5F9"
                        }
                        val r = dp(4).toFloat()
                        val rL = if (connectedLeft) 0f else r
                        val rR = if (connectedRight) 0f else r
                        val badge = TextView(context).apply {
                            text = if (connectedLeft) " " else absItem.title
                            setTextColor(Color.parseColor(fgHex))
                            setTextSize(TypedValue.COMPLEX_UNIT_SP, 9.5f)
                            setTypeface(null, Typeface.BOLD)
                            maxLines = 1
                            ellipsize = TextUtils.TruncateAt.END
                            background = GradientDrawable().apply {
                                shape = GradientDrawable.RECTANGLE
                                setColor(Color.parseColor(bgHex))
                                cornerRadii = floatArrayOf(rL, rL, rR, rR, rR, rR, rL, rL)
                            }
                            setPadding(if (connectedLeft) 0 else dp(3), dp(1), if (connectedRight) 0 else dp(3), dp(1))
                            alpha = contentAlpha
                        }
                        cell.addView(
                            badge,
                            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                                bottomMargin = dp(2)
                            }
                        )
                    }
                }

                // Työvuorot asetusten värikoodeilla (muun kuukauden päivät himmennettynä)
                dayData?.shifts?.forEach { shift ->
                    val bgRgb = pickShiftRgb(shift, morningRgb, eveningRgb, nightRgb)
                    val fgColor = contrastColor(bgRgb)
                    val label = "${shift.startText}\\n${shift.endText}"
                    val badge = TextView(context).apply {
                        text = label
                        setTextColor(fgColor)
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 10f)
                        setTypeface(null, Typeface.BOLD)
                        gravity = Gravity.CENTER
                        maxLines = 2
                        background = GradientDrawable().apply {
                            shape = GradientDrawable.RECTANGLE
                            cornerRadius = dp(4).toFloat()
                            setColor(bgRgb)
                        }
                        setPadding(dp(2), dp(2), dp(2), dp(2))
                        alpha = contentAlpha
                    }
                    cell.addView(
                        badge,
                        LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                            bottomMargin = dp(2)
                        }
                    )
                }

                // Toiveet
                dayData?.requests?.forEach { req ->
                    val badge = TextView(context).apply {
                        text = req.title
                        setTextColor(Color.parseColor("#EDE9FE"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 9.5f)
                        setTypeface(null, Typeface.BOLD)
                        maxLines = 1
                        ellipsize = TextUtils.TruncateAt.END
                        background = UiStyleHelper.roundedBg(context, "#2E1F47", "#8B5CF6", 4f)
                        setPadding(dp(3), dp(1), dp(3), dp(1))
                        alpha = contentAlpha
                    }
                    cell.addView(
                        badge,
                        LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                            bottomMargin = dp(2)
                        }
                    )
                }

                row.addView(cell, LayoutParams(0, LayoutParams.MATCH_PARENT, 1f))
            }"""

    text = replace_once(
        text,
        old_cell_block,
        new_cell_block,
        "NativeShiftsView: viereisten kuukausien vuorot, poissaolot, pyhät ja päivädialogi himmennettynä"
    )

    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_build_gradle(path: Path, should_bump: bool) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    if should_bump:
        m_code = re.search(r"versionCode\s*=\s*(\d+)", text)
        if m_code:
            old_code = int(m_code.group(1))
            new_code = old_code + 1
            text = text[:m_code.start()] + f"versionCode = {new_code}" + text[m_code.end():]
            print(f"  [PÄIVITETTY] versionCode {old_code} -> {new_code}")

        m_name = re.search(r'versionName\s*=\s*"(\d+)\.(\d+)\.(\d+)"', text)
        if m_name:
            maj, minor, patch_num = int(m_name.group(1)), int(m_name.group(2)), int(m_name.group(3))
            old_name = f"{maj}.{minor}.{patch_num}"
            new_name = f"{maj}.{minor}.{patch_num + 1}"
            text = text[:m_name.start()] + f'versionName = "{new_name}"' + text[m_name.end():]
            print(f'  [PÄIVITETTY] versionName "{old_name}" -> "{new_name}"')
    else:
        print("  [OK - jo sovellettu] versiota ei koroteta toistuvassa ajossa")

    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def main() -> int:
    changed = 0

    ns_path = find_file("NativeShiftsView.kt")
    if ns_path is None:
        print("[VIRHE] NativeShiftsView.kt ei löytynyt!")
        return 1

    print(f"Käsitellään: {ns_path}")
    shifts_changed = patch_native_shifts_view(ns_path)
    if shifts_changed:
        changed += 1

    gr_path = find_file("build.gradle.kts")
    if gr_path is not None:
        print(f"Käsitellään: {gr_path}")
        if patch_build_gradle(gr_path, should_bump=shifts_changed):
            changed += 1
    else:
        print("[EI LÖYTYNYT] build.gradle.kts")

    print(f"\nValmis! Muokattuja tiedostoja: {changed}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
