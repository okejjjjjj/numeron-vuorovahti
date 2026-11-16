#!/usr/bin/env python3
import os
import re

BASE_PKG_DIR = os.path.join("app", "src", "main", "java", "fi", "numeron", "vuorovahti")
RES_DIR = os.path.join("app", "src", "main", "res")

def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Päivitetty: {path}")

# 1. Custom-ilmoitusasettelut (vihreä & punainen toimintopainike leimausnotifikaatioon)
layout_notif_expanded = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:orientation="vertical"
    android:padding="12dp">

    <TextView
        android:id="@+id/notifTitle"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="Vuoro alkaa klo 07:00"
        android:textColor="#0F1722"
        android:textSize="15sp"
        android:textStyle="bold" />

    <TextView
        android:id="@+id/notifSubtitle"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:layout_marginTop="2dp"
        android:text="Aamuvuoro"
        android:textColor="#334155"
        android:textSize="13sp" />

    <TextView
        android:id="@+id/btnNotifStamp"
        android:layout_width="match_parent"
        android:layout_height="40dp"
        android:layout_marginTop="10dp"
        android:background="@drawable/bg_notif_btn_in"
        android:clickable="true"
        android:focusable="true"
        android:gravity="center"
        android:text="LEIMAA SISÄÄN"
        android:textColor="#FFFFFF"
        android:textSize="14sp"
        android:textStyle="bold" />
</LinearLayout>
"""

layout_notif_collapsed = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:gravity="center_vertical"
    android:orientation="horizontal"
    android:padding="10dp">

    <LinearLayout
        android:layout_width="0dp"
        android:layout_height="wrap_content"
        android:layout_weight="1"
        android:orientation="vertical"
        android:paddingEnd="8dp">

        <TextView
            android:id="@+id/notifTitleCollapsed"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:ellipsize="end"
            android:maxLines="1"
            android:text="Vuoro alkaa klo 07:00"
            android:textColor="#0F1722"
            android:textSize="14sp"
            android:textStyle="bold" />

        <TextView
            android:id="@+id/notifSubtitleCollapsed"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:ellipsize="end"
            android:maxLines="1"
            android:text="Aamuvuoro"
            android:textColor="#334155"
            android:textSize="12sp" />
    </LinearLayout>

    <TextView
        android:id="@+id/btnNotifStampCollapsed"
        android:layout_width="wrap_content"
        android:layout_height="34dp"
        android:background="@drawable/bg_notif_btn_in"
        android:clickable="true"
        android:focusable="true"
        android:gravity="center"
        android:paddingStart="14dp"
        android:paddingEnd="14dp"
        android:text="SISÄÄN"
        android:textColor="#FFFFFF"
        android:textSize="12sp"
        android:textStyle="bold" />
</LinearLayout>
"""

bg_btn_in = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">
    <solid android:color="#16A34A" />
    <corners android:radius="8dp" />
</shape>
"""

bg_btn_out = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">
    <solid android:color="#DC2626" />
    <corners android:radius="8dp" />
</shape>
"""

write_file(os.path.join(RES_DIR, "layout", "notification_stamp_expanded.xml"), layout_notif_expanded)
write_file(os.path.join(RES_DIR, "layout", "notification_stamp_collapsed.xml"), layout_notif_collapsed)
write_file(os.path.join(RES_DIR, "drawable", "bg_notif_btn_in.xml"), bg_btn_in)
write_file(os.path.join(RES_DIR, "drawable", "bg_notif_btn_out.xml"), bg_btn_out)

# 2. Päivitetään CalendarSyncHelper.kt
cal_sync_path = os.path.join(BASE_PKG_DIR, "CalendarSyncHelper.kt")
with open(cal_sync_path, "r", encoding="utf-8") as f:
    cal_sync = f.read()

old_sync_return = """        if (detectedChanges.isNotEmpty()) {
            CalendarChangeTracker.saveChanges(context, detectedChanges)
            ShiftReminderReceiver.showCalendarChangesNotification(context, detectedChanges)
        }

        return detectedChanges"""

new_sync_return = """        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putLong("last_calendar_sync_ms", System.currentTimeMillis())
            .apply()

        if (detectedChanges.isNotEmpty()) {
            CalendarChangeTracker.saveChanges(context, detectedChanges)
            ShiftReminderReceiver.showCalendarChangesNotification(context, detectedChanges)
        }

        return detectedChanges"""

if old_sync_return not in cal_sync:
    raise RuntimeError("CalendarSyncHelper.kt: syncShiftsToCalendar-lopetuskohtaa ei löytynyt.")
cal_sync = cal_sync.replace(old_sync_return, new_sync_return, 1)

old_sched_block = """        val sortedShifts = userShifts.sortedBy { it.startMs }
        val maxGapMs = 15L * 60_000L

        for (i in sortedShifts.indices) {
            val current = sortedShifts[i]
            val prev = if (i > 0) sortedShifts[i - 1] else null
            val next = if (i < sortedShifts.lastIndex) sortedShifts[i + 1] else null

            val continuesFromPrev = prev != null && (current.startMs - prev.endMs) in (-maxGapMs)..maxGapMs
            val continuesToNext = next != null && (next.startMs - current.endMs) in (-maxGapMs)..maxGapMs

            if (!continuesFromPrev) {
                val startTrigger = current.startMs - (minutesBefore * 60_000L)
                if (startTrigger > now) {
                    val startStr = Instant.ofEpochMilli(current.startMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                    setExactAlarmSafe(context, alarmManager, startTrigger, current.displayTitle, startStr, isEnding = false)
                }
            }

            if (!continuesToNext) {
                val endTrigger = current.endMs - (minutesBefore * 60_000L)
                if (endTrigger > now) {
                    val endStr = Instant.ofEpochMilli(current.endMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                    setExactAlarmSafe(context, alarmManager, endTrigger, current.displayTitle, endStr, isEnding = true)
                }
            }
        }"""

