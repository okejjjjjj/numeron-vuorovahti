package fi.numeron.vuorovahti

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

class NativeRequestsView(
    private val context: Context,
    private val scope: CoroutineScope,
    private val onOpenWebUrl: (url: String, title: String) -> Unit
) : LinearLayout(context) {

    private var currentFilter: String = "active"
    private var loadJob: Job? = null
    private var lastSessionEpoch: Long = -1L
    private var lastRenderedItems: List<PersonRequestItem>? = null
    private var lastRenderedFilter: String? = null
    private var lastRenderedLangEn: Boolean? = null
    private var lastRenderedDemo: Boolean? = null
    private val memoryByFilter = mutableMapOf<String, Pair<List<PersonRequestItem>, Long>>()

    private val swipeRefresh: SwipeRefreshLayout
    private val txtTitle: TextView
    private val btnAdd: Button
    private val btnRefresh: Button
    private val btnFilterActive: Button
    private val btnFilterOld: Button
    private val btnFilterRemoved: Button
    private val progressBar: ProgressBar
    private val txtStatus: TextView
    private val listContainer: LinearLayout

    private val dateFmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")
    private val shortDateFmt = DateTimeFormatter.ofPattern("dd.MM.")
    private val dateTimeFmt = DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm")
    private val fiDow = arrayOf("Ma", "Ti", "Ke", "To", "Pe", "La", "Su")
    private val enDow = arrayOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

    init {
        orientation = VERTICAL
        setBackgroundColor(Color.parseColor("#0F1722"))
        setPadding(dp(10), dp(10), dp(10), dp(4))

        val topCard = LinearLayout(context).apply {
            orientation = VERTICAL
            background = UiStyleHelper.roundedBg(context, "#182332", "#2A394A", 12f)
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }

        val titleRow = LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        txtTitle = TextView(context).apply {
            setTextColor(Color.parseColor("#F1F5F9"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
            setTypeface(null, Typeface.BOLD)
        }
        titleRow.addView(txtTitle, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))

        btnRefresh = Button(context).apply {
            text = "↻"
            setTextColor(Color.parseColor("#38BDF8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            background = UiStyleHelper.rippleRoundedBg(context, "#233040", "#37475A", 8f)
            setPadding(0, 0, 0, 0)
            setOnClickListener { loadRequests(forceNetwork = true, fromSwipe = false) }
        }
        titleRow.addView(
            btnRefresh,
            LayoutParams(dp(40), dp(36)).apply {
                marginEnd = dp(8)
            }
        )

        btnAdd = Button(context).apply {
            isAllCaps = false
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)
            setTypeface(null, Typeface.BOLD)
            background = UiStyleHelper.rippleRoundedBg(context, "#1982C4", "#38BDF8", 8f, "#44FFFFFF")
            setPadding(dp(14), dp(4), dp(14), dp(4))
            minHeight = 0
            minimumHeight = dp(36)
            setOnClickListener { openNewRequest() }
        }
        titleRow.addView(btnAdd, LayoutParams(LayoutParams.WRAP_CONTENT, dp(36)))
        topCard.addView(titleRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        // Suodatinpainikkeet
        val filterRow = LinearLayout(context).apply {
            orientation = HORIZONTAL
            setPadding(0, dp(10), 0, 0)
        }

        btnFilterActive = makeFilterButton("active")
        btnFilterOld = makeFilterButton("old")
        btnFilterRemoved = makeFilterButton("removed")

        filterRow.addView(btnFilterActive, LayoutParams(0, dp(34), 1f).apply { marginEnd = dp(6) })
        filterRow.addView(btnFilterOld, LayoutParams(0, dp(34), 1f).apply { marginEnd = dp(6) })
        filterRow.addView(btnFilterRemoved, LayoutParams(0, dp(34), 1f))
        topCard.addView(filterRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        // Tilapalkki
        val statusRow = LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(8), 0, 0)
        }
        progressBar = ProgressBar(context, null, android.R.attr.progressBarStyleSmall).apply {
            isIndeterminate = true
            visibility = View.GONE
        }
        statusRow.addView(progressBar, LayoutParams(dp(16), dp(16)))

        txtStatus = TextView(context).apply {
            setTextColor(Color.parseColor("#94A3B8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setPadding(dp(6), 0, 0, 0)
        }
        statusRow.addView(txtStatus, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))
        topCard.addView(statusRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        addView(
            topCard,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(8)
            }
        )

        swipeRefresh = SwipeRefreshLayout(context).apply {
            UiStyleHelper.configureSwipeRefresh(this)
            setOnRefreshListener { loadRequests(forceNetwork = true, fromSwipe = true) }
        }

        val scroll = ScrollView(context).apply {
            isFillViewport = true
        }
        listContainer = LinearLayout(context).apply {
            orientation = VERTICAL
        }
        scroll.addView(listContainer, FrameLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        swipeRefresh.addView(scroll)
        addView(swipeRefresh, LayoutParams(LayoutParams.MATCH_PARENT, 0, 1f))
    }

    private fun makeFilterButton(filterKey: String): Button {
        return Button(context).apply {
            isAllCaps = false
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)
            setPadding(dp(6), dp(2), dp(6), dp(2))
            minHeight = 0
            minimumHeight = dp(34)
            setOnClickListener {
                if (currentFilter != filterKey) {
                    currentFilter = filterKey
                    updateFilterStyles()
                    loadRequests(forceNetwork = false, fromSwipe = false)
                }
            }
        }
    }

    fun onShow(forceNetwork: Boolean = false) {
        updateLocalizedLabels()
        updateFilterStyles()
        loadRequests(forceNetwork = forceNetwork, fromSwipe = false)
    }

    fun refreshAfterWebEdit() {
        updateLocalizedLabels()
        loadRequests(forceNetwork = true, fromSwipe = false)
    }

    private fun updateLocalizedLabels() {
        val en = DemoModeHelper.isEnglish(context)
        txtTitle.text = if (en) "Requests" else "Toiveet"
        btnAdd.text = if (en) "+ Add" else "+ Lisää"
        btnFilterActive.text = if (en) "Active" else "Aktiiviset"
        btnFilterOld.text = if (en) "All / Old" else "Myös vanhat"
        btnFilterRemoved.text = if (en) "Removed" else "Poistetut"
    }

    private fun updateFilterStyles() {
        val pairs = listOf(
            "active" to btnFilterActive,
            "old" to btnFilterOld,
            "removed" to btnFilterRemoved
        )
        for ((key, btn) in pairs) {
            val selected = (key == currentFilter)
            btn.background = UiStyleHelper.rippleRoundedBg(
                context,
                if (selected) "#1982C4" else "#111923",
                if (selected) "#38BDF8" else "#2A394A",
                8f
            )
            btn.setTextColor(if (selected) Color.WHITE else Color.parseColor("#CBD5E1"))
            btn.setTypeface(null, if (selected) Typeface.BOLD else Typeface.NORMAL)
        }
    }

    private fun openNewRequest() {
        val en = DemoModeHelper.isEnglish(context)
        if (DemoModeHelper.isDemoEnabled(context)) {
            Toast.makeText(
                context,
                if (en) "Demo mode: Adding requests is disabled" else "Demotila: Toiveen lisäys ei ole käytössä demossa",
                Toast.LENGTH_SHORT
            ).show()
            return
        }
        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) {
            Toast.makeText(
                context,
                if (en) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista",
                Toast.LENGTH_LONG
            ).show()
            return
        }
        onOpenWebUrl("$baseUrl/PersonRequests/Edit", if (en) "New request" else "Uusi toive")
    }

    private fun renderRequestsIfChanged(items: List<PersonRequestItem>, forceRender: Boolean = false) {
        val en = DemoModeHelper.isEnglish(context)
        val isDemo = DemoModeHelper.isDemoEnabled(context)
        if (!forceRender &&
            items == lastRenderedItems &&
            currentFilter == lastRenderedFilter &&
            en == lastRenderedLangEn &&
            isDemo == lastRenderedDemo
        ) {
            return
        }
        lastRenderedItems = items
        lastRenderedFilter = currentFilter
        lastRenderedLangEn = en
        lastRenderedDemo = isDemo
        renderRequests(items)
    }

    private fun loadRequests(forceNetwork: Boolean, fromSwipe: Boolean = false) {
        val filter = currentFilter
        val en = DemoModeHelper.isEnglish(context)
        val isDemo = DemoModeHelper.isDemoEnabled(context)
        loadJob?.cancel()

        val epoch = SessionCookieStore.sessionEpoch
        if (epoch != lastSessionEpoch || lastRenderedDemo != isDemo) {
            lastSessionEpoch = epoch
            memoryByFilter.clear()
            lastRenderedItems = null
        }

        if (isDemo) {
            swipeRefresh.isRefreshing = false
            progressBar.visibility = View.GONE
            txtStatus.text = if (en) "Demo mode" else "Demotila"
            val today = LocalDate.now()
            val demoItems = listOf(
                PersonRequestItem(
                    id = 1,
                    type = if (en) "Day off" else "Vapaapäivä",
                    dateFrom = today.plusDays(10),
                    dateTo = today.plusDays(10),
                    timeFromText = "",
                    timeToText = "",
                    info = if (en) "Family event" else "Perhejuhla",
                    statusCode = 50,
                    statusDescription = if (en) "Approved" else "Hyväksytty",
                    belongsToSeries = false,
                    approvedBy = "esimies@organisaatio.fi",
                    approvedDateMs = System.currentTimeMillis() - 3600_000L * 5
                ),
                PersonRequestItem(
                    id = 2,
                    type = if (en) "Morning shift" else "Aamuvuoro",
                    dateFrom = today.plusDays(14),
                    dateTo = today.plusDays(14),
                    timeFromText = "",
                    timeToText = "",
                    info = "",
                    statusCode = 10,
                    statusDescription = if (en) "Pending" else "Odottaa käsittelyä",
                    belongsToSeries = false,
                    approvedBy = "",
                    approvedDateMs = null
                )
            )
            renderRequestsIfChanged(if (filter == "removed") emptyList() else demoItems)
            return
        }

        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) {
            swipeRefresh.isRefreshing = false
            progressBar.visibility = View.GONE
            txtStatus.text = if (en) "Set organization in Settings" else "Aseta organisaatio asetuksista"
            renderRequestsIfChanged(emptyList())
            return
        }

        // 1. Muistivälimuisti + 45 s tuoreusaika
        val mem = memoryByFilter[filter]
        if (mem != null) {
            renderRequestsIfChanged(mem.first)
            if (!forceNetwork && (System.currentTimeMillis() - mem.second) < 45_000L) {
                swipeRefresh.isRefreshing = false
                progressBar.visibility = View.GONE
                val countPart = if (en) "${mem.first.size} requests" else "${mem.first.size} toivetta"
                val timePart = UiStyleHelper.formatUpdatedLabel(context, mem.second, isCache = false)
                txtStatus.text = if (timePart.isNotEmpty()) "$countPart • $timePart" else countPart
                return
            }
        }

        loadJob = scope.launch {
            var cached: List<PersonRequestItem>? = mem?.first
            var cachedAtMs: Long = mem?.second ?: 0L

            if (cached == null) {
                val diskRes = withContext(Dispatchers.IO) {
                    val items = NumeronApiClient.loadCachedRequests(context, filter)
                    val savedMs = NumeronApiClient.getRequestsCacheSavedAtMs(context, filter)
                    items to savedMs
                }
                if (filter != currentFilter) return@launch
                cached = diskRes.first
                cachedAtMs = diskRes.second
                if (cached != null) {
                    renderRequestsIfChanged(cached)
                }
            }

            if (!fromSwipe) {
                progressBar.visibility = View.VISIBLE
            }
            txtStatus.text = if (cached != null && !forceNetwork) {
                if (en) "Updating…" else "Päivitetään…"
            } else {
                if (en) "Loading requests…" else "Haetaan toiveita…"
            }

            val result = NumeronApiClient.fetchRequests(context, filter)
            if (filter != currentFilter) return@launch
            swipeRefresh.isRefreshing = false
            progressBar.visibility = View.GONE

            if (result.items != null) {
                val nowMs = System.currentTimeMillis()
                if (!result.fromCache) {
                    memoryByFilter[filter] = result.items to nowMs
                }
                renderRequestsIfChanged(result.items)
                val countPart = if (en) "${result.items.size} requests" else "${result.items.size} toivetta"
                val timePart = UiStyleHelper.formatUpdatedLabel(
                    context,
                    if (result.fromCache) cachedAtMs else nowMs,
                    isCache = result.fromCache
                )
                txtStatus.text = if (timePart.isNotEmpty()) "$countPart • $timePart" else countPart
            } else {
                txtStatus.text = result.errorMessage ?: (if (en) "Failed to load" else "Haku epäonnistui")
                if (cached == null) {
                    renderRequestsIfChanged(emptyList())
                }
            }
        }
    }

    private fun formatDateWithDow(date: LocalDate, en: Boolean, includeYear: Boolean = true): String {
        val dow = (if (en) enDow else fiDow)[date.dayOfWeek.value - 1]
        val dStr = date.format(if (includeYear) dateFmt else shortDateFmt)
        return "$dow $dStr"
    }

    private fun renderRequests(items: List<PersonRequestItem>) {
        listContainer.removeAllViews()
        val en = DemoModeHelper.isEnglish(context)

        if (items.isEmpty()) {
            val emptyCard = TextView(context).apply {
                text = if (en) "No requests in this view." else "Ei toiveita tässä näkymässä."
                setTextColor(Color.parseColor("#94A3B8"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
                gravity = Gravity.CENTER
                background = UiStyleHelper.roundedBg(context, "#182332", "#2A394A", 12f)
                setPadding(dp(16), dp(24), dp(16), dp(24))
            }
            listContainer.addView(emptyCard, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
            return
        }

        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        val isDemo = DemoModeHelper.isDemoEnabled(context)

        for (item in items) {
            val (badgeBg, badgeBorder, badgeFg) = when (item.statusCode) {
                50 -> Triple("#0F2E26", "#22C55E", "#4ADE80")
                40 -> Triple("#3B2810", "#F59E0B", "#FBBF24")
                80 -> Triple("#3F1D24", "#EF4444", "#F87171")
                else -> Triple("#1E3A5F", "#38BDF8", "#7DD3FC")
            }

            // Kortti jossa 4dp tilaväripalkki vasemmassa reunassa + Ripple
            val cardOuter = LinearLayout(context).apply {
                orientation = HORIZONTAL
                background = UiStyleHelper.rippleRoundedBg(context, "#182332", "#2A394A", 12f)
                setPadding(dp(10), dp(12), dp(14), dp(12))
                setOnClickListener {
                    if (isDemo) {
                        Toast.makeText(
                            context,
                            if (en) "Demo mode: Editing is disabled" else "Demotila: Muokkaus ei ole käytössä demossa",
                            Toast.LENGTH_SHORT
                        ).show()
                    } else if (baseUrl.isNotBlank()) {
                        onOpenWebUrl("$baseUrl/PersonRequests/Edit/${item.id}", item.type)
                    }
                }
            }

            val accentBar = View(context).apply {
                background = UiStyleHelper.roundedBg(context, badgeBorder, badgeBorder, 2f, 0)
            }
            cardOuter.addView(
                accentBar,
                LayoutParams(dp(4), LayoutParams.MATCH_PARENT).apply {
                    marginEnd = dp(11)
                }
            )

            val cardBody = LinearLayout(context).apply {
                orientation = VERTICAL
            }

            // Ylärivi: tyyppi + tilabadge
            val topRow = LinearLayout(context).apply {
                orientation = HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
            }

            val typeTv = TextView(context).apply {
                text = item.type
                setTextColor(Color.parseColor("#F1F5F9"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 15.5f)
                setTypeface(null, Typeface.BOLD)
            }
            topRow.addView(typeTv, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))

            val statusTv = TextView(context).apply {
                text = item.statusDescription
                setTextColor(Color.parseColor(badgeFg))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)
                setTypeface(null, Typeface.BOLD)
                background = UiStyleHelper.roundedBg(context, badgeBg, badgeBorder, 99f)
                setPadding(dp(10), dp(3), dp(10), dp(3))
            }
            topRow.addView(
                statusTv,
                LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT).apply {
                    marginStart = dp(8)
                }
            )
            cardBody.addView(topRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

            // Viikonpäivä + päivämäärä ja kellonaika
            val dateLine = buildString {
                if (item.dateFrom != null) {
                    if (item.dateTo != null && item.dateTo != item.dateFrom) {
                        val sameYear = item.dateFrom.year == item.dateTo.year
                        append(formatDateWithDow(item.dateFrom, en, includeYear = !sameYear))
                        append(" – ")
                        append(formatDateWithDow(item.dateTo, en, includeYear = true))
                    } else {
                        append(formatDateWithDow(item.dateFrom, en, includeYear = true))
                    }
                }
                if (item.timeFromText.isNotEmpty() || item.timeToText.isNotEmpty()) {
                    if (isNotEmpty()) append("  •  ")
                    append(item.timeFromText)
                    if (item.timeToText.isNotEmpty()) {
                        append("–")
                        append(item.timeToText)
                    }
                }
                if (item.belongsToSeries) {
                    if (isNotEmpty()) append("  •  ")
                    append(if (en) "Recurring" else "Jatkuva")
                }
            }

            if (dateLine.isNotEmpty()) {
                cardBody.addView(
                    TextView(context).apply {
                        text = dateLine
                        setTextColor(Color.parseColor("#38BDF8"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)
                        setTypeface(null, Typeface.BOLD)
                        setPadding(0, dp(6), 0, 0)
                    }
                )
            }

            if (item.info.isNotEmpty()) {
                cardBody.addView(
                    TextView(context).apply {
                        text = item.info
                        setTextColor(Color.parseColor("#CBD5E1"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
                        setPadding(0, dp(4), 0, 0)
                    }
                )
            }

            // Käsittelijä ja käsittelyaika
            val metaParts = mutableListOf<String>()
            if (item.approvedDateMs != null && item.approvedDateMs > 0L) {
                val dtStr = Instant.ofEpochMilli(item.approvedDateMs)
                    .atZone(ZoneId.systemDefault())
                    .toLocalDateTime()
                    .format(dateTimeFmt)
                metaParts.add(dtStr)
            }
            if (item.approvedBy.isNotEmpty()) {
                metaParts.add(item.approvedBy)
            }
            if (metaParts.isNotEmpty()) {
                cardBody.addView(
                    TextView(context).apply {
                        text = metaParts.joinToString(" • ")
                        setTextColor(Color.parseColor("#94A3B8"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)
                        setPadding(0, dp(6), 0, 0)
                    }
                )
            }

            cardOuter.addView(cardBody, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))
            listContainer.addView(
                cardOuter,
                LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                    bottomMargin = dp(8)
                }
            )
        }
    }

    private fun dp(value: Int): Int = UiStyleHelper.dp(context, value)
}
