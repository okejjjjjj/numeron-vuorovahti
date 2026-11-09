package fi.oma.numeron

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.widget.RemoteViews
import androidx.core.app.NotificationCompat

class ShiftAlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED || intent.action == Intent.ACTION_MY_PACKAGE_REPLACED) {
            VuorovahtiHelper.ensureRemindersFromCalendar(context)
            return
        }

        val actionType = intent.getStringExtra("ACTION_TYPE") ?: "STAMP"
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        if (actionType == "CHECK_NEW_LIST") {
            if (!SettingsManager.isAutoSyncEnabled(context)) return

            val checkIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
                putExtra("AUTO_SYNC_NEW_LIST", true)
            }
            val pi = PendingIntent.getActivity(
                context, 9991, checkIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                nm.createNotificationChannel(
                    NotificationChannel("numeron_list_channel", "Uudet työvuorolistat", NotificationManager.IMPORTANCE_HIGH)
                )
            }
            val notif = NotificationCompat.Builder(context, "numeron_list_channel")
                .setSmallIcon(R.drawable.ic_launcher)
                .setSubText("Numeron Vuorovahti")
                .setContentTitle("Uusi työvuorolista saatavilla!")
                .setContentText("Napauta tästä, niin uudet vuorot haetaan suoraan kalenteriin.")
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .setContentIntent(pi)
                .build()
            nm.notify(3003, notif)
            return
        }

        if (!SettingsManager.isStampNotificationEnabled(context)) return

        val shiftTitle = intent.getStringExtra("SHIFT_TITLE") ?: "Työvuoro"
        val shiftTime = intent.getStringExtra("SHIFT_TIME") ?: ""
        val isEnding = intent.getBooleanExtra("IS_ENDING", false)

        val titleText = if (isEnding) {
            if (shiftTime.isNotEmpty()) "Vuoro päättyy klo $shiftTime" else "Vuoro päättyy pian"
        } else {
            if (shiftTime.isNotEmpty()) "Vuoro alkaa klo $shiftTime" else "Vuoro alkaa pian"
        }
        val btnText = if (isEnding) "LEIMAA ULOS" else "LEIMAA SISÄÄN"

        val channelId = "numeron_shift_channel"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(channelId, "Työvuoromuistutukset", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Hiljaiset leimausmuistutukset"
                enableVibration(false)
                setSound(null, null)
            }
            nm.createNotificationChannel(channel)
        }

        val clickIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra("AUTO_STAMP", true)
            putExtra("IS_ENDING", isEnding)
        }
        val reqCode = (System.currentTimeMillis() / 1000L).toInt()
        val pi = PendingIntent.getActivity(
            context, reqCode, clickIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val customView = RemoteViews(context.packageName, R.layout.notification_shift).apply {
            setTextViewText(R.id.notif_title, titleText)
            setTextViewText(R.id.notif_text, shiftTitle)
            setTextViewText(R.id.notif_btn, btnText)
            setOnClickPendingIntent(R.id.notif_btn, pi)
        }

        VuorovahtiHelper.saveLastTriggeredReminder(
            context,
            "${if (isEnding) "Ulosleimaus" else "Sisäänleimaus"} ($shiftTitle${if (shiftTime.isNotEmpty()) " klo $shiftTime" else ""})"
        )

        val notification = NotificationCompat.Builder(context, channelId)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle("Numeron Vuorovahti – $titleText")
            .setContentText(shiftTitle)
            .setSubText("Numeron Vuorovahti")
            .setCustomContentView(customView)
            .setCustomBigContentView(customView)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setAutoCancel(true)
            .setTimeoutAfter(60 * 60 * 1000L)
            .setContentIntent(pi)
            .build()

        nm.notify(if (isEnding) 2002 else 1001, notification)
    }
}
