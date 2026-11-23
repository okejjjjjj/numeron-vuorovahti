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
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.TimeZone
import java.util.UUID

object CalendarSyncHelper {

    const val EVENT_DESCRIPTION_TAG = "Synkronoitu Numeron Vuorovahti -sovelluksesta"
    private val syncLock = Any()

    private val KNOWN_SHIFT_OR_LEAVE_KEYWORDS = listOf(
        "työvuoro", "vuoro", "aamuvuoro", "iltavuoro", "yövuoro", "päivävuoro", "välivuoro",
        "loma", "vuosiloma", "talviloma", "kesäloma", "poissaolo", "vapaa", "koulutus",
        "sairausloma", "isyysvapaa", "vanhempainvapaa", "saldovapaa", "arkipyhä"
    )

    private data class ExistingEvent(
        val eventId: Long,
        val title: String,
        val location: String,
        val description: String,
        val colorKey: String?,
        val startMs: Long,
        val endMs: Long,
        val isAllDay: Boolean,
        val isOwnedByApp: Boolean
    )

    private data class PreparedShift(
        val shift: WorkShift,
        val newStartMs: Long,
        val newEndMs: Long,
        val desiredTitle: String,
        val fullDescription: String,
        val desiredColorKey: String?
    )

    private data class ShiftColorKeys(
        val greenKey: String?,
        val orangeKey: String?,
        val purpleKey: String?
    )

    private data class ReminderEventItem(
        val displayTitle: String,
        val startMs: Long,
        val endMs: Long
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

    private fun getUserTag(context: Context): String {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        return (prefs.getString("calendar_user_tag", "") ?: "").trim()
    }

    private fun formatShiftTitle(baseTitle: String, userTag: String): String {
        return if (userTag.isNotEmpty()) "$baseTitle ($userTag)" else baseTitle
    }

    private fun buildUserTagSuffix(userTag: String): String {
        return if (userTag.isNotEmpty()) "$EVENT_DESCRIPTION_TAG [$userTag]" else EVENT_DESCRIPTION_TAG
    }

    private fun buildFullDescription(comment: String, userTag: String): String {
        val clean = comment.trim()
        val tagLine = buildUserTagSuffix(userTag)
        return if (clean.isEmpty()) tagLine else "$clean\n\n$tagLine"
    }

    private fun resolveGoogleShiftColorKeys(context: Context, calendarId: Long): ShiftColorKeys {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val morningRgb = prefs.getInt("color_morning_rgb", SettingsDialogHelper.DEFAULT_MORNING_RGB)
        val eveningRgb = prefs.getInt("color_evening_rgb", SettingsDialogHelper.DEFAULT_EVENING_RGB)
        val nightRgb = prefs.getInt("color_night_rgb", SettingsDialogHelper.DEFAULT_NIGHT_RGB)
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

        val greenKey = findClosestKey(morningRgb)
        val orangeKey = findClosestKey(eveningRgb)
        val purpleKey = findClosestKey(nightRgb)
        return ShiftColorKeys(greenKey, orangeKey, purpleKey)
    }

    private fun pickColorKeyForShift(shift: WorkShift, keys: ShiftColorKeys): String? {
        if (shift.isAllDayLeave) return null
        val startMinutes = shift.start.hour * 60 + shift.start.minute
        val endMinutes = shift.end.hour * 60 + shift.end.minute
        val crossesMidnight = shift.end.toLocalDate().isAfter(shift.start.toLocalDate()) || endMinutes < startMinutes

        return when {
            crossesMidnight || startMinutes >= 20 * 60 || startMinutes < 4 * 60 -> keys.purpleKey
            startMinutes >= 11 * 60 + 30 -> keys.orangeKey
            else -> keys.greenKey
        }
    }

    private fun belongsToCurrentUser(description: String, title: String, userTag: String): Boolean {
        if (!description.contains(EVENT_DESCRIPTION_TAG)) return false
        if (userTag.isEmpty()) {
            val bracketRegex = Regex("Synkronoitu Numeron Vuorovahti -sovelluksesta\\s*\\[.+?]")
            return !bracketRegex.containsMatchIn(description)
        }
        return description.contains("[$userTag]", ignoreCase = true) ||
               title.endsWith("($userTag)", ignoreCase = true)
    }

    private fun belongsToAnotherUser(description: String, userTag: String): Boolean {
        if (!description.contains(EVENT_DESCRIPTION_TAG)) return false
        val match = Regex("Synkronoitu Numeron Vuorovahti -sovelluksesta\\s*\\[(.+?)]").find(description)
        if (match != null) {
            val owner = match.groupValues[1].trim()
            return !owner.equals(userTag, ignoreCase = true)
        }
        return userTag.isNotEmpty()
    }

    private fun looksLikeShiftOrLeave(title: String, desiredTitle: String, userTag: String): Boolean {
        val lower = title.lowercase().trim()
        if (userTag.isNotEmpty() && !lower.contains(userTag.lowercase())) {
            return false
        }
        if (lower == desiredTitle.lowercase() || lower.startsWith("työvuoro")) return true
        return KNOWN_SHIFT_OR_LEAVE_KEYWORDS.any { kw ->
            lower == kw || lower.startsWith("$kw ") || lower.startsWith("$kw(") || lower.startsWith("$kw-")
        }
    }

    fun syncShiftsToCalendar(
        context: Context,
        calendarId: Long,
        shifts: List<WorkShift>
    ): List<CalendarChangeItem> = synchronized(syncLock) {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_CALENDAR) != PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return@synchronized emptyList()
        }

