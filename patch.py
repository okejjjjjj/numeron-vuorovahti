import pathlib
import re

# ==============================================================================
# 1. MainActivity.kt (Sumea siirtymäefekti + pieni latausmerkki)
# ==============================================================================
main_file = pathlib.Path("app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt")
main_text = main_file.read_text(encoding="utf-8")

def replace_block(text: str, start_marker: str, end_marker: str, replacement: str) -> str:
    s = text.find(start_marker)
    assert s != -1, f"Puuttuva aloitusmerkki: {start_marker}"
    e = text.find(end_marker, s)
    assert e != -1, f"Puuttuva lopetusmerkki: {end_marker}"
    return text[:s] + replacement + text[e:]

extra_imports = [
    "import android.content.res.ColorStateList",
    "import android.graphics.RenderEffect",
    "import android.graphics.Shader",
    "import android.view.Gravity",
    "import android.view.ViewGroup",
    "import android.widget.FrameLayout",
    "import android.widget.ProgressBar",
]
for imp in extra_imports:
    if imp not in main_text:
        main_text = main_text.replace(
            "import android.graphics.Color",
            f"import android.graphics.Color\n{imp}"
        )

nav_start = (
    "    private var transitionOverlay: FrameLayout? = null"
    if "    private var transitionOverlay: FrameLayout? = null" in main_text
    else (
        "    private fun fadeWebViewOut()"
        if "    private fun fadeWebViewOut()" in main_text
        else "    private fun navigateToTab(tab: Tab)"
    )
)

new_transition_and_nav = r'''    private var transitionOverlay: FrameLayout? = null
    private var isTransitionActive: Boolean = false

    private fun ensureTransitionOverlay(): FrameLayout {
        transitionOverlay?.let { return it }
        val parent = webView.parent as ViewGroup
        val overlay = FrameLayout(this).apply {
            setBackgroundColor(Color.parseColor("#B80F1722"))
            alpha = 0f
            visibility = View.GONE
            isClickable = true
            isFocusable = true
        }
        val spinner = ProgressBar(this).apply {
            isIndeterminate = true
            indeterminateTintList = ColorStateList.valueOf(Color.parseColor("#38BDF8"))
        }
        val sizePx = (34 * resources.displayMetrics.density).toInt()
        val lp = FrameLayout.LayoutParams(sizePx, sizePx, Gravity.CENTER)
        overlay.addView(spinner, lp)
        parent.addView(
            overlay,
            ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        )
        transitionOverlay = overlay
        return overlay
    }

    private fun startBlurTransition() {
        val overlay = ensureTransitionOverlay()
        overlay.animate().cancel()
        if (!isTransitionActive) {
            isTransitionActive = true
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val radius = 22f * resources.displayMetrics.density
                webView.setRenderEffect(
                    RenderEffect.createBlurEffect(radius, radius, Shader.TileMode.CLAMP)
                )
            }
            overlay.visibility = View.VISIBLE
            overlay.animate()
                .alpha(1f)
                .setDuration(120L)
                .start()
        }
    }

    private fun endBlurTransition() {
        val overlay = transitionOverlay ?: return
        overlay.animate().cancel()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            webView.setRenderEffect(null)
        }
        overlay.animate()
            .alpha(0f)
            .setDuration(220L)
            .withEndAction {
                overlay.visibility = View.GONE
                isTransitionActive = false
            }
            .start()
    }

    private fun navigateToTab(tab: Tab) {
        currentTab = tab
        updateDemoBanner()

        when (tab) {
            Tab.STAMP -> setActiveTab(btnNavStamp)
            Tab.REQUESTS -> setActiveTab(btnNavRequests)
            Tab.SHIFTS -> setActiveTab(btnNavShifts)
        }

        startBlurTransition()

        if (DemoModeHelper.isDemoEnabled(this)) {
            val html = when (tab) {
                Tab.STAMP -> DemoModeHelper.getDemoStampingHtml(this)
                Tab.REQUESTS -> DemoModeHelper.getDemoRequestsHtml(this)
                Tab.SHIFTS -> DemoModeHelper.getDemoShiftsHtml(this)
            }
            webView.loadDataWithBaseURL("https://demo.local/", html, "text/html", "UTF-8", null)
        } else {
            val baseUrl = getBaseUrl()
            val url = when (tab) {
                Tab.STAMP -> "$baseUrl/WorktimeStamping"
                Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
                Tab.SHIFTS -> "$baseUrl/Calendar/Month"
            }
            webView.loadUrl(url)
        }
    }

'''
main_text = replace_block(main_text, nav_start, "    private fun setupBottomBar()", new_transition_and_nav)

