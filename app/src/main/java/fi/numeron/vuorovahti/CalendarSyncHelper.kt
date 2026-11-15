package fi.numeron.vuorovahti

import android.Manifest
import android.app.AlarmManager
import android.app.PendingIntent
import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.provider.CalendarContract
import androidx.core.content.ContextCompat
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.TimeZone
import java.util.UUID

object CalendarSyncHelper {

    const val EVENT_DESCRIPTION_TAG = "Synkronoitu Numeron Vuorovahti -sovelluksesta"

    private data class ExistingEvent(
        val eventId: Long,
        val title: String,
        val startMs: Long,
        val endMs: Long,
        val isAllDay: Boolean
    )

    fun getTargetCalendarId(context: Context): Long? {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val savedId = prefs.getLong("calendar_id", -1L)
        if (savedId > 0) return savedId

        val available = SettingsDialogHelper.getAvailableCalendars(context)
        return available.firstOrNull()?.id
    }

    fun syncShiftsToCalendar(context: Context, calendarId: Long, shifts: List<WorkShift>): List<CalendarChangeItem> {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_CALENDAR) != PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return emptyList()
        }

        val resolver = context.contentResolver
        val todayStartMs = LocalDate.now().atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli()

        // 1. Haetaan olemassa olevat sovelluksen synkronoimat tulevat tapahtumat vertailua varten
        val existingEvents = mutableListOf<ExistingEvent>()
        val projection = arrayOf(
            CalendarContract.Events._ID,
            CalendarContract.Events.TITLE,
            CalendarContract.Events.DTSTART,
            CalendarContract.Events.DTEND,
            CalendarContract.Events.ALL_DAY
        )
        val selection = "${CalendarContract.Events.CALENDAR_ID} = ? AND " +
                "${CalendarContract.Events.DESCRIPTION} = ? AND " +
                "${CalendarContract.Events.DTSTART} >= ? AND " +
                "${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(calendarId.toString(), EVENT_DESCRIPTION_TAG, todayStartMs.toString())

        resolver.query(CalendarContract.Events.CONTENT_URI, projection, selection, selectionArgs, null)?.use { c ->
            while (c.moveToNext()) {
                existingEvents.add(
                    ExistingEvent(
                        eventId = c.getLong(0),
                        title = c.getString(1) ?: "",
                        startMs = c.getLong(2),
                        endMs = c.getLong(3),
                        isAllDay = c.getInt(4) == 1
                    )
                )
            }
        }

        val unmatchedExisting = existingEvents.toMutableList()
        val detectedChanges = mutableListOf<CalendarChangeItem>()

        for (shift in shifts) {
            val newStartMs = if (shift.isAllDayLeave) {
                shift.start.toInstant(ZoneOffset.UTC).toEpochMilli()
            } else {
                shift.start.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            }
            val newEndMs = if (shift.isAllDayLeave) {
                shift.end.toInstant(ZoneOffset.UTC).toEpochMilli()
            } else {
                shift.end.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            }

            // Etsitään täysin identtinen tapahtuma
            val exactMatch = unmatchedExisting.firstOrNull {
                it.title == shift.title &&
                it.startMs == newStartMs &&
                it.endMs == newEndMs &&
                it.isAllDay == shift.isAllDayLeave
            }

            if (exactMatch != null) {
                unmatchedExisting.remove(exactMatch)
                continue
            }

            // Etsitään samalle päivälle osuva tapahtuma, jota on muokattu (esim. vuoro tai kellonaika vaihtunut)
            val sameDayMatch = unmatchedExisting.firstOrNull { ex ->
                ex.isAllDay == shift.isAllDayLeave && isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave)
            }

            if (sameDayMatch != null) {
                unmatchedExisting.remove(sameDayMatch)
                val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, sameDayMatch.eventId)
                val values = ContentValues().apply {
                    put(CalendarContract.Events.TITLE, shift.title)
                    put(CalendarContract.Events.ALL_DAY, if (shift.isAllDayLeave) 1 else 0)
                    put(CalendarContract.Events.EVENT_TIMEZONE, if (shift.isAllDayLeave) "UTC" else TimeZone.getDefault().id)
                    put(CalendarContract.Events.DTSTART, newStartMs)
                    put(CalendarContract.Events.DTEND, newEndMs)
                }
                resolver.update(uri, values, null, null)

                detectedChanges.add(
                    CalendarChangeItem(
                        id = UUID.randomUUID().toString(),
                        type = ChangeType.MODIFIED,
                        calendarId = calendarId,
                        eventId = sameDayMatch.eventId,
                        title = shift.title,
                        startMs = newStartMs,
                        endMs = newEndMs,
                        isAllDay = shift.isAllDayLeave,
                        prevTitle = sameDayMatch.title,
                        prevStartMs = sameDayMatch.startMs,
                        prevEndMs = sameDayMatch.endMs,
                        prevIsAllDay = sameDayMatch.isAllDay
                    )
                )
            } else {
                // Uusi tapahtuma lisätään
                val values = ContentValues().apply {
                    put(CalendarContract.Events.CALENDAR_ID, calendarId)
                    put(CalendarContract.Events.TITLE, shift.title)
                    put(CalendarContract.Events.DESCRIPTION, EVENT_DESCRIPTION_TAG)
                    put(CalendarContract.Events.ALL_DAY, if (shift.isAllDayLeave) 1 else 0)
                    put(CalendarContract.Events.EVENT_TIMEZONE, if (shift.isAllDayLeave) "UTC" else TimeZone.getDefault().id)
                    put(CalendarContract.Events.DTSTART, newStartMs)
                    put(CalendarContract.Events.DTEND, newEndMs)
                }
                val insertedUri = resolver.insert(CalendarContract.Events.CONTENT_URI, values)
                val newEventId = insertedUri?.lastPathSegment?.toLongOrNull()

                detectedChanges.add(
                    CalendarChangeItem(
                        id = UUID.randomUUID().toString(),
                        type = ChangeType.ADDED,
                        calendarId = calendarId,
                        eventId = newEventId,
                        title = shift.title,
                        startMs = newStartMs,
                        endMs = newEndMs,
                        isAllDay = shift.isAllDayLeave
                    )
                )
            }
        }

        // Poistetaan tapahtumat, jotka poistuivat työvuorolistalta
        for (removedEx in unmatchedExisting) {
            val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, removedEx.eventId)
            resolver.delete(uri, null, null)

            detectedChanges.add(
                CalendarChangeItem(
                    id = UUID.randomUUID().toString(),
                    type = ChangeType.REMOVED,
                    calendarId = calendarId,
                    eventId = null,
                    title = removedEx.title,
                    startMs = removedEx.startMs,
                    endMs = removedEx.endMs,
                    isAllDay = removedEx.isAllDay,
                    prevTitle = removedEx.title,
                    prevStartMs = removedEx.startMs,
                    prevEndMs = removedEx.endMs,
                    prevIsAllDay = removedEx.isAllDay
                )
            )
        }

        if (detectedChanges.isNotEmpty()) {
            CalendarChangeTracker.saveChanges(context, detectedChanges)
            ShiftReminderReceiver.showCalendarChangesNotification(context, detectedChanges)
        }

        return detectedChanges
    }

    private fun isSameCalendarDay(ms1: Long, ms2: Long, isAllDay: Boolean): Boolean {
        val zone = if (isAllDay) ZoneOffset.UTC else ZoneId.systemDefault()
        val d1 = Instant.ofEpochMilli(ms1).atZone(zone).toLocalDate()
        val d2 = Instant.ofEpochMilli(ms2).atZone(zone).toLocalDate()
        return d1 == d2
    }

    fun scheduleShiftReminders(context: Context, calendarId: Long) {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return
        }
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val minutesBefore = prefs.getInt("reminder_minutes", 30)

        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val now = System.currentTimeMillis()
        val twoWeeksAhead = now + 14L * 24 * 60 * 60 * 1000L
        val timeFmt = DateTimeFormatter.ofPattern("HH:mm")

        val projection = arrayOf(
            CalendarContract.Events.TITLE,
            CalendarContract.Events.DTSTART,
            CalendarContract.Events.DTEND,
            CalendarContract.Events.ALL_DAY
        )
        val selection = "${CalendarContract.Events.CALENDAR_ID} = ? AND " +
                "${CalendarContract.Events.DESCRIPTION} = ? AND " +
                "${CalendarContract.Events.DTEND} > ? AND " +
                "${CalendarContract.Events.DTSTART} < ? AND " +
                "${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(calendarId.toString(), EVENT_DESCRIPTION_TAG, now.toString(), twoWeeksAhead.toString())

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
                val endMs = cursor.getLong(2)
                val isAllDay = cursor.getInt(3) == 1

                if (isAllDay) continue

                val startTrigger = startMs - (minutesBefore * 60_000L)
                if (startTrigger > now) {
                    val startStr = Instant.ofEpochMilli(startMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                    setExactAlarmSafe(context, alarmManager, startTrigger, title, startStr, isEnding = false)
                }

                val endTrigger = endMs - (minutesBefore * 60_000L)
                if (endTrigger > now) {
                    val endStr = Instant.ofEpochMilli(endMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                    setExactAlarmSafe(context, alarmManager, endTrigger, title, endStr, isEnding = true)
                }
            }
        }
    }

    private fun setExactAlarmSafe(
        context: Context,
        alarmManager: AlarmManager,
        triggerMs: Long,
        title: String,
        timeStr: String,
        isEnding: Boolean
    ) {
        val reqCode = ((triggerMs / 60_000L) + if (isEnding) 1 else 0).toInt()
        val intent = Intent(context, ShiftReminderReceiver::class.java).apply {
            putExtra("SHIFT_TITLE", title)
            putExtra("SHIFT_TIME", timeStr)
            putExtra("IS_ENDING", isEnding)
        }
        val pi = PendingIntent.getBroadcast(
            context,
            reqCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !alarmManager.canScheduleExactAlarms()) {
                alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerMs, pi)
            } else {
                alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerMs, pi)
            }
        } catch (_: SecurityException) {
            alarmManager.set(AlarmManager.RTC_WAKEUP, triggerMs, pi)
        }
    }
}
