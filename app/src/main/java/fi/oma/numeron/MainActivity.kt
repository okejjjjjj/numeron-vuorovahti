package fi.oma.numeron

import android.Manifest
import android.annotation.SuppressLint
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.ColorStateList
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
import android.webkit.*
import android.widget.*
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import org.json.JSONArray
import java.text.SimpleDateFormat
import java.time.*
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Date
import java.util.Locale

object VuorovahtiHelper {

    // 1. Määritä kalenterimerkinnän väri vuoron alkamisajan tai tyypin mukaan
    fun getShiftEventColor(title: String, startHour: Int): Int {
        val lowerTitle = title.trim().lowercase(Locale.getDefault())
        return when {
            lowerTitle == "loma" || lowerTitle.contains("vuosiloma") -> Color.parseColor("#00ACC1") // Turkoosi (Loma)
            startHour in 5..10 -> Color.parseColor("#43A047")  // Vihreä (Aamuvuoro)
            startHour in 11..17 -> Color.parseColor("#FB8C00") // Oranssi (Iltavuoro)
            else -> Color.parseColor("#8E24AA")                // Violetti (Yövuoro)
        }
    }

    fun applyShiftColor(values: ContentValues, title: String, startHour: Int) {
        values.put(CalendarContract.Events.EVENT_COLOR, getShiftEventColor(title, startHour))
    }