        val resolver = context.contentResolver
        val now = LocalDateTime.now()
        val today = now.toLocalDate()
        val nowMs = now.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
        val todayStartUtcMs = today.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli()
        val queryMinEndMs = minOf(nowMs, todayStartUtcMs)
        val colorKeys = resolveGoogleShiftColorKeys(context, calendarId)
        val userTag = getUserTag(context)

        // Jo alkaneita työvuoroja ei ylikirjoiteta toteutuneilla leimausajoilla;
        // koko päivän lomat suodatetaan paikallisen päivän ja UTC-keskiyön mukaan.
        val upcomingShifts = shifts.filter { shift ->
            if (shift.isAllDayLeave) shift.end.toLocalDate().isAfter(today) else shift.start.isAfter(now)
        }

        val ownedEvents = mutableListOf<ExistingEvent>()
        val unownedCandidateEvents = mutableListOf<ExistingEvent>()

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
                "${CalendarContract.Events.DTEND} > ? AND " +
                "${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(calendarId.toString(), queryMinEndMs.toString())

        resolver.query(CalendarContract.Events.CONTENT_URI, projection, selection, selectionArgs, null)?.use { c ->
            while (c.moveToNext()) {
                val id = c.getLong(0)
                val title = c.getString(1) ?: ""
                val loc = c.getString(2) ?: ""
                val desc = c.getString(3) ?: ""
                val cKey = c.getString(4)
                val sMs = c.getLong(5)
                val eMs = c.getLong(6)
                val allDay = c.getInt(7) == 1

                if (allDay && eMs <= todayStartUtcMs) continue
                if (!allDay && eMs <= nowMs) continue

                if (belongsToAnotherUser(desc, userTag)) {
                    continue
                }

                val owned = belongsToCurrentUser(desc, title, userTag)
                val ev = ExistingEvent(id, title, loc, desc, cKey, sMs, eMs, allDay, owned)
                if (owned) {
                    ownedEvents.add(ev)
                } else {
                    unownedCandidateEvents.add(ev)
                }
            }
        }

        val unmatchedOwned = ownedEvents.toMutableList()
        val unmatchedExternal = unownedCandidateEvents.toMutableList()
        val detectedChanges = mutableListOf<CalendarChangeItem>()

        val preparedShifts = upcomingShifts.map { shift ->
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
            PreparedShift(
                shift = shift,
                newStartMs = newStartMs,
                newEndMs = newEndMs,
                desiredTitle = formatShiftTitle(shift.title, userTag),
                fullDescription = buildFullDescription(shift.description, userTag),
                desiredColorKey = pickColorKeyForShift(shift, colorKeys)
            )
        }

