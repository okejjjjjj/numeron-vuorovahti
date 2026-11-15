package fi.numeron.vuorovahti

import android.Manifest
import android.app.AlarmManager
import android.app.PendingIntent
import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.provider.CalendarContract
import androidx.core.content.ContextCompat
import java.time.Instant
import java.time.LocalDateTime
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
        val location: String,
        val description: String,
        val colorKey: String?,
        val startMs: Long,
        val endMs: Long,
        val isAllDay: Boolean
    )

    private data class ShiftColorKeys(
        val greenKey: String?,
        val orangeKey: String?,
        val purpleKey: String?
    )

    fun getTargetCalendarId(context: Context): Long? {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val available = SettingsDialogHelper.getAvailableCalendars(context)
        val savedId = prefs.getLong("calendar_id", -1L)
        if (savedId > 0 && available.any { it.id == savedId }) return savedId

        val defaultGoogle = available.firstOrNull()
        if (defaultGoogle != null) {
            prefs.edit().putLong("calendar_id", defaultGoogle.id).apply()
        }
        return defaultGoogle?.id
    }

    private fun buildFullDescription(comment: String): String {
        val clean = comment.trim()
        return if (clean.isEmpty()) EVENT_DESCRIPTION_TAG else "$clean\n\n$EVENT_DESCRIPTION_TAG"
    }

    private fun resolveGoogleShiftColorKeys(context: Context, calendarId: Long): ShiftColorKeys {
        val resolver = context.contentResolver
        var accountName: String? = null
        var accountType: String? = null

        resolver.query(
            CalendarContract.Calendars.CONTENT_URI,
            arrayOf(CalendarContract.Calendars.ACCOUNT_NAME, CalendarContract.Calendars.ACCOUNT_TYPE),
            "${CalendarContract.Calendars._ID} = ?",
            arrayOf(calendarId.toString()),
            null
        )?.use { c ->
            if (c.moveToFirst()) {
                accountName = c.getString(0)
                accountType = c.getString(1)
            }
        }

        if (accountName.isNullOrEmpty() || accountType.isNullOrEmpty()) {
            return ShiftColorKeys(null, null, null)
        }

        val availableColors = mutableListOf<Pair<String, Int>>()
        resolver.query(
            CalendarContract.Colors.CONTENT_URI,
            arrayOf(CalendarContract.Colors.COLOR_KEY, CalendarContract.Colors.COLOR),
            "${CalendarContract.Colors.ACCOUNT_NAME} = ? AND ${CalendarContract.Colors.ACCOUNT_TYPE} = ? AND ${CalendarContract.Colors.COLOR_TYPE} = ?",
            arrayOf(accountName, accountType, CalendarContract.Colors.TYPE_EVENT.toString()),
            null
        )?.use { c ->
            while (c.moveToNext()) {
                val key = c.getString(0) ?: continue
                val colorInt = c.getInt(1)
                availableColors.add(key to colorInt)
            }
        }

        if (availableColors.isEmpty()) {
            return ShiftColorKeys(null, null, null)
        }

        fun findClosestKey(targetRgb: Int): String? {
            val tr = Color.red(targetRgb)
            val tg = Color.green(targetRgb)
            val tb = Color.blue(targetRgb)
            return availableColors.minByOrNull { (_, colorInt) ->
                val dr = Color.red(colorInt) - tr
                val dg = Color.green(colorInt) - tg
                val db = Color.blue(colorInt) - tb
                dr * dr + dg * dg + db * db
            }?.first
        }

        // Google Calendarin tapahtumavärien tavoitesävyt: vihreä (Basil/Sage), oranssi (Tangerine), lila (Grape)
        val greenKey = findClosestKey(Color.rgb(11, 128, 67))
        val orangeKey = findClosestKey(Color.rgb(244, 81, 30))
        val purpleKey = findClosestKey(Color.rgb(142, 36, 170))
        return ShiftColorKeys(greenKey, orangeKey, purpleKey)
    }

    private fun pickColorKeyForShift(shift: WorkShift, keys: ShiftColorKeys): String? {
        if (shift.isAllDayLeave) return null
        val startMinutes = shift.start.hour * 60 + shift.start.minute
        val endMinutes = shift.end.hour * 60 + shift.end.minute
        val crossesMidnight = shift.end.toLocalDate().isAfter(shift.start.toLocalDate()) || endMinutes < startMinutes

        return when {
            crossesMidnight || startMinutes >= 20 * 60 || startMinutes < 4 * 60 -> keys.purpleKey // Lila (yö)
            startMinutes >= 11 * 60 + 30 -> keys.orangeKey                                        // Oranssi (ilta)
            else -> keys.greenKey                                                                  // Vihreä (aamu)
        }
    }

    fun syncShiftsToCalendar(context: Context, calendarId: Long, shifts: List<WorkShift>): List<CalendarChangeItem> {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_CALENDAR) != PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return emptyList()
        }

        val resolver = context.contentResolver
        val now = LocalDateTime.now()
        val nowMs = now.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
        val colorKeys = resolveGoogleShiftColorKeys(context, calendarId)

        // Suodatetaan pois menneet ja meneillään olevat vuorot
        val upcomingShifts = shifts.filter { it.start.isAfter(now) }

        // 1. Haetaan olemassa olevat sovelluksen synkronoimat tulevat tapahtumat vertailua varten
        val existingEvents = mutableListOf<ExistingEvent>()
        val projection = arrayOf(
            CalendarContract.Events._ID,
            CalendarContract.Events.TITLE,
            CalendarContract.Events.EVENT_LOCATION,
            CalendarContract.Events.DESCRIPTION,
            CalendarContract.Events.EVENT_COLOR_KEY,
            CalendarContract.Events.DTSTART,
            CalendarContract.Events.DTEND,
            CalendarContract.Events.ALL_DAY
        )
        val selection = "${CalendarContract.Events.CALENDAR_ID} = ? AND " +
                "${CalendarContract.Events.DESCRIPTION} LIKE ? AND " +
                "${CalendarContract.Events.DTSTART} > ? AND " +
                "${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(calendarId.toString(), "%$EVENT_DESCRIPTION_TAG%", nowMs.toString())

        resolver.query(CalendarContract.Events.CONTENT_URI, projection, selection, selectionArgs, null)?.use { c ->
            while (c.moveToNext()) {
                existingEvents.add(
                    ExistingEvent(
                        eventId = c.getLong(0),
                        title = c.getString(1) ?: "",
                        location = c.getString(2) ?: "",
                        description = c.getString(3) ?: "",
                        colorKey = c.getString(4),
                        startMs = c.getLong(5),
                        endMs = c.getLong(6),
                        isAllDay = c.getInt(7) == 1
                    )
                )
            }
        }

        val unmatchedExisting = existingEvents.toMutableList()
        val detectedChanges = mutableListOf<CalendarChangeItem>()

        for (shift in upcomingShifts) {
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
            val fullDescription = buildFullDescription(shift.description)
            val desiredColorKey = pickColorKeyForShift(shift, colorKeys)

            // Etsitään täysin identtinen tapahtuma
            val exactMatch = unmatchedExisting.firstOrNull {
                it.title == shift.title &&
                it.location == shift.location &&
                it.description == fullDescription &&
                it.colorKey == desiredColorKey &&
                it.startMs == newStartMs &&
                it.endMs == newEndMs &&
                it.isAllDay == shift.isAllDayLeave
            }

            if (exactMatch != null) {
                unmatchedExisting.remove(exactMatch)
                continue
            }

            // Etsitään samalle päivälle osuva tapahtuma, jota on muokattu
            val sameDayMatch = unmatchedExisting.firstOrNull { ex ->
                ex.isAllDay == shift.isAllDayLeave && isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave)
            }

            if (sameDayMatch != null) {
                unmatchedExisting.remove(sameDayMatch)
                val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, sameDayMatch.eventId)
                val values = ContentValues().apply {
                    put(CalendarContract.Events.TITLE, shift.title)
                    put(CalendarContract.Events.EVENT_LOCATION, shift.location)
                    put(CalendarContract.Events.DESCRIPTION, fullDescription)
                    if (desiredColorKey != null) {
                        put(CalendarContract.Events.EVENT_COLOR_KEY, desiredColorKey)
                    } else {
                        putNull(CalendarContract.Events.EVENT_COLOR_KEY)
                    }
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
                    put(CalendarContract.Events.EVENT_LOCATION, shift.location)
                    put(CalendarContract.Events.DESCRIPTION, fullDescription)
                    if (desiredColorKey != null) {
                        put(CalendarContract.Events.EVENT_COLOR_KEY, desiredColorKey)
                    }
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

        // Poistetaan tulevat tapahtumat, jotka poistuivat työvuorolistalta
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
            CalendarContract.Events.DESCRIPTION,
            CalendarContract.Events.DTSTART,
            CalendarContract.Events.DTEND,
            CalendarContract.Events.ALL_DAY
        )
        val selection = "${CalendarContract.Events.CALENDAR_ID} = ? AND " +
                "${CalendarContract.Events.DESCRIPTION} LIKE ? AND " +
                "${CalendarContract.Events.DTEND} > ? AND " +
                "${CalendarContract.Events.DTSTART} < ? AND " +
                "${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(calendarId.toString(), "%$EVENT_DESCRIPTION_TAG%", now.toString(), twoWeeksAhead.toString())

        context.contentResolver.query(
            CalendarContract.Events.CONTENT_URI,
            projection,
            selection,
            selectionArgs,
            "${CalendarContract.Events.DTSTART} ASC"
        )?.use { cursor ->
            while (cursor.moveToNext()) {
                val baseTitle = cursor.getString(0) ?: continue
                val desc = cursor.getString(1) ?: ""
                val shiftRoleInfo = desc.substringBefore(EVENT_DESCRIPTION_TAG).trim()
                val displayTitle = if (shiftRoleInfo.isNotEmpty()) "$baseTitle ($shiftRoleInfo)" else baseTitle
                val startMs = cursor.getLong(2)
                val endMs = cursor.getLong(3)
                val isAllDay = cursor.getInt(4) == 1

                if (isAllDay) continue

                val startTrigger = startMs - (minutesBefore * 60_000L)
                if (startTrigger > now) {
                    val startStr = Instant.ofEpochMilli(startMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                    setExactAlarmSafe(context, alarmManager, startTrigger, displayTitle, startStr, isEnding = false)
                }

                val endTrigger = endMs - (minutesBefore * 60_000L)
                if (endTrigger > now) {
                    val endStr = Instant.ofEpochMilli(endMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                    setExactAlarmSafe(context, alarmManager, endTrigger, displayTitle, endStr, isEnding = true)
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