    // 2. Tallenna ja hae "Viimeksi synkronoitu" -aikaleima sekä vuorovaihdosten taustatarkistusaika
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
            ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return false
        }
        val lastMs = context.getSharedPreferences("vuorovahti_prefs", Context.MODE_PRIVATE)
            .getLong("last_sync_millis", 0L)
        return (System.currentTimeMillis() - lastMs) > 18L * 60 * 60 * 1000L
    }

    // 3. Tallenna ja hae edellinen toteutunut sekä seuraava tuleva leimausmuistutus
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
        shiftKeywords: List<String> = listOf("työvuoro", "aamuvuoro", "iltavuoro", "yövuoro", "vuoro")
    ): String {
        if (!SettingsManager.isStampNotificationEnabled(context)) {
            return "Ei käytössä (leimausmuistutukset kytketty pois)"
        }
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR)
            != PackageManager.PERMISSION_GRANTED) {
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
            val titleIdx = cursor.getColumnIndex(CalendarContract.Events.TITLE)
            val descIdx = cursor.getColumnIndex(CalendarContract.Events.DESCRIPTION)
            val startIdx = cursor.getColumnIndex(CalendarContract.Events.DTSTART)
            val endIdx = cursor.getColumnIndex(CalendarContract.Events.DTEND)

            while (cursor.moveToNext()) {
                val title = cursor.getString(titleIdx) ?: continue
                val desc = if (descIdx != -1) (cursor.getString(descIdx) ?: "") else ""
                val startTime = cursor.getLong(startIdx)
                val endTime = if (endIdx != -1) cursor.getLong(endIdx) else 0L

                val lowerTitle = title.lowercase(Locale.getDefault())
                val isWorkShift = shiftKeywords.any { lowerTitle.contains(it) } &&
                                  !lowerTitle.contains("loma") &&
                                  !lowerTitle.contains("vapaa")

                if (isWorkShift) {
                    val shiftName = desc.lines().firstOrNull()?.takeIf { it.isNotBlank() } ?: title
                    val startTrigger = startTime - (reminderMinutesBefore * 60 * 1000L)
                    if (startTrigger > now && startTrigger < earliestTrigger) {
                        earliestTrigger = startTrigger
                        earliestDesc = "${dateFmt.format(Date(startTrigger))} (Sisäänleimaus – $shiftName klo ${hourFmt.format(Date(startTime))})"
                    }

                    if (endTime > startTime) {
                        val endTrigger = endTime - (reminderMinutesBefore * 60 * 1000L)
                        if (endTrigger > now && endTrigger < earliestTrigger) {
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

    // 4. Napakka haptinen värinäpalaute
    fun triggerConfirmHaptics(view: View) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            view.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
        } else {
            view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
        }
    }

    // 5. Tarkista onko kyseessä Demo-käyttäjä
    fun isDemoMode(username: String?, password: String?): Boolean {
        return username?.trim().equals("demo", ignoreCase = true) &&
               password?.trim().equals("demo", ignoreCase = true)
    }

    // 6. Ajastaa 3 viikon listantarkistuksen (toimii myös suoraan puhelimen buutin jälkeen)
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
        } catch (e: Exception) { e.printStackTrace() }
    }

    // 7. Siivoaa vanhat/perutut hälytykset ja asettaa voimassa olevat hälytykset kalenterista
    fun ensureRemindersFromCalendar(
        context: Context,
        reminderMinutesBefore: Int = 30,
        shiftKeywords: List<String> = listOf("työvuoro", "aamuvuoro", "iltavuoro", "yövuoro", "vuoro")
    ) {
        scheduleNextThreeWeekListCheck(context)

        val prefs = context.getSharedPreferences("vuorovahti_prefs", Context.MODE_PRIVATE)
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager

        val oldCodes = prefs.getStringSet("active_alarm_codes", emptySet()) ?: emptySet()
        for (codeStr in oldCodes) {
            val code = codeStr.toIntOrNull() ?: continue
            val cancelIntent = Intent(context, ShiftAlarmReceiver::class.java)
            val pi = PendingIntent.getBroadcast(
                context,
                code,
                cancelIntent,
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
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR)
            != PackageManager.PERMISSION_GRANTED) {
            return
        }

        val now = System.currentTimeMillis()
        val twoWeeksAhead = now + 14L * 24 * 60 * 60 * 1000L
        val newCodes = mutableSetOf<String>()

        val projection = arrayOf(
            CalendarContract.Events._ID,
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
            val titleIdx = cursor.getColumnIndex(CalendarContract.Events.TITLE)
            val descIdx = cursor.getColumnIndex(CalendarContract.Events.DESCRIPTION)
            val startIdx = cursor.getColumnIndex(CalendarContract.Events.DTSTART)
            val endIdx = cursor.getColumnIndex(CalendarContract.Events.DTEND)

            while (cursor.moveToNext()) {
                val title = cursor.getString(titleIdx) ?: continue
                val desc = if (descIdx != -1) (cursor.getString(descIdx) ?: "") else ""
                val startTime = cursor.getLong(startIdx)
                val endTime = if (endIdx != -1) cursor.getLong(endIdx) else 0L

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
        } catch (e: SecurityException) {
            alarmManager.set(AlarmManager.RTC_WAKEUP, triggerTime, pendingIntent)
        }
    }

    // 8. Tarkistaa kalenterista onko huomenna (ja lähipäivinä) vapaata ja palauttaa toivotuksen
    fun getFreeDayGreetingIfApplicable(
        context: Context,
        shiftKeywords: List<String> = listOf("työvuoro", "aamuvuoro", "iltavuoro", "yövuoro", "vuoro")
    ): String? {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR)
            != PackageManager.PERMISSION_GRANTED) {
            return null
        }

        val zone = ZoneId.systemDefault()
        val today = LocalDate.now(zone)
        val tomorrowStart = today.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        val lookAheadEnd = today.plusDays(8).atStartOfDay(zone).toInstant().toEpochMilli()

        val projection = arrayOf(
            CalendarContract.Events.TITLE,
            CalendarContract.Events.DTSTART
        )
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
            val titleIdx = cursor.getColumnIndex(CalendarContract.Events.TITLE)
            val startIdx = cursor.getColumnIndex(CalendarContract.Events.DTSTART)

            while (cursor.moveToNext()) {
                val title = cursor.getString(titleIdx) ?: continue
                val startMs = cursor.getLong(startIdx)
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
            "Hyvää huomista vapaapäivää! ☀️",
            "Huomenna ei ole vuoroa – rentouttavaa vapaapäivää! ☕",
            "Vuoro paketissa ja huominen vapaana. Nauti vapaapäivästä! 🛋️",
            "Ansaittu huili edessä – mukavaa vapaapäivää! 🌿"
        )

        val multiDayGreetings = listOf(
            "Edessä useampi vapaapäivä – mukavia ja rentouttavia vapaita! 🎉",
            "Työputki takana! Nauti tulevista vapaapäivistä! 🌲",
            "Hyviä vapaita! Nyt voi nollata ajatukset ihan rauhassa. ✨",
            "Vapaat alkoivat nyt – oikein mukavia vapaapäiviä! 🔋"
        )

        return if (freeDaysCount == 1) {
            singleDayGreetings.random()
        } else {
            multiDayGreetings.random()
        }
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

    private var pendingAutoStamp = false
    private var pendingStampIsEnding = false
    private var autoStampClickDone = false
    private var autoStampRetryCount = 0
    private var waitingForListViewSync = false
    private var lastAutoLoginAttempt = 0L

    private var pagesRemainingToSync = 0
    private var totalFoundInBatch = 0
    private var totalAddedInBatch = 0
    private var totalRemovedInBatch = 0
    private var isBackgroundListSync = false
    private var forceListOnNextCalendarLoad = false
    private var lastKnownBaseUrl = ""

    private val syncedDatesInBatch = mutableSetOf<LocalDate>()
    private val syncedShiftRangesInBatch = mutableSetOf<Pair<Long, Long>>()
    private var silentSyncWebView: WebView? = null
    private var isSilentSyncRunning = false

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
        val biometricPrompt = BiometricPrompt(this, executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    super.onAuthenticationSucceeded(result)
                    VuorovahtiHelper.triggerConfirmHaptics(window.decorView)
                    onSuccess()
                }
            })

        val promptInfo = BiometricPrompt.PromptInfo.Builder()
            .setTitle(title)
            .setSubtitle("Vahvista sormenjäljellä tai lukituskoodilla")
            .setAllowedAuthenticators(authenticators)
            .build()

        biometricPrompt.authenticate(promptInfo)
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        lastKnownBaseUrl = if (isDemoActive) "demo" else SettingsManager.getBaseUrl(this)

        val rootFrame = FrameLayout(this).apply {
            layoutParams = FrameLayout.LayoutParams(-1, -1)
            setBackgroundColor(Color.parseColor("#0F172A"))
            fitsSystemWindows = true
        }

        mainColumn = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = FrameLayout.LayoutParams(-1, -1)
            setBackgroundColor(Color.parseColor("#0F172A"))
        }

        VuorovahtiHelper.ensureRemindersFromCalendar(this)

        webView = WebView(this).apply {
            layoutParams = LinearLayout.LayoutParams(-1, 0, 1f)
            setBackgroundColor(Color.parseColor("#0F172A"))
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                databaseEnabled = true
                setSupportZoom(true)
                builtInZoomControls = true
                displayZoomControls = false
            }
            webChromeClient = object : WebChromeClient() {
                override fun onJsAlert(view: WebView?, url: String?, message: String?, result: JsResult?): Boolean {
                    val msg = (message ?: "").lowercase()
                    if (msg.contains("istunto") || msg.contains("session") || msg.contains("vanhentu") || msg.contains("kirjaudu")) {
                        result?.confirm()
                        view?.loadUrl(urlStamping)
                        return true
                    }
                    return super.onJsAlert(view, url, message, result)
                }

                override fun onJsConfirm(view: WebView?, url: String?, message: String?, result: JsResult?): Boolean {
                    val msg = (message ?: "").lowercase()
                    if (msg.contains("istunto") || msg.contains("session") || msg.contains("vanhentu") || msg.contains("kirjaudu")) {
                        result?.confirm()
                        view?.loadUrl(urlStamping)
                        return true
                    }
                    return super.onJsConfirm(view, url, message, result)
                }
            }
            webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
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
                        view?.loadUrl(urlStamping)
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
                    } else if (forceListOnNextCalendarLoad && (currentUrl.contains("/Calendar/", ignoreCase = true) || currentUrl.contains("demo_shifts", ignoreCase = true)) && !currentUrl.contains("login", ignoreCase = true)) {
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
            setBackgroundColor(Color.parseColor("#0F172A"))
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
                textSize = 11.5f
                setTextColor(Color.WHITE)
                isAllCaps = false
                setPadding(6, 8, 6, 8)
                minHeight = 0
                minimumHeight = 0
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, weight).apply {
                    marginStart = 5
                    marginEnd = 5
                }
                setOnClickListener { action() }
            }
        }

        btnStamp = createNavButton("Leimaus") { webView.loadUrl(urlStamping) }.apply {
            setOnLongClickListener { openSettings(); true }
        }
        btnWishes = createNavButton("Toiveet") { webView.loadUrl(urlWishes) }
        btnCalendar = createNavButton("Vuorot") { webView.loadUrl(urlCalendar) }
        btnSync = createNavButton("Synkronoi") { checkPermissionsAndSync() }.apply {
            visibility = View.GONE
        }
        btnSettings = createNavButton("⚙", 0.55f) { openSettings() }
        btnClose = createNavButton("✕", 0.55f) { finishAndRemoveTask() }

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
        scheduleNextThreeWeekListCheck()

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (stampOverlay.visibility == View.VISIBLE) {
                    pendingAutoStamp = false
                    isBackgroundListSync = false
                    hideStampOverlay()
                } else if (webView.canGoBack()) {
                    webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })

        if (SettingsManager.isFirstRun(this) && !pendingAutoStamp && !isBackgroundListSync) {
            checkAndRequestAllPermissions()
            openSettings()
        }

        if (!isBackgroundListSync) {
            webView.loadUrl(urlStamping)
        }
    }

    private fun openSettings() {
        startActivity(Intent(this, SettingsActivity::class.java))
    }

    override fun onResume() {
        super.onResume()
        VuorovahtiHelper.ensureRemindersFromCalendar(this)
        val currentBase = if (isDemoActive) "demo" else SettingsManager.getBaseUrl(this)
        if (lastKnownBaseUrl.isNotEmpty() && lastKnownBaseUrl != currentBase) {
            lastKnownBaseUrl = currentBase
            webView.loadUrl(urlStamping)
        } else if (::webView.isInitialized && !isDemoActive) {
            tryAutoLoginIfNeeded()
        }
        scheduleNextThreeWeekListCheck()
    }

    override fun onDestroy() {
        (silentSyncWebView?.parent as? ViewGroup)?.removeView(silentSyncWebView)
        silentSyncWebView?.destroy()
        silentSyncWebView = null
        super.onDestroy()
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
                if (userEl) setNativeValue(userEl, '$safeU');
                setNativeValue(passEl, '$safeP');
                var submitBtn = document.querySelector('input[type="submit"], button[type="submit"], button[id*="login" i], button[name*="login" i], input[id*="SignIn" i]');
                if (submitBtn && submitBtn.offsetParent !== null) { submitBtn.click(); return "SUBMITTED"; }
                if (passEl.form) { passEl.form.submit(); return "SUBMITTED"; }
                return "FILLED";
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { res ->
            val r = res ?: ""
            val now = System.currentTimeMillis()
            when {
                r.contains("SESSION_EXPIRED_RELOAD") -> webView.loadUrl(if (isBackgroundListSync) urlCalendar else urlStamping)
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
        if (pendingAutoStamp && ::webView.isInitialized) webView.loadUrl(urlStamping)
    }

    private fun handleIncomingIntent(intent: Intent?) {
        val quickAction = intent?.getStringExtra("quick_action")?.trim()
        if (quickAction == "ACTION_STAMP") {
            intent.removeExtra("quick_action")
            if (::webView.isInitialized) webView.loadUrl(urlStamping)
        } else if (quickAction == "ACTION_SYNC") {
            intent.removeExtra("quick_action")
            isBackgroundListSync = true
            forceListOnNextCalendarLoad = true
            pagesRemainingToSync = 3
            totalFoundInBatch = 0
            totalAddedInBatch = 0
            totalRemovedInBatch = 0
            syncedDatesInBatch.clear()
            syncedShiftRangesInBatch.clear()
            showStampOverlay("Synkronoidaan työvuoroja", "Avataan kalenteria...")
            if (::webView.isInitialized) webView.loadUrl(urlCalendar)
        }

        if (intent?.getBooleanExtra("AUTO_STAMP", false) == true) {
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
        if (intent?.getBooleanExtra("AUTO_SYNC_NEW_LIST", false) == true) {
            intent.removeExtra("AUTO_SYNC_NEW_LIST")
            isBackgroundListSync = true
            forceListOnNextCalendarLoad = true
            pagesRemainingToSync = 3
            totalFoundInBatch = 0
            totalAddedInBatch = 0
            totalRemovedInBatch = 0
            syncedDatesInBatch.clear()
            syncedShiftRangesInBatch.clear()
            showStampOverlay("Haetaan uutta työvuorolistaa", "Avataan kalenteria...")
            if (::webView.isInitialized) webView.loadUrl(urlCalendar)
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
                        webView.loadUrl(urlStamping)
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

        val freeDayGreeting = if (wasEnding) {
            VuorovahtiHelper.getFreeDayGreetingIfApplicable(this)
        } else null

        val statusText = if (freeDayGreeting != null) {
            "$freeDayGreeting\n\nSuljetaan sovellus..."
        } else {
            "Suljetaan sovellus..."
        }

        showStampOverlay(" ✓  $message", statusText, showSpinner = false)
        webView.postDelayed({ finishAndRemoveTask() }, if (freeDayGreeting != null) 2600L else 1400L)
    }

    private fun checkPermissionsAndSync() {
        val needed = mutableListOf(Manifest.permission.READ_CALENDAR, Manifest.permission.WRITE_CALENDAR)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) needed.add(Manifest.permission.POST_NOTIFICATIONS)
        val missing = needed.filter { ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 100)
        } else {
            pagesRemainingToSync = if (isDemoActive) 0 else 3
            totalFoundInBatch = 0
            totalAddedInBatch = 0
            totalRemovedInBatch = 0
            syncedDatesInBatch.clear()
            syncedShiftRangesInBatch.clear()
            extractShiftsFromPage(forceList = true)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        VuorovahtiHelper.ensureRemindersFromCalendar(this)
        if (requestCode == 100) {
            val r = ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CALENDAR) == PackageManager.PERMISSION_GRANTED
            val w = ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_CALENDAR) == PackageManager.PERMISSION_GRANTED
            if (r && w) {
                pagesRemainingToSync = if (isDemoActive) 0 else 3
                totalFoundInBatch = 0
                totalAddedInBatch = 0
                totalRemovedInBatch = 0
                syncedDatesInBatch.clear()
                syncedShiftRangesInBatch.clear()
                extractShiftsFromPage(forceList = true)
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
                var bodyText = document.body ? document.body.innerText : "";
                var isGrid = /Vk\.?\s+Ma\s+Ti\s+Ke/i.test(bodyText);
                if ($forceList && isGrid) {
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
                    var links = document.querySelectorAll('a, li, button, span, div');
                    for (var i = 0; i < links.length; i++) {
                        var t = (links[i].innerText || "").trim().toLowerCase();
                        var href = (links[i].getAttribute && links[i].getAttribute('href')) || "";
                        if (t === 'luettelo' || t === 'lista' || href.toLowerCase().indexOf('/calendar/list') !== -1 || href.toLowerCase().indexOf('view=list') !== -1) {
                            links[i].click();
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
                        var extra = [];
                        var ch = td.querySelectorAll('[title], [data-original-title]');
                        for (var c = 0; c < ch.length; c++) {
                            var ti = ch[c].getAttribute('title') || ch[c].getAttribute('data-original-title');
                            if (ti) extra.push(ti);
                        }
                        cells.push({ text: (td.innerText || "").trim(), isOther: isOther, extra: extra.join(" | ") });
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

    inner class CalendarBridge {
        @JavascriptInterface
        fun confirmWishAction(actionTitle: String) {
            runOnUiThread {
                requireBiometricAuth(actionTitle) {
                    webView.evaluateJavascript("""
                        if (window._pendingWishEl) {
                            window._wishAuthApproved = true;
                            window._pendingWishEl.click();
                        }
                    """.trimIndent(), null)
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

                if (pagesRemainingToSync > 0) {
                    pagesRemainingToSync--
                    if (isBackgroundListSync) {
                        showStampOverlay("Haetaan uutta työvuorolistaa", "Tarkistetaan tulevia viikkoja... (muutoksia $totalAddedInBatch)")
                    }
                    clickNextCalendarPeriod(calId)
                } else {
                    totalRemovedInBatch += reconcileRemovedShifts(calId)
                    hideStampOverlay()
                    isBackgroundListSync = false
                    VuorovahtiHelper.saveLastSyncStatus(this@MainActivity, totalFoundInBatch)
                    VuorovahtiHelper.triggerConfirmHaptics(window.decorView)
                    VuorovahtiHelper.ensureRemindersFromCalendar(this@MainActivity)
                    if (totalAddedInBatch > 0) sendNewShiftsAddedNotification(totalAddedInBatch)
                    Toast.makeText(
                        this@MainActivity,
                        "Tarkistettu $totalFoundInBatch merkintää: $totalAddedInBatch lisätty/päivitetty, $totalRemovedInBatch poistettu.",
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        }
    }

    private fun clickNextCalendarPeriod(calId: Long) {
        val js = """
            (function() {
                var nextSelectors = ['a[title*="Seuraava" i]', 'button[title*="Seuraava" i]', '.fa-chevron-right', '.fa-angle-right', '.glyphicon-chevron-right', '.icon-chevron-right', '.fc-next-button'];
                for (var s = 0; s < nextSelectors.length; s++) {
                    var el = document.querySelector(nextSelectors[s]);
                    if (el) { (el.closest('a, button, div, span') || el).click(); return "NEXT_CLICKED"; }
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
                totalRemovedInBatch += reconcileRemovedShifts(calId)
                hideStampOverlay()
                isBackgroundListSync = false
                VuorovahtiHelper.saveLastSyncStatus(this, totalFoundInBatch)
                VuorovahtiHelper.ensureRemindersFromCalendar(this)
                VuorovahtiHelper.triggerConfirmHaptics(window.decorView)
                if (totalAddedInBatch > 0) sendNewShiftsAddedNotification(totalAddedInBatch)
                Toast.makeText(
                    this,
                    "Valmis: $totalAddedInBatch lisätty/päivitetty, $totalRemovedInBatch poistettu.",
                    Toast.LENGTH_LONG
                ).show()
            }
        }
    }

    private fun sendNewShiftsAddedNotification(addedCount: Int) {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channelId = "numeron_list_channel"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(NotificationChannel(channelId, "Uudet työvuorolistat", NotificationManager.IMPORTANCE_HIGH))
        }
        val notif = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(R.drawable.ic_launcher)
            .setSubText("Numeron Vuorovahti")
            .setContentTitle("Uudet työvuorot päivitetty!")
            .setContentText("Kalenteriin vietiin $addedCount uutta tai muuttunutta työvuoroa/lomaa.")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .build()
        nm.notify(3004, notif)
    }

    private fun scheduleNextThreeWeekListCheck() {
        VuorovahtiHelper.scheduleNextThreeWeekListCheck(this)
    }

    private fun resolveMonthAndYear(pageText: String, currentUrl: String): Pair<Int, Int> {
        val months = mapOf("tammikuu" to 1, "helmikuu" to 2, "maaliskuu" to 3, "huhtikuu" to 4, "toukokuu" to 5, "kesäkuu" to 6, "heinäkuu" to 7, "elokuu" to 8, "syyskuu" to 9, "lokakuu" to 10, "marraskuu" to 11, "joulukuu" to 12)
        val mMatch = Regex("""(tammikuu|helmikuu|maaliskuu|huhtikuu|toukokuu|kesäkuu|heinäkuu|elokuu|syyskuu|lokakuu|marraskuu|joulukuu)\s+(\d{4})""", RegexOption.IGNORE_CASE).find(pageText)
        if (mMatch != null) {
            val m = months[mMatch.groupValues[1].lowercase()]
            val y = mMatch.groupValues[2].toIntOrNull()
            if (m != null && y != null) return Pair(m, y)
        }
        val wkYear = Regex("""Vk\.?\s*\d{1,2}\s*/\s*(\d{4})""", RegexOption.IGNORE_CASE).find(pageText)?.groupValues?.get(1)?.toIntOrNull()
        val now = LocalDate.now()
        val uri = try { Uri.parse(currentUrl) } catch (e: Exception) { null }
        return Pair(uri?.getQueryParameter("month")?.toIntOrNull() ?: now.monthValue, uri?.getQueryParameter("year")?.toIntOrNull() ?: wkYear ?: now.year)
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
                    while (!cur.isAfter(end)) { vacationDays.add(cur); cur = cur.plusDays(1) }
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

        var found = 0; var added = 0
        val vacationDays = mutableListOf<LocalDate>()
        found += extractDirectVacationRanges(pageText, targetYear, vacationDays)

        try {
            val arr = JSONArray(cellsJson)
            if (arr.length() > 15) {
                var inMonth = false; var lastDay = 0
                for (i in 0 until arr.length()) {
                    val obj = arr.getJSONObject(i)
                    val txt = obj.optString("text", "").trim()
                    val isOther = obj.optBoolean("isOther", false)
                    val extra = obj.optString("extra", "").trim()
                    val day = Regex("""^(\d{1,2})\b""").find(txt)?.groupValues?.get(1)?.toIntOrNull() ?: continue
                    if (day !in 1..31) continue
                    if (!inMonth) {
                        if (day == 1) { inMonth = true; lastDay = 1 } else continue
                    } else {
                        if (day < lastDay && lastDay >= 20) break
                        if (day == lastDay + 1 || day == lastDay) lastDay = day else continue
                    }
                    if (isOther) continue
                    val res = processDayContent(calId, day, targetMonth, targetYear, txt, extra, fmt, vacationDays)
                    found += res.first; added += res.second
                }
            }
        } catch (e: Exception) { e.printStackTrace() }

        added += saveGroupedVacations(calId, vacationDays)
        return Pair(found, added)
    }

    private fun parseListView(pageText: String, targetMonth: Int, targetYear: Int, calId: Long, fmt: DateTimeFormatter): Pair<Int, Int> {
        var found = 0; var added = 0
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
                val yr = rawYr ?: if (targetMonth == 12 && mo == 1) targetYear + 1 else if (targetMonth == 1 && mo == 12) targetYear - 1 else targetYear
                if (d !in 1..31 || mo !in 1..12) continue
                val sIdx = m.range.last + 1
                val eIdx = if (i + 1 < matches.size) matches[i + 1].range.first else minOf(sIdx + 500, pageText.length)
                if (sIdx >= eIdx) continue
                val res = processListBlock(calId, d, mo, yr, pageText.substring(sIdx, eIdx).trim(), fmt, vacationDays)
                found += res.first; added += res.second
            }
            added += saveGroupedVacations(calId, vacationDays)
            if (found > 0) return Pair(found, added)
        }
        return Pair(found, added)
    }

    private fun processListBlock(calId: Long, d: Int, m: Int, y: Int, block: String, fmt: DateTimeFormatter, vacationDays: MutableList<LocalDate>): Pair<Int, Int> {
        try { syncedDatesInBatch.add(LocalDate.of(y, m, d)) } catch (_: Exception) {}
        if (block.lowercase().let { it.contains("vuosiloma") || it.contains("loma") || Regex("""\bvl\b""").containsMatchIn(it) }) {
            try { vacationDays.add(LocalDate.of(y, m, d)) } catch (_: Exception) {}
            return Pair(1, 0)
        }
        val sMatches = Regex("""(\d{1,2}[:.]\d{2})[\s\t]*[-–][\s\t]*(\d{1,2}[:.]\d{2})""").findAll(block).toList()
        if (sMatches.isNotEmpty()) {
            var added = 0
            for (idx in sMatches.indices) {
                val sMatch = sMatches[idx]
                val s = sMatch.groupValues[1].trim().replace('.', ':')
                val e = sMatch.groupValues[2].trim().replace('.', ':')
                val nextStart = if (idx + 1 < sMatches.size) sMatches[idx + 1].range.first else block.length
                val after = block.substring(sMatch.range.last + 1, nextStart).trim()
                val details = if (after.isNotEmpty()) after else block.substring(0, sMatch.range.first).trim()
                if (saveWorkShift(calId, "$d.$m.$y", s, e, details, fmt)) added++
            }
            return Pair(sMatches.size, added)
        }
        return Pair(0, 0)
    }

    private fun processDayContent(calId: Long, d: Int, m: Int, y: Int, txt: String, extra: String, fmt: DateTimeFormatter, vacationDays: MutableList<LocalDate>): Pair<Int, Int> {
        try { syncedDatesInBatch.add(LocalDate.of(y, m, d)) } catch (_: Exception) {}
        val rest = "${txt.replaceFirst(Regex("""^\d{1,2}\s*"""), "")} $extra".lowercase()
        if (rest.contains("vuosiloma") || rest.contains("loma") || Regex("""\bvl\b""").containsMatchIn(rest)) {
            try { vacationDays.add(LocalDate.of(y, m, d)) } catch (_: Exception) {}
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
            it.length > 2 && !it.equals("Uusi", true) && !it.equals("Lisää uusi", true) &&
            !it.equals("Valinnat", true) && !it.startsWith("Vk", true) &&
            !it.startsWith("Viikko", true) && !Regex("""^\d{1,2}$""").matches(it)
        }
        if (lines.size >= 2) {
            val codeLine = lines.firstOrNull { Regex("""^\d{3,5}\b""").containsMatchIn(it) }
            val roleLine = lines.firstOrNull { it != codeLine }
            return Pair(codeLine ?: lines[0], roleLine ?: lines[1])
        } else if (lines.size == 1) return Pair(lines[0], lines[0])
        val h = startStr.substringBefore(":").toIntOrNull() ?: 7
        return Pair("", if (h < 11) "Aamuvuoro" else if (h < 18) "Iltavuoro" else "Yövuoro")
    }

    private fun scheduleShiftAlarms(startMillis: Long, endMillis: Long, startStr: String, endStr: String, title: String) {
        if (!SettingsManager.isStampNotificationEnabled(this)) return
        try {
            val alarmManager = getSystemService(ALARM_SERVICE) as AlarmManager
            val now = System.currentTimeMillis()
            val startAlarmTime = startMillis - (30 * 60 * 1000L)
            if (startAlarmTime > now) {
                val startIntent = Intent(this, ShiftAlarmReceiver::class.java).apply {
                    putExtra("SHIFT_TITLE", title); putExtra("SHIFT_TIME", startStr); putExtra("IS_ENDING", false)
                }
                val startPi = PendingIntent.getBroadcast(this, (startAlarmTime / 60000L).toInt(), startIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                VuorovahtiHelper.scheduleAlarmSafe(alarmManager, startAlarmTime, startPi)
            }
            val endAlarmTime = endMillis - (30 * 60 * 1000L)
            if (endAlarmTime > now) {
                val endIntent = Intent(this, ShiftAlarmReceiver::class.java).apply {
                    putExtra("SHIFT_TITLE", title); putExtra("SHIFT_TIME", endStr); putExtra("IS_ENDING", true)
                }
                val endPi = PendingIntent.getBroadcast(this, (endAlarmTime / 60000L).toInt() + 1, endIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                VuorovahtiHelper.scheduleAlarmSafe(alarmManager, endAlarmTime, endPi)
            }
        } catch (e: Exception) { e.printStackTrace() }
    }

    private fun saveWorkShift(calId: Long, dateStr: String, startStr: String, endStr: String, raw: String, fmt: DateTimeFormatter): Boolean {
        return try {
            val sDt = LocalDateTime.parse("$dateStr $startStr", fmt)
            var eDt = LocalDateTime.parse("$dateStr $endStr", fmt)
            if (eDt.isBefore(sDt)) eDt = eDt.plusDays(1)
            val sMs = sDt.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            val eMs = eDt.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            if (eMs < System.currentTimeMillis()) return false

            syncedShiftRangesInBatch.add(Pair(sMs, eMs))

            val (loc, desc) = extractLocAndDesc(startStr, raw)
            val dayStartMs = sDt.toLocalDate().atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli()
            val dayEndMs = sDt.toLocalDate().plusDays(1).atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli()
            val exId = findShiftOnSameDay(calId, sMs, eMs, dayStartMs, dayEndMs)

            if (exId == null) {
                insertEvent(calId, "Työvuoro", loc, desc, sMs, eMs, false, sDt.hour)
                true
            } else {
                updateEvent(exId, loc, desc, sMs, eMs, sDt.hour)
            }
        } catch (e: Exception) { false }
    }

    private fun findShiftOnSameDay(calId: Long, sMs: Long, eMs: Long, dayStartMs: Long, dayEndMs: Long): Long? {
        val exactSel = "${CalendarContract.Events.CALENDAR_ID} = ? AND ${CalendarContract.Events.DTSTART} = ? AND ${CalendarContract.Events.DTEND} = ? AND ${CalendarContract.Events.DELETED} = 0"
        contentResolver.query(CalendarContract.Events.CONTENT_URI, arrayOf(CalendarContract.Events._ID), exactSel, arrayOf(calId.toString(), sMs.toString(), eMs.toString()), null)?.use {
            if (it.moveToFirst()) return it.getLong(0)
        }
        val daySel = "${CalendarContract.Events.CALENDAR_ID} = ? AND ${CalendarContract.Events.TITLE} = ? AND ${CalendarContract.Events.DTSTART} >= ? AND ${CalendarContract.Events.DTSTART} < ? AND ${CalendarContract.Events.DELETED} = 0"
        contentResolver.query(CalendarContract.Events.CONTENT_URI, arrayOf(CalendarContract.Events._ID, CalendarContract.Events.DTSTART, CalendarContract.Events.DTEND), daySel, arrayOf(calId.toString(), "Työvuoro", dayStartMs.toString(), dayEndMs.toString()), null)?.use {
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

    private fun updateEvent(eventId: Long, loc: String, desc: String, sMs: Long, eMs: Long, startHour: Int): Boolean {
        var curLoc = ""
        var curDesc = ""
        var curStart = 0L
        var curEnd = 0L
        contentResolver.query(
            CalendarContract.Events.CONTENT_URI,
            arrayOf(CalendarContract.Events.EVENT_LOCATION, CalendarContract.Events.DESCRIPTION, CalendarContract.Events.DTSTART, CalendarContract.Events.DTEND),
            "${CalendarContract.Events._ID} = ?",
            arrayOf(eventId.toString()),
            null
        )?.use {
            if (it.moveToFirst()) {
                curLoc = it.getString(0) ?: ""
                curDesc = it.getString(1) ?: ""
                curStart = it.getLong(2)
                curEnd = it.getLong(3)
            }
        }
        val timeChanged = (curStart != sMs || curEnd != eMs)
        val textChanged = (loc.isNotEmpty() && (curLoc != loc || curDesc != desc))
        if (!timeChanged && !textChanged) return false

        val v = ContentValues().apply {
            put(CalendarContract.Events.DTSTART, sMs)
            put(CalendarContract.Events.DTEND, eMs)
            if (loc.isNotEmpty()) put(CalendarContract.Events.EVENT_LOCATION, loc)
            if (desc.isNotEmpty()) put(CalendarContract.Events.DESCRIPTION, desc)
            VuorovahtiHelper.applyShiftColor(this, desc.ifEmpty { "Työvuoro" }, startHour)
        }
        return try {
            contentResolver.update(CalendarContract.Events.CONTENT_URI, v, "${CalendarContract.Events._ID} = ?", arrayOf(eventId.toString())) > 0
        } catch (_: Exception) {
            v.remove(CalendarContract.Events.EVENT_COLOR)
            contentResolver.update(CalendarContract.Events.CONTENT_URI, v, "${CalendarContract.Events._ID} = ?", arrayOf(eventId.toString())) > 0
        }
    }

    private fun reconcileRemovedShifts(calId: Long): Int {
        if (syncedDatesInBatch.isEmpty()) return 0
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
            contentResolver.query(
                CalendarContract.Events.CONTENT_URI,
                arrayOf(CalendarContract.Events._ID, CalendarContract.Events.DTSTART, CalendarContract.Events.DTEND),
                sel,
                args,
                null
            )?.use { c ->
                while (c.moveToNext()) {
                    val id = c.getLong(0)
                    val sMs = c.getLong(1)
                    val eMs = c.getLong(2)
                    if (sMs > now && !syncedShiftRangesInBatch.contains(Pair(sMs, eMs))) {
                        idsToDelete.add(id)
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
        var silentPagesLeft = 0

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

        syncedDatesInBatch.clear()
        syncedShiftRangesInBatch.clear()
        totalFoundInBatch = 0
        totalAddedInBatch = 0
        totalRemovedInBatch = 0

        bgWeb.addJavascriptInterface(object {
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
                            bgWeb.evaluateJavascript("""
                                (function() {
                                    var el = document.querySelector('a[title*="Seuraava" i], button[title*="Seuraava" i], .fa-chevron-right, .fc-next-button');
                                    if (el) { (el.closest('a, button, div, span') || el).click(); return "NEXT"; }
                                    return "NONE";
                                })();
                            """.trimIndent()) { res ->
                                if (res?.contains("NEXT") == true) {
                                    bgWeb.postDelayed({
                                        bgWeb.evaluateJavascript("""
                                            AndroidSilentBridge.onSilentData("[]", document.body ? document.body.innerText : "", window.location.href);
                                        """.trimIndent(), null)
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
        }, "AndroidSilentBridge")

        bgWeb.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                val u = url ?: ""
                if (u.contains("/Calendar/", ignoreCase = true) && !u.contains("login", ignoreCase = true)) {
                    view?.postDelayed({
                        view.evaluateJavascript("""
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
                        """.trimIndent(), null)
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
        var startDate = days[0]; var endDate = days[0]
        for (i in 1 until days.size) {
            val current = days[i]
            val gapDays = ChronoUnit.DAYS.between(endDate, current)
            val isWeekendBridge = gapDays in 2..3 && (endDate.dayOfWeek == DayOfWeek.FRIDAY || endDate.dayOfWeek == DayOfWeek.SATURDAY) && current.dayOfWeek == DayOfWeek.MONDAY
            if (gapDays == 1L || isWeekendBridge) endDate = current
            else {
                if (saveCleanVacationPeriod(calId, startDate, endDate)) addedCount++
                startDate = current; endDate = current
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
            contentResolver.query(CalendarContract.Events.CONTENT_URI, arrayOf(CalendarContract.Events._ID, CalendarContract.Events.DTSTART, CalendarContract.Events.DTEND), sel, args, null)?.use { c ->
                while (c.moveToNext()) {
                    existingIds.add(c.getLong(0))
                    minStartMs = minOf(minStartMs, c.getLong(1))
                    maxEndMs = maxOf(maxEndMs, c.getLong(2))
                }
            }
            if (existingIds.size == 1) {
                val v = ContentValues().apply {
                    put(CalendarContract.Events.DTSTART, minStartMs); put(CalendarContract.Events.DTEND, maxEndMs)
                    put(CalendarContract.Events.ALL_DAY, 1); put(CalendarContract.Events.EVENT_TIMEZONE, "UTC")
                }
                contentResolver.update(CalendarContract.Events.CONTENT_URI, v, "${CalendarContract.Events._ID} = ?", arrayOf(existingIds[0].toString()))
                return true
            } else if (existingIds.size > 1) {
                for (id in existingIds) contentResolver.delete(CalendarContract.Events.CONTENT_URI, "${CalendarContract.Events._ID} = ?", arrayOf(id.toString()))
            }
            insertEvent(calId, "Loma", "", "Vuosiloma", minStartMs, maxEndMs, true, 0)
            true
        } catch (e: Exception) { false }
    }

    private fun getTargetOrPrimaryCalendarId(): Long? {
        val proj = arrayOf(CalendarContract.Calendars._ID)
        val preferredId = SettingsManager.getTargetCalendarId(this)
        if (preferredId != -1L) {
            contentResolver.query(CalendarContract.Calendars.CONTENT_URI, proj, "${CalendarContract.Calendars._ID} = ?", arrayOf(preferredId.toString()), null)?.use {
                if (it.moveToFirst()) return it.getLong(0)
            }
        }
        contentResolver.query(CalendarContract.Calendars.CONTENT_URI, proj, "${CalendarContract.Calendars.IS_PRIMARY} = 1", null, null)?.use { if (it.moveToFirst()) return it.getLong(0) }
        contentResolver.query(CalendarContract.Calendars.CONTENT_URI, proj, "${CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL} >= ${CalendarContract.Calendars.CAL_ACCESS_CONTRIBUTOR}", null, null)?.use { if (it.moveToFirst()) return it.getLong(0) }
        return null
    }

    private fun insertEvent(calId: Long, title: String, loc: String, desc: String, sMs: Long, eMs: Long, allDay: Boolean, startHour: Int = 8) {
        val v = ContentValues().apply {
            put(CalendarContract.Events.DTSTART, sMs); put(CalendarContract.Events.DTEND, eMs)
            put(CalendarContract.Events.TITLE, title); put(CalendarContract.Events.EVENT_LOCATION, loc)
            put(CalendarContract.Events.DESCRIPTION, desc); put(CalendarContract.Events.CALENDAR_ID, calId)
            put(CalendarContract.Events.ALL_DAY, if (allDay) 1 else 0)
            put(CalendarContract.Events.EVENT_TIMEZONE, if (allDay) "UTC" else ZoneId.systemDefault().id)
            VuorovahtiHelper.applyShiftColor(this, if (allDay) "Loma" else desc.ifEmpty { title }, startHour)
        }
        try {
            contentResolver.insert(CalendarContract.Events.CONTENT_URI, v)
        } catch (_: Exception) {
            v.remove(CalendarContract.Events.EVENT_COLOR)
            contentResolver.insert(CalendarContract.Events.CONTENT_URI, v)
        }
    }

    private fun checkAndRequestAllPermissions() {
        val neededPermissions = mutableListOf(
            Manifest.permission.READ_CALENDAR,
            Manifest.permission.WRITE_CALENDAR
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            neededPermissions.add(Manifest.permission.POST_NOTIFICATIONS)
        }

        val missing = neededPermissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 105)
        }
    }
}