main_text = main_text.replace("fadeWebViewOut()", "startBlurTransition()")
main_text = main_text.replace("fadeWebViewIn()", "endBlurTransition()")
main_text = main_text.replace(
    "                view?.postDelayed({\n                    endBlurTransition()\n                }, 70L)",
    "                val revealDelay = if (url.contains(\"/Calendar\", ignoreCase = true)) 160L else 80L\n                view?.postDelayed({\n                    endBlurTransition()\n                }, revealDelay)"
)

main_file.write_text(main_text, encoding="utf-8")

# ==============================================================================
# 2. NumeronParser.kt (Sijainti, vuoron nimitys ja toimenkuva + vain tulevat)
# ==============================================================================
parser_file = pathlib.Path("app/src/main/java/fi/numeron/vuorovahti/NumeronParser.kt")
new_parser_code = r'''package fi.numeron.vuorovahti

import org.jsoup.Jsoup
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.format.DateTimeFormatter

data class WorkShift(
    val title: String,
    val start: LocalDateTime,
    val end: LocalDateTime,
    val isAllDayLeave: Boolean = false,
    val location: String = "",
    val description: String = ""
)

object NumeronParser {

    private val finnishMonths = mapOf(
        "tammikuu" to 1, "helmikuu" to 2, "maaliskuu" to 3, "huhtikuu" to 4,
        "toukokuu" to 5, "kesäkuu" to 6, "heinäkuu" to 7, "elokuu" to 8,
        "syyskuu" to 9, "lokakuu" to 10, "marraskuu" to 11, "joulukuu" to 12
    )

    private data class ParsedShiftText(
        val location: String,
        val shiftName: String,
        val role: String
    )

    private fun parseShiftText(rawName: String): ParsedShiftText {
        val cleaned = rawName.trim().replace(Regex("^\\d+\\s*"), "").trim()
        val tokens = cleaned.split(Regex("\\s+")).filter { it.isNotBlank() }
        if (tokens.isEmpty()) {
            return ParsedShiftText(location = "", shiftName = "", role = "")
        }

        val shiftKeywords = setOf(
            "aamu", "aamuvuoro",
            "ilta", "iltavuoro",
            "yö", "yövuoro",
            "päivä", "päivävuoro",
            "väli", "välivuoro"
        )

        val firstKwIdx = tokens.indexOfFirst { it.lowercase() in shiftKeywords }
        return if (firstKwIdx != -1) {
            val location = tokens.subList(0, firstKwIdx).joinToString(" ")
            val remainder = tokens.subList(firstKwIdx, tokens.size)
            val lastKwOffset = remainder.indexOfLast { it.lowercase() in shiftKeywords }
            val shiftName = remainder.subList(0, lastKwOffset + 1).joinToString(" ")
                .replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
            val role = remainder.subList(lastKwOffset + 1, remainder.size).joinToString(" ")
                .replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
            ParsedShiftText(location = location, shiftName = shiftName, role = role)
        } else if (tokens.size >= 2) {
            val role = tokens.last().replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
            val location = tokens.dropLast(1).joinToString(" ")
            ParsedShiftText(location = location, shiftName = "", role = role)
        } else {
            ParsedShiftText(location = cleaned, shiftName = "", role = "")
        }
    }

    fun parseCalendarHtml(html: String): List<WorkShift> {
        val doc = Jsoup.parse(html)
        val shifts = mutableListOf<WorkShift>()

        val monthHeader = doc.selectFirst("#monthText")?.text()?.trim()?.lowercase() ?: return emptyList()
        val parts = monthHeader.split(" ")
        if (parts.size < 2) return emptyList()

        val currentMonth = finnishMonths[parts[0]] ?: return emptyList()
        val currentYear = parts[1].toIntOrNull() ?: return emptyList()
        val now = LocalDateTime.now()
        val today = now.toLocalDate()

        val dayCells = doc.select("table.month-table td.month-day")
        for (cell in dayCells) {
            if (cell.hasClass("past-day") || cell.hasClass("day-different-month")) continue

            val dayNum = cell.selectFirst(".dayNum")?.text()?.trim()?.toIntOrNull() ?: continue
            val date = LocalDate.of(currentYear, currentMonth, dayNum)

            if (date.isBefore(today)) continue

            cell.select(".month-item.work").forEach { item ->
                val timesText = item.selectFirst(".itemTimes")?.text()?.trim() ?: ""
                val rawNameText = item.selectFirst(".itemName")?.text()?.trim() ?: ""

                val timeParts = timesText.split("-").map { it.trim() }
                if (timeParts.size == 2) {
                    val startTime = LocalTime.parse(timeParts[0], DateTimeFormatter.ofPattern("H:mm"))
                    val endTime = LocalTime.parse(timeParts[1], DateTimeFormatter.ofPattern("H:mm"))

                    val startDateTime = LocalDateTime.of(date, startTime)
                    // Ei huomioida menneitä tai meneillään olevia vuoroja
                    if (!startDateTime.isAfter(now)) return@forEach

                    var endDate = date
                    if (endTime.isBefore(startTime)) {
                        endDate = date.plusDays(1)
                    }

                    val parsed = parseShiftText(rawNameText)
                    val comment = listOf(parsed.shiftName, parsed.role)
                        .filter { it.isNotBlank() }
                        .joinToString(" • ")

                    shifts.add(
                        WorkShift(
                            title = "Työvuoro",
                            start = startDateTime,
                            end = LocalDateTime.of(endDate, endTime),
                            isAllDayLeave = false,
                            location = parsed.location,
                            description = comment
                        )
                    )
                }
            }

            cell.select(".month-item.absence").forEach { item ->
                val nameText = item.selectFirst(".itemName")?.text()?.trim() ?: "Loma / Poissaolo"
                val leaveStart = date.atStartOfDay()
                if (!leaveStart.isAfter(now)) return@forEach

                shifts.add(
                    WorkShift(
                        title = nameText,
                        start = leaveStart,
                        end = date.plusDays(1).atStartOfDay(),
                        isAllDayLeave = true,
                        location = "",
                        description = ""
                    )
                )
            }
        }

        return mergeConsecutiveLeaves(shifts)
    }

    private fun mergeConsecutiveLeaves(rawShifts: List<WorkShift>): List<WorkShift> {
        val workShifts = rawShifts.filter { !it.isAllDayLeave }.toMutableList()
        val leaves = rawShifts.filter { it.isAllDayLeave }.sortedBy { it.start }

        if (leaves.isEmpty()) return workShifts

        var currentLeave = leaves.first()
        for (i in 1 until leaves.size) {
            val next = leaves[i]
            if (next.title == currentLeave.title && next.start.toLocalDate() == currentLeave.end.toLocalDate()) {
                currentLeave = currentLeave.copy(end = next.end)
            } else {
                workShifts.add(currentLeave)
                currentLeave = next
            }
        }
        workShifts.add(currentLeave)
        return workShifts
    }
}
'''
parser_file.write_text(new_parser_code, encoding="utf-8")

