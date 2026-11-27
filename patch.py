#!/usr/bin/env python3
"""
Numeron Vuorovahti – Vaiheet 1, 2 ja 3 (patch.py):
- Vaihe 1: Laiska WebView, NumeronApiClient, tarkka maxSessionTimeInMilliseconds-istuntoaika, eligibility-esto
- Vaihe 2: Natiivi Vuorot-kuukausikalenteri (välimuisti + offline + taustahaku + päivän yksityiskohdat + kommentit)
- Vaihe 3: Natiivi Toiveet-lista (suora POST /PersonRequests/Read + välimuisti + laiska WebView muokkaukseen/lisäykseen)
- Versiokoodin korotus: versionCode 123 -> 124, versionName 3.2.181 -> 3.2.182
"""

import sys
from pathlib import Path


def find_file(filename: str) -> Path | None:
    candidates = [
        Path("app/src/main/java/fi/numeron/vuorovahti") / filename,
        Path("src/main/java/fi/numeron/vuorovahti") / filename,
        Path("app/src/main/res/layout") / filename,
        Path("src/main/res/layout") / filename,
        Path("app") / filename,
        Path(filename),
    ]
    for c in candidates:
        if c.exists():
            return c
    for p in Path(".").rglob(filename):
        if ".git" not in p.parts and "build" not in p.parts:
            return p
    return None


def read_text_keep_nl(path: Path) -> tuple[str, str]:
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def write_text_keep_nl(path: Path, content: str, newline: str) -> None:
    normalized = content.replace("\r\n", "\n")
    if newline == "\r\n":
        normalized = normalized.replace("\n", "\r\n")
    path.write_bytes(normalized.encode("utf-8"))


def write_new_file(path: Path, content: str, label: str) -> bool:
    normalized = content.replace("\r\n", "\n").lstrip("\n")
    if path.exists():
        existing, nl = read_text_keep_nl(path)
        if existing == normalized:
            print(f"  [OK - jo ajantasalla] {label} ({path})")
            return False
        write_text_keep_nl(path, normalized, nl)
        print(f"  [PÄIVITETTY] {label} ({path})")
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(normalized.encode("utf-8"))
    print(f"  [LUOTU] {label} ({path})")
    return True


def replace_once(content: str, old: str, new: str, label: str) -> str:
    if new in content:
        print(f"  [OK - jo sovellettu] {label}")
        return content
    if old not in content:
        print(f"  [VAROITUS - kohdetta ei löytynyt] {label}")
        return content
    print(f"  [PÄIVITETTY] {label}")
    return content.replace(old, new, 1)

NUMERON_API_CLIENT_KT = 'package fi.numeron.vuorovahti\n\nimport android.content.Context\nimport android.webkit.CookieManager\nimport kotlinx.coroutines.Dispatchers\nimport kotlinx.coroutines.withContext\nimport org.json.JSONArray\nimport org.json.JSONObject\nimport java.io.File\nimport java.io.OutputStreamWriter\nimport java.net.HttpURLConnection\nimport java.net.URL\nimport java.time.Instant\nimport java.time.LocalDate\nimport java.time.ZoneId\n\ndata class PersonRequestItem(\n    val id: Int,\n    val type: String,\n    val dateFrom: LocalDate?,\n    val dateTo: LocalDate?,\n    val timeFromText: String,\n    val timeToText: String,\n    val info: String,\n    val statusCode: Int,\n    val statusDescription: String,\n    val belongsToSeries: Boolean,\n    val approvedBy: String,\n    val approvedDateMs: Long?\n)\n\ndata class RequestsFetchResult(\n    val items: List<PersonRequestItem>?,\n    val fromCache: Boolean = false,\n    val errorMessage: String? = null\n)\n\nobject NumeronApiClient {\n\n    private val MAX_SESSION_REGEX = Regex("maxSessionTimeInMilliseconds\\\\s*=\\\\s*(\\\\d+)")\n    private val DOTNET_DATE_REGEX = Regex("/Date\\\\((-?\\\\d+)\\\\)/")\n\n    fun extractAndSaveMaxSessionTime(context: Context, html: String) {\n        if (html.isEmpty()) return\n        val match = MAX_SESSION_REGEX.find(html) ?: return\n        val expiryMs = match.groupValues[1].toLongOrNull() ?: return\n        val nowMs = System.currentTimeMillis()\n        if (expiryMs > nowMs) {\n            context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n                .edit()\n                .putLong("server_session_expiry_ms", expiryMs)\n                .putLong("last_valid_session_ms", nowMs)\n                .apply()\n        }\n    }\n\n    fun isSessionLikelyValid(\n        context: Context,\n        baseUrl: String,\n        isAutoStamping: Boolean = false\n    ): Boolean {\n        if (baseUrl.isBlank()) return false\n        val existingCookies = try {\n            CookieManager.getInstance().getCookie(baseUrl)\n        } catch (_: Exception) {\n            null\n        }\n        if (existingCookies.isNullOrBlank()) return false\n\n        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n        val nowMs = System.currentTimeMillis()\n        val serverExpiryMs = prefs.getLong("server_session_expiry_ms", 0L)\n        if (serverExpiryMs > 0L) {\n            val bufferMs = if (isAutoStamping) 15L * 60_000L else 10L * 60_000L\n            return nowMs < (serverExpiryMs - bufferMs)\n        }\n\n        val lastSessionMs = prefs.getLong("last_valid_session_ms", 0L)\n        val maxAgeMs = if (isAutoStamping) 10L * 60_000L else 4L * 60L * 60_000L\n        return lastSessionMs > 0L && (nowMs - lastSessionMs) <= maxAgeMs\n    }\n\n    suspend fun fetchMonthCalendarHtml(context: Context, year: Int, month: Int): String? =\n        withContext(Dispatchers.IO) {\n            val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n            if (baseUrl.isBlank()) return@withContext null\n            val url = "$baseUrl/Calendar/Month?month=$month&year=$year"\n            val html = BackgroundAuthHelper.fetchAuthenticatedPages(context, listOf(url))?.firstOrNull()\n            if (html != null) {\n                extractAndSaveMaxSessionTime(context, html)\n            }\n            html\n        }\n\n    suspend fun fetchRequests(context: Context, filter: String = "active"): RequestsFetchResult =\n        withContext(Dispatchers.IO) {\n            val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n            if (baseUrl.isBlank()) {\n                return@withContext RequestsFetchResult(null, errorMessage = "Organisaatio puuttuu")\n            }\n            if (BackgroundAuthHelper.isCredentialBlocked(context)) {\n                return@withContext RequestsFetchResult(null, errorMessage = "Tarkista tunnukset asetuksista")\n            }\n\n            if (!isSessionLikelyValid(context, baseUrl, isAutoStamping = false)) {\n                BackgroundAuthHelper.ensureAuthenticatedSession(context)\n            }\n\n            var json = executeRequestsPost(baseUrl, filter)\n            if (json == null) {\n                val reauthed = BackgroundAuthHelper.ensureAuthenticatedSession(context, forceRefresh = true)\n                if (reauthed) {\n                    json = executeRequestsPost(baseUrl, filter)\n                }\n            }\n\n            if (json == null) {\n                val cached = loadCachedRequests(context, filter)\n                return@withContext if (cached != null) {\n                    RequestsFetchResult(cached, fromCache = true, errorMessage = "Näytetään välimuisti")\n                } else {\n                    RequestsFetchResult(null, errorMessage = "Toiveiden haku epäonnistui")\n                }\n            }\n\n            val parsed = parseRequestsJson(context, json)\n            if (parsed != null) {\n                saveCachedRequestsJson(context, filter, json)\n                context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n                    .edit()\n                    .putLong("last_valid_session_ms", System.currentTimeMillis())\n                    .apply()\n                RequestsFetchResult(parsed, fromCache = false)\n            } else {\n                RequestsFetchResult(null, errorMessage = "Vastauksen lukeminen epäonnistui")\n            }\n        }\n\n    private fun executeRequestsPost(baseUrl: String, filter: String): String? {\n        var conn: HttpURLConnection? = null\n        return try {\n            val cookies = CookieManager.getInstance().getCookie(baseUrl)\n            if (cookies.isNullOrBlank()) return null\n\n            val safeFilter = when (filter) {\n                "old", "removed" -> filter\n                else -> "active"\n            }\n\n            conn = (URL("$baseUrl/PersonRequests/Read").openConnection() as HttpURLConnection).apply {\n                requestMethod = "POST"\n                instanceFollowRedirects = false\n                setRequestProperty("Cookie", cookies)\n                setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")\n                setRequestProperty("Accept", "application/json, text/javascript, */*; q=0.01")\n                setRequestProperty("X-Requested-With", "XMLHttpRequest")\n                setRequestProperty(\n                    "User-Agent",\n                    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"\n                )\n                doOutput = true\n                connectTimeout = 15_000\n                readTimeout = 15_000\n            }\n\n            OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { writer ->\n                writer.write("sort=&page=1&pageSize=100&group=&filter=&selectedFilter=$safeFilter")\n                writer.flush()\n            }\n\n            if (conn.responseCode != 200) return null\n            val body = conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }\n            if (body.trim().startsWith("{")) body else null\n        } catch (_: Exception) {\n            null\n        } finally {\n            conn?.disconnect()\n        }\n    }\n\n    fun parseRequestsJson(context: Context, jsonStr: String): List<PersonRequestItem>? {\n        return try {\n            val root = JSONObject(jsonStr)\n            val dataArray = root.optJSONArray("data") ?: root.optJSONArray("Data") ?: return emptyList()\n            val en = DemoModeHelper.isEnglish(context)\n            val list = ArrayList<PersonRequestItem>(dataArray.length())\n\n            for (i in 0 until dataArray.length()) {\n                val item = dataArray.optJSONObject(i) ?: continue\n                val id = item.optInt("Id", -1).let { if (it > 0) it else item.optInt("RowId", -1) }\n                if (id <= 0) continue\n\n                val rawStatus = item.optString("Status", "").trim().toIntOrNull()\n                    ?: item.optString("StatusId", "").trim().toIntOrNull()\n                    ?: item.optInt("Status", -1).let { if (it > 0) it else item.optInt("StatusId", -1) }\n                val rawDesc = item.optString("StatusDescription", "").trim()\n                val statusCode = resolveStatusCode(rawStatus, rawDesc)\n                val statusDesc = rawDesc.ifEmpty { fallbackStatusLabel(statusCode, en) }\n\n                val type = item.optString("Type", if (en) "Request" else "Toive").trim()\n                val dateFrom = parseLocalDate(item.optString("DateFrom", ""))\n                val dateTo = parseLocalDate(item.optString("DateTo", ""))\n                val timeFromText = parseTimeSpan(item.optJSONObject("TimeFromTimeSpan"))\n                val timeToText = parseTimeSpan(item.optJSONObject("TimeToTimeSpan"))\n                val info = item.optString("Info", "").let { if (it.equals("null", true)) "" else it.trim() }\n                val belongsToSeries = item.optBoolean("BelongsToSeries", false)\n                val approvedBy = item.optString("ApprovedBy", "").let { if (it.equals("null", true)) "" else it.trim() }\n                val approvedDateMs = parseDotNetDateMs(item.optString("ApprovedDate", ""))\n\n                list.add(\n                    PersonRequestItem(\n                        id = id,\n                        type = type,\n                        dateFrom = dateFrom,\n                        dateTo = dateTo,\n                        timeFromText = timeFromText,\n                        timeToText = timeToText,\n                        info = info,\n                        statusCode = statusCode,\n                        statusDescription = statusDesc,\n                        belongsToSeries = belongsToSeries,\n                        approvedBy = approvedBy,\n                        approvedDateMs = approvedDateMs\n                    )\n                )\n            }\n            list\n        } catch (_: Exception) {\n            null\n        }\n    }\n\n    private fun resolveStatusCode(rawStatus: Int, statusDesc: String): Int {\n        if (rawStatus == 10 || rawStatus == 40 || rawStatus == 50 || rawStatus == 80) return rawStatus\n        val lower = statusDesc.trim().lowercase()\n        if (lower.isEmpty()) return rawStatus\n        return when {\n            lower.contains("odottaa") || lower.contains("pending") || lower.contains("waiting") || lower.contains("väntar") -> 10\n            lower.contains("osittain") || lower.contains("partial") || lower.contains("delvis") -> 40\n            lower.contains("hylätty") || lower.contains("reject") || lower.contains("denied") || lower.contains("avslag") -> 80\n            lower.contains("hyväksytty") || lower.contains("approved") || lower.contains("godkänd") -> 50\n            else -> rawStatus\n        }\n    }\n\n    private fun fallbackStatusLabel(statusId: Int, en: Boolean): String = when (statusId) {\n        10 -> if (en) "Pending" else "Odottaa käsittelyä"\n        40 -> if (en) "Partially approved" else "Osittain hyväksytty"\n        50 -> if (en) "Approved" else "Hyväksytty"\n        80 -> if (en) "Rejected" else "Hylätty"\n        else -> ""\n    }\n\n    private fun parseDotNetDateMs(raw: String): Long? {\n        val match = DOTNET_DATE_REGEX.find(raw.trim()) ?: return null\n        return match.groupValues[1].toLongOrNull()\n    }\n\n    private fun parseLocalDate(raw: String): LocalDate? {\n        val trimmed = raw.trim()\n        if (trimmed.isEmpty() || trimmed.equals("null", ignoreCase = true)) return null\n        val ms = parseDotNetDateMs(trimmed)\n        if (ms != null) {\n            return Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).toLocalDate()\n        }\n        val iso = Regex("^(\\\\d{4}-\\\\d{2}-\\\\d{2})").find(trimmed)?.groupValues?.get(1)\n        if (iso != null) {\n            return try {\n                LocalDate.parse(iso)\n            } catch (_: Exception) {\n                null\n            }\n        }\n        return null\n    }\n\n    private fun parseTimeSpan(obj: JSONObject?): String {\n        if (obj == null) return ""\n        val hours = obj.optInt("Hours", 0)\n        val minutes = obj.optInt("Minutes", 0)\n        if (hours == 0 && minutes == 0) return ""\n        return String.format("%02d:%02d", hours, minutes)\n    }\n\n    private fun requestsCacheFile(context: Context, filter: String): File {\n        val safe = when (filter) {\n            "old", "removed" -> filter\n            else -> "active"\n        }\n        return File(context.cacheDir, "vv_requests_$safe.json")\n    }\n\n    private fun saveCachedRequestsJson(context: Context, filter: String, json: String) {\n        try {\n            requestsCacheFile(context, filter).writeText(json, Charsets.UTF_8)\n        } catch (_: Exception) {\n        }\n    }\n\n    fun loadCachedRequests(context: Context, filter: String): List<PersonRequestItem>? {\n        return try {\n            val file = requestsCacheFile(context, filter)\n            if (!file.exists()) return null\n            parseRequestsJson(context, file.readText(Charsets.UTF_8))\n        } catch (_: Exception) {\n            null\n        }\n    }\n\n    private fun monthCacheFile(context: Context, year: Int, month: Int): File {\n        return File(context.cacheDir, "vv_month_${year}_${month}.json")\n    }\n\n    fun saveMonthDisplayCache(context: Context, data: MonthDisplayData) {\n        try {\n            val root = JSONObject().apply {\n                put("year", data.year)\n                put("month", data.month)\n                put("savedAt", System.currentTimeMillis())\n            }\n            val daysArr = JSONArray()\n            for ((date, day) in data.days) {\n                val dObj = JSONObject().apply {\n                    put("date", date.toString())\n                    put("hasCommentCircle", day.hasCommentCircle)\n                }\n                val shiftsArr = JSONArray()\n                for (s in day.shifts) {\n                    shiftsArr.put(\n                        JSONObject().apply {\n                            put("startText", s.startText)\n                            put("endText", s.endText)\n                            put("startMinutes", s.startMinutes)\n                            put("endMinutes", s.endMinutes)\n                            put("location", s.location)\n                            put("shiftName", s.shiftName)\n                            put("role", s.role)\n                            put("rawTitle", s.rawTitle)\n                        }\n                    )\n                }\n                dObj.put("shifts", shiftsArr)\n\n                val absArr = JSONArray()\n                for (a in day.absences) {\n                    absArr.put(\n                        JSONObject().apply {\n                            put("title", a.title)\n                            put("kind", a.kind)\n                            put("spanDays", a.spanDays)\n                        }\n                    )\n                }\n                dObj.put("absences", absArr)\n\n                val reqArr = JSONArray()\n                for (r in day.requests) {\n                    reqArr.put(r.title)\n                }\n                dObj.put("requests", reqArr)\n\n                daysArr.put(dObj)\n            }\n            root.put("days", daysArr)\n            monthCacheFile(context, data.year, data.month).writeText(root.toString(), Charsets.UTF_8)\n        } catch (_: Exception) {\n        }\n    }\n\n    fun loadMonthDisplayCache(context: Context, year: Int, month: Int): MonthDisplayData? {\n        return try {\n            val file = monthCacheFile(context, year, month)\n            if (!file.exists()) return null\n            val root = JSONObject(file.readText(Charsets.UTF_8))\n            val daysArr = root.optJSONArray("days") ?: return null\n            val map = mutableMapOf<LocalDate, CalendarDisplayDay>()\n\n            for (i in 0 until daysArr.length()) {\n                val dObj = daysArr.optJSONObject(i) ?: continue\n                val date = try {\n                    LocalDate.parse(dObj.optString("date", ""))\n                } catch (_: Exception) {\n                    continue\n                }\n                val hasCircle = dObj.optBoolean("hasCommentCircle", false)\n\n                val shifts = mutableListOf<CalendarDisplayShift>()\n                val sArr = dObj.optJSONArray("shifts")\n                if (sArr != null) {\n                    for (j in 0 until sArr.length()) {\n                        val s = sArr.optJSONObject(j) ?: continue\n                        shifts.add(\n                            CalendarDisplayShift(\n                                startText = s.optString("startText", ""),\n                                endText = s.optString("endText", ""),\n                                startMinutes = s.optInt("startMinutes", 0),\n                                endMinutes = s.optInt("endMinutes", 0),\n                                location = s.optString("location", ""),\n                                shiftName = s.optString("shiftName", ""),\n                                role = s.optString("role", ""),\n                                rawTitle = s.optString("rawTitle", "")\n                            )\n                        )\n                    }\n                }\n\n                val absences = mutableListOf<CalendarDisplayAbsence>()\n                val aArr = dObj.optJSONArray("absences")\n                if (aArr != null) {\n                    for (j in 0 until aArr.length()) {\n                        val a = aArr.optJSONObject(j) ?: continue\n                        absences.add(\n                            CalendarDisplayAbsence(\n                                title = a.optString("title", ""),\n                                kind = a.optString("kind", "other"),\n                                spanDays = a.optInt("spanDays", 1)\n                            )\n                        )\n                    }\n                }\n\n                val requests = mutableListOf<CalendarDisplayRequest>()\n                val rArr = dObj.optJSONArray("requests")\n                if (rArr != null) {\n                    for (j in 0 until rArr.length()) {\n                        val t = rArr.optString(j, "")\n                        if (t.isNotEmpty()) requests.add(CalendarDisplayRequest(t))\n                    }\n                }\n\n                map[date] = CalendarDisplayDay(\n                    date = date,\n                    shifts = shifts,\n                    absences = absences,\n                    requests = requests,\n                    hasCommentCircle = hasCircle\n                )\n            }\n            MonthDisplayData(year = year, month = month, days = map)\n        } catch (_: Exception) {\n            null\n        }\n    }\n\n    fun buildMonthDisplayFromCachedShifts(\n        shifts: List<WorkShift>,\n        year: Int,\n        month: Int\n    ): MonthDisplayData? {\n        val targetYm = java.time.YearMonth.of(year, month)\n        val firstDay = targetYm.atDay(1)\n        val lastDay = targetYm.atEndOfMonth()\n\n        val shiftsByDate = mutableMapOf<LocalDate, MutableList<CalendarDisplayShift>>()\n        val absencesByDate = mutableMapOf<LocalDate, MutableList<CalendarDisplayAbsence>>()\n        var matchedAny = false\n\n        for (shift in shifts) {\n            if (shift.isAllDayLeave) {\n                var d = shift.start.toLocalDate()\n                val endExcl = shift.end.toLocalDate()\n                val kind = when {\n                    shift.title.contains("sairaus", true) || shift.title.contains("hoitovapaa", true) -> "sick"\n                    shift.title.contains("loma", true) || shift.title.contains("säästövapaa", true) -> "vacation"\n                    else -> "other"\n                }\n                while (d.isBefore(endExcl)) {\n                    if (!d.isBefore(firstDay) && !d.isAfter(lastDay)) {\n                        matchedAny = true\n                        val list = absencesByDate.getOrPut(d) { mutableListOf() }\n                        if (list.none { it.title.equals(shift.title, true) }) {\n                            list.add(CalendarDisplayAbsence(shift.title, kind, 1))\n                        }\n                    }\n                    d = d.plusDays(1)\n                }\n            } else {\n                val d = shift.start.toLocalDate()\n                if (!d.isBefore(firstDay) && !d.isAfter(lastDay)) {\n                    matchedAny = true\n                    val startText = String.format("%d:%02d", shift.start.hour, shift.start.minute)\n                    val endText = String.format("%d:%02d", shift.end.hour, shift.end.minute)\n                    val startMin = shift.start.hour * 60 + shift.start.minute\n                    val endMin = shift.end.hour * 60 + shift.end.minute\n                    val list = shiftsByDate.getOrPut(d) { mutableListOf() }\n                    list.add(\n                        CalendarDisplayShift(\n                            startText = startText,\n                            endText = endText,\n                            startMinutes = startMin,\n                            endMinutes = endMin,\n                            location = shift.location,\n                            shiftName = shift.title.takeUnless { it.equals("Työvuoro", true) }.orEmpty(),\n                            role = shift.description.lineSequence().firstOrNull().orEmpty(),\n                            rawTitle = shift.title\n                        )\n                    )\n                }\n            }\n        }\n\n        if (!matchedAny) return null\n        val allDates = (shiftsByDate.keys + absencesByDate.keys)\n        val dayMap = mutableMapOf<LocalDate, CalendarDisplayDay>()\n        for (d in allDates) {\n            dayMap[d] = CalendarDisplayDay(\n                date = d,\n                shifts = shiftsByDate[d].orEmpty(),\n                absences = absencesByDate[d].orEmpty(),\n                requests = emptyList(),\n                hasCommentCircle = false\n            )\n        }\n        return MonthDisplayData(year = year, month = month, days = dayMap)\n    }\n}\n'

