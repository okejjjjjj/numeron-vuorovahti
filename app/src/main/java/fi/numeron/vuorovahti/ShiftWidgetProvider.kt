package fi.numeron.vuorovahti

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

class ShiftWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray
    ) {
        for (appWidgetId in appWidgetIds) {
            updateWidget(context, appWidgetManager, appWidgetId)
        }
    }

    companion object {
        private val timeFmt = DateTimeFormatter.ofPattern("HH:mm")
        private val dateFmt = DateTimeFormatter.ofPattern("d.M.")
        private val fiDow = arrayOf("Ma", "Ti", "Ke", "To", "Pe", "La", "Su")
        private val enDow = arrayOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

        fun updateAllWidgets(context: Context) {
            try {
                val appCtx = context.applicationContext
                val manager = AppWidgetManager.getInstance(appCtx)
                val ids = manager.getAppWidgetIds(ComponentName(appCtx, ShiftWidgetProvider::class.java))
                if (ids.isEmpty()) return
                for (id in ids) {
                    updateWidget(appCtx, manager, id)
                }
            } catch (_: Exception) {
            }
        }

        private fun updateWidget(
            context: Context,
            appWidgetManager: AppWidgetManager,
            appWidgetId: Int
        ) {
            val en = DemoModeHelper.isEnglish(context)
            val isDemo = DemoModeHelper.isDemoEnabled(context)
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)

            val isClockedIn = if (isDemo) {
                prefs.getBoolean("demo_stamped_in", false)
            } else {
                NumeronApiClient.loadCachedStampingState(context)
                    ?.nextDirection?.equals("OUT", ignoreCase = true) == true
            }

            val shifts = if (isDemo) {
                DemoModeHelper.generateDemoWorkShifts(context)
            } else {
                CalendarSyncHelper.loadCachedShifts(context)
            }.orEmpty()

            val now = LocalDateTime.now()
            val today = LocalDate.now()
            val activeOrNext = shifts
                .filter { !it.isAllDayLeave && it.end.isAfter(now) }
                .minByOrNull { it.start }

            val statusText = when {
                isClockedIn -> if (en) "● CLOCKED IN" else "● TÖISSÄ"
                activeOrNext != null && !activeOrNext.start.isAfter(now) -> if (en) "SHIFT IN PROGRESS" else "VUORO KÄYNNISSÄ"
                else -> if (en) "NEXT SHIFT" else "SEURAAVA VUORO"
            }

            val mainLine: String
            val subLine: String
            if (activeOrNext != null) {
                val dayPrefix = when (activeOrNext.start.toLocalDate()) {
                    today -> if (en) "Today" else "Tänään"
                    today.plusDays(1) -> if (en) "Tomorrow" else "Huomenna"
                    else -> {
                        val dow = (if (en) enDow else fiDow)[activeOrNext.start.dayOfWeek.value - 1]
                        "$dow ${activeOrNext.start.format(dateFmt)}"
                    }
                }
                val timePart = "${activeOrNext.start.format(timeFmt)}–${activeOrNext.end.format(timeFmt)}"
                mainLine = "$dayPrefix $timePart"
                val detailParts = listOf(
                    activeOrNext.location.trim(),
                    activeOrNext.description.lineSequence().firstOrNull()?.trim().orEmpty()
                ).filter { it.isNotEmpty() }
                subLine = if (detailParts.isNotEmpty()) {
                    detailParts.joinToString(" • ")
                } else {
                    activeOrNext.title
                }
            } else {
                mainLine = if (en) "No upcoming shifts" else "Ei tulevia vuoroja"
                subLine = if (en) "Tap to open Vuorovahti" else "Napauta avataksesi Vuorovahti"
            }

            val btnLabel = if (isClockedIn) {
                if (en) "OUT" else "ULOS"
            } else {
                if (en) "IN" else "SISÄÄN"
            }
            val btnBg = if (isClockedIn) R.drawable.bg_notif_btn_out else R.drawable.bg_notif_btn_in

            val openAppIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            }
            val openAppPi = PendingIntent.getActivity(
                context,
                8800 + appWidgetId,
                openAppIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            val stampIntent = Intent(context, QuickStampActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra("AUTO_STAMP", true)
                putExtra("IS_ENDING", isClockedIn)
                putExtra("IS_TEST", false)
            }
            val stampPi = PendingIntent.getActivity(
                context,
                8900 + appWidgetId,
                stampIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            val views = RemoteViews(context.packageName, R.layout.widget_shift_info).apply {
                setTextViewText(R.id.widgetStatus, statusText)
                setTextViewText(R.id.widgetShiftMain, mainLine)
                setTextViewText(R.id.widgetShiftSub, subLine)
                setTextViewText(R.id.widgetBtnStamp, btnLabel)
                setInt(R.id.widgetBtnStamp, "setBackgroundResource", btnBg)
                setOnClickPendingIntent(R.id.widgetInfoArea, openAppPi)
                setOnClickPendingIntent(R.id.widgetBtnStamp, stampPi)
            }
            appWidgetManager.updateAppWidget(appWidgetId, views)
        }
    }
}