new_sched_block = """        val sortedShifts = userShifts.sortedBy { it.startMs }
        val maxGapMs = 15L * 60_000L
        var earliestNextTriggerMs = Long.MAX_VALUE
        var earliestNextLabel = ""

        for (i in sortedShifts.indices) {
            val current = sortedShifts[i]
            val prev = if (i > 0) sortedShifts[i - 1] else null
            val next = if (i < sortedShifts.lastIndex) sortedShifts[i + 1] else null

            val continuesFromPrev = prev != null && (current.startMs - prev.endMs) in (-maxGapMs)..maxGapMs
            val continuesToNext = next != null && (next.startMs - current.endMs) in (-maxGapMs)..maxGapMs

            if (!continuesFromPrev) {
                val startTrigger = current.startMs - (minutesBefore * 60_000L)
                if (startTrigger > now) {
                    val startStr = Instant.ofEpochMilli(current.startMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                    setExactAlarmSafe(context, alarmManager, startTrigger, current.displayTitle, startStr, isEnding = false)
                    if (startTrigger < earliestNextTriggerMs) {
                        earliestNextTriggerMs = startTrigger
                        earliestNextLabel = "Sisään (${current.displayTitle}, vuoro klo $startStr)"
                    }
                }
            }

            if (!continuesToNext) {
                val endTrigger = current.endMs - (minutesBefore * 60_000L)
                if (endTrigger > now) {
                    val endStr = Instant.ofEpochMilli(current.endMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                    setExactAlarmSafe(context, alarmManager, endTrigger, current.displayTitle, endStr, isEnding = true)
                    if (endTrigger < earliestNextTriggerMs) {
                        earliestNextTriggerMs = endTrigger
                        earliestNextLabel = "Ulos (${current.displayTitle}, päättyy klo $endStr)"
                    }
                }
            }
        }

        prefs.edit().apply {
            if (earliestNextTriggerMs < Long.MAX_VALUE) {
                putLong("next_reminder_ms", earliestNextTriggerMs)
                putString("next_reminder_label", earliestNextLabel)
            } else {
                remove("next_reminder_ms")
                remove("next_reminder_label")
            }
        }.apply()"""

if old_sched_block not in cal_sync:
    raise RuntimeError("CalendarSyncHelper.kt: scheduleShiftReminders-silmukkaa ei löytynyt.")
cal_sync = cal_sync.replace(old_sched_block, new_sched_block, 1)
write_file(cal_sync_path, cal_sync)

# 3. Päivitetään ShiftReminderReceiver.kt
shift_recv_path = os.path.join(BASE_PKG_DIR, "ShiftReminderReceiver.kt")
with open(shift_recv_path, "r", encoding="utf-8") as f:
    shift_recv = f.read()

if "import android.widget.RemoteViews" not in shift_recv:
    shift_recv = shift_recv.replace("import android.widget.Toast\n", "import android.widget.RemoteViews\nimport android.widget.Toast\n", 1)

old_show_notif = re.search(
    r"    fun showReminderNotification\(.*?\n    \}\n",
    shift_recv,
    flags=re.DOTALL,
)
if not old_show_notif:
    raise RuntimeError("ShiftReminderReceiver.kt: showReminderNotification-metodia ei löytynyt.")

new_show_notif = """    fun showReminderNotification(
        context: Context,
        shiftTitle: String,
        timeStr: String,
        isEnding: Boolean,
        isTest: Boolean = false
    ) {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channelId = "numeron_vuorovahti_reminders"

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "Työvuoro- ja kalenteri-ilmoitukset",
                NotificationManager.IMPORTANCE_HIGH
            )
            nm.createNotificationChannel(channel)
        }

        val notifId = if (isEnding) 2002 else 1001
        val fullButtonLabel = if (isEnding) "LEIMAA ULOS" else "LEIMAA SISÄÄN"
        val shortButtonLabel = if (isEnding) "ULOS" else "SISÄÄN"
        val contentTitle = if (isEnding) "Vuoro päättyy klo $timeStr" else "Vuoro alkaa klo $timeStr"
        val btnBgRes = if (isEnding) R.drawable.bg_notif_btn_out else R.drawable.bg_notif_btn_in

        val dirTag = if (isEnding) "Ulos" else "Sisään"
        val testSuffix = if (isTest) " [Testi]" else ""
        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putLong("last_reminder_sent_ms", System.currentTimeMillis())
            .putString("last_reminder_sent_label", "$dirTag – $shiftTitle$testSuffix")
            .apply()

        if (!isTest) {
            CalendarSyncHelper.getTargetCalendarId(context)?.let { calId ->
                CalendarSyncHelper.scheduleShiftReminders(context, calId)
            }
        }

        val stampIntent = Intent(context, ShiftReminderReceiver::class.java).apply {
            action = ACTION_QUICK_STAMP
            putExtra("IS_ENDING", isEnding)
            putExtra("IS_TEST", isTest)
            putExtra("NOTIF_ID", notifId)
        }
        val stampPi = PendingIntent.getBroadcast(
            context,
            notifId,
            stampIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val openAppIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val openAppPi = PendingIntent.getActivity(
            context,
            notifId + 10,
            openAppIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val collapsedView = RemoteViews(context.packageName, R.layout.notification_stamp_collapsed).apply {
            setTextViewText(R.id.notifTitleCollapsed, contentTitle)
            setTextViewText(R.id.notifSubtitleCollapsed, shiftTitle)
            setTextViewText(R.id.btnNotifStampCollapsed, shortButtonLabel)
            setInt(R.id.btnNotifStampCollapsed, "setBackgroundResource", btnBgRes)
            setOnClickPendingIntent(R.id.btnNotifStampCollapsed, stampPi)
        }

        val expandedView = RemoteViews(context.packageName, R.layout.notification_stamp_expanded).apply {
            setTextViewText(R.id.notifTitle, contentTitle)
            setTextViewText(R.id.notifSubtitle, shiftTitle)
            setTextViewText(R.id.btnNotifStamp, fullButtonLabel)
            setInt(R.id.btnNotifStamp, "setBackgroundResource", btnBgRes)
            setOnClickPendingIntent(R.id.btnNotifStamp, stampPi)
        }

        val notification = NotificationCompat.Builder(context, channelId)
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle(contentTitle)
            .setContentText(shiftTitle)
            .setStyle(NotificationCompat.DecoratedCustomViewStyle())
            .setCustomContentView(collapsedView)
            .setCustomBigContentView(expandedView)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(openAppPi)
            .build()

        nm.notify(notifId, notification)
    }
"""

shift_recv = shift_recv[:old_show_notif.start()] + new_show_notif + shift_recv[old_show_notif.end():]

old_bg_sched = """            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                "NumeronVuorovahtiSync",
                ExistingPeriodicWorkPolicy.KEEP,
                syncRequest
            )"""

new_bg_sched = """            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                "NumeronVuorovahtiSync",
                ExistingPeriodicWorkPolicy.KEEP,
                syncRequest
            )
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            if (prefs.getLong("next_calendar_sync_ms", 0L) <= System.currentTimeMillis()) {
                prefs.edit()
                    .putLong("next_calendar_sync_ms", System.currentTimeMillis() + TimeUnit.HOURS.toMillis(12))
                    .apply()
            }"""

if old_bg_sched not in shift_recv:
    raise RuntimeError("ShiftReminderReceiver.kt: ensureBackgroundSyncScheduled-lohkoa ei löytynyt.")
shift_recv = shift_recv.replace(old_bg_sched, new_bg_sched, 1)

old_worker_succ = """            CalendarSyncHelper.scheduleShiftReminders(appContext, calId)
            Result.success()"""