NATIVE_SHIFTS_VIEW_KT = 'package fi.numeron.vuorovahti\n\nimport android.content.Context\nimport android.graphics.Color\nimport android.graphics.Typeface\nimport android.graphics.drawable.GradientDrawable\nimport android.text.TextUtils\nimport android.util.TypedValue\nimport android.view.Gravity\nimport android.view.View\nimport android.webkit.CookieManager\nimport android.widget.Button\nimport android.widget.FrameLayout\nimport android.widget.LinearLayout\nimport android.widget.ProgressBar\nimport android.widget.ScrollView\nimport android.widget.TextView\nimport androidx.appcompat.app.AlertDialog\nimport kotlinx.coroutines.CoroutineScope\nimport kotlinx.coroutines.Dispatchers\nimport kotlinx.coroutines.Job\nimport kotlinx.coroutines.launch\nimport kotlinx.coroutines.withContext\nimport java.net.URLEncoder\nimport java.time.DayOfWeek\nimport java.time.LocalDate\nimport java.time.YearMonth\nimport java.time.format.DateTimeFormatter\nimport java.time.temporal.WeekFields\n\nclass NativeShiftsView(\n    private val context: Context,\n    private val scope: CoroutineScope,\n    private val onOpenWebUrl: (url: String, title: String) -> Unit\n) : LinearLayout(context) {\n\n    private var displayedMonth: YearMonth = YearMonth.now()\n    private var currentData: MonthDisplayData? = null\n    private var loadJob: Job? = null\n\n    private val txtMonthTitle: TextView\n    private val btnPrev: Button\n    private val btnNext: Button\n    private val btnToday: Button\n    private val btnRefresh: Button\n    private val progressBar: ProgressBar\n    private val txtStatus: TextView\n    private val gridContainer: LinearLayout\n\n    private val fiMonths = arrayOf(\n        "Tammikuu", "Helmikuu", "Maaliskuu", "Huhtikuu", "Toukokuu", "Kesäkuu",\n        "Heinäkuu", "Elokuu", "Syyskuu", "Lokakuu", "Marraskuu", "Joulukuu"\n    )\n    private val enMonths = arrayOf(\n        "January", "February", "March", "April", "May", "June",\n        "July", "August", "September", "October", "November", "December"\n    )\n    private val fiShortMonths = arrayOf(\n        "Tammi", "Helmi", "Maalis", "Huhti", "Touko", "Kesä",\n        "Heinä", "Elo", "Syys", "Loka", "Marras", "Joulu"\n    )\n    private val enShortMonths = arrayOf(\n        "Jan", "Feb", "Mar", "Apr", "May", "Jun",\n        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"\n    )\n\n    init {\n        orientation = VERTICAL\n        setBackgroundColor(Color.parseColor("#0F1722"))\n        setPadding(dp(8), dp(8), dp(8), dp(4))\n\n        // Yläkortti: kuukausivalitsin + pikapainikkeet\n        val headerCard = LinearLayout(context).apply {\n            orientation = VERTICAL\n            background = roundedBg("#182332", "#2A394A", 12f)\n            setPadding(dp(10), dp(10), dp(10), dp(8))\n        }\n\n        val navRow = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n            gravity = Gravity.CENTER_VERTICAL\n        }\n\n        btnPrev = Button(context).apply {\n            text = "◀"\n            setTextColor(Color.parseColor("#38BDF8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)\n            background = roundedBg("#233040", "#37475A", 10f)\n            setPadding(0, 0, 0, 0)\n            setOnClickListener {\n                displayedMonth = displayedMonth.minusMonths(1)\n                loadMonth(forceNetwork = true)\n            }\n        }\n        navRow.addView(btnPrev, LayoutParams(dp(44), dp(38)))\n\n        txtMonthTitle = TextView(context).apply {\n            setTextColor(Color.parseColor("#F1F5F9"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)\n            setTypeface(null, Typeface.BOLD)\n            gravity = Gravity.CENTER\n            background = roundedBg("#111923", "#2A394A", 10f)\n            setPadding(dp(12), dp(7), dp(12), dp(7))\n            setOnClickListener { showMonthJumpDialog() }\n        }\n        navRow.addView(\n            txtMonthTitle,\n            LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f).apply {\n                marginStart = dp(10)\n                marginEnd = dp(10)\n            }\n        )\n\n        btnNext = Button(context).apply {\n            text = "▶"\n            setTextColor(Color.parseColor("#38BDF8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)\n            background = roundedBg("#233040", "#37475A", 10f)\n            setPadding(0, 0, 0, 0)\n            setOnClickListener {\n                displayedMonth = displayedMonth.plusMonths(1)\n                loadMonth(forceNetwork = true)\n            }\n        }\n        navRow.addView(btnNext, LayoutParams(dp(44), dp(38)))\n\n        headerCard.addView(navRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        val actionRow = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n            gravity = Gravity.CENTER_VERTICAL\n            setPadding(0, dp(8), 0, 0)\n        }\n\n        btnToday = Button(context).apply {\n            isAllCaps = false\n            setTextColor(Color.parseColor("#E2E8F0"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)\n            background = roundedBg("#233040", "#37475A", 8f)\n            setPadding(dp(12), dp(4), dp(12), dp(4))\n            minHeight = 0\n            minimumHeight = dp(32)\n            setOnClickListener {\n                displayedMonth = YearMonth.now()\n                loadMonth(forceNetwork = true)\n            }\n        }\n        actionRow.addView(btnToday, LayoutParams(LayoutParams.WRAP_CONTENT, dp(32)))\n\n        btnRefresh = Button(context).apply {\n            isAllCaps = false\n            setTextColor(Color.parseColor("#38BDF8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)\n            background = roundedBg("#233040", "#37475A", 8f)\n            setPadding(dp(12), dp(4), dp(12), dp(4))\n            minHeight = 0\n            minimumHeight = dp(32)\n            setOnClickListener { loadMonth(forceNetwork = true) }\n        }\n        actionRow.addView(\n            btnRefresh,\n            LayoutParams(LayoutParams.WRAP_CONTENT, dp(32)).apply {\n                marginStart = dp(8)\n            }\n        )\n\n        val spacer = View(context)\n        actionRow.addView(spacer, LayoutParams(0, 1, 1f))\n\n        progressBar = ProgressBar(context, null, android.R.attr.progressBarStyleSmall).apply {\n            isIndeterminate = true\n            visibility = View.GONE\n        }\n        actionRow.addView(progressBar, LayoutParams(dp(18), dp(18)))\n\n        txtStatus = TextView(context).apply {\n            setTextColor(Color.parseColor("#94A3B8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)\n            setPadding(dp(6), 0, 0, 0)\n        }\n        actionRow.addView(txtStatus, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))\n\n        headerCard.addView(actionRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n        addView(\n            headerCard,\n            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                bottomMargin = dp(8)\n            }\n        )\n\n        val scroll = ScrollView(context).apply {\n            isFillViewport = true\n        }\n        gridContainer = LinearLayout(context).apply {\n            orientation = VERTICAL\n        }\n        scroll.addView(gridContainer, FrameLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n        addView(scroll, LayoutParams(LayoutParams.MATCH_PARENT, 0, 1f))\n    }\n\n    fun onShow(forceNetwork: Boolean = false) {\n        updateLocalizedLabels()\n        loadMonth(forceNetwork = forceNetwork)\n    }\n\n    fun refreshFromCacheAndNetwork() {\n        updateLocalizedLabels()\n        loadMonth(forceNetwork = true)\n    }\n\n    private fun updateLocalizedLabels() {\n        val en = DemoModeHelper.isEnglish(context)\n        val monthName = (if (en) enMonths else fiMonths)[displayedMonth.monthValue - 1]\n        txtMonthTitle.text = "$monthName ${displayedMonth.year} ▾"\n        btnToday.text = if (en) "Today" else "Tänään"\n        btnRefresh.text = if (en) "↻ Refresh" else "↻ Päivitä"\n    }\n\n    private fun loadMonth(forceNetwork: Boolean) {\n        val ym = displayedMonth\n        val en = DemoModeHelper.isEnglish(context)\n        updateLocalizedLabels()\n        loadJob?.cancel()\n\n        if (DemoModeHelper.isDemoEnabled(context)) {\n            progressBar.visibility = View.GONE\n            txtStatus.text = if (en) "Demo" else "Demo"\n            val demoShifts = DemoModeHelper.generateDemoWorkShifts(context)\n            currentData = NumeronApiClient.buildMonthDisplayFromCachedShifts(demoShifts, ym.year, ym.monthValue)\n                ?: MonthDisplayData(ym.year, ym.monthValue, emptyMap())\n            renderCalendarGrid()\n            return\n        }\n\n        // 1. Näytetään heti välimuistista (0 ms viive)\n        val cachedMonth = NumeronApiClient.loadMonthDisplayCache(context, ym.year, ym.monthValue)\n        val fallbackCached = if (cachedMonth == null) {\n            CalendarSyncHelper.loadCachedShifts(context)?.let {\n                NumeronApiClient.buildMonthDisplayFromCachedShifts(it, ym.year, ym.monthValue)\n            }\n        } else {\n            null\n        }\n\n        currentData = cachedMonth ?: fallbackCached ?: MonthDisplayData(ym.year, ym.monthValue, emptyMap())\n        renderCalendarGrid()\n\n        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n        if (baseUrl.isBlank()) {\n            progressBar.visibility = View.GONE\n            txtStatus.text = if (en) "Set organization in Settings" else "Aseta organisaatio asetuksista"\n            return\n        }\n\n        if (!forceNetwork && cachedMonth != null) {\n            // Haetaan silti taustalla tuore data hiljaisesti\n            txtStatus.text = if (en) "Updating..." else "Päivitetään..."\n        } else {\n            txtStatus.text = if (en) "Loading..." else "Ladataan..."\n        }\n        progressBar.visibility = View.VISIBLE\n\n        loadJob = scope.launch {\n            val html = NumeronApiClient.fetchMonthCalendarHtml(context, ym.year, ym.monthValue)\n            if (ym != displayedMonth) return@launch\n\n            progressBar.visibility = View.GONE\n            if (html != null) {\n                val parsed = withContext(Dispatchers.Default) {\n                    NumeronParser.parseMonthForDisplay(html)\n                }\n                if (parsed != null) {\n                    withContext(Dispatchers.IO) {\n                        NumeronApiClient.saveMonthDisplayCache(context, parsed)\n                    }\n                    currentData = parsed\n                    txtStatus.text = ""\n                    renderCalendarGrid()\n                    return@launch\n                }\n            }\n\n            txtStatus.text = if (cachedMonth != null || fallbackCached != null) {\n                if (en) "Offline cache" else "Välimuisti"\n            } else {\n                if (en) "Could not load" else "Lataus epäonnistui"\n            }\n        }\n    }\n\n    private fun renderCalendarGrid() {\n        gridContainer.removeAllViews()\n        val en = DemoModeHelper.isEnglish(context)\n        val ym = displayedMonth\n        val today = LocalDate.now()\n        val dayMap = currentData?.days.orEmpty()\n\n        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n        val morningRgb = prefs.getInt("color_morning_rgb", SettingsDialogHelper.DEFAULT_MORNING_RGB)\n        val eveningRgb = prefs.getInt("color_evening_rgb", SettingsDialogHelper.DEFAULT_EVENING_RGB)\n        val nightRgb = prefs.getInt("color_night_rgb", SettingsDialogHelper.DEFAULT_NIGHT_RGB)\n\n        // Otsikkorivi: Vko + Ma..Su\n        val headerRow = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n        }\n        val dayHeaders = if (en) {\n            arrayOf("Wk", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")\n        } else {\n            arrayOf("Vko", "Ma", "Ti", "Ke", "To", "Pe", "La", "Su")\n        }\n        for (i in dayHeaders.indices) {\n            val tv = TextView(context).apply {\n                text = dayHeaders[i]\n                gravity = Gravity.CENTER\n                setTextColor(Color.parseColor("#CBD5E1"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, if (i == 0) 10f else 11.5f)\n                setTypeface(null, Typeface.BOLD)\n                background = cellBg("#233040", "#2A394A")\n                setPadding(dp(1), dp(6), dp(1), dp(6))\n            }\n            val lp = if (i == 0) LayoutParams(dp(26), LayoutParams.WRAP_CONTENT) else LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f)\n            headerRow.addView(tv, lp)\n        }\n        gridContainer.addView(headerRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        val firstOfMonth = ym.atDay(1)\n        val lastOfMonth = ym.atEndOfMonth()\n        val startMonday = firstOfMonth.with(DayOfWeek.MONDAY)\n        val endSunday = lastOfMonth.with(DayOfWeek.SUNDAY)\n\n        var weekStart = startMonday\n        val weekFields = WeekFields.ISO\n\n        while (!weekStart.isAfter(endSunday)) {\n            val row = LinearLayout(context).apply {\n                orientation = HORIZONTAL\n                minimumHeight = dp(72)\n            }\n\n            // Viikkonumero\n            val weekNum = weekStart.get(weekFields.weekOfWeekBasedYear())\n            val wkTv = TextView(context).apply {\n                text = weekNum.toString()\n                gravity = Gravity.TOP or Gravity.CENTER_HORIZONTAL\n                setTextColor(Color.parseColor("#64748B"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 10f)\n                background = cellBg("#131C28", "#2A394A")\n                setPadding(dp(1), dp(5), dp(1), dp(4))\n            }\n            row.addView(wkTv, LayoutParams(dp(26), LayoutParams.MATCH_PARENT))\n\n            for (offset in 0..6) {\n                val date = weekStart.plusDays(offset.toLong())\n                val isCurrentMonth = (date.monthValue == ym.monthValue && date.year == ym.year)\n                val isToday = (date == today)\n                val isPast = date.isBefore(today)\n                val dayData = dayMap[date]\n\n                val cellBgColor = when {\n                    isToday -> "#1E3A5F"\n                    !isCurrentMonth || isPast -> "#121A24"\n                    else -> "#182332"\n                }\n                val cellBorderColor = if (isToday) "#38BDF8" else "#2A394A"\n\n                val cell = LinearLayout(context).apply {\n                    orientation = VERTICAL\n                    background = cellBg(cellBgColor, cellBorderColor)\n                    setPadding(dp(2), dp(2), dp(2), dp(3))\n                    minimumHeight = dp(72)\n                    if (isCurrentMonth) {\n                        setOnClickListener { showDayDetailsDialog(date, dayData) }\n                    }\n                }\n\n                // Päivänumero + kommenttipallukka\n                val topRow = LinearLayout(context).apply {\n                    orientation = HORIZONTAL\n                    gravity = Gravity.CENTER_VERTICAL\n                }\n                val numTv = TextView(context).apply {\n                    text = date.dayOfMonth.toString()\n                    setTextColor(\n                        if (!isCurrentMonth) Color.parseColor("#64748B")\n                        else if (isToday) Color.parseColor("#38BDF8")\n                        else Color.parseColor("#F1F5F9")\n                    )\n                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)\n                    setTypeface(null, Typeface.BOLD)\n                    setPadding(dp(2), 0, 0, dp(1))\n                }\n                topRow.addView(numTv, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))\n\n                if (dayData?.hasCommentCircle == true) {\n                    val dot = View(context).apply {\n                        background = GradientDrawable().apply {\n                            shape = GradientDrawable.OVAL\n                            setColor(Color.parseColor("#F59E0B"))\n                        }\n                    }\n                    topRow.addView(\n                        dot,\n                        LayoutParams(dp(6), dp(6)).apply {\n                            marginEnd = dp(2)\n                        }\n                    )\n                }\n                cell.addView(topRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n                // Poissaolot (loma, sairaus, koulutus/muu)\n                dayData?.absences?.forEach { abs ->\n                    val (bgHex, fgHex) = when (abs.kind) {\n                        "vacation" -> "#15803D" to "#FFFFFF"\n                        "sick" -> "#B91C1C" to "#FFFFFF"\n                        else -> "#334155" to "#F1F5F9"\n                    }\n                    val badge = TextView(context).apply {\n                        text = abs.title\n                        setTextColor(Color.parseColor(fgHex))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 9.5f)\n                        setTypeface(null, Typeface.BOLD)\n                        maxLines = 1\n                        ellipsize = TextUtils.TruncateAt.END\n                        background = roundedBg(bgHex, bgHex, 4f)\n                        setPadding(dp(3), dp(1), dp(3), dp(1))\n                    }\n                    cell.addView(\n                        badge,\n                        LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                            bottomMargin = dp(2)\n                        }\n                    )\n                }\n\n                // Työvuorot asetusten värikoodeilla\n                dayData?.shifts?.forEach { shift ->\n                    val bgRgb = pickShiftRgb(shift, morningRgb, eveningRgb, nightRgb)\n                    val fgColor = contrastColor(bgRgb)\n                    val label = "${shift.startText}\\n${shift.endText}"\n                    val badge = TextView(context).apply {\n                        text = label\n                        setTextColor(fgColor)\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 10f)\n                        setTypeface(null, Typeface.BOLD)\n                        gravity = Gravity.CENTER\n                        maxLines = 2\n                        background = GradientDrawable().apply {\n                            shape = GradientDrawable.RECTANGLE\n                            cornerRadius = dp(4).toFloat()\n                            setColor(bgRgb)\n                        }\n                        setPadding(dp(2), dp(2), dp(2), dp(2))\n                    }\n                    cell.addView(\n                        badge,\n                        LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                            bottomMargin = dp(2)\n                        }\n                    )\n                }\n\n                // Toiveet\n                dayData?.requests?.forEach { req ->\n                    val badge = TextView(context).apply {\n                        text = req.title\n                        setTextColor(Color.parseColor("#EDE9FE"))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 9.5f)\n                        setTypeface(null, Typeface.BOLD)\n                        maxLines = 1\n                        ellipsize = TextUtils.TruncateAt.END\n                        background = roundedBg("#2E1F47", "#8B5CF6", 4f)\n                        setPadding(dp(3), dp(1), dp(3), dp(1))\n                    }\n                    cell.addView(\n                        badge,\n                        LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                            bottomMargin = dp(2)\n                        }\n                    )\n                }\n\n                row.addView(cell, LayoutParams(0, LayoutParams.MATCH_PARENT, 1f))\n            }\n\n            gridContainer.addView(row, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n            weekStart = weekStart.plusWeeks(1)\n        }\n    }\n\n    private fun showDayDetailsDialog(date: LocalDate, dayData: CalendarDisplayDay?) {\n        val en = DemoModeHelper.isEnglish(context)\n        val fiWeekdays = arrayOf("Ma", "Ti", "Ke", "To", "Pe", "La", "Su")\n        val enWeekdays = arrayOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")\n        val dowStr = (if (en) enWeekdays else fiWeekdays)[date.dayOfWeek.value - 1]\n        val dateStr = date.format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))\n\n        val root = LinearLayout(context).apply {\n            orientation = VERTICAL\n            setBackgroundColor(Color.parseColor("#182332"))\n            setPadding(dp(18), dp(16), dp(18), dp(14))\n        }\n\n        val titleTv = TextView(context).apply {\n            text = "$dowStr $dateStr"\n            setTextColor(Color.parseColor("#F1F5F9"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)\n            setTypeface(null, Typeface.BOLD)\n        }\n        root.addView(titleTv)\n\n        val contentBox = LinearLayout(context).apply {\n            orientation = VERTICAL\n            setPadding(0, dp(10), 0, dp(10))\n        }\n\n        var hasAny = false\n        dayData?.shifts?.forEach { shift ->\n            hasAny = true\n            val card = LinearLayout(context).apply {\n                orientation = VERTICAL\n                background = roundedBg("#111923", "#2A394A", 10f)\n                setPadding(dp(12), dp(10), dp(12), dp(10))\n            }\n            card.addView(\n                TextView(context).apply {\n                    text = "${shift.startText} – ${shift.endText}"\n                    setTextColor(Color.parseColor("#38BDF8"))\n                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)\n                    setTypeface(null, Typeface.BOLD)\n                }\n            )\n            if (shift.location.isNotEmpty()) {\n                card.addView(\n                    TextView(context).apply {\n                        text = shift.location\n                        setTextColor(Color.parseColor("#F1F5F9"))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)\n                        setTypeface(null, Typeface.BOLD)\n                        setPadding(0, dp(2), 0, 0)\n                    }\n                )\n            }\n            val sub = listOf(shift.shiftName, shift.role).filter { it.isNotBlank() }.joinToString(" • ")\n            if (sub.isNotEmpty()) {\n                card.addView(\n                    TextView(context).apply {\n                        text = sub\n                        setTextColor(Color.parseColor("#CBD5E1"))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n                        setPadding(0, dp(2), 0, 0)\n                    }\n                )\n            }\n            contentBox.addView(\n                card,\n                LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                    bottomMargin = dp(8)\n                }\n            )\n        }\n\n        dayData?.absences?.forEach { abs ->\n            hasAny = true\n            val borderHex = when (abs.kind) {\n                "vacation" -> "#22C55E"\n                "sick" -> "#F87171"\n                else -> "#64748B"\n            }\n            val tv = TextView(context).apply {\n                text = abs.title\n                setTextColor(Color.parseColor("#F1F5F9"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)\n                setTypeface(null, Typeface.BOLD)\n                background = roundedBg("#111923", borderHex, 8f)\n                setPadding(dp(12), dp(9), dp(12), dp(9))\n            }\n            contentBox.addView(\n                tv,\n                LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                    bottomMargin = dp(8)\n                }\n            )\n        }\n\n        dayData?.requests?.forEach { req ->\n            hasAny = true\n            val tv = TextView(context).apply {\n                text = (if (en) "Request: " else "Toive: ") + req.title\n                setTextColor(Color.parseColor("#EDE9FE"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)\n                background = roundedBg("#2E1F47", "#8B5CF6", 8f)\n                setPadding(dp(12), dp(9), dp(12), dp(9))\n            }\n            contentBox.addView(\n                tv,\n                LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                    bottomMargin = dp(8)\n                }\n            )\n        }\n\n        if (!hasAny) {\n            contentBox.addView(\n                TextView(context).apply {\n                    text = if (en) "No scheduled shifts" else "Ei merkittyjä vuoroja"\n                    setTextColor(Color.parseColor("#94A3B8"))\n                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)\n                }\n            )\n        }\n\n        val commentTv = TextView(context).apply {\n            setTextColor(Color.parseColor("#FDE68A"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n            background = roundedBg("#2A2210", "#F59E0B", 8f)\n            setPadding(dp(10), dp(8), dp(10), dp(8))\n            visibility = if (dayData?.hasCommentCircle == true && !DemoModeHelper.isDemoEnabled(context)) View.VISIBLE else View.GONE\n            text = if (en) "Loading shift comment..." else "Haetaan vuorokommenttia..."\n        }\n        contentBox.addView(\n            commentTv,\n            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                bottomMargin = dp(8)\n            }\n        )\n\n        root.addView(contentBox)\n\n        val dialog = AlertDialog.Builder(context)\n            .setView(root)\n            .create()\n\n        if (!DemoModeHelper.isDemoEnabled(context)) {\n            val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n            val btnRow = LinearLayout(context).apply {\n                orientation = HORIZONTAL\n            }\n            val isoDate = date.toString()\n            val listDateParam = URLEncoder.encode("${date.monthValue}/${date.dayOfMonth}/${date.year} 00:00:00", "UTF-8")\n\n            val btnAddReq = Button(context).apply {\n                text = if (en) "+ Add Request" else "+ Lisää toive"\n                isAllCaps = false\n                setTextColor(Color.WHITE)\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)\n                setTypeface(null, Typeface.BOLD)\n                background = roundedBg("#1982C4", "#38BDF8", 8f)\n                setOnClickListener {\n                    dialog.dismiss()\n                    if (baseUrl.isNotBlank()) {\n                        onOpenWebUrl(\n                            "$baseUrl/PersonRequests/Edit?calendarView=Month&returnValue=$isoDate",\n                            if (en) "New request ($dateStr)" else "Uusi toive ($dateStr)"\n                        )\n                    }\n                }\n            }\n            btnRow.addView(\n                btnAddReq,\n                LayoutParams(0, dp(40), 1f).apply {\n                    marginEnd = dp(8)\n                }\n            )\n\n            val btnOpenDay = Button(context).apply {\n                text = if (en) "Open day" else "Avaa päivä"\n                isAllCaps = false\n                setTextColor(Color.parseColor("#E2E8F0"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)\n                background = roundedBg("#233040", "#37475A", 8f)\n                setOnClickListener {\n                    dialog.dismiss()\n                    if (baseUrl.isNotBlank()) {\n                        onOpenWebUrl(\n                            "$baseUrl/Calendar/List?date=$listDateParam",\n                            dateStr\n                        )\n                    }\n                }\n            }\n            btnRow.addView(btnOpenDay, LayoutParams(0, dp(40), 1f))\n            root.addView(btnRow)\n\n            if (dayData?.hasCommentCircle == true && baseUrl.isNotBlank()) {\n                scope.launch {\n                    val comment = withContext(Dispatchers.IO) {\n                        val cookies = try {\n                            CookieManager.getInstance().getCookie(baseUrl)\n                        } catch (_: Exception) {\n                            null\n                        }\n                        NumeronParser.fetchDayComments(baseUrl, cookies, date)\n                    }\n                    if (dialog.isShowing) {\n                        if (!comment.isNullOrBlank()) {\n                            commentTv.text = (if (en) "Note: " else "Huomio: ") + comment\n                            commentTv.visibility = View.VISIBLE\n                        } else {\n                            commentTv.visibility = View.GONE\n                        }\n                    }\n                }\n            }\n        }\n\n        val btnClose = Button(context).apply {\n            text = if (en) "Close" else "Sulje"\n            isAllCaps = false\n            setTextColor(Color.parseColor("#CBD5E1"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n            background = roundedBg("#233040", "#37475A", 8f)\n            setOnClickListener { dialog.dismiss() }\n        }\n        root.addView(\n            btnClose,\n            LayoutParams(LayoutParams.MATCH_PARENT, dp(38)).apply {\n                topMargin = dp(8)\n            }\n        )\n\n        dialog.window?.setBackgroundDrawable(GradientDrawable().apply {\n            cornerRadius = dp(14).toFloat()\n            setColor(Color.parseColor("#182332"))\n            setStroke(dp(1), Color.parseColor("#38BDF8"))\n        })\n        dialog.show()\n    }\n\n    private fun showMonthJumpDialog() {\n        val en = DemoModeHelper.isEnglish(context)\n        val shortNames = if (en) enShortMonths else fiShortMonths\n        var selectedYear = displayedMonth.year\n        val realNow = YearMonth.now()\n\n        val root = LinearLayout(context).apply {\n            orientation = VERTICAL\n            setBackgroundColor(Color.parseColor("#182332"))\n            setPadding(dp(16), dp(16), dp(16), dp(14))\n        }\n\n        root.addView(\n            TextView(context).apply {\n                text = if (en) "JUMP TO MONTH & YEAR" else "SIIRRY KUUKAUTEEN JA VUOTEEN"\n                setTextColor(Color.parseColor("#38BDF8"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)\n                setTypeface(null, Typeface.BOLD)\n                gravity = Gravity.CENTER\n                setPadding(0, 0, 0, dp(10))\n            }\n        )\n\n        val yearRow = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n            gravity = Gravity.CENTER_VERTICAL\n            background = roundedBg("#111923", "#2A394A", 10f)\n            setPadding(dp(8), dp(6), dp(8), dp(6))\n        }\n\n        val yearLabel = TextView(context).apply {\n            text = selectedYear.toString()\n            setTextColor(Color.parseColor("#F1F5F9"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)\n            setTypeface(null, Typeface.BOLD)\n            gravity = Gravity.CENTER\n        }\n\n        val gridHost = LinearLayout(context).apply {\n            orientation = VERTICAL\n            setPadding(0, dp(12), 0, dp(12))\n        }\n\n        val dialog = AlertDialog.Builder(context)\n            .setView(root)\n            .create()\n\n        fun renderMonths() {\n            yearLabel.text = selectedYear.toString()\n            gridHost.removeAllViews()\n            for (r in 0..3) {\n                val mRow = LinearLayout(context).apply {\n                    orientation = HORIZONTAL\n                }\n                for (c in 0..2) {\n                    val mVal = r * 3 + c + 1\n                    val isSelected = (selectedYear == displayedMonth.year && mVal == displayedMonth.monthValue)\n                    val isCurrent = (selectedYear == realNow.year && mVal == realNow.monthValue)\n                    val bgHex = if (isSelected) "#1982C4" else "#111923"\n                    val borderHex = if (isSelected || isCurrent) "#38BDF8" else "#2A394A"\n                    val btn = Button(context).apply {\n                        text = shortNames[mVal - 1]\n                        isAllCaps = false\n                        setTextColor(if (isSelected) Color.WHITE else Color.parseColor("#E2E8F0"))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n                        setTypeface(null, Typeface.BOLD)\n                        background = roundedBg(bgHex, borderHex, 8f)\n                        setOnClickListener {\n                            dialog.dismiss()\n                            displayedMonth = YearMonth.of(selectedYear, mVal)\n                            loadMonth(forceNetwork = true)\n                        }\n                    }\n                    mRow.addView(\n                        btn,\n                        LayoutParams(0, dp(40), 1f).apply {\n                            setMargins(dp(3), dp(3), dp(3), dp(3))\n                        }\n                    )\n                }\n                gridHost.addView(mRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n            }\n        }\n\n        val btnPrevYear = Button(context).apply {\n            text = "◀"\n            setTextColor(Color.parseColor("#38BDF8"))\n            background = roundedBg("#233040", "#37475A", 8f)\n            setOnClickListener {\n                selectedYear -= 1\n                renderMonths()\n            }\n        }\n        val btnNextYear = Button(context).apply {\n            text = "▶"\n            setTextColor(Color.parseColor("#38BDF8"))\n            background = roundedBg("#233040", "#37475A", 8f)\n            setOnClickListener {\n                selectedYear += 1\n                renderMonths()\n            }\n        }\n\n        yearRow.addView(btnPrevYear, LayoutParams(dp(42), dp(36)))\n        yearRow.addView(yearLabel, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))\n        yearRow.addView(btnNextYear, LayoutParams(dp(42), dp(36)))\n\n        root.addView(yearRow)\n        root.addView(gridHost)\n\n        val footer = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n        }\n        val btnNow = Button(context).apply {\n            text = if (en) "Current month" else "Nykyinen kuukausi"\n            isAllCaps = false\n            setTextColor(Color.parseColor("#38BDF8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n            background = roundedBg("#233040", "#37475A", 8f)\n            setOnClickListener {\n                dialog.dismiss()\n                displayedMonth = YearMonth.now()\n                loadMonth(forceNetwork = true)\n            }\n        }\n        val btnCancel = Button(context).apply {\n            text = if (en) "Cancel" else "Peruuta"\n            isAllCaps = false\n            setTextColor(Color.parseColor("#CBD5E1"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n            background = roundedBg("#233040", "#37475A", 8f)\n            setOnClickListener { dialog.dismiss() }\n        }\n        footer.addView(btnNow, LayoutParams(0, dp(38), 1f).apply { marginEnd = dp(8) })\n        footer.addView(btnCancel, LayoutParams(0, dp(38), 1f))\n        root.addView(footer)\n\n        renderMonths()\n        dialog.window?.setBackgroundDrawable(GradientDrawable().apply {\n            cornerRadius = dp(14).toFloat()\n            setColor(Color.parseColor("#182332"))\n            setStroke(dp(1), Color.parseColor("#38BDF8"))\n        })\n        dialog.show()\n    }\n\n    private fun pickShiftRgb(\n        shift: CalendarDisplayShift,\n        morningRgb: Int,\n        eveningRgb: Int,\n        nightRgb: Int\n    ): Int {\n        val crossesMidnight = shift.endMinutes < shift.startMinutes\n        return when {\n            crossesMidnight || shift.startMinutes >= 20 * 60 || shift.startMinutes < 4 * 60 -> nightRgb\n            shift.startMinutes >= 11 * 60 + 30 -> eveningRgb\n            else -> morningRgb\n        }\n    }\n\n    private fun contrastColor(rgb: Int): Int {\n        val lum = 0.299 * Color.red(rgb) + 0.587 * Color.green(rgb) + 0.114 * Color.blue(rgb)\n        return if (lum > 150.0) Color.parseColor("#0F1722") else Color.WHITE\n    }\n\n    private fun roundedBg(fillHex: String, strokeHex: String, radiusDp: Float): GradientDrawable {\n        return GradientDrawable().apply {\n            shape = GradientDrawable.RECTANGLE\n            cornerRadius = dp(radiusDp.toInt()).toFloat()\n            setColor(Color.parseColor(fillHex))\n            setStroke(dp(1), Color.parseColor(strokeHex))\n        }\n    }\n\n    private fun cellBg(fillHex: String, strokeHex: String): GradientDrawable {\n        return GradientDrawable().apply {\n            shape = GradientDrawable.RECTANGLE\n            setColor(Color.parseColor(fillHex))\n            setStroke(1, Color.parseColor(strokeHex))\n        }\n    }\n\n    private fun dp(value: Int): Int {\n        return TypedValue.applyDimension(\n            TypedValue.COMPLEX_UNIT_DIP,\n            value.toFloat(),\n            resources.displayMetrics\n        ).toInt()\n    }\n}\n'

