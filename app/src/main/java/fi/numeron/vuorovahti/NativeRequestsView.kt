package fi.numeron.vuorovahti

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
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
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
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
    private val dateTimeFmt = DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm")

    init {
        orientation = VERTICAL
        setBackgroundColor(Color.parseColor("#0F1722"))
        setPadding(dp(10), dp(10), dp(10), dp(4))

        val topCard = LinearLayout(context).apply {
            orientation = VERTICAL
            background = roundedBg("#182332", "#2A394A", 12f)
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
            background = roundedBg("#233040", "#37475A", 8f)
            setPadding(0, 0, 0, 0)
            setOnClickListener { loadRequests(forceNetwork = true) }
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
            background = roundedBg("#1982C4", "#38BDF8", 8f)
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

        val scroll = ScrollView(context).apply {
            isFillViewport = true
        }
        listContainer = LinearLayout(context).apply {
            orientation = VERTICAL
        }
        scroll.addView(listContainer, FrameLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        addView(scroll, LayoutParams(LayoutParams.MATCH_PARENT, 0, 1f))
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
                    loadRequests(forceNetwork = true)
                }
            }
        }
    }

    fun onShow(forceNetwork: Boolean = false) {
        updateLocalizedLabels()
        updateFilterStyles()
        loadRequests(forceNetwork = forceNetwork)
    }

    fun refreshAfterWebEdit() {
        updateLocalizedLabels()
        loadRequests(forceNetwork = true)
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
            btn.background = roundedBg(
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

    private fun loadRequests(forceNetwork: Boolean) {
        val filter = currentFilter
        val en = DemoModeHelper.isEnglish(context)
        loadJob?.cancel()

        if (DemoModeHelper.isDemoEnabled(context)) {
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
            renderRequests(if (filter == "removed") emptyList() else demoItems)
            return
        }

        // 1. Näytetään heti paikallinen välimuisti
        val cached = NumeronApiClient.loadCachedRequests(context, filter)
        if (cached != null) {
            renderRequests(cached)
        }

        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) {
            progressBar.visibility = View.GONE
            txtStatus.text = if (en) "Set organization in Settings" else "Aseta organisaatio asetuksista"
            return
        }

        progressBar.visibility = View.VISIBLE
        txtStatus.text = if (cached != null && !forceNetwork) {
            if (en) "Updating..." else "Päivitetään..."
        } else {
            if (en) "Loading requests..." else "Haetaan toiveita..."
        }

        loadJob = scope.launch {
            val result = NumeronApiClient.fetchRequests(context, filter)
            if (filter != currentFilter) return@launch
            progressBar.visibility = View.GONE

            if (result.items != null) {
                renderRequests(result.items)
                txtStatus.text = if (result.fromCache) {
                    if (en) "Offline cache (${result.items.size})" else "Välimuisti (${result.items.size} kpl)"
                } else {
                    if (en) "${result.items.size} requests" else "${result.items.size} toivetta"
                }
            } else {
                txtStatus.text = result.errorMessage ?: (if (en) "Failed to load" else "Haku epäonnistui")
                if (cached == null) {
                    renderRequests(emptyList())
                }
            }
        }
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
                background = roundedBg("#182332", "#2A394A", 12f)
                setPadding(dp(16), dp(24), dp(16), dp(24))
            }
            listContainer.addView(emptyCard, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
            return
        }

        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        val isDemo = DemoModeHelper.isDemoEnabled(context)

        for (item in items) {
            val card = LinearLayout(context).apply {
                orientation = VERTICAL
                background = roundedBg("#182332", "#2A394A", 12f)
                setPadding(dp(14), dp(12), dp(14), dp(12))
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

            val (badgeBg, badgeBorder, badgeFg) = when (item.statusCode) {
                50 -> Triple("#0F2E26", "#22C55E", "#4ADE80")
                40 -> Triple("#3B2810", "#F59E0B", "#FBBF24")
                80 -> Triple("#3F1D24", "#EF4444", "#F87171")
                else -> Triple("#1E3A5F", "#38BDF8", "#7DD3FC")
            }

            val statusTv = TextView(context).apply {
                text = item.statusDescription
                setTextColor(Color.parseColor(badgeFg))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)
                setTypeface(null, Typeface.BOLD)
                background = roundedBg(badgeBg, badgeBorder, 99f)
                setPadding(dp(10), dp(3), dp(10), dp(3))
            }
            topRow.addView(
                statusTv,
                LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT).apply {
                    marginStart = dp(8)
                }
            )
            card.addView(topRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

            // Päivämäärä ja kellonaika
            val dateLine = buildString {
                if (item.dateFrom != null) {
                    append(item.dateFrom.format(dateFmt))
                    if (item.dateTo != null && item.dateTo != item.dateFrom) {
                        append(" – ")
                        append(item.dateTo.format(dateFmt))
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
                card.addView(
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
                card.addView(
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
                card.addView(
                    TextView(context).apply {
                        text = metaParts.joinToString(" • ")
                        setTextColor(Color.parseColor("#94A3B8"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)
                        setPadding(0, dp(6), 0, 0)
                    }
                )
            }

            listContainer.addView(
                card,
                LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                    bottomMargin = dp(8)
                }
            )
        }
    }

    private fun roundedBg(fillHex: String, strokeHex: String, radiusDp: Float): GradientDrawable {
        return GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = dp(radiusDp.toInt()).toFloat()
            setColor(Color.parseColor(fillHex))
            setStroke(dp(1), Color.parseColor(strokeHex))
        }
    }

    private fun dp(value: Int): Int {
        return TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP,
            value.toFloat(),
            resources.displayMetrics
        ).toInt()
    }
}
