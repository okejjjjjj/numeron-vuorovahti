package fi.numeron.vuorovahti

import android.content.Context
import android.webkit.CookieManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

data class PersonRequestItem(
    val id: Int,
    val type: String,
    val dateFrom: LocalDate?,
    val dateTo: LocalDate?,
    val timeFromText: String,
    val timeToText: String,
    val info: String,
    val statusCode: Int,
    val statusDescription: String,
    val belongsToSeries: Boolean,
    val approvedBy: String,
    val approvedDateMs: Long?
)

data class RequestsFetchResult(
    val items: List<PersonRequestItem>?,
    val fromCache: Boolean = false,
    val errorMessage: String? = null
)

object NumeronApiClient {

    private val MAX_SESSION_REGEX = Regex("maxSessionTimeInMilliseconds\\s*=\\s*(\\d+)")
    private val DOTNET_DATE_REGEX = Regex("/Date\\((-?\\d+)\\)/")

    fun extractAndSaveMaxSessionTime(context: Context, html: String) {
        if (html.isEmpty()) return
        val match = MAX_SESSION_REGEX.find(html) ?: return
        val expiryMs = match.groupValues[1].toLongOrNull() ?: return
        val nowMs = System.currentTimeMillis()
        if (expiryMs > nowMs) {
            context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                .edit()
                .putLong("server_session_expiry_ms", expiryMs)
                .putLong("last_valid_session_ms", nowMs)
                .apply()
        }
    }

    fun isSessionLikelyValid(
        context: Context,
        baseUrl: String,
        isAutoStamping: Boolean = false
    ): Boolean {
        if (baseUrl.isBlank()) return false
        val existingCookies = try {
            CookieManager.getInstance().getCookie(baseUrl)
        } catch (_: Exception) {
            null
        }
        if (existingCookies.isNullOrBlank()) return false

        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val nowMs = System.currentTimeMillis()
        val serverExpiryMs = prefs.getLong("server_session_expiry_ms", 0L)
        if (serverExpiryMs > 0L) {
            val bufferMs = if (isAutoStamping) 15L * 60_000L else 10L * 60_000L
            return nowMs < (serverExpiryMs - bufferMs)
        }

        val lastSessionMs = prefs.getLong("last_valid_session_ms", 0L)
        val maxAgeMs = if (isAutoStamping) 10L * 60_000L else 4L * 60L * 60_000L
        return lastSessionMs > 0L && (nowMs - lastSessionMs) <= maxAgeMs
    }

    suspend fun fetchMonthCalendarHtml(context: Context, year: Int, month: Int): String? =
        withContext(Dispatchers.IO) {
            val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
            if (baseUrl.isBlank()) return@withContext null
            val url = "$baseUrl/Calendar/Month?month=$month&year=$year"
            val html = BackgroundAuthHelper.fetchAuthenticatedPages(context, listOf(url))?.firstOrNull()
            if (html != null) {
                extractAndSaveMaxSessionTime(context, html)
            }
            html
        }

    suspend fun fetchRequests(context: Context, filter: String = "active"): RequestsFetchResult =
        withContext(Dispatchers.IO) {
            val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
            if (baseUrl.isBlank()) {
                return@withContext RequestsFetchResult(null, errorMessage = "Organisaatio puuttuu")
            }
            if (BackgroundAuthHelper.isCredentialBlocked(context)) {
                return@withContext RequestsFetchResult(null, errorMessage = "Tarkista tunnukset asetuksista")
            }

            if (!isSessionLikelyValid(context, baseUrl, isAutoStamping = false)) {
                BackgroundAuthHelper.ensureAuthenticatedSession(context)
            }

            var json = executeRequestsPost(baseUrl, filter)
            if (json == null) {
                val reauthed = BackgroundAuthHelper.ensureAuthenticatedSession(context, forceRefresh = true)
                if (reauthed) {
                    json = executeRequestsPost(baseUrl, filter)
                }
            }

            if (json == null) {
                val cached = loadCachedRequests(context, filter)
                return@withContext if (cached != null) {
                    RequestsFetchResult(cached, fromCache = true, errorMessage = "Näytetään välimuisti")
                } else {
                    RequestsFetchResult(null, errorMessage = "Toiveiden haku epäonnistui")
                }
            }

            val parsed = parseRequestsJson(context, json)
            if (parsed != null) {
                saveCachedRequestsJson(context, filter, json)
                context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                    .edit()
                    .putLong("last_valid_session_ms", System.currentTimeMillis())
                    .apply()
                RequestsFetchResult(parsed, fromCache = false)
            } else {
                RequestsFetchResult(null, errorMessage = "Vastauksen lukeminen epäonnistui")
            }
        }

