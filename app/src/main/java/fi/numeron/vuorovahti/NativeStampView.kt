package fi.numeron.vuorovahti

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.os.Handler
import android.os.Looper
import android.text.Editable
import android.text.InputFilter
import android.text.TextWatcher
import android.transition.AutoTransition
import android.transition.TransitionManager
import android.util.TypedValue
import android.view.Gravity
import android.view.HapticFeedbackConstants
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
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Duration
import java.time.LocalDate
import java.time.LocalDateTime
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
    private var isOptionsExpanded: Boolean = false
    private var lastSuccessfulStampMs: Long = 0L
    private var lastNetworkFetchMs: Long = 0L
    private var lastSessionEpoch: Long = -1L
    private var lastRenderedState: StampingPageState? = null
    private var lastRenderedNextShift: String? = null
    private var lastRenderedLangEn: Boolean? = null
    private var lastRenderedDemo: Boolean? = null
    private var lastRenderedAmoled: Boolean? = null
    private var lastRenderedBalanceKey: String? = null
    private var cachedNextShiftText: String? = null
    private var cachedPeriodBalance: PeriodBalanceResult? = null
    private var loadJob: Job? = null

    private val tickerHandler = Handler(Looper.getMainLooper())
    private val liveDurationRunnable = object : Runnable {
        override fun run() {
            updateWorkingStatusPill()
            tickerHandler.postDelayed(this, 30_000L)
        }
    }

    private val swipeRefresh: SwipeRefreshLayout
    private val todayCard: LinearLayout
    private val stampCard: LinearLayout
    private val historyCard: LinearLayout

    private val txtTodayCaption: TextView
    private val btnRefresh: Button
    private val progressBar: ProgressBar
    private val txtStatus: TextView
    private val txtWorkingPill: TextView
    private val txtShiftTimes: TextView
    private val txtShiftWorkplace: TextView
    private val txtShiftDetails: TextView
    private val shiftProgressContainer: LinearLayout
    private val txtShiftRemaining: TextView
    private val shiftProgressTrack: LinearLayout
    private val shiftProgressFill: View
    private val shiftProgressRest: View
    private val txtPeriodBalance: TextView
    private val txtNextShift: TextView

    private val txtStampCaption: TextView
    private val btnPunch: Button
    private val btnOptionsToggle: Button
    private val optionsContainer: LinearLayout
    private val txtReasonLabel: TextView
    private val btnReasonSelector: Button
    private val txtCommentLabel: TextView
    private val editComment: EditText
    private val btnForgotten: Button

    private val txtLatestCaption: TextView
    private val stampsListContainer: LinearLayout
    private val btnShowMore: Button

    init {
        orientation = VERTICAL

        swipeRefresh = SwipeRefreshLayout(context).apply {
            setOnRefreshListener { loadState(forceNetwork = true, fromSwipe = true) }
        }

        val scroll = ScrollView(context).apply {
            isFillViewport = true
        }
        val content = LinearLayout(context).apply {
            orientation = VERTICAL
            setPadding(dp(12), dp(12), dp(12), dp(14))
        }

        // === KORTTI 1: TÄNÄÄN ===
        todayCard = LinearLayout(context).apply {
            orientation = VERTICAL
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
        todayTopRow.addView(progressBar, LayoutParams(dp(16), dp(16)))

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
            setPadding(0, 0, 0, 0)
            minHeight = 0
            minimumHeight = dp(32)
            setOnClickListener { loadState(forceNetwork = true, fromSwipe = false) }
        }
        todayTopRow.addView(btnRefresh, LayoutParams(dp(36), dp(32)))

        todayCard.addView(todayTopRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        txtWorkingPill = TextView(context).apply {
            setTextColor(Color.parseColor("#4ADE80"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)
            setTypeface(null, Typeface.BOLD)
            background = UiStyleHelper.roundedBg(context, "#0F2E26", "#22C55E", 99f)
            setPadding(dp(11), dp(4), dp(11), dp(4))
            visibility = View.GONE
        }
        todayCard.addView(
            txtWorkingPill,
            LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(8)
                bottomMargin = dp(2)
            }
        )

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

        // Vuoron edistymispalkki (näkyy sisäänleimattuna kun vuorolle on kellonajat)
        shiftProgressContainer = LinearLayout(context).apply {
            orientation = VERTICAL
            visibility = View.GONE
            setPadding(0, dp(10), 0, 0)
        }
        txtShiftRemaining = TextView(context).apply {
            setTextColor(Color.parseColor("#94A3B8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, dp(5))
        }
        shiftProgressContainer.addView(txtShiftRemaining, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        shiftProgressTrack = LinearLayout(context).apply {
            orientation = HORIZONTAL
            weightSum = 1f
        }
        shiftProgressFill = View(context)
        shiftProgressRest = View(context)
        shiftProgressTrack.addView(shiftProgressFill, LayoutParams(0, LayoutParams.MATCH_PARENT, 0f))
        shiftProgressTrack.addView(shiftProgressRest, LayoutParams(0, LayoutParams.MATCH_PARENT, 1f))
        shiftProgressContainer.addView(shiftProgressTrack, LayoutParams(LayoutParams.MATCH_PARENT, dp(5)))
        todayCard.addView(shiftProgressContainer, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        txtPeriodBalance = TextView(context).apply {
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)
            setTypeface(null, Typeface.BOLD)
            setPadding(dp(10), dp(7), dp(10), dp(7))
            visibility = View.GONE
        }
        todayCard.addView(
            txtPeriodBalance,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(10)
            }
        )

        txtNextShift = TextView(context).apply {
            setTextColor(Color.parseColor("#E2E8F0"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            setPadding(dp(10), dp(8), dp(10), dp(8))
            visibility = View.GONE
        }
        todayCard.addView(
            txtNextShift,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(10)
            }
        )

        content.addView(
            todayCard,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(12)
            }
        )

        // === KORTTI 2: LEIMAUS (nappi heti ylhäällä peukalon alla) ===
        stampCard = LinearLayout(context).apply {
            orientation = VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(10))
        }

        txtStampCaption = TextView(context).apply {
            setTextColor(Color.parseColor("#94A3B8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setTypeface(null, Typeface.BOLD)
            letterSpacing = 0.06f
            setPadding(0, 0, 0, dp(10))
        }
        stampCard.addView(txtStampCaption, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        btnPunch = Button(context).apply {
            isAllCaps = false
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 17.5f)
            setTypeface(null, Typeface.BOLD)
            background = UiStyleHelper.rippleRoundedBg(context, "#15803D", "#22C55E", 10f, "#44FFFFFF")
            setPadding(dp(12), dp(14), dp(12), dp(14))
            minHeight = dp(54)
            minimumHeight = dp(54)
            setOnClickListener { handlePunchClick() }
        }
        stampCard.addView(btnPunch, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        optionsContainer = LinearLayout(context).apply {
            orientation = VERTICAL
            visibility = View.GONE
            setPadding(0, dp(8), 0, dp(2))
        }

        // Kompakti syykoodi + lisätieto -avausrivi (TransitionManager-mikroanimaatio)
        btnOptionsToggle = Button(context).apply {
            isAllCaps = false
            gravity = Gravity.START or Gravity.CENTER_VERTICAL
            setTextColor(Color.parseColor("#CBD5E1"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            setPadding(dp(12), dp(8), dp(12), dp(8))
            minHeight = 0
            minimumHeight = dp(38)
            setOnClickListener {
                try {
                    TransitionManager.beginDelayedTransition(
                        stampCard,
                        AutoTransition().apply { duration = 170L }
                    )
                } catch (_: Exception) {
                }
                isOptionsExpanded = !isOptionsExpanded
                optionsContainer.visibility = if (isOptionsExpanded) View.VISIBLE else View.GONE
                updateOptionsToggleText()
            }
        }
        stampCard.addView(
            btnOptionsToggle,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(10)
            }
        )

        txtReasonLabel = TextView(context).apply {
            setTextColor(Color.parseColor("#CBD5E1"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)
            setPadding(0, 0, 0, dp(4))
        }
        optionsContainer.addView(txtReasonLabel, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        btnReasonSelector = Button(context).apply {
            isAllCaps = false
            gravity = Gravity.START or Gravity.CENTER_VERTICAL
            setTextColor(Color.parseColor("#F1F5F9"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            setPadding(dp(12), dp(10), dp(12), dp(10))
            setOnClickListener { showReasonCodeDialog() }
        }
        optionsContainer.addView(
            btnReasonSelector,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(10)
            }
        )

        txtCommentLabel = TextView(context).apply {
            setTextColor(Color.parseColor("#CBD5E1"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)
            setPadding(0, 0, 0, dp(4))
        }
        optionsContainer.addView(txtCommentLabel, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        editComment = EditText(context).apply {
            setTextColor(Color.WHITE)
            setHintTextColor(Color.parseColor("#64748B"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            setPadding(dp(12), dp(10), dp(12), dp(10))
            isSingleLine = true
            filters = arrayOf(InputFilter.LengthFilter(255))
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
                override fun afterTextChanged(s: Editable?) {
                    updateOptionsToggleText()
                }
            })
        }
        optionsContainer.addView(
            editComment,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(4)
            }
        )

        stampCard.addView(optionsContainer, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        btnForgotten = Button(context).apply {
            isAllCaps = false
            setTextColor(Color.parseColor("#38BDF8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)
            setTypeface(null, Typeface.BOLD)
            background = UiStyleHelper.rippleTransparentBg(context, 8f)
            gravity = Gravity.START or Gravity.CENTER_VERTICAL
            setPadding(dp(4), dp(8), dp(10), dp(4))
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
        stampCard.addView(
            btnForgotten,
            LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(4)
            }
        )

        content.addView(
            stampCard,
            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(12)
            }
        )

        // === KORTTI 3: VIIMEISIMMÄT LEIMAUKSET ===
        historyCard = LinearLayout(context).apply {
            orientation = VERTICAL
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
            background = UiStyleHelper.rippleTransparentBg(context, 8f)
            gravity = Gravity.START or Gravity.CENTER_VERTICAL
            setPadding(dp(4), dp(8), dp(10), dp(4))
            minHeight = 0
            minimumHeight = dp(36)
            visibility = View.GONE
            setOnClickListener { loadMoreStamps() }
        }
        historyCard.addView(btnShowMore, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))

        content.addView(historyCard, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        scroll.addView(content, FrameLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
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
        todayCard.background = UiStyleHelper.roundedBg(context, card, border, 12f)
        stampCard.background = UiStyleHelper.roundedBg(context, card, border, 12f)
        historyCard.background = UiStyleHelper.roundedBg(context, card, border, 12f)
        btnRefresh.background = UiStyleHelper.rippleRoundedBg(context, headerBtn, borderStrong, 8f)
        txtNextShift.background = UiStyleHelper.roundedBg(context, cardAlt, border, 8f)
        btnOptionsToggle.background = UiStyleHelper.rippleRoundedBg(context, cardAlt, border, 8f)
        btnReasonSelector.background = UiStyleHelper.rippleRoundedBg(context, cardAlt, borderStrong, 8f)
        editComment.background = UiStyleHelper.roundedBg(context, cardAlt, borderStrong, 8f)
        shiftProgressTrack.background = UiStyleHelper.roundedBg(context, cardAlt, border, 99f, 0)
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        tickerHandler.removeCallbacks(liveDurationRunnable)
        tickerHandler.postDelayed(liveDurationRunnable, 30_000L)
    }

    override fun onDetachedFromWindow() {
        tickerHandler.removeCallbacks(liveDurationRunnable)
        super.onDetachedFromWindow()
    }

    fun onShow(forceNetwork: Boolean = false) {
        applyThemeColors()
        updateLocalizedLabels()
        loadState(forceNetwork = forceNetwork, fromSwipe = false)
    }

    fun refreshFromNetwork() {
        applyThemeColors()
        updateLocalizedLabels()
        loadState(forceNetwork = true, fromSwipe = false)
    }

    fun performAutoStamp(wantIn: Boolean, onFinished: () -> Unit) {
        applyThemeColors()
        updateLocalizedLabels()
        val en = DemoModeHelper.isEnglish(context)
        if (DemoModeHelper.isDemoEnabled(context)) {
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val currentlyIn = prefs.getBoolean("demo_stamped_in", false)
            val dirLabel = if (en) (if (wantIn) "In" else "Out") else (if (wantIn) "Sisään" else "Ulos")
            if (wantIn != currentlyIn) {
                recordDemoStamp(wantIn)
                ShiftWidgetProvider.updateAllWidgets(context)
                QuickStampTileService.requestTileUpdate(context)
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
            loadState(forceNetwork = false, fromSwipe = false)
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
                    val nowMs = System.currentTimeMillis()
                    lastSuccessfulStampMs = nowMs
                    lastNetworkFetchMs = nowMs
                    res.updatedState?.let {
                        currentState = it
                        selectedReasonCodeId = it.defaultReasonCode
                        lastRenderedState = null
                        renderState(it)
                    }
                    ShiftWidgetProvider.updateAllWidgets(context)
                    QuickStampTileService.requestTileUpdate(context)
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
                    loadState(forceNetwork = true, fromSwipe = false)
                    postDelayed(onFinished, 1400L)
                }
                is StampSubmitResult.ValidationRejected -> {
                    Toast.makeText(context, res.message, Toast.LENGTH_LONG).show()
                    loadState(forceNetwork = true, fromSwipe = false)
                }
                is StampSubmitResult.Failed -> {
                    Toast.makeText(context, res.message, Toast.LENGTH_LONG).show()
                    loadState(forceNetwork = true, fromSwipe = false)
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
        updateOptionsToggleText()
    }

    private fun updateOptionsToggleText() {
        val en = DemoModeHelper.isEnglish(context)
        val state = currentState
        val activeRc = state?.reasonCodes?.firstOrNull { it.id == selectedReasonCodeId }
            ?: state?.reasonCodes?.firstOrNull()
        val rcLabel = activeRc?.label ?: (if (en) "Normal working time" else "Normaali työaika")
        val comment = editComment.text?.toString()?.trim().orEmpty()
        val arrow = if (isOptionsExpanded) "▴" else "▾"
        val notePart = if (comment.isNotEmpty()) {
            val shortNote = if (comment.length > 18) comment.take(18) + "…" else comment
            "\"$shortNote\""
        } else {
            if (en) "+ Note" else "+ Lisätieto"
        }
        btnOptionsToggle.text = "$rcLabel  •  $notePart  $arrow"
        btnReasonSelector.text = "$rcLabel  ▾"
    }

    private fun isSameVisualState(a: StampingPageState?, b: StampingPageState): Boolean {
        if (a == null) return false
        return a.shiftTimes == b.shiftTimes &&
            a.shiftWorkplace == b.shiftWorkplace &&
            a.shiftDetails == b.shiftDetails &&
            a.nextDirection == b.nextDirection &&
            a.punchButtonText == b.punchButtonText &&
            a.defaultReasonCode == b.defaultReasonCode &&
            a.reasonCodes == b.reasonCodes &&
            a.latestStamps == b.latestStamps &&
            a.hasMoreStamps == b.hasMoreStamps
    }

    private fun buildBalanceRenderKey(): String {
        val enabled = PeriodBalanceManager.isEnabled(context)
        val b = cachedPeriodBalance
        return "$enabled|${PeriodBalanceManager.version}|${b?.periodStart}|${b?.diffMinutes}|${b?.plannedMinutes}|${b?.effectiveMinutes}"
    }

    private fun updatePeriodBalanceBanner() {
        val en = DemoModeHelper.isEnglish(context)
        val bal = cachedPeriodBalance
        if (!PeriodBalanceManager.isEnabled(context) ||
            DemoModeHelper.isDemoEnabled(context) ||
            bal == null ||
            bal.diffMinutes == 0
        ) {
            txtPeriodBalance.visibility = View.GONE
            return
        }
        val shortFmt = DateTimeFormatter.ofPattern("d.M.")
        val rangeStr = "${bal.periodStart.format(shortFmt)}–${bal.periodEnd.format(shortFmt)}"
        val diffStr = PeriodBalanceManager.formatSignedExact(bal.diffMinutes, en)
        val planH = PeriodBalanceManager.formatHoursDecimal(bal.plannedMinutes, en)
        val effH = PeriodBalanceManager.formatHoursDecimal(bal.effectiveMinutes, en)
        val prefix = if (en) "Period balance" else "Jakson saldo"
        txtPeriodBalance.text = "$prefix ($rangeStr): $diffStr  ($planH → $effH h)"

        if (bal.diffMinutes > 0) {
            txtPeriodBalance.setTextColor(Color.parseColor("#4ADE80"))
            txtPeriodBalance.background = UiStyleHelper.roundedBg(context, "#0F2E26", "#22C55E", 8f)
        } else {
            txtPeriodBalance.setTextColor(Color.parseColor("#FCA5A5"))
            txtPeriodBalance.background = UiStyleHelper.roundedBg(context, "#3F1D24", "#F87171", 8f)
        }
        txtPeriodBalance.visibility = View.VISIBLE
    }

    private fun renderStateIfChanged(state: StampingPageState, forceRender: Boolean = false) {
        val en = DemoModeHelper.isEnglish(context)
        val isDemo = DemoModeHelper.isDemoEnabled(context)
        val amoled = UiStyleHelper.isAmoled(context)
        val balKey = buildBalanceRenderKey()
        if (!forceRender &&
            isSameVisualState(lastRenderedState, state) &&
            lastRenderedNextShift == cachedNextShiftText &&
            lastRenderedLangEn == en &&
            lastRenderedDemo == isDemo &&
            lastRenderedAmoled == amoled &&
            lastRenderedBalanceKey == balKey
        ) {
            updateWorkingStatusPill()
            updateOptionsToggleText()
            return
        }
        lastRenderedState = state
        lastRenderedNextShift = cachedNextShiftText
        lastRenderedLangEn = en
        lastRenderedDemo = isDemo
        lastRenderedAmoled = amoled
        lastRenderedBalanceKey = balKey
        renderState(state)
    }

    private fun loadState(forceNetwork: Boolean, fromSwipe: Boolean = false) {
        val en = DemoModeHelper.isEnglish(context)
        val isDemo = DemoModeHelper.isDemoEnabled(context)
        loadJob?.cancel()

        val epoch = SessionCookieStore.sessionEpoch
        if (epoch != lastSessionEpoch || lastRenderedDemo != isDemo) {
            lastSessionEpoch = epoch
            currentState = null
            lastNetworkFetchMs = 0L
            lastRenderedState = null
            cachedNextShiftText = null
            cachedPeriodBalance = null
        }

        if (isDemo) {
            swipeRefresh.isRefreshing = false
            progressBar.visibility = View.GONE
            txtStatus.text = "Demo"
            btnPunch.setOnClickListener { handlePunchClick() }
            val demoState = buildDemoState()
            currentState = demoState
            selectedReasonCodeId = demoState.defaultReasonCode
            renderStateIfChanged(demoState, forceRender = true)
            return
        }

        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) {
            swipeRefresh.isRefreshing = false
            progressBar.visibility = View.GONE
            txtStatus.text = ""
            txtWorkingPill.visibility = View.GONE
            shiftProgressContainer.visibility = View.GONE
            txtPeriodBalance.visibility = View.GONE
            txtNextShift.visibility = View.GONE
            txtShiftTimes.visibility = View.VISIBLE
            txtShiftTimes.text = if (en) "Welcome" else "Tervetuloa"
            txtShiftWorkplace.visibility = View.VISIBLE
            txtShiftWorkplace.text = if (en) "Set organization ID in Settings" else "Aseta organisaatiotunnus asetuksista"
            txtShiftDetails.visibility = View.GONE
            lastRenderedState = null
            btnPunch.isEnabled = true
            btnPunch.text = if (en) "Open Settings" else "Avaa asetukset"
            btnPunch.background = UiStyleHelper.rippleRoundedBg(context, "#1982C4", "#38BDF8", 10f, "#44FFFFFF")
            btnPunch.setOnClickListener { onOpenSettings() }
            return
        }

        btnPunch.setOnClickListener { handlePunchClick() }

        val existing = currentState
        val nowMs = System.currentTimeMillis()
        if (!forceNetwork && existing != null && !existing.fromCache && (nowMs - lastNetworkFetchMs) < 45_000L) {
            swipeRefresh.isRefreshing = false
            progressBar.visibility = View.GONE
            txtStatus.text = UiStyleHelper.formatUpdatedLabel(context, lastNetworkFetchMs, isCache = false)
            renderStateIfChanged(existing)
            loadJob = scope.launch {
                val bal = withContext(Dispatchers.IO) { PeriodBalanceManager.computeCurrentPeriodBalance(context) }
                cachedPeriodBalance = bal
                renderStateIfChanged(existing)
            }
            return
        }

        loadJob = scope.launch {
            var cached: StampingPageState? = existing
            var cachedAtMs: Long = lastNetworkFetchMs

            val diskResult = withContext(Dispatchers.IO) {
                val diskState = if (cached == null) NumeronApiClient.loadCachedStampingState(context) else cached
                val diskMs = if (cached == null) NumeronApiClient.getStampingCacheSavedAtMs(context) else cachedAtMs
                val nextShift = if (cachedNextShiftText == null) findNextUpcomingShiftText() else cachedNextShiftText
                val bal = PeriodBalanceManager.computeCurrentPeriodBalance(context)
                arrayOf<Any?>(diskState, diskMs, nextShift, bal)
            }
            cached = diskResult[0] as? StampingPageState
            cachedAtMs = (diskResult[1] as? Long) ?: 0L
            cachedNextShiftText = diskResult[2] as? String
            cachedPeriodBalance = diskResult[3] as? PeriodBalanceResult
            if (cached != null) {
                if (currentState == null) {
                    currentState = cached
                    selectedReasonCodeId = cached.defaultReasonCode
                }
                renderStateIfChanged(currentState ?: cached)
            }

            val blocked = withContext(Dispatchers.IO) {
                BackgroundAuthHelper.isCredentialBlocked(context)
            }
            if (blocked) {
                swipeRefresh.isRefreshing = false
                progressBar.visibility = View.GONE
                txtStatus.text = if (en) "Check login" else "Tarkista tunnukset"
                Toast.makeText(
                    context,
                    if (en) "Login failed – please check username and password in Settings"
                    else "Kirjautuminen epäonnistui – tarkista käyttäjätunnus ja salasana asetuksista",
                    Toast.LENGTH_LONG
                ).show()
                return@launch
            }

            if (!fromSwipe) {
                progressBar.visibility = View.VISIBLE
            }
            txtStatus.text = if (cached != null && !forceNetwork) {
                if (en) "Updating…" else "Päivitetään…"
            } else {
                if (en) "Loading…" else "Ladataan…"
            }

            val fresh = NumeronApiClient.fetchStampingState(context, forceRefreshSession = false)
            swipeRefresh.isRefreshing = false
            progressBar.visibility = View.GONE
            if (fresh != null) {
                val fetchedAt = System.currentTimeMillis()
                lastNetworkFetchMs = fetchedAt
                currentState = fresh
                selectedReasonCodeId = fresh.defaultReasonCode
                if (fresh.shiftTimes.isEmpty() && cachedNextShiftText == null) {
                    cachedNextShiftText = withContext(Dispatchers.IO) { findNextUpcomingShiftText() }
                }
                txtStatus.text = UiStyleHelper.formatUpdatedLabel(context, fetchedAt, isCache = false)
                renderStateIfChanged(fresh)
                ShiftWidgetProvider.updateAllWidgets(context)
                QuickStampTileService.requestTileUpdate(context)
            } else {
                txtStatus.text = if (cached != null) {
                    UiStyleHelper.formatUpdatedLabel(context, cachedAtMs, isCache = true)
                        .ifEmpty { if (en) "Offline cache" else "Välimuisti" }
                } else {
                    if (en) "Load failed" else "Lataus epäonnistui"
                }
            }
        }
    }

    private fun renderState(state: StampingPageState) {
        val en = DemoModeHelper.isEnglish(context)

        updateWorkingStatusPill()
        updatePeriodBalanceBanner()

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

        // Vapaapäivänä näytetään seuraava tuleva vuoro kalenterivälimuistista (luettu IO-säikeessä)
        if (state.shiftTimes.isEmpty()) {
            val nextInfo = cachedNextShiftText
            if (nextInfo != null) {
                txtNextShift.text = nextInfo
                txtNextShift.visibility = View.VISIBLE
            } else {
                txtNextShift.visibility = View.GONE
            }
        } else {
            txtNextShift.visibility = View.GONE
        }

        updateOptionsToggleText()

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
            UiStyleHelper.rippleRoundedBg(context, "#B91C1C", "#F87171", 10f, "#44FFFFFF")
        } else {
            UiStyleHelper.rippleRoundedBg(context, "#15803D", "#22C55E", 10f, "#44FFFFFF")
        }

        renderStampsTable(state.latestStamps)
        btnShowMore.visibility = if (state.hasMoreStamps) View.VISIBLE else View.GONE
    }

    private fun parseStampRowDateTime(row: StampHistoryRow): LocalDateTime? {
        val timeMatch = Regex("(\\d{1,2}):(\\d{2})").find(row.timeText.trim()) ?: return null
        val hh = timeMatch.groupValues[1].toIntOrNull() ?: return null
        val mm = timeMatch.groupValues[2].toIntOrNull() ?: return null
        val time = try {
            LocalTime.of(hh, mm)
        } catch (_: Exception) {
            return null
        }

        val dayClean = row.dayText.trim().lowercase()
        val today = LocalDate.now()
        val date = when {
            dayClean == "tänään" || dayClean == "today" || dayClean == "idag" -> today
            dayClean == "eilen" || dayClean == "yesterday" || dayClean == "igår" -> today.minusDays(1)
            else -> {
                val m = Regex("(\\d{1,2})\\.(\\d{1,2})\\.(\\d{4})").find(dayClean)
                if (m != null) {
                    try {
                        LocalDate.of(m.groupValues[3].toInt(), m.groupValues[2].toInt(), m.groupValues[1].toInt())
                    } catch (_: Exception) {
                        null
                    }
                } else {
                    null
                }
            }
        } ?: return null

        return LocalDateTime.of(date, time)
    }

    private fun parseShiftBounds(shiftTimes: String, referenceInDt: LocalDateTime?): Pair<LocalDateTime, LocalDateTime>? {
        val m = Regex("(\\d{1,2}):(\\d{2})\\s*[-–—]\\s*(\\d{1,2}):(\\d{2})").find(shiftTimes) ?: return null
        val sTime = try {
            LocalTime.of(m.groupValues[1].toInt(), m.groupValues[2].toInt())
        } catch (_: Exception) {
            return null
        }
        val eTime = try {
            LocalTime.of(m.groupValues[3].toInt(), m.groupValues[4].toInt())
        } catch (_: Exception) {
            return null
        }
        val baseDate = referenceInDt?.toLocalDate() ?: LocalDate.now()
        var startDt = LocalDateTime.of(baseDate, sTime)
        var endDt = LocalDateTime.of(if (eTime.isBefore(sTime)) baseDate.plusDays(1) else baseDate, eTime)
        val now = LocalDateTime.now()
        // Jos yövuoro alkoi eilen ja päättyy tänä aamuna
        if (referenceInDt == null && eTime.isBefore(sTime) && now.toLocalTime().isBefore(eTime.plusHours(2))) {
            startDt = startDt.minusDays(1)
            endDt = endDt.minusDays(1)
        }
        return startDt to endDt
    }

    private fun updateShiftProgressBar(state: StampingPageState, inDt: LocalDateTime?) {
        val en = DemoModeHelper.isEnglish(context)
        if (!state.nextDirection.equals("OUT", ignoreCase = true) || state.shiftTimes.isBlank()) {
            shiftProgressContainer.visibility = View.GONE
            return
        }
        val bounds = parseShiftBounds(state.shiftTimes, inDt)
        if (bounds == null) {
            shiftProgressContainer.visibility = View.GONE
            return
        }
        val (shiftStart, shiftEnd) = bounds
        val totalMins = Duration.between(shiftStart, shiftEnd).toMinutes()
        if (totalMins <= 0L) {
            shiftProgressContainer.visibility = View.GONE
            return
        }
        val now = LocalDateTime.now()
        val elapsedMins = Duration.between(shiftStart, now).toMinutes()
        val remainingMins = Duration.between(now, shiftEnd).toMinutes()
        val ratio = (elapsedMins.toFloat() / totalMins.toFloat()).coerceIn(0f, 1f)
        val pct = (ratio * 100f).toInt().coerceIn(0, 100)

        fun fmtDur(mins: Long): String {
            val h = mins / 60L
            val m = mins % 60L
            return if (en) {
                if (h > 0L) "${h}h ${m}m" else "${m}m"
            } else {
                if (h > 0L) "$h h $m min" else "$m min"
            }
        }

        val statusLabel = when {
            remainingMins > 0L -> {
                if (en) "Remaining ${fmtDur(remainingMins)} • $pct%" else "Jäljellä ${fmtDur(remainingMins)} • $pct %"
            }
            remainingMins == 0L -> {
                if (en) "Shift complete • 100%" else "Vuoro täynnä • 100 %"
            }
            else -> {
                val over = -remainingMins
                if (en) "Overtime +${fmtDur(over)}" else "Ylitöillä +${fmtDur(over)}"
            }
        }
        txtShiftRemaining.text = statusLabel
        val fillColorHex = when {
            remainingMins < 0L -> "#F59E0B"
            ratio >= 0.85f -> "#22C55E"
            else -> "#38BDF8"
        }
        shiftProgressFill.background = UiStyleHelper.roundedBg(context, fillColorHex, fillColorHex, 99f, 0)

        val fillWeight = ratio.coerceIn(0.02f, 1f)
        (shiftProgressFill.layoutParams as LayoutParams).weight = fillWeight
        (shiftProgressRest.layoutParams as LayoutParams).weight = (1f - fillWeight).coerceAtLeast(0f)
        shiftProgressTrack.requestLayout()
        shiftProgressContainer.visibility = View.VISIBLE
    }

    private fun updateWorkingStatusPill() {
        val state = currentState
        if (state == null || !state.nextDirection.equals("OUT", ignoreCase = true)) {
            txtWorkingPill.visibility = View.GONE
            shiftProgressContainer.visibility = View.GONE
            return
        }
        val en = DemoModeHelper.isEnglish(context)
        val latestIn = state.latestStamps.firstOrNull { it.isIn }
        val inDt = latestIn?.let { parseStampRowDateTime(it) }
        val now = LocalDateTime.now()

        updateShiftProgressBar(state, inDt)

        if (inDt != null && !inDt.isAfter(now.plusMinutes(2))) {
            val mins = Duration.between(inDt, now).toMinutes().coerceAtLeast(0L)
            if (mins <= 20L * 60L) {
                val h = mins / 60L
                val m = mins % 60L
                val timeStr = inDt.format(DateTimeFormatter.ofPattern("HH:mm"))
                val durStr = if (en) {
                    if (h > 0L) "${h}h ${m}m" else "${m}m"
                } else {
                    if (h > 0L) "$h h $m min" else "$m min"
                }
                txtWorkingPill.text = if (en) {
                    "● Clocked in • $timeStr • $durStr"
                } else {
                    "● Töissä • sisään klo $timeStr • $durStr"
                }
                txtWorkingPill.visibility = View.VISIBLE
                return
            }
        }

        txtWorkingPill.text = if (en) "● Clocked in" else "● Töissä (leimattu sisään)"
        txtWorkingPill.visibility = View.VISIBLE
    }

    private fun findNextUpcomingShiftText(): String? {
        val en = DemoModeHelper.isEnglish(context)
        val shifts = if (DemoModeHelper.isDemoEnabled(context)) {
            DemoModeHelper.generateDemoWorkShifts(context)
        } else {
            CalendarSyncHelper.loadCachedShifts(context)
        } ?: return null

        val now = LocalDateTime.now()
        val next = shifts
            .filter { !it.isAllDayLeave && it.start.isAfter(now) }
            .minByOrNull { it.start }
            ?: return null

        val fiDow = arrayOf("Ma", "Ti", "Ke", "To", "Pe", "La", "Su")
        val enDow = arrayOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        val dow = (if (en) enDow else fiDow)[next.start.dayOfWeek.value - 1]
        val datePart = next.start.format(DateTimeFormatter.ofPattern("d.M."))
        val timePart = "${next.start.format(DateTimeFormatter.ofPattern("HH:mm"))}–${next.end.format(DateTimeFormatter.ofPattern("HH:mm"))}"
        val locPart = next.location.takeIf { it.isNotBlank() }?.let { " • $it" }.orEmpty()
        return if (en) {
            "Next shift: $dow $datePart $timePart$locPart"
        } else {
            "Seuraava vuoro: $dow $datePart klo $timePart$locPart"
        }
    }

    private fun renderStampsTable(rows: List<StampHistoryRow>) {
        stampsListContainer.removeAllViews()
        val en = DemoModeHelper.isEnglish(context)
        val isDemo = DemoModeHelper.isDemoEnabled(context)
        val dividerColor = Color.parseColor(UiStyleHelper.borderHex(context))

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
                    setBackgroundColor(dividerColor)
                }
                stampsListContainer.addView(divider, LayoutParams(LayoutParams.MATCH_PARENT, 1))
            }

            val rowView = LinearLayout(context).apply {
                orientation = HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(4), dp(11), dp(4), dp(11))
                if (!isDemo && row.rowId.isNotEmpty()) {
                    background = UiStyleHelper.rippleTransparentBg(context, 8f)
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
                background = UiStyleHelper.roundedBg(context, badgeBg, badgeBorder, 99f)
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
                updateOptionsToggleText()
                dialog.dismiss()
            }
            .setNegativeButton(if (en) "Cancel" else "Peruuta", null)
            .show()
    }

    private fun recentStampTimeLabel(): String? {
        val nowMs = System.currentTimeMillis()
        if (lastSuccessfulStampMs > 0L && (nowMs - lastSuccessfulStampMs) in 0L..(4L * 60_000L)) {
            return LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
        }
        val latest = currentState?.latestStamps?.firstOrNull() ?: return null
        val dt = parseStampRowDateTime(latest) ?: return null
        val diffMins = Duration.between(dt, LocalDateTime.now()).toMinutes()
        return if (diffMins in 0L..4L) dt.format(DateTimeFormatter.ofPattern("HH:mm")) else null
    }

    private fun handlePunchClick() {
        if (isSubmitting) return
        btnPunch.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)

        val recentTime = recentStampTimeLabel()
        if (recentTime != null && !DemoModeHelper.isDemoEnabled(context)) {
            val en = DemoModeHelper.isEnglish(context)
            AlertDialog.Builder(context)
                .setTitle(if (en) "Confirm stamp" else "Vahvista leimaus")
                .setMessage(
                    if (en) "You recorded a stamp just a moment ago ($recentTime). Do you want to stamp again?"
                    else "Teit leimauksen juuri äsken (klo $recentTime). Haluatko varmasti leimata uudelleen?"
                )
                .setPositiveButton(if (en) "Stamp" else "Leimaa") { _, _ ->
                    executePunchNow()
                }
                .setNegativeButton(if (en) "Cancel" else "Peruuta", null)
                .show()
            return
        }

        executePunchNow()
    }

    private fun executePunchNow() {
        val en = DemoModeHelper.isEnglish(context)

        if (DemoModeHelper.isDemoEnabled(context)) {
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val currentlyIn = prefs.getBoolean("demo_stamped_in", false)
            val wantIn = !currentlyIn
            recordDemoStamp(wantIn)
            editComment.setText("")
            ShiftWidgetProvider.updateAllWidgets(context)
            QuickStampTileService.requestTileUpdate(context)
            val dirLabel = if (en) (if (wantIn) "In" else "Out") else (if (wantIn) "Sisään" else "Ulos")
            Toast.makeText(
                context,
                if (en) "Demo stamp recorded ($dirLabel)" else "Demoleimaus tallennettu ($dirLabel)",
                Toast.LENGTH_SHORT
            ).show()
            loadState(forceNetwork = false, fromSwipe = false)
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
                    lastSuccessfulStampMs = System.currentTimeMillis()
                    lastNetworkFetchMs = lastSuccessfulStampMs
                    editComment.setText("")
                    isOptionsExpanded = false
                    optionsContainer.visibility = View.GONE
                    val dirLabel = if (en) {
                        if (result.directionUsed == "IN") "In" else "Out"
                    } else {
                        if (result.directionUsed == "IN") "Sisään" else "Ulos"
                    }
                    result.updatedState?.let {
                        currentState = it
                        selectedReasonCodeId = it.defaultReasonCode
                        txtStatus.text = UiStyleHelper.formatUpdatedLabel(context, lastSuccessfulStampMs, isCache = false)
                        renderStateIfChanged(it, forceRender = true)
                    }
                    ShiftWidgetProvider.updateAllWidgets(context)
                    QuickStampTileService.requestTileUpdate(context)
                    Toast.makeText(
                        context,
                        if (en) "Stamp confirmed ($dirLabel)" else "Leimaus vahvistettu ($dirLabel)",
                        Toast.LENGTH_SHORT
                    ).show()
                }
                is StampSubmitResult.AlreadyInDirection -> {
                    loadState(forceNetwork = true, fromSwipe = false)
                }
                is StampSubmitResult.ValidationRejected -> {
                    AlertDialog.Builder(context)
                        .setTitle(if (en) "Stamp not saved" else "Leimausta ei tallennettu")
                        .setMessage(result.message)
                        .setPositiveButton("OK", null)
                        .show()
                    loadState(forceNetwork = true, fromSwipe = false)
                }
                is StampSubmitResult.Failed -> {
                    Toast.makeText(context, result.message, Toast.LENGTH_LONG).show()
                    loadState(forceNetwork = true, fromSwipe = false)
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

            if (res != null) {
                val (newRows, hasMore) = res
                val updated = state.copy(
                    latestStamps = newRows,
                    hasMoreStamps = hasMore,
                    currentTake = newRows.size.coerceAtLeast(nextTake)
                )
                val updatedAt = System.currentTimeMillis()
                lastNetworkFetchMs = updatedAt
                currentState = updated
                withContext(Dispatchers.IO) {
                    NumeronApiClient.saveCachedStampingState(context, updated)
                }
                txtStatus.text = UiStyleHelper.formatUpdatedLabel(context, updatedAt, isCache = false)
                renderStateIfChanged(updated, forceRender = true)
            } else {
                txtStatus.text = ""
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
        btnOptionsToggle.isEnabled = !busy
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

    private fun dp(value: Int): Int = UiStyleHelper.dp(context, value)
}
