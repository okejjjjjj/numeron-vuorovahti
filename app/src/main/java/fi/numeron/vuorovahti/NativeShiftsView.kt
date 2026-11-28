package fi.numeron.vuorovahti

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.webkit.CookieManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.URLEncoder
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.time.temporal.WeekFields
import kotlin.math.abs

class NativeShiftsView(
    private val context: Context,
    private val scope: CoroutineScope,
    private val onOpenWebUrl: (url: String, title: String) -> Unit
) : LinearLayout(context) {

    private var displayedMonth: YearMonth = YearMonth.now()
    private var currentData: MonthDisplayData? = null
    private var loadJob: Job? = null

    private var swipeDownX: Float = 0f
    private var swipeDownY: Float = 0f

    private val swipeRefresh: SwipeRefreshLayout
    private val txtMonthTitle: TextView
    private val btnPrev: Button
    private val btnNext: Button
    private val btnToday: Button
    private val btnRefresh: Button
    private val progressBar: ProgressBar
    private val txtStatus: TextView
    private val gridContainer: LinearLayout
    private val txtMonthSummary: TextView

    private val fiMonths = arrayOf(
        "Tammikuu", "Helmikuu", "Maaliskuu", "Huhtikuu", "Toukokuu", "Kesäkuu",
        "Heinäkuu", "Elokuu", "Syyskuu", "Lokakuu", "Marraskuu", "Joulukuu"
    )
    private val enMonths = arrayOf(
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    )
    private val fiShortMonths = arrayOf(
        "Tammi", "Helmi", "Maalis", "Huhti", "Touko", "Kesä",
        "Heinä", "Elo", "Syys", "Loka", "Marras", "Joulu"
    )
    private val enShortMonths = arrayOf(
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    )

    init {
        orientation = VERTICAL
        setBackgroundColor(Color.parseColor("#0F1722"))
        setPadding(dp(8), dp(8), dp(8), dp(4))

        // Yläkortti: kuukausivalitsin + pikapainikkeet
        val headerCard = LinearLayout(context).apply {
            orientation = VERTICAL
            background = UiStyleHelper.roundedBg(context, "#182332", "#2A394A", 12f)
            setPadding(dp(10), dp(10), dp(10), dp(8))
        }

        val navRow = LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        btnPrev = Button(context).apply {
            text = "◀"
            setTextColor(Color.parseColor("#38BDF8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            background = UiStyleHelper.rippleRoundedBg(context, "#233040", "#37475A", 10f)
            setPadding(0, 0, 0, 0)
            setOnClickListener {
                displayedMonth = displayedMonth.minusMonths(1)
                loadMonth(forceNetwork = true, fromSwipe = false)
            }
        }
        navRow.addView(btnPrev, LayoutParams(dp(44), dp(38)))

        txtMonthTitle = TextView(context).apply {
            setTextColor(Color.parseColor("#F1F5F9"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
            setTypeface(null, Typeface.BOLD)
            gravity = Gravity.CENTER
            background = UiStyleHelper.rippleRoundedBg(context, "#111923", "#2A394A", 10f)
            setPadding(dp(12), dp(7), dp(12), dp(7))
            setOnClickListener { showMonthJumpDialog() }
        }
        navRow.addView(
            txtMonthTitle,
            LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f).apply {
                marginStart = dp(10)
                marginEnd = dp(10)
            }
        )

        btnNext = Button(context).apply {
            text = "▶"
            setTextColor(Color.parseColor("#38BDF8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            background = UiStyleHelper.rippleRoundedBg(context, "#233040", "#37475A", 10f)
            setPadding(0, 0, 0, 0)
            setOnClickListener {
                displayedMonth = displayedMonth.plusMonths(1)
                loadMonth(forceNetwork = true, fromSwipe = false)
            }
        }
        navRow.addView(btnNext, LayoutParams(dp(44), dp(38)))

        headerCard.addView(navRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        val actionRow = LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(8), 0, 0)
        }

        btnToday = Button(context).apply {
            isAllCaps = false
            setTextColor(Color.parseColor("#E2E8F0"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)
            background = UiStyleHelper.rippleRoundedBg(context, "#233040", "#37475A", 8f)
            setPadding(dp(12), dp(4), dp(12), dp(4))
            minHeight = 0
            minimumHeight = dp(32)
            setOnClickListener {
                displayedMonth = YearMonth.now()
                loadMonth(forceNetwork = true, fromSwipe = false)
            }
        }
        actionRow.addView(btnToday, LayoutParams(LayoutParams.WRAP_CONTENT, dp(32)))

        btnRefresh = Button(context).apply {
            isAllCaps = false
            setTextColor(Color.parseColor("#38BDF8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)
            background = UiStyleHelper.rippleRoundedBg(context, "#233040", "#37475A", 8f)
            setPadding(dp(12), dp(4), dp(12), dp(4))
            minHeight = 0
            minimumHeight = dp(32)
            setOnClickListener { loadMonth(forceNetwork = true, fromSwipe = false) }
        }
        actionRow.addView(
            btnRefresh,
            LayoutParams(LayoutParams.WRAP_CONTENT, dp(32)).apply {
                marginStart = dp(8)
            }
        )

        val spacer = View(context)
        actionRow.addView(spacer, LayoutParams(0, 1, 1f))

        progressBar = ProgressBar(context, null, android.R.attr.progressBarStyleSmall).apply {
            isIndeterminate = true
            visibility = View.GONE
        }
        actionRow.addView(progressBar, LayoutParams(dp(18), dp(18)))

        txtStatus = TextView(context).apply {
            setTextColor(Color.parseColor("#94A3B8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)
            setPadding(dp(6), 0, 0, 0)
        }
        actionRow.addView(txtStatus, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))

        headerCard.addView(actionRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        addView(
            headerCard,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(8)
            }
        )

        swipeRefresh = SwipeRefreshLayout(context).apply {
            UiStyleHelper.configureSwipeRefresh(this)
            setOnRefreshListener { loadMonth(forceNetwork = true, fromSwipe = true) }
        }

        val scroll = ScrollView(context).apply {
            isFillViewport = true
        }
        val scrollBody = LinearLayout(context).apply {
            orientation = VERTICAL
        }
        gridContainer = LinearLayout(context).apply {
            orientation = VERTICAL
        }
        scrollBody.addView(gridContainer, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        txtMonthSummary = TextView(context).apply {
            setTextColor(Color.parseColor("#CBD5E1"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)
            gravity = Gravity.CENTER
            background = UiStyleHelper.roundedBg(context, "#182332", "#2A394A", 10f)
            setPadding(dp(10), dp(9), dp(10), dp(9))
            visibility = View.GONE
        }
        scrollBody.addView(
            txtMonthSummary,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(8)
                bottomMargin = dp(6)
            }
        )

        scroll.addView(scrollBody, FrameLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        swipeRefresh.addView(scroll)
        addView(swipeRefresh, LayoutParams(LayoutParams.MATCH_PARENT, 0, 1f))
    }

    override fun dispatchTouchEvent(ev: MotionEvent): Boolean {
        when (ev.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                swipeDownX = ev.x
                swipeDownY = ev.y
            }
            MotionEvent.ACTION_UP -> {
                val dx = ev.x - swipeDownX
                val dy = ev.y - swipeDownY
                if (abs(dx) > dp(64) && abs(dx) > abs(dy) * 1.8f) {
                    val cancelEv = MotionEvent.obtain(ev)
                    cancelEv.action = MotionEvent.ACTION_CANCEL
                    super.dispatchTouchEvent(cancelEv)
                    cancelEv.recycle()

                    displayedMonth = if (dx < 0f) displayedMonth.plusMonths(1) else displayedMonth.minusMonths(1)
                    loadMonth(forceNetwork = true, fromSwipe = false)
                    return true
                }
            }
        }
        return super.dispatchTouchEvent(ev)
    }

    fun onShow(forceNetwork: Boolean = false) {
        updateLocalizedLabels()
        loadMonth(forceNetwork = forceNetwork, fromSwipe = false)
    }

    fun refreshFromCacheAndNetwork() {
        updateLocalizedLabels()
        loadMonth(forceNetwork = true, fromSwipe = false)
    }

    private fun updateLocalizedLabels() {
        val en = DemoModeHelper.isEnglish(context)
        val monthName = (if (en) enMonths else fiMonths)[displayedMonth.monthValue - 1]
        txtMonthTitle.text = "$monthName ${displayedMonth.year} ▾"
        btnToday.text = if (en) "Today" else "Tänään"
        btnRefresh.text = if (en) "↻ Refresh" else "↻ Päivitä"
    }

    private fun loadMonth(forceNetwork: Boolean, fromSwipe: Boolean = false) {
        val ym = displayedMonth
        val en = DemoModeHelper.isEnglish(context)
        updateLocalizedLabels()
        loadJob?.cancel()

        if (DemoModeHelper.isDemoEnabled(context)) {
            swipeRefresh.isRefreshing = false
            progressBar.visibility = View.GONE
            txtStatus.text = "Demo"
            val demoShifts = DemoModeHelper.generateDemoWorkShifts(context)
            currentData = NumeronApiClient.buildMonthDisplayFromCachedShifts(demoShifts, ym.year, ym.monthValue)
                ?: MonthDisplayData(ym.year, ym.monthValue, emptyMap())
            renderCalendarGrid()
            return
        }

        // 1. Näytetään heti välimuistista (0 ms viive)
        val cachedMonth = NumeronApiClient.loadMonthDisplayCache(context, ym.year, ym.monthValue)
        val cachedAtMs = NumeronApiClient.getMonthCacheSavedAtMs(context, ym.year, ym.monthValue)
        val fallbackCached = if (cachedMonth == null) {
            CalendarSyncHelper.loadCachedShifts(context)?.let {
                NumeronApiClient.buildMonthDisplayFromCachedShifts(it, ym.year, ym.monthValue)
            }
        } else {
            null
        }

        currentData = cachedMonth ?: fallbackCached ?: MonthDisplayData(ym.year, ym.monthValue, emptyMap())
        renderCalendarGrid()

        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) {
            swipeRefresh.isRefreshing = false
            progressBar.visibility = View.GONE
            txtStatus.text = if (en) "Set organization in Settings" else "Aseta organisaatio asetuksista"
            return
        }

        if (!fromSwipe) {
            progressBar.visibility = View.VISIBLE
        }
        txtStatus.text = if (!forceNetwork && cachedMonth != null) {
            if (en) "Updating…" else "Päivitetään…"
        } else {
            if (en) "Loading…" else "Ladataan…"
        }

        loadJob = scope.launch {
            val html = NumeronApiClient.fetchMonthCalendarHtml(context, ym.year, ym.monthValue)
            if (ym != displayedMonth) return@launch

            swipeRefresh.isRefreshing = false
            progressBar.visibility = View.GONE
            if (html != null) {
                val parsed = withContext(Dispatchers.Default) {
                    NumeronParser.parseMonthForDisplay(html)
                }
                if (parsed != null) {
                    withContext(Dispatchers.IO) {
                        NumeronApiClient.saveMonthDisplayCache(context, parsed)
                    }
                    currentData = parsed
                    txtStatus.text = UiStyleHelper.formatUpdatedLabel(context, System.currentTimeMillis(), isCache = false)
                    renderCalendarGrid()
                    return@launch
                }
            }

            txtStatus.text = if (cachedMonth != null || fallbackCached != null) {
                UiStyleHelper.formatUpdatedLabel(context, cachedAtMs, isCache = true)
                    .ifEmpty { if (en) "Offline cache" else "Välimuisti" }
            } else {
                if (en) "Could not load" else "Lataus epäonnistui"
            }
        }
    }

    private fun resolvePeriodAnchorMonday(): LocalDate {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val raw = prefs.getString("shift_period_anchor_iso", "2026-12-28").orEmpty().trim()
        val parsed = try {
            LocalDate.parse(raw)
        } catch (_: Exception) {
            LocalDate.of(2026, 12, 28)
        }
        return parsed.with(DayOfWeek.MONDAY)
    }

    private fun renderCalendarGrid() {
        gridContainer.removeAllViews()
        val en = DemoModeHelper.isEnglish(context)
        val ym = displayedMonth
        val today = LocalDate.now()
        val dayMap = currentData?.days.orEmpty()

        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val morningRgb = prefs.getInt("color_morning_rgb", SettingsDialogHelper.DEFAULT_MORNING_RGB)
        val eveningRgb = prefs.getInt("color_evening_rgb", SettingsDialogHelper.DEFAULT_EVENING_RGB)
        val nightRgb = prefs.getInt("color_night_rgb", SettingsDialogHelper.DEFAULT_NIGHT_RGB)
        val showShiftPeriods = prefs.getBoolean("show_shift_periods", true)
        val periodDays = 21L
        val anchorMonday = resolvePeriodAnchorMonday()
        val shortDateFmt = DateTimeFormatter.ofPattern("d.M.")

        // Otsikkorivi: Vko + Ma..Su
        val headerRow = LinearLayout(context).apply {
            orientation = HORIZONTAL
        }
        val dayHeaders = if (en) {
            arrayOf("Wk", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        } else {
            arrayOf("Vko", "Ma", "Ti", "Ke", "To", "Pe", "La", "Su")
        }
        for (i in dayHeaders.indices) {
            val isWeekendHeader = (i == 6 || i == 7)
            val tv = TextView(context).apply {
                text = dayHeaders[i]
                gravity = Gravity.CENTER
                setTextColor(Color.parseColor(if (isWeekendHeader) "#93C5FD" else "#CBD5E1"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, if (i == 0) 10f else 11.5f)
                setTypeface(null, Typeface.BOLD)
                background = UiStyleHelper.cellBg(context, if (isWeekendHeader) "#1E2B3D" else "#233040", "#2A394A")
                setPadding(dp(1), dp(6), dp(1), dp(6))
            }
            val lp = if (i == 0) LayoutParams(dp(26), LayoutParams.WRAP_CONTENT) else LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f)
            headerRow.addView(tv, lp)
        }
        gridContainer.addView(headerRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        val firstOfMonth = ym.atDay(1)
        val lastOfMonth = ym.atEndOfMonth()
        val startMonday = firstOfMonth.with(DayOfWeek.MONDAY)
        val endSunday = lastOfMonth.with(DayOfWeek.SUNDAY)

        var weekStart = startMonday
        val weekFields = WeekFields.ISO

        // Kuukausikoosteen laskurit
        var shiftCount = 0
        var totalMinutes = 0
        var morningCount = 0
        var eveningCount = 0
        var nightCount = 0

        while (!weekStart.isAfter(endSunday)) {
            val daysFromAnchor = ChronoUnit.DAYS.between(anchorMonday, weekStart)
            val periodIdx = Math.floorDiv(daysFromAnchor, periodDays)
            val periodStart = anchorMonday.plusDays(periodIdx * periodDays)
            val periodEnd = periodStart.plusDays(periodDays - 1L)
            val isPeriodStartRow = (weekStart == periodStart)
            val periodAccentHex = if (abs(periodIdx) % 2L == 0L) "#38BDF8" else "#F59E0B"

            // 3 viikon työvuorolistajakson raja (ei listanumeroa, ei viikkonumerointia 1/3)
            if (showShiftPeriods && (isPeriodStartRow || weekStart == startMonday)) {
                val periodBar = LinearLayout(context).apply {
                    orientation = HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    background = UiStyleHelper.cellBg(
                        context = context,
                        fillHex = if (isPeriodStartRow) "#162436" else "#121B28",
                        strokeHex = "#2A394A",
                        leftAccentHex = periodAccentHex
                    )
                    setPadding(dp(8), dp(3), dp(8), dp(3))
                }
                val labelPrefix = if (en) "Period" else "Työvuorolista"
                val rangeText = "${periodStart.format(shortDateFmt)}–${periodEnd.format(shortDateFmt)}"
                val pTv = TextView(context).apply {
                    text = "$labelPrefix $rangeText"
                    setTextColor(Color.parseColor(if (isPeriodStartRow) periodAccentHex else "#94A3B8"))
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 10.5f)
                    setTypeface(null, if (isPeriodStartRow) Typeface.BOLD else Typeface.NORMAL)
                }
                periodBar.addView(pTv, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
                gridContainer.addView(periodBar, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
            }

            val row = LinearLayout(context).apply {
                orientation = HORIZONTAL
                minimumHeight = dp(72)
            }

            // Viikkonumero (vain tavallinen kalenteriviikko + jakson vasen värikorostusreuna)
            val weekNum = weekStart.get(weekFields.weekOfWeekBasedYear())
            val wkTv = TextView(context).apply {
                text = weekNum.toString()
                gravity = Gravity.TOP or Gravity.CENTER_HORIZONTAL
                setTextColor(Color.parseColor("#64748B"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 10f)
                background = UiStyleHelper.cellBg(
                    context = context,
                    fillHex = "#131C28",
                    strokeHex = "#2A394A",
                    leftAccentHex = if (showShiftPeriods) periodAccentHex else null
                )
                setPadding(dp(3), dp(5), dp(1), dp(4))
            }
            row.addView(wkTv, LayoutParams(dp(26), LayoutParams.MATCH_PARENT))

            for (offset in 0..6) {
                val date = weekStart.plusDays(offset.toLong())
                val isCurrentMonth = (date.monthValue == ym.monthValue && date.year == ym.year)
                val isToday = (date == today)
                val isPast = date.isBefore(today)
                val isWeekend = (offset == 5 || offset == 6)
                val dayData = dayMap[date]

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
                    isToday -> "#1E3A5F"
                    !isCurrentMonth -> "#101720"
                    isPast -> if (isWeekend) "#111924" else "#121A24"
                    isWeekend -> "#15202E"
                    else -> "#182332"
                }
                val cellBorderColor = if (isToday) "#38BDF8" else "#2A394A"

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
                        setOnClickListener { showDayDetailsDialog(date, dayData) }
                    }
                }

                // Päivänumero + kommenttipallukka
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
                            isWeekend -> Color.parseColor("#93C5FD")
                            else -> Color.parseColor("#F1F5F9")
                        }
                    )
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)
                    setTypeface(null, Typeface.BOLD)
                    setPadding(dp(2), 0, 0, dp(1))
                }
                topRow.addView(numTv, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))

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

                // Poissaolot (yhtenäiset lomapalkit peräkkäisille päiville)
                val prevDate = date.minusDays(1)
                val nextDate = date.plusDays(1)
                val prevAbsences = if (offset > 0) dayMap[prevDate]?.absences.orEmpty() else emptyList()
                val nextAbsences = if (offset < 6) dayMap[nextDate]?.absences.orEmpty() else emptyList()

                dayData?.absences?.forEach { absItem ->
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

                // Työvuorot asetusten värikoodeilla
                dayData?.shifts?.forEach { shift ->
                    val bgRgb = pickShiftRgb(shift, morningRgb, eveningRgb, nightRgb)
                    val fgColor = contrastColor(bgRgb)
                    val label = "${shift.startText}\n${shift.endText}"
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
            }

            gridContainer.addView(row, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
            weekStart = weekStart.plusWeeks(1)
        }

        // Kuukauden pikakooste
        if (shiftCount > 0) {
            val hours = totalMinutes / 60.0
            val hoursStr = if (totalMinutes % 60 == 0) {
                "${totalMinutes / 60}"
            } else {
                String.format("%.1f", hours).replace(".", if (en) "." else ",")
            }
            val breakdownParts = mutableListOf<String>()
            if (morningCount > 0) breakdownParts.add(if (en) "$morningCount morn" else "$morningCount aamu")
            if (eveningCount > 0) breakdownParts.add(if (en) "$eveningCount eve" else "$eveningCount ilta")
            if (nightCount > 0) breakdownParts.add(if (en) "$nightCount night" else "$nightCount yö")

            val shiftWord = if (en) {
                if (shiftCount == 1) "shift" else "shifts"
            } else {
                if (shiftCount == 1) "vuoro" else "vuoroa"
            }
            val breakdownSuffix = if (breakdownParts.isNotEmpty()) "  •  ${breakdownParts.joinToString(" / ")}" else ""
            txtMonthSummary.text = "$shiftCount $shiftWord • $hoursStr h$breakdownSuffix"
            txtMonthSummary.visibility = View.VISIBLE
        } else {
            txtMonthSummary.visibility = View.GONE
        }
    }

    private fun showDayDetailsDialog(date: LocalDate, dayData: CalendarDisplayDay?) {
        val en = DemoModeHelper.isEnglish(context)
        val fiWeekdays = arrayOf("Ma", "Ti", "Ke", "To", "Pe", "La", "Su")
        val enWeekdays = arrayOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        val dowStr = (if (en) enWeekdays else fiWeekdays)[date.dayOfWeek.value - 1]
        val dateStr = date.format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))

        val root = LinearLayout(context).apply {
            orientation = VERTICAL
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(18), dp(16), dp(18), dp(14))
        }

        val titleTv = TextView(context).apply {
            text = "$dowStr $dateStr"
            setTextColor(Color.parseColor("#F1F5F9"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
            setTypeface(null, Typeface.BOLD)
        }
        root.addView(titleTv)

        val contentBox = LinearLayout(context).apply {
            orientation = VERTICAL
            setPadding(0, dp(10), 0, dp(10))
        }

        var hasAny = false
        dayData?.shifts?.forEach { shift ->
            hasAny = true
            val card = LinearLayout(context).apply {
                orientation = VERTICAL
                background = UiStyleHelper.roundedBg(context, "#111923", "#2A394A", 10f)
                setPadding(dp(12), dp(10), dp(12), dp(10))
            }
            card.addView(
                TextView(context).apply {
                    text = "${shift.startText} – ${shift.endText}"
                    setTextColor(Color.parseColor("#38BDF8"))
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
                    setTypeface(null, Typeface.BOLD)
                }
            )
            if (shift.location.isNotEmpty()) {
                card.addView(
                    TextView(context).apply {
                        text = shift.location
                        setTextColor(Color.parseColor("#F1F5F9"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
                        setTypeface(null, Typeface.BOLD)
                        setPadding(0, dp(2), 0, 0)
                    }
                )
            }
            val sub = listOf(shift.shiftName, shift.role).filter { it.isNotBlank() }.joinToString(" • ")
            if (sub.isNotEmpty()) {
                card.addView(
                    TextView(context).apply {
                        text = sub
                        setTextColor(Color.parseColor("#CBD5E1"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
                        setPadding(0, dp(2), 0, 0)
                    }
                )
            }
            contentBox.addView(
                card,
                LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                    bottomMargin = dp(8)
                }
            )
        }

        dayData?.absences?.forEach { absItem ->
            hasAny = true
            val borderHex = when (absItem.kind) {
                "vacation" -> "#22C55E"
                "sick" -> "#F87171"
                else -> "#64748B"
            }
            val tv = TextView(context).apply {
                text = absItem.title
                setTextColor(Color.parseColor("#F1F5F9"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
                setTypeface(null, Typeface.BOLD)
                background = UiStyleHelper.roundedBg(context, "#111923", borderHex, 8f)
                setPadding(dp(12), dp(9), dp(12), dp(9))
            }
            contentBox.addView(
                tv,
                LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                    bottomMargin = dp(8)
                }
            )
        }

        dayData?.requests?.forEach { req ->
            hasAny = true
            val tv = TextView(context).apply {
                text = (if (en) "Request: " else "Toive: ") + req.title
                setTextColor(Color.parseColor("#EDE9FE"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)
                background = UiStyleHelper.roundedBg(context, "#2E1F47", "#8B5CF6", 8f)
                setPadding(dp(12), dp(9), dp(12), dp(9))
            }
            contentBox.addView(
                tv,
                LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                    bottomMargin = dp(8)
                }
            )
        }

        if (!hasAny) {
            contentBox.addView(
                TextView(context).apply {
                    text = if (en) "No scheduled shifts" else "Ei merkittyjä vuoroja"
                    setTextColor(Color.parseColor("#94A3B8"))
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
                }
            )
        }

        val commentTv = TextView(context).apply {
            setTextColor(Color.parseColor("#FDE68A"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            background = UiStyleHelper.roundedBg(context, "#2A2210", "#F59E0B", 8f)
            setPadding(dp(10), dp(8), dp(10), dp(8))
            visibility = if (dayData?.hasCommentCircle == true && !DemoModeHelper.isDemoEnabled(context)) View.VISIBLE else View.GONE
            text = if (en) "Loading shift comment..." else "Haetaan vuorokommenttia..."
        }
        contentBox.addView(
            commentTv,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(8)
            }
        )

        root.addView(contentBox)

        val dialog = AlertDialog.Builder(context)
            .setView(root)
            .create()

        if (!DemoModeHelper.isDemoEnabled(context)) {
            val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
            val btnRow = LinearLayout(context).apply {
                orientation = HORIZONTAL
            }
            val isoDate = date.toString()
            val listDateParam = URLEncoder.encode("${date.monthValue}/${date.dayOfMonth}/${date.year} 00:00:00", "UTF-8")

            val btnAddReq = Button(context).apply {
                text = if (en) "+ Add Request" else "+ Lisää toive"
                isAllCaps = false
                setTextColor(Color.WHITE)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)
                setTypeface(null, Typeface.BOLD)
                background = UiStyleHelper.rippleRoundedBg(context, "#1982C4", "#38BDF8", 8f, "#44FFFFFF")
                setOnClickListener {
                    dialog.dismiss()
                    if (baseUrl.isNotBlank()) {
                        onOpenWebUrl(
                            "$baseUrl/PersonRequests/Edit?calendarView=Month&returnValue=$isoDate",
                            if (en) "New request ($dateStr)" else "Uusi toive ($dateStr)"
                        )
                    }
                }
            }
            btnRow.addView(
                btnAddReq,
                LayoutParams(0, dp(40), 1f).apply {
                    marginEnd = dp(8)
                }
            )

            val btnOpenDay = Button(context).apply {
                text = if (en) "Open day" else "Avaa päivä"
                isAllCaps = false
                setTextColor(Color.parseColor("#E2E8F0"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)
                background = UiStyleHelper.rippleRoundedBg(context, "#233040", "#37475A", 8f)
                setOnClickListener {
                    dialog.dismiss()
                    if (baseUrl.isNotBlank()) {
                        onOpenWebUrl(
                            "$baseUrl/Calendar/List?date=$listDateParam",
                            dateStr
                        )
                    }
                }
            }
            btnRow.addView(btnOpenDay, LayoutParams(0, dp(40), 1f))
            root.addView(btnRow)

            if (dayData?.hasCommentCircle == true && baseUrl.isNotBlank()) {
                scope.launch {
                    val comment = withContext(Dispatchers.IO) {
                        val cookies = try {
                            CookieManager.getInstance().getCookie(baseUrl)
                        } catch (_: Exception) {
                            null
                        }
                        NumeronParser.fetchDayComments(baseUrl, cookies, date)
                    }
                    if (dialog.isShowing) {
                        if (!comment.isNullOrBlank()) {
                            commentTv.text = (if (en) "Note: " else "Huomio: ") + comment
                            commentTv.visibility = View.VISIBLE
                        } else {
                            commentTv.visibility = View.GONE
                        }
                    }
                }
            }
        }

        val btnClose = Button(context).apply {
            text = if (en) "Close" else "Sulje"
            isAllCaps = false
            setTextColor(Color.parseColor("#CBD5E1"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            background = UiStyleHelper.rippleRoundedBg(context, "#233040", "#37475A", 8f)
            setOnClickListener { dialog.dismiss() }
        }
        root.addView(
            btnClose,
            LayoutParams(LayoutParams.MATCH_PARENT, dp(38)).apply {
                topMargin = dp(8)
            }
        )

        dialog.window?.setBackgroundDrawable(UiStyleHelper.roundedBg(context, "#182332", "#38BDF8", 14f))
        dialog.show()
    }

    private fun showMonthJumpDialog() {
        val en = DemoModeHelper.isEnglish(context)
        val shortNames = if (en) enShortMonths else fiShortMonths
        var selectedYear = displayedMonth.year
        val realNow = YearMonth.now()

        val root = LinearLayout(context).apply {
            orientation = VERTICAL
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(16), dp(16), dp(16), dp(14))
        }

        root.addView(
            TextView(context).apply {
                text = if (en) "JUMP TO MONTH & YEAR" else "SIIRRY KUUKAUTEEN JA VUOTEEN"
                setTextColor(Color.parseColor("#38BDF8"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
                setTypeface(null, Typeface.BOLD)
                gravity = Gravity.CENTER
                setPadding(0, 0, 0, dp(10))
            }
        )

        val yearRow = LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = UiStyleHelper.roundedBg(context, "#111923", "#2A394A", 10f)
            setPadding(dp(8), dp(6), dp(8), dp(6))
        }

        val yearLabel = TextView(context).apply {
            text = selectedYear.toString()
            setTextColor(Color.parseColor("#F1F5F9"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
            setTypeface(null, Typeface.BOLD)
            gravity = Gravity.CENTER
        }

        val gridHost = LinearLayout(context).apply {
            orientation = VERTICAL
            setPadding(0, dp(12), 0, dp(12))
        }

        val dialog = AlertDialog.Builder(context)
            .setView(root)
            .create()

        fun renderMonths() {
            yearLabel.text = selectedYear.toString()
            gridHost.removeAllViews()
            for (r in 0..3) {
                val mRow = LinearLayout(context).apply {
                    orientation = HORIZONTAL
                }
                for (c in 0..2) {
                    val mVal = r * 3 + c + 1
                    val isSelected = (selectedYear == displayedMonth.year && mVal == displayedMonth.monthValue)
                    val isCurrent = (selectedYear == realNow.year && mVal == realNow.monthValue)
                    val bgHex = if (isSelected) "#1982C4" else "#111923"
                    val borderHex = if (isSelected || isCurrent) "#38BDF8" else "#2A394A"
                    val btn = Button(context).apply {
                        text = shortNames[mVal - 1]
                        isAllCaps = false
                        setTextColor(if (isSelected) Color.WHITE else Color.parseColor("#E2E8F0"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
                        setTypeface(null, Typeface.BOLD)
                        background = UiStyleHelper.rippleRoundedBg(context, bgHex, borderHex, 8f)
                        setOnClickListener {
                            dialog.dismiss()
                            displayedMonth = YearMonth.of(selectedYear, mVal)
                            loadMonth(forceNetwork = true, fromSwipe = false)
                        }
                    }
                    mRow.addView(
                        btn,
                        LayoutParams(0, dp(40), 1f).apply {
                            setMargins(dp(3), dp(3), dp(3), dp(3))
                        }
                    )
                }
                gridHost.addView(mRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
            }
        }

        val btnPrevYear = Button(context).apply {
            text = "◀"
            setTextColor(Color.parseColor("#38BDF8"))
            background = UiStyleHelper.rippleRoundedBg(context, "#233040", "#37475A", 8f)
            setOnClickListener {
                selectedYear -= 1
                renderMonths()
            }
        }
        val btnNextYear = Button(context).apply {
            text = "▶"
            setTextColor(Color.parseColor("#38BDF8"))
            background = UiStyleHelper.rippleRoundedBg(context, "#233040", "#37475A", 8f)
            setOnClickListener {
                selectedYear += 1
                renderMonths()
            }
        }

        yearRow.addView(btnPrevYear, LayoutParams(dp(42), dp(36)))
        yearRow.addView(yearLabel, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))
        yearRow.addView(btnNextYear, LayoutParams(dp(42), dp(36)))

        root.addView(yearRow)
        root.addView(gridHost)

        val footer = LinearLayout(context).apply {
            orientation = HORIZONTAL
        }
        val btnNow = Button(context).apply {
            text = if (en) "Current month" else "Nykyinen kuukausi"
            isAllCaps = false
            setTextColor(Color.parseColor("#38BDF8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            background = UiStyleHelper.rippleRoundedBg(context, "#233040", "#37475A", 8f)
            setOnClickListener {
                dialog.dismiss()
                displayedMonth = YearMonth.now()
                loadMonth(forceNetwork = true, fromSwipe = false)
            }
        }
        val btnCancel = Button(context).apply {
            text = if (en) "Cancel" else "Peruuta"
            isAllCaps = false
            setTextColor(Color.parseColor("#CBD5E1"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            background = UiStyleHelper.rippleRoundedBg(context, "#233040", "#37475A", 8f)
            setOnClickListener { dialog.dismiss() }
        }
        footer.addView(btnNow, LayoutParams(0, dp(38), 1f).apply { marginEnd = dp(8) })
        footer.addView(btnCancel, LayoutParams(0, dp(38), 1f))
        root.addView(footer)

        renderMonths()
        dialog.window?.setBackgroundDrawable(UiStyleHelper.roundedBg(context, "#182332", "#38BDF8", 14f))
        dialog.show()
    }

    private fun pickShiftRgb(
        shift: CalendarDisplayShift,
        morningRgb: Int,
        eveningRgb: Int,
        nightRgb: Int
    ): Int {
        val crossesMidnight = shift.endMinutes < shift.startMinutes
        return when {
            crossesMidnight || shift.startMinutes >= 20 * 60 || shift.startMinutes < 4 * 60 -> nightRgb
            shift.startMinutes >= 11 * 60 + 30 -> eveningRgb
            else -> morningRgb
        }
    }

    private fun contrastColor(rgb: Int): Int {
        val lum = 0.299 * Color.red(rgb) + 0.587 * Color.green(rgb) + 0.114 * Color.blue(rgb)
        return if (lum > 150.0) Color.parseColor("#0F1722") else Color.WHITE
    }

    private fun dp(value: Int): Int = UiStyleHelper.dp(context, value)
}