NATIVE_REQUESTS_VIEW_KT = 'package fi.numeron.vuorovahti\n\nimport android.content.Context\nimport android.graphics.Color\nimport android.graphics.Typeface\nimport android.graphics.drawable.GradientDrawable\nimport android.util.TypedValue\nimport android.view.Gravity\nimport android.view.View\nimport android.widget.Button\nimport android.widget.FrameLayout\nimport android.widget.LinearLayout\nimport android.widget.ProgressBar\nimport android.widget.ScrollView\nimport android.widget.TextView\nimport android.widget.Toast\nimport kotlinx.coroutines.CoroutineScope\nimport kotlinx.coroutines.Job\nimport kotlinx.coroutines.launch\nimport java.time.Instant\nimport java.time.LocalDate\nimport java.time.ZoneId\nimport java.time.format.DateTimeFormatter\n\nclass NativeRequestsView(\n    private val context: Context,\n    private val scope: CoroutineScope,\n    private val onOpenWebUrl: (url: String, title: String) -> Unit\n) : LinearLayout(context) {\n\n    private var currentFilter: String = "active"\n    private var loadJob: Job? = null\n\n    private val txtTitle: TextView\n    private val btnAdd: Button\n    private val btnRefresh: Button\n    private val btnFilterActive: Button\n    private val btnFilterOld: Button\n    private val btnFilterRemoved: Button\n    private val progressBar: ProgressBar\n    private val txtStatus: TextView\n    private val listContainer: LinearLayout\n\n    private val dateFmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")\n    private val dateTimeFmt = DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm")\n\n    init {\n        orientation = VERTICAL\n        setBackgroundColor(Color.parseColor("#0F1722"))\n        setPadding(dp(10), dp(10), dp(10), dp(4))\n\n        val topCard = LinearLayout(context).apply {\n            orientation = VERTICAL\n            background = roundedBg("#182332", "#2A394A", 12f)\n            setPadding(dp(12), dp(10), dp(12), dp(10))\n        }\n\n        val titleRow = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n            gravity = Gravity.CENTER_VERTICAL\n        }\n\n        txtTitle = TextView(context).apply {\n            setTextColor(Color.parseColor("#F1F5F9"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)\n            setTypeface(null, Typeface.BOLD)\n        }\n        titleRow.addView(txtTitle, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))\n\n        btnRefresh = Button(context).apply {\n            text = "↻"\n            setTextColor(Color.parseColor("#38BDF8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)\n            background = roundedBg("#233040", "#37475A", 8f)\n            setPadding(0, 0, 0, 0)\n            setOnClickListener { loadRequests(forceNetwork = true) }\n        }\n        titleRow.addView(\n            btnRefresh,\n            LayoutParams(dp(40), dp(36)).apply {\n                marginEnd = dp(8)\n            }\n        )\n\n        btnAdd = Button(context).apply {\n            isAllCaps = false\n            setTextColor(Color.WHITE)\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)\n            setTypeface(null, Typeface.BOLD)\n            background = roundedBg("#1982C4", "#38BDF8", 8f)\n            setPadding(dp(14), dp(4), dp(14), dp(4))\n            minHeight = 0\n            minimumHeight = dp(36)\n            setOnClickListener { openNewRequest() }\n        }\n        titleRow.addView(btnAdd, LayoutParams(LayoutParams.WRAP_CONTENT, dp(36)))\n        topCard.addView(titleRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        // Suodatinpainikkeet\n        val filterRow = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n            setPadding(0, dp(10), 0, 0)\n        }\n\n        btnFilterActive = makeFilterButton("active")\n        btnFilterOld = makeFilterButton("old")\n        btnFilterRemoved = makeFilterButton("removed")\n\n        filterRow.addView(btnFilterActive, LayoutParams(0, dp(34), 1f).apply { marginEnd = dp(6) })\n        filterRow.addView(btnFilterOld, LayoutParams(0, dp(34), 1f).apply { marginEnd = dp(6) })\n        filterRow.addView(btnFilterRemoved, LayoutParams(0, dp(34), 1f))\n        topCard.addView(filterRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        // Tilapalkki\n        val statusRow = LinearLayout(context).apply {\n            orientation = HORIZONTAL\n            gravity = Gravity.CENTER_VERTICAL\n            setPadding(0, dp(8), 0, 0)\n        }\n        progressBar = ProgressBar(context, null, android.R.attr.progressBarStyleSmall).apply {\n            isIndeterminate = true\n            visibility = View.GONE\n        }\n        statusRow.addView(progressBar, LayoutParams(dp(16), dp(16)))\n\n        txtStatus = TextView(context).apply {\n            setTextColor(Color.parseColor("#94A3B8"))\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)\n            setPadding(dp(6), 0, 0, 0)\n        }\n        statusRow.addView(txtStatus, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))\n        topCard.addView(statusRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n        addView(\n            topCard,\n            LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                bottomMargin = dp(8)\n            }\n        )\n\n        val scroll = ScrollView(context).apply {\n            isFillViewport = true\n        }\n        listContainer = LinearLayout(context).apply {\n            orientation = VERTICAL\n        }\n        scroll.addView(listContainer, FrameLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n        addView(scroll, LayoutParams(LayoutParams.MATCH_PARENT, 0, 1f))\n    }\n\n    private fun makeFilterButton(filterKey: String): Button {\n        return Button(context).apply {\n            isAllCaps = false\n            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)\n            setPadding(dp(6), dp(2), dp(6), dp(2))\n            minHeight = 0\n            minimumHeight = dp(34)\n            setOnClickListener {\n                if (currentFilter != filterKey) {\n                    currentFilter = filterKey\n                    updateFilterStyles()\n                    loadRequests(forceNetwork = true)\n                }\n            }\n        }\n    }\n\n    fun onShow(forceNetwork: Boolean = false) {\n        updateLocalizedLabels()\n        updateFilterStyles()\n        loadRequests(forceNetwork = forceNetwork)\n    }\n\n    fun refreshAfterWebEdit() {\n        updateLocalizedLabels()\n        loadRequests(forceNetwork = true)\n    }\n\n    private fun updateLocalizedLabels() {\n        val en = DemoModeHelper.isEnglish(context)\n        txtTitle.text = if (en) "Requests" else "Toiveet"\n        btnAdd.text = if (en) "+ Add" else "+ Lisää"\n        btnFilterActive.text = if (en) "Active" else "Aktiiviset"\n        btnFilterOld.text = if (en) "All / Old" else "Myös vanhat"\n        btnFilterRemoved.text = if (en) "Removed" else "Poistetut"\n    }\n\n    private fun updateFilterStyles() {\n        val pairs = listOf(\n            "active" to btnFilterActive,\n            "old" to btnFilterOld,\n            "removed" to btnFilterRemoved\n        )\n        for ((key, btn) in pairs) {\n            val selected = (key == currentFilter)\n            btn.background = roundedBg(\n                if (selected) "#1982C4" else "#111923",\n                if (selected) "#38BDF8" else "#2A394A",\n                8f\n            )\n            btn.setTextColor(if (selected) Color.WHITE else Color.parseColor("#CBD5E1"))\n            btn.setTypeface(null, if (selected) Typeface.BOLD else Typeface.NORMAL)\n        }\n    }\n\n    private fun openNewRequest() {\n        val en = DemoModeHelper.isEnglish(context)\n        if (DemoModeHelper.isDemoEnabled(context)) {\n            Toast.makeText(\n                context,\n                if (en) "Demo mode: Adding requests is disabled" else "Demotila: Toiveen lisäys ei ole käytössä demossa",\n                Toast.LENGTH_SHORT\n            ).show()\n            return\n        }\n        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n        if (baseUrl.isBlank()) {\n            Toast.makeText(\n                context,\n                if (en) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista",\n                Toast.LENGTH_LONG\n            ).show()\n            return\n        }\n        onOpenWebUrl("$baseUrl/PersonRequests/Edit", if (en) "New request" else "Uusi toive")\n    }\n\n    private fun loadRequests(forceNetwork: Boolean) {\n        val filter = currentFilter\n        val en = DemoModeHelper.isEnglish(context)\n        loadJob?.cancel()\n\n        if (DemoModeHelper.isDemoEnabled(context)) {\n            progressBar.visibility = View.GONE\n            txtStatus.text = if (en) "Demo mode" else "Demotila"\n            val today = LocalDate.now()\n            val demoItems = listOf(\n                PersonRequestItem(\n                    id = 1,\n                    type = if (en) "Day off" else "Vapaapäivä",\n                    dateFrom = today.plusDays(10),\n                    dateTo = today.plusDays(10),\n                    timeFromText = "",\n                    timeToText = "",\n                    info = if (en) "Family event" else "Perhejuhla",\n                    statusCode = 50,\n                    statusDescription = if (en) "Approved" else "Hyväksytty",\n                    belongsToSeries = false,\n                    approvedBy = "esimies@organisaatio.fi",\n                    approvedDateMs = System.currentTimeMillis() - 3600_000L * 5\n                ),\n                PersonRequestItem(\n                    id = 2,\n                    type = if (en) "Morning shift" else "Aamuvuoro",\n                    dateFrom = today.plusDays(14),\n                    dateTo = today.plusDays(14),\n                    timeFromText = "",\n                    timeToText = "",\n                    info = "",\n                    statusCode = 10,\n                    statusDescription = if (en) "Pending" else "Odottaa käsittelyä",\n                    belongsToSeries = false,\n                    approvedBy = "",\n                    approvedDateMs = null\n                )\n            )\n            renderRequests(if (filter == "removed") emptyList() else demoItems)\n            return\n        }\n\n        // 1. Näytetään heti paikallinen välimuisti\n        val cached = NumeronApiClient.loadCachedRequests(context, filter)\n        if (cached != null) {\n            renderRequests(cached)\n        }\n\n        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n        if (baseUrl.isBlank()) {\n            progressBar.visibility = View.GONE\n            txtStatus.text = if (en) "Set organization in Settings" else "Aseta organisaatio asetuksista"\n            return\n        }\n\n        progressBar.visibility = View.VISIBLE\n        txtStatus.text = if (cached != null && !forceNetwork) {\n            if (en) "Updating..." else "Päivitetään..."\n        } else {\n            if (en) "Loading requests..." else "Haetaan toiveita..."\n        }\n\n        loadJob = scope.launch {\n            val result = NumeronApiClient.fetchRequests(context, filter)\n            if (filter != currentFilter) return@launch\n            progressBar.visibility = View.GONE\n\n            if (result.items != null) {\n                renderRequests(result.items)\n                txtStatus.text = if (result.fromCache) {\n                    if (en) "Offline cache (${result.items.size})" else "Välimuisti (${result.items.size} kpl)"\n                } else {\n                    if (en) "${result.items.size} requests" else "${result.items.size} toivetta"\n                }\n            } else {\n                txtStatus.text = result.errorMessage ?: (if (en) "Failed to load" else "Haku epäonnistui")\n                if (cached == null) {\n                    renderRequests(emptyList())\n                }\n            }\n        }\n    }\n\n    private fun renderRequests(items: List<PersonRequestItem>) {\n        listContainer.removeAllViews()\n        val en = DemoModeHelper.isEnglish(context)\n\n        if (items.isEmpty()) {\n            val emptyCard = TextView(context).apply {\n                text = if (en) "No requests in this view." else "Ei toiveita tässä näkymässä."\n                setTextColor(Color.parseColor("#94A3B8"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)\n                gravity = Gravity.CENTER\n                background = roundedBg("#182332", "#2A394A", 12f)\n                setPadding(dp(16), dp(24), dp(16), dp(24))\n            }\n            listContainer.addView(emptyCard, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n            return\n        }\n\n        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)\n        val isDemo = DemoModeHelper.isDemoEnabled(context)\n\n        for (item in items) {\n            val card = LinearLayout(context).apply {\n                orientation = VERTICAL\n                background = roundedBg("#182332", "#2A394A", 12f)\n                setPadding(dp(14), dp(12), dp(14), dp(12))\n                setOnClickListener {\n                    if (isDemo) {\n                        Toast.makeText(\n                            context,\n                            if (en) "Demo mode: Editing is disabled" else "Demotila: Muokkaus ei ole käytössä demossa",\n                            Toast.LENGTH_SHORT\n                        ).show()\n                    } else if (baseUrl.isNotBlank()) {\n                        onOpenWebUrl("$baseUrl/PersonRequests/Edit/${item.id}", item.type)\n                    }\n                }\n            }\n\n            // Ylärivi: tyyppi + tilabadge\n            val topRow = LinearLayout(context).apply {\n                orientation = HORIZONTAL\n                gravity = Gravity.CENTER_VERTICAL\n            }\n\n            val typeTv = TextView(context).apply {\n                text = item.type\n                setTextColor(Color.parseColor("#F1F5F9"))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 15.5f)\n                setTypeface(null, Typeface.BOLD)\n            }\n            topRow.addView(typeTv, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))\n\n            val (badgeBg, badgeBorder, badgeFg) = when (item.statusCode) {\n                50 -> Triple("#0F2E26", "#22C55E", "#4ADE80")\n                40 -> Triple("#3B2810", "#F59E0B", "#FBBF24")\n                80 -> Triple("#3F1D24", "#EF4444", "#F87171")\n                else -> Triple("#1E3A5F", "#38BDF8", "#7DD3FC")\n            }\n\n            val statusTv = TextView(context).apply {\n                text = item.statusDescription\n                setTextColor(Color.parseColor(badgeFg))\n                setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)\n                setTypeface(null, Typeface.BOLD)\n                background = roundedBg(badgeBg, badgeBorder, 99f)\n                setPadding(dp(10), dp(3), dp(10), dp(3))\n            }\n            topRow.addView(\n                statusTv,\n                LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT).apply {\n                    marginStart = dp(8)\n                }\n            )\n            card.addView(topRow, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))\n\n            // Päivämäärä ja kellonaika\n            val dateLine = buildString {\n                if (item.dateFrom != null) {\n                    append(item.dateFrom.format(dateFmt))\n                    if (item.dateTo != null && item.dateTo != item.dateFrom) {\n                        append(" – ")\n                        append(item.dateTo.format(dateFmt))\n                    }\n                }\n                if (item.timeFromText.isNotEmpty() || item.timeToText.isNotEmpty()) {\n                    if (isNotEmpty()) append("  •  ")\n                    append(item.timeFromText)\n                    if (item.timeToText.isNotEmpty()) {\n                        append("–")\n                        append(item.timeToText)\n                    }\n                }\n                if (item.belongsToSeries) {\n                    if (isNotEmpty()) append("  •  ")\n                    append(if (en) "Recurring" else "Jatkuva")\n                }\n            }\n\n            if (dateLine.isNotEmpty()) {\n                card.addView(\n                    TextView(context).apply {\n                        text = dateLine\n                        setTextColor(Color.parseColor("#38BDF8"))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)\n                        setTypeface(null, Typeface.BOLD)\n                        setPadding(0, dp(6), 0, 0)\n                    }\n                )\n            }\n\n            if (item.info.isNotEmpty()) {\n                card.addView(\n                    TextView(context).apply {\n                        text = item.info\n                        setTextColor(Color.parseColor("#CBD5E1"))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)\n                        setPadding(0, dp(4), 0, 0)\n                    }\n                )\n            }\n\n            // Käsittelijä ja käsittelyaika\n            val metaParts = mutableListOf<String>()\n            if (item.approvedDateMs != null && item.approvedDateMs > 0L) {\n                val dtStr = Instant.ofEpochMilli(item.approvedDateMs)\n                    .atZone(ZoneId.systemDefault())\n                    .toLocalDateTime()\n                    .format(dateTimeFmt)\n                metaParts.add(dtStr)\n            }\n            if (item.approvedBy.isNotEmpty()) {\n                metaParts.add(item.approvedBy)\n            }\n            if (metaParts.isNotEmpty()) {\n                card.addView(\n                    TextView(context).apply {\n                        text = metaParts.joinToString(" • ")\n                        setTextColor(Color.parseColor("#94A3B8"))\n                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)\n                        setPadding(0, dp(6), 0, 0)\n                    }\n                )\n            }\n\n            listContainer.addView(\n                card,\n                LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply {\n                    bottomMargin = dp(8)\n                }\n            )\n        }\n    }\n\n    private fun roundedBg(fillHex: String, strokeHex: String, radiusDp: Float): GradientDrawable {\n        return GradientDrawable().apply {\n            shape = GradientDrawable.RECTANGLE\n            cornerRadius = dp(radiusDp.toInt()).toFloat()\n            setColor(Color.parseColor(fillHex))\n            setStroke(dp(1), Color.parseColor(strokeHex))\n        }\n    }\n\n    private fun dp(value: Int): Int {\n        return TypedValue.applyDimension(\n            TypedValue.COMPLEX_UNIT_DIP,\n            value.toFloat(),\n            resources.displayMetrics\n        ).toInt()\n    }\n}\n'