    private fun executeRequestsPost(baseUrl: String, filter: String): String? {
        var conn: HttpURLConnection? = null
        return try {
            val cookies = CookieManager.getInstance().getCookie(baseUrl)
            if (cookies.isNullOrBlank()) return null

            val safeFilter = when (filter) {
                "old", "removed" -> filter
                else -> "active"
            }

            conn = (URL("$baseUrl/PersonRequests/Read").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                instanceFollowRedirects = false
                setRequestProperty("Cookie", cookies)
                setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
                setRequestProperty("Accept", "application/json, text/javascript, */*; q=0.01")
                setRequestProperty("X-Requested-With", "XMLHttpRequest")
                setRequestProperty(
                    "User-Agent",
                    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
                )
                doOutput = true
                connectTimeout = 15_000
                readTimeout = 15_000
            }

            OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { writer ->
                writer.write("sort=&page=1&pageSize=100&group=&filter=&selectedFilter=$safeFilter")
                writer.flush()
            }

            if (conn.responseCode != 200) return null
            val body = conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            if (body.trim().startsWith("{")) body else null
        } catch (_: Exception) {
            null
        } finally {
            conn?.disconnect()
        }
    }

    fun parseRequestsJson(context: Context, jsonStr: String): List<PersonRequestItem>? {
        return try {
            val root = JSONObject(jsonStr)
            val dataArray = root.optJSONArray("data") ?: root.optJSONArray("Data") ?: return emptyList()
            val en = DemoModeHelper.isEnglish(context)
            val list = ArrayList<PersonRequestItem>(dataArray.length())

            for (i in 0 until dataArray.length()) {
                val item = dataArray.optJSONObject(i) ?: continue
                val id = item.optInt("Id", -1).let { if (it > 0) it else item.optInt("RowId", -1) }
                if (id <= 0) continue

                val rawStatus = item.optString("Status", "").trim().toIntOrNull()
                    ?: item.optString("StatusId", "").trim().toIntOrNull()
                    ?: item.optInt("Status", -1).let { if (it > 0) it else item.optInt("StatusId", -1) }
                val rawDesc = item.optString("StatusDescription", "").trim()
                val statusCode = resolveStatusCode(rawStatus, rawDesc)
                val statusDesc = rawDesc.ifEmpty { fallbackStatusLabel(statusCode, en) }

                val type = item.optString("Type", if (en) "Request" else "Toive").trim()
                val dateFrom = parseLocalDate(item.optString("DateFrom", ""))
                val dateTo = parseLocalDate(item.optString("DateTo", ""))
                val timeFromText = parseTimeSpan(item.optJSONObject("TimeFromTimeSpan"))
                val timeToText = parseTimeSpan(item.optJSONObject("TimeToTimeSpan"))
                val info = item.optString("Info", "").let { if (it.equals("null", true)) "" else it.trim() }
                val belongsToSeries = item.optBoolean("BelongsToSeries", false)
                val approvedBy = item.optString("ApprovedBy", "").let { if (it.equals("null", true)) "" else it.trim() }
                val approvedDateMs = parseDotNetDateMs(item.optString("ApprovedDate", ""))

                list.add(
                    PersonRequestItem(
                        id = id,
                        type = type,
                        dateFrom = dateFrom,
                        dateTo = dateTo,
                        timeFromText = timeFromText,
                        timeToText = timeToText,
                        info = info,
                        statusCode = statusCode,
                        statusDescription = statusDesc,
                        belongsToSeries = belongsToSeries,
                        approvedBy = approvedBy,
                        approvedDateMs = approvedDateMs
                    )
                )
            }
            list
        } catch (_: Exception) {
            null
        }
    }

    private fun resolveStatusCode(rawStatus: Int, statusDesc: String): Int {
        if (rawStatus == 10 || rawStatus == 40 || rawStatus == 50 || rawStatus == 80) return rawStatus
        val lower = statusDesc.trim().lowercase()
        if (lower.isEmpty()) return rawStatus
        return when {
            lower.contains("odottaa") || lower.contains("pending") || lower.contains("waiting") || lower.contains("väntar") -> 10
            lower.contains("osittain") || lower.contains("partial") || lower.contains("delvis") -> 40
            lower.contains("hylätty") || lower.contains("reject") || lower.contains("denied") || lower.contains("avslag") -> 80
            lower.contains("hyväksytty") || lower.contains("approved") || lower.contains("godkänd") -> 50
            else -> rawStatus
        }
    }

    private fun fallbackStatusLabel(statusId: Int, en: Boolean): String = when (statusId) {
        10 -> if (en) "Pending" else "Odottaa käsittelyä"
        40 -> if (en) "Partially approved" else "Osittain hyväksytty"
        50 -> if (en) "Approved" else "Hyväksytty"
        80 -> if (en) "Rejected" else "Hylätty"
        else -> ""
    }