new_worker_succ = """            CalendarSyncHelper.scheduleShiftReminders(appContext, calId)
            prefs.edit()
                .putLong("next_calendar_sync_ms", System.currentTimeMillis() + TimeUnit.HOURS.toMillis(12))
                .apply()
            Result.success()"""

if old_worker_succ not in shift_recv:
    raise RuntimeError("ShiftReminderReceiver.kt: BackgroundSyncWorker Result.success()-kohtaa ei löytynyt.")
shift_recv = shift_recv.replace(old_worker_succ, new_worker_succ, 1)
write_file(shift_recv_path, shift_recv)

# 4. Päivitetään SettingsDialogHelper.kt
settings_helper_code = r"""package fi.numeron.vuorovahti

import android.Manifest
import android.app.AlertDialog
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.provider.CalendarContract
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.ContextCompat
import androidx.work.WorkManager
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

data class CalendarOption(
    val id: Long,
    val name: String,
    val accountName: String,
    val accountType: String
) {
    override fun toString(): String {
        val typeTag = if (accountType == "com.google") "Google" else "Paikallinen"
        return "$name ($accountName) [$typeTag]"
    }
}

data class ShiftColorChoice(
    val name: String,
    val rgb: Int
) {
    override fun toString(): String = name
}

object SettingsDialogHelper {

    val SHIFT_COLOR_CHOICES = listOf(
        ShiftColorChoice("Basilika (Vihreä)", Color.rgb(11, 128, 67)),
        ShiftColorChoice("Salvia (Vaaleanvihreä)", Color.rgb(51, 182, 121)),
        ShiftColorChoice("Mandariini (Oranssi)", Color.rgb(244, 81, 30)),
        ShiftColorChoice("Banaani (Keltainen)", Color.rgb(246, 191, 38)),
        ShiftColorChoice("Viinirypäle (Lila)", Color.rgb(142, 36, 170)),
        ShiftColorChoice("Mustikka (Sininen)", Color.rgb(63, 81, 181)),
        ShiftColorChoice("Riikinkukko (Turkoosi)", Color.rgb(3, 155, 229)),
        ShiftColorChoice("Flamingo (Vaaleanpunainen)", Color.rgb(230, 124, 115)),
        ShiftColorChoice("Tomaatti (Punainen)", Color.rgb(213, 0, 0)),
        ShiftColorChoice("Grafiitti (Harmaa)", Color.rgb(97, 97, 97))
    )

    val DEFAULT_MORNING_RGB = Color.rgb(11, 128, 67)
    val DEFAULT_EVENING_RGB = Color.rgb(244, 81, 30)
    val DEFAULT_NIGHT_RGB = Color.rgb(142, 36, 170)

    fun getAvailableCalendars(context: Context): List<CalendarOption> {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return emptyList()
        }
        val list = mutableListOf<CalendarOption>()
        val projection = arrayOf(
            CalendarContract.Calendars._ID,
            CalendarContract.Calendars.CALENDAR_DISPLAY_NAME,
            CalendarContract.Calendars.ACCOUNT_NAME,
            CalendarContract.Calendars.ACCOUNT_TYPE,
            CalendarContract.Calendars.IS_PRIMARY
        )
        val selection = "${CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL} >= ? AND ${CalendarContract.Calendars.VISIBLE} = 1"
        val selectionArgs = arrayOf(CalendarContract.Calendars.CAL_ACCESS_CONTRIBUTOR.toString())

        context.contentResolver.query(
            CalendarContract.Calendars.CONTENT_URI,
            projection,
            selection,
            selectionArgs,
            null
        )?.use { cursor ->
            while (cursor.moveToNext()) {
                val id = cursor.getLong(0)
                val name = cursor.getString(1) ?: "Kalenteri"
                val account = cursor.getString(2) ?: ""
                val accountType = cursor.getString(3) ?: ""
                val isPrimary = cursor.getInt(4) == 1
                list.add(CalendarOption(id, name, account, accountType))
                if (accountType == "com.google" && (isPrimary || name.equals(account, ignoreCase = true))) {
                    val item = list.removeAt(list.lastIndex)
                    list.add(0, item)
                }
            }
        }
        return list.sortedBy { if (it.accountType == "com.google") 0 else 1 }
    }

    private fun formatTimestamp(ms: Long, fallback: String): String {
        if (ms <= 0L) return fallback
        val fmt = DateTimeFormatter.ofPattern("dd.MM.yyyy 'klo' HH:mm")
        return Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).format(fmt)
    }

    private fun resolveNextSyncMs(context: Context, fallbackSavedMs: Long): Long {
        try {
            val infos = WorkManager.getInstance(context)
                .getWorkInfosForUniqueWork("NumeronVuorovahtiSync")
                .get()
            val nextRun = infos.firstOrNull { !it.state.isFinished }?.nextScheduleTimeMillis ?: 0L
            if (nextRun > System.currentTimeMillis() && nextRun < Long.MAX_VALUE) {
                return nextRun
            }
        } catch (_: Exception) {
        }
        return fallbackSavedMs
    }

    fun showSettingsDialog(
        context: Context,
        onManualSync: () -> Unit,
        onManageChanges: () -> Unit,
        onTestNotification: () -> Unit,
        onSaved: () -> Unit
    ) {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val density = context.resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()

        fun makeCardBg(fillHex: String = "#182332", strokeHex: String = "#2A394A", radiusDp: Int = 12): GradientDrawable {
            return GradientDrawable().apply {
                setColor(Color.parseColor(fillHex))
                setStroke(dp(1), Color.parseColor(strokeHex))
                cornerRadius = dp(radiusDp).toFloat()
            }
        }

        val rootContainer = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#0F1722"))
        }

        val headerBar = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(20), dp(18), dp(20), dp(14))
        }
        headerBar.addView(TextView(context).apply {
            text = "Vuorovahti – Asetukset"
            textSize = 19f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#F1F5F9"))
        })
        headerBar.addView(TextView(context).apply {
            text = "Tunnukset, kalenterisynkronointi ja ilmoitukset"
            textSize = 12f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, dp(2), 0, 0)
        })
        rootContainer.addView(headerBar)

        val divider = View(context).apply {
            setBackgroundColor(Color.parseColor("#2A394A"))
        }
        rootContainer.addView(divider, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)))

        val scrollView = ScrollView(context).apply {
            isFillViewport = true
        }
        val layout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(14), dp(16), dp(16))
        }
        scrollView.addView(layout)
        rootContainer.addView(scrollView, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))

        fun createSectionCard(title: String): LinearLayout {
            val card = LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                background = makeCardBg("#182332", "#2A394A", 12)
                setPadding(dp(16), dp(14), dp(16), dp(16))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    bottomMargin = dp(14)
                }
            }
            val sectionHeader = TextView(context).apply {
                text = title.uppercase()
                textSize = 11f
                letterSpacing = 0.06f
                setTypeface(null, Typeface.BOLD)
                setTextColor(Color.parseColor("#38BDF8"))
                setPadding(0, 0, 0, dp(8))
            }
            card.addView(sectionHeader)
            layout.addView(card)
            return card
        }

        fun createLabel(text: String): TextView = TextView(context).apply {
            this.text = text
            textSize = 13f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, dp(10), 0, dp(5))
        }

        fun styleEditText(et: EditText) {
            et.background = makeCardBg("#111923", "#37475A", 8)
            et.setTextColor(Color.parseColor("#F1F5F9"))
            et.setHintTextColor(Color.parseColor("#64748B"))
            et.setPadding(dp(12), dp(10), dp(12), dp(10))
            et.textSize = 14f
        }

        fun styleButton(btn: Button, bgHex: String = "#233040", strokeHex: String = "#37475A", textHex: String = "#F1F5F9") {
            btn.background = makeCardBg(bgHex, strokeHex, 8)
            btn.setTextColor(Color.parseColor(textHex))
            btn.isAllCaps = false
            btn.textSize = 14f
            btn.setTypeface(null, Typeface.BOLD)
            btn.setPadding(dp(14), dp(11), dp(14), dp(11))
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                topMargin = dp(10)
            }
            btn.layoutParams = lp
        }

        fun styleSpinner(spinner: Spinner) {
            spinner.background = makeCardBg("#111923", "#37475A", 8)
            spinner.setPadding(dp(8), dp(6), dp(8), dp(6))
        }

        fun createDarkAdapter(items: List<Any>): ArrayAdapter<Any> {
            return object : ArrayAdapter<Any>(context, android.R.layout.simple_spinner_item, items) {
                override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
                    val tv = super.getView(position, convertView, parent) as TextView
                    tv.setTextColor(Color.parseColor("#F1F5F9"))
                    tv.textSize = 14f
                    return tv
                }

                override fun getDropDownView(position: Int, convertView: View?, parent: ViewGroup): View {
                    val tv = super.getDropDownView(position, convertView, parent) as TextView
                    tv.setBackgroundColor(Color.parseColor("#1E293B"))
                    tv.setTextColor(Color.parseColor("#F1F5F9"))
                    tv.setPadding(dp(14), dp(12), dp(14), dp(12))
                    tv.textSize = 14f
                    return tv
                }
            }
        }

        // === KORTTI 1: TILA JA AIKATAULUT ===
        val statusCard = createSectionCard("Tila ja aikataulut")

        val lastSyncMs = prefs.getLong("last_calendar_sync_ms", 0L)
        val nextSyncMs = resolveNextSyncMs(context, prefs.getLong("next_calendar_sync_ms", 0L))
        val lastNotifMs = prefs.getLong("last_reminder_sent_ms", 0L)
        val lastNotifLabel = prefs.getString("last_reminder_sent_label", "") ?: ""
        val nextNotifMs = prefs.getLong("next_reminder_ms", 0L)
        val nextNotifLabel = prefs.getString("next_reminder_label", "") ?: ""

        fun addStatusRow(parent: LinearLayout, title: String, value: String, subValue: String? = null) {
            val box = LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                background = makeCardBg("#111923", "#233040", 8)
                setPadding(dp(12), dp(9), dp(12), dp(9))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    bottomMargin = dp(8)
                }
            }
            box.addView(TextView(context).apply {
                text = title
                textSize = 11f
                setTextColor(Color.parseColor("#94A3B8"))
            })
            box.addView(TextView(context).apply {
                text = value
                textSize = 14f
                setTypeface(null, Typeface.BOLD)
                setTextColor(Color.parseColor("#F1F5F9"))
                setPadding(0, dp(2), 0, 0)
            })
            if (!subValue.isNullOrEmpty()) {
                box.addView(TextView(context).apply {
                    text = subValue
                    textSize = 12f
                    setTextColor(Color.parseColor("#38BDF8"))
                    setPadding(0, dp(2), 0, 0)
                })
            }
            parent.addView(box)
        }

        addStatusRow(
            statusCard,
            "Kalenterimerkinnät tarkistettu edellisen kerran",
            formatTimestamp(lastSyncMs, "Ei vielä tarkistettu")
        )
        addStatusRow(
            statusCard,
            "Seuraava kalenteritarkistus ajoitettu",
            formatTimestamp(nextSyncMs, "Automaattinen tarkistus (12 h välein)")
        )
        addStatusRow(
            statusCard,
            "Edellinen leimausnotifikaatio lähetetty",
            formatTimestamp(lastNotifMs, "Ei vielä lähetetty"),
            if (lastNotifMs > 0L) lastNotifLabel else null
        )
        addStatusRow(
            statusCard,
            "Seuraava leimausnotifikaatio lähetetään",
            if (nextNotifMs > System.currentTimeMillis()) formatTimestamp(nextNotifMs, "") else "Ei tulevia ajoitettuja hälytyksiä",
            if (nextNotifMs > System.currentTimeMillis()) nextNotifLabel else null
        )

        // === KORTTI 2: KIRJAUTUMINEN JA YHTEYS ===
        val authCard = createSectionCard("Kirjautuminen ja yhteys")

        authCard.addView(createLabel("Organisaatiotunnus (esim. siunsote)"))
        val editOrg = EditText(context).apply {
            hint = "siunsote"
            setText(prefs.getString("org_raw_input", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            isSingleLine = true
            styleEditText(this)
        }
        authCard.addView(editOrg)

        authCard.addView(createLabel("Käyttäjätunnus"))
        val editUser = EditText(context).apply {
            hint = "Käyttäjätunnus"
            setText(prefs.getString("username", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            isSingleLine = true
            styleEditText(this)
        }
        authCard.addView(editUser)

        authCard.addView(createLabel("Salasana"))
        val editPass = EditText(context).apply {
            hint = "Salasana"
            setText(prefs.getString("password", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            isSingleLine = true
            styleEditText(this)
        }
        authCard.addView(editPass)

        val tvTestStatus = TextView(context).apply {
            text = ""
            textSize = 13f
            setPadding(0, dp(8), 0, dp(2))
        }

        val btnTestCredentials = Button(context).apply {
            text = "Testaa yhteys ja tunnukset"
            styleButton(this, "#1E3A5F", "#0284C7", "#E0F2FE")
            setOnClickListener {
                val normalizedUrl = UrlNormalizer.normalizeOrgUrl(editOrg.text.toString())
                val user = editUser.text.toString().trim()
                val pass = editPass.text.toString()

                if (normalizedUrl.isEmpty()) {
                    tvTestStatus.setTextColor(Color.parseColor("#EF4444"))
                    tvTestStatus.text = "Virhe: Syötä organisaatiotunnus."
                    return@setOnClickListener
                }
                if (user.isEmpty() || pass.isEmpty()) {
                    tvTestStatus.setTextColor(Color.parseColor("#EF4444"))
                    tvTestStatus.text = "Virhe: Syötä käyttäjätunnus ja salasana."
                    return@setOnClickListener
                }
                if (DemoModeHelper.isDemoCredentials(editOrg.text.toString(), user, pass)) {
                    tvTestStatus.setTextColor(Color.parseColor("#10B981"))
                    tvTestStatus.text = "Demotila tunnistettu! Tallenna asetukset ottaaksesi demotilan käyttöön."
                    return@setOnClickListener
                }

                isEnabled = false
                tvTestStatus.setTextColor(Color.parseColor("#38BDF8"))
                tvTestStatus.text = "Testataan osoitetta $normalizedUrl..."

                testLoginWithHiddenWebView(context, normalizedUrl, user, pass) { success, message ->
                    isEnabled = true
                    tvTestStatus.setTextColor(
                        if (success) Color.parseColor("#10B981") else Color.parseColor("#EF4444")
                    )
                    tvTestStatus.text = message
                }
            }
        }
        authCard.addView(btnTestCredentials)
        authCard.addView(tvTestStatus)

        // === KORTTI 3: KALENTERI JA VÄRIKOODIT ===
        val calCard = createSectionCard("Kalenteri ja värikoodit")

        calCard.addView(createLabel("Kohdekalenteri"))
        val calendars = getAvailableCalendars(context)
        val spinnerCalendar = Spinner(context).apply { styleSpinner(this) }
        if (calendars.isNotEmpty()) {
            spinnerCalendar.adapter = createDarkAdapter(calendars)
            val savedCalId = prefs.getLong("calendar_id", -1L)
            val idx = calendars.indexOfFirst { it.id == savedCalId }
            spinnerCalendar.setSelection(if (idx >= 0) idx else 0)
        }
        calCard.addView(spinnerCalendar)

        calCard.addView(createLabel("Henkilötunniste yhteiskalenteriin (valinnainen, esim. Jukka)"))
        val editUserTag = EditText(context).apply {
            hint = "Jätä tyhjäksi omassa kalenterissa"
            setText(prefs.getString("calendar_user_tag", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_WORDS
            isSingleLine = true
            styleEditText(this)
        }
        calCard.addView(editUserTag)

        fun createColorSpinner(savedRgb: Int): Spinner {
            val spinner = Spinner(context).apply { styleSpinner(this) }
            spinner.adapter = createDarkAdapter(SHIFT_COLOR_CHOICES)
            val idx = SHIFT_COLOR_CHOICES.indexOfFirst { it.rgb == savedRgb }
            if (idx >= 0) spinner.setSelection(idx)
            return spinner
        }

        calCard.addView(createLabel("Aamuvuoron väri"))
        val spinnerMorningColor = createColorSpinner(prefs.getInt("color_morning_rgb", DEFAULT_MORNING_RGB))
        calCard.addView(spinnerMorningColor)

        calCard.addView(createLabel("Iltavuoron väri"))
        val spinnerEveningColor = createColorSpinner(prefs.getInt("color_evening_rgb", DEFAULT_EVENING_RGB))
        calCard.addView(spinnerEveningColor)

        calCard.addView(createLabel("Yövuoron väri"))
        val spinnerNightColor = createColorSpinner(prefs.getInt("color_night_rgb", DEFAULT_NIGHT_RGB))
        calCard.addView(spinnerNightColor)

        // === KORTTI 4: MUISTUTUKSET JA TOIMINNOT ===
        val actionCard = createSectionCard("Muistutukset ja toiminnot")

        actionCard.addView(createLabel("Muistutus ennen vuoroa (min)"))
        val editReminder = EditText(context).apply {
            setText(prefs.getInt("reminder_minutes", 30).toString())
            inputType = InputType.TYPE_CLASS_NUMBER
            isSingleLine = true
            styleEditText(this)
        }
        actionCard.addView(editReminder)

        val btnSync = Button(context).apply {
            text = "Synkronoi työvuorot kalenteriin nyt"
            styleButton(this, "#1982C4", "#38BDF8", "#FFFFFF")
        }
        actionCard.addView(btnSync)

        val btnChanges = Button(context).apply {
            text = "Hallitse kalenterimuutoksia"
            styleButton(this, "#233040", "#37475A", "#F1F5F9")
        }
        actionCard.addView(btnChanges)

        val btnTestNotif = Button(context).apply {
            text = "Lähetä testi-ilmoitus"
            styleButton(this, "#233040", "#37475A", "#F1F5F9")
        }
        actionCard.addView(btnTestNotif)

        // Alapalkki: Peruuta ja Tallenna
        val bottomDivider = View(context).apply {
            setBackgroundColor(Color.parseColor("#2A394A"))
        }
        rootContainer.addView(bottomDivider, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)))

        val footerBar = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(16), dp(12), dp(16), dp(12))
        }

        val btnCancel = Button(context).apply {
            text = "Peruuta"
            background = makeCardBg("#233040", "#37475A", 8)
            setTextColor(Color.parseColor("#CBD5E1"))
            isAllCaps = false
            textSize = 14f
            setPadding(dp(18), dp(10), dp(18), dp(10))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                marginEnd = dp(10)
            }
        }

        val btnSave = Button(context).apply {
            text = "Tallenna"
            background = makeCardBg("#1982C4", "#38BDF8", 8)
            setTextColor(Color.parseColor("#FFFFFF"))
            isAllCaps = false
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            setPadding(dp(22), dp(10), dp(22), dp(10))
        }

        footerBar.addView(btnCancel)
        footerBar.addView(btnSave)
        rootContainer.addView(footerBar)

        val dialog = AlertDialog.Builder(context)
            .setView(rootContainer)
            .create()

        dialog.window?.setBackgroundDrawable(makeCardBg("#0F1722", "#2A394A", 14))

        btnSync.setOnClickListener {
            dialog.dismiss()
            onManualSync()
        }

        btnChanges.setOnClickListener {
            dialog.dismiss()
            onManageChanges()
        }

        btnTestNotif.setOnClickListener {
            onTestNotification()
        }

        btnCancel.setOnClickListener {
            dialog.dismiss()
        }

        btnSave.setOnClickListener {
            val rawOrg = editOrg.text.toString().trim()
            val normalizedUrl = UrlNormalizer.normalizeOrgUrl(rawOrg)
            val selectedCal = spinnerCalendar.selectedItem as? CalendarOption
            val userTag = editUserTag.text.toString().trim()
            val reminderMins = editReminder.text.toString().toIntOrNull() ?: 30

            val morningRgb = (spinnerMorningColor.selectedItem as? ShiftColorChoice)?.rgb ?: DEFAULT_MORNING_RGB
            val eveningRgb = (spinnerEveningColor.selectedItem as? ShiftColorChoice)?.rgb ?: DEFAULT_EVENING_RGB
            val nightRgb = (spinnerNightColor.selectedItem as? ShiftColorChoice)?.rgb ?: DEFAULT_NIGHT_RGB

            val savedUser = editUser.text.toString().trim()
            val savedPass = editPass.text.toString()
            val isDemo = savedUser.isEmpty() || savedPass.isEmpty() || rawOrg.isEmpty() ||
                DemoModeHelper.isDemoCredentials(rawOrg, savedUser, savedPass)

            prefs.edit()
                .putString("org_raw_input", rawOrg)
                .putString("server_url", normalizedUrl)
                .putString("username", savedUser)
                .putString("password", savedPass)
                .putBoolean("demo_mode", isDemo)
                .putString("calendar_user_tag", userTag)
                .putInt("reminder_minutes", reminderMins)
                .putInt("color_morning_rgb", morningRgb)
                .putInt("color_evening_rgb", eveningRgb)
                .putInt("color_night_rgb", nightRgb)
                .apply {
                    if (selectedCal != null) putLong("calendar_id", selectedCal.id)
                }
                .apply()

            val statusMsg = if (isDemo) "Demotila aktiivinen" else "Tallennettu ($normalizedUrl)"
            Toast.makeText(context, statusMsg, Toast.LENGTH_SHORT).show()
            dialog.dismiss()
            onSaved()
        }

        dialog.show()
    }

    private fun testLoginWithHiddenWebView(
        context: Context,
        baseUrl: String,
        username: String,
        password: String,
        callback: (Boolean, String) -> Unit
    ) {
        val testWebView = WebView(context).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
        }

        CookieManager.getInstance().removeAllCookies(null)

        var loginAttempted = false
        var finished = false

        fun cleanupAndRespond(success: Boolean, msg: String) {
            if (finished) return
            finished = true
            testWebView.stopLoading()
            testWebView.destroy()
            callback(success, msg)
        }

        testWebView.webViewClient = object : WebViewClient() {
            override fun onReceivedError(
                view: WebView?,
                errorCode: Int,
                description: String?,
                failingUrl: String?
            ) {
                cleanupAndRespond(
                    false,
                    "Yhteysvirhe: Organisaatiota '$baseUrl' ei löytynyt tai verkkoyhteys puuttuu."
                )
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                if (url == null || finished) return

                if (url.contains("/Login/Login", ignoreCase = true)) {
                    if (!loginAttempted) {
                        loginAttempted = true
                        val safeUser = username.replace("\\", "\\\\").replace("'", "\\'")
                        val safePass = password.replace("\\", "\\\\").replace("'", "\\'")
                        val js = [[TQ]]
                            (function() {
                                var u = document.getElementById('Username');
                                var p = document.getElementById('Password');
                                var f = document.getElementById('LoginForm');
                                if (u && p && f) {
                                    u.value = '$safeUser';
                                    p.value = '$safePass';
                                    f.submit();
                                    return 'SUBMITTED';
                                }
                                return 'NO_FORM';
                            })();
                        [[TQ]].trimIndent()
                        view?.evaluateJavascript(js) { res ->
                            if (res?.contains("NO_FORM") == true) {
                                cleanupAndRespond(false, "Virhe: Kirjautumislomaketta ei tunnistettu sivulta.")
                            }
                        }
                    } else {
                        val errJs = [[TQ]]
                            (function() {
                                var err = document.querySelector('.validation-summary-errors, .alert-danger');
                                return err ? err.innerText.trim() : '';
                            })();
                        [[TQ]].trimIndent()
                        view?.evaluateJavascript(errJs) { errText ->
                            val cleanErr = errText?.replace("\"", "")?.trim() ?: ""
                            if (cleanErr.isNotEmpty()) {
                                cleanupAndRespond(false, "Kirjautuminen epäonnistui: $cleanErr")
                            } else {
                                cleanupAndRespond(false, "Virheellinen käyttäjätunnus tai salasana.")
                            }
                        }
                    }
                } else if (
                    url.contains("/WorktimeStamping", ignoreCase = true) ||
                    url.contains("/InfraDashboard", ignoreCase = true) ||
                    url.contains("/Calendar", ignoreCase = true)
                ) {
                    cleanupAndRespond(true, "Yhteys ja tunnukset toimivat! ($baseUrl)")
                }
            }
        }

        testWebView.loadUrl("$baseUrl/Login/Login")
    }
}
""".replace("[[TQ]]", '"""')