NEW_ACTIVITY_MAIN_XML = '<?xml version="1.0" encoding="utf-8"?>\n<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"\n    android:layout_width="match_parent"\n    android:layout_height="match_parent"\n    android:orientation="vertical"\n    android:background="#0F1722">\n\n    <TextView\n        android:id="@+id/bannerDemoMode"\n        android:layout_width="match_parent"\n        android:layout_height="wrap_content"\n        android:background="#D97706"\n        android:text="DEMOTILA AKTIIVINEN – Kokeile leimausta, vuoroja ja ilmoituksia"\n        android:textColor="#FFFFFF"\n        android:textSize="12sp"\n        android:textStyle="bold"\n        android:gravity="center"\n        android:paddingVertical="4dp"\n        android:visibility="gone" />\n\n    <FrameLayout\n        android:id="@+id/contentContainer"\n        android:layout_width="match_parent"\n        android:layout_height="0dp"\n        android:layout_weight="1"\n        android:background="#0F1722">\n\n        <LinearLayout\n            android:id="@+id/webViewHost"\n            android:layout_width="match_parent"\n            android:layout_height="match_parent"\n            android:orientation="vertical"\n            android:background="#0F1722"\n            android:visibility="gone">\n\n            <LinearLayout\n                android:id="@+id/webOverlayHeader"\n                android:layout_width="match_parent"\n                android:layout_height="46dp"\n                android:orientation="horizontal"\n                android:gravity="center_vertical"\n                android:paddingHorizontal="10dp"\n                android:background="#182332"\n                android:visibility="gone">\n\n                <Button\n                    android:id="@+id/btnWebOverlayBack"\n                    android:layout_width="wrap_content"\n                    android:layout_height="34dp"\n                    android:minHeight="0dp"\n                    android:paddingHorizontal="12dp"\n                    android:background="@drawable/nav_btn_inactive"\n                    android:text="← Takaisin"\n                    android:textAllCaps="false"\n                    android:textColor="#38BDF8"\n                    android:textStyle="bold"\n                    android:textSize="13sp" />\n\n                <TextView\n                    android:id="@+id/txtWebOverlayTitle"\n                    android:layout_width="0dp"\n                    android:layout_height="wrap_content"\n                    android:layout_weight="1"\n                    android:layout_marginStart="10dp"\n                    android:textColor="#F1F5F9"\n                    android:textSize="14sp"\n                    android:textStyle="bold"\n                    android:maxLines="1"\n                    android:ellipsize="end" />\n            </LinearLayout>\n\n            <FrameLayout\n                android:id="@+id/webViewSlot"\n                android:layout_width="match_parent"\n                android:layout_height="0dp"\n                android:layout_weight="1"\n                android:background="#0F1722" />\n        </LinearLayout>\n\n        <FrameLayout\n            android:id="@+id/nativeShiftsContainer"\n            android:layout_width="match_parent"\n            android:layout_height="match_parent"\n            android:background="#0F1722"\n            android:visibility="gone" />\n\n        <FrameLayout\n            android:id="@+id/nativeRequestsContainer"\n            android:layout_width="match_parent"\n            android:layout_height="match_parent"\n            android:background="#0F1722"\n            android:visibility="gone" />\n    </FrameLayout>\n\n    <LinearLayout\n        android:layout_width="match_parent"\n        android:layout_height="60dp"\n        android:orientation="horizontal"\n        android:padding="6dp"\n        android:background="#0B111A"\n        android:gravity="center_vertical">\n\n        <Button\n            android:id="@+id/btnNavStamp"\n            android:layout_width="0dp"\n            android:layout_height="match_parent"\n            android:layout_weight="1.3"\n            android:layout_marginEnd="4dp"\n            android:background="@drawable/nav_btn_active"\n            android:text="Leimaus"\n            android:textAllCaps="false"\n            android:textColor="#FFFFFF"\n            android:textStyle="bold"\n            android:textSize="13sp" />\n\n        <Button\n            android:id="@+id/btnNavRequests"\n            android:layout_width="0dp"\n            android:layout_height="match_parent"\n            android:layout_weight="1.2"\n            android:layout_marginEnd="4dp"\n            android:background="@drawable/nav_btn_inactive"\n            android:text="Toiveet"\n            android:textAllCaps="false"\n            android:textColor="#E0E6ED"\n            android:textSize="13sp" />\n\n        <Button\n            android:id="@+id/btnNavShifts"\n            android:layout_width="0dp"\n            android:layout_height="match_parent"\n            android:layout_weight="1.2"\n            android:layout_marginEnd="4dp"\n            android:background="@drawable/nav_btn_inactive"\n            android:text="Vuorot"\n            android:textAllCaps="false"\n            android:textColor="#E0E6ED"\n            android:textSize="13sp" />\n\n        <Button\n            android:id="@+id/btnNavSettings"\n            android:layout_width="0dp"\n            android:layout_height="match_parent"\n            android:layout_weight="0.8"\n            android:layout_marginEnd="4dp"\n            android:background="@drawable/nav_btn_inactive"\n            android:text="⚙"\n            android:textColor="#E0E6ED"\n            android:textSize="18sp" />\n\n        <Button\n            android:id="@+id/btnNavClose"\n            android:layout_width="0dp"\n            android:layout_height="match_parent"\n            android:layout_weight="0.8"\n            android:background="@drawable/nav_btn_close"\n            android:text="✕"\n            android:textColor="#FFFFFF"\n            android:textSize="16sp" />\n    </LinearLayout>\n</LinearLayout>\n'