# ==============================================================================
# 3. SettingsDialogHelper.kt (Oletuskalenteriksi Googlen kalenteri)
# ==============================================================================
settings_file = pathlib.Path("app/src/main/java/fi/numeron/vuorovahti/SettingsDialogHelper.kt")
settings_text = settings_file.read_text(encoding="utf-8")

new_get_calendars = r'''    fun getAvailableCalendars(context: Context): List<CalendarInfo> {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return emptyList()
        }
        val primaryGoogle = mutableListOf<CalendarInfo>()
        val otherGoogle = mutableListOf<CalendarInfo>()
        val others = mutableListOf<CalendarInfo>()

        val projection = arrayOf(
            CalendarContract.Calendars._ID,
            CalendarContract.Calendars.CALENDAR_DISPLAY_NAME,
            CalendarContract.Calendars.ACCOUNT_TYPE,
            CalendarContract.Calendars.IS_PRIMARY
        )
        val selection = "${CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL} >= ${CalendarContract.Calendars.CAL_ACCESS_CONTRIBUTOR} AND " +
                "${CalendarContract.Calendars.VISIBLE} = 1"
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
                val accountType = cursor.getString(2) ?: ""
                val isPrimary = cursor.getInt(3) == 1
                val info = CalendarInfo(id, name)

                if (accountType == "com.google") {
                    if (isPrimary) primaryGoogle.add(info) else otherGoogle.add(info)
                } else {
                    others.add(info)
                }
            }
        }
        return primaryGoogle + otherGoogle + others
    }'''