        // Vaihe 1: Tarkat osumat ja kattavat koko päivän lomat pois ennen saman päivän täsmäytystä
        val pendingShifts = mutableListOf<PreparedShift>()
        for (prep in preparedShifts) {
            val shift = prep.shift
            val exactMatch = unmatchedOwned.firstOrNull {
                it.title == prep.desiredTitle &&
                it.location == shift.location &&
                it.description == prep.fullDescription &&
                it.colorKey == prep.desiredColorKey &&
                it.startMs == prep.newStartMs &&
                it.endMs == prep.newEndMs &&
                it.isAllDay == shift.isAllDayLeave
            }
            if (exactMatch != null) {
                unmatchedOwned.remove(exactMatch)
                continue
            }

            if (shift.isAllDayLeave) {
                val coveringOwned = unmatchedOwned.firstOrNull { ex ->
                    ex.isAllDay &&
                    ex.title.equals(prep.desiredTitle, ignoreCase = true) &&
                    ex.startMs < prep.newStartMs &&
                    ex.endMs == prep.newEndMs
                }
                if (coveringOwned != null) {
                    unmatchedOwned.remove(coveringOwned)
                    continue
                }
                val coveringExternal = unmatchedExternal.firstOrNull { ex ->
                    ex.isAllDay &&
                    ex.title.equals(prep.desiredTitle, ignoreCase = true) &&
                    ex.startMs < prep.newStartMs &&
                    ex.endMs == prep.newEndMs
                }
                if (coveringExternal != null) {
                    unmatchedExternal.remove(coveringExternal)
                    continue
                }
            }

            pendingShifts.add(prep)
        }

