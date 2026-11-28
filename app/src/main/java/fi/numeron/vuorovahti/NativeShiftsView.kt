package fi.numeron.vuorovahti

import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.provider.AlarmClock
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.URLEncoder
import java.time.DayOfWeek
import java.time.Duration
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
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
    private var adjacentDayMap: Map<LocalDate, CalendarDisplayDay> = emptyMap()
    private var loadJob: Job? = null
    private var prefetchJob: Job? = null
    private var lastSessionEpoch: Long = -1L
    private var lastRenderedRenderKey: String? = null
    private var lastRenderedData: MonthDisplayData? = null
    private var lastRenderedAdjacentSize: Int = -1
    private val memoryMonths = LinkedHashMap<YearMonth, Pair<MonthDisplayData, Long>>()

    private var swipeDownX: Float = 0f
    private var swipeDownY: Float = 0f

    private val headerCard: LinearLayout
    private val swipeRefresh: SwipeRefreshLayout
    private val txtMonthTitle: TextView
    private val btnPrev: Button
    private val btnNext: Button
    private val btnToday: Button
    private val btnRefresh: Button
    private val btnShare: Button
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
        setPadding(dp(8), dp(8), dp(8), dp(4))

        // Yläkortti: kuukausivalitsin + pikapainikkeet
        headerCard = LinearLayout(context).apply {
            orientation = VERTICAL
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
            setPadding(0, 0, 0, 0)
            setOnClickListener {
                displayedMonth = displayedMonth.minusMonths(1)
                animateMonthSlide(-1)
                loadMonth(forceNetwork = false, fromSwipe = false)
            }
        }
        navRow.addView(btnPrev, LayoutParams(dp(44), dp(38)))

        txtMonthTitle = TextView(context).apply {
            setTextColor(Color.parseColor("#F1F5F9"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
            setTypeface(null, Typeface.BOLD)
            gravity = Gravity.CENTER
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
            setPadding(0, 0, 0, 0)
            setOnClickListener {
                displayedMonth = displayedMonth.plusMonths(1)
                animateMonthSlide(1)
                loadMonth(forceNetwork = false, fromSwipe = false)
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
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setPadding(dp(10), dp(4), dp(10), dp(4))
            minHeight = 0
            minimumHeight = dp(32)
            setOnClickListener {
                displayedMonth = YearMonth.now()
                loadMonth(forceNetwork = false, fromSwipe = false)
            }
        }
        actionRow.addView(btnToday, LayoutParams(LayoutParams.WRAP_CONTENT, dp(32)))

        btnRefresh = Button(context).apply {
            isAllCaps = false
            setTextColor(Color.parseColor("#38BDF8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setPadding(dp(10), dp(4), dp(10), dp(4))
            minHeight = 0
            minimumHeight = dp(32)
            setOnClickListener { loadMonth(forceNetwork = true, fromSwipe = false) }
        }
        actionRow.addView(
            btnRefresh,
            LayoutParams(LayoutParams.WRAP_CONTENT, dp(32)).apply {
                marginStart = dp(6)
            }
        )

        btnShare = Button(context).apply {
            isAllCaps = false
            setTextColor(Color.parseColor("#E2E8F0"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setPadding(dp(10), dp(4), dp(10), dp(4))
            minHeight = 0
            minimumHeight = dp(32)
            setOnClickListener { openShareMenu() }
        }
        actionRow.addView(
            btnShare,
            LayoutParams(LayoutParams.WRAP_CONTENT, dp(32)).apply {
                marginStart = dp(6)
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
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 11f)
            setPadding(dp(5), 0, 0, 0)
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

        applyThemeColors()
    }

    fun applyThemeColors() {
        val bg = UiStyleHelper.bgHex(context)
        val card = UiStyleHelper.cardHex(context)
        val cardAlt = UiStyleHelper.cardAltHex(context)
        val headerBtn = UiStyleHelper.headerCellHex(context)
        val border = UiStyleHelper.borderHex(context)
        val borderStrong = UiStyleHelper.borderStrongHex(context)

        setBackgroundColor(Color.parseColor(bg))
        UiStyleHelper.configureSwipeRefresh(swipeRefresh)
        headerCard.background = UiStyleHelper.roundedBg(context, card, border, 12f)
        btnPrev.background = UiStyleHelper.rippleRoundedBg(context, headerBtn, borderStrong, 10f)
        btnNext.background = UiStyleHelper.rippleRoundedBg(context, headerBtn, borderStrong, 10f)
        txtMonthTitle.background = UiStyleHelper.rippleRoundedBg(context, cardAlt, border, 10f)
        btnToday.background = UiStyleHelper.rippleRoundedBg(context, headerBtn, borderStrong, 8f)
        btnRefresh.background = UiStyleHelper.rippleRoundedBg(context, headerBtn, borderStrong, 8f)
        btnShare.background = UiStyleHelper.rippleRoundedBg(context, headerBtn, borderStrong, 8f)
        txtMonthSummary.background = UiStyleHelper.roundedBg(context, card, border, 10f)
    }

    private fun animateMonthSlide(direction: Int) {
        gridContainer.animate().cancel()
        val shift = dp(24).toFloat() * direction
        gridContainer.translationX = shift
        gridContainer.alpha = 0.35f
        gridContainer.animate()
            .translationX(0f)
            .alpha(1f)
            .setDuration(150L)
            .start()
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

                    val dir = if (dx < 0f) 1 else -1
                    displayedMonth = if (dir > 0) displayedMonth.plusMonths(1) else displayedMonth.minusMonths(1)
                    animateMonthSlide(dir)
                    loadMonth(forceNetwork = false, fromSwipe = false)
                    return true
                }
            }
        }
        return super.dispatchTouchEvent(ev)
    }

    fun onShow(forceNetwork: Boolean = false) {
        applyThemeColors()
        updateLocalizedLabels()
        loadMonth(forceNetwork = forceNetwork, fromSwipe = false)
    }

    fun refreshFromCacheAndNetwork() {
        applyThemeColors()
        updateLocalizedLabels()
        loadMonth(forceNetwork = true, fromSwipe = false)
    }

    private fun updateLocalizedLabels() {
        val en = DemoModeHelper.isEnglish(context)
        val monthName = (if (en) enMonths else fiMonths)[displayedMonth.monthValue - 1]
        txtMonthTitle.text = "$monthName ${displayedMonth.year} ▾"
        btnToday.text = if (en) "Today" else "Tänään"
        btnRefresh.text = if (en) "↻" else "↻"
        btnShare.text = if (en) "↗ Share" else "↗ Jaa"
    }

    private fun buildCombinedDayMap(): Map<LocalDate, CalendarDisplayDay> {
        val combined = LinkedHashMap<LocalDate, CalendarDisplayDay>(adjacentDayMap.size + (currentData?.days?.size ?: 0))
        combined.putAll(adjacentDayMap)
        currentData?.days?.let { combined.putAll(it) }
        return combined
    }

    private fun loadAdjacentMonthsCacheSync(ym: YearMonth): Map<LocalDate, CalendarDisplayDay> {
        val map = LinkedHashMap<LocalDate, CalendarDisplayDay>()
        val prevYm = ym.minusMonths(1)
        val nextYm = ym.plusMonths(1)
        if (DemoModeHelper.isDemoEnabled(context)) {
            val demoShifts = DemoModeHelper.generateDemoWorkShifts(context)
            NumeronApiClient.buildMonthDisplayFromCachedShifts(demoShifts, prevYm.year, prevYm.monthValue)?.days?.let { map.putAll(it) }
            NumeronApiClient.buildMonthDisplayFromCachedShifts(demoShifts, nextYm.year, nextYm.monthValue)?.days?.let { map.putAll(it) }
            return map
        }
        val cachedShifts = CalendarSyncHelper.loadCachedShifts(context)
        for (adjYm in listOf(prevYm, nextYm)) {
            val mem = memoryMonths[adjYm]?.first
            val disk = mem ?: NumeronApiClient.loadMonthDisplayCache(context, adjYm.year, adjYm.monthValue)
            val data = disk ?: cachedShifts?.let {
                NumeronApiClient.buildMonthDisplayFromCachedShifts(it, adjYm.year, adjYm.monthValue)
            }
            data?.days?.let { map.putAll(it) }
        }
        return map
    }

    private fun buildRenderKey(): String {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val en = DemoModeHelper.isEnglish(context)
        val isDemo = DemoModeHelper.isDemoEnabled(context)
        val amoled = UiStyleHelper.isAmoled(context)
        val morningRgb = prefs.getInt("color_morning_rgb", SettingsDialogHelper.DEFAULT_MORNING_RGB)
        val eveningRgb = prefs.getInt("color_evening_rgb", SettingsDialogHelper.DEFAULT_EVENING_RGB)
        val nightRgb = prefs.getInt("color_night_rgb", SettingsDialogHelper.DEFAULT_NIGHT_RGB)
        val showPeriods = prefs.getBoolean("show_shift_periods", true)
        val showHolidays = prefs.getBoolean("show_finnish_holidays", true)
        val showShortRest = prefs.getBoolean("show_short_rest_warning", true)
        val anchor = prefs.getString("shift_period_anchor_iso", "2026-12-28").orEmpty()
        return "$displayedMonth|$en|$isDemo|$amoled|$morningRgb|$eveningRgb|$nightRgb|$showPeriods|$showHolidays|$showShortRest|$anchor|${LocalDate.now()}"
    }

    private fun renderCalendarGridIfChanged(forceRender: Boolean = false) {
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
    }

    private fun storeMemoryMonth(ym: YearMonth, data: MonthDisplayData, fetchedAtMs: Long) {
        memoryMonths.remove(ym)
        memoryMonths[ym] = data to fetchedAtMs
        if (memoryMonths.size > 12) {
            val oldest = memoryMonths.keys.firstOrNull()
            if (oldest != null) memoryMonths.remove(oldest)
        }
    }

    private fun scheduleNextMonthPrefetch(baseYm: YearMonth) {
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
                    adjacentDayMap = withContext(Dispatchers.IO) { loadAdjacentMonthsCacheSync(baseYm) }
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
            }
            storeMemoryMonth(nextYm, parsed, System.currentTimeMillis())
            if (displayedMonth == baseYm) {
                adjacentDayMap = withContext(Dispatchers.IO) { loadAdjacentMonthsCacheSync(baseYm) }
                renderCalendarGridIfChanged()
            }
        }
    }

    private fun loadMonth(forceNetwork: Boolean, fromSwipe: Boolean = false) {
        val ym = displayedMonth
        val en = DemoModeHelper.isEnglish(context)
        updateLocalizedLabels()
        loadJob?.cancel()

        val epoch = SessionCookieStore.sessionEpoch
        if (epoch != lastSessionEpoch) {
            lastSessionEpoch = epoch
            memoryMonths.clear()
            adjacentDayMap = emptyMap()
            lastRenderedRenderKey = null
            lastRenderedData = null
        }

        if (DemoModeHelper.isDemoEnabled(context)) {
            swipeRefresh.isRefreshing = false
            progressBar.visibility = View.GONE
            txtStatus.text = "Demo"
            val demoShifts = DemoModeHelper.generateDemoWorkShifts(context)
            currentData = NumeronApiClient.buildMonthDisplayFromCachedShifts(demoShifts, ym.year, ym.monthValue)
                ?: MonthDisplayData(ym.year, ym.monthValue, emptyMap())
            adjacentDayMap = loadAdjacentMonthsCacheSync(ym)
            renderCalendarGridIfChanged()
            return
        }

        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) {
            swipeRefresh.isRefreshing = false
            progressBar.visibility = View.GONE
            txtStatus.text = if (en) "Set organization in Settings" else "Aseta organisaatio asetuksista"
            currentData = MonthDisplayData(ym.year, ym.monthValue, emptyMap())
            adjacentDayMap = emptyMap()
            renderCalendarGridIfChanged()
            return
        }

        // 1. Muistivälimuisti + 2 min tuoreusaika
        val memEntry = memoryMonths[ym]
        if (memEntry != null) {
            currentData = memEntry.first
            if (!forceNetwork && (System.currentTimeMillis() - memEntry.second) < 120_000L) {
                swipeRefresh.isRefreshing = false
                progressBar.visibility = View.GONE
                txtStatus.text = UiStyleHelper.formatUpdatedLabel(context, memEntry.second, isCache = false)
                loadJob = scope.launch {
                    adjacentDayMap = withContext(Dispatchers.IO) { loadAdjacentMonthsCacheSync(ym) }
                    if (ym == displayedMonth) {
                        renderCalendarGridIfChanged()
                        scheduleNextMonthPrefetch(ym)
                    }
                }
                return
            }
            renderCalendarGridIfChanged()
        }

        loadJob = scope.launch {
            var cachedMonth: MonthDisplayData? = memEntry?.first
            var cachedAtMs: Long = memEntry?.second ?: 0L
            var hasAnyCache = (cachedMonth != null)

            val diskLoad = withContext(Dispatchers.IO) {
                val adj = loadAdjacentMonthsCacheSync(ym)
                if (cachedMonth == null) {
                    val mCache = NumeronApiClient.loadMonthDisplayCache(context, ym.year, ym.monthValue)
                    val mSaved = NumeronApiClient.getMonthCacheSavedAtMs(context, ym.year, ym.monthValue)
                    val fallback = if (mCache == null) {
                        CalendarSyncHelper.loadCachedShifts(context)?.let {
                            NumeronApiClient.buildMonthDisplayFromCachedShifts(it, ym.year, ym.monthValue)
                        }
                    } else {
                        null
                    }
                    Triple(mCache ?: fallback, mSaved, adj)
                } else {
                    Triple(cachedMonth, cachedAtMs, adj)
                }
            }
            if (ym != displayedMonth) return@launch

            adjacentDayMap = diskLoad.third
            if (cachedMonth == null) {
                cachedMonth = diskLoad.first
                cachedAtMs = diskLoad.second
                hasAnyCache = (cachedMonth != null)
                currentData = cachedMonth ?: MonthDisplayData(ym.year, ym.monthValue, emptyMap())
            }
            renderCalendarGridIfChanged()

            if (!fromSwipe) {
                progressBar.visibility = View.VISIBLE
            }
            txtStatus.text = if (!forceNetwork && hasAnyCache) {
                if (en) "Updating…" else "Päivitetään…"
            } else {
                if (en) "Loading…" else "Ladataan…"
            }

            val html = NumeronApiClient.fetchMonthCalendarHtml(context, ym.year, ym.monthValue)
            if (ym != displayedMonth) return@launch

            swipeRefresh.isRefreshing = false
            progressBar.visibility = View.GONE
            if (html != null) {
                val parsed = withContext(Dispatchers.Default) {
                    NumeronParser.parseMonthForDisplay(html)
                }
                if (parsed != null) {
                    val fetchedAt = System.currentTimeMillis()
                    withContext(Dispatchers.IO) {
                        NumeronApiClient.saveMonthDisplayCache(context, parsed)
                    }
                    storeMemoryMonth(ym, parsed, fetchedAt)
                    currentData = parsed
                    txtStatus.text = UiStyleHelper.formatUpdatedLabel(context, fetchedAt, isCache = false)
                    renderCalendarGridIfChanged()
                    scheduleNextMonthPrefetch(ym)
                    return@launch
                }
            }

            txtStatus.text = if (hasAnyCache) {
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

    private data class PeriodStats(
        val shiftCount: Int,
        val totalMinutes: Int,
        val morningCount: Int,
        val eveningCount: Int,
        val nightCount: Int
    )

    private fun computePeriodStats(
        periodStart: LocalDate,
        periodEnd: LocalDate,
        combinedMap: Map<LocalDate, CalendarDisplayDay>
    ): PeriodStats {
        var count = 0
        var mins = 0
        var morning = 0
        var evening = 0
        var night = 0
        var d = periodStart
        while (!d.isAfter(periodEnd)) {
            val day = combinedMap[d]
            if (day != null) {
                for (shift in day.shifts) {
                    count++
                    val dur = if (shift.endMinutes >= shift.startMinutes) {
                        shift.endMinutes - shift.startMinutes
                    } else {
                        (24 * 60 - shift.startMinutes) + shift.endMinutes
                    }
                    mins += dur
                    val crossesMidnight = shift.endMinutes < shift.startMinutes
                    when {
                        crossesMidnight || shift.startMinutes >= 20 * 60 || shift.startMinutes < 4 * 60 -> night++
                        shift.startMinutes >= 11 * 60 + 30 -> evening++
                        else -> morning++
                    }
                }
            }
            d = d.plusDays(1)
        }
        return PeriodStats(count, mins, morning, evening, night)
    }

    private fun computeShortRestMinutes(
        date: LocalDate,
        combinedMap: Map<LocalDate, CalendarDisplayDay>
    ): Long? {
        val todayShifts = combinedMap[date]?.shifts.orEmpty()
        if (todayShifts.isEmpty()) return null

        val firstToday = todayShifts.minByOrNull { it.startMinutes } ?: return null
        val firstStartDt = LocalDateTime.of(
            date,
            LocalTime.of((firstToday.startMinutes / 60).coerceIn(0, 23), (firstToday.startMinutes % 60).coerceIn(0, 59))
        )

        var latestPrevEnd: LocalDateTime? = null
        val prevDate = date.minusDays(1)
        combinedMap[prevDate]?.shifts?.forEach { prevShift ->
            val endDate = if (prevShift.endMinutes < prevShift.startMinutes) date else prevDate
            val endDt = LocalDateTime.of(
                endDate,
                LocalTime.of((prevShift.endMinutes / 60).coerceIn(0, 23), (prevShift.endMinutes % 60).coerceIn(0, 59))
            )
            if (!endDt.isAfter(firstStartDt) && (latestPrevEnd == null || endDt.isAfter(latestPrevEnd))) {
                latestPrevEnd = endDt
            }
        }

        val prevEnd = latestPrevEnd ?: return null
        val restMins = Duration.between(prevEnd, firstStartDt).toMinutes()
        return if (restMins in 1L..659L) restMins else null
    }

    private fun openShareMenu() {
        val en = DemoModeHelper.isEnglish(context)
        val ym = displayedMonth
        val monthName = (if (en) enMonths else fiMonths)[ym.monthValue - 1]
        val monthTitle = "$monthName ${ym.year}"
        val anchorMonday = resolvePeriodAnchorMonday()
        val refDate = if (YearMonth.now() == ym) LocalDate.now() else ym.atDay(1)
        val refMonday = refDate.with(DayOfWeek.MONDAY)
        val periodIdx = Math.floorDiv(ChronoUnit.DAYS.between(anchorMonday, refMonday), 21L)
        val periodStart = anchorMonday.plusDays(periodIdx * 21L)
        val periodEnd = periodStart.plusDays(20L)

        ScheduleShareHelper.showShareDialog(
            context = context,
            ym = ym,
            monthTitle = monthTitle,
            allDayMap = buildCombinedDayMap(),
            periodStart = periodStart,
            periodEnd = periodEnd
        )
    }

    private fun showPeriodSummaryDialog(
        periodStart: LocalDate,
        periodEnd: LocalDate,
        stats: PeriodStats,
        combinedMap: Map<LocalDate, CalendarDisplayDay>
    ) {
        val en = DemoModeHelper.isEnglish(context)
        val cardBg = UiStyleHelper.cardHex(context)
        val altBg = UiStyleHelper.cardAltHex(context)
        val btnBg = UiStyleHelper.headerCellHex(context)
        val border = UiStyleHelper.borderHex(context)
        val borderStrong = UiStyleHelper.borderStrongHex(context)
        val fmt = DateTimeFormatter.ofPattern("d.M.yyyy")

        val root = LinearLayout(context).apply {
            orientation = VERTICAL
            setBackgroundColor(Color.parseColor(cardBg))
            setPadding(dp(18), dp(16), dp(18), dp(14))
        }

        root.addView(
            TextView(context).apply {
                text = if (en) "3-WEEK SHIFT PERIOD" else "3 VIIKON TYÖVUOROLISTA"
                setTextColor(Color.parseColor("#38BDF8"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)
                setTypeface(null, Typeface.BOLD)
            }
        )
        root.addView(
            TextView(context).apply {
                text = "${periodStart.format(fmt)} – ${periodEnd.format(fmt)}"
                setTextColor(Color.parseColor("#F1F5F9"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
                setTypeface(null, Typeface.BOLD)
                setPadding(0, dp(3), 0, dp(10))
            }
        )

        val summaryBox = LinearLayout(context).apply {
            orientation = VERTICAL
            background = UiStyleHelper.roundedBg(context, altBg, border, 10f)
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }

        if (stats.shiftCount > 0) {
            val hoursStr = ScheduleShareHelper.formatHours(stats.totalMinutes, en)
            val word = if (en) {
                if (stats.shiftCount == 1) "shift" else "shifts"
            } else {
                if (stats.shiftCount == 1) "vuoro" else "vuoroa"
            }
            summaryBox.addView(
                TextView(context).apply {
                    text = "${stats.shiftCount} $word  •  $hoursStr h"
                    setTextColor(Color.WHITE)
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
                    setTypeface(null, Typeface.BOLD)
                }
            )
            val parts = mutableListOf<String>()
            if (stats.morningCount > 0) parts.add(if (en) "${stats.morningCount} morn" else "${stats.morningCount} aamu")
            if (stats.eveningCount > 0) parts.add(if (en) "${stats.eveningCount} eve" else "${stats.eveningCount} ilta")
            if (stats.nightCount > 0) parts.add(if (en) "${stats.nightCount} night" else "${stats.nightCount} yö")
            if (parts.isNotEmpty()) {
                summaryBox.addView(
                    TextView(context).apply {
                        text = parts.joinToString(" / ")
                        setTextColor(Color.parseColor("#CBD5E1"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)
                        setPadding(0, dp(4), 0, 0)
                    }
                )
            }
        } else {
            summaryBox.addView(
                TextView(context).apply {
                    text = if (en) "No shifts loaded for this period yet" else "Ei ladattuja vuoroja tälle jaksolle"
                    setTextColor(Color.parseColor("#94A3B8"))
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)
                }
            )
        }
        root.addView(
            summaryBox,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(12)
            }
        )

        val dialog = AlertDialog.Builder(context)
            .setView(root)
            .create()

        val shareRow = LinearLayout(context).apply {
            orientation = HORIZONTAL
        }
        val btnShareImg = Button(context).apply {
            text = if (en) "🖼 Share PNG" else "🖼 Jaa kuvana"
            isAllCaps = false
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            setTypeface(null, Typeface.BOLD)
            background = UiStyleHelper.rippleRoundedBg(context, "#1982C4", "#38BDF8", 8f, "#44FFFFFF")
            setOnClickListener {
                dialog.dismiss()
                ScheduleShareHelper.sharePeriodDirectly(context, periodStart, periodEnd, combinedMap, asImage = true)
            }
        }
        val btnShareTxt = Button(context).apply {
            text = if (en) "📝 Share text" else "📝 Jaa tekstinä"
            isAllCaps = false
            setTextColor(Color.parseColor("#E2E8F0"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            background = UiStyleHelper.rippleRoundedBg(context, btnBg, borderStrong, 8f)
            setOnClickListener {
                dialog.dismiss()
                ScheduleShareHelper.sharePeriodDirectly(context, periodStart, periodEnd, combinedMap, asImage = false)
            }
        }
        shareRow.addView(btnShareImg, LayoutParams(0, dp(40), 1f).apply { marginEnd = dp(8) })
        shareRow.addView(btnShareTxt, LayoutParams(0, dp(40), 1f))
        root.addView(shareRow)

        val btnClose = Button(context).apply {
            text = if (en) "Close" else "Sulje"
            isAllCaps = false
            setTextColor(Color.parseColor("#CBD5E1"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            background = UiStyleHelper.rippleRoundedBg(context, btnBg, borderStrong, 8f)
            setOnClickListener { dialog.dismiss() }
        }
        root.addView(
            btnClose,
            LayoutParams(LayoutParams.MATCH_PARENT, dp(38)).apply {
                topMargin = dp(8)
            }
        )

        dialog.window?.setBackgroundDrawable(UiStyleHelper.roundedBg(context, cardBg, "#38BDF8", 14f))
        dialog.show()
    }

    private fun renderCalendarGrid() {
        gridContainer.removeAllViews()
        val en = DemoModeHelper.isEnglish(context)
        val ym = displayedMonth
        val today = LocalDate.now()
        val dayMap = currentData?.days.orEmpty()
        val combinedMap = buildCombinedDayMap()

        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val morningRgb = prefs.getInt("color_morning_rgb", SettingsDialogHelper.DEFAULT_MORNING_RGB)
        val eveningRgb = prefs.getInt("color_evening_rgb", SettingsDialogHelper.DEFAULT_EVENING_RGB)
        val nightRgb = prefs.getInt("color_night_rgb", SettingsDialogHelper.DEFAULT_NIGHT_RGB)
        val showShiftPeriods = prefs.getBoolean("show_shift_periods", true)
        val showHolidays = prefs.getBoolean("show_finnish_holidays", true)
        val showShortRest = prefs.getBoolean("show_short_rest_warning", true)
        val periodDays = 21L
        val anchorMonday = resolvePeriodAnchorMonday()
        val shortDateFmt = DateTimeFormatter.ofPattern("d.M.")

        val borderHex = UiStyleHelper.borderHex(context)
        val headerBgHex = UiStyleHelper.headerCellHex(context)
        val weekendHeaderBgHex = UiStyleHelper.weekendHeaderHex(context)
        val weekColBgHex = UiStyleHelper.weekColHex(context)

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
                background = UiStyleHelper.cellBg(context, if (isWeekendHeader) weekendHeaderBgHex else headerBgHex, borderHex)
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

            // 3 viikon työvuorolistajakson raja + tuntisaldo oikeaan reunaan (napautettava!)
            if (showShiftPeriods && (isPeriodStartRow || weekStart == startMonday)) {
                val pStats = computePeriodStats(periodStart, periodEnd, combinedMap)
                val periodBar = LinearLayout(context).apply {
                    orientation = HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    background = UiStyleHelper.cellBg(
                        context = context,
                        fillHex = if (isPeriodStartRow) UiStyleHelper.periodBarStartHex(context) else UiStyleHelper.periodBarMidHex(context),
                        strokeHex = borderHex,
                        leftAccentHex = periodAccentHex
                    )
                    setPadding(dp(8), dp(4), dp(8), dp(4))
                    setOnClickListener {
                        showPeriodSummaryDialog(periodStart, periodEnd, pStats, combinedMap)
                    }
                }
                val labelPrefix = if (en) "Period" else "Työvuorolista"
                val rangeText = "${periodStart.format(shortDateFmt)}–${periodEnd.format(shortDateFmt)}"
                val pTv = TextView(context).apply {
                    text = "$labelPrefix $rangeText"
                    setTextColor(Color.parseColor(if (isPeriodStartRow) periodAccentHex else "#94A3B8"))
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 10.5f)
                    setTypeface(null, if (isPeriodStartRow) Typeface.BOLD else Typeface.NORMAL)
                }
                periodBar.addView(pTv, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))

                if (pStats.shiftCount > 0) {
                    val pHours = ScheduleShareHelper.formatHours(pStats.totalMinutes, en)
                    val unitShort = if (en) "sh" else "v"
                    val pBreakdownParts = mutableListOf<String>()
                    if (pStats.morningCount > 0) pBreakdownParts.add(if (en) "${pStats.morningCount} morn" else "${pStats.morningCount} aamu")
                    if (pStats.eveningCount > 0) pBreakdownParts.add(if (en) "${pStats.eveningCount} eve" else "${pStats.eveningCount} ilta")
                    if (pStats.nightCount > 0) pBreakdownParts.add(if (en) "${pStats.nightCount} night" else "${pStats.nightCount} yö")
                    val pBreakdownSuffix = if (pBreakdownParts.isNotEmpty()) " • ${pBreakdownParts.joinToString(" / ")}" else ""

                    val hTv = TextView(context).apply {
                        text = "${pStats.shiftCount} $unitShort • $pHours h$pBreakdownSuffix"
                        gravity = Gravity.END
                        setTextColor(Color.parseColor(if (isPeriodStartRow) "#E2E8F0" else "#94A3B8"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 10f)
                        setTypeface(null, Typeface.BOLD)
                    }
                    periodBar.addView(
                        hTv,
                        LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f).apply {
                            marginStart = dp(6)
                        }
                    )
                }
                gridContainer.addView(periodBar, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
            }

            val row = LinearLayout(context).apply {
                orientation = HORIZONTAL
                minimumHeight = dp(72)
            }

            // Viikkonumero + jakson vasen värikorostusreuna
            val weekNum = weekStart.get(weekFields.weekOfWeekBasedYear())
            val wkTv = TextView(context).apply {
                text = weekNum.toString()
                gravity = Gravity.TOP or Gravity.CENTER_HORIZONTAL
                setTextColor(Color.parseColor("#64748B"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 10f)
                background = UiStyleHelper.cellBg(
                    context = context,
                    fillHex = weekColBgHex,
                    strokeHex = borderHex,
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
                val holidayName = if (showHolidays && isCurrentMonth) FinnishHolidays.getHolidayName(date, en) else null
                val dayData = dayMap[date]
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
                        setOnClickListener { showDayDetailsDialog(date, dayData, holidayName, shortRestMins) }
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
            val hoursStr = ScheduleShareHelper.formatHours(totalMinutes, en)
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

    private fun launchShiftAlarm(shift: CalendarDisplayShift) {
        val en = DemoModeHelper.isEnglish(context)
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val leadMins = prefs.getInt("alarm_lead_minutes", 75).coerceIn(5, 240)
        val alarmTotal = ((shift.startMinutes - leadMins) % (24 * 60) + (24 * 60)) % (24 * 60)
        val hour = alarmTotal / 60
        val minute = alarmTotal % 60
        val locPart = shift.location.takeIf { it.isNotBlank() }?.let { " ($it)" }.orEmpty()
        val msg = if (en) {
            "Work shift ${shift.startText}$locPart"
        } else {
            "Työvuoro klo ${shift.startText}$locPart"
        }

        val intent = Intent(AlarmClock.ACTION_SET_ALARM).apply {
            putExtra(AlarmClock.EXTRA_HOUR, hour)
            putExtra(AlarmClock.EXTRA_MINUTES, minute)
            putExtra(AlarmClock.EXTRA_MESSAGE, msg)
            putExtra(AlarmClock.EXTRA_SKIP_UI, false)
        }
        try {
            context.startActivity(intent)
        } catch (_: Exception) {
            Toast.makeText(
                context,
                if (en) "Clock app not found" else "Kellosovellusta ei löytynyt",
                Toast.LENGTH_SHORT
            ).show()
        }
    }

    private fun showDayDetailsDialog(
        date: LocalDate,
        dayData: CalendarDisplayDay?,
        holidayName: String?,
        shortRestMins: Long?
    ) {
        val en = DemoModeHelper.isEnglish(context)
        val fiWeekdays = arrayOf("Ma", "Ti", "Ke", "To", "Pe", "La", "Su")
        val enWeekdays = arrayOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        val dowStr = (if (en) enWeekdays else fiWeekdays)[date.dayOfWeek.value - 1]
        val dateStr = date.format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))

        val cardBg = UiStyleHelper.cardHex(context)
        val altBg = UiStyleHelper.cardAltHex(context)
        val btnBg = UiStyleHelper.headerCellHex(context)
        val border = UiStyleHelper.borderHex(context)
        val borderStrong = UiStyleHelper.borderStrongHex(context)

        val root = LinearLayout(context).apply {
            orientation = VERTICAL
            setBackgroundColor(Color.parseColor(cardBg))
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

        if (holidayName != null) {
            contentBox.addView(
                TextView(context).apply {
                    text = "🇫🇮 $holidayName"
                    setTextColor(Color.parseColor("#FCA5A5"))
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)
                    setTypeface(null, Typeface.BOLD)
                    background = UiStyleHelper.roundedBg(context, "#3F1D24", "#EF4444", 8f)
                    setPadding(dp(10), dp(7), dp(10), dp(7))
                },
                LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                    bottomMargin = dp(8)
                }
            )
        }

        if (shortRestMins != null) {
            val h = shortRestMins / 60L
            val m = shortRestMins % 60L
            val durStr = if (en) {
                if (m > 0L) "${h}h ${m}m" else "${h}h"
            } else {
                if (m > 0L) "$h h $m min" else "$h h"
            }
            contentBox.addView(
                TextView(context).apply {
                    text = if (en) {
                        "⚠ Short rest: $durStr since previous shift"
                    } else {
                        "⚠ Lyhyt lepoaika: $durStr edellisestä vuorosta"
                    }
                    setTextColor(Color.parseColor("#FEF3C7"))
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
                    setTypeface(null, Typeface.BOLD)
                    background = UiStyleHelper.roundedBg(context, "#3B2810", "#F59E0B", 8f)
                    setPadding(dp(10), dp(7), dp(10), dp(7))
                },
                LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                    bottomMargin = dp(8)
                }
            )
        }

        var hasAny = false
        dayData?.shifts?.forEach { shift ->
            hasAny = true
            val card = LinearLayout(context).apply {
                orientation = VERTICAL
                background = UiStyleHelper.roundedBg(context, altBg, border, 10f)
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
                background = UiStyleHelper.roundedBg(context, altBg, borderHex, 8f)
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

        // Aseta herätys yhdellä napautuksella
        val earliestShift = dayData?.shifts?.minByOrNull { it.startMinutes }
        if (earliestShift != null) {
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val leadMins = prefs.getInt("alarm_lead_minutes", 75).coerceIn(5, 240)
            val alarmTotal = ((earliestShift.startMinutes - leadMins) % (24 * 60) + (24 * 60)) % (24 * 60)
            val alarmTimeStr = String.format("%02d:%02d", alarmTotal / 60, alarmTotal % 60)

            val btnAlarm = Button(context).apply {
                text = if (en) "⏰ Set alarm ($alarmTimeStr)" else "⏰ Aseta herätys (klo $alarmTimeStr)"
                isAllCaps = false
                setTextColor(Color.parseColor("#E0F2FE"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)
                setTypeface(null, Typeface.BOLD)
                background = UiStyleHelper.rippleRoundedBg(context, "#1E3A5F", "#0284C7", 8f)
                setOnClickListener {
                    dialog.dismiss()
                    launchShiftAlarm(earliestShift)
                }
            }
            root.addView(
                btnAlarm,
                LayoutParams(LayoutParams.MATCH_PARENT, dp(40)).apply {
                    bottomMargin = dp(8)
                }
            )
        }

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
                background = UiStyleHelper.rippleRoundedBg(context, btnBg, borderStrong, 8f)
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
                        val cookies = SessionCookieStore.getCookieHeader(context, baseUrl)
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
            background = UiStyleHelper.rippleRoundedBg(context, btnBg, borderStrong, 8f)
            setOnClickListener { dialog.dismiss() }
        }
        root.addView(
            btnClose,
            LayoutParams(LayoutParams.MATCH_PARENT, dp(38)).apply {
                topMargin = dp(8)
            }
        )

        dialog.window?.setBackgroundDrawable(UiStyleHelper.roundedBg(context, cardBg, "#38BDF8", 14f))
        dialog.show()
    }

    private fun showMonthJumpDialog() {
        val en = DemoModeHelper.isEnglish(context)
        val shortNames = if (en) enShortMonths else fiShortMonths
        var selectedYear = displayedMonth.year
        val realNow = YearMonth.now()
        val cardBg = UiStyleHelper.cardHex(context)
        val altBg = UiStyleHelper.cardAltHex(context)
        val btnBg = UiStyleHelper.headerCellHex(context)
        val border = UiStyleHelper.borderHex(context)
        val borderStrong = UiStyleHelper.borderStrongHex(context)

        val root = LinearLayout(context).apply {
            orientation = VERTICAL
            setBackgroundColor(Color.parseColor(cardBg))
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
            background = UiStyleHelper.roundedBg(context, altBg, border, 10f)
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
                    val bgHex = if (isSelected) "#1982C4" else altBg
                    val borderHex = if (isSelected || isCurrent) "#38BDF8" else border
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
                            loadMonth(forceNetwork = false, fromSwipe = false)
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
            background = UiStyleHelper.rippleRoundedBg(context, btnBg, borderStrong, 8f)
            setOnClickListener {
                selectedYear -= 1
                renderMonths()
            }
        }
        val btnNextYear = Button(context).apply {
            text = "▶"
            setTextColor(Color.parseColor("#38BDF8"))
            background = UiStyleHelper.rippleRoundedBg(context, btnBg, borderStrong, 8f)
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
            background = UiStyleHelper.rippleRoundedBg(context, btnBg, borderStrong, 8f)
            setOnClickListener {
                dialog.dismiss()
                displayedMonth = YearMonth.now()
                loadMonth(forceNetwork = false, fromSwipe = false)
            }
        }
        val btnCancel = Button(context).apply {
            text = if (en) "Cancel" else "Peruuta"
            isAllCaps = false
            setTextColor(Color.parseColor("#CBD5E1"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            background = UiStyleHelper.rippleRoundedBg(context, btnBg, borderStrong, 8f)
            setOnClickListener { dialog.dismiss() }
        }
        footer.addView(btnNow, LayoutParams(0, dp(38), 1f).apply { marginEnd = dp(8) })
        footer.addView(btnCancel, LayoutParams(0, dp(38), 1f))
        root.addView(footer)

        renderMonths()
        dialog.window?.setBackgroundDrawable(UiStyleHelper.roundedBg(context, cardBg, "#38BDF8", 14f))
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
