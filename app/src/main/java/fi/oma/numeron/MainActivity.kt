package fi.oma.numeron

import android.Manifest
import android.annotation.SuppressLint
import android.app.AlarmManager
import android.app.AlertDialog
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.RenderEffect
import android.graphics.Shader
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.CalendarContract
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.JsResult
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Date
import java.util.Locale

object VuorovahtiHelper {

    private val DEFAULT_SHIFT_KEYWORDS = listOf("työvuoro", "aamuvuoro", "iltavuoro", "yövuoro", "vuoro")

    fun getShiftEventColor(title: String, startHour: Int): Int {
        val lowerTitle = title.trim().lowercase(Locale.getDefault())
        return when {
            lowerTitle == "loma" || lowerTitle.contains("vuosiloma") -> Color.parseColor("#00ACC1")
            startHour in 5..10 -> Color.parseColor("#43A047")
            startHour in 11..17 -> Color.parseColor("#FB8C00")
            else -> Color.parseColor("#8E24AA")
        }
    }

    fun applyShiftColor(values: ContentValues, title: String, startHour: Int) {
        values.put(CalendarContract.Events.EVENT_COLOR, getShiftEventColor(title, startHour))
    }

    fun saveLastSyncStatus(context: Context, shiftCount: Int) {
        val timeFormat = SimpleDateFormat("dd.MM. 'klo' HH:mm", Locale.getDefault())
        val statusText = "Synkronoitu: ${timeFormat.format(Date())} ($shiftCount vuoroa)"
        context.getSharedPreferences("vuorovahti_prefs", Context.MODE_PRIVATE)
            .edit()
            .putString("last_sync_status", statusText)
            .putLong("last_sync_millis", System.currentTimeMillis())
            .apply()
    }

    fun getLastSyncStatus(context: Context): String {
        return context.getSharedPreferences("vuorovahti_prefs", Context.MODE_PRIVATE)
            .getString("last_sync_status", "Ei vielä synkronoitu") ?: "Ei vielä synkronoitu"
    }

    fun shouldRunDailySilentSync(context: Context): Boolean {
        if (!SettingsManager.isAutoSyncEnabled(context)) return false
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_CALENDAR) != PackageManager.PERMISSION_GRANTED
        ) {
            return false
        }
        val lastMs = context.getSharedPreferences("vuorovahti_prefs", Context.MODE_PRIVATE)
            .getLong("last_sync_millis", 0L)
        return (System.currentTimeMillis() - lastMs) > 18L * 60 * 60 * 1000L
    }

    fun saveLastTriggeredReminder(context: Context, infoText: String) {
        val timeFormat = SimpleDateFormat("dd.MM. 'klo' HH:mm", Locale.getDefault())
        val fullText = "${timeFormat.format(Date())} – $infoText"
        context.getSharedPreferences("vuorovahti_prefs", Context.MODE_PRIVATE)
            .edit()
            .putString("last_triggered_reminder", fullText)
            .apply()
    }

    fun getLastTriggeredReminder(context: Context): String {
        return context.getSharedPreferences("vuorovahti_prefs", Context.MODE_PRIVATE)
            .getString("last_triggered_reminder", "Ei vielä toteutuneita muistutuksia")
            ?: "Ei vielä toteutuneita muistutuksia"
    }

    fun getNextScheduledReminderText(
        context: Context,
        reminderMinutesBefore: Int = 30,
        shiftKeywords: List<String> = DEFAULT_SHIFT_KEYWORDS
    ): String {
        if (!SettingsManager.isStampNotificationEnabled(context)) {
            return "Ei käytössä (leimausmuistutukset kytketty pois)"
        }
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return "Kalenterilupa puuttuu – muistutuksia ei voida tarkistaa"
        }

        val now = System.currentTimeMillis()
        val twoWeeksAhead = now + 14L * 24 * 60 * 60 * 1000L
        val projection = arrayOf(
            CalendarContract.Events.TITLE,
            CalendarContract.Events.DESCRIPTION,
            CalendarContract.Events.DTSTART,
            CalendarContract.Events.DTEND
        )
        val selection = "${CalendarContract.Events.DTEND} > ? AND ${CalendarContract.Events.DTSTART} < ? AND ${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(now.toString(), twoWeeksAhead.toString())

        var earliestTrigger = Long.MAX_VALUE
        var earliestDesc = ""
        val dateFmt = SimpleDateFormat("dd.MM. 'klo' HH:mm", Locale.getDefault())
        val hourFmt = SimpleDateFormat("HH:mm", Locale.getDefault())

        context.contentResolver.query(
            CalendarContract.Events.CONTENT_URI,
            projection,
            selection,
            selectionArgs,
            "${CalendarContract.Events.DTSTART} ASC"
        )?.use { cursor ->
            while (cursor.moveToNext()) {
                val title = cursor.getString(0) ?: continue
                val desc = cursor.getString(1) ?: ""
                val startTime = cursor.getLong(2)
                val endTime = cursor.getLong(3)

                val lowerTitle = title.lowercase(Locale.getDefault())
                val isWorkShift = shiftKeywords.any { lowerTitle.contains(it) } &&
                    !lowerTitle.contains("loma") &&
                    !lowerTitle.contains("vapaa")

                if (isWorkShift) {
                    val shiftName = desc.lines().firstOrNull()?.takeIf { it.isNotBlank() } ?: title
                    val startTrigger = startTime - (reminderMinutesBefore * 60 * 1000L)
                    if (startTrigger in (now + 1) until earliestTrigger) {
                        earliestTrigger = startTrigger
                        earliestDesc = "${dateFmt.format(Date(startTrigger))} (Sisäänleimaus – $shiftName klo ${hourFmt.format(Date(startTime))})"
                    }
                    if (endTime > startTime) {
                        val endTrigger = endTime - (reminderMinutesBefore * 60 * 1000L)
                        if (endTrigger in (now + 1) until earliestTrigger) {
                            earliestTrigger = endTrigger
                            earliestDesc = "${dateFmt.format(Date(endTrigger))} (Ulosleimaus – $shiftName klo ${hourFmt.format(Date(endTime))})"
                        }
                    }
                }
            }
        }

        return if (earliestTrigger != Long.MAX_VALUE) {
            earliestDesc
        } else {
            "Ei tulevia työvuoroja kalenterissa seuraavan 14 vrk aikana"
        }
    }

    fun triggerConfirmHaptics(view: View) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            view.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
        } else {
            view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
        }
    }

    fun isDemoMode(username: String?, password: String?): Boolean {
        return username?.trim().equals("demo", ignoreCase = true) &&
            password?.trim().equals("demo", ignoreCase = true)
    }

    fun scheduleNextThreeWeekListCheck(context: Context) {
        try {
            val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
            val intent = Intent(context, ShiftAlarmReceiver::class.java).apply { putExtra("ACTION_TYPE", "CHECK_NEW_LIST") }
            val pi = PendingIntent.getBroadcast(context, 9991, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            if (!SettingsManager.isAutoSyncEnabled(context)) {
                alarmManager.cancel(pi)
                return
            }
            val anchorFriday = LocalDate.of(2026, 11, 6)
            val now = ZonedDateTime.now(ZoneId.systemDefault())
            var nextPublishDate = anchorFriday
            while (nextPublishDate.atTime(11, 5).atZone(ZoneId.systemDefault()).isBefore(now.plusMinutes(5))) {
                nextPublishDate = nextPublishDate.plusWeeks(3)
            }
            val triggerMillis = nextPublishDate.atTime(11, 5).atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            scheduleAlarmSafe(alarmManager, triggerMillis, pi)
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    fun ensureRemindersFromCalendar(
        context: Context,
        reminderMinutesBefore: Int = 30,
        shiftKeywords: List<String> = DEFAULT_SHIFT_KEYWORDS
    ) {
        scheduleNextThreeWeekListCheck(context)

        val prefs = context.getSharedPreferences("vuorovahti_prefs", Context.MODE_PRIVATE)
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager

        val oldCodes = prefs.getStringSet("active_alarm_codes", emptySet()) ?: emptySet()
        for (codeStr in oldCodes) {
            val code = codeStr.toIntOrNull() ?: continue
            val pi = PendingIntent.getBroadcast(
                context,
                code,
                Intent(context, ShiftAlarmReceiver::class.java),
                PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE
            )
            if (pi != null) {
                alarmManager.cancel(pi)
                pi.cancel()
            }
        }

        if (!SettingsManager.isStampNotificationEnabled(context)) {
            prefs.edit().remove("active_alarm_codes").apply()
            return
        }
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return
        }

        val now = System.currentTimeMillis()
        val twoWeeksAhead = now + 14L * 24 * 60 * 60 * 1000L
        val newCodes = mutableSetOf<String>()

        val projection = arrayOf(
            CalendarContract.Events.TITLE,
            CalendarContract.Events.DESCRIPTION,
            CalendarContract.Events.DTSTART,
            CalendarContract.Events.DTEND
        )
        val selection = "${CalendarContract.Events.DTEND} > ? AND ${CalendarContract.Events.DTSTART} < ? AND ${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(now.toString(), twoWeeksAhead.toString())
        val timeFmt = DateTimeFormatter.ofPattern("HH:mm")

        context.contentResolver.query(
            CalendarContract.Events.CONTENT_URI,
            projection,
            selection,
            selectionArgs,
            "${CalendarContract.Events.DTSTART} ASC"
        )?.use { cursor ->
            while (cursor.moveToNext()) {
                val title = cursor.getString(0) ?: continue
                val desc = cursor.getString(1) ?: ""
                val startTime = cursor.getLong(2)
                val endTime = cursor.getLong(3)

                val lowerTitle = title.lowercase(Locale.getDefault())
                val isWorkShift = shiftKeywords.any { lowerTitle.contains(it) } &&
                    !lowerTitle.contains("loma") &&
                    !lowerTitle.contains("vapaa")

                if (isWorkShift) {
                    val displayTitle = desc.ifEmpty { title }
                    val startStr = Instant.ofEpochMilli(startTime).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)

                    val startTrigger = startTime - (reminderMinutesBefore * 60 * 1000L)
                    if (startTrigger > now) {
                        val reqCode = (startTrigger / 60000L).toInt()
                        val startIntent = Intent(context, ShiftAlarmReceiver::class.java).apply {
                            putExtra("SHIFT_TITLE", displayTitle)
                            putExtra("SHIFT_TIME", startStr)
                            putExtra("IS_ENDING", false)
                        }
                        val startPi = PendingIntent.getBroadcast(
                            context, reqCode, startIntent,
                            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                        )
                        scheduleAlarmSafe(alarmManager, startTrigger, startPi)
                        newCodes.add(reqCode.toString())
                    }

                    if (endTime > startTime) {
                        val endStr = Instant.ofEpochMilli(endTime).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                        val endTrigger = endTime - (reminderMinutesBefore * 60 * 1000L)
                        if (endTrigger > now) {
                            val reqCode = (endTrigger / 60000L).toInt() + 1
                            val endIntent = Intent(context, ShiftAlarmReceiver::class.java).apply {
                                putExtra("SHIFT_TITLE", displayTitle)
                                putExtra("SHIFT_TIME", endStr)
                                putExtra("IS_ENDING", true)
                            }
                            val endPi = PendingIntent.getBroadcast(
                                context, reqCode, endIntent,
                                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                            )
                            scheduleAlarmSafe(alarmManager, endTrigger, endPi)
                            newCodes.add(reqCode.toString())
                        }
                    }
                }
            }
        }
        prefs.edit().putStringSet("active_alarm_codes", newCodes).apply()
    }

    fun scheduleAlarmSafe(alarmManager: AlarmManager, triggerTime: Long, pendingIntent: PendingIntent) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !alarmManager.canScheduleExactAlarms()) {
                alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerTime, pendingIntent)
            } else {
                alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerTime, pendingIntent)
            }
        } catch (_: SecurityException) {
            alarmManager.set(AlarmManager.RTC_WAKEUP, triggerTime, pendingIntent)
        }
    }

    fun getFreeDayGreetingIfApplicable(
        context: Context,
        shiftKeywords: List<String> = DEFAULT_SHIFT_KEYWORDS
    ): String? {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return null
        }

        val zone = ZoneId.systemDefault()
        val today = LocalDate.now(zone)
        val tomorrowStart = today.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        val lookAheadEnd = today.plusDays(8).atStartOfDay(zone).toInstant().toEpochMilli()

        val projection = arrayOf(CalendarContract.Events.TITLE, CalendarContract.Events.DTSTART)
        val selection = "${CalendarContract.Events.DTSTART} >= ? AND ${CalendarContract.Events.DTSTART} < ? AND ${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(tomorrowStart.toString(), lookAheadEnd.toString())

        var nextShiftDate: LocalDate? = null

        context.contentResolver.query(
            CalendarContract.Events.CONTENT_URI,
            projection,
            selection,
            selectionArgs,
            "${CalendarContract.Events.DTSTART} ASC"
        )?.use { cursor ->
            while (cursor.moveToNext()) {
                val title = cursor.getString(0) ?: continue
                val startMs = cursor.getLong(1)
                val lowerTitle = title.lowercase(Locale.getDefault())
                val isWorkShift = shiftKeywords.any { lowerTitle.contains(it) } &&
                    !lowerTitle.contains("loma") &&
                    !lowerTitle.contains("vapaa")

                if (isWorkShift) {
                    nextShiftDate = Instant.ofEpochMilli(startMs).atZone(zone).toLocalDate()
                    break
                }
            }
        }

        val freeDaysCount = if (nextShiftDate == null) {
            7
        } else {
            ChronoUnit.DAYS.between(today.plusDays(1), nextShiftDate).toInt()
        }
        if (freeDaysCount <= 0) return null

        val singleDayGreetings = listOf(
            "Huomenna ei ole vuoroa – ota rennosti ja nauti vapaasta!",
            "Vuoro paketissa ja huominen vapaana. Mukavaa huilipäivää!",
            "Hyvää huomista vapaapäivää, nollaa ajatukset ihan rauhassa!",
            "Huominen on pyhitetty vapaalle. Rentouttavaa vapaapäivää!",
            "Ansaittu hengähdystauko edessä – leppoisaa vapaapäivää!"
        )
        val multiDayGreetings = listOf(
            "Työputki takana ja vapaat edessä! Nauti tulevista vapaapäivistä!",
            "Useampi vapaapäivä edessä – mukavia ja rentouttavia vapaita!",
            "Vapaat alkoivat nyt. Ota ihan rennosti ja lataa akut rauhassa!",
            "Hyviä vapaita! Nyt on hyvin aikaa hengähtää ja puuhailla omia juttuja.",
            "Vuorot on tältä erää taputeltu – oikein leppoisia vapaapäiviä!"
        )

        return if (freeDaysCount == 1) singleDayGreetings.random() else multiDayGreetings.random()
    }
}

class MainActivity : AppCompatActivity() {

    private lateinit var mainColumn: LinearLayout
    private lateinit var webView: WebView
    private lateinit var btnStamp: Button
    private lateinit var btnWishes: Button
    private lateinit var btnCalendar: Button
    private lateinit var btnSync: Button
    private lateinit var btnSettings: Button
    private lateinit var btnClose: Button

    private lateinit var stampOverlay: LinearLayout
    private lateinit var overlayTitle: TextView
    private lateinit var overlayStatus: TextView
    private lateinit var overlayProgress: ProgressBar

    private var pendingSummaryDialog = false
    private var pendingAutoStamp = false
    private var pendingStampIsEnding = false
    private var autoStampClickDone = false
    private var autoStampRetryCount = 0
    private var waitingForListViewSync = false
    private var lastAutoLoginAttempt = 0L

    private var pagesRemainingToSync = 0
    private var missingFieldsCount = 0
    private var consecutiveEmptyPages = 0
    private var totalFoundInBatch = 0
    private var totalAddedInBatch = 0
    private var totalRemovedInBatch = 0
    private var isBackgroundListSync = false
    private var forceListOnNextCalendarLoad = false
    private var lastKnownBaseUrl = ""

