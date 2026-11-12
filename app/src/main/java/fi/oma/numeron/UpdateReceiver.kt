package fi.oma.numeron

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class UpdateReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        if (action == Intent.ACTION_MY_PACKAGE_REPLACED || action == Intent.ACTION_BOOT_COMPLETED) {
            try {
                VuorovahtiHelper.ensureRemindersFromCalendar(context)
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }
}