        // Vaihe 2: Saman päivän täsmäytys (lähimmän aloitusajan mukaan) sekä uusien lisäys
        for (prep in pendingShifts) {
            val shift = prep.shift
            val newStartMs = prep.newStartMs
            val newEndMs = prep.newEndMs
            val desiredTitle = prep.desiredTitle
            val fullDescription = prep.fullDescription
            val desiredColorKey = prep.desiredColorKey

            val sameDayOwned = unmatchedOwned
                .filter { ex ->
                    ex.isAllDay == shift.isAllDayLeave &&
                    isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave) &&
                    (!shift.isAllDayLeave || ex.title.equals(desiredTitle, ignoreCase = true) || ex.startMs == newStartMs)
                }
                .minByOrNull { kotlin.math.abs(it.startMs - newStartMs) }
                ?: unmatchedOwned.firstOrNull { ex ->
                    shift.isAllDayLeave &&
                    ex.isAllDay &&
                    ex.title.equals(desiredTitle, ignoreCase = true) &&
                    ex.startMs < newStartMs &&
                    ex.endMs > newStartMs
                }
                ?: unmatchedOwned
                    .filter { ex ->
                        ex.isAllDay == shift.isAllDayLeave && isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave)
                    }
                    .minByOrNull { kotlin.math.abs(it.startMs - newStartMs) }

            val sameDayExternal = if (sameDayOwned == null) {
                unmatchedExternal
                    .filter { ex ->
                        ex.isAllDay == shift.isAllDayLeave &&
                        isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave) &&
                        looksLikeShiftOrLeave(ex.title, desiredTitle, userTag)
                    }
                    .minByOrNull { kotlin.math.abs(it.startMs - newStartMs) }
            } else {
                null
            }

            val targetMatch = sameDayOwned ?: sameDayExternal

            if (targetMatch != null) {
                if (sameDayOwned != null) {
                    unmatchedOwned.remove(sameDayOwned)
                } else if (sameDayExternal != null) {
                    unmatchedExternal.remove(sameDayExternal)
                }

                val effectiveStartMs = if (shift.isAllDayLeave && targetMatch.startMs < newStartMs) {
                    targetMatch.startMs
                } else {
                    newStartMs
                }
                val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, targetMatch.eventId)
                val values = ContentValues().apply {
                    put(CalendarContract.Events.TITLE, desiredTitle)
                    put(CalendarContract.Events.EVENT_LOCATION, shift.location)
                    put(CalendarContract.Events.DESCRIPTION, fullDescription)
                    if (desiredColorKey != null) {
                        put(CalendarContract.Events.EVENT_COLOR_KEY, desiredColorKey)
                    } else {
                        putNull(CalendarContract.Events.EVENT_COLOR_KEY)
                    }
                    put(CalendarContract.Events.ALL_DAY, if (shift.isAllDayLeave) 1 else 0)
                    put(CalendarContract.Events.EVENT_TIMEZONE, if (shift.isAllDayLeave) "UTC" else TimeZone.getDefault().id)
                    put(CalendarContract.Events.DTSTART, effectiveStartMs)
                    put(CalendarContract.Events.DTEND, newEndMs)
                }
                resolver.update(uri, values, null, null)

                val contentChanged =
                    targetMatch.title != desiredTitle ||
                    targetMatch.location != shift.location ||
                    targetMatch.description != fullDescription ||
                    targetMatch.startMs != effectiveStartMs ||
                    targetMatch.endMs != newEndMs ||
                    targetMatch.isAllDay != shift.isAllDayLeave

                if (contentChanged) {
                    detectedChanges.add(
                        CalendarChangeItem(
                            id = UUID.randomUUID().toString(),
                            type = ChangeType.MODIFIED,
                            calendarId = calendarId,
                            eventId = targetMatch.eventId,
                            title = desiredTitle,
                            startMs = effectiveStartMs,
                            endMs = newEndMs,
                            isAllDay = shift.isAllDayLeave,
                            location = shift.location,
                            description = fullDescription,
                            prevTitle = targetMatch.title,
                            prevStartMs = targetMatch.startMs,
                            prevEndMs = targetMatch.endMs,
                            prevIsAllDay = targetMatch.isAllDay,
                            prevLocation = targetMatch.location,
                            prevDescription = targetMatch.description
                        )
                    )
                }
            } else {
                val values = ContentValues().apply {
                    put(CalendarContract.Events.CALENDAR_ID, calendarId)
                    put(CalendarContract.Events.TITLE, desiredTitle)
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
                        title = desiredTitle,
                        startMs = newStartMs,
                        endMs = newEndMs,
                        isAllDay = shift.isAllDayLeave,
                        location = shift.location,
                        description = fullDescription
                    )
                )
            }
        }

        for (removedEx in unmatchedOwned) {
            val alreadyStarted = if (removedEx.isAllDay) {
                removedEx.startMs <= todayStartUtcMs
            } else {
                removedEx.startMs <= nowMs
            }
            if (alreadyStarted) continue
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
                    location = removedEx.location,
                    description = removedEx.description,
                    prevTitle = removedEx.title,
                    prevStartMs = removedEx.startMs,
                    prevEndMs = removedEx.endMs,
                    prevIsAllDay = removedEx.isAllDay,
                    prevLocation = removedEx.location,
                    prevDescription = removedEx.description
                )
            )
        }

        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putLong("last_calendar_sync_ms", System.currentTimeMillis())
            .apply()

        if (detectedChanges.isNotEmpty()) {
            CalendarChangeTracker.mergeChanges(context, detectedChanges)
        }

        detectedChanges
    }

    private fun isSameCalendarDay(ms1: Long, ms2: Long, isAllDay: Boolean): Boolean {
        val zone = if (isAllDay) ZoneOffset.UTC else ZoneId.systemDefault()
        val d1 = Instant.ofEpochMilli(ms1).atZone(zone).toLocalDate()
        val d2 = Instant.ofEpochMilli(ms2).atZone(zone).toLocalDate()
        return d1 == d2
    }

    fun saveCachedShifts(context: Context, shifts: List<WorkShift>) {
        val zone = ZoneId.systemDefault()
        val arr = JSONArray()
        for (shift in shifts) {
            val obj = JSONObject().apply {
                put("title", shift.title)
                put("startMs", shift.start.atZone(zone).toInstant().toEpochMilli())
                put("endMs", shift.end.atZone(zone).toInstant().toEpochMilli())
                put("isAllDayLeave", shift.isAllDayLeave)
                put("location", shift.location)
                put("description", shift.description)
            }
            arr.put(obj)
        }
        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putString("cached_work_shifts_json", arr.toString())
            .apply()
    }

    fun hasCachedShifts(context: Context): Boolean {
        val raw = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .getString("cached_work_shifts_json", null)
        return !raw.isNullOrBlank()
    }

    private fun loadCachedShifts(context: Context): List<WorkShift>? {
        val raw = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .getString("cached_work_shifts_json", null) ?: return null
        return try {
            val zone = ZoneId.systemDefault()
            val arr = JSONArray(raw)
            val list = ArrayList<WorkShift>(arr.length())
            for (i in 0 until arr.length()) {
                val obj = arr.getJSONObject(i)
                val startMs = obj.getLong("startMs")
                val endMs = obj.getLong("endMs")
                list.add(
                    WorkShift(
                        title = obj.optString("title", "Työvuoro"),
                        start = Instant.ofEpochMilli(startMs).atZone(zone).toLocalDateTime(),
                        end = Instant.ofEpochMilli(endMs).atZone(zone).toLocalDateTime(),
                        isAllDayLeave = obj.optBoolean("isAllDayLeave", false),
                        location = obj.optString("location", ""),
                        description = obj.optString("description", "")
                    )
                )
            }
            list
        } catch (_: Exception) {
            null
        }
    }

    fun countFutureSyncedEvents(context: Context, calendarId: Long): Int {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return 0
        }
        val nowMs = System.currentTimeMillis()
        val userTag = getUserTag(context)
        var count = 0
        val projection = arrayOf(
            CalendarContract.Events.TITLE,
            CalendarContract.Events.DESCRIPTION
        )
        val selection = "${CalendarContract.Events.CALENDAR_ID} = ? AND " +
                "${CalendarContract.Events.DTEND} > ? AND " +
                "${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(calendarId.toString(), nowMs.toString())

        context.contentResolver.query(CalendarContract.Events.CONTENT_URI, projection, selection, selectionArgs, null)?.use { c ->
            while (c.moveToNext()) {
                val title = c.getString(0) ?: ""
                val desc = c.getString(1) ?: ""
                if (belongsToAnotherUser(desc, userTag)) continue
                if (belongsToCurrentUser(desc, title, userTag)) {
                    count++
                }
            }
        }
        return count
    }

    fun deleteFutureSyncedEvents(context: Context, calendarId: Long): Int {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_CALENDAR) != PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return 0
        }
        val resolver = context.contentResolver
        val nowMs = System.currentTimeMillis()
        val userTag = getUserTag(context)
        val toDeleteIds = mutableListOf<Long>()

        val projection = arrayOf(
            CalendarContract.Events._ID,
            CalendarContract.Events.TITLE,
            CalendarContract.Events.DESCRIPTION
        )
        val selection = "${CalendarContract.Events.CALENDAR_ID} = ? AND " +
                "${CalendarContract.Events.DTEND} > ? AND " +
                "${CalendarContract.Events.DELETED} = 0"
        val selectionArgs = arrayOf(calendarId.toString(), nowMs.toString())

        resolver.query(CalendarContract.Events.CONTENT_URI, projection, selection, selectionArgs, null)?.use { c ->
            while (c.moveToNext()) {
                val id = c.getLong(0)
                val title = c.getString(1) ?: ""
                val desc = c.getString(2) ?: ""
                if (belongsToAnotherUser(desc, userTag)) continue
                if (belongsToCurrentUser(desc, title, userTag)) {
                    toDeleteIds.add(id)
                }
            }
        }

        for (id in toDeleteIds) {
            val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, id)
            resolver.delete(uri, null, null)
        }
        if (toDeleteIds.isNotEmpty()) {
            CalendarChangeTracker.saveChanges(context, emptyList())
            scheduleShiftReminders(context, calendarId)
        }
        return toDeleteIds.size
    }

    fun cancelAllShiftReminders(context: Context) {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val oldReqCodes = prefs.getStringSet("scheduled_alarm_req_codes", emptySet()) ?: emptySet()
        for (oldCodeStr in oldReqCodes) {
            val oldCode = oldCodeStr.toIntOrNull() ?: continue
            val cancelIntent = Intent(context, ShiftReminderReceiver.InternalReceiver::class.java).apply {
                action = ShiftReminderReceiver.ACTION_SHIFT_REMINDER
            }
            val existingPi = PendingIntent.getBroadcast(
                context,
                oldCode,
                cancelIntent,
                PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE
            )
            if (existingPi != null) {
                alarmManager.cancel(existingPi)
                existingPi.cancel()
            }
        }
        prefs.edit()
            .remove("scheduled_alarm_req_codes")
            .remove("next_reminder_ms")
            .remove("next_reminder_label")
            .apply()
    }

    fun scheduleShiftReminders(context: Context, calendarId: Long? = getTargetCalendarId(context)) {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        if (!prefs.getBoolean("shift_reminders_enabled", true)) {
            cancelAllShiftReminders(context)
            return
        }

        val minutesBefore = prefs.getInt("reminder_minutes", 30)
        val userTag = getUserTag(context)
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val now = System.currentTimeMillis()
        val twoWeeksAhead = now + 14L * 24 * 60 * 60 * 1000L
        val timeFmt = DateTimeFormatter.ofPattern("HH:mm")
        val zone = ZoneId.systemDefault()

        val userShifts = mutableListOf<ReminderEventItem>()
        val cachedShifts = loadCachedShifts(context)

        if (cachedShifts != null) {
            for (shift in cachedShifts) {
                if (shift.isAllDayLeave) continue
                val startMs = shift.start.atZone(zone).toInstant().toEpochMilli()
                val endMs = shift.end.atZone(zone).toInstant().toEpochMilli()
                if (endMs <= now || startMs >= twoWeeksAhead) continue

                val baseTitle = formatShiftTitle(shift.title, userTag)
                val shiftRoleInfo = shift.description.substringBefore(EVENT_DESCRIPTION_TAG).lineSequence().firstOrNull()?.trim().orEmpty()
                val displayTitle = if (shiftRoleInfo.isNotEmpty()) "$baseTitle ($shiftRoleInfo)" else baseTitle
                userShifts.add(ReminderEventItem(displayTitle, startMs, endMs))
            }
        } else if (calendarId != null &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) == PackageManager.PERMISSION_GRANTED
        ) {
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
                    val startMs = cursor.getLong(2)
                    val endMs = cursor.getLong(3)
                    val isAllDay = cursor.getInt(4) == 1

                    if (isAllDay) continue
                    if (!belongsToCurrentUser(desc, baseTitle, userTag)) continue

                    val shiftRoleInfo = desc.substringBefore(EVENT_DESCRIPTION_TAG).lineSequence().firstOrNull()?.trim().orEmpty()
                    val displayTitle = if (shiftRoleInfo.isNotEmpty()) "$baseTitle ($shiftRoleInfo)" else baseTitle
                    userShifts.add(ReminderEventItem(displayTitle, startMs, endMs))
                }
            }
        }

        val sortedShifts = userShifts.sortedBy { it.startMs }
        val maxGapMs = 15L * 60_000L
        var earliestNextTriggerMs = Long.MAX_VALUE
        var earliestNextLabel = ""
        val newReqCodes = mutableSetOf<String>()

        for (i in sortedShifts.indices) {
            val current = sortedShifts[i]
            val prev = if (i > 0) sortedShifts[i - 1] else null
            val next = if (i < sortedShifts.lastIndex) sortedShifts[i + 1] else null

            val continuesFromPrev = prev != null && (current.startMs - prev.endMs) in (-maxGapMs)..maxGapMs
            val continuesToNext = next != null && (next.startMs - current.endMs) in (-maxGapMs)..maxGapMs

            if (!continuesFromPrev) {
                val startTrigger = current.startMs - (minutesBefore * 60_000L)
                val startStr = Instant.ofEpochMilli(current.startMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                if (startTrigger > now) {
                    val code = setExactAlarmSafe(
                        context,
                        alarmManager,
                        startTrigger,
                        current.displayTitle,
                        startStr,
                        isEnding = false,
                        shiftStartMs = current.startMs
                    )
                    newReqCodes.add(code.toString())
                    if (startTrigger < earliestNextTriggerMs) {
                        earliestNextTriggerMs = startTrigger
                        earliestNextLabel = "Sisään (${current.displayTitle}, vuoro klo $startStr)"
                    }
                } else if (now <= current.startMs + 10L * 60_000L && current.endMs - now > 30L * 60_000L) {
                    // Vuoro on alkamassa hetken kuluttua tai juuri alkanut eikä sisäänleimausmuistutusta ole vielä lähetetty
                    val alreadyNotifiedStart = prefs.getLong("notified_ongoing_start_ms", 0L)
                    if (alreadyNotifiedStart != current.startMs) {
                        prefs.edit().putLong("notified_ongoing_start_ms", current.startMs).apply()
                        ShiftReminderReceiver().showReminderNotification(
                            context = context,
                            shiftTitle = current.displayTitle,
                            timeStr = startStr,
                            isEnding = false,
                            rescheduleNext = false
                        )
                    }
                }
            }

            if (!continuesToNext) {
                val endTrigger = current.endMs - (minutesBefore * 60_000L)
                if (endTrigger > now) {
                    val endStr = Instant.ofEpochMilli(current.endMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                    val code = setExactAlarmSafe(context, alarmManager, endTrigger, current.displayTitle, endStr, isEnding = true)
                    newReqCodes.add(code.toString())
                    if (endTrigger < earliestNextTriggerMs) {
                        earliestNextTriggerMs = endTrigger
                        earliestNextLabel = "Ulos (${current.displayTitle}, päättyy klo $endStr)"
                    }
                }
            }
        }

        val oldReqCodes = prefs.getStringSet("scheduled_alarm_req_codes", emptySet()) ?: emptySet()
        for (oldCodeStr in oldReqCodes) {
            if (oldCodeStr !in newReqCodes) {
                val oldCode = oldCodeStr.toIntOrNull() ?: continue
                val cancelIntent = Intent(context, ShiftReminderReceiver.InternalReceiver::class.java).apply {
                    action = ShiftReminderReceiver.ACTION_SHIFT_REMINDER
                }
                val existingPi = PendingIntent.getBroadcast(
                    context,
                    oldCode,
                    cancelIntent,
                    PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE
                )
                if (existingPi != null) {
                    alarmManager.cancel(existingPi)
                    existingPi.cancel()
                }
            }
        }

        prefs.edit().apply {
            putStringSet("scheduled_alarm_req_codes", newReqCodes)
            if (earliestNextTriggerMs < Long.MAX_VALUE) {
                putLong("next_reminder_ms", earliestNextTriggerMs)
                putString("next_reminder_label", earliestNextLabel)
            } else {
                remove("next_reminder_ms")
                remove("next_reminder_label")
            }
        }.apply()
    }

    private fun setExactAlarmSafe(
        context: Context,
        alarmManager: AlarmManager,
        triggerMs: Long,
        title: String,
        timeStr: String,
        isEnding: Boolean,
        shiftStartMs: Long = 0L
    ): Int {
        val reqCode = ((triggerMs / 60_000L).toInt() * 2) + (if (isEnding) 1 else 0)
        val intent = Intent(context, ShiftReminderReceiver.InternalReceiver::class.java).apply {
            action = ShiftReminderReceiver.ACTION_SHIFT_REMINDER
            putExtra("SHIFT_TITLE", title)
            putExtra("SHIFT_TIME", timeStr)
            putExtra("IS_ENDING", isEnding)
            if (shiftStartMs > 0L) {
                putExtra("SHIFT_START_MS", shiftStartMs)
            }
        }
        val pi = PendingIntent.getBroadcast(
            context,
            reqCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        try {
            alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerMs, pi)
        } catch (_: SecurityException) {
            alarmManager.set(AlarmManager.RTC_WAKEUP, triggerMs, pi)
        }
        return reqCode
    }
}
