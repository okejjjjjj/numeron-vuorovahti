package fi.numeron.vuorovahti

import android.Manifest
import android.app.AlertDialog
import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CalendarContract
import android.text.InputType
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.ContextCompat
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.TimeZone

enum class ChangeType {
    ADDED, MODIFIED, REMOVED
}

data class CalendarChangeItem(
    val id: String,
    val type: ChangeType,
    val calendarId: Long,
    val eventId: Long?, // Nykyisen kalenteritapahtuman ID (ADDED / MODIFIED)
    val title: String,
    val startMs: Long,
    val endMs: Long,
    val isAllDay: Boolean,
    // Edeltävät arvot kumoamista varten (MODIFIED / REMOVED)
    val prevTitle: String? = null,
    val prevStartMs: Long? = null,
    val prevEndMs: Long? = null,
    val prevIsAllDay: Boolean = false,
    val timestampMs: Long = System.currentTimeMillis()
) {
    fun toJson(): JSONObject = JSONObject().apply {
        put("id", id)
        put("type", type.name)
        put("calendarId", calendarId)
        put("eventId", eventId ?: -1L)
        put("title", title)
        put("startMs", startMs)
        put("endMs", endMs)
        put("isAllDay", isAllDay)
        if (prevTitle != null) put("prevTitle", prevTitle)
        if (prevStartMs != null) put("prevStartMs", prevStartMs)
        if (prevEndMs != null) put("prevEndMs", prevEndMs)
        put("prevIsAllDay", prevIsAllDay)
        put("timestampMs", timestampMs)
    }

    companion object {
        fun fromJson(obj: JSONObject): CalendarChangeItem {
            val evId = obj.optLong("eventId", -1L)
            return CalendarChangeItem(
                id = obj.getString("id"),
                type = ChangeType.valueOf(obj.getString("type")),
                calendarId = obj.getLong("calendarId"),
                eventId = if (evId > 0) evId else null,
                title = obj.getString("title"),
                startMs = obj.getLong("startMs"),
                endMs = obj.getLong("endMs"),
                isAllDay = obj.getBoolean("isAllDay"),
                prevTitle = if (obj.has("prevTitle")) obj.getString("prevTitle") else null,
                prevStartMs = if (obj.has("prevStartMs")) obj.getLong("prevStartMs") else null,
                prevEndMs = if (obj.has("prevEndMs")) obj.getLong("prevEndMs") else null,
                prevIsAllDay = obj.optBoolean("prevIsAllDay", false),
                timestampMs = obj.optLong("timestampMs", System.currentTimeMillis())
            )
        }
    }
}

object CalendarChangeTracker {

    private const val PREFS_NAME = "NumeronPrefs"
    private const val KEY_CHANGES = "last_calendar_changes"