    private data class SyncChangeItem(
        val eventId: Long,
        val type: String,
        val dateStr: String,
        val timeStr: String,
        val title: String
    )

    private val syncChangesList = mutableListOf<SyncChangeItem>()
    private val syncedDatesInBatch = mutableSetOf<LocalDate>()
    private val syncedShiftRangesInBatch = mutableSetOf<Pair<Long, Long>>()
    private var silentSyncWebView: WebView? = null
    private var isSilentSyncRunning = false

    private val revealSafetyRunnable = Runnable {
        if (::webView.isInitialized) webView.alpha = 1f
    }

    private val isDemoActive: Boolean
        get() = VuorovahtiHelper.isDemoMode(SettingsManager.getUsername(this), SettingsManager.getPassword(this))

    private val urlStamping: String
        get() = if (isDemoActive) "file:///android_asset/demo_shifts.html" else "${SettingsManager.getBaseUrl(this)}/WorktimeStamping"

    private val urlWishes: String
        get() = if (isDemoActive) "file:///android_asset/demo_shifts.html" else "${SettingsManager.getBaseUrl(this)}/PersonRequests/List"

    private val urlCalendar: String
        get() = if (isDemoActive) "file:///android_asset/demo_shifts.html" else "${SettingsManager.getBaseUrl(this)}/Calendar/Month"

