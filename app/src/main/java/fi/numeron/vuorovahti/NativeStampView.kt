package fi.numeron.vuorovahti

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.InputFilter
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.LocalTime
import java.time.format.DateTimeFormatter

class NativeStampView(
    private val context: Context,
    private val scope: CoroutineScope,
    private val onOpenForgottenStampWeb: () -> Unit,
    private val onOpenEditStampWeb: (rowId: String) -> Unit,
    private val onOpenSettings: () -> Unit
) : LinearLayout(context) {

    private var currentState: StampingPageState? = null
    private var selectedReasonCodeId: Int = 0
    private var isSubmitting: Boolean = false
    private var loadJob: Job? = null

    private val txtTodayCaption: TextView
    private val btnRefresh: Button
    private val progressBar: ProgressBar
    private val txtStatus: TextView
    private val txtShiftTimes: TextView
    private val txtShiftWorkplace: TextView
    private val txtShiftDetails: TextView

    private val txtStampCaption: TextView
    private val txtReasonLabel: TextView
    private val btnReasonSelector: Button
    private val txtCommentLabel: TextView
    private val editComment: EditText
    private val btnPunch: Button
    private val btnForgotten: Button

    private val txtLatestCaption: TextView
    private val stampsListContainer: LinearLayout
    private val btnShowMore: Button

    init {
        orientation = VERTICAL
        setBackgroundColor(Color.parseColor("#0F1722"))

        val scroll = ScrollView(context).apply {
            isFillViewport = true
        }
        val content = LinearLayout(context).apply {
            orientation = VERTICAL
            setPadding(dp(12), dp(12), dp(12), dp(12))
        }

        // === KORTTI 1: TÄNÄÄN ===
        val todayCard = LinearLayout(context).apply {
            orientation = VERTICAL
            background = roundedBg("#182332", "#2A394A", 12f)
            setPadding(dp(14), dp(12), dp(14), dp(14))
        }

        val todayTopRow = LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        txtTodayCaption = TextView(context).apply {
            setTextColor(Color.parseColor("#94A3B8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setTypeface(null, Typeface.BOLD)
            letterSpacing = 0.06f
        }
        todayTopRow.addView(txtTodayCaption, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))

        progressBar = ProgressBar(context, null, android.R.attr.progressBarStyleSmall).apply {
            isIndeterminate = true
            visibility = View.GONE
        }
        todayTopRow.addView(progressBar, LayoutParams(dp(18), dp(18)))

        txtStatus = TextView(context).apply {
            setTextColor(Color.parseColor("#94A3B8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)
            setPadding(dp(6), 0, dp(8), 0)
        }
        todayTopRow.addView(txtStatus, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))

        btnRefresh = Button(context).apply {
            text = "↻"
            setTextColor(Color.parseColor("#38BDF8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
            background = roundedBg("#233040", "#37475A", 8f)
            setPadding(0, 0, 0, 0)
            minHeight = 0
            minimumHeight = dp(32)
            setOnClickListener { loadState(forceNetwork = true) }
        }
        todayTopRow.addView(btnRefresh, LayoutParams(dp(36), dp(32)))

        todayCard.addView(todayTopRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        txtShiftTimes = TextView(context).apply {
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 24f)
            setTypeface(null, Typeface.BOLD)
            setPadding(0, dp(6), 0, dp(2))
        }
        todayCard.addView(txtShiftTimes, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        txtShiftWorkplace = TextView(context).apply {
            setTextColor(Color.parseColor("#38BDF8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            setTypeface(null, Typeface.BOLD)
            setPadding(0, dp(2), 0, 0)
        }
        todayCard.addView(txtShiftWorkplace, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        txtShiftDetails = TextView(context).apply {
            setTextColor(Color.parseColor("#CBD5E1"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            setPadding(0, dp(2), 0, 0)
        }
        todayCard.addView(txtShiftDetails, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        content.addView(
            todayCard,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(12)
            }
        )

        // === KORTTI 2: LEIMAUS ===
        val stampCard = LinearLayout(context).apply {
            orientation = VERTICAL
            background = roundedBg("#182332", "#2A394A", 12f)
            setPadding(dp(14), dp(12), dp(14), dp(12))
        }

        txtStampCaption = TextView(context).apply {
            setTextColor(Color.parseColor("#94A3B8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setTypeface(null, Typeface.BOLD)
            letterSpacing = 0.06f
            setPadding(0, 0, 0, dp(8))
        }
        stampCard.addView(txtStampCaption, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        txtReasonLabel = TextView(context).apply {
            setTextColor(Color.parseColor("#CBD5E1"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            setPadding(0, 0, 0, dp(4))
        }
        stampCard.addView(txtReasonLabel, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        btnReasonSelector = Button(context).apply {
            isAllCaps = false
            gravity = Gravity.START or Gravity.CENTER_VERTICAL
            setTextColor(Color.parseColor("#F1F5F9"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            background = roundedBg("#111923", "#37475A", 8f)
            setPadding(dp(12), dp(10), dp(12), dp(10))
            setOnClickListener { showReasonCodeDialog() }
        }
        stampCard.addView(
            btnReasonSelector,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(10)
            }
        )

        txtCommentLabel = TextView(context).apply {
            setTextColor(Color.parseColor("#CBD5E1"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            setPadding(0, 0, 0, dp(4))
        }
        stampCard.addView(txtCommentLabel, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        editComment = EditText(context).apply {
            setTextColor(Color.WHITE)
            setHintTextColor(Color.parseColor("#64748B"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            background = roundedBg("#111923", "#37475A", 8f)
            setPadding(dp(12), dp(10), dp(12), dp(10))
            isSingleLine = true
            filters = arrayOf(InputFilter.LengthFilter(255))
        }
        stampCard.addView(
            editComment,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(14)
            }
        )

        btnPunch = Button(context).apply {
            isAllCaps = false
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
            setTypeface(null, Typeface.BOLD)
            background = roundedBg("#15803D", "#22C55E", 10f)
            setPadding(dp(12), dp(14), dp(12), dp(14))
            setOnClickListener { handlePunchClick() }
        }
        stampCard.addView(btnPunch, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        btnForgotten = Button(context).apply {
            isAllCaps = false
            setTextColor(Color.parseColor("#38BDF8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)
            setTypeface(null, Typeface.BOLD)
            setBackgroundColor(Color.TRANSPARENT)
            gravity = Gravity.START or Gravity.CENTER_VERTICAL
            setPadding(0, dp(10), dp(8), dp(2))
            minHeight = 0
            minimumHeight = dp(36)
            setOnClickListener {
                val en = DemoModeHelper.isEnglish(context)
                if (DemoModeHelper.isDemoEnabled(context)) {
                    Toast.makeText(
                        context,
                        if (en) "Demo mode: Missing stamp form is disabled" else "Demotila: Puuttuvan leimauksen lisäys ei ole käytössä demossa",
                        Toast.LENGTH_SHORT
                    ).show()
                } else {
                    onOpenForgottenStampWeb()
                }
            }
        }
        stampCard.addView(btnForgotten, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))

        content.addView(
            stampCard,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(12)
            }
        )

        // === KORTTI 3: VIIMEISIMMÄT LEIMAUKSET ===
        val historyCard = LinearLayout(context).apply {
            orientation = VERTICAL
            background = roundedBg("#182332", "#2A394A", 12f)
            setPadding(dp(14), dp(12), dp(14), dp(10))
        }

        txtLatestCaption = TextView(context).apply {
            setTextColor(Color.parseColor("#94A3B8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setTypeface(null, Typeface.BOLD)
            letterSpacing = 0.06f
            setPadding(0, 0, 0, dp(8))
        }
        historyCard.addView(txtLatestCaption, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        stampsListContainer = LinearLayout(context).apply {
            orientation = VERTICAL
        }
        historyCard.addView(stampsListContainer, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        btnShowMore = Button(context).apply {
            isAllCaps = false
            setTextColor(Color.parseColor("#38BDF8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)
            setTypeface(null, Typeface.BOLD)
            setBackgroundColor(Color.TRANSPARENT)
            gravity = Gravity.START or Gravity.CENTER_VERTICAL
            setPadding(0, dp(8), dp(8), dp(2))
            minHeight = 0
            minimumHeight = dp(36)
            visibility = View.GONE
            setOnClickListener { loadMoreStamps() }
        }
        historyCard.addView(btnShowMore, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))

        content.addView(historyCard, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        scroll.addView(content, FrameLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        addView(scroll, LayoutParams(LayoutParams.MATCH_PARENT, 0, 1f))
    }

    fun onShow(forceNetwork: Boolean = false) {
        updateLocalizedLabels()
        loadState(forceNetwork = forceNetwork)
    }

    fun refreshFromNetwork() {
        updateLocalizedLabels()
        loadState(forceNetwork = true)
    }

    fun performAutoStamp(wantIn: Boolean, onFinished: () -> Unit) {
        updateLocalizedLabels()
        val en = DemoModeHelper.isEnglish(context)
        if (DemoModeHelper.isDemoEnabled(context)) {
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val currentlyIn = prefs.getBoolean("demo_stamped_in", false)
            val dirLabel = if (en) (if (wantIn) "In" else "Out") else (if (wantIn) "Sisään" else "Ulos")
            if (wantIn != currentlyIn) {
                recordDemoStamp(wantIn)
                Toast.makeText(
                    context,
                    if (en) "Demo mode: Clocked $dirLabel" else "Demotila: Leimattu ($dirLabel)",
                    Toast.LENGTH_SHORT
                ).show()
            } else {
                Toast.makeText(
                    context,
                    if (en) "Demo mode: Already clocked $dirLabel" else "Demotila: Olet jo leimannut tilaan $dirLabel",
                    Toast.LENGTH_SHORT
                ).show()
            }
            loadState(forceNetwork = false)
            postDelayed(onFinished, 1200L)
            return
        }

        val expectedDir = if (wantIn) "IN" else "OUT"
        val dirLabel = if (en) (if (wantIn) "In" else "Out") else (if (wantIn) "Sisään" else "Ulos")
        setControlsBusy(true, if (en) "Stamping ($dirLabel)…" else "Leimataan ($dirLabel)…")

        scope.launch {
            val res = NumeronApiClient.performDirectStamp(
                context = context,
                currentState = null,
                reasonCodeId = null,
                comment = "",
                expectedDirection = expectedDir,
                onStatusUpdate = { msg -> post { txtStatus.text = msg } }
            )
            setControlsBusy(false, "")
            when (res) {
                is StampSubmitResult.Success -> {
                    res.updatedState?.let {
                        currentState = it
                        selectedReasonCodeId = it.defaultReasonCode
                        renderState(it)
                    }
                    Toast.makeText(
                        context,
                        if (en) "Stamp confirmed ($dirLabel)" else "Leimaus vahvistettu ($dirLabel)",
                        Toast.LENGTH_SHORT
                    ).show()
                    postDelayed(onFinished, 1200L)
                }
                is StampSubmitResult.AlreadyInDirection -> {
                    Toast.makeText(
                        context,
                        if (en) "Already clocked $dirLabel" else "Olet jo leimannut tilaan: $dirLabel",
                        Toast.LENGTH_LONG
                    ).show()
                    loadState(forceNetwork = true)
                    postDelayed(onFinished, 1400L)
                }
                is StampSubmitResult.ValidationRejected -> {
                    Toast.makeText(context, res.message, Toast.LENGTH_LONG).show()
                    loadState(forceNetwork = true)
                }
                is StampSubmitResult.Failed -> {
                    Toast.makeText(context, res.message, Toast.LENGTH_LONG).show()
                    loadState(forceNetwork = true)
                }
            }
        }
    }

    private fun updateLocalizedLabels() {
        val en = DemoModeHelper.isEnglish(context)
        txtTodayCaption.text = if (en) "TODAY" else "TÄNÄÄN"
        txtStampCaption.text = if (en) "TIME STAMPING" else "LEIMAUS"
        txtReasonLabel.text = if (en) "Reason code" else "Syykoodi"
        txtCommentLabel.text = if (en) "Comment" else "Lisätiedot"
        editComment.hint = if (en) "Write a note if needed" else "Kirjoita selite tarvittaessa"
        btnForgotten.text = if (en) "+ Add missing stamp" else "+ Lisää puuttuva leimaus"
        txtLatestCaption.text = if (en) "LATEST STAMPS" else "VIIMEISIMMÄT LEIMAUKSET"
        btnShowMore.text = if (en) "Show more" else "Näytä lisää"
    }

    private fun loadState(forceNetwork: Boolean) {
        val en = DemoModeHelper.isEnglish(context)
        loadJob?.cancel()

        if (DemoModeHelper.isDemoEnabled(context)) {
            progressBar.visibility = View.GONE
            txtStatus.text = "Demo"
            val demoState = buildDemoState()
            currentState = demoState
            selectedReasonCodeId = demoState.defaultReasonCode
            renderState(demoState)
            return
        }

        // 1. Näytetään heti paikallinen välimuisti (0 ms viive)
        val cached = NumeronApiClient.loadCachedStampingState(context)
        if (cached != null) {
            if (currentState == null) {
                currentState = cached
                selectedReasonCodeId = cached.defaultReasonCode
            }
            renderState(currentState ?: cached)
        }

        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) {
            progressBar.visibility = View.GONE
            txtStatus.text = ""
            txtShiftTimes.text = if (en) "Welcome" else "Tervetuloa"
            txtShiftWorkplace.text = if (en) "Set organization ID in Settings" else "Aseta organisaatiotunnus asetuksista"
            txtShiftDetails.visibility = View.GONE
            btnPunch.isEnabled = false
            btnPunch.text = if (en) "Open Settings" else "Avaa asetukset"
            btnPunch.setOnClickListener { onOpenSettings() }
            return
        }

        btnPunch.setOnClickListener { handlePunchClick() }

        if (BackgroundAuthHelper.isCredentialBlocked(context)) {
            progressBar.visibility = View.GONE
            txtStatus.text = if (en) "Check login" else "Tarkista tunnukset"
            Toast.makeText(
                context,
                if (en) "Login failed – please check username and password in Settings"
                else "Kirjautuminen epäonnistui – tarkista käyttäjätunnus ja salasana asetuksista",
                Toast.LENGTH_LONG
            ).show()
            return
        }

        progressBar.visibility = View.VISIBLE
        txtStatus.text = if (cached != null && !forceNetwork) {
            if (en) "Updating…" else "Päivitetään…"
        } else {
            if (en) "Loading…" else "Ladataan…"
        }

        loadJob = scope.launch {
            val fresh = NumeronApiClient.fetchStampingState(context, forceRefreshSession = false)
            progressBar.visibility = View.GONE
            if (fresh != null) {
                currentState = fresh
                selectedReasonCodeId = fresh.defaultReasonCode
                txtStatus.text = ""
                renderState(fresh)
            } else {
                txtStatus.text = if (cached != null) {
                    if (en) "Offline cache" else "Välimuisti"
                } else {
                    if (en) "Load failed" else "Lataus epäonnistui"
                }
            }
        }
    }

    private fun renderState(state: StampingPageState) {
        val en = DemoModeHelper.isEnglish(context)

        if (state.shiftTimes.isNotEmpty()) {
            txtShiftTimes.visibility = View.VISIBLE
            txtShiftTimes.text = state.shiftTimes
        } else {
            txtShiftTimes.visibility = View.GONE
        }

        if (state.shiftWorkplace.isNotEmpty()) {
            txtShiftWorkplace.visibility = View.VISIBLE
            txtShiftWorkplace.text = state.shiftWorkplace
        } else if (state.shiftTimes.isEmpty()) {
            txtShiftWorkplace.visibility = View.VISIBLE
            txtShiftWorkplace.text = if (en) "No scheduled shift today" else "Ei suunniteltua työvuoroa tänään"
        } else {
            txtShiftWorkplace.visibility = View.GONE
        }

        if (state.shiftDetails.isNotEmpty()) {
            txtShiftDetails.visibility = View.VISIBLE
            txtShiftDetails.text = state.shiftDetails
        } else {
            txtShiftDetails.visibility = View.GONE
        }

        val activeRc = state.reasonCodes.firstOrNull { it.id == selectedReasonCodeId }
            ?: state.reasonCodes.firstOrNull()
        val rcLabel = activeRc?.label ?: (if (en) "Normal working time" else "Normaali työaika")
        btnReasonSelector.text = "$rcLabel  ▾"

        val isOutNext = state.nextDirection.equals("OUT", ignoreCase = true)
        btnPunch.isEnabled = !isSubmitting && (state.nextDirection == "IN" || state.nextDirection == "OUT")
        btnPunch.text = state.punchButtonText.ifEmpty {
            if (en) {
                if (isOutNext) "Clock Out" else "Clock In"
            } else {
                if (isOutNext) "Leimaa Ulos" else "Leimaa Sisään"
            }
        }
        btnPunch.background = if (isOutNext) {
            roundedBg("#B91C1C", "#F87171", 10f)
        } else {
            roundedBg("#15803D", "#22C55E", 10f)
        }

        renderStampsTable(state.latestStamps)
        btnShowMore.visibility = if (state.hasMoreStamps) View.VISIBLE else View.GONE
    }

    private fun renderStampsTable(rows: List<StampHistoryRow>) {
        stampsListContainer.removeAllViews()
        val en = DemoModeHelper.isEnglish(context)
        val isDemo = DemoModeHelper.isDemoEnabled(context)

        if (rows.isEmpty()) {
            stampsListContainer.addView(
                TextView(context).apply {
                    text = if (en) "No recent stamps" else "Ei viimeisimpiä leimauksia"
                    setTextColor(Color.parseColor("#94A3B8"))
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)
                    setPadding(0, dp(6), 0, dp(6))
                }
            )
            return
        }

        for (i in rows.indices) {
            val row = rows[i]
            if (i > 0) {
                val divider = View(context).apply {
                    setBackgroundColor(Color.parseColor("#2A394A"))
                }
                stampsListContainer.addView(divider, LayoutParams(LayoutParams.MATCH_PARENT, 1))
            }

            val rowView = LinearLayout(context).apply {
                orientation = HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(4), dp(10), dp(4), dp(10))
                if (!isDemo && row.rowId.isNotEmpty()) {
                    setOnClickListener { onOpenEditStampWeb(row.rowId) }
                }
            }

            val dayTv = TextView(context).apply {
                text = row.dayText
                setTextColor(Color.parseColor("#E2E8F0"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            }
            rowView.addView(dayTv, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1.2f))

            val timeTv = TextView(context).apply {
                text = row.timeText
                setTextColor(Color.WHITE)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14.5f)
                setTypeface(null, Typeface.BOLD)
            }
            rowView.addView(timeTv, LayoutParams(0, LayoutParams.WRAP_CONTENT, 0.8f))

            val badgeBg = if (row.isIn) "#122B22" else "#3F1D24"
            val badgeBorder = if (row.isIn) "#22C55E" else "#F87171"
            val badgeFg = if (row.isIn) "#4ADE80" else "#F87171"
            val dirBadge = TextView(context).apply {
                text = row.directionText
                setTextColor(Color.parseColor(badgeFg))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
                setTypeface(null, Typeface.BOLD)
                background = roundedBg(badgeBg, badgeBorder, 99f)
                setPadding(dp(10), dp(3), dp(10), dp(3))
            }
            rowView.addView(dirBadge, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))

            if (!isDemo && row.rowId.isNotEmpty()) {
                val arrow = TextView(context).apply {
                    text = "›"
                    setTextColor(Color.parseColor("#64748B"))
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
                    setPadding(dp(10), 0, dp(2), 0)
                }
                rowView.addView(arrow, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))
            }

            stampsListContainer.addView(rowView, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        }
    }

    private fun showReasonCodeDialog() {
        val codes = currentState?.reasonCodes.orEmpty()
        if (codes.isEmpty()) return
        val en = DemoModeHelper.isEnglish(context)
        val labels = codes.map { it.label }.toTypedArray()
        val checkedIdx = codes.indexOfFirst { it.id == selectedReasonCodeId }.coerceAtLeast(0)

        AlertDialog.Builder(context)
            .setTitle(if (en) "Select reason code" else "Valitse syykoodi")
            .setSingleChoiceItems(labels, checkedIdx) { dialog, which ->
                val chosen = codes[which]
                selectedReasonCodeId = chosen.id
                btnReasonSelector.text = "${chosen.label}  ▾"
                dialog.dismiss()
            }
            .setNegativeButton(if (en) "Cancel" else "Peruuta", null)
            .show()
    }

    private fun handlePunchClick() {
        if (isSubmitting) return
        val en = DemoModeHelper.isEnglish(context)

        if (DemoModeHelper.isDemoEnabled(context)) {
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val currentlyIn = prefs.getBoolean("demo_stamped_in", false)
            val wantIn = !currentlyIn
            recordDemoStamp(wantIn)
            editComment.setText("")
            val dirLabel = if (en) (if (wantIn) "In" else "Out") else (if (wantIn) "Sisään" else "Ulos")
            Toast.makeText(
                context,
                if (en) "Demo stamp recorded ($dirLabel)" else "Demoleimaus tallennettu ($dirLabel)",
                Toast.LENGTH_SHORT
            ).show()
            loadState(forceNetwork = false)
            return
        }

        val state = currentState
        val comment = editComment.text?.toString()?.trim().orEmpty()
        setControlsBusy(true, if (en) "Recording stamp…" else "Lähetetään leimausta…")

        scope.launch {
            val result = NumeronApiClient.performDirectStamp(
                context = context,
                currentState = state,
                reasonCodeId = selectedReasonCodeId,
                comment = comment,
                expectedDirection = null,
                onStatusUpdate = { msg -> post { txtStatus.text = msg } }
            )
            setControlsBusy(false, "")

            when (result) {
                is StampSubmitResult.Success -> {
                    editComment.setText("")
                    val dirLabel = if (en) {
                        if (result.directionUsed == "IN") "In" else "Out"
                    } else {
                        if (result.directionUsed == "IN") "Sisään" else "Ulos"
                    }
                    result.updatedState?.let {
                        currentState = it
                        selectedReasonCodeId = it.defaultReasonCode
                        renderState(it)
                    }
                    Toast.makeText(
                        context,
                        if (en) "Stamp confirmed ($dirLabel)" else "Leimaus vahvistettu ($dirLabel)",
                        Toast.LENGTH_SHORT
                    ).show()
                }
                is StampSubmitResult.AlreadyInDirection -> {
                    loadState(forceNetwork = true)
                }
                is StampSubmitResult.ValidationRejected -> {
                    AlertDialog.Builder(context)
                        .setTitle(if (en) "Stamp not saved" else "Leimausta ei tallennettu")
                        .setMessage(result.message)
                        .setPositiveButton("OK", null)
                        .show()
                    loadState(forceNetwork = true)
                }
                is StampSubmitResult.Failed -> {
                    Toast.makeText(context, result.message, Toast.LENGTH_LONG).show()
                    loadState(forceNetwork = true)
                }
            }
        }
    }

    private fun loadMoreStamps() {
        val state = currentState ?: return
        val en = DemoModeHelper.isEnglish(context)
        val nextTake = state.currentTake + 6
        btnShowMore.isEnabled = false
        progressBar.visibility = View.VISIBLE
        txtStatus.text = if (en) "Loading more…" else "Haetaan lisää…"

        scope.launch {
            val res = NumeronApiClient.fetchMoreStamps(context, nextTake, state.getMoreStampsUrl)
            progressBar.visibility = View.GONE
            btnShowMore.isEnabled = true
            txtStatus.text = ""

            if (res != null) {
                val (newRows, hasMore) = res
                val updated = state.copy(
                    latestStamps = newRows,
                    hasMoreStamps = hasMore,
                    currentTake = newRows.size.coerceAtLeast(nextTake)
                )
                currentState = updated
                NumeronApiClient.saveCachedStampingState(context, updated)
                renderState(updated)
            } else {
                Toast.makeText(
                    context,
                    if (en) "Could not load more stamps" else "Lisäleimausten haku epäonnistui",
                    Toast.LENGTH_SHORT
                ).show()
            }
        }
    }

    private fun setControlsBusy(busy: Boolean, statusMsg: String) {
        isSubmitting = busy
        btnPunch.isEnabled = !busy
        btnReasonSelector.isEnabled = !busy
        editComment.isEnabled = !busy
        progressBar.visibility = if (busy) View.VISIBLE else View.GONE
        txtStatus.text = statusMsg
    }

    private fun buildDemoState(): StampingPageState {
        val en = DemoModeHelper.isEnglish(context)
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val isIn = prefs.getBoolean("demo_stamped_in", false)
        val yest = LocalDate.now().minusDays(1).format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
        val defaultHist = "$yest | 14:30 | Ulos\n$yest | 07:00 | Sisään"
        val rawHist = prefs.getString("demo_stamp_history", defaultHist) ?: defaultHist
        val todayStr = LocalDate.now().format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))

        val rows = rawHist.lineSequence()
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .mapNotNull { line ->
                val parts = line.split("|").map { it.trim() }
                if (parts.size < 3) return@mapNotNull null
                val dayDisplay = if (parts[0] == todayStr) (if (en) "Today" else "Tänään") else parts[0]
                val isRowIn = parts[2].equals("Sisään", true) || parts[2].equals("In", true)
                val dirLabel = if (en) (if (isRowIn) "In" else "Out") else (if (isRowIn) "Sisään" else "Ulos")
                StampHistoryRow("", dayDisplay, parts[1], dirLabel, isRowIn, "")
            }
            .toList()

        return StampingPageState(
            shiftTimes = "07:00 - 14:30",
            shiftWorkplace = if (en) "Demo Ward A" else "Demo-osasto A",
            shiftDetails = if (en) "Morning shift • Nurse" else "Aamuvuoro • Hoitaja",
            nextDirection = if (isIn) "OUT" else "IN",
            punchButtonText = if (en) {
                if (isIn) "Clock Out" else "Clock In"
            } else {
                if (isIn) "Leimaa Ulos" else "Leimaa Sisään"
            },
            defaultReasonCode = 0,
            reasonCodes = listOf(
                StampReasonCode(0, if (en) "Normal working time" else "Normaali työaika"),
                StampReasonCode(7, if (en) "Work matter" else "Työasia")
            ),
            latestStamps = rows,
            hasMoreStamps = false,
            currentTake = rows.size,
            verificationToken = "",
            saveStampUrl = "",
            validateStampSaveUrl = "",
            getMoreStampsUrl = "",
            fromCache = false
        )
    }

    private fun recordDemoStamp(wantIn: Boolean) {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val nowDate = LocalDate.now().format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
        val nowTime = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
        val yest = LocalDate.now().minusDays(1).format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
        val defaultHistory = "$yest | 14:30 | Ulos\n$yest | 07:00 | Sisään"
        val oldHistory = prefs.getString("demo_stamp_history", defaultHistory) ?: defaultHistory
        val dirFi = if (wantIn) "Sisään" else "Ulos"
        val newHistory = "$nowDate | $nowTime | $dirFi\n$oldHistory"
        prefs.edit()
            .putBoolean("demo_stamped_in", wantIn)
            .putString("demo_stamp_history", newHistory)
            .apply()
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