settings_text = replace_block(settings_text, "    fun getAvailableCalendars(context: Context): List<CalendarInfo> {", "\n}", new_get_calendars)
settings_file.write_text(settings_text, encoding="utf-8")

# ==============================================================================
# 4. CalendarSyncHelper.kt (Googlen värit + otsikko/sijainti/kuvaus + tulevat)
# ==============================================================================
sync_file = pathlib.Path("app/src/main/java/fi/numeron/vuorovahti/CalendarSyncHelper.kt")
new_sync_code = r'''package fi.numeron.vuorovahti

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
'''
sync_file.write_text(new_sync_code, encoding="utf-8")

# ==============================================================================
# 5. DemoModeHelper.kt (Yhteensopivuus uusien WorkShift-kenttien kanssa)
# ==============================================================================
demo_file = pathlib.Path("app/src/main/java/fi/numeron/vuorovahti/DemoModeHelper.kt")
demo_text = demo_file.read_text(encoding="utf-8")

new_demo_shifts = r'''    fun generateDemoWorkShifts(context: Context): List<WorkShift> {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val variant = prefs.getInt("demo_shift_variant", 0)
        val today = LocalDate.now()

        return if (variant % 2 == 0) {
            listOf(
                WorkShift("Työvuoro", LocalDateTime.of(today.plusDays(1), LocalTime.of(7, 0)), LocalDateTime.of(today.plusDays(1), LocalTime.of(15, 0)), false, "Outokumpu Onni", "Aamu • Hoitaja"),
                WorkShift("Työvuoro", LocalDateTime.of(today.plusDays(2), LocalTime.of(13, 0)), LocalDateTime.of(today.plusDays(2), LocalTime.of(21, 0)), false, "Outokumpu Onni", "Ilta • Hoitaja"),
                WorkShift("Työvuoro", LocalDateTime.of(today.plusDays(3), LocalTime.of(21, 0)), LocalDateTime.of(today.plusDays(4), LocalTime.of(7, 0)), false, "Outokumpu Onni", "Yö • Hoitaja"),
                WorkShift("Vuosiloma (Demo)", today.plusDays(5).atStartOfDay(), today.plusDays(7).atStartOfDay(), true)
            )
        } else {
            listOf(
                WorkShift("Työvuoro", LocalDateTime.of(today.plusDays(1), LocalTime.of(13, 0)), LocalDateTime.of(today.plusDays(1), LocalTime.of(21, 0)), false, "Outokumpu Onni", "Ilta • Hoitaja"),
                WorkShift("Työvuoro", LocalDateTime.of(today.plusDays(2), LocalTime.of(13, 0)), LocalDateTime.of(today.plusDays(2), LocalTime.of(21, 0)), false, "Outokumpu Onni", "Ilta • Hoitaja"),
                WorkShift("Työvuoro", LocalDateTime.of(today.plusDays(4), LocalTime.of(7, 0)), LocalDateTime.of(today.plusDays(4), LocalTime.of(15, 0)), false, "Outokumpu Onni", "Aamu • Hoitaja"),
                WorkShift("Vuosiloma (Demo)", today.plusDays(5).atStartOfDay(), today.plusDays(7).atStartOfDay(), true)
            )
        }
    }'''

demo_text = replace_block(
    demo_text,
    "    fun generateDemoWorkShifts(context: Context): List<WorkShift> {",
    "\n\n    class DemoJsBridge(",
    new_demo_shifts
)
demo_file.write_text(demo_text, encoding="utf-8")

# ==============================================================================
# 6. versionCode +1
# ==============================================================================
for candidate in ["app/build.gradle.kts", "app/build.gradle"]:
    gf = pathlib.Path(candidate)
    if gf.exists():
        gt = gf.read_text(encoding="utf-8")
        gt, n = re.subn(r'(versionCode\s*=?\s*)(\d+)', lambda m: f"{m.group(1)}{int(m.group(2)) + 1}", gt, count=1)
        if n == 1:
            gf.write_text(gt, encoding="utf-8")