    fun saveChanges(context: Context, changes: List<CalendarChangeItem>) {
        val arr = JSONArray()
        changes.forEach { arr.put(it.toJson()) }
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_CHANGES, arr.toString())
            .apply()
    }

    fun getLastChanges(context: Context): MutableList<CalendarChangeItem> {
        val raw = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_CHANGES, "[]") ?: "[]"
        val list = mutableListOf<CalendarChangeItem>()
        try {
            val arr = JSONArray(raw)
            for (i in 0 until arr.length()) {
                list.add(CalendarChangeItem.fromJson(arr.getJSONObject(i)))
            }
        } catch (_: Exception) {
        }
        return list
    }

    fun formatSummary(changes: List<CalendarChangeItem>): String {
        val added = changes.count { it.type == ChangeType.ADDED }
        val mod = changes.count { it.type == ChangeType.MODIFIED }
        val rem = changes.count { it.type == ChangeType.REMOVED }
        val parts = mutableListOf<String>()
        if (added > 0) parts.add("$added lisätty")
        if (mod > 0) parts.add("$mod muokattu")
        if (rem > 0) parts.add("$rem poistettu")
        return if (parts.isEmpty()) "Ei muutoksia" else parts.joinToString(", ")
    }

    fun formatChangeDisplay(item: CalendarChangeItem): String {
        val dateFmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")
        val timeFmt = DateTimeFormatter.ofPattern("HH:mm")

        fun fmtSpan(startMs: Long, endMs: Long, allDay: Boolean): String {
            return if (allDay) {
                val s = Instant.ofEpochMilli(startMs).atZone(ZoneOffset.UTC).toLocalDate()
                val e = Instant.ofEpochMilli(endMs).atZone(ZoneOffset.UTC).toLocalDate().minusDays(1)
                if (s == e) "${s.format(dateFmt)} (Koko päivä)"
                else "${s.format(dateFmt)}–${e.format(dateFmt)} (Koko päivä)"
            } else {
                val s = Instant.ofEpochMilli(startMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
                val e = Instant.ofEpochMilli(endMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
                "${s.format(dateFmt)} ${s.format(timeFmt)}–${e.format(timeFmt)}"
            }
        }

        return when (item.type) {
            ChangeType.ADDED -> "[LISÄTTY] ${item.title}\n${fmtSpan(item.startMs, item.endMs, item.isAllDay)}"
            ChangeType.REMOVED -> "[POISTETTU] ${item.title}\n${fmtSpan(item.startMs, item.endMs, item.isAllDay)}"
            ChangeType.MODIFIED -> {
                val oldInfo = if (item.prevTitle != null && item.prevStartMs != null && item.prevEndMs != null) {
                    "\nAiemmin: ${item.prevTitle} (${fmtSpan(item.prevStartMs, item.prevEndMs, item.prevIsAllDay)})"
                } else ""
                "[MUOKATTU] ${item.title}\nUusi: ${fmtSpan(item.startMs, item.endMs, item.isAllDay)}$oldInfo"
            }
        }
    }

    fun revertSingleChange(context: Context, item: CalendarChangeItem): Boolean {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return false
        }
        val resolver = context.contentResolver
        try {
            when (item.type) {
                ChangeType.ADDED -> {
                    if (item.eventId != null) {
                        val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, item.eventId)
                        resolver.delete(uri, null, null)
                    }
                }
                ChangeType.REMOVED -> {
                    val values = ContentValues().apply {
                        put(CalendarContract.Events.CALENDAR_ID, item.calendarId)
                        put(CalendarContract.Events.TITLE, item.prevTitle ?: item.title)
                        put(CalendarContract.Events.DESCRIPTION, CalendarSyncHelper.EVENT_DESCRIPTION_TAG)
                        val sMs = item.prevStartMs ?: item.startMs
                        val eMs = item.prevEndMs ?: item.endMs
                        val allDay = if (item.prevStartMs != null) item.prevIsAllDay else item.isAllDay
                        put(CalendarContract.Events.ALL_DAY, if (allDay) 1 else 0)
                        put(CalendarContract.Events.EVENT_TIMEZONE, if (allDay) "UTC" else TimeZone.getDefault().id)
                        put(CalendarContract.Events.DTSTART, sMs)
                        put(CalendarContract.Events.DTEND, eMs)
                    }
                    resolver.insert(CalendarContract.Events.CONTENT_URI, values)
                }
                ChangeType.MODIFIED -> {
                    if (item.eventId != null && item.prevTitle != null && item.prevStartMs != null && item.prevEndMs != null) {
                        val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, item.eventId)
                        val values = ContentValues().apply {
                            put(CalendarContract.Events.TITLE, item.prevTitle)
                            put(CalendarContract.Events.ALL_DAY, if (item.prevIsAllDay) 1 else 0)
                            put(CalendarContract.Events.EVENT_TIMEZONE, if (item.prevIsAllDay) "UTC" else TimeZone.getDefault().id)
                            put(CalendarContract.Events.DTSTART, item.prevStartMs)
                            put(CalendarContract.Events.DTEND, item.prevEndMs)
                        }
                        resolver.update(uri, values, null, null)
                    }
                }
            }
            val remaining = getLastChanges(context).filterNot { it.id == item.id }
            saveChanges(context, remaining)
            CalendarSyncHelper.scheduleShiftReminders(context, item.calendarId)
            return true
        } catch (_: Exception) {
            return false
        }
    }

    fun revertAllChanges(context: Context): Int {
        val current = getLastChanges(context)
        var count = 0
        for (item in current) {
            if (revertSingleChange(context, item)) {
                count++
            }
        }
        return count
    }

    fun updateSingleEvent(
        context: Context,
        item: CalendarChangeItem,
        newTitle: String,
        newStartMs: Long,
        newEndMs: Long,
        newIsAllDay: Boolean
    ): Boolean {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return false
        }
        val resolver = context.contentResolver
        try {
            var activeEventId = item.eventId
            val values = ContentValues().apply {
                put(CalendarContract.Events.TITLE, newTitle)
                put(CalendarContract.Events.ALL_DAY, if (newIsAllDay) 1 else 0)
                put(CalendarContract.Events.EVENT_TIMEZONE, if (newIsAllDay) "UTC" else TimeZone.getDefault().id)
                put(CalendarContract.Events.DTSTART, newStartMs)
                put(CalendarContract.Events.DTEND, newEndMs)
            }

            if (item.type == ChangeType.REMOVED || activeEventId == null) {
                values.put(CalendarContract.Events.CALENDAR_ID, item.calendarId)
                values.put(CalendarContract.Events.DESCRIPTION, CalendarSyncHelper.EVENT_DESCRIPTION_TAG)
                val insertedUri = resolver.insert(CalendarContract.Events.CONTENT_URI, values)
                activeEventId = insertedUri?.lastPathSegment?.toLongOrNull()
            } else {
                val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, activeEventId)
                resolver.update(uri, values, null, null)
            }

            val updatedItem = item.copy(
                type = if (item.type == ChangeType.REMOVED) ChangeType.ADDED else item.type,
                eventId = activeEventId,
                title = newTitle,
                startMs = newStartMs,
                endMs = newEndMs,
                isAllDay = newIsAllDay
            )
            val all = getLastChanges(context).map { if (it.id == item.id) updatedItem else it }
            saveChanges(context, all)
            CalendarSyncHelper.scheduleShiftReminders(context, item.calendarId)
            return true
        } catch (_: Exception) {
            return false
        }
    }

    fun showManageChangesDialog(context: Context, onChanged: (() -> Unit)? = null) {
        val changes = getLastChanges(context)

        val scroll = ScrollView(context)
        val rootLayout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 24, 40, 16)
        }
        scroll.addView(rootLayout)

        if (changes.isEmpty()) {
            val emptyTv = TextView(context).apply {
                text = "Ei viimeisimpiä synkronoinnin tekemiä kalenterimuutoksia."
                setPadding(0, 20, 0, 20)
            }
            rootLayout.addView(emptyTv)
        } else {
            val headerTv = TextView(context).apply {
                text = "Voit perua yksittäisiä muutoksia, muokata niiden tietoja tai kumota kaikki kerralla:"
                setPadding(0, 0, 0, 16)
            }
            rootLayout.addView(headerTv)

            for (item in changes) {
                val card = LinearLayout(context).apply {
                    orientation = LinearLayout.VERTICAL
                    setBackgroundColor(0xFF1E293B.toInt())
                    setPadding(24, 20, 24, 20)
                    val params = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT
                    )
                    params.setMargins(0, 0, 0, 16)
                    layoutParams = params
                }

                val infoTv = TextView(context).apply {
                    text = formatChangeDisplay(item)
                    setTextColor(0xFFF1F5F9.toInt())
                    textSize = 14f
                }
                card.addView(infoTv)

                val btnRow = LinearLayout(context).apply {
                    orientation = LinearLayout.HORIZONTAL
                    setPadding(0, 14, 0, 0)
                }

                val btnEdit = Button(context).apply {
                    text = "Muokkaa"
                    isAllCaps = false
                }
                val btnRevert = Button(context).apply {
                    text = "Peru muutos"
                    isAllCaps = false
                }

                btnRow.addView(btnEdit)
                btnRow.addView(btnRevert)
                card.addView(btnRow)
                rootLayout.addView(card)

                btnEdit.setOnClickListener {
                    showEditEventDialog(context, item) {
                        onChanged?.invoke()
                        showManageChangesDialog(context, onChanged)
                    }
                }

                btnRevert.setOnClickListener {
                    if (revertSingleChange(context, item)) {
                        Toast.makeText(context, "Muutos peruttu: ${item.title}", Toast.LENGTH_SHORT).show()
                        onChanged?.invoke()
                        showManageChangesDialog(context, onChanged)
                    } else {
                        Toast.makeText(context, "Muutoksen peruminen epäonnistui", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }

        val builder = AlertDialog.Builder(context)
            .setTitle("Kalenterimuutosten hallinta")
            .setView(scroll)
            .setPositiveButton("Sulje", null)

        if (changes.isNotEmpty()) {
            builder.setNeutralButton("Peru kaikki muutokset (${changes.size})") { _, _ ->
                val reverted = revertAllChanges(context)
                Toast.makeText(context, "Peruttu $reverted kalenterimuutosta", Toast.LENGTH_LONG).show()
                onChanged?.invoke()
            }
        }

        builder.show()
    }

    private fun showEditEventDialog(
        context: Context,
        item: CalendarChangeItem,
        onSaved: () -> Unit
    ) {
        val layout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(45, 25, 45, 10)
        }

        val lblTitle = TextView(context).apply { text = "Tapahtuman otsikko" }
        val inputTitle = EditText(context).apply {
            setText(item.title)
            inputType = InputType.TYPE_CLASS_TEXT
        }

        val chkAllDay = CheckBox(context).apply {
            text = "Koko päivän tapahtuma (loma/vapaa)"
            isChecked = item.isAllDay
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

        val btnStartDate = Button(context).apply { text = "Alkupäivä: ${selectedStart.format(dateFmt)}" }
        val btnStartTime = Button(context).apply { text = "Alkuaika: ${selectedStart.format(timeFmt)}" }
        val btnEndDate = Button(context).apply { text = "Loppupäivä: ${selectedEnd.format(dateFmt)}" }
        val btnEndTime = Button(context).apply { text = "Loppuaika: ${selectedEnd.format(timeFmt)}" }

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

        AlertDialog.Builder(context)
            .setTitle("Muokkaa kalenteritapahtumaa")
            .setView(layout)
            .setPositiveButton("Tallenna") { _, _ ->
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
                    onSaved()
                } else {
                    Toast.makeText(context, "Tapahtuman päivitys epäonnistui", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("Peruuta", null)
            .show()
    }
}
