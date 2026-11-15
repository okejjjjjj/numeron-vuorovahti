package fi.numeron.vuorovahti

import android.Manifest
import android.app.AlertDialog
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CalendarContract
import android.text.InputType
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.ContextCompat

data class CalendarInfo(val id: Long, val name: String) {
    override fun toString(): String = name
}

object SettingsDialogHelper {

    fun showSettingsDialog(
        context: Context,
        onManualSync: () -> Unit,
        onManageChanges: () -> Unit,
        onTestNotification: () -> Unit,
        onSaved: () -> Unit
    ) {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)

        val scroll = ScrollView(context)
        val layout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(50, 30, 50, 10)
        }
        scroll.addView(layout)

        val chkDemo = CheckBox(context).apply {
            text = "Demotila (kokeile ilman tunnuksia)"
            isChecked = DemoModeHelper.isDemoEnabled(context)
        }

        val lblUrl = TextView(context).apply { text = "Numeron-palvelimen osoite (URL)" }
        val inputUrl = EditText(context).apply {
            setText(prefs.getString("server_url", "https://"))
            hint = "https://organisaatio.numeronwfm.com"
            inputType = InputType.TYPE_TEXT_VARIATION_URI
        }

        val lblUser = TextView(context).apply { text = "Käyttäjätunnus" }
        val inputUser = EditText(context).apply {
            setText(prefs.getString("username", ""))
            inputType = InputType.TYPE_CLASS_TEXT
        }

        val lblPass = TextView(context).apply { text = "Salasana" }
        val inputPass = EditText(context).apply {
            setText(prefs.getString("password", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }

        val lblCal = TextView(context).apply { text = "Kohdekalenteri" }
        val calendars = getAvailableCalendars(context)
        val spinnerCal = Spinner(context)
        val adapter = ArrayAdapter(context, android.R.layout.simple_spinner_dropdown_item, calendars)
        spinnerCal.adapter = adapter

        val savedCalId = prefs.getLong("calendar_id", -1L)
        val selectedIndex = calendars.indexOfFirst { it.id == savedCalId }
        if (selectedIndex >= 0) spinnerCal.setSelection(selectedIndex)

        val lblReminder = TextView(context).apply { text = "Muistutus ennen vuoroa (min)" }
        val inputReminder = EditText(context).apply {
            setText(prefs.getInt("reminder_minutes", 30).toString())
            inputType = InputType.TYPE_CLASS_NUMBER
        }

        val chkRequests = CheckBox(context).apply {
            text = "Ilmoita vapaatoiveiden päätöksistä"
            isChecked = prefs.getBoolean("track_requests", true)
        }

        val btnSyncNow = Button(context).apply {
            text = "Synkronoi vuorot kalenteriin nyt"
        }

        val pendingCount = CalendarChangeTracker.getLastChanges(context).size
        val btnManageChanges = Button(context).apply {
            text = "Hallitse / Peru kalenterimuutoksia ($pendingCount)"
        }

        val btnTestNotif = Button(context).apply {
            text = "Testaa leimausmuistutusilmoitusta"
        }

        layout.addView(chkDemo)
        layout.addView(lblUrl)
        layout.addView(inputUrl)
        layout.addView(lblUser)
        layout.addView(inputUser)
        layout.addView(lblPass)
        layout.addView(inputPass)
        layout.addView(lblCal)
        layout.addView(spinnerCal)
        layout.addView(lblReminder)
        layout.addView(inputReminder)
        layout.addView(chkRequests)
        layout.addView(btnSyncNow)
        layout.addView(btnManageChanges)
        layout.addView(btnTestNotif)

        val dialog = AlertDialog.Builder(context)
            .setTitle("Numeron Vuorovahti – Asetukset")
            .setView(scroll)
            .setPositiveButton("Tallenna") { _, _ ->
                val selectedCal = spinnerCal.selectedItem as? CalendarInfo
                val reminderMins = inputReminder.text.toString().toIntOrNull() ?: 30
                val enteredUser = inputUser.text.toString().trim()
                val demoState = if (enteredUser.isNotEmpty() && chkDemo.isChecked && prefs.getString("username", "").isNullOrEmpty()) {
                    false
                } else {
                    chkDemo.isChecked
                }

                prefs.edit()
                    .putBoolean("demo_mode", demoState)
                    .putString("server_url", inputUrl.text.toString().trim().trimEnd('/'))
                    .putString("username", enteredUser)
                    .putString("password", inputPass.text.toString())
                    .putLong("calendar_id", selectedCal?.id ?: -1L)
                    .putInt("reminder_minutes", reminderMins)
                    .putBoolean("track_requests", chkRequests.isChecked)
                    .apply()

                Toast.makeText(context, "Asetukset tallennettu", Toast.LENGTH_SHORT).show()
                onSaved()
            }
            .setNegativeButton("Peruuta", null)
            .create()

        btnSyncNow.setOnClickListener {
            dialog.dismiss()
            onManualSync()
        }

        btnManageChanges.setOnClickListener {
            dialog.dismiss()
            onManageChanges()
        }

        btnTestNotif.setOnClickListener {
            dialog.dismiss()
            onTestNotification()
        }

        dialog.show()
    }

    fun getAvailableCalendars(context: Context): List<CalendarInfo> {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return emptyList()
        }
        val list = mutableListOf<CalendarInfo>()
        val projection = arrayOf(
            CalendarContract.Calendars._ID,
            CalendarContract.Calendars.CALENDAR_DISPLAY_NAME
        )
        val selection = "${CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL} >= ${CalendarContract.Calendars.CAL_ACCESS_CONTRIBUTOR}"
        context.contentResolver.query(
            CalendarContract.Calendars.CONTENT_URI,
            projection,
            selection,
            null,
            null
        )?.use { cursor ->
            while (cursor.moveToNext()) {
                val id = cursor.getLong(0)
                val name = cursor.getString(1) ?: "Kalenteri $id"
                list.add(CalendarInfo(id, name))
            }
        }
        return list
    }
}