    private fun requireBiometricAuth(title: String, onSuccess: () -> Unit) {
        if (!SettingsManager.isBiometricEnabled(this)) {
            onSuccess()
            return
        }
        val bm = BiometricManager.from(this)
        val authenticators = BiometricManager.Authenticators.BIOMETRIC_STRONG or BiometricManager.Authenticators.DEVICE_CREDENTIAL
        if (bm.canAuthenticate(authenticators) != BiometricManager.BIOMETRIC_SUCCESS) {
            onSuccess()
            return
        }

        val executor = ContextCompat.getMainExecutor(this)
        val biometricPrompt = BiometricPrompt(
            this,
            executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    super.onAuthenticationSucceeded(result)
                    VuorovahtiHelper.triggerConfirmHaptics(window.decorView)
                    onSuccess()
                }
            }
        )

        val promptInfo = BiometricPrompt.PromptInfo.Builder()
            .setTitle(title)
            .setSubtitle("Vahvista sormenjäljellä tai lukituskoodilla")
            .setAllowedAuthenticators(authenticators)
            .build()

        biometricPrompt.authenticate(promptInfo)
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)

        ViewCompat.setOnApplyWindowInsetsListener(findViewById(android.R.id.content)) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }
        lastKnownBaseUrl = if (isDemoActive) "demo" else SettingsManager.getBaseUrl(this)

        val bgDark = Color.parseColor("#0F172A")
        val rootFrame = FrameLayout(this).apply {
            layoutParams = FrameLayout.LayoutParams(-1, -1)
            setBackgroundColor(bgDark)
        }

        mainColumn = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = FrameLayout.LayoutParams(-1, -1)
            setBackgroundColor(bgDark)
        }

        VuorovahtiHelper.ensureRemindersFromCalendar(this)

        webView = WebView(this).apply {
            layoutParams = LinearLayout.LayoutParams(-1, 0, 1f)
            setBackgroundColor(bgDark)
            alpha = 0f
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                databaseEnabled = true
                setSupportZoom(true)
                builtInZoomControls = true
                displayZoomControls = false
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    isAlgorithmicDarkeningAllowed = true
                } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    @Suppress("DEPRECATION")
                    forceDark = WebSettings.FORCE_DARK_ON
                }
            }

            webChromeClient = object : WebChromeClient() {
                override fun onJsAlert(view: WebView?, url: String?, message: String?, result: JsResult?): Boolean {
                    val msg = (message ?: "").lowercase()
                    if (msg.contains("istunto") || msg.contains("session") || msg.contains("vanhentu") || msg.contains("kirjaudu")) {
                        result?.confirm()
                        navigateWebView(urlStamping)
                        return true
                    }
                    return super.onJsAlert(view, url, message, result)
                }

                override fun onJsConfirm(view: WebView?, url: String?, message: String?, result: JsResult?): Boolean {
                    val msg = (message ?: "").lowercase()
                    if (msg.contains("istunto") || msg.contains("session") || msg.contains("vanhentu") || msg.contains("kirjaudu")) {
                        result?.confirm()
                        navigateWebView(urlStamping)
                        return true
                    }
                    return super.onJsConfirm(view, url, message, result)
                }
            }

            webViewClient = object : WebViewClient() {
                override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                    super.onPageStarted(view, url, favicon)
                    preparePageTransition()
                    injectCleanTheme(view, revealAfter = false)
                }

                override fun onPageCommitVisible(view: WebView?, url: String?) {
                    super.onPageCommitVisible(view, url)
                    injectCleanTheme(view, revealAfter = true)
                }

                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    injectCleanTheme(view, revealAfter = true)
                    CookieManager.getInstance().flush()

                    val currentUrl = url ?: ""
                    updateNavigationState(currentUrl)
                    if (!isDemoActive) {
                        tryAutoLoginIfNeeded()
                    }

                    val base = SettingsManager.getBaseUrl(this@MainActivity).trimEnd('/')
                    if (!isDemoActive && !isBackgroundListSync &&
                        (currentUrl.trimEnd('/').equals(base, ignoreCase = true) ||
                            currentUrl.contains("/Home", ignoreCase = true) ||
                            currentUrl.contains("/Default", ignoreCase = true))
                    ) {
                        navigateWebView(urlStamping)
                        return
                    }

                    if (currentUrl.contains("/PersonRequests/", ignoreCase = true)) {
                        injectWishProtection()
                    }

                    if (currentUrl.contains("/WorktimeStamping", ignoreCase = true) && !pendingAutoStamp) {
                        webView.postDelayed({ triggerSilentDailySyncIfNeeded() }, 2500L)
                    }

                    if (pendingAutoStamp) {
                        scheduleAutoStampCheck(1000)
                    } else if (forceListOnNextCalendarLoad &&
                        (currentUrl.contains("/Calendar/", ignoreCase = true) || currentUrl.contains("demo_shifts", ignoreCase = true)) &&
                        !currentUrl.contains("login", ignoreCase = true)
                    ) {
                        forceListOnNextCalendarLoad = false
                        webView.postDelayed({ extractShiftsFromPage(forceList = true) }, 750)
                    } else if (waitingForListViewSync && currentUrl.contains("/Calendar/", ignoreCase = true)) {
                        waitingForListViewSync = false
                        webView.postDelayed({ extractShiftsFromPage(forceList = false) }, 750)
                    }
                }
            }

            addJavascriptInterface(CalendarBridge(), "AndroidBridge")
        }

        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, true)
        }

        val navWrapper = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(20, 12, 20, 20)
            setBackgroundColor(bgDark)
        }

        val buttonBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(12, 12, 12, 12)
            background = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = 36f
                setColor(Color.parseColor("#1E293B"))
                setStroke(2, Color.parseColor("#334155"))
            }
        }

        fun createNavButton(label: String, weight: Float = 1f, action: () -> Unit): Button {
            return Button(this).apply {
                text = label
                textSize = 13.5f
                setTextColor(Color.WHITE)
                isAllCaps = false
                setPadding(12, 32, 12, 32)
                minHeight = 0
                minimumHeight = 0
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, weight).apply {
                    marginStart = 6
                    marginEnd = 6
                }
                setOnClickListener { action() }
            }
        }

        btnStamp = createNavButton("Leimaus") { navigateWebView(urlStamping) }.apply {
            setOnLongClickListener { openSettings(); true }
        }
        btnWishes = createNavButton("Toiveet") { navigateWebView(urlWishes) }
        btnCalendar = createNavButton("Vuorot") { navigateWebView(urlCalendar) }
        btnSync = createNavButton("Synkronoi") { checkPermissionsAndSync() }.apply {
            visibility = View.GONE
        }
        btnSettings = createNavButton("⚙", 0.68f) { openSettings() }
        btnClose = createNavButton("✕", 0.68f) { finishAndRemoveTask() }

        buttonBar.addView(btnStamp)
        buttonBar.addView(btnWishes)
        buttonBar.addView(btnCalendar)
        buttonBar.addView(btnSync)
        buttonBar.addView(btnSettings)
        buttonBar.addView(btnClose)
        navWrapper.addView(buttonBar)

        mainColumn.addView(webView)
        mainColumn.addView(navWrapper)

        stampOverlay = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            layoutParams = FrameLayout.LayoutParams(-1, -1)
            setBackgroundColor(Color.parseColor("#EB0A0F1D"))
            isClickable = true
            isFocusable = true
            visibility = View.GONE
        }

        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(56, 56, 56, 48)
            layoutParams = LinearLayout.LayoutParams(-1, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                marginStart = 64
                marginEnd = 64
            }
            background = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = 36f
                setColor(Color.parseColor("#1E293B"))
                setStroke(2, Color.parseColor("#38BDF8"))
            }
        }

        overlayProgress = ProgressBar(this).apply {
            indeterminateTintList = ColorStateList.valueOf(Color.parseColor("#10B981"))
            layoutParams = LinearLayout.LayoutParams(96, 96).apply { bottomMargin = 32 }
        }

        overlayTitle = TextView(this).apply {
            text = "Automaattinen toiminto"
            textSize = 17f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        }

        overlayStatus = TextView(this).apply {
            text = "Yhdistetään palveluun..."
            textSize = 13.5f
            setTextColor(Color.parseColor("#CBD5E1"))
            gravity = Gravity.CENTER
            setPadding(0, 16, 0, 36)
        }

        val btnCancelOverlay = Button(this).apply {
            text = "Peruuta"
            textSize = 12f
            isAllCaps = false
            setTextColor(Color.parseColor("#E2E8F0"))
            background = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = 20f
                setColor(Color.parseColor("#334155"))
            }
            setOnClickListener {
                pendingAutoStamp = false
                autoStampClickDone = false
                isBackgroundListSync = false
                forceListOnNextCalendarLoad = false
                pagesRemainingToSync = 0
                hideStampOverlay()
            }
        }

        card.addView(overlayProgress)
        card.addView(overlayTitle)
        card.addView(overlayStatus)
        card.addView(btnCancelOverlay)
        stampOverlay.addView(card)

        rootFrame.addView(mainColumn)
        rootFrame.addView(stampOverlay)
        setContentView(rootFrame)

        handleIncomingIntent(intent)
        updateNavigationState(urlStamping)

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (stampOverlay.visibility == View.VISIBLE) {
                    pendingAutoStamp = false
                    isBackgroundListSync = false
                    hideStampOverlay()
                } else if (webView.canGoBack()) {
                    preparePageTransition()
                    webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })

        if (SettingsManager.isFirstRun(this) && !pendingAutoStamp && !isBackgroundListSync) {
            val missing = getRequiredPermissions().filter {
                ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
            }
            if (missing.isNotEmpty()) {
                ActivityCompat.requestPermissions(this, missing.toTypedArray(), 105)
            }
            openSettings()
        }

        if (!isBackgroundListSync) {
            navigateWebView(urlStamping)
        }
    }

    private fun preparePageTransition() {
        if (!::webView.isInitialized) return
        webView.removeCallbacks(revealSafetyRunnable)
        webView.alpha = 0f
        webView.postDelayed(revealSafetyRunnable, 1500L)
    }

    private fun revealWebView() {
        if (!::webView.isInitialized) return
        webView.removeCallbacks(revealSafetyRunnable)
        if (webView.alpha < 1f) {
            webView.alpha = 1f
        }
    }

    private fun navigateWebView(url: String) {
        if (!::webView.isInitialized) return
        preparePageTransition()
        webView.loadUrl(url)
    }

    private fun openSettings() {
        startActivity(Intent(this, SettingsActivity::class.java))
    }

    override fun onResume() {
        super.onResume()
        if (pendingSummaryDialog) {
            pendingSummaryDialog = false
            webView.postDelayed({ showSyncSummaryDialog() }, 300)
        }
        VuorovahtiHelper.ensureRemindersFromCalendar(this)
        val currentBase = if (isDemoActive) "demo" else SettingsManager.getBaseUrl(this)
        if (lastKnownBaseUrl.isNotEmpty() && lastKnownBaseUrl != currentBase) {
            lastKnownBaseUrl = currentBase
            navigateWebView(urlStamping)
        } else if (::webView.isInitialized && !isDemoActive) {
            tryAutoLoginIfNeeded()
        }
    }

    override fun onDestroy() {
        if (::webView.isInitialized) {
            webView.removeCallbacks(revealSafetyRunnable)
        }
        (silentSyncWebView?.parent as? ViewGroup)?.removeView(silentSyncWebView)
        silentSyncWebView?.destroy()
        silentSyncWebView = null
        super.onDestroy()
    }

    private fun injectCleanTheme(view: WebView?, revealAfter: Boolean) {
        val css = """
            :root { color-scheme: dark; }
            html, body {
                background: #0F172A !important;
                background-color: #0F172A !important;
                background-image: none !important;
                color: #E2E8F0 !important;
                font-family: sans-serif !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            a { color: #38BDF8; }
            nav.navbar, nav.loginnav, .loginnav, footer, img[src*="visma"],
            .container > h1.clear, .container-fluid > h1.clear, h1.clear,
            #wfm-modal-div:empty, .alert:empty, .messageBox:empty, .infoBox:empty, .statusBox:empty,
            #mobile_AddButton, #mobileViewDropdown, .whitebox hr,
            #cookieConsent, .cookie-consent, .cookie-banner, #cookie-banner, .cc-window, .cc-banner {
                display: none !important;
            }
            .container, .container-fluid, .content-container {
                width: 100% !important;
                max-width: 100% !important;
                padding: 14px 10px 24px 10px !important;
                margin: 0 !important;
                background-color: #0F172A !important;
            }
            .content {
                float: none !important;
                width: 100% !important;
                max-width: 440px !important;
                margin: 0 auto !important;
                padding: 24px 14px !important;
                position: static !important;
                top: auto !important;
                left: auto !important;
                transform: none !important;
            }
            .blurbox {
                background: transparent !important;
                background-color: transparent !important;
                background-image: none !important;
                backdrop-filter: none !important;
                -webkit-backdrop-filter: none !important;
                border: none !important;
                box-shadow: none !important;
                padding: 12px 0 8px 0 !important;
                margin: 0 !important;
                text-align: center !important;
            }
            .blurbox h1 {
                color: #38BDF8 !important;
                font-size: 24px !important;
                font-weight: bold !important;
                margin: 0 0 14px 0 !important;
                text-shadow: none !important;
            }
            .whitebox, .panel, .panel-default, .well, .list-group-item,
            .modal-content, .popover, .popover-content, .popover-title, .tooltip-inner {
                background-color: #1E293B !important;
                background-image: none !important;
                border: 1px solid #334155 !important;
                border-radius: 14px !important;
                box-shadow: none !important;
                color: #E2E8F0 !important;
            }
            .whitebox {
                padding: 20px 18px !important;
                margin: 0 !important;
                min-height: 0 !important;
                height: auto !important;
            }
            #LoginForm .form-group { margin: 0 0 14px 0 !important; }
            #LoginForm .control-label {
                display: block !important;
                width: 100% !important;
                float: none !important;
                text-align: left !important;
                padding: 0 0 6px 2px !important;
                margin: 0 !important;
                font-size: 13px !important;
            }
            #LoginForm .col-sm-7, #LoginForm .col-sm-offset-4 {
                width: 100% !important;
                float: none !important;
                margin-left: 0 !important;
                padding: 0 !important;
            }
            #LoginForm .form-control {
                height: 44px !important;
                font-size: 16px !important;
                padding: 10px 12px !important;
            }
            #LoginForm .pull-left, #LoginForm .pull-right {
                float: none !important;
                display: block !important;
                text-align: center !important;
                margin: 6px 0 !important;
                font-size: 13px !important;
            }
            #LoginForm input[type="submit"] {
                height: 46px !important;
                font-size: 15px !important;
                margin-top: 12px !important;
            }
            .validation-summary-errors, .field-validation-error {
                background-color: #450A0A !important;
                border: 1px solid #EF4444 !important;
                border-radius: 10px !important;
                color: #FCA5A5 !important;
                padding: 10px 12px !important;
                margin-bottom: 12px !important;
                font-size: 13px !important;
                display: block !important;
            }
            .validation-summary-errors ul { margin: 0 !important; padding-left: 18px !important; }
            .panel, .panel-default { margin-bottom: 10px !important; }
            .panel-body { padding: 12px !important; }
            .modal-header, .modal-footer, .panel-heading, .panel-footer {
                background-color: #1E293B !important;
                border-color: #334155 !important;
                color: #F8FAFC !important;
            }
            .close { color: #94A3B8 !important; text-shadow: none !important; opacity: 0.9 !important; }
            .fog-of-war, .drw-fog-of-war { background-color: rgba(15, 23, 42, 0.78) !important; }
            label, .control-label, .punching-shift-caption, .previous-stamps-caption, .punching-caption, .forgotten-stamp-labels {
                color: #94A3B8 !important;
                font-weight: 600 !important;
            }
            .form-control, input[type="text"], input[type="password"], input[type="number"], input[type="date"], input[type="time"],
            select, textarea, .k-textbox, .k-input {
                background: #0F172A !important;
                background-color: #0F172A !important;
                background-image: none !important;
                color: #FFFFFF !important;
                border: 1px solid #334155 !important;
                border-radius: 10px !important;
                box-shadow: none !important;
            }
            .form-control:focus, input:focus, select:focus, textarea:focus { border-color: #38BDF8 !important; outline: none !important; }
            input[type="checkbox"], input[type="radio"] { accent-color: #0284C7 !important; }
            .btn, .btn-default, .dropdown-toggle, .punch-button,
            #pcViewButt, #todayButt, #pcAddButt, #dropdownMenu1, #dropdownMenu2, #dropdownMenuStampDirection {
                background: #0F172A !important;
                background-color: #0F172A !important;
                background-image: none !important;
                color: #E2E8F0 !important;
                border: 1px solid #334155 !important;
                border-radius: 10px !important;
                box-shadow: none !important;
                text-shadow: none !important;
            }
            .btn:hover, .btn:focus, .btn:active, .open > .dropdown-toggle.btn-default {
                background: #1E293B !important;
                background-color: #1E293B !important;
                color: #38BDF8 !important;
                border-color: #38BDF8 !important;
            }
            .btn-primary, input[type="submit"], #punchButton, #punchForgottenButton {
                background: #0284C7 !important;
                background-color: #0284C7 !important;
                background-image: none !important;
                border: none !important;
                border-radius: 12px !important;
                color: #FFFFFF !important;
                font-weight: bold !important;
                text-shadow: none !important;
            }
            .btn-primary:hover, .btn-primary:focus, #punchButton:hover, #punchForgottenButton:hover {
                background: #0369A1 !important;
                color: #FFFFFF !important;
            }
            .btn-text, .btn-link {
                color: #38BDF8 !important;
                background: transparent !important;
                border: none !important;
                box-shadow: none !important;
            }
            .dropdown-menu {
                background-color: #1E293B !important;
                border: 1px solid #334155 !important;
                border-radius: 10px !important;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5) !important;
            }
            .dropdown-menu > li > a, .dropdown-menu li a { color: #E2E8F0 !important; background: transparent !important; padding: 10px 14px !important; }
            .dropdown-menu > li > a:hover, .dropdown-menu > li > a:focus { background-color: #334155 !important; color: #38BDF8 !important; }
            .dropdown-header { color: #94A3B8 !important; }
            .k-widget, .k-dropdown, .k-dropdown-wrap, .k-picker-wrap, .k-numeric-wrap, .k-multiselect-wrap,
            .k-state-default, .k-state-hover, .k-state-focused, .k-button, .k-select {
                background: #0F172A !important;
                background-color: #0F172A !important;
                background-image: none !important;
                color: #E2E8F0 !important;
                border-color: #334155 !important;
                box-shadow: none !important;
            }
            .k-animation-container, .k-popup, .k-list-container, .k-list-scroller, ul.k-list,
            .k-calendar, .k-calendar-container, .k-column-menu, .k-filter-menu, .k-list-filter {
                background: #1E293B !important;
                background-color: #1E293B !important;
                background-image: none !important;
                color: #E2E8F0 !important;
                border-color: #334155 !important;
            }
            .k-list .k-item, .k-column-menu .k-item, select option { background-color: #1E293B !important; color: #E2E8F0 !important; }
            .k-list .k-item:hover, .k-list .k-state-hover, .k-list .k-state-focused,
            .k-list .k-state-selected, .k-state-selected, .k-grid tr.k-state-selected td {
                background-color: #0284C7 !important;
                color: #FFFFFF !important;
            }
            .k-icon { filter: invert(0.85) brightness(1.2) !important; }
            .k-grid, .k-grid-content, .k-grid-header, .k-grid-header-wrap, .k-pager-wrap {
                background-color: #1E293B !important;
                color: #E2E8F0 !important;
                border-color: #334155 !important;
            }
            .k-grid-header th.k-header, .k-grid-header th.k-header .k-link {
                background-color: #0F172A !important;
                color: #94A3B8 !important;
                border-color: #334155 !important;
            }
            .k-grid tr { background-color: #1E293B !important; color: #E2E8F0 !important; }
            .k-grid tr.k-alt { background-color: #172033 !important; }
            .k-grid td { border-color: #334155 !important; color: #E2E8F0 !important; }
            .k-grid tr:hover td { background-color: #334155 !important; color: #FFFFFF !important; }
            .punching-balance-overview-container, .punching-balance-container, .punching-weekbalance-container { display: none !important; }
            #panel-body-main { padding: 10px 12px !important; height: auto !important; min-height: 0 !important; }
            .punching-overview-container { display: block !important; height: auto !important; min-height: 0 !important; padding: 0 !important; margin: 0 !important; }
            .punching-shift-container {
                width: 100% !important;
                max-width: 100% !important;
                height: auto !important;
                min-height: 0 !important;
                background-color: #334155 !important;
                border: 1px solid #475569 !important;
                border-radius: 12px !important;
                padding: 12px 14px !important;
                margin: 0 !important;
                display: flex !important;
                flex-direction: column !important;
                gap: 4px !important;
            }
            .punching-shift-caption { color: #BAE6FD !important; font-size: 11px !important; letter-spacing: 0.05em !important; text-transform: uppercase !important; margin: 0 !important; }
            .punching-shift-name { color: #F8FAFC !important; font-size: 15px !important; font-weight: bold !important; line-height: 1.3 !important; margin: 0 !important; }
            #panel-body-tabs, .punching-events-container-header, .punching-events-caption,
            .tab-content-wts, .tab-pane-wts, #latestStampsContainer, .punching-bottom-container,
            .punching-previous-stamps, .punching-previous-stamps-container-header, .punching-show-more-button {
                background: transparent !important;
                background-color: transparent !important;
                color: #E2E8F0 !important;
            }
            .nav-tabs-wts { border-bottom: 1px solid #334155 !important; background: transparent !important; }
            .nav-tabs-wts > li > a, .wts-tab-item > a {
                background: transparent !important;
                background-color: transparent !important;
                color: #94A3B8 !important;
                border: none !important;
            }
            .nav-tabs-wts > li.active > a, .nav-tabs-wts > li.active > a:focus, .nav-tabs-wts > li.active > a:hover {
                background: transparent !important;
                background-color: transparent !important;
                color: #38BDF8 !important;
                border: none !important;
                border-bottom: 2px solid #38BDF8 !important;
            }
            .table, .table > tbody, .table > tbody > tr, .table > tbody > tr > td, .table > tbody > tr > th,
            .table-active, .table-active > tbody > tr, .table-active > tbody > tr > td, .table-active > td,
            #table-latest-stamps, #table-latest-stamps tbody, #table-latest-stamps tr, #table-latest-stamps td {
                background: transparent !important;
                background-color: transparent !important;
                background-image: none !important;
                color: #E2E8F0 !important;
            }
            #table-latest-stamps tr { border-bottom: 1px solid #334155 !important; }
            #table-latest-stamps tr:hover, #table-latest-stamps tr:hover td,
            #table-latest-stamps tr:active, #table-latest-stamps tr:active td {
                background-color: #334155 !important;
                color: #FFFFFF !important;
            }
            #table-latest-stamps td { border: none !important; padding: 10px 6px !important; }
            .visma-icon-arrow-next-icon { filter: invert(0.85) brightness(1.2) !important; }
            #forgotStampPanel { background-color: #1E293B !important; color: #E2E8F0 !important; }
            .fixed-menu-bar { display: flex !important; flex-wrap: wrap !important; gap: 8px !important; margin: 0 0 10px 0 !important; }
            .fixed-menu-bar .col-sm-8 { width: 100% !important; padding: 0 !important; display: flex !important; flex-wrap: wrap !important; gap: 8px !important; }
            .fixed-menu-bar .col-sm-8 .btn, .fixed-menu-bar .col-sm-8 .btn-group { flex: 1 1 auto !important; margin: 0 !important; }
            .fixed-menu-bar .col-sm-8 .btn-group .btn { width: 100% !important; }
            .fixed-menu-bar .form-inline.pull-right { width: 100% !important; float: none !important; margin: 4px 0 0 0 !important; display: flex !important; align-items: center !important; gap: 8px !important; }
            .fixed-menu-bar .form-inline .form-group { flex: 1 !important; margin: 0 !important; }
            .fixed-menu-bar #filterOptions { width: 100% !important; }
            .calendar-body, .calendar-heading {
                background-color: #1E293B !important;
                box-shadow: none !important;
                border: 1px solid #334155 !important;
                border-radius: 14px !important;
                padding: 8px !important;
                margin-bottom: 10px !important;
                height: auto !important;
                min-height: 0 !important;
                max-height: none !important;
                overflow: visible !important;
            }
            .calendar-heading {
                display: flex !important;
                flex-wrap: wrap !important;
                align-items: center !important;
                justify-content: space-between !important;
                gap: 8px !important;
                padding: 10px !important;
                position: static !important;
            }
            .calendar-heading .monthSelector, .calendar-heading .weekSelector { display: contents !important; }
            .calendar-heading .monthSelector .panel-body, .calendar-heading .weekSelector .panel-body {
                order: 1 !important;
                width: 100% !important;
                height: auto !important;
                min-height: 0 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: space-between !important;
                padding: 0 4px 4px 4px !important;
                margin: 0 !important;
                float: none !important;
                position: static !important;
            }
            #monthText, #weekText, .calendar-heading .view-label {
                color: #F8FAFC !important;
                font-size: 18px !important;
                font-weight: bold !important;
                margin: 0 !important;
                line-height: 1.2 !important;
            }
            #pc_AddButton {
                order: 2 !important;
                width: 100% !important;
                height: auto !important;
                min-height: 0 !important;
                display: flex !important;
                gap: 8px !important;
                margin: 0 !important;
                float: none !important;
                position: static !important;
            }
            #pc_AddButton > .btn-group, #pc_AddButton > .dropdown {
                flex: 1 !important;
                margin: 0 !important;
                display: block !important;
                position: relative !important;
            }
            #pcAddButt, #pc_AddButton .filterButton {
                width: 100% !important;
                height: 36px !important;
                min-height: 36px !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                padding: 6px 10px !important;
                margin: 0 !important;
                font-size: 13px !important;
                line-height: 1.2 !important;
                position: static !important;
                top: auto !important;
            }
            #pcTodayButton, #pcViewDropdown {
                order: 3 !important;
                flex: 1 1 46% !important;
                height: auto !important;
                min-height: 0 !important;
                display: block !important;
                margin: 0 !important;
                float: none !important;
                position: relative !important;
                top: auto !important;
            }
            #todayButt, #pcViewButt {
                width: 100% !important;
                max-width: none !important;
                min-width: 0 !important;
                height: 36px !important;
                min-height: 36px !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                padding: 6px 10px !important;
                margin: 0 !important;
                font-size: 13px !important;
                line-height: 1.2 !important;
                position: static !important;
                top: auto !important;
            }
            #pcViewDropdown .dropdown-menu, #pc_AddButton .dropdown-menu {
                z-index: 1060 !important;
                top: 100% !important;
                margin-top: 4px !important;
            }
            #pcViewDropdown .dropdown-menu { right: 0 !important; left: auto !important; }
            #calendar-content {
                height: auto !important;
                min-height: 0 !important;
                max-height: none !important;
                overflow: visible !important;
                clear: both !important;
                position: static !important;
            }
            #calendar-content hr { border-color: #334155 !important; margin: 8px 0 !important; }
            #calendar-content .list-week-header, #calendar-content .week-header, #calendar-content h3, #calendar-content h4 {
                color: #38BDF8 !important;
                border-color: #334155 !important;
                background: transparent !important;
            }
            #calendar-content .list-day-header, #calendar-content .day-header, #calendar-content .list-date-header {
                color: #F8FAFC !important;
                background: transparent !important;
            }
            #calendar-content .list-item, #calendar-content .list-item-work, #calendar-content .list-item-content,
            #calendar-content .calendar-list-item, #calendar-content .schedule-item, #calendar-content .schedule-item-work,
            #calendar-content .list-day-item, #calendar-content .shift-item {
                background-color: #1E293B !important;
                background-image: none !important;
                color: #F1F5F9 !important;
                border-color: #334155 !important;
            }
            #calendar-content .list-item, #calendar-content .calendar-list-item, #calendar-content .schedule-item {
                border: 1px solid #334155 !important;
                border-left: 4px solid #0284C7 !important;
                border-radius: 12px !important;
                padding: 8px 10px !important;
                margin: 6px 0 !important;
            }
            #calendar-content .list-item *, #calendar-content .calendar-list-item *, #calendar-content .schedule-item * {
                color: #F1F5F9 !important;
                border-color: #334155 !important;
            }
            .month-table { width: 100% !important; table-layout: fixed !important; background-color: #1E293B !important; border-collapse: collapse !important; }
            .month-week-days td { background-color: #0F172A !important; color: #94A3B8 !important; border: 1px solid #334155 !important; padding: 5px 1px !important; font-weight: bold !important; font-size: 11px !important; }
            .month-week-number { width: 22px !important; background-color: #0F172A !important; color: #64748B !important; border: 1px solid #334155 !important; text-align: center !important; font-size: 10px !important; }
            td.month-day { background-color: #1E293B !important; border: 1px solid #334155 !important; vertical-align: top !important; padding: 2px !important; overflow: hidden !important; }
            td.month-day.day-different-month { background-color: #131C2E !important; opacity: 0.72 !important; }
            td.month-day.todayTd { background-color: #1E3A5F !important; border: 1px solid #38BDF8 !important; }
            .dayNum { color: #CBD5E1 !important; font-weight: bold !important; font-size: 11px !important; padding-left: 2px !important; }
            .today .dayNum { color: #38BDF8 !important; }
            .month-item { border-radius: 5px !important; padding: 2px 3px !important; margin-top: 2px !important; font-size: 10px !important; line-height: 1.2 !important; overflow: hidden !important; text-overflow: ellipsis !important; }
            .month-item.work { background-color: #0284C7 !important; color: #FFFFFF !important; border: none !important; }
            .month-item.work .itemTimes, .month-item.work .itemName { color: #FFFFFF !important; display: block !important; }
            .month-item.request { background-color: #7C3AED !important; color: #FFFFFF !important; }
            .month-item.absence { background-color: #D97706 !important; color: #FFFFFF !important; }
            .month-item.opportunity { background-color: #059669 !important; color: #FFFFFF !important; }
            .month-item.hidden-items-box { background-color: #334155 !important; color: #38BDF8 !important; text-align: center !important; font-weight: bold !important; }
            [style*="background-color: #fff"], [style*="background-color:#fff"], [style*="background-color: rgb(255, 255, 255)"],
            [style*="background: #fff"], [style*="background:#fff"], [style*="background: rgb(255, 255, 255)"] {
                background-color: #1E293B !important;
                background-image: none !important;
                color: #F1F5F9 !important;
                border-color: #334155 !important;
            }
        """.trimIndent().replace("\n", " ")

        val hasCreds = SettingsManager.getUsername(this).isNotEmpty() && SettingsManager.getPassword(this).isNotEmpty()

        val js = """
            (function() {
                var cssText = `$css`;
                function fixCalendarListTheme() {
                    var rootEl = document.getElementById('calendar-content') || document.querySelector('.calendar-body');
                    if (!rootEl) return;
                    var nodes = rootEl.querySelectorAll('div, table, tbody, tr, td, section, article, ul, li');
                    for (var i = 0; i < nodes.length; i++) {
                        var el = nodes[i];
                        if (el.classList && (el.classList.contains('month-item') || el.classList.contains('month-day'))) continue;
                        var cs = window.getComputedStyle(el);
                        var bg = cs.backgroundColor;
                        var m = bg && bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
                        if (m) {
                            var a = m[4] !== undefined ? parseFloat(m[4]) : 1;
                            if (a > 0.1 && parseInt(m[1], 10) > 205 && parseInt(m[2], 10) > 205 && parseInt(m[3], 10) > 205) {
                                el.style.setProperty('background-color', '#1E293B', 'important');
                                el.style.setProperty('background-image', 'none', 'important');
                                el.style.setProperty('border-color', '#334155', 'important');
                                if (el.offsetHeight >= 44 && el.offsetHeight <= 260 && el.offsetWidth > 180) {
                                    el.style.setProperty('border', '1px solid #334155', 'important');
                                    el.style.setProperty('border-left', '4px solid #0284C7', 'important');
                                    el.style.setProperty('border-radius', '12px', 'important');
                                }
                            }
                        }
                        var col = cs.color;
                        var cm = col && col.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
                        if (cm) {
                            var r = parseInt(cm[1], 10), g = parseInt(cm[2], 10), b = parseInt(cm[3], 10);
                            if (r < 130 && g < 130 && b < 130) {
                                el.style.setProperty('color', '#E2E8F0', 'important');
                            }
                        }
                    }
                }
                function attachTheme() {
                    var root = document.documentElement || document.head;
                    if (!root) return false;
                    var style = document.getElementById('custom-numeron-theme');
                    if (!style) {
                        style = document.createElement('style');
                        style.id = 'custom-numeron-theme';
                        style.textContent = cssText;
                    }
                    if (style.parentNode !== root || root.lastElementChild !== style) {
                        root.appendChild(style);
                    }
                    fixCalendarListTheme();
                    return true;
                }
                function dismissCookieBanner() {
                    var btns = document.querySelectorAll('button, a, input[type="button"], input[type="submit"]');
                    for (var i = 0; i < btns.length; i++) {
                        var b = btns[i];
                        var t = (b.innerText || b.value || '').trim().toLowerCase();
                        if (t === 'hyväksy' || t === 'hyväksy evästeet' || t === 'accept') {
                            var box = b.closest('div, section, aside, footer, header, nav');
                            var boxTxt = box ? (box.innerText || '').toLowerCase() : '';
                            if (boxTxt.indexOf('eväste') !== -1 || boxTxt.indexOf('cookie') !== -1) {
                                if (!b.dataset.cookieClicked) {
                                    b.dataset.cookieClicked = '1';
                                    b.click();
                                }
                                if (box && box !== document.body && !box.querySelector('#LoginForm')) {
                                    box.style.setProperty('display', 'none', 'important');
                                }
                            }
                        }
                    }
                }
                attachTheme();
                dismissCookieBanner();
                if (!window._numeronThemeObserver) {
                    window._numeronThemeObserver = new MutationObserver(function() {
                        attachTheme();
                        dismissCookieBanner();
                    });
                    window._numeronThemeObserver.observe(document, { childList: true, subtree: true });
                }
                if ($hasCreds) {
                    var errEl = document.querySelector('.validation-summary-errors, .field-validation-error, .alert-danger');
                    var hasLoginError = errEl && (errEl.innerText || '').trim().length > 0;
                    var form = document.getElementById('LoginForm');
                    if (form && !hasLoginError && !form.dataset.hiddenByTheme) {
                        form.dataset.hiddenByTheme = 'true';
                        form.style.cssText = 'opacity:0;height:0;overflow:hidden;pointer-events:none;';
                        var msg = document.createElement('div');
                        msg.id = 'custom-login-msg';
                        msg.style.cssText = 'text-align:center;padding:24px 12px;';
                        msg.innerHTML = '<div style="color:#38BDF8;font-size:16px;font-weight:bold;margin-bottom:6px;">Kirjaudutaan sisään...</div><div style="color:#94A3B8;font-size:13px;">Yhdistetään OmaNumeron-palveluun</div>';
                        form.parentNode.insertBefore(msg, form);
                        setTimeout(function() {
                            var f = document.getElementById('LoginForm');
                            var m = document.getElementById('custom-login-msg');
                            if (f) {
                                f.style.cssText = '';
                                delete f.dataset.hiddenByTheme;
                            }
                            if (m) m.remove();
                        }, 5000);
                    }
                }
            })();
        """.trimIndent()

        view?.evaluateJavascript(js) {
            if (revealAfter) revealWebView()
        }
    }

    private fun injectWishProtection() {
        val js = """
            (function() {
                if (window._wishGuardInstalled) return;
                window._wishGuardInstalled = true;
                document.addEventListener('click', function(e) {
                    if (window._wishAuthApproved) {
                        window._wishAuthApproved = false;
                        return;
                    }
                    var el = e.target.closest('button, input[type="submit"], input[type="button"], a');
                    if (!el) return;
                    var txt = (el.innerText || el.value || el.title || "").trim().toLowerCase();
                    var cls = (el.className || "").toLowerCase();
                    var isSave = txt.indexOf('tallenna') !== -1 || txt.indexOf('lähetä') !== -1;
                    var isDelete = txt.indexOf('poista') !== -1 || cls.indexOf('delete') !== -1 || cls.indexOf('trash') !== -1 || cls.indexOf('remove') !== -1;

                    if (isSave || isDelete) {
                        e.preventDefault();
                        e.stopPropagation();
                        window._pendingWishEl = el;
                        var label = isDelete ? "Vahvista toiveen poisto" : "Vahvista toiveen tallennus";
                        AndroidBridge.confirmWishAction(label);
                    }
                }, true);
            })();
        """.trimIndent()
        webView.evaluateJavascript(js, null)
    }

    private fun showStampOverlay(title: String, status: String, showSpinner: Boolean = true) {
        if (!::stampOverlay.isInitialized) return
        overlayTitle.text = title
        overlayStatus.text = status
        overlayProgress.visibility = if (showSpinner) View.VISIBLE else View.GONE
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && ::mainColumn.isInitialized) {
            mainColumn.setRenderEffect(RenderEffect.createBlurEffect(28f, 28f, Shader.TileMode.CLAMP))
        }
        stampOverlay.visibility = View.VISIBLE
    }

    private fun hideStampOverlay() {
        if (!::stampOverlay.isInitialized) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && ::mainColumn.isInitialized) {
            mainColumn.setRenderEffect(null)
        }
        stampOverlay.visibility = View.GONE
    }

    private fun styleButton(btn: Button, bgColor: String, isSelected: Boolean) {
        btn.background = GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = 24f
            setColor(Color.parseColor(bgColor))
            if (isSelected) setStroke(3, Color.parseColor("#7DD3FC"))
        }
        btn.setTypeface(null, if (isSelected) Typeface.BOLD else Typeface.NORMAL)
        btn.alpha = if (isSelected) 1.0f else 0.88f
    }

    private fun updateNavigationState(url: String) {
        val u = if (url.isNotEmpty()) url else (webView.url ?: "")
        val isDemo = u.contains("demo_shifts.html", ignoreCase = true)
        val isCal = u.contains("/Calendar/", ignoreCase = true) || isDemo
        val isWishes = u.contains("/PersonRequests/", ignoreCase = true)
        val isStamp = u.contains("/WorktimeStamping", ignoreCase = true) || (!isCal && !isWishes)

        btnCalendar.visibility = if (isCal && !isDemo) View.GONE else View.VISIBLE
        btnSync.visibility = if (isCal) View.VISIBLE else View.GONE

        styleButton(btnStamp, if (isStamp) "#0284C7" else "#334155", isStamp)
        styleButton(btnWishes, if (isWishes) "#0284C7" else "#334155", isWishes)
        styleButton(btnCalendar, "#334155", false)
        styleButton(btnSync, "#059669", true)
        styleButton(btnSettings, "#334155", false)
        styleButton(btnClose, "#7F1D1D", false)
    }

    private fun tryAutoLoginIfNeeded() {
        if (isDemoActive) return
        val u = SettingsManager.getUsername(this)
        val p = SettingsManager.getPassword(this)
        val safeU = u.replace("\\", "\\\\").replace("'", "\\'")
        val safeP = p.replace("\\", "\\\\").replace("'", "\\'")

        val js = """
            (function() {
                var bodyTxt = (document.body ? document.body.innerText : "").toLowerCase();
                var passInputs = document.querySelectorAll('input[type="password"]');
                var hasVisiblePass = false;
                for (var i = 0; i < passInputs.length; i++) {
                    if (passInputs[i].offsetParent !== null) { hasVisiblePass = true; break; }
                }
                if (!hasVisiblePass && (bodyTxt.indexOf('istunto on vanhentunut') !== -1 || bodyTxt.indexOf('istuntosi on vanhentunut') !== -1 || bodyTxt.indexOf('session expired') !== -1 || bodyTxt.indexOf('kirjaudu sisään uudelleen') !== -1 || bodyTxt.indexOf('uloskirjattu') !== -1)) {
                    var btns = document.querySelectorAll('button, a, input[type="button"], input[type="submit"]');
                    for (var b = 0; b < btns.length; b++) {
                        if (btns[b].offsetParent === null) continue;
                        var t = (btns[b].innerText || btns[b].value || "").trim().toLowerCase();
                        if (t.indexOf('kirjaudu') !== -1 || t === 'ok' || t.indexOf('jatka') !== -1 || t.indexOf('uudelleen') !== -1 || t.indexOf('alkuun') !== -1) {
                            btns[b].click();
                            return "SESSION_EXPIRED_CLICKED";
                        }
                    }
                    return "SESSION_EXPIRED_RELOAD";
                }
                if ('$safeU' === '' || '$safeP' === '') return "NO_CREDS";
                function setNativeValue(el, val) {
                    var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    if (setter) setter.call(el, val);
                    else el.value = val;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
                var userInputs = document.querySelectorAll('input[type="email"], input[name*="user" i], input[name*="login" i], input[id*="user" i], input[name*="fmt" i], input[type="text"]');
                var userEl = null;
                for (var uIdx = 0; uIdx < userInputs.length; uIdx++) {
                    var inp = userInputs[uIdx];
                    if (inp.offsetParent !== null && !inp.readOnly && !inp.disabled) { userEl = inp; break; }
                }
                var passEl = null;
                for (var pIdx = 0; pIdx < passInputs.length; pIdx++) {
                    if (passInputs[pIdx].offsetParent !== null && !passInputs[pIdx].disabled) { passEl = passInputs[pIdx]; break; }
                }
                if (userEl && !passEl && (window.location.href.toLowerCase().indexOf('login') !== -1 || window.location.href.toLowerCase().indexOf('auth') !== -1 || window.location.href.toLowerCase().indexOf('microsoft') !== -1 || bodyTxt.indexOf('kirjaudu') !== -1)) {
                    setNativeValue(userEl, '$safeU');
                    var nextBtn = document.querySelector('input[type="submit"], button[type="submit"], button[id*="next" i], input[id*="next" i]');
                    if (nextBtn && nextBtn.offsetParent !== null) { nextBtn.click(); return "USER_STEP_SUBMITTED"; }
                }
                if (!passEl) return "NO_LOGIN_FORM";
                var errEl = document.querySelector('.validation-summary-errors, .field-validation-error, .alert-danger');
                if (errEl && (errEl.innerText || '').trim().length > 0) return "LOGIN_ERROR";
                var nowTs = Date.now();
                if (window._numeronAutoLoginTs && (nowTs - window._numeronAutoLoginTs) < 4000) return "SUBMIT_COOLDOWN";
                window._numeronAutoLoginTs = nowTs;
                if (userEl) setNativeValue(userEl, '$safeU');
                setNativeValue(passEl, '$safeP');
                var submitBtn = document.querySelector('input[type="submit"], button[type="submit"], button[id*="login" i], button[name*="login" i], input[id*="SignIn" i]');
                if (submitBtn && submitBtn.offsetParent !== null) {
                    submitBtn.disabled = false;
                    submitBtn.click();
                    return "SUBMITTED";
                }
                if (passEl.form) { passEl.form.submit(); return "SUBMITTED"; }
                return "FILLED";
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { res ->
            val r = res ?: ""
            val now = System.currentTimeMillis()
            when {
                r.contains("SESSION_EXPIRED_RELOAD") -> navigateWebView(if (isBackgroundListSync) urlCalendar else urlStamping)
                r.contains("SESSION_EXPIRED_CLICKED") || r.contains("USER_STEP_SUBMITTED") -> {
                    if (pendingAutoStamp || isBackgroundListSync) showStampOverlay(overlayTitle.text.toString(), "Kirjaudutaan sisään...")
                    webView.postDelayed({ tryAutoLoginIfNeeded() }, 1400)
                }
                r.contains("SUBMITTED") -> {
                    if (now - lastAutoLoginAttempt > 4000L) {
                        lastAutoLoginAttempt = now
                        if (pendingAutoStamp || isBackgroundListSync) {
                            showStampOverlay(overlayTitle.text.toString(), "Kirjaudutaan sisään, odota hetki...")
                        }
                    }
                    if (pendingAutoStamp) webView.postDelayed({ scheduleAutoStampCheck(1500) }, 2200)
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIncomingIntent(intent)
        if (pendingAutoStamp && ::webView.isInitialized) {
            navigateWebView(urlStamping)
        } else if (pendingSummaryDialog && ::webView.isInitialized) {
            pendingSummaryDialog = false
            showSyncSummaryDialog()
        }
    }

    private fun resetSyncBatch(pages: Int) {
        pagesRemainingToSync = pages
        consecutiveEmptyPages = 0
        totalFoundInBatch = 0
        totalAddedInBatch = 0
        totalRemovedInBatch = 0
        syncedDatesInBatch.clear()
        syncChangesList.clear()
        syncedShiftRangesInBatch.clear()
    }

    private fun handleIncomingIntent(intent: Intent?) {
        if (intent == null) return

        if (intent.getBooleanExtra("OPEN_SYNC_SUMMARY", false)) {
            intent.removeExtra("OPEN_SYNC_SUMMARY")
            pendingSummaryDialog = true
        }

        val quickAction = intent.getStringExtra("quick_action")?.trim()
        if (quickAction == "ACTION_STAMP") {
            intent.removeExtra("quick_action")
            if (::webView.isInitialized) navigateWebView(urlStamping)
        } else if (quickAction == "ACTION_SYNC") {
            intent.removeExtra("quick_action")
            isBackgroundListSync = true
            forceListOnNextCalendarLoad = true
            resetSyncBatch(12)
            showStampOverlay("Synkronoidaan työvuoroja", "Avataan kalenteria...")
            if (::webView.isInitialized) navigateWebView(urlCalendar)
        }

        if (intent.getBooleanExtra("AUTO_STAMP", false)) {
            pendingAutoStamp = true
            pendingStampIsEnding = intent.getBooleanExtra("IS_ENDING", false)
            autoStampClickDone = false
            autoStampRetryCount = 0
            intent.removeExtra("AUTO_STAMP")
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.cancel(if (pendingStampIsEnding) 2002 else 1001)
            val title = if (pendingStampIsEnding) "Ulosleimaus käynnissä" else "Sisäänleimaus käynnissä"
            showStampOverlay(title, "Valmistellaan leimausta...")
        }

        if (intent.getBooleanExtra("AUTO_SYNC_NEW_LIST", false)) {
            intent.removeExtra("AUTO_SYNC_NEW_LIST")
            isBackgroundListSync = true
            forceListOnNextCalendarLoad = true
            resetSyncBatch(12)
            showStampOverlay("Haetaan uutta työvuorolistaa", "Avataan kalenteria...")
            if (::webView.isInitialized) navigateWebView(urlCalendar)
        }
    }

    private fun scheduleAutoStampCheck(delayMs: Long) {
        if (!pendingAutoStamp) return
        webView.postDelayed({ executeAutoStampStep() }, delayMs)
    }

    private fun executeAutoStampStep() {
        if (!pendingAutoStamp || autoStampClickDone) return
        autoStampRetryCount++
        if (autoStampRetryCount > 15) {
            pendingAutoStamp = false
            hideStampOverlay()
            Toast.makeText(this, "Automaattileimaus aikakatkaistiin.", Toast.LENGTH_LONG).show()
            return
        }
        val currentUrl = webView.url ?: ""
        val targetKeyword = if (pendingStampIsEnding) "ulos" else "sisään"
        val oppositeKeyword = if (pendingStampIsEnding) "sisään" else "ulos"

        val js = """
            (function() {
                var passInputs = document.querySelectorAll('input[type="password"]');
                for (var p = 0; p < passInputs.length; p++) {
                    if (passInputs[p].offsetParent !== null) return "LOGIN_PAGE";
                }
                var btns = document.querySelectorAll('button, input[type="button"], input[type="submit"], a.btn');
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i].offsetParent === null) continue;
                    var txt = (btns[i].innerText || btns[i].value || "").trim().toLowerCase();
                    if (txt.indexOf('leimaa') !== -1 && txt.indexOf('$targetKeyword') !== -1) {
                        btns[i].click();
                        return "CLICKED:" + txt;
                    }
                }
                for (var j = 0; j < btns.length; j++) {
                    if (btns[j].offsetParent === null) continue;
                    var t = (btns[j].innerText || btns[j].value || "").trim().toLowerCase();
                    if (t.indexOf('leimaa') !== -1 && t.indexOf('$oppositeKeyword') !== -1) return "ALREADY_IN_TARGET_STATE";
                }
                return "WAITING";
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { res ->
            val r = res ?: ""
            when {
                r.contains("LOGIN_PAGE") -> {
                    showStampOverlay(overlayTitle.text.toString(), "Kirjaudutaan sisään...")
                    tryAutoLoginIfNeeded()
                    scheduleAutoStampCheck(2000)
                }
                r.contains("CLICKED:") -> {
                    autoStampClickDone = true
                    showStampOverlay(overlayTitle.text.toString(), "Suoritetaan leimausta ja varmistetaan...")
                    webView.postDelayed({ verifyStampSuccess(1) }, 1800)
                }
                r.contains("ALREADY_IN_TARGET_STATE") -> completeAutoStampSuccess("Leimaus on jo voimassa!")
                else -> {
                    if (!currentUrl.contains("/WorktimeStamping", ignoreCase = true) && !currentUrl.contains("login", ignoreCase = true) && autoStampRetryCount % 3 == 0) {
                        navigateWebView(urlStamping)
                    }
                    scheduleAutoStampCheck(1400)
                }
            }
        }
    }

    private fun verifyStampSuccess(attempt: Int) {
        if (!pendingAutoStamp) return
        val targetKeyword = if (pendingStampIsEnding) "ulos" else "sisään"
        val oppositeKeyword = if (pendingStampIsEnding) "sisään" else "ulos"

        val js = """
            (function() {
                var btns = document.querySelectorAll('button, input[type="button"], input[type="submit"], a.btn');
                var targetStillVisible = false;
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i].offsetParent === null) continue;
                    var txt = (btns[i].innerText || btns[i].value || "").trim().toLowerCase();
                    if (txt.indexOf('leimaa') !== -1 && txt.indexOf('$oppositeKeyword') !== -1) return "VERIFIED_OPPOSITE";
                    if (txt.indexOf('leimaa') !== -1 && txt.indexOf('$targetKeyword') !== -1) targetStillVisible = true;
                }
                var bodyTxt = (document.body ? document.body.innerText : "").toLowerCase();
                if (bodyTxt.indexOf('onnistui') !== -1 || bodyTxt.indexOf('tallennettu') !== -1 || bodyTxt.indexOf('leimattu sisään') !== -1) return "VERIFIED_TEXT";
                if (!targetStillVisible && bodyTxt.indexOf('työaikaleimaus') !== -1) return "VERIFIED_GONE";
                return "PENDING";
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { res ->
            val r = res ?: ""
            if (r.contains("VERIFIED")) {
                completeAutoStampSuccess(if (pendingStampIsEnding) "Ulosleimaus varmistettu!" else "Sisäänleimaus varmistettu!")
            } else if (attempt < 5) {
                webView.postDelayed({ verifyStampSuccess(attempt + 1) }, 1200)
            } else {
                pendingAutoStamp = false
                autoStampClickDone = false
                hideStampOverlay()
                Toast.makeText(this, "Varmista leimauksen tila ruudulta.", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun completeAutoStampSuccess(message: String) {
        val wasEnding = pendingStampIsEnding
        pendingAutoStamp = false
        autoStampClickDone = false
        VuorovahtiHelper.triggerConfirmHaptics(window.decorView)

        val freeDayGreeting = if (wasEnding) VuorovahtiHelper.getFreeDayGreetingIfApplicable(this) else null
        val statusText = if (freeDayGreeting != null) {
            "$freeDayGreeting\n\nSuljetaan sovellus..."
        } else {
            "Suljetaan sovellus..."
        }

        showStampOverlay(" ✓  $message", statusText, showSpinner = false)
        webView.postDelayed({ finishAndRemoveTask() }, if (freeDayGreeting != null) 2600L else 1400L)
    }

    private fun getRequiredPermissions(): List<String> {
        val list = mutableListOf(Manifest.permission.READ_CALENDAR, Manifest.permission.WRITE_CALENDAR)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            list.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        return list
    }

    private fun startManualForegroundSync() {
        isBackgroundListSync = true
        resetSyncBatch(if (isDemoActive) 0 else 12)
        showStampOverlay("Synkronoidaan kalenteria", "Haetaan työvuoroja ja lomia taustalla...")
        extractShiftsFromPage(forceList = true)
    }

    private fun checkPermissionsAndSync() {
        val missing = getRequiredPermissions().filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 100)
        } else {
            startManualForegroundSync()
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        VuorovahtiHelper.ensureRemindersFromCalendar(this)
        if (requestCode == 100) {
            val r = ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CALENDAR) == PackageManager.PERMISSION_GRANTED
            val w = ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_CALENDAR) == PackageManager.PERMISSION_GRANTED
            if (r && w) {
                startManualForegroundSync()
            }
        }
    }

    private fun extractShiftsFromPage(forceList: Boolean = true) {
        if (isDemoActive) {
            val calId = getTargetOrPrimaryCalendarId()
            if (calId != null) {
                val fmt = DateTimeFormatter.ofPattern("d.M.yyyy H:mm")
                val tomorrow = LocalDate.now().plusDays(1)
                val day2 = LocalDate.now().plusDays(2)
                val day3 = LocalDate.now().plusDays(3)
                var added = 0
                if (saveWorkShift(calId, "${tomorrow.dayOfMonth}.${tomorrow.monthValue}.${tomorrow.year}", "07:00", "15:00", "Aamuvuoro (Demo)", fmt)) added++
                if (saveWorkShift(calId, "${day2.dayOfMonth}.${day2.monthValue}.${day2.year}", "13:00", "21:00", "Iltavuoro (Demo)", fmt)) added++
                if (saveWorkShift(calId, "${day3.dayOfMonth}.${day3.monthValue}.${day3.year}", "21:00", "07:00", "Yövuoro (Demo)", fmt)) added++
                VuorovahtiHelper.saveLastSyncStatus(this, 3)
                VuorovahtiHelper.ensureRemindersFromCalendar(this)
                VuorovahtiHelper.triggerConfirmHaptics(window.decorView)
                hideStampOverlay()
                Toast.makeText(this, "Demo-synkronointi valmis ($added vuoroa viety kalenteriin).", Toast.LENGTH_LONG).show()
            }
            return
        }

        val js = """
            (function() {
                function isIgnoredRowText(str) {
                    if (!str) return false;
                    var low = str.toLowerCase();
                    return low.indexOf('toive') !== -1 ||
                           low.indexOf('toivottu') !== -1 ||
                           low.indexOf('vapaa') !== -1 ||
                           /\bvp\b/.test(low) ||
                           low.indexOf('ei käytettävissä') !== -1;
                }
                var bodyText = "";
                if (document.body) {
                    var bodyClone = document.body.cloneNode(true);
                    var uiChrome = bodyClone.querySelectorAll('nav, #pc_AddButton, #mobile_AddButton, #pcViewDropdown, #mobileViewDropdown, .dropdown-menu');
                    for (var u = 0; u < uiChrome.length; u++) uiChrome[u].remove();
                    var badEls = bodyClone.querySelectorAll('.request, .opportunity, .schedule-item-request, .schedule-item-opportunity, .month-item.request, .month-item.opportunity, [class*="request" i], [class*="opportunity" i], [class*="wish" i]');
                    for (var b = 0; b < badEls.length; b++) badEls[b].remove();
                    var rows = bodyClone.querySelectorAll('tr, .list-item, .schedule-item, .calendar-list-item, .list-day-item');
                    for (var r = 0; r < rows.length; r++) {
                        if (isIgnoredRowText(rows[r].innerText)) rows[r].remove();
                    }
                    bodyText = bodyClone.innerText || "";
                }
                var pathLower = (window.location.pathname || "").toLowerCase();
                var isListPage = pathLower.indexOf('/calendar/list') !== -1 || pathLower.indexOf('demo_shifts') !== -1;
                var isGrid = /Vk\.?\s+Ma\s+Ti\s+Ke/i.test(bodyText) || document.querySelector('.month-table') !== null;
                if ($forceList && !isListPage && isGrid) {
                    var directListLink = document.querySelector('#go-to-list a, #go-to-list-mobile a, a[href*="/Calendar/List" i]');
                    if (directListLink) {
                        if (directListLink.href && directListLink.href.indexOf('#') === -1) {
                            window.location.href = directListLink.href;
                        } else {
                            directListLink.click();
                        }
                        return "SWITCHED_TO_LIST";
                    }
                    var selects = document.querySelectorAll('select');
                    for (var s = 0; s < selects.length; s++) {
                        for (var o = 0; o < selects[s].options.length; o++) {
                            var optTxt = (selects[s].options[o].text || "").toLowerCase();
                            if (optTxt.indexOf('luettelo') !== -1 || optTxt.indexOf('lista') !== -1 || optTxt.indexOf('list') !== -1) {
                                selects[s].selectedIndex = o;
                                selects[s].dispatchEvent(new Event('change', { bubbles: true }));
                                return "SWITCHED_TO_LIST";
                            }
                        }
                    }
                    var links = document.querySelectorAll('a, button');
                    for (var i = 0; i < links.length; i++) {
                        var t = (links[i].innerText || "").trim().toLowerCase();
                        var href = (links[i].getAttribute && links[i].getAttribute('href')) || "";
                        if (t === 'luettelo' || t === 'lista' || href.toLowerCase().indexOf('/calendar/list') !== -1 || href.toLowerCase().indexOf('view=list') !== -1) {
                            if (links[i].href && links[i].href.indexOf('#') === -1) {
                                window.location.href = links[i].href;
                            } else {
                                links[i].click();
                            }
                            return "SWITCHED_TO_LIST";
                        }
                    }
                }
                var cells = [];
                var tds = document.querySelectorAll('td');
                if (tds.length > 15) {
                    for (var j = 0; j < tds.length; j++) {
                        var td = tds[j];
                        var cls = (td.className || "").toLowerCase();
                        var isWeekCol = /week|vk|wk/.test(cls) || (td.parentElement && td.parentElement.children.length === 8 && td.cellIndex === 0);
                        if (isWeekCol) continue;
                        var isOther = /other|old|new|disabled|off|outside|gray|grey/.test(cls);
                        var dayNumEl = td.querySelector('.dayNum');
                        var dayNum = dayNumEl ? (dayNumEl.innerText || "").trim() : "";
                        var validItems = td.querySelectorAll('.month-item.work, .month-item.absence, .schedule-item-work, .schedule-item-absence');
                        var cellText = "";
                        if (dayNum && (validItems.length > 0 || td.querySelector('.month-day-content'))) {
                            var lines = [dayNum];
                            for (var v = 0; v < validItems.length; v++) {
                                var it = validItems[v];
                                if (it.classList.contains('hidden-items-box')) continue;
                                var tStr = (it.innerText || "").trim().replace(/\s+/g, ' ');
                                if (tStr) lines.push(tStr);
                            }
                            cellText = lines.join("\n");
                        } else {
                            var clone = td.cloneNode(true);
                            var ignored = clone.querySelectorAll('.request, .opportunity, .schedule-item-request, .schedule-item-opportunity, .hidden-items-box');
                            for (var ig = 0; ig < ignored.length; ig++) ignored[ig].remove();
                            cellText = (clone.innerText || "").trim();
                        }
                        var extra = [];
                        var ch = td.querySelectorAll('.work [title], .absence [title], .work [data-original-title], .absence [data-original-title]');
                        for (var c = 0; c < ch.length; c++) {
                            var ti = ch[c].getAttribute('title') || ch[c].getAttribute('data-original-title');
                            if (ti) extra.push(ti);
                        }
                        cells.push({ text: cellText, isOther: isOther, extra: extra.join(" | ") });
                    }
                }
                AndroidBridge.processCalendarData(JSON.stringify(cells), bodyText, window.location.href);
                return "EXTRACTED";
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { result ->
            if (result != null && result.contains("SWITCHED_TO_LIST")) {
                waitingForListViewSync = true
                webView.postDelayed({
                    if (waitingForListViewSync) {
                        waitingForListViewSync = false
                        extractShiftsFromPage(forceList = false)
                    }
                }, 1200)
            }
        }
    }

    private fun switchBackToMonthView() {
        if (!::webView.isInitialized || isDemoActive) return
        webView.post {
            webView.evaluateJavascript(
                """
                (function() {
                    var directMonth = document.querySelector('#go-to-month a, #go-to-month-mobile a, a[href*="/Calendar/Month" i]');
                    if (directMonth && directMonth.href && directMonth.href.indexOf('#') === -1) {
                        window.location.href = directMonth.href;
                        return "MONTH_NAVIGATED";
                    }
                    var selects = document.querySelectorAll('select');
                    for (var s = 0; s < selects.length; s++) {
                        for (var o = 0; o < selects[s].options.length; o++) {
                            var optTxt = (selects[s].options[o].text || "").toLowerCase();
                            if (optTxt.indexOf('kuukausi') !== -1 || optTxt.indexOf('month') !== -1) {
                                selects[s].selectedIndex = o;
                                selects[s].dispatchEvent(new Event('change', { bubbles: true }));
                                return "MONTH_SELECTED";
                            }
                        }
                    }
                    var btns = document.querySelectorAll('a, button, li, span');
                    for (var i = 0; i < btns.length; i++) {
                        var t = (btns[i].innerText || "").trim().toLowerCase();
                        if (t === 'kuukausi' || t === 'month' || t === 'kuukausinäkymä') {
                            btns[i].click();
                            return "MONTH_CLICKED";
                        }
                    }
                    window.location.href = '/Calendar/Month';
                    return "MONTH_FALLBACK";
                })();
                """.trimIndent(),
                null
            )
        }
    }

    private fun finishCalendarSyncBatch(calId: Long, toastPrefix: String) {
        totalRemovedInBatch += reconcileRemovedShifts(calId)
        switchBackToMonthView()
        hideStampOverlay()
        isBackgroundListSync = false
        VuorovahtiHelper.saveLastSyncStatus(this, totalFoundInBatch)
        VuorovahtiHelper.triggerConfirmHaptics(window.decorView)
        VuorovahtiHelper.ensureRemindersFromCalendar(this)
        saveSyncChangesHistory()
        if (totalAddedInBatch > 0 || totalRemovedInBatch > 0) {
            sendNewShiftsAddedNotification(totalAddedInBatch)
        }
        val missingTxt = if (missingFieldsCount > 0) " (Varoitus: $missingFieldsCount merkinnästä puuttui kenttiä)" else ""
        Toast.makeText(
            this,
            "$toastPrefix $totalAddedInBatch lisätty/päivitetty, $totalRemovedInBatch poistettu.$missingTxt",
            Toast.LENGTH_LONG
        ).show()
    }

    inner class CalendarBridge {
        @JavascriptInterface
        fun confirmWishAction(actionTitle: String) {
            runOnUiThread {
                requireBiometricAuth(actionTitle) {
                    webView.evaluateJavascript(
                        """
                        if (window._pendingWishEl) {
                            window._wishAuthApproved = true;
                            window._pendingWishEl.click();
                        }
                        """.trimIndent(),
                        null
                    )
                }
            }
        }

        @JavascriptInterface
        fun processCalendarData(cellsJson: String, pageText: String, currentUrl: String) {
            runOnUiThread {
                val calId = getTargetOrPrimaryCalendarId()
                if (calId == null) {
                    hideStampOverlay()
                    Toast.makeText(this@MainActivity, "Kalenteria ei löytynyt.", Toast.LENGTH_LONG).show()
                    return@runOnUiThread
                }
                val (found, added) = parseAndInsertCalendar(cellsJson, pageText, currentUrl, calId)
                totalFoundInBatch += found
                totalAddedInBatch += added

                if (found == 0) {
                    consecutiveEmptyPages++
                } else {
                    consecutiveEmptyPages = 0
                }

                if (consecutiveEmptyPages >= 2) {
                    pagesRemainingToSync = 0
                    finishCalendarSyncBatch(calId, "Haku keskeytetty (3 viikkoa ilman työvuoroja tai lomaa). Tarkistettu $totalFoundInBatch merkintää:")
                } else if (pagesRemainingToSync > 0) {
                    pagesRemainingToSync--
                    if (isBackgroundListSync || stampOverlay.visibility == View.VISIBLE) {
                        val checkedCount = 12 - pagesRemainingToSync
                        showStampOverlay(
                            "Synkronoidaan kalenteria",
                            "Tarkistetaan jaksoa $checkedCount / 12...\nLöydetty $totalFoundInBatch merkintää (muutoksia $totalAddedInBatch)"
                        )
                    }
                    clickNextCalendarPeriod(calId)
                } else {
                    finishCalendarSyncBatch(calId, "Tarkistettu $totalFoundInBatch merkintää:")
                }
            }
        }
    }

    private fun clickNextCalendarPeriod(calId: Long) {
        val js = """
            (function() {
                var nextSelectors = ['a.nextButton', '.nextButton', '.vismaicon-arrow-right-circle', 'a[title*="Seuraava" i]', 'button[title*="Seuraava" i]', '.fa-chevron-right', '.fa-angle-right', '.glyphicon-chevron-right', '.icon-chevron-right', '.fc-next-button'];
                for (var s = 0; s < nextSelectors.length; s++) {
                    var el = document.querySelector(nextSelectors[s]);
                    if (el) {
                        var clickable = el.closest('a, button') || el;
                        if (clickable.href && clickable.href.indexOf('#') === -1 && !clickable.getAttribute('onclick')) {
                            window.location.href = clickable.href;
                        } else {
                            clickable.click();
                        }
                        return "NEXT_CLICKED";
                    }
                }
                var all = document.querySelectorAll('button, a, span');
                for (var i = 0; i < all.length; i++) {
                    var t = (all[i].innerText || "").trim().toLowerCase();
                    if (t === '>' || t === '›' || t === '»') { all[i].click(); return "NEXT_CLICKED"; }
                }
                return "NO_NEXT_BTN";
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { res ->
            if (res != null && res.contains("NEXT_CLICKED")) {
                waitingForListViewSync = true
                webView.postDelayed({
                    if (waitingForListViewSync) {
                        waitingForListViewSync = false
                        extractShiftsFromPage(forceList = false)
                    }
                }, 1400)
            } else {
                pagesRemainingToSync = 0
                finishCalendarSyncBatch(calId, "Valmis:")
            }
        }
    }

    private fun saveSyncChangesHistory() {
        val arr = JSONArray()
        for (item in syncChangesList) {
            arr.put(
                JSONObject().apply {
                    put("eventId", item.eventId)
                    put("type", item.type)
                    put("dateStr", item.dateStr)
                    put("timeStr", item.timeStr)
                    put("title", item.title)
                }
            )
        }
        getSharedPreferences("vuorovahti_prefs", Context.MODE_PRIVATE)
            .edit()
            .putString("last_sync_changes_json", arr.toString())
            .apply()
    }

    private fun sendNewShiftsAddedNotification(addedCount: Int) {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channelId = "numeron_list_channel"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(NotificationChannel(channelId, "Uudet työvuorolistat", NotificationManager.IMPORTANCE_HIGH))
        }
        val summaryIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra("OPEN_SYNC_SUMMARY", true)
        }
        val pi = PendingIntent.getActivity(
            this, 3004, summaryIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val removedTxt = if (totalRemovedInBatch > 0) ", poistettu $totalRemovedInBatch" else ""
        val notif = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(R.drawable.ic_launcher)
            .setSubText("Numeron Vuorovahti")
            .setContentTitle("Uudet työvuorot päivitetty!")
            .setContentText("Lisätty/muutettu $addedCount$removedTxt." + (if (missingFieldsCount > 0) " Huomio: $missingFieldsCount merkinnästä puuttui kenttiä." else "") + " Napauta tarkistaaksesi.")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()
        nm.notify(3004, notif)
    }

    private fun showSyncSummaryDialog() {
        val rawJson = getSharedPreferences("vuorovahti_prefs", Context.MODE_PRIVATE)
            .getString("last_sync_changes_json", "[]") ?: "[]"
        val arr = try { JSONArray(rawJson) } catch (_: Exception) { JSONArray() }

        val dp = { v: Int -> (v * resources.displayMetrics.density).toInt() }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(14))
            setBackgroundColor(Color.parseColor("#0F172A"))
        }

        root.addView(TextView(this).apply {
            text = "Viimeisimmän synkronoinnin muutokset"
            textSize = 18f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#38BDF8"))
            setPadding(0, 0, 0, dp(6))
        })

        root.addView(TextView(this).apply {
            text = "Voit muokata merkintää kalenterissa tai kumota yksittäisen lisäyksen."
            textSize = 12.5f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, 0, 0, dp(12))
        })

        val scroll = ScrollView(this).apply {
            layoutParams = LinearLayout.LayoutParams(-1, 0, 1f)
        }
        val listCol = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }

        if (arr.length() == 0) {
            listCol.addView(TextView(this).apply {
                text = "Ei tallennettuja yksittäisiä vuoromuutoksia viimeisimmässä erässä."
                textSize = 13.5f
                setTextColor(Color.parseColor("#CBD5E1"))
                setPadding(0, dp(12), 0, dp(12))
            })
        } else {
            for (i in 0 until arr.length()) {
                val obj = arr.getJSONObject(i)
                val evId = obj.optLong("eventId", -1L)
                val type = obj.optString("type", "ADDED")
                val dateStr = obj.optString("dateStr", "")
                val timeStr = obj.optString("timeStr", "")
                val title = obj.optString("title", "Työvuoro")

                val badgeText = when (type) {
                    "UPDATED" -> "MUUTETTU"
                    "REMOVED" -> "POISTETTU"
                    else -> "UUSI"
                }
                val badgeColor = when (type) {
                    "UPDATED" -> "#FB8C00"
                    "REMOVED" -> "#EF4444"
                    else -> "#10B981"
                }

                val itemCard = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    setPadding(dp(14), dp(12), dp(14), dp(12))
                    layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) }
                    background = GradientDrawable().apply {
                        cornerRadius = dp(12).toFloat()
                        setColor(Color.parseColor("#1E293B"))
                        setStroke(dp(1), Color.parseColor("#334155"))
                    }
                }

                val infoText = TextView(this).apply {
                    text = "[$badgeText]  $dateStr  klo $timeStr${System.lineSeparator()}$title"
                    textSize = 13.5f
                    setTypeface(null, Typeface.BOLD)
                    setTextColor(Color.parseColor(badgeColor))
                }
                itemCard.addView(infoText)

                if (type != "REMOVED" && evId > 0L) {
                    val actRow = LinearLayout(this).apply {
                        orientation = LinearLayout.HORIZONTAL
                        gravity = Gravity.END
                        setPadding(0, dp(8), 0, 0)
                    }

                    val btnEdit = Button(this).apply {
                        text = "Muokkaa"
                        isAllCaps = false
                        textSize = 12f
                        setTextColor(Color.WHITE)
                        background = GradientDrawable().apply {
                            cornerRadius = dp(8).toFloat()
                            setColor(Color.parseColor("#0284C7"))
                        }
                        minHeight = 0
                        minimumHeight = 0
                        setPadding(dp(12), dp(6), dp(12), dp(6))
                        layoutParams = LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(8) }
                        setOnClickListener {
                            val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, evId)
                            try {
                                startActivity(Intent(Intent.ACTION_EDIT).apply { data = uri })
                            } catch (_: Exception) {
                                try {
                                    startActivity(Intent(Intent.ACTION_VIEW).apply { data = uri })
                                } catch (_: Exception) {}
                            }
                        }
                    }

                    val btnDelete = Button(this).apply {
                        text = "Peruuta / Poista"
                        isAllCaps = false
                        textSize = 12f
                        setTextColor(Color.WHITE)
                        background = GradientDrawable().apply {
                            cornerRadius = dp(8).toFloat()
                            setColor(Color.parseColor("#991B1B"))
                        }
                        minHeight = 0
                        minimumHeight = 0
                        setPadding(dp(12), dp(6), dp(12), dp(6))
                        setOnClickListener {
                            contentResolver.delete(
                                CalendarContract.Events.CONTENT_URI,
                                "${CalendarContract.Events._ID} = ?",
                                arrayOf(evId.toString())
                            )
                            VuorovahtiHelper.ensureRemindersFromCalendar(this@MainActivity)
                            VuorovahtiHelper.triggerConfirmHaptics(window.decorView)
                            infoText.text = "[PERUTTU]  $dateStr  klo $timeStr — Poistettu kalenterista"
                            infoText.setTextColor(Color.parseColor("#64748B"))
                            actRow.visibility = View.GONE
                        }
                    }

                    actRow.addView(btnEdit)
                    actRow.addView(btnDelete)
                    itemCard.addView(actRow)
                }

                listCol.addView(itemCard)
            }
        }

        scroll.addView(listCol)
        root.addView(scroll)

        val dlg = AlertDialog.Builder(this).setView(root).create()
        val btnCloseDlg = Button(this).apply {
            text = "Sulje"
            isAllCaps = false
            textSize = 14f
            setTextColor(Color.WHITE)
            background = GradientDrawable().apply {
                cornerRadius = dp(10).toFloat()
                setColor(Color.parseColor("#334155"))
            }
            layoutParams = LinearLayout.LayoutParams(-1, dp(44)).apply { topMargin = dp(10) }
            setOnClickListener { dlg.dismiss() }
        }
        root.addView(btnCloseDlg)
        dlg.show()
    }

    private fun resolveMonthAndYear(pageText: String, currentUrl: String): Pair<Int, Int> {
        val now = LocalDate.now()
        val months = mapOf(
            "tammikuu" to 1, "helmikuu" to 2, "maaliskuu" to 3, "huhtikuu" to 4,
            "toukokuu" to 5, "kesäkuu" to 6, "heinäkuu" to 7, "elokuu" to 8,
            "syyskuu" to 9, "lokakuu" to 10, "marraskuu" to 11, "joulukuu" to 12
        )
        val mMatch = Regex("""(tammikuu|helmikuu|maaliskuu|huhtikuu|toukokuu|kesäkuu|heinäkuu|elokuu|syyskuu|lokakuu|marraskuu|joulukuu)\s+(\d{4})""", RegexOption.IGNORE_CASE).find(pageText)
        if (mMatch != null) {
            val m = months[mMatch.groupValues[1].lowercase()]
            val y = mMatch.groupValues[2].toIntOrNull()
            if (m != null && y != null) return Pair(m, y)
        }
        val wkSlashMatch = Regex("""(?:Vk|Viikko)\.?\s*(\d{1,2})\s*/\s*(\d{4})""", RegexOption.IGNORE_CASE).find(pageText)
        if (wkSlashMatch != null) {
            val wk = wkSlashMatch.groupValues[1].toIntOrNull() ?: 1
            val yr = wkSlashMatch.groupValues[2].toIntOrNull() ?: now.year
            val approxMonth = if (wk >= 48) 12 else if (wk <= 4) 1 else now.monthValue
            return Pair(approxMonth, yr)
        }
        val wkOnlyMatch = Regex("""(?:Vk|Viikko)\.?\s*(\d{1,2})\b""", RegexOption.IGNORE_CASE).find(pageText)
        if (wkOnlyMatch != null) {
            val wk = wkOnlyMatch.groupValues[1].toIntOrNull() ?: 1
            val inferredYear = if (now.monthValue >= 11 && wk <= 10) now.year + 1 else if (now.monthValue == 1 && wk >= 48) now.year - 1 else now.year
            val approxMonth = if (wk >= 48) 12 else if (wk <= 4) 1 else now.monthValue
            return Pair(approxMonth, inferredYear)
        }
        val uri = try { Uri.parse(currentUrl) } catch (_: Exception) { null }
        return Pair(uri?.getQueryParameter("month")?.toIntOrNull() ?: now.monthValue, uri?.getQueryParameter("year")?.toIntOrNull() ?: now.year)
    }

    private fun extractDirectVacationRanges(text: String, defaultYear: Int, vacationDays: MutableList<LocalDate>): Int {
        var foundRanges = 0
        val rangeRegex = Regex("""(\d{1,2})\.(?:(\d{1,2})\.)?(?:\d{4})?\s*[-–]\s*(\d{1,2})\.(\d{1,2})\.?(?:(\d{4}))?[^\n\r]*(?:loma|\bvl\b)""", RegexOption.IGNORE_CASE)
        for (m in rangeRegex.findAll(text)) {
            val d1 = m.groupValues[1].toIntOrNull() ?: continue
            val d2 = m.groupValues[3].toIntOrNull() ?: continue
            val m2 = m.groupValues[4].toIntOrNull() ?: continue
            val m1 = m.groupValues[2].toIntOrNull() ?: m2
            val y2 = m.groupValues[5].toIntOrNull() ?: defaultYear
            val y1 = if (m1 > m2) y2 - 1 else y2
            try {
                var cur = LocalDate.of(y1, m1, d1)
                val end = LocalDate.of(y2, m2, d2)
                if (!end.isBefore(cur) && ChronoUnit.DAYS.between(cur, end) <= 45) {
                    foundRanges++
                    while (!cur.isAfter(end)) {
                        vacationDays.add(cur)
                        cur = cur.plusDays(1)
                    }
                }
            } catch (_: Exception) {}
        }
        return foundRanges
    }

    private fun parseAndInsertCalendar(cellsJson: String, pageText: String, currentUrl: String, calId: Long): Pair<Int, Int> {
        val (targetMonth, targetYear) = resolveMonthAndYear(pageText, currentUrl)
        val fmt = DateTimeFormatter.ofPattern("d.M.yyyy H:mm")
        val listRes = parseListView(pageText, targetMonth, targetYear, calId, fmt)
        if (listRes.first > 0) return listRes

        var found = 0
        var added = 0
        val vacationDays = mutableListOf<LocalDate>()
        found += extractDirectVacationRanges(pageText, targetYear, vacationDays)

        try {
            val arr = JSONArray(cellsJson)
            if (arr.length() > 15) {
                var inMonth = false
                var lastDay = 0
                for (i in 0 until arr.length()) {
                    val obj = arr.getJSONObject(i)
                    val txt = obj.optString("text", "").trim()
                    val isOther = obj.optBoolean("isOther", false)
                    val extra = obj.optString("extra", "").trim()
                    val day = Regex("""^(\d{1,2})\b""").find(txt)?.groupValues?.get(1)?.toIntOrNull() ?: continue
                    if (day !in 1..31) continue
                    if (!inMonth) {
                        if (day == 1) {
                            inMonth = true
                            lastDay = 1
                        } else continue
                    } else {
                        if (day < lastDay && lastDay >= 20) break
                        if (day == lastDay + 1 || day == lastDay) lastDay = day else continue
                    }
                    if (isOther) continue
                    val res = processDayContent(calId, day, targetMonth, targetYear, txt, extra, fmt, vacationDays)
                    found += res.first
                    added += res.second
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }

        added += saveGroupedVacations(calId, vacationDays)
        return Pair(found, added)
    }

    private fun parseListView(pageText: String, targetMonth: Int, targetYear: Int, calId: Long, fmt: DateTimeFormatter): Pair<Int, Int> {
        var found = 0
        var added = 0
        val vacationDays = mutableListOf<LocalDate>()
        found += extractDirectVacationRanges(pageText, targetYear, vacationDays)
        val dateRe = Regex("""(?:(?:ma|ti|ke|to|pe|la|su|maanantai|tiistai|keskiviikko|torstai|perjantai|lauantai|sunnuntai)[\s.,]+(\d{1,2})\.(\d{1,2})(?:\.(\d{4})?)?|(?<![:\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})?)(?!\d)""", RegexOption.IGNORE_CASE)
        val matches = dateRe.findAll(pageText).toList()
        if (matches.isNotEmpty()) {
            for (i in matches.indices) {
                val m = matches[i]
                val d = (m.groupValues[1].ifEmpty { m.groupValues[4] }).toIntOrNull() ?: continue
                val mo = (m.groupValues[2].ifEmpty { m.groupValues[5] }).toIntOrNull() ?: continue
                val rawYr = (m.groupValues[3].ifEmpty { m.groupValues[6] }).toIntOrNull()
                val yr = rawYr ?: if (mo < LocalDate.now().monthValue - 1 && LocalDate.now().monthValue >= 10) LocalDate.now().year + 1 else if (targetMonth == 12 && mo == 1) targetYear + 1 else if (targetMonth == 1 && mo == 12) targetYear - 1 else targetYear
                if (d !in 1..31 || mo !in 1..12) continue
                val sIdx = m.range.last + 1
                val eIdx = if (i + 1 < matches.size) matches[i + 1].range.first else minOf(sIdx + 500, pageText.length)
                if (sIdx >= eIdx) continue
                val res = processListBlock(calId, d, mo, yr, pageText.substring(sIdx, eIdx).trim(), fmt, vacationDays)
                found += res.first
                added += res.second
            }
            if (matches.size >= 5 || found > 0) {
                for (m in matches) {
                    val d = (m.groupValues[1].ifEmpty { m.groupValues[4] }).toIntOrNull() ?: continue
                    val mo = (m.groupValues[2].ifEmpty { m.groupValues[5] }).toIntOrNull() ?: continue
                    val rawYr = (m.groupValues[3].ifEmpty { m.groupValues[6] }).toIntOrNull()
                    val yr = rawYr ?: if (mo < LocalDate.now().monthValue - 1 && LocalDate.now().monthValue >= 10) LocalDate.now().year + 1 else if (targetMonth == 12 && mo == 1) targetYear + 1 else if (targetMonth == 1 && mo == 12) targetYear - 1 else targetYear
                    try {
                        syncedDatesInBatch.add(LocalDate.of(yr, mo, d))
                    } catch (_: Exception) {}
                }
            }
            added += saveGroupedVacations(calId, vacationDays)
            if (found > 0) return Pair(found, added)
        }
        return Pair(found, added)
    }

    private fun isIgnoredEntry(text: String): Boolean {
        val low = text.lowercase()
        return low.contains("toive") ||
            low.contains("toivottu") ||
            low.contains("vapaa") ||
            Regex("""\bvp\b""").containsMatchIn(low) ||
            low.contains("ei käytettävissä") ||
            low.contains("vapaa vuoro")
    }

    private fun processListBlock(calId: Long, d: Int, m: Int, y: Int, block: String, fmt: DateTimeFormatter, vacationDays: MutableList<LocalDate>): Pair<Int, Int> {
        val cleanLines = block.lines().filter { !isIgnoredEntry(it) }
        val filteredBlock = cleanLines.joinToString("\n").trim()
        if (filteredBlock.isEmpty()) return Pair(0, 0)

        if (filteredBlock.lowercase().let { it.contains("vuosiloma") || it.contains("loma") || Regex("""\bvl\b""").containsMatchIn(it) }) {
            try {
                vacationDays.add(LocalDate.of(y, m, d))
            } catch (_: Exception) {}
            return Pair(1, 0)
        }
        val sMatches = Regex("""(\d{1,2}[:.]\d{2})[\s\t]*[-–][\s\t]*(\d{1,2}[:.]\d{2})""").findAll(filteredBlock).toList()
        if (sMatches.isNotEmpty()) {
            var added = 0
            for (idx in sMatches.indices) {
                val sMatch = sMatches[idx]
                val s = sMatch.groupValues[1].trim().replace('.', ':')
                val e = sMatch.groupValues[2].trim().replace('.', ':')
                val nextStart = if (idx + 1 < sMatches.size) sMatches[idx + 1].range.first else filteredBlock.length
                val after = filteredBlock.substring(sMatch.range.last + 1, nextStart).trim()
                val details = if (after.isNotEmpty()) after else filteredBlock.substring(0, sMatch.range.first).trim()
                if (saveWorkShift(calId, "$d.$m.$y", s, e, details, fmt)) added++
            }
            return Pair(sMatches.size, added)
        }
        return Pair(0, 0)
    }

    private fun processDayContent(calId: Long, d: Int, m: Int, y: Int, txt: String, extra: String, fmt: DateTimeFormatter, vacationDays: MutableList<LocalDate>): Pair<Int, Int> {
        val rest = "${txt.replaceFirst(Regex("""^\d{1,2}\s*"""), "")} $extra".lowercase()
        if (rest.contains("vuosiloma") || rest.contains("loma") || Regex("""\bvl\b""").containsMatchIn(rest)) {
            try {
                vacationDays.add(LocalDate.of(y, m, d))
            } catch (_: Exception) {}
            return Pair(1, 0)
        }
        val shifts = Regex("""(\d{1,2}[:.]\d{2})[\s\t\r\n]*[-–][\s\t\r\n]*(\d{1,2}[:.]\d{2})""").findAll(txt).toList()
        if (shifts.isNotEmpty()) {
            var added = 0
            for (sh in shifts) {
                val s = sh.groupValues[1].trim().replace('.', ':')
                val e = sh.groupValues[2].trim().replace('.', ':')
                val after = txt.substring(sh.range.last + 1).trim()
                val comb = listOf(after, extra).filter { it.isNotEmpty() }.joinToString("\n")
                if (saveWorkShift(calId, "$d.$m.$y", s, e, comb, fmt)) added++
            }
            return Pair(shifts.size, added)
        }
        return Pair(0, 0)
    }

    private fun extractLocAndDesc(startStr: String, raw: String): Pair<String, String> {
        val lines = raw.lines().map { it.trim() }.filter {
            it.length > 2 &&
                !it.equals("Uusi", true) &&
                !it.equals("Lisää uusi", true) &&
                !it.equals("Valinnat", true) &&
                !it.startsWith("Vk", true) &&
                !it.startsWith("Viikko", true) &&
                !Regex("""^\d{1,2}$""").matches(it) &&
                !isIgnoredEntry(it)
        }

        val h = startStr.substringBefore(":").toIntOrNull() ?: 7
        val fallbackDesc = if (h < 11) "Aamuvuoro" else if (h < 18) "Iltavuoro" else "Yövuoro"

        if (lines.isEmpty()) {
            return Pair("", fallbackDesc)
        }

        // Poistetaan rivin alusta epäolennaiset prosentti-/kustannusnumerot (esim. "90 ", "60 ", "30")
        val cleaned = lines[0]
            .replace(Regex("""^\d{1,4}\s*(?=[A-ZÅÄÖ])"""), "")
            .replace(Regex("""\s+"""), " ")
            .trim()

        // Erotetaan työn suoritussijainti (esim. "Outokumpu Onni") ja vuoron kuvaus ("ilta hoitaja", "aamu hoitaja")
        val shiftSplitRegex = Regex(
            """^(.*?)\s+((?:aamu|ilta|yö|päivä|väli|pitkä|tupla|viikonloppu|ilta\s+välivuoro|aamu\s+välivuoro).*)$""",
            RegexOption.IGNORE_CASE
        )
        val match = shiftSplitRegex.find(cleaned)
        if (match != null) {
            val location = match.groupValues[1].trim().trim(',', '-', ':')
            val roleDesc = match.groupValues[2].trim().replaceFirstChar {
                if (it.isLowerCase()) it.titlecase(Locale.getDefault()) else it.toString()
            }
            return Pair(location, roleDesc.ifEmpty { fallbackDesc })
        }

        // Jos rivillä ei ole erillistä vuorokuvausta, tulkitaan teksti sijainniksi jos se alkaa isolla kirjaimella
        if (cleaned.isNotEmpty() && cleaned[0].isUpperCase()) {
            val secondLineDesc = lines.getOrNull(1)?.takeIf { it.isNotBlank() } ?: fallbackDesc
            return Pair(cleaned, secondLineDesc)
        }

        return Pair("", cleaned.ifEmpty { fallbackDesc })
    }

    private fun saveWorkShift(calId: Long, dateStr: String, startStr: String, endStr: String, raw: String, fmt: DateTimeFormatter): Boolean {
        if (isIgnoredEntry(raw)) return false
        return try {
            val sDt = LocalDateTime.parse("$dateStr $startStr", fmt)
            var eDt = LocalDateTime.parse("$dateStr $endStr", fmt)
            if (eDt.isBefore(sDt)) eDt = eDt.plusDays(1)
            val sMs = sDt.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            val eMs = eDt.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            if (eMs < System.currentTimeMillis()) return false

            syncedShiftRangesInBatch.add(Pair(sMs, eMs))

            val (loc, desc) = extractLocAndDesc(startStr, raw)
            val workplace = if (loc.isNotEmpty()) loc else "Outokumpu Onni"
            val finalLocation = if (desc.isNotEmpty()) "$workplace, $desc" else workplace
            if (loc.isEmpty() || desc.isEmpty()) {
                missingFieldsCount++
            }
            val dayStartMs = sDt.toLocalDate().atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli()
            val dayEndMs = sDt.toLocalDate().plusDays(1).atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli()
            val exId = findShiftOnSameDay(calId, sMs, eMs, dayStartMs, dayEndMs)

            if (exId == null) {
                val newId = insertEvent(calId, "Työvuoro", finalLocation, desc, sMs, eMs, false, sDt.hour)
                if (newId != null) {
                    syncChangesList.add(SyncChangeItem(newId, "ADDED", dateStr, "$startStr - $endStr", desc.ifEmpty { "Työvuoro" }))
                }
                newId != null
            } else {
                val updated = updateEvent(calId, exId, finalLocation, desc, sMs, eMs, sDt.hour)
                if (updated) {
                    syncChangesList.add(SyncChangeItem(exId, "UPDATED", dateStr, "$startStr - $endStr", desc.ifEmpty { "Työvuoro" }))
                }
                updated
            }
        } catch (_: Exception) {
            false
        }
    }

    private fun findShiftOnSameDay(calId: Long, sMs: Long, eMs: Long, dayStartMs: Long, dayEndMs: Long): Long? {
        val exactSel = "${CalendarContract.Events.CALENDAR_ID} = ? AND ${CalendarContract.Events.DTSTART} = ? AND ${CalendarContract.Events.DTEND} = ? AND ${CalendarContract.Events.DELETED} = 0"
        contentResolver.query(
            CalendarContract.Events.CONTENT_URI,
            arrayOf(CalendarContract.Events._ID),
            exactSel,
            arrayOf(calId.toString(), sMs.toString(), eMs.toString()),
            null
        )?.use {
            if (it.moveToFirst()) return it.getLong(0)
        }
        val daySel = "${CalendarContract.Events.CALENDAR_ID} = ? AND ${CalendarContract.Events.TITLE} = ? AND ${CalendarContract.Events.DTSTART} >= ? AND ${CalendarContract.Events.DTSTART} < ? AND ${CalendarContract.Events.DELETED} = 0"
        contentResolver.query(
            CalendarContract.Events.CONTENT_URI,
            arrayOf(CalendarContract.Events._ID, CalendarContract.Events.DTSTART, CalendarContract.Events.DTEND),
            daySel,
            arrayOf(calId.toString(), "Työvuoro", dayStartMs.toString(), dayEndMs.toString()),
            null
        )?.use {
            while (it.moveToNext()) {
                val id = it.getLong(0)
                val oldStart = it.getLong(1)
                val oldEnd = it.getLong(2)
                if (!syncedShiftRangesInBatch.contains(Pair(oldStart, oldEnd))) {
                    return id
                }
            }
        }
        return null
    }

    private fun updateEvent(calId: Long, eventId: Long, loc: String, desc: String, sMs: Long, eMs: Long, startHour: Int): Boolean {
        var curLoc = ""
        var curDesc = ""
        var curStart = 0L
        var curEnd = 0L
        var curColor = 0
        contentResolver.query(
            CalendarContract.Events.CONTENT_URI,
            arrayOf(CalendarContract.Events.EVENT_LOCATION, CalendarContract.Events.DESCRIPTION, CalendarContract.Events.DTSTART, CalendarContract.Events.DTEND, CalendarContract.Events.EVENT_COLOR),
            "${CalendarContract.Events._ID} = ?",
            arrayOf(eventId.toString()),
            null
        )?.use {
            if (it.moveToFirst()) {
                curLoc = it.getString(0) ?: ""
                curDesc = it.getString(1) ?: ""
                curStart = it.getLong(2)
                curEnd = it.getLong(3)
                curColor = if (!it.isNull(4)) it.getInt(4) else 0
            }
        }
        val targetColor = VuorovahtiHelper.getShiftEventColor(desc.ifEmpty { "Työvuoro" }, startHour)
        val timeChanged = (curStart != sMs || curEnd != eMs)
        val textChanged = (curLoc != loc || (desc.isNotEmpty() && curDesc != desc))
        val colorMissing = (curColor != targetColor)

        if (!timeChanged && !textChanged && !colorMissing) return false

        val v = ContentValues().apply {
            put(CalendarContract.Events.TITLE, "Työvuoro")
            put(CalendarContract.Events.DTSTART, sMs)
            put(CalendarContract.Events.DTEND, eMs)
            put(CalendarContract.Events.EVENT_LOCATION, loc)
            if (desc.isNotEmpty()) put(CalendarContract.Events.DESCRIPTION, desc)
            applyColorWithFallback(this, calId, desc.ifEmpty { "Työvuoro" }, startHour)
        }
        try {
            contentResolver.update(CalendarContract.Events.CONTENT_URI, v, "${CalendarContract.Events._ID} = ?", arrayOf(eventId.toString()))
        } catch (_: Exception) {
            v.remove(CalendarContract.Events.EVENT_COLOR_KEY)
            try {
                contentResolver.update(CalendarContract.Events.CONTENT_URI, v, "${CalendarContract.Events._ID} = ?", arrayOf(eventId.toString()))
            } catch (_: Exception) {
                v.remove(CalendarContract.Events.EVENT_COLOR)
                contentResolver.update(CalendarContract.Events.CONTENT_URI, v, "${CalendarContract.Events._ID} = ?", arrayOf(eventId.toString()))
            }
        }
        return timeChanged || textChanged
    }

    private fun reconcileRemovedShifts(calId: Long): Int {
        if (syncedDatesInBatch.size < 5 || totalFoundInBatch == 0) return 0
        val zone = ZoneId.systemDefault()
        val now = System.currentTimeMillis()
        var removedCount = 0

        for (date in syncedDatesInBatch) {
            val dayStartMs = date.atStartOfDay(zone).toInstant().toEpochMilli()
            val dayEndMs = date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
            if (dayEndMs < now) continue

            val sel = "${CalendarContract.Events.CALENDAR_ID} = ? AND ${CalendarContract.Events.TITLE} = ? AND ${CalendarContract.Events.DTSTART} >= ? AND ${CalendarContract.Events.DTSTART} < ? AND ${CalendarContract.Events.DELETED} = 0"
            val args = arrayOf(calId.toString(), "Työvuoro", dayStartMs.toString(), dayEndMs.toString())

            val idsToDelete = mutableListOf<Long>()
            val timeFmt = DateTimeFormatter.ofPattern("HH:mm")
            val dateStr = "${date.dayOfMonth}.${date.monthValue}.${date.year}"
            contentResolver.query(
                CalendarContract.Events.CONTENT_URI,
                arrayOf(CalendarContract.Events._ID, CalendarContract.Events.DTSTART, CalendarContract.Events.DTEND, CalendarContract.Events.DESCRIPTION),
                sel,
                args,
                null
            )?.use { c ->
                while (c.moveToNext()) {
                    val id = c.getLong(0)
                    val sMs = c.getLong(1)
                    val eMs = c.getLong(2)
                    val desc = c.getString(3) ?: "Työvuoro"
                    if (sMs > now && !syncedShiftRangesInBatch.contains(Pair(sMs, eMs))) {
                        idsToDelete.add(id)
                        val sStr = Instant.ofEpochMilli(sMs).atZone(zone).toLocalTime().format(timeFmt)
                        val eStr = Instant.ofEpochMilli(eMs).atZone(zone).toLocalTime().format(timeFmt)
                        syncChangesList.add(SyncChangeItem(id, "REMOVED", dateStr, "$sStr - $eStr", desc.ifEmpty { "Työvuoro" }))
                    }
                }
            }
            for (id in idsToDelete) {
                contentResolver.delete(CalendarContract.Events.CONTENT_URI, "${CalendarContract.Events._ID} = ?", arrayOf(id.toString()))
                removedCount++
            }
        }
        return removedCount
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun triggerSilentDailySyncIfNeeded() {
        if (isDemoActive || isSilentSyncRunning || isBackgroundListSync || pendingAutoStamp) return
        if (!VuorovahtiHelper.shouldRunDailySilentSync(this)) return

        isSilentSyncRunning = true
        var silentPagesLeft = 2

        val bgWeb = WebView(this).apply {
            layoutParams = FrameLayout.LayoutParams(1, 1)
            alpha = 0.01f
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.databaseEnabled = true
        }
        CookieManager.getInstance().setAcceptThirdPartyCookies(bgWeb, true)
        addContentView(bgWeb, FrameLayout.LayoutParams(1, 1))
        silentSyncWebView = bgWeb

        fun cleanupSilentSync() {
            isSilentSyncRunning = false
            (silentSyncWebView?.parent as? ViewGroup)?.removeView(silentSyncWebView)
            silentSyncWebView?.destroy()
            silentSyncWebView = null
        }

        resetSyncBatch(0)

        bgWeb.addJavascriptInterface(
            object {
                @JavascriptInterface
                fun onSilentData(cellsJson: String, pageText: String, currentUrl: String) {
                    runOnUiThread {
                        val calId = getTargetOrPrimaryCalendarId()
                        if (calId != null) {
                            val (found, added) = parseAndInsertCalendar(cellsJson, pageText, currentUrl, calId)
                            totalFoundInBatch += found
                            totalAddedInBatch += added
                            if (silentPagesLeft > 0) {
                                silentPagesLeft--
                                bgWeb.evaluateJavascript(
                                    """
                                    (function() {
                                        var el = document.querySelector('a.nextButton, .nextButton, .vismaicon-arrow-right-circle, a[title*="Seuraava" i], button[title*="Seuraava" i], .fa-chevron-right, .fc-next-button');
                                        if (el) {
                                            var clickable = el.closest('a, button') || el;
                                            if (clickable.href && clickable.href.indexOf('#') === -1 && !clickable.getAttribute('onclick')) {
                                                window.location.href = clickable.href;
                                            } else {
                                                clickable.click();
                                            }
                                            return "NEXT";
                                        }
                                        return "NONE";
                                    })();
                                    """.trimIndent()
                                ) { res ->
                                    if (res?.contains("NEXT") == true) {
                                        bgWeb.postDelayed({
                                            bgWeb.evaluateJavascript(
                                                """
                                                var cells=[]; var tds=document.querySelectorAll("td"); for(var j=0;j<tds.length;j++){var td=tds[j]; var cls=(td.className||"").toLowerCase(); if(/week|vk|wk/.test(cls)) continue; cells.push({text:(td.innerText||"").trim(), isOther:/other|old|new|disabled|off|outside|gray|grey/.test(cls), extra:""});} AndroidSilentBridge.onSilentData(JSON.stringify(cells), document.body ? document.body.innerText : "", window.location.href);
                                                """.trimIndent(),
                                                null
                                            )
                                        }, 1500L)
                                    } else {
                                        reconcileRemovedShifts(calId)
                                        VuorovahtiHelper.saveLastSyncStatus(this@MainActivity, totalFoundInBatch)
                                        VuorovahtiHelper.ensureRemindersFromCalendar(this@MainActivity)
                                        cleanupSilentSync()
                                    }
                                }
                            } else {
                                reconcileRemovedShifts(calId)
                                VuorovahtiHelper.saveLastSyncStatus(this@MainActivity, totalFoundInBatch)
                                VuorovahtiHelper.ensureRemindersFromCalendar(this@MainActivity)
                                cleanupSilentSync()
                            }
                        } else {
                            cleanupSilentSync()
                        }
                    }
                }
            },
            "AndroidSilentBridge"
        )

        bgWeb.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                val u = url ?: ""
                if (u.contains("login", ignoreCase = true) || u.contains("auth", ignoreCase = true)) {
                    cleanupSilentSync()
                    return
                }
                if (u.contains("/Calendar/", ignoreCase = true)) {
                    view?.postDelayed({
                        view.evaluateJavascript(
                            """
                            (function() {
                                var cells = [];
                                var tds = document.querySelectorAll('td');
                                for (var j = 0; j < tds.length; j++) {
                                    var td = tds[j];
                                    var cls = (td.className || "").toLowerCase();
                                    if (/week|vk|wk/.test(cls)) continue;
                                    cells.push({ text: (td.innerText || "").trim(), isOther: /other|old|new|disabled|off|outside|gray|grey/.test(cls), extra: "" });
                                }
                                AndroidSilentBridge.onSilentData(JSON.stringify(cells), document.body ? document.body.innerText : "", window.location.href);
                            })();
                            """.trimIndent(),
                            null
                        )
                    }, 1000L)
                }
            }
        }
        bgWeb.loadUrl(urlCalendar)
        webView.postDelayed({ if (isSilentSyncRunning) cleanupSilentSync() }, 15000L)
    }

    private fun saveGroupedVacations(calId: Long, rawDays: List<LocalDate>): Int {
        val days = rawDays.distinct().sorted()
        if (days.isEmpty()) return 0
        var addedCount = 0
        var startDate = days[0]
        var endDate = days[0]
        for (i in 1 until days.size) {
            val current = days[i]
            val gapDays = ChronoUnit.DAYS.between(endDate, current)
            val isWeekendBridge = gapDays in 2..3 &&
                (endDate.dayOfWeek == DayOfWeek.FRIDAY || endDate.dayOfWeek == DayOfWeek.SATURDAY) &&
                current.dayOfWeek == DayOfWeek.MONDAY
            if (gapDays == 1L || isWeekendBridge) {
                endDate = current
            } else {
                if (saveCleanVacationPeriod(calId, startDate, endDate)) addedCount++
                startDate = current
                endDate = current
            }
        }
        if (saveCleanVacationPeriod(calId, startDate, endDate)) addedCount++
        return addedCount
    }

    private fun saveCleanVacationPeriod(calId: Long, startDate: LocalDate, endDate: LocalDate): Boolean {
        return try {
            var minStartMs = startDate.atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()
            var maxEndMs = endDate.plusDays(1).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()
            val oneDayMs = 24 * 60 * 60 * 1000L
            val sel = "${CalendarContract.Events.CALENDAR_ID} = ? AND ${CalendarContract.Events.TITLE} = ? AND ${CalendarContract.Events.DTSTART} <= ? AND ${CalendarContract.Events.DTEND} >= ? AND ${CalendarContract.Events.DELETED} = 0"
            val args = arrayOf(calId.toString(), "Loma", (maxEndMs + oneDayMs).toString(), (minStartMs - oneDayMs).toString())
            val existingIds = mutableListOf<Long>()
            contentResolver.query(
                CalendarContract.Events.CONTENT_URI,
                arrayOf(CalendarContract.Events._ID, CalendarContract.Events.DTSTART, CalendarContract.Events.DTEND),
                sel,
                args,
                null
            )?.use { c ->
                while (c.moveToNext()) {
                    existingIds.add(c.getLong(0))
                    minStartMs = minOf(minStartMs, c.getLong(1))
                    maxEndMs = maxOf(maxEndMs, c.getLong(2))
                }
            }
            if (existingIds.size == 1) {
                val v = ContentValues().apply {
                    put(CalendarContract.Events.DTSTART, minStartMs)
                    put(CalendarContract.Events.DTEND, maxEndMs)
                    put(CalendarContract.Events.ALL_DAY, 1)
                    put(CalendarContract.Events.EVENT_TIMEZONE, "UTC")
                }
                contentResolver.update(CalendarContract.Events.CONTENT_URI, v, "${CalendarContract.Events._ID} = ?", arrayOf(existingIds[0].toString()))
                return true
            } else if (existingIds.size > 1) {
                for (id in existingIds) {
                    contentResolver.delete(CalendarContract.Events.CONTENT_URI, "${CalendarContract.Events._ID} = ?", arrayOf(id.toString()))
                }
            }
            insertEvent(calId, "Loma", "", "Vuosiloma", minStartMs, maxEndMs, true, 0)
            true
        } catch (_: Exception) {
            false
        }
    }

    private fun getTargetOrPrimaryCalendarId(): Long? {
        val proj = arrayOf(CalendarContract.Calendars._ID)
        val preferredId = SettingsManager.getTargetCalendarId(this)
        if (preferredId != -1L) {
            contentResolver.query(CalendarContract.Calendars.CONTENT_URI, proj, "${CalendarContract.Calendars._ID} = ?", arrayOf(preferredId.toString()), null)?.use {
                if (it.moveToFirst()) return it.getLong(0)
            }
        }
        contentResolver.query(CalendarContract.Calendars.CONTENT_URI, proj, "${CalendarContract.Calendars.IS_PRIMARY} = 1", null, null)?.use {
            if (it.moveToFirst()) return it.getLong(0)
        }
        contentResolver.query(CalendarContract.Calendars.CONTENT_URI, proj, "${CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL} >= ${CalendarContract.Calendars.CAL_ACCESS_CONTRIBUTOR}", null, null)?.use {
            if (it.moveToFirst()) return it.getLong(0)
        }
        return null
    }

    private fun applyColorWithFallback(v: ContentValues, calId: Long, label: String, startHour: Int) {
        val targetColor = VuorovahtiHelper.getShiftEventColor(label, startHour)
        v.put(CalendarContract.Events.EVENT_COLOR, targetColor)
        try {
            var accountName = ""
            var accountType = ""
            contentResolver.query(
                CalendarContract.Calendars.CONTENT_URI,
                arrayOf(CalendarContract.Calendars.ACCOUNT_NAME, CalendarContract.Calendars.ACCOUNT_TYPE),
                "${CalendarContract.Calendars._ID} = ?",
                arrayOf(calId.toString()),
                null
            )?.use { c ->
                if (c.moveToFirst()) {
                    accountName = c.getString(0) ?: ""
                    accountType = c.getString(1) ?: ""
                }
            }
            if (accountName.isNotEmpty() && accountType.isNotEmpty()) {
                var bestKey: String? = null
                var bestDist = Int.MAX_VALUE
                val r1 = Color.red(targetColor)
                val g1 = Color.green(targetColor)
                val b1 = Color.blue(targetColor)
                contentResolver.query(
                    CalendarContract.Colors.CONTENT_URI,
                    arrayOf(CalendarContract.Colors.COLOR_KEY, CalendarContract.Colors.COLOR),
                    "${CalendarContract.Colors.ACCOUNT_NAME} = ? AND ${CalendarContract.Colors.ACCOUNT_TYPE} = ? AND ${CalendarContract.Colors.COLOR_TYPE} = ?",
                    arrayOf(accountName, accountType, CalendarContract.Colors.TYPE_EVENT.toString()),
                    null
                )?.use { cc ->
                    while (cc.moveToNext()) {
                        val key = cc.getString(0) ?: continue
                        val col = cc.getInt(1)
                        val dist = (r1 - Color.red(col)) * (r1 - Color.red(col)) +
                            (g1 - Color.green(col)) * (g1 - Color.green(col)) +
                            (b1 - Color.blue(col)) * (b1 - Color.blue(col))
                        if (dist < bestDist) {
                            bestDist = dist
                            bestKey = key
                        }
                    }
                }
                if (bestKey != null) {
                    v.put(CalendarContract.Events.EVENT_COLOR_KEY, bestKey)
                }
            }
        } catch (_: Exception) {}
    }

    private fun insertEvent(calId: Long, title: String, loc: String, desc: String, sMs: Long, eMs: Long, allDay: Boolean, startHour: Int = 8): Long? {
        val colorLabel = if (allDay) "Loma" else desc.ifEmpty { title }
        val v = ContentValues().apply {
            put(CalendarContract.Events.TITLE, title)
            put(CalendarContract.Events.DTSTART, sMs)
            put(CalendarContract.Events.DTEND, eMs)
            put(CalendarContract.Events.EVENT_LOCATION, loc)
            put(CalendarContract.Events.DESCRIPTION, desc)
            put(CalendarContract.Events.CALENDAR_ID, calId)
            put(CalendarContract.Events.ALL_DAY, if (allDay) 1 else 0)
            put(CalendarContract.Events.EVENT_TIMEZONE, if (allDay) "UTC" else ZoneId.systemDefault().id)
            applyColorWithFallback(this, calId, colorLabel, startHour)
        }
        return try {
            contentResolver.insert(CalendarContract.Events.CONTENT_URI, v)?.lastPathSegment?.toLongOrNull()
        } catch (_: Exception) {
            v.remove(CalendarContract.Events.EVENT_COLOR_KEY)
            try {
                contentResolver.insert(CalendarContract.Events.CONTENT_URI, v)?.lastPathSegment?.toLongOrNull()
            } catch (_: Exception) {
                v.remove(CalendarContract.Events.EVENT_COLOR)
                contentResolver.insert(CalendarContract.Events.CONTENT_URI, v)?.lastPathSegment?.toLongOrNull()
            }
        }
    }
}