write_file(os.path.join(BASE_PKG_DIR, "SettingsDialogHelper.kt"), settings_helper_code)

# 5. Päivitetään CalendarChangeTracker.kt
change_tracker_path = os.path.join(BASE_PKG_DIR, "CalendarChangeTracker.kt")
with open(change_tracker_path, "r", encoding="utf-8") as f:
    change_tracker = f.read()

old_ui_methods = re.search(
    r"    fun showManageChangesDialog\(.*$",
    change_tracker,
    flags=re.DOTALL,
)
if not old_ui_methods:
    raise RuntimeError("CalendarChangeTracker.kt: showManageChangesDialog-metodia ei löytynyt.")

for imp in [
    "import android.graphics.Color",
    "import android.graphics.Typeface",
    "import android.graphics.drawable.GradientDrawable",
    "import android.view.Gravity",
    "import android.view.View",
    "import android.view.ViewGroup",
]:
    if imp not in change_tracker:
        change_tracker = change_tracker.replace("import android.content.Context\n", f"import android.content.Context\n{imp}\n", 1)

new_ui_methods = """    fun showManageChangesDialog(context: Context, onChanged: (() -> Unit)? = null) {
        val changes = getLastChanges(context)
        val density = context.resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()

        fun makeCardBg(fillHex: String = "#182332", strokeHex: String = "#2A394A", radiusDp: Int = 12): GradientDrawable {
            return GradientDrawable().apply {
                setColor(Color.parseColor(fillHex))
                setStroke(dp(1), Color.parseColor(strokeHex))
                cornerRadius = dp(radiusDp).toFloat()
            }
        }

        val rootContainer = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#0F1722"))
        }

        val headerBar = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(20), dp(18), dp(20), dp(14))
        }
        headerBar.addView(TextView(context).apply {
            text = "Kalenterimuutosten hallinta"
            textSize = 19f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#F1F5F9"))
        })
        headerBar.addView(TextView(context).apply {
            text = if (changes.isEmpty()) "Ei avoimia muutoksia" else "Yhteenveto: ${formatSummary(changes)}"
            textSize = 12f
            setTextColor(Color.parseColor("#38BDF8"))
            setPadding(0, dp(2), 0, 0)
        })
        rootContainer.addView(headerBar)

        val topDivider = View(context).apply { setBackgroundColor(Color.parseColor("#2A394A")) }
        rootContainer.addView(topDivider, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)))

        val scroll = ScrollView(context).apply { isFillViewport = true }
        val rootLayout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(14), dp(16), dp(16))
        }
        scroll.addView(rootLayout)
        rootContainer.addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))

        var dialogRef: AlertDialog? = null

        if (changes.isEmpty()) {
            val emptyBox = LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                background = makeCardBg("#182332", "#2A394A", 12)
                setPadding(dp(16), dp(20), dp(16), dp(20))
            }
            emptyBox.addView(TextView(context).apply {
                text = "Ei viimeisimpiä synkronoinnin tekemiä kalenterimuutoksia."
                setTextColor(Color.parseColor("#CBD5E1"))
                textSize = 14f
            })
            rootLayout.addView(emptyBox)
        } else {
            val headerTv = TextView(context).apply {
                text = "Voit perua yksittäisiä muutoksia, muokata niiden tietoja tai kumota kaikki kerralla:"
                setTextColor(Color.parseColor("#94A3B8"))
                textSize = 13f
                setPadding(0, 0, 0, dp(12))
            }
            rootLayout.addView(headerTv)

            for (item in changes) {
                val accentHex = when (item.type) {
                    ChangeType.ADDED -> "#10B981"
                    ChangeType.MODIFIED -> "#38BDF8"
                    ChangeType.REMOVED -> "#EF4444"
                }

                val card = LinearLayout(context).apply {
                    orientation = LinearLayout.VERTICAL
                    background = makeCardBg("#182332", "#2A394A", 12)
                    setPadding(dp(14), dp(14), dp(14), dp(14))
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT
                    ).apply {
                        bottomMargin = dp(12)
                    }
                }

                val badgeTv = TextView(context).apply {
                    text = when (item.type) {
                        ChangeType.ADDED -> "LISÄTTY"
                        ChangeType.MODIFIED -> "MUOKATTU"
                        ChangeType.REMOVED -> "POISTETTU"
                    }
                    textSize = 11f
                    letterSpacing = 0.05f
                    setTypeface(null, Typeface.BOLD)
                    setTextColor(Color.parseColor(accentHex))
                    setPadding(0, 0, 0, dp(4))
                }
                card.addView(badgeTv)

                val bodyLines = formatChangeDisplay(item).substringAfter("] ").trim()
                val infoTv = TextView(context).apply {
                    text = bodyLines
                    setTextColor(Color.parseColor("#F1F5F9"))
                    textSize = 14f
                }
                card.addView(infoTv)

                val btnRow = LinearLayout(context).apply {
                    orientation = LinearLayout.HORIZONTAL
                    setPadding(0, dp(12), 0, 0)
                }

                val btnEdit = Button(context).apply {
                    text = "Muokkaa"
                    isAllCaps = false
                    textSize = 13f
                    setTypeface(null, Typeface.BOLD)
                    background = makeCardBg("#1E3A5F", "#0284C7", 8)
                    setTextColor(Color.parseColor("#E0F2FE"))
                    setPadding(dp(14), dp(8), dp(14), dp(8))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
                        marginEnd = dp(8)
                    }
                }

                val btnRevert = Button(context).apply {
                    text = "Peru muutos"
                    isAllCaps = false
                    textSize = 13f
                    setTypeface(null, Typeface.BOLD)
                    background = makeCardBg("#3F1D24", "#DC2626", 8)
                    setTextColor(Color.parseColor("#FEE2E2"))
                    setPadding(dp(14), dp(8), dp(14), dp(8))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                }

                btnRow.addView(btnEdit)
                btnRow.addView(btnRevert)
                card.addView(btnRow)
                rootLayout.addView(card)

                btnEdit.setOnClickListener {
                    showEditEventDialog(context, item) {
                        dialogRef?.dismiss()
                        onChanged?.invoke()
                        showManageChangesDialog(context, onChanged)
                    }
                }

                btnRevert.setOnClickListener {
                    if (revertSingleChange(context, item)) {
                        Toast.makeText(context, "Muutos peruttu: ${item.title}", Toast.LENGTH_SHORT).show()
                        dialogRef?.dismiss()
                        onChanged?.invoke()
                        showManageChangesDialog(context, onChanged)
                    } else {
                        Toast.makeText(context, "Muutoksen peruminen epäonnistui", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }

        val bottomDivider = View(context).apply { setBackgroundColor(Color.parseColor("#2A394A")) }
        rootContainer.addView(bottomDivider, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)))

        val footerBar = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(16), dp(12), dp(16), dp(12))
        }

        if (changes.isNotEmpty()) {
            val btnRevertAll = Button(context).apply {
                text = "Peru kaikki (${changes.size})"
                isAllCaps = false
                textSize = 13f
                setTypeface(null, Typeface.BOLD)
                background = makeCardBg("#3F1D24", "#DC2626", 8)
                setTextColor(Color.parseColor("#FEE2E2"))
                setPadding(dp(14), dp(10), dp(14), dp(10))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    marginEnd = dp(10)
                }
                setOnClickListener {
                    val reverted = revertAllChanges(context)
                    Toast.makeText(context, "Peruttu $reverted kalenterimuutosta", Toast.LENGTH_LONG).show()
                    dialogRef?.dismiss()
                    onChanged?.invoke()
                }
            }
            footerBar.addView(btnRevertAll)
        }

        val btnClose = Button(context).apply {
            text = "Sulje"
            isAllCaps = false
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            background = makeCardBg("#1982C4", "#38BDF8", 8)
            setTextColor(Color.parseColor("#FFFFFF"))
            setPadding(dp(20), dp(10), dp(20), dp(10))
            setOnClickListener { dialogRef?.dismiss() }
        }
        footerBar.addView(btnClose)
        rootContainer.addView(footerBar)

        val dialog = AlertDialog.Builder(context)
            .setView(rootContainer)
            .create()
        dialogRef = dialog
        dialog.window?.setBackgroundDrawable(makeCardBg("#0F1722", "#2A394A", 14))
        dialog.show()
    }

    private fun showEditEventDialog(
        context: Context,
        item: CalendarChangeItem,
        onSaved: () -> Unit
    ) {
        val density = context.resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()

        fun makeCardBg(fillHex: String = "#182332", strokeHex: String = "#2A394A", radiusDp: Int = 10): GradientDrawable {
            return GradientDrawable().apply {
                setColor(Color.parseColor(fillHex))
                setStroke(dp(1), Color.parseColor(strokeHex))
                cornerRadius = dp(radiusDp).toFloat()
            }
        }

        val rootContainer = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#0F1722"))
        }

        val headerBar = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(20), dp(16), dp(20), dp(14))
        }
        headerBar.addView(TextView(context).apply {
            text = "Muokkaa kalenteritapahtumaa"
            textSize = 18f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#F1F5F9"))
        })
        rootContainer.addView(headerBar)

        val layout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(14), dp(18), dp(14))
        }
        rootContainer.addView(layout)

        val lblTitle = TextView(context).apply {
            text = "Tapahtuman otsikko"
            textSize = 13f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, 0, 0, dp(6))
        }
        val inputTitle = EditText(context).apply {
            setText(item.title)
            inputType = InputType.TYPE_CLASS_TEXT
            background = makeCardBg("#111923", "#37475A", 8)
            setTextColor(Color.parseColor("#F1F5F9"))
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }

        val chkAllDay = CheckBox(context).apply {
            text = "Koko päivän tapahtuma (loma/vapaa)"
            isChecked = item.isAllDay
            setTextColor(Color.parseColor("#F1F5F9"))
            setPadding(dp(4), dp(12), 0, dp(12))
        }

        var selectedStart = if (item.isAllDay) {
            Instant.ofEpochMilli(item.startMs).atZone(ZoneOffset.UTC).toLocalDateTime()
        } else {
            Instant.ofEpochMilli(item.startMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
        }

        var selectedEnd = if (item.isAllDay) {
            Instant.ofEpochMilli(item.endMs).atZone(ZoneOffset.UTC).toLocalDateTime()
        } else {
            Instant.ofEpochMilli(item.endMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
        }

        val dateFmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")
        val timeFmt = DateTimeFormatter.ofPattern("HH:mm")

        fun stylePickerBtn(btn: Button) {
            btn.background = makeCardBg("#182332", "#37475A", 8)
            btn.setTextColor(Color.parseColor("#38BDF8"))
            btn.isAllCaps = false
            btn.textSize = 14f
            btn.setPadding(dp(12), dp(10), dp(12), dp(10))
            btn.layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                bottomMargin = dp(8)
            }
        }

        val btnStartDate = Button(context).apply {
            text = "Alkupäivä: ${selectedStart.format(dateFmt)}"
            stylePickerBtn(this)
        }
        val btnStartTime = Button(context).apply {
            text = "Alkuaika: ${selectedStart.format(timeFmt)}"
            stylePickerBtn(this)
        }
        val btnEndDate = Button(context).apply {
            text = "Loppupäivä: ${selectedEnd.format(dateFmt)}"
            stylePickerBtn(this)
        }
        val btnEndTime = Button(context).apply {
            text = "Loppuaika: ${selectedEnd.format(timeFmt)}"
            stylePickerBtn(this)
        }

        btnStartDate.setOnClickListener {
            DatePickerDialog(context, { _, y, m, d ->
                selectedStart = selectedStart.withYear(y).withMonth(m + 1).withDayOfMonth(d)
                btnStartDate.text = "Alkupäivä: ${selectedStart.format(dateFmt)}"
            }, selectedStart.year, selectedStart.monthValue - 1, selectedStart.dayOfMonth).show()
        }

        btnStartTime.setOnClickListener {
            TimePickerDialog(context, { _, h, min ->
                selectedStart = selectedStart.withHour(h).withMinute(min)
                btnStartTime.text = "Alkuaika: ${selectedStart.format(timeFmt)}"
            }, selectedStart.hour, selectedStart.minute, true).show()
        }

        btnEndDate.setOnClickListener {
            DatePickerDialog(context, { _, y, m, d ->
                selectedEnd = selectedEnd.withYear(y).withMonth(m + 1).withDayOfMonth(d)
                btnEndDate.text = "Loppupäivä: ${selectedEnd.format(dateFmt)}"
            }, selectedEnd.year, selectedEnd.monthValue - 1, selectedEnd.dayOfMonth).show()
        }

        btnEndTime.setOnClickListener {
            TimePickerDialog(context, { _, h, min ->
                selectedEnd = selectedEnd.withHour(h).withMinute(min)
                btnEndTime.text = "Loppuaika: ${selectedEnd.format(timeFmt)}"
            }, selectedEnd.hour, selectedEnd.minute, true).show()
        }

        layout.addView(lblTitle)
        layout.addView(inputTitle)
        layout.addView(chkAllDay)
        layout.addView(btnStartDate)
        layout.addView(btnStartTime)
        layout.addView(btnEndDate)
        layout.addView(btnEndTime)

        val footerBar = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(16), dp(12), dp(16), dp(12))
        }

        val btnCancel = Button(context).apply {
            text = "Peruuta"
            isAllCaps = false
            background = makeCardBg("#233040", "#37475A", 8)
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(dp(16), dp(10), dp(16), dp(10))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                marginEnd = dp(10)
            }
        }

        val btnSave = Button(context).apply {
            text = "Tallenna"
            isAllCaps = false
            setTypeface(null, Typeface.BOLD)
            background = makeCardBg("#1982C4", "#38BDF8", 8)
            setTextColor(Color.parseColor("#FFFFFF"))
            setPadding(dp(20), dp(10), dp(20), dp(10))
        }

        footerBar.addView(btnCancel)
        footerBar.addView(btnSave)
        rootContainer.addView(footerBar)

        val dialog = AlertDialog.Builder(context)
            .setView(rootContainer)
            .create()
        dialog.window?.setBackgroundDrawable(makeCardBg("#0F1722", "#2A394A", 14))

        btnCancel.setOnClickListener { dialog.dismiss() }
        btnSave.setOnClickListener {
            val titleStr = inputTitle.text.toString().trim().ifEmpty { item.title }
            val allDay = chkAllDay.isChecked
            val finalStartMs: Long
            val finalEndMs: Long
            if (allDay) {
                val sDate = selectedStart.toLocalDate()
                var eDate = selectedEnd.toLocalDate()
                if (!eDate.isAfter(sDate)) eDate = sDate.plusDays(1)
                finalStartMs = sDate.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli()
                finalEndMs = eDate.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli()
            } else {
                finalStartMs = selectedStart.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
                var eDt = selectedEnd
                if (!eDt.isAfter(selectedStart)) eDt = selectedStart.plusHours(8)
                finalEndMs = eDt.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            }

            if (updateSingleEvent(context, item, titleStr, finalStartMs, finalEndMs, allDay)) {
                Toast.makeText(context, "Tapahtuma päivitetty kalenteriin", Toast.LENGTH_SHORT).show()
                dialog.dismiss()
                onSaved()
            } else {
                Toast.makeText(context, "Tapahtuman päivitys epäonnistui", Toast.LENGTH_SHORT).show()
            }
        }

        dialog.show()
    }
}
"""

change_tracker = change_tracker[:old_ui_methods.start()] + new_ui_methods
write_file(change_tracker_path, change_tracker)

print("Kaikki muutokset ajettu onnistuneesti!")