NUMERON_PARSER_ADDITION = '\n\ndata class CalendarDisplayShift(\n    val startText: String,\n    val endText: String,\n    val startMinutes: Int,\n    val endMinutes: Int,\n    val location: String,\n    val shiftName: String,\n    val role: String,\n    val rawTitle: String\n)\n\ndata class CalendarDisplayAbsence(\n    val title: String,\n    val kind: String,\n    val spanDays: Int = 1\n)\n\ndata class CalendarDisplayRequest(\n    val title: String\n)\n\ndata class CalendarDisplayDay(\n    val date: LocalDate,\n    val shifts: List<CalendarDisplayShift>,\n    val absences: List<CalendarDisplayAbsence>,\n    val requests: List<CalendarDisplayRequest>,\n    val hasCommentCircle: Boolean = false\n)\n\ndata class MonthDisplayData(\n    val year: Int,\n    val month: Int,\n    val days: Map<LocalDate, CalendarDisplayDay>\n)\n'

NUMERON_PARSER_METHODS = '\n    private fun isDisplayIgnoredAbsence(nameText: String): Boolean {\n        val lower = nameText.trim().lowercase()\n        return lower == "vapaa" ||\n            lower.startsWith("vapaapäivä") ||\n            lower.startsWith("arkipyhä") ||\n            lower.startsWith("viikkolepo") ||\n            lower.startsWith("viikkovapaa") ||\n            lower.startsWith("tasausvapaa") ||\n            lower.startsWith("saldovapaa") ||\n            lower.startsWith("pekkanen") ||\n            lower.startsWith("pekkaspäivä") ||\n            lower.startsWith("ei suunniteltuja töitä") ||\n            lower == "ei työvuoroa" ||\n            lower == "ei vuoroa"\n    }\n\n    private fun classifyDisplayAbsence(nameText: String): String {\n        val lower = nameText.trim().lowercase()\n        return when {\n            lower.contains("sairaus") || lower.contains("hoitovapaa") -> "sick"\n            lower.contains("loma") || lower.contains("säästövapaa") || lower.contains("lomarahavapaa") -> "vacation"\n            else -> "other"\n        }\n    }\n\n    fun parseMonthForDisplay(html: String): MonthDisplayData? {\n        val doc = Jsoup.parse(html)\n        val monthHeader = doc.selectFirst("#monthText")?.text()?.trim()?.lowercase() ?: return null\n        val parts = monthHeader.split(Regex("\\\\s+"))\n        if (parts.size < 2) return null\n\n        val currentMonth = finnishMonths[parts[0]] ?: return null\n        val currentYear = parts[1].toIntOrNull() ?: return null\n        val dayCells = doc.select("table.month-table td.month-day")\n        if (dayCells.isEmpty()) return null\n\n        val shiftsByDate = mutableMapOf<LocalDate, MutableList<CalendarDisplayShift>>()\n        val absencesByDate = mutableMapOf<LocalDate, MutableList<CalendarDisplayAbsence>>()\n        val requestsByDate = mutableMapOf<LocalDate, MutableList<CalendarDisplayRequest>>()\n        val circleDates = mutableSetOf<LocalDate>()\n        val timeFmt = DateTimeFormatter.ofPattern("H:mm")\n\n        for (cell in dayCells) {\n            if (cell.hasClass("day-different-month")) continue\n            val dayNum = cell.selectFirst(".dayNum")?.text()?.trim()?.toIntOrNull() ?: continue\n            val date = try {\n                LocalDate.of(currentYear, currentMonth, dayNum)\n            } catch (_: Exception) {\n                continue\n            }\n\n            if (cell.selectFirst(".circle") != null) {\n                circleDates.add(date)\n            }\n\n            // Poissaolot (säilyttää lomat, sairauslomat ja koulutukset/muut)\n            cell.select(".month-item.absence").forEach { item ->\n                val nameText = item.selectFirst(".itemName")?.text()?.trim() ?: return@forEach\n                if (nameText.isEmpty() || isDisplayIgnoredAbsence(nameText)) return@forEach\n                val kind = classifyDisplayAbsence(nameText)\n                val spanDays = parseAbsenceSpanDays(item.attr("style"))\n                for (offset in 0 until spanDays) {\n                    val targetDate = date.plusDays(offset.toLong())\n                    if (targetDate.monthValue == currentMonth && targetDate.year == currentYear) {\n                        val list = absencesByDate.getOrPut(targetDate) { mutableListOf() }\n                        if (list.none { it.title.equals(nameText, ignoreCase = true) }) {\n                            list.add(CalendarDisplayAbsence(nameText, kind, if (offset == 0) spanDays else 1))\n                        }\n                    }\n                }\n            }\n\n            // Työvuorot (sekä menneet että tulevat koko kuukaudelta)\n            cell.select(".month-item.work").forEach { item ->\n                val timesText = item.selectFirst(".itemTimes")?.text()?.trim() ?: ""\n                val rawNameText = item.selectFirst(".itemName")?.text()?.trim() ?: ""\n                val timeParts = timesText.split("-").map { it.trim() }\n                if (timeParts.size == 2) {\n                    val startTime = try {\n                        LocalTime.parse(timeParts[0], timeFmt)\n                    } catch (_: Exception) {\n                        return@forEach\n                    }\n                    val endTime = try {\n                        LocalTime.parse(timeParts[1], timeFmt)\n                    } catch (_: Exception) {\n                        return@forEach\n                    }\n                    val parsed = parseShiftText(rawNameText)\n                    val list = shiftsByDate.getOrPut(date) { mutableListOf() }\n                    list.add(\n                        CalendarDisplayShift(\n                            startText = String.format("%d:%02d", startTime.hour, startTime.minute),\n                            endText = String.format("%d:%02d", endTime.hour, endTime.minute),\n                            startMinutes = startTime.hour * 60 + startTime.minute,\n                            endMinutes = endTime.hour * 60 + endTime.minute,\n                            location = parsed.location,\n                            shiftName = parsed.shiftName,\n                            role = parsed.role,\n                            rawTitle = rawNameText\n                        )\n                    )\n                }\n            }\n\n            // Toiveet kalenterissa\n            cell.select(".month-item.request").forEach { item ->\n                val title = (item.selectFirst(".itemName")?.text() ?: item.text()).replace(Regex("\\\\s+"), " ").trim()\n                if (title.isNotEmpty()) {\n                    val list = requestsByDate.getOrPut(date) { mutableListOf() }\n                    if (list.none { it.title.equals(title, ignoreCase = true) }) {\n                        list.add(CalendarDisplayRequest(title))\n                    }\n                }\n            }\n        }\n\n        val allDates = (shiftsByDate.keys + absencesByDate.keys + requestsByDate.keys + circleDates)\n        val dayMap = mutableMapOf<LocalDate, CalendarDisplayDay>()\n        for (d in allDates) {\n            dayMap[d] = CalendarDisplayDay(\n                date = d,\n                shifts = shiftsByDate[d].orEmpty(),\n                absences = absencesByDate[d].orEmpty(),\n                requests = requestsByDate[d].orEmpty(),\n                hasCommentCircle = d in circleDates\n            )\n        }\n        return MonthDisplayData(year = currentYear, month = currentMonth, days = dayMap)\n    }\n\n    fun fetchDayComments(baseUrl: String, cookieHeader: String?, date: LocalDate): String? {\n        if (baseUrl.isBlank()) return null\n        val cleanBase = baseUrl.trimEnd(\'/\')\n        val listUrl = "$cleanBase/Calendar/List?date=${date.monthValue}%2F${date.dayOfMonth}%2F${date.year}%2000%3A00%3A00"\n        val html = fetchHtmlWithCookies(listUrl, cookieHeader) ?: return null\n        val parsed = parseListCommentsHtml(html)\n        val comments = parsed.entries\n            .filter { it.key.first == date }\n            .map { it.value.trim() }\n            .filter { it.isNotEmpty() }\n            .distinct()\n        return if (comments.isEmpty()) null else comments.joinToString("\\n")\n    }\n'