    private fun parseDotNetDateMs(raw: String): Long? {
        val match = DOTNET_DATE_REGEX.find(raw.trim()) ?: return null
        return match.groupValues[1].toLongOrNull()
    }

    private fun parseLocalDate(raw: String): LocalDate? {
        val trimmed = raw.trim()
        if (trimmed.isEmpty() || trimmed.equals("null", ignoreCase = true)) return null
        val ms = parseDotNetDateMs(trimmed)
        if (ms != null) {
            return Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).toLocalDate()
        }
        val iso = Regex("^(\\d{4}-\\d{2}-\\d{2})").find(trimmed)?.groupValues?.get(1)
        if (iso != null) {
            return try {
                LocalDate.parse(iso)
            } catch (_: Exception) {
                null
            }
        }
        return null
    }

    private fun parseTimeSpan(obj: JSONObject?): String {
        if (obj == null) return ""
        val hours = obj.optInt("Hours", 0)
        val minutes = obj.optInt("Minutes", 0)
        if (hours == 0 && minutes == 0) return ""
        return String.format("%02d:%02d", hours, minutes)
    }

    private fun requestsCacheFile(context: Context, filter: String): File {
        val safe = when (filter) {
            "old", "removed" -> filter
            else -> "active"
        }
        return File(context.cacheDir, "vv_requests_$safe.json")
    }

    private fun saveCachedRequestsJson(context: Context, filter: String, json: String) {
        try {
            requestsCacheFile(context, filter).writeText(json, Charsets.UTF_8)
        } catch (_: Exception) {
        }
    }

    fun loadCachedRequests(context: Context, filter: String): List<PersonRequestItem>? {
        return try {
            val file = requestsCacheFile(context, filter)
            if (!file.exists()) return null
            parseRequestsJson(context, file.readText(Charsets.UTF_8))
        } catch (_: Exception) {
            null
        }
    }

    private fun monthCacheFile(context: Context, year: Int, month: Int): File {
        return File(context.cacheDir, "vv_month_${year}_${month}.json")
    }

    fun saveMonthDisplayCache(context: Context, data: MonthDisplayData) {
        try {
            val root = JSONObject().apply {
                put("year", data.year)
                put("month", data.month)
                put("savedAt", System.currentTimeMillis())
            }
            val daysArr = JSONArray()
            for ((date, day) in data.days) {
                val dObj = JSONObject().apply {
                    put("date", date.toString())
                    put("hasCommentCircle", day.hasCommentCircle)
                }
                val shiftsArr = JSONArray()
                for (s in day.shifts) {
                    shiftsArr.put(
                        JSONObject().apply {
                            put("startText", s.startText)
                            put("endText", s.endText)
                            put("startMinutes", s.startMinutes)
                            put("endMinutes", s.endMinutes)
                            put("location", s.location)
                            put("shiftName", s.shiftName)
                            put("role", s.role)
                            put("rawTitle", s.rawTitle)
                        }
                    )
                }
                dObj.put("shifts", shiftsArr)

                val absArr = JSONArray()
                for (a in day.absences) {
                    absArr.put(
                        JSONObject().apply {
                            put("title", a.title)
                            put("kind", a.kind)
                            put("spanDays", a.spanDays)
                        }
                    )
                }
                dObj.put("absences", absArr)

                val reqArr = JSONArray()
                for (r in day.requests) {
                    reqArr.put(r.title)
                }
                dObj.put("requests", reqArr)

                daysArr.put(dObj)
            }
            root.put("days", daysArr)
            monthCacheFile(context, data.year, data.month).writeText(root.toString(), Charsets.UTF_8)
        } catch (_: Exception) {
        }
    }

    fun loadMonthDisplayCache(context: Context, year: Int, month: Int): MonthDisplayData? {
        return try {
            val file = monthCacheFile(context, year, month)
            if (!file.exists()) return null
            val root = JSONObject(file.readText(Charsets.UTF_8))
            val daysArr = root.optJSONArray("days") ?: return null
            val map = mutableMapOf<LocalDate, CalendarDisplayDay>()

            for (i in 0 until daysArr.length()) {
                val dObj = daysArr.optJSONObject(i) ?: continue
                val date = try {
                    LocalDate.parse(dObj.optString("date", ""))
                } catch (_: Exception) {
                    continue
                }
                val hasCircle = dObj.optBoolean("hasCommentCircle", false)

                val shifts = mutableListOf<CalendarDisplayShift>()
                val sArr = dObj.optJSONArray("shifts")
                if (sArr != null) {
                    for (j in 0 until sArr.length()) {
                        val s = sArr.optJSONObject(j) ?: continue
                        shifts.add(
                            CalendarDisplayShift(
                                startText = s.optString("startText", ""),
                                endText = s.optString("endText", ""),
                                startMinutes = s.optInt("startMinutes", 0),
                                endMinutes = s.optInt("endMinutes", 0),
                                location = s.optString("location", ""),
                                shiftName = s.optString("shiftName", ""),
                                role = s.optString("role", ""),
                                rawTitle = s.optString("rawTitle", "")
                            )
                        )
                    }
                }

                val absences = mutableListOf<CalendarDisplayAbsence>()
                val aArr = dObj.optJSONArray("absences")
                if (aArr != null) {
                    for (j in 0 until aArr.length()) {
                        val a = aArr.optJSONObject(j) ?: continue
                        absences.add(
                            CalendarDisplayAbsence(
                                title = a.optString("title", ""),
                                kind = a.optString("kind", "other"),
                                spanDays = a.optInt("spanDays", 1)
                            )
                        )
                    }
                }

                val requests = mutableListOf<CalendarDisplayRequest>()
                val rArr = dObj.optJSONArray("requests")
                if (rArr != null) {
                    for (j in 0 until rArr.length()) {
                        val t = rArr.optString(j, "")
                        if (t.isNotEmpty()) requests.add(CalendarDisplayRequest(t))
                    }
                }

                map[date] = CalendarDisplayDay(
                    date = date,
                    shifts = shifts,
                    absences = absences,
                    requests = requests,
                    hasCommentCircle = hasCircle
                )
            }
            MonthDisplayData(year = year, month = month, days = map)
        } catch (_: Exception) {
            null
        }
    }

    fun buildMonthDisplayFromCachedShifts(
        shifts: List<WorkShift>,
        year: Int,
        month: Int
    ): MonthDisplayData? {
        val targetYm = java.time.YearMonth.of(year, month)
        val firstDay = targetYm.atDay(1)
        val lastDay = targetYm.atEndOfMonth()

        val shiftsByDate = mutableMapOf<LocalDate, MutableList<CalendarDisplayShift>>()
        val absencesByDate = mutableMapOf<LocalDate, MutableList<CalendarDisplayAbsence>>()
        var matchedAny = false

        for (shift in shifts) {
            if (shift.isAllDayLeave) {
                var d = shift.start.toLocalDate()
                val endExcl = shift.end.toLocalDate()
                val kind = when {
                    shift.title.contains("sairaus", true) || shift.title.contains("hoitovapaa", true) -> "sick"
                    shift.title.contains("loma", true) || shift.title.contains("säästövapaa", true) -> "vacation"
                    else -> "other"
                }
                while (d.isBefore(endExcl)) {
                    if (!d.isBefore(firstDay) && !d.isAfter(lastDay)) {
                        matchedAny = true
                        val list = absencesByDate.getOrPut(d) { mutableListOf() }
                        if (list.none { it.title.equals(shift.title, true) }) {
                            list.add(CalendarDisplayAbsence(shift.title, kind, 1))
                        }
                    }
                    d = d.plusDays(1)
                }
            } else {
                val d = shift.start.toLocalDate()
                if (!d.isBefore(firstDay) && !d.isAfter(lastDay)) {
                    matchedAny = true
                    val startText = String.format("%d:%02d", shift.start.hour, shift.start.minute)
                    val endText = String.format("%d:%02d", shift.end.hour, shift.end.minute)
                    val startMin = shift.start.hour * 60 + shift.start.minute
                    val endMin = shift.end.hour * 60 + shift.end.minute
                    val list = shiftsByDate.getOrPut(d) { mutableListOf() }
                    list.add(
                        CalendarDisplayShift(
                            startText = startText,
                            endText = endText,
                            startMinutes = startMin,
                            endMinutes = endMin,
                            location = shift.location,
                            shiftName = shift.title.takeUnless { it.equals("Työvuoro", true) }.orEmpty(),
                            role = shift.description.lineSequence().firstOrNull().orEmpty(),
                            rawTitle = shift.title
                        )
                    )
                }
            }
        }

        if (!matchedAny) return null
        val allDates = (shiftsByDate.keys + absencesByDate.keys)
        val dayMap = mutableMapOf<LocalDate, CalendarDisplayDay>()
        for (d in allDates) {
            dayMap[d] = CalendarDisplayDay(
                date = d,
                shifts = shiftsByDate[d].orEmpty(),
                absences = absencesByDate[d].orEmpty(),
                requests = emptyList(),
                hasCommentCircle = false
            )
        }
        return MonthDisplayData(year = year, month = month, days = dayMap)
    }
}