def patch_calendar_sync_helper(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text
    text = replace_once(
        text,
        "    private fun loadCachedShifts(context: Context): List<WorkShift>? {",
        "    fun loadCachedShifts(context: Context): List<WorkShift>? {",
        "CalendarSyncHelper.loadCachedShifts julkiseksi natiivikalenterille"
    )
    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_background_auth_helper(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text
    old_block = (
        "            bodies.add(res.body)\n"
        "        }\n\n"
        '        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)'
    )
    new_block = (
        "            NumeronApiClient.extractAndSaveMaxSessionTime(context, res.body)\n"
        "            bodies.add(res.body)\n"
        "        }\n\n"
        '        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)'
    )
    text = replace_once(
        text,
        old_block,
        new_block,
        "BackgroundAuthHelper tallentaa maxSessionTimeInMilliseconds-ajan haetuista sivuista"
    )
    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_numeron_parser(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    old_data_anchor = (
        "data class WorkShift(\n"
        "    val title: String,\n"
        "    val start: LocalDateTime,\n"
        "    val end: LocalDateTime,\n"
        "    val isAllDayLeave: Boolean = false,\n"
        '    val location: String = "",\n'
        '    val description: String = ""\n'
        ")"
    )
    new_data_anchor = old_data_anchor + NUMERON_PARSER_ADDITION
    text = replace_once(
        text,
        old_data_anchor,
        new_data_anchor,
        "Lisätty MonthDisplayData- ja CalendarDisplay*-tietoluokat NumeronParser.kt:hen"
    )

    old_tail = (
        "        workShifts.add(currentLeave)\n"
        "        return workShifts.sortedBy { it.start }\n"
        "    }\n"
        "}"
    )
    new_tail = (
        "        workShifts.add(currentLeave)\n"
        "        return workShifts.sortedBy { it.start }\n"
        "    }\n"
        + NUMERON_PARSER_METHODS +
        "}"
    )
    text = replace_once(
        text,
        old_tail,
        new_tail,
        "Lisätty parseMonthForDisplay ja fetchDayComments NumeronParser.kt:hen"
    )

    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_activity_main_xml(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    target = NEW_ACTIVITY_MAIN_XML.strip() + "\n"
    if text.strip() == target.strip():
        print("  [OK - jo sovellettu] activity_main.xml (laiska WebView + natiivisäiliöt)")
        return False
    write_text_keep_nl(path, target, nl)
    print("  [PÄIVITETTY] activity_main.xml (contentContainer + webViewHost + nativeShifts/Requests)")
    return True


def patch_build_gradle(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text
    if "versionCode = 124" in text:
        print("  [OK - jo sovellettu] build.gradle.kts versionCode 124")
        return False
    text = replace_once(text, "versionCode = 123", "versionCode = 124", "versionCode 123 -> 124")
    text = replace_once(text, 'versionName = "3.2.181"', 'versionName = "3.2.182"', 'versionName 3.2.181 -> 3.2.182')
    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_main_activity(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    old_fields = """    private lateinit var webView: WebView
    private lateinit var bannerDemoMode: TextView
    private lateinit var btnNavStamp: Button
    private lateinit var btnNavRequests: Button
    private lateinit var btnNavShifts: Button
    private lateinit var btnNavSettings: Button
    private lateinit var btnNavClose: Button"""

    new_fields = """    private var webView: WebView? = null
    private lateinit var webViewHost: android.widget.LinearLayout
    private lateinit var webOverlayHeader: android.widget.LinearLayout
    private lateinit var btnWebOverlayBack: Button
    private lateinit var txtWebOverlayTitle: TextView
    private lateinit var webViewSlot: FrameLayout
    private lateinit var nativeShiftsContainer: FrameLayout
    private lateinit var nativeRequestsContainer: FrameLayout
    private var nativeShiftsView: NativeShiftsView? = null
    private var nativeRequestsView: NativeRequestsView? = null
    private var isWebOverlayOpen: Boolean = false
    private var pendingOverlayUrl: String? = null

    private lateinit var bannerDemoMode: TextView
    private lateinit var btnNavStamp: Button
    private lateinit var btnNavRequests: Button
    private lateinit var btnNavShifts: Button
    private lateinit var btnNavSettings: Button
    private lateinit var btnNavClose: Button"""

    text = replace_once(text, old_fields, new_fields, "Laiska WebView ja natiivisäiliöiden kentät")

    old_oncreate = """        webView = findViewById(R.id.webView)
        bannerDemoMode = findViewById(R.id.bannerDemoMode)
        btnNavStamp = findViewById(R.id.btnNavStamp)
        btnNavRequests = findViewById(R.id.btnNavRequests)
        btnNavShifts = findViewById(R.id.btnNavShifts)
        btnNavSettings = findViewById(R.id.btnNavSettings)
        btnNavClose = findViewById(R.id.btnNavClose)

        setupWebView()
        setupBottomBar()
        setupBackNavigation()
        handleIncomingIntent(intent)

        // Näytetään heti käynnistyksessä splash-ruutu "Kirjaudutaan..."
        startSnapshotTransition()

        if (intent?.getBooleanExtra("OPEN_REQUESTS", false) == true) {
            intent.removeExtra("OPEN_REQUESTS")
            navigateToTab(Tab.REQUESTS)
        } else {
            navigateToTab(Tab.STAMP)
        }"""

    new_oncreate = """        webViewHost = findViewById(R.id.webViewHost)
        webOverlayHeader = findViewById(R.id.webOverlayHeader)
        btnWebOverlayBack = findViewById(R.id.btnWebOverlayBack)
        txtWebOverlayTitle = findViewById(R.id.txtWebOverlayTitle)
        webViewSlot = findViewById(R.id.webViewSlot)
        nativeShiftsContainer = findViewById(R.id.nativeShiftsContainer)
        nativeRequestsContainer = findViewById(R.id.nativeRequestsContainer)

        bannerDemoMode = findViewById(R.id.bannerDemoMode)
        btnNavStamp = findViewById(R.id.btnNavStamp)
        btnNavRequests = findViewById(R.id.btnNavRequests)
        btnNavShifts = findViewById(R.id.btnNavShifts)
        btnNavSettings = findViewById(R.id.btnNavSettings)
        btnNavClose = findViewById(R.id.btnNavClose)

        btnWebOverlayBack.setOnClickListener {
            closeWebOverlay(refreshNative = true)
        }

        setupBottomBar()
        setupBackNavigation()
        handleIncomingIntent(intent)

        if (intent?.getBooleanExtra("OPEN_REQUESTS", false) == true) {
            intent.removeExtra("OPEN_REQUESTS")
            navigateToTab(Tab.REQUESTS)
        } else {
            navigateToTab(Tab.STAMP)
        }"""

    text = replace_once(text, old_oncreate, new_oncreate, "onCreate alustaa säiliöt ja jättää WebView:n laiskaksi")

    old_resume = """    private fun resolveResumeUrl(baseUrl: String): String {
        return when {
            pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> "$baseUrl/WorktimeStamping"
            pendingAction == Action.SYNC_CALENDAR -> "$baseUrl/Calendar/Month"
            currentTab == Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
            currentTab == Tab.SHIFTS -> "$baseUrl/Calendar/Month"
            else -> "$baseUrl/WorktimeStamping"
        }
    }"""

    new_resume = """    private fun resolveResumeUrl(baseUrl: String): String {
        val overlayUrl = pendingOverlayUrl
        return when {
            isWebOverlayOpen && !overlayUrl.isNullOrBlank() -> overlayUrl
            pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> "$baseUrl/WorktimeStamping"
            pendingAction == Action.SYNC_CALENDAR -> "$baseUrl/Calendar/Month"
            currentTab == Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
            currentTab == Tab.SHIFTS -> "$baseUrl/Calendar/Month"
            else -> "$baseUrl/WorktimeStamping"
        }
    }

    private fun ensureWebView(): WebView {
        webView?.let { return it }
        val wv = WebView(this)
        webViewSlot.removeAllViews()
        webViewSlot.addView(
            wv,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        webView = wv
        setupWebView(wv)
        return wv
    }

    private fun ensureNativeShiftsView(): NativeShiftsView {
        nativeShiftsView?.let { return it }
        val v = NativeShiftsView(
            context = this,
            scope = scope,
            onOpenWebUrl = { url, title -> openWebOverlayUrl(url, title) }
        )
        nativeShiftsContainer.removeAllViews()
        nativeShiftsContainer.addView(
            v,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        nativeShiftsView = v
        return v
    }

    private fun ensureNativeRequestsView(): NativeRequestsView {
        nativeRequestsView?.let { return it }
        val v = NativeRequestsView(
            context = this,
            scope = scope,
            onOpenWebUrl = { url, title -> openWebOverlayUrl(url, title) }
        )
        nativeRequestsContainer.removeAllViews()
        nativeRequestsContainer.addView(
            v,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        nativeRequestsView = v
        return v
    }

    private fun openWebOverlayUrl(url: String, title: String) {
        val baseUrl = getBaseUrl()
        val en = DemoModeHelper.isEnglish(this)
        if (baseUrl.isBlank()) {
            Toast.makeText(
                this,
                if (en) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista",
                Toast.LENGTH_LONG
            ).show()
            return
        }
        isWebOverlayOpen = true
        pendingOverlayUrl = url
        dashboardRedirectCount = 0
        isAutoSubmittingLogin = false
        val token = ++navigationToken
        navigateJob?.cancel()

        btnWebOverlayBack.text = if (en) "← Back" else "← Takaisin"
        txtWebOverlayTitle.text = title
        webOverlayHeader.visibility = View.VISIBLE
        nativeShiftsContainer.visibility = View.GONE
        nativeRequestsContainer.visibility = View.GONE
        webViewHost.visibility = View.VISIBLE

        val wv = ensureWebView()
        startSnapshotTransition {
            if (token != navigationToken) return@startSnapshotTransition
            if (!NumeronApiClient.isSessionLikelyValid(this, baseUrl, isAutoStamping = false)) {
                navigateJob = scope.launch {
                    try {
                        BackgroundAuthHelper.ensureAuthenticatedSession(this@MainActivity)
                    } catch (_: Exception) {
                    }
                    if (token == navigationToken && isWebOverlayOpen && !isFinishing && !isDestroyed) {
                        wv.stopLoading()
                        wv.loadUrl(url)
                    }
                }
            } else {
                wv.stopLoading()
                wv.loadUrl(url)
            }
        }
    }

    private fun closeWebOverlay(refreshNative: Boolean) {
        isWebOverlayOpen = false
        pendingOverlayUrl = null
        isAutoSubmittingLogin = false
        endSnapshotTransition()
        webOverlayHeader.visibility = View.GONE
        webView?.stopLoading()

        when (currentTab) {
            Tab.SHIFTS -> {
                webViewHost.visibility = View.GONE
                nativeRequestsContainer.visibility = View.GONE
                nativeShiftsContainer.visibility = View.VISIBLE
                if (refreshNative) {
                    ensureNativeShiftsView().refreshFromCacheAndNetwork()
                }
            }
            Tab.REQUESTS -> {
                webViewHost.visibility = View.GONE
                nativeShiftsContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.VISIBLE
                if (refreshNative) {
                    ensureNativeRequestsView().refreshAfterWebEdit()
                }
            }
            Tab.STAMP -> {
                nativeShiftsContainer.visibility = View.GONE
                nativeRequestsContainer.visibility = View.GONE
                webViewHost.visibility = View.VISIBLE
            }
        }
    }"""

    text = replace_once(text, old_resume, new_resume, "Lisätty ensureWebView, ensureNative*View ja open/closeWebOverlay")

    old_overlay = """        rootContent.addView(overlay, FrameLayout.LayoutParams(webView.width, webView.height))
        syncOverlayBoundsToWebView(overlay)
        webView.post { syncOverlayBoundsToWebView(overlay) }
        transitionOverlay = overlay
        return overlay
    }

    private fun syncOverlayBoundsToWebView(overlay: FrameLayout) {
        if (webView.width <= 0 || webView.height <= 0) return
        val rootContent = findViewById<View>(android.R.id.content)
        val webLoc = IntArray(2)
        val rootLoc = IntArray(2)
        webView.getLocationInWindow(webLoc)
        rootContent.getLocationInWindow(rootLoc)

        val lp = overlay.layoutParams as FrameLayout.LayoutParams
        lp.width = webView.width
        lp.height = webView.height
        lp.leftMargin = webLoc[0] - rootLoc[0]
        lp.topMargin = webLoc[1] - rootLoc[1]
        overlay.layoutParams = lp
    }

    private fun recycleSnapshotBitmap() {
        snapshotView?.setImageDrawable(null)
        snapshotView?.visibility = View.GONE
        try {
            snapshotBitmap?.let {
                if (!it.isRecycled) it.recycle()
            }
        } catch (_: Exception) {}
        snapshotBitmap = null
    }

    private fun startSnapshotTransition(onReady: (() -> Unit)? = null) {
        val overlay = ensureTransitionOverlay()
        overlay.animate().cancel()
        webView.removeCallbacks(transitionFallbackRunnable)
        webView.postDelayed(transitionFallbackRunnable, 6500L)

        if (!isTransitionActive) {
            isTransitionActive = true
            recycleSnapshotBitmap()

            if (webView.width > 0 && webView.height > 0 && webView.alpha > 0.5f) {
                try {
                    val bitmap = Bitmap.createBitmap(webView.width, webView.height, Bitmap.Config.RGB_565)
                    val canvas = Canvas(bitmap)
                    webView.draw(canvas)
                    snapshotBitmap = bitmap
                    snapshotView?.setImageBitmap(bitmap)
                    snapshotView?.visibility = View.VISIBLE
                } catch (_: Exception) {
                    recycleSnapshotBitmap()
                }
            }

            overlay.alpha = 1f
            overlay.visibility = View.VISIBLE
            webView.alpha = 0f
            webView.post { syncOverlayBoundsToWebView(overlay) }

            if (onReady != null) {
                webView.post { onReady() }
            }
        } else {
            onReady?.invoke()
        }
    }

    private fun endSnapshotTransition() {
        webView.removeCallbacks(transitionFallbackRunnable)
        webView.alpha = 1f
        isTransitionActive = false"""

    new_overlay = """        rootContent.addView(overlay, FrameLayout.LayoutParams(webViewSlot.width, webViewSlot.height))
        syncOverlayBoundsToWebView(overlay)
        webViewSlot.post { syncOverlayBoundsToWebView(overlay) }
        transitionOverlay = overlay
        return overlay
    }

    private fun syncOverlayBoundsToWebView(overlay: FrameLayout) {
        if (webViewSlot.width <= 0 || webViewSlot.height <= 0) return
        val rootContent = findViewById<View>(android.R.id.content)
        val webLoc = IntArray(2)
        val rootLoc = IntArray(2)
        webViewSlot.getLocationInWindow(webLoc)
        rootContent.getLocationInWindow(rootLoc)

        val lp = overlay.layoutParams as FrameLayout.LayoutParams
        lp.width = webViewSlot.width
        lp.height = webViewSlot.height
        lp.leftMargin = webLoc[0] - rootLoc[0]
        lp.topMargin = webLoc[1] - rootLoc[1]
        overlay.layoutParams = lp
    }

    private fun recycleSnapshotBitmap() {
        snapshotView?.setImageDrawable(null)
        snapshotView?.visibility = View.GONE
        try {
            snapshotBitmap?.let {
                if (!it.isRecycled) it.recycle()
            }
        } catch (_: Exception) {}
        snapshotBitmap = null
    }

    private fun startSnapshotTransition(onReady: (() -> Unit)? = null) {
        val overlay = ensureTransitionOverlay()
        overlay.animate().cancel()
        webViewSlot.removeCallbacks(transitionFallbackRunnable)
        webViewSlot.postDelayed(transitionFallbackRunnable, 6500L)

        val wv = webView
        if (!isTransitionActive) {
            isTransitionActive = true
            recycleSnapshotBitmap()

            if (wv != null && wv.width > 0 && wv.height > 0 && wv.alpha > 0.5f && webViewHost.visibility == View.VISIBLE) {
                try {
                    val bitmap = Bitmap.createBitmap(wv.width, wv.height, Bitmap.Config.RGB_565)
                    val canvas = Canvas(bitmap)
                    wv.draw(canvas)
                    snapshotBitmap = bitmap
                    snapshotView?.setImageBitmap(bitmap)
                    snapshotView?.visibility = View.VISIBLE
                } catch (_: Exception) {
                    recycleSnapshotBitmap()
                }
            }

            overlay.alpha = 1f
            overlay.visibility = View.VISIBLE
            wv?.alpha = 0f
            webViewSlot.post { syncOverlayBoundsToWebView(overlay) }

            if (onReady != null) {
                webViewSlot.post { onReady() }
            }
        } else {
            onReady?.invoke()
        }
    }

    private fun endSnapshotTransition() {
        webViewSlot.removeCallbacks(transitionFallbackRunnable)
        webView?.alpha = 1f
        isTransitionActive = false"""

    text = replace_once(text, old_overlay, new_overlay, "Siirtymäverho sidottu webViewSlot-säiliöön")

    old_nav = """    private fun navigateToTab(tab: Tab) {
        currentTab = tab
        dashboardRedirectCount = 0
        isAutoSubmittingLogin = false
        val token = ++navigationToken
        navigateJob?.cancel()
        updateDemoBanner()

        when (tab) {
            Tab.STAMP -> setActiveTab(btnNavStamp)
            Tab.REQUESTS -> setActiveTab(btnNavRequests)
            Tab.SHIFTS -> setActiveTab(btnNavShifts)
        }

        if (DemoModeHelper.isDemoEnabled(this)) {
            if (tab == Tab.SHIFTS) {
                DemoModeHelper.resetDemoCalendarMonth(this)
            }
            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition
                val html = when (tab) {
                    Tab.STAMP -> DemoModeHelper.getDemoStampingHtml(this)
                    Tab.REQUESTS -> DemoModeHelper.getDemoRequestsHtml(this)
                    Tab.SHIFTS -> DemoModeHelper.getDemoShiftsHtml(this)
                }
                webView.stopLoading()
                webView.loadDataWithBaseURL("https://demo.local/", html, "text/html", "UTF-8", null)
            }
        } else {
            val baseUrl = getBaseUrl()
            if (baseUrl.isEmpty() || (!baseUrl.startsWith("http://") && !baseUrl.startsWith("https://"))) {
                endSnapshotTransition()
                Toast.makeText(
                    this,
                    if (DemoModeHelper.isEnglish(this)) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista",
                    Toast.LENGTH_LONG
                ).show()
                btnNavSettings.performClick()
                return
            }
            if (BackgroundAuthHelper.isCredentialBlocked(this)) {
                endSnapshotTransition()
                Toast.makeText(
                    this,
                    if (DemoModeHelper.isEnglish(this)) {
                        "Login failed – please check username and password in Settings"
                    } else {
                        "Kirjautuminen epäonnistui – tarkista käyttäjätunnus ja salasana asetuksista"
                    },
                    Toast.LENGTH_LONG
                ).show()
                return
            }
            val now = LocalDate.now()
            val url = when (tab) {
                Tab.STAMP -> "$baseUrl/WorktimeStamping"
                Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
                Tab.SHIFTS -> "$baseUrl/Calendar/Month?month=${now.monthValue}&year=${now.year}"
            }
            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition
                navigateJob?.cancel()
                val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                val lastSessionMs = prefs.getLong("last_valid_session_ms", 0L)
                val sessionAgeMs = System.currentTimeMillis() - lastSessionMs
                val existingCookies = CookieManager.getInstance().getCookie(baseUrl)
                val isAutoStamping = (pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT)
                val maxSessionAgeMs = if (isAutoStamping) 10L * 60 * 1000L else 4L * 60 * 60 * 1000L

                if (existingCookies.isNullOrBlank() || sessionAgeMs > maxSessionAgeMs) {
                    navigateJob = scope.launch {
                        try {
                            val ok = BackgroundAuthHelper.ensureAuthenticatedSession(this@MainActivity)
                            if (ok) {
                                prefs.edit().putLong("last_valid_session_ms", System.currentTimeMillis()).apply()
                            }
                        } catch (_: Exception) {
                        }
                        if (token == navigationToken && !isFinishing && !isDestroyed) {
                            if (BackgroundAuthHelper.isCredentialBlocked(this@MainActivity)) {
                                endSnapshotTransition()
                                Toast.makeText(
                                    this@MainActivity,
                                    if (DemoModeHelper.isEnglish(this@MainActivity)) {
                                        "Login failed – please check username and password in Settings"
                                    } else {
                                        "Kirjautuminen epäonnistui – tarkista käyttäjätunnus ja salasana asetuksista"
                                    },
                                    Toast.LENGTH_LONG
                                ).show()
                            } else {
                                webView.stopLoading()
                                webView.loadUrl(url)
                            }
                        }
                    }
                } else {
                    webView.stopLoading()
                    webView.loadUrl(url)
                }
            }
        }
    }"""

    new_nav = """    private fun navigateToTab(tab: Tab) {
        currentTab = tab
        isWebOverlayOpen = false
        pendingOverlayUrl = null
        dashboardRedirectCount = 0
        isAutoSubmittingLogin = false
        val token = ++navigationToken
        navigateJob?.cancel()
        updateDemoBanner()

        when (tab) {
            Tab.STAMP -> setActiveTab(btnNavStamp)
            Tab.REQUESTS -> setActiveTab(btnNavRequests)
            Tab.SHIFTS -> setActiveTab(btnNavShifts)
        }

        if (tab == Tab.SHIFTS) {
            endSnapshotTransition()
            webView?.stopLoading()
            webOverlayHeader.visibility = View.GONE
            webViewHost.visibility = View.GONE
            nativeRequestsContainer.visibility = View.GONE
            nativeShiftsContainer.visibility = View.VISIBLE
            ensureNativeShiftsView().onShow(forceNetwork = false)
            return
        }

        if (tab == Tab.REQUESTS) {
            endSnapshotTransition()
            webView?.stopLoading()
            webOverlayHeader.visibility = View.GONE
            webViewHost.visibility = View.GONE
            nativeShiftsContainer.visibility = View.GONE
            nativeRequestsContainer.visibility = View.VISIBLE
            ensureNativeRequestsView().onShow(forceNetwork = false)
            return
        }

        nativeShiftsContainer.visibility = View.GONE
        nativeRequestsContainer.visibility = View.GONE
        webOverlayHeader.visibility = View.GONE
        webViewHost.visibility = View.VISIBLE
        val wv = ensureWebView()

        if (DemoModeHelper.isDemoEnabled(this)) {
            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition
                val html = DemoModeHelper.getDemoStampingHtml(this)
                wv.stopLoading()
                wv.loadDataWithBaseURL("https://demo.local/", html, "text/html", "UTF-8", null)
            }
        } else {
            val baseUrl = getBaseUrl()
            if (baseUrl.isEmpty() || (!baseUrl.startsWith("http://") && !baseUrl.startsWith("https://"))) {
                endSnapshotTransition()
                Toast.makeText(
                    this,
                    if (DemoModeHelper.isEnglish(this)) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista",
                    Toast.LENGTH_LONG
                ).show()
                btnNavSettings.performClick()
                return
            }
            if (BackgroundAuthHelper.isCredentialBlocked(this)) {
                endSnapshotTransition()
                Toast.makeText(
                    this,
                    if (DemoModeHelper.isEnglish(this)) {
                        "Login failed – please check username and password in Settings"
                    } else {
                        "Kirjautuminen epäonnistui – tarkista käyttäjätunnus ja salasana asetuksista"
                    },
                    Toast.LENGTH_LONG
                ).show()
                return
            }
            val url = "$baseUrl/WorktimeStamping"
            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition
                navigateJob?.cancel()
                val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                val isAutoStamping = (pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT)

                if (!NumeronApiClient.isSessionLikelyValid(this, baseUrl, isAutoStamping)) {
                    navigateJob = scope.launch {
                        try {
                            val ok = BackgroundAuthHelper.ensureAuthenticatedSession(this@MainActivity)
                            if (ok) {
                                prefs.edit().putLong("last_valid_session_ms", System.currentTimeMillis()).apply()
                            }
                        } catch (_: Exception) {
                        }
                        if (token == navigationToken && !isFinishing && !isDestroyed) {
                            if (BackgroundAuthHelper.isCredentialBlocked(this@MainActivity)) {
                                endSnapshotTransition()
                                Toast.makeText(
                                    this@MainActivity,
                                    if (DemoModeHelper.isEnglish(this@MainActivity)) {
                                        "Login failed – please check username and password in Settings"
                                    } else {
                                        "Kirjautuminen epäonnistui – tarkista käyttäjätunnus ja salasana asetuksista"
                                    },
                                    Toast.LENGTH_LONG
                                ).show()
                            } else {
                                wv.stopLoading()
                                wv.loadUrl(url)
                            }
                        }
                    }
                } else {
                    wv.stopLoading()
                    wv.loadUrl(url)
                }
            }
        }
    }"""

    text = replace_once(text, old_nav, new_nav, "navigateToTab käyttää natiiveja Vuorot- ja Toiveet-näkymiä")

    old_back = """    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(
            this,
            object : androidx.activity.OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    if (::webView.isInitialized && webView.canGoBack()) {
                        startSnapshotTransition()
                        webView.goBack()
                    } else {
                        isEnabled = false
                        onBackPressedDispatcher.onBackPressed()
                    }
                }
            }
        )
    }"""

    new_back = """    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(
            this,
            object : androidx.activity.OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    if (isWebOverlayOpen) {
                        closeWebOverlay(refreshNative = true)
                        return
                    }
                    val wv = webView
                    if (currentTab == Tab.STAMP && wv != null && wv.canGoBack()) {
                        startSnapshotTransition()
                        wv.goBack()
                    } else {
                        isEnabled = false
                        onBackPressedDispatcher.onBackPressed()
                    }
                }
            }
        )
    }"""

    text = replace_once(text, old_back, new_back, "Takaisin-näppäin sulkee lomake-overlayn ja palaa natiivinäkymään")

    old_sync_fb = """                pendingAction = Action.SYNC_CALENDAR
                syncStep = 0
                collectedCalendarHtml.clear()
                webView.loadUrl(urls[0])"""

    new_sync_fb = """                pendingAction = Action.SYNC_CALENDAR
                syncStep = 0
                collectedCalendarHtml.clear()
                ensureWebView().loadUrl(urls[0])"""

    text = replace_once(text, old_sync_fb, new_sync_fb, "startCalendarSync varapolku käyttää ensureWebView()")

    old_setup_wv = """    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        webView.setBackgroundColor(Color.parseColor("#0F1722"))
        (webView.parent as? View)?.setBackgroundColor(Color.parseColor("#0F1722"))

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            userAgentString = WebSettings.getDefaultUserAgent(this@MainActivity)
        }
        webView.webChromeClient = android.webkit.WebChromeClient()

        webView.addJavascriptInterface(
            DemoModeHelper.DemoJsBridge(
                context = this,
                onReloadNeeded = { runOnUiThread { navigateToTab(currentTab) } },
                onSyncRequested = { runOnUiThread { startCalendarSync() } },
                onManageChangesRequested = { runOnUiThread { CalendarChangeTracker.showManageChangesDialog(this) } }
            ),
            "DemoBridge"
        )

        webView.addJavascriptInterface(
            object {
                @android.webkit.JavascriptInterface
                fun onSessionExpired() {
                    runOnUiThread {
                        handleWebSessionExpired()
                    }
                }

                @android.webkit.JavascriptInterface
                fun onSessionExpiringSoon() {
                    runOnUiThread {
                        handleWebSessionExpiringSoon()
                    }
                }
            },
            "SessionBridge"
        )

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)

        webView.webViewClient = object : WebViewClient() {"""

    new_setup_wv = """    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView(wv: WebView) {
        wv.setBackgroundColor(Color.parseColor("#0F1722"))
        (wv.parent as? View)?.setBackgroundColor(Color.parseColor("#0F1722"))

        wv.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            userAgentString = WebSettings.getDefaultUserAgent(this@MainActivity)
        }
        wv.webChromeClient = android.webkit.WebChromeClient()

        wv.addJavascriptInterface(
            DemoModeHelper.DemoJsBridge(
                context = this,
                onReloadNeeded = { runOnUiThread { navigateToTab(currentTab) } },
                onSyncRequested = { runOnUiThread { startCalendarSync() } },
                onManageChangesRequested = { runOnUiThread { CalendarChangeTracker.showManageChangesDialog(this) } }
            ),
            "DemoBridge"
        )

        wv.addJavascriptInterface(
            object {
                @android.webkit.JavascriptInterface
                fun onSessionExpired() {
                    runOnUiThread {
                        handleWebSessionExpired()
                    }
                }

                @android.webkit.JavascriptInterface
                fun onSessionExpiringSoon() {
                    runOnUiThread {
                        handleWebSessionExpiringSoon()
                    }
                }
            },
            "SessionBridge"
        )

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(wv, true)

        wv.webViewClient = object : WebViewClient() {"""

    text = replace_once(text, old_setup_wv, new_setup_wv, "setupWebView(wv) alustaa laiskasti luodun WebView:n")

    old_override = """                    if (isInternal) {
                        if (request?.isForMainFrame == true &&
                            url.contains("/InfraDashboard", ignoreCase = true) &&
                            dashboardRedirectCount < 2
                        ) {
                            dashboardRedirectCount++
                            startSnapshotTransition()
                            view?.loadUrl(resolveResumeUrl(getBaseUrl()))
                            return true
                        }
                        startSnapshotTransition()
                        return false
                    }"""

    new_override = """                    if (isInternal) {
                        if (request?.isForMainFrame == true &&
                            isWebOverlayOpen &&
                            pendingAction != Action.SYNC_CALENDAR &&
                            (url.contains("/PersonRequests/List", ignoreCase = true) ||
                                url.contains("/Calendar/Month", ignoreCase = true))
                        ) {
                            closeWebOverlay(refreshNative = true)
                            return true
                        }
                        if (request?.isForMainFrame == true &&
                            url.contains("/InfraDashboard", ignoreCase = true) &&
                            dashboardRedirectCount < 2
                        ) {
                            dashboardRedirectCount++
                            startSnapshotTransition()
                            view?.loadUrl(resolveResumeUrl(getBaseUrl()))
                            return true
                        }
                        startSnapshotTransition()
                        return false
                    }"""

    text = replace_once(text, old_override, new_override, "Lomake-overlay sulkeutuu automaattisesti paluussa listaan/kalenteriin")

    old_amp = '                if (url.contains("amplitude")) {'
    new_amp = '                if (url.contains("amplitude") || url.contains("eligibility.")) {'
    text = replace_once(text, old_amp, new_amp, "Estetty myös eligibility.-seurantakutsu")

    old_finished = """                injectDarkTheme(view, forceDomInit = true)
                CookieManager.getInstance().flush()
                if (!url.contains("/Login/", ignoreCase = true) && !url.contains("/InfraDashboard", ignoreCase = true)) {
                    dashboardRedirectCount = 0
                }
                if (!url.contains("/Login/", ignoreCase = true)) {
                    webLoginAttemptFingerprint = ""
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                }

                when {
                    url.contains("/Login/LogOff", ignoreCase = true) -> {
                        isAutoSubmittingLogin = true
                        startSnapshotTransition()
                        webView.loadUrl("${getBaseUrl()}/Login/Login")
                        return
                    }
                    url.contains("/Login/Login", ignoreCase = true) -> {
                        isAutoSubmittingLogin = true
                        startSnapshotTransition()
                        handleAutoLogin()
                        return
                    }
                    url.contains("/InfraDashboard", ignoreCase = true) && dashboardRedirectCount < 2 -> {
                        dashboardRedirectCount++
                        startSnapshotTransition()
                        webView.loadUrl(resolveResumeUrl(getBaseUrl()))
                        return
                    }
                    url.contains("/WorktimeStamping", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        setActiveTab(btnNavStamp)
                        handleStampingPage()
                    }
                    url.contains("/PersonRequests", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        setActiveTab(btnNavRequests)
                    }
                    url.contains("/Calendar", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        setActiveTab(btnNavShifts)
                        handleCalendarPage()
                    }
                    pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> {
                        isAutoSubmittingLogin = false
                        webView.loadUrl("${getBaseUrl()}/WorktimeStamping")
                        return
                    }
                    else -> {
                        isAutoSubmittingLogin = false
                    }
                }"""

    new_finished = """                if (isWebOverlayOpen &&
                    pendingAction != Action.SYNC_CALENDAR &&
                    (url.contains("/PersonRequests/List", ignoreCase = true) ||
                        url.contains("/Calendar/Month", ignoreCase = true))
                ) {
                    closeWebOverlay(refreshNative = true)
                    return
                }

                injectDarkTheme(view, forceDomInit = true)
                if (url.contains("/Login/", ignoreCase = true) ||
                    url.contains("/WorktimeStamping", ignoreCase = true) ||
                    isAutoSubmittingLogin
                ) {
                    CookieManager.getInstance().flush()
                }
                if (!url.contains("/Login/", ignoreCase = true) && !url.contains("/InfraDashboard", ignoreCase = true)) {
                    dashboardRedirectCount = 0
                }
                if (!url.contains("/Login/", ignoreCase = true)) {
                    webLoginAttemptFingerprint = ""
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                }

                when {
                    url.contains("/Login/LogOff", ignoreCase = true) -> {
                        isAutoSubmittingLogin = true
                        startSnapshotTransition()
                        wv.loadUrl("${getBaseUrl()}/Login/Login")
                        return
                    }
                    url.contains("/Login/Login", ignoreCase = true) -> {
                        isAutoSubmittingLogin = true
                        startSnapshotTransition()
                        handleAutoLogin()
                        return
                    }
                    url.contains("/InfraDashboard", ignoreCase = true) && dashboardRedirectCount < 2 -> {
                        dashboardRedirectCount++
                        startSnapshotTransition()
                        wv.loadUrl(resolveResumeUrl(getBaseUrl()))
                        return
                    }
                    url.contains("/WorktimeStamping", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        if (!isWebOverlayOpen) setActiveTab(btnNavStamp)
                        handleStampingPage()
                    }
                    url.contains("/PersonRequests", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        if (!isWebOverlayOpen) setActiveTab(btnNavRequests)
                    }
                    url.contains("/Calendar", ignoreCase = true) -> {
                        isAutoSubmittingLogin = false
                        if (!isWebOverlayOpen) setActiveTab(btnNavShifts)
                        handleCalendarPage()
                    }
                    pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> {
                        isAutoSubmittingLogin = false
                        wv.loadUrl("${getBaseUrl()}/WorktimeStamping")
                        return
                    }
                    else -> {
                        isAutoSubmittingLogin = false
                    }
                }"""

    text = replace_once(text, old_finished, new_finished, "onPageFinished päivitetty overlay-paluulle ja rajatulle flush-kutsulle")

    old_demo_stamp = """            if (wantIn != currentlyIn) {
                webView.evaluateJavascript("DemoBridge.toggleStamp()", null)
                webView.postDelayed({ finishAndRemoveTask() }, 1200L)
            } else {
                val en = DemoModeHelper.isEnglish(this)
                val stateStr = if (en) (if (wantIn) "In" else "Out") else (if (wantIn) "Sisään" else "Ulos")
                val msg = if (en) "Demo mode: Already clocked $stateStr" else "Demotila: Olet jo leimannut tilaan $stateStr"
                Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
                webView.postDelayed({ finishAndRemoveTask() }, 1200L)
            }"""

    new_demo_stamp = """            if (wantIn != currentlyIn) {
                webView?.evaluateJavascript("DemoBridge.toggleStamp()", null)
                webViewSlot.postDelayed({ finishAndRemoveTask() }, 1200L)
            } else {
                val en = DemoModeHelper.isEnglish(this)
                val stateStr = if (en) (if (wantIn) "In" else "Out") else (if (wantIn) "Sisään" else "Ulos")
                val msg = if (en) "Demo mode: Already clocked $stateStr" else "Demotila: Olet jo leimannut tilaan $stateStr"
                Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
                webViewSlot.postDelayed({ finishAndRemoveTask() }, 1200L)
            }"""

    text = replace_once(text, old_demo_stamp, new_demo_stamp, "handleDemoAutoStamp null-turvalliseksi")

    old_autologin_eval = """        webView.evaluateJavascript(js) { res ->
            if (res?.contains("SUBMITTED") == true) {
                webLoginAttemptFingerprint = fp
            } else if (res?.contains("WAITING") == true) {
                if (attempt < 15) {
                    webView.postDelayed({ handleAutoLogin(attempt + 1) }, 300L)
                } else {
                    isAutoSubmittingLogin = false
                    endSnapshotTransition()
                }
            }
        }"""

    new_autologin_eval = """        val wv = webView ?: return
        wv.evaluateJavascript(js) { res ->
            if (res?.contains("SUBMITTED") == true) {
                webLoginAttemptFingerprint = fp
            } else if (res?.contains("WAITING") == true) {
                if (attempt < 15) {
                    wv.postDelayed({ handleAutoLogin(attempt + 1) }, 300L)
                } else {
                    isAutoSubmittingLogin = false
                    endSnapshotTransition()
                }
            }
        }"""

    text = replace_once(text, old_autologin_eval, new_autologin_eval, "handleAutoLogin null-turvalliseksi")

    old_expired_load = """                    val targetUrl = resolveResumeUrl(baseUrl)
                    webView.loadUrl(targetUrl)
                } else if (BackgroundAuthHelper.isCredentialBlocked(this@MainActivity)) {
                    endSnapshotTransition()
                    Toast.makeText(
                        this@MainActivity,
                        if (DemoModeHelper.isEnglish(this@MainActivity)) {
                            "Login failed – please check username and password in Settings"
                        } else {
                            "Kirjautuminen epäonnistui – tarkista käyttäjätunnus ja salasana asetuksista"
                        },
                        Toast.LENGTH_LONG
                    ).show()
                } else {
                    webView.loadUrl("$baseUrl/Login/Login")
                }"""

    new_expired_load = """                    val targetUrl = resolveResumeUrl(baseUrl)
                    ensureWebView().loadUrl(targetUrl)
                } else if (BackgroundAuthHelper.isCredentialBlocked(this@MainActivity)) {
                    endSnapshotTransition()
                    Toast.makeText(
                        this@MainActivity,
                        if (DemoModeHelper.isEnglish(this@MainActivity)) {
                            "Login failed – please check username and password in Settings"
                        } else {
                            "Kirjautuminen epäonnistui – tarkista käyttäjätunnus ja salasana asetuksista"
                        },
                        Toast.LENGTH_LONG
                    ).show()
                } else {
                    ensureWebView().loadUrl("$baseUrl/Login/Login")
                }"""

    text = replace_once(text, old_expired_load, new_expired_load, "handleWebSessionExpired käyttää ensureWebView()")

    old_stamp_page = """        webView.evaluateJavascript(StampingWebHelper.buildClickStampJs(wantIn)) { rawResult ->
            val obj = StampingWebHelper.parseJsonResult(rawResult)
            val status = obj?.optString("status", "") ?: ""

            when {
                status == "CLICKED" -> {
                    inFlightStampAction = pendingAction
                    pendingAction = Action.NONE
                    val beforeDir = obj?.optString("dir", "") ?: ""
                    val beforeBtn = obj?.optString("btn", "") ?: ""
                    val beforeRow = obj?.optString("row", "") ?: ""
                    val beforeRowId = obj?.optString("rowId", "") ?: ""
                    val en = DemoModeHelper.isEnglish(this)
                    val dirLabel = if (en) (if (wantIn) "In" else "Out") else targetText
                    Toast.makeText(this, if (en) "Stamping ($dirLabel)..." else "Leimataan ($targetText)...", Toast.LENGTH_SHORT).show()
                    verifyStampAndClose(wantIn, beforeDir, beforeBtn, beforeRow, beforeRowId, 0)
                }
                status == "WRONG_DIRECTION" -> {
                    pendingAction = Action.NONE
                    inFlightStampAction = Action.NONE
                    val en = DemoModeHelper.isEnglish(this)
                    val dirLabel = if (en) (if (wantIn) "In" else "Out") else targetText
                    Toast.makeText(this, if (en) "Already clocked $dirLabel" else "Olet jo leimannut tilaan: $targetText", Toast.LENGTH_LONG).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                }
                status == "NO_BUTTON" && attempt < 10 -> {
                    webView.postDelayed({ handleStampingPage(attempt + 1) }, 300L)
                }
                else -> {
                    pendingAction = Action.NONE
                }
            }
        }"""

    new_stamp_page = """        val wv = webView ?: return
        wv.evaluateJavascript(StampingWebHelper.buildClickStampJs(wantIn)) { rawResult ->
            val obj = StampingWebHelper.parseJsonResult(rawResult)
            val status = obj?.optString("status", "") ?: ""

            when {
                status == "CLICKED" -> {
                    inFlightStampAction = pendingAction
                    pendingAction = Action.NONE
                    val beforeDir = obj?.optString("dir", "") ?: ""
                    val beforeBtn = obj?.optString("btn", "") ?: ""
                    val beforeRow = obj?.optString("row", "") ?: ""
                    val beforeRowId = obj?.optString("rowId", "") ?: ""
                    val en = DemoModeHelper.isEnglish(this)
                    val dirLabel = if (en) (if (wantIn) "In" else "Out") else targetText
                    Toast.makeText(this, if (en) "Stamping ($dirLabel)..." else "Leimataan ($targetText)...", Toast.LENGTH_SHORT).show()
                    verifyStampAndClose(wantIn, beforeDir, beforeBtn, beforeRow, beforeRowId, 0)
                }
                status == "WRONG_DIRECTION" -> {
                    pendingAction = Action.NONE
                    inFlightStampAction = Action.NONE
                    val en = DemoModeHelper.isEnglish(this)
                    val dirLabel = if (en) (if (wantIn) "In" else "Out") else targetText
                    Toast.makeText(this, if (en) "Already clocked $dirLabel" else "Olet jo leimannut tilaan: $targetText", Toast.LENGTH_LONG).show()
                    wv.postDelayed({ finishAndRemoveTask() }, 1500L)
                }
                status == "NO_BUTTON" && attempt < 10 -> {
                    wv.postDelayed({ handleStampingPage(attempt + 1) }, 300L)
                }
                else -> {
                    pendingAction = Action.NONE
                }
            }
        }"""

    text = replace_once(text, old_stamp_page, new_stamp_page, "handleStampingPage null-turvalliseksi")

    old_verify = """        webView.postDelayed({
            if (isFinishing || isDestroyed) return@postDelayed
            webView.evaluateJavascript(StampingWebHelper.buildVerifyStampJs()) { rawResult ->"""

    new_verify = """        val wv = webView ?: return
        wv.postDelayed({
            if (isFinishing || isDestroyed) return@postDelayed
            wv.evaluateJavascript(StampingWebHelper.buildVerifyStampJs()) { rawResult ->"""

    text = replace_once(text, old_verify, new_verify, "verifyStampAndClose alku null-turvalliseksi")

    old_verify_close = """                    inFlightStampAction = Action.NONE
                    CookieManager.getInstance().flush()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)"""

    new_verify_close = """                    inFlightStampAction = Action.NONE
                    CookieManager.getInstance().flush()
                    wv.postDelayed({ finishAndRemoveTask() }, 1500L)"""

    text = replace_once(text, old_verify_close, new_verify_close, "verifyStampAndClose loppu null-turvalliseksi")

    old_handle_cal = """    private fun handleCalendarPage() {
        if (pendingAction != Action.SYNC_CALENDAR) return

        webView.evaluateJavascript("document.documentElement.outerHTML") { rawHtml ->
            if (rawHtml == null || rawHtml == "null") {
                pendingAction = Action.NONE
                collectedCalendarHtml.clear()
                return@evaluateJavascript
            }
            val unescapedHtml = try {
                JSONTokener(rawHtml).nextValue() as? String
            } catch (_: Exception) {
                null
            } ?: run {
                pendingAction = Action.NONE
                collectedCalendarHtml.clear()
                return@evaluateJavascript
            }
            collectedCalendarHtml.add(unescapedHtml)

            if (syncStep == 0) {
                syncStep = 1
                val nextMonth = LocalDate.now().plusMonths(1)
                val baseUrl = getBaseUrl()
                webView.loadUrl("$baseUrl/Calendar/Month?month=${nextMonth.monthValue}&year=${nextMonth.year}")
            } else {
                pendingAction = Action.NONE
                val pagesToParse = collectedCalendarHtml.toList()
                collectedCalendarHtml.clear()
                processSyncedCalendarPages(pagesToParse)
            }
        }
    }"""

    new_handle_cal = """    private fun handleCalendarPage() {
        if (pendingAction != Action.SYNC_CALENDAR) return
        val wv = webView ?: return

        wv.evaluateJavascript("document.documentElement.outerHTML") { rawHtml ->
            if (rawHtml == null || rawHtml == "null") {
                pendingAction = Action.NONE
                collectedCalendarHtml.clear()
                return@evaluateJavascript
            }
            val unescapedHtml = try {
                JSONTokener(rawHtml).nextValue() as? String
            } catch (_: Exception) {
                null
            } ?: run {
                pendingAction = Action.NONE
                collectedCalendarHtml.clear()
                return@evaluateJavascript
            }
            collectedCalendarHtml.add(unescapedHtml)

            if (syncStep == 0) {
                syncStep = 1
                val nextMonth = LocalDate.now().plusMonths(1)
                val baseUrl = getBaseUrl()
                wv.loadUrl("$baseUrl/Calendar/Month?month=${nextMonth.monthValue}&year=${nextMonth.year}")
            } else {
                pendingAction = Action.NONE
                val pagesToParse = collectedCalendarHtml.toList()
                collectedCalendarHtml.clear()
                processSyncedCalendarPages(pagesToParse)
            }
        }
    }"""

    text = replace_once(text, old_handle_cal, new_handle_cal, "handleCalendarPage null-turvalliseksi")

    old_proc_sync = """            val parsedPages = pagesToParse.map { NumeronParser.parseCalendarHtml(it) }"""
    new_proc_sync = """            pagesToParse.forEach { html ->
                NumeronParser.parseMonthForDisplay(html)?.let { displayData ->
                    NumeronApiClient.saveMonthDisplayCache(this@MainActivity, displayData)
                }
            }
            val parsedPages = pagesToParse.map { NumeronParser.parseCalendarHtml(it) }"""
    text = replace_once(text, old_proc_sync, new_proc_sync, "Manuaalisynkka päivittää natiivikalenterin kuukausivälimuistin")

    old_proc_ui = """            withContext(Dispatchers.Main) {
                if (isFinishing || isDestroyed) return@withContext
                val en = DemoModeHelper.isEnglish(this@MainActivity)"""
    new_proc_ui = """            withContext(Dispatchers.Main) {
                if (isFinishing || isDestroyed) return@withContext
                if (currentTab == Tab.SHIFTS && !isWebOverlayOpen) {
                    nativeShiftsView?.onShow(forceNetwork = false)
                } else if (currentTab == Tab.REQUESTS && !isWebOverlayOpen) {
                    nativeRequestsView?.refreshAfterWebEdit()
                }
                val en = DemoModeHelper.isEnglish(this@MainActivity)"""
    text = replace_once(text, old_proc_ui, new_proc_ui, "Manuaalisynkka päivittää aktiivisen natiivinäkymän")

    old_life = """    override fun onPause() {
        try {
            webView.onPause()
        } catch (_: Exception) {}
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        try {
            webView.onResume()
        } catch (_: Exception) {}
    }

    override fun onDestroy() {
        navigateJob?.cancel()
        webView.removeCallbacks(transitionFallbackRunnable)
        recycleSnapshotBitmap()
        try {
            CookieManager.getInstance().flush()
        } catch (_: Exception) {}
        try {
            (webView.parent as? ViewGroup)?.removeView(webView)
            webView.stopLoading()
            webView.destroy()
        } catch (_: Exception) {}
        scope.cancel()
        super.onDestroy()
    }"""

    new_life = """    override fun onPause() {
        try {
            webView?.onPause()
        } catch (_: Exception) {}
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        try {
            webView?.onResume()
        } catch (_: Exception) {}
    }

    override fun onDestroy() {
        navigateJob?.cancel()
        webViewSlot.removeCallbacks(transitionFallbackRunnable)
        recycleSnapshotBitmap()
        try {
            if (webView != null) {
                CookieManager.getInstance().flush()
            }
        } catch (_: Exception) {}
        try {
            webView?.let { wv ->
                (wv.parent as? ViewGroup)?.removeView(wv)
                wv.stopLoading()
                wv.destroy()
            }
            webView = null
        } catch (_: Exception) {}
        scope.cancel()
        super.onDestroy()
    }"""

    text = replace_once(text, old_life, new_life, "onPause/onResume/onDestroy null-turvallisiksi")

    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def main() -> int:
    changed = 0

    ma_path = find_file("MainActivity.kt")
    if ma_path is None:
        print("[VIRHE] MainActivity.kt ei löytynyt!")
        return 1

    kt_dir = ma_path.parent
    print(f"Kotlin-hakemisto: {kt_dir}")

    if write_new_file(kt_dir / "NumeronApiClient.kt", NUMERON_API_CLIENT_KT, "NumeronApiClient.kt"):
        changed += 1
    if write_new_file(kt_dir / "NativeShiftsView.kt", NATIVE_SHIFTS_VIEW_KT, "NativeShiftsView.kt"):
        changed += 1
    if write_new_file(kt_dir / "NativeRequestsView.kt", NATIVE_REQUESTS_VIEW_KT, "NativeRequestsView.kt"):
        changed += 1

    for filename, fn in [
        ("CalendarSyncHelper.kt", patch_calendar_sync_helper),
        ("BackgroundAuthHelper.kt", patch_background_auth_helper),
        ("NumeronParser.kt", patch_numeron_parser),
        ("activity_main.xml", patch_activity_main_xml),
        ("MainActivity.kt", patch_main_activity),
        ("build.gradle.kts", patch_build_gradle),
    ]:
        p = find_file(filename)
        if p is None:
            print(f"[EI LÖYTYNYT] {filename}")
            continue
        print(f"Käsitellään: {p}")
        if fn(p):
            changed += 1

    print(f"\nValmis! Luotuja/muokattuja tiedostoja: {changed}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
