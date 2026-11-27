#!/usr/bin/env python3
"""
Numeron Vuorovahti – Toiveilmoitusten korjaus + avautumisnopeuden optimointi (patch.py).
Päivittää tiedostot ShiftReminderReceiver.kt ja MainActivity.kt vastaamaan
/PersonRequests/Read -rajapinnan todellista rakennetta.
"""

import sys
from pathlib import Path


def find_file(filename: str) -> Path | None:
    candidates = [
        Path("app/src/main/java/fi/numeron/vuorovahti") / filename,
        Path("src/main/java/fi/numeron/vuorovahti") / filename,
        Path(filename),
    ]
    for c in candidates:
        if c.exists():
            return c
    for p in Path(".").rglob(filename):
        if ".git" not in p.parts and "build" not in p.parts:
            return p
    return None


def read_kt(path: Path) -> tuple[str, str]:
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def write_kt(path: Path, content: str, newline: str) -> None:
    normalized = content.replace("\r\n", "\n")
    if newline == "\r\n":
        normalized = normalized.replace("\n", "\r\n")
    path.write_bytes(normalized.encode("utf-8"))


def replace_once(content: str, old: str, new: str, label: str) -> str:
    if new in content:
        print(f"  [OK - jo sovellettu] {label}")
        return content
    if old not in content:
        print(f"  [VAROITUS - kohdetta ei löytynyt] {label}")
        return content
    print(f"  [PÄIVITETTY] {label}")
    return content.replace(old, new, 1)


def patch_shift_reminder_receiver(path: Path) -> bool:
    text, nl = read_kt(path)
    orig = text

    old_notif_tail = (
        "            val notif = NotificationCompat.Builder(context, channelId)\n"
        "                .setSmallIcon(android.R.drawable.ic_dialog_info)\n"
        "                .setContentTitle(title)\n"
        "                .setContentText(body)\n"
        "                .setPriority(NotificationCompat.PRIORITY_DEFAULT)\n"
        "                .setAutoCancel(true)\n"
        "                .setContentIntent(pi)\n"
        "                .build()\n"
        "            nm.notify(notifId, notif)\n"
        "        }\n"
        "    }\n"
        "}"
    )

    new_notif_tail = (
        "            val notif = NotificationCompat.Builder(context, channelId)\n"
        "                .setSmallIcon(android.R.drawable.ic_dialog_info)\n"
        "                .setContentTitle(title)\n"
        "                .setContentText(body)\n"
        "                .setPriority(NotificationCompat.PRIORITY_HIGH)\n"
        "                .setAutoCancel(true)\n"
        "                .setContentIntent(pi)\n"
        "                .build()\n"
        "            nm.notify(notifId, notif)\n"
        "        }\n\n"
        "        fun syncRequestsAndNotify(context: Context, baseUrl: String): Int {\n"
        "            if (baseUrl.isBlank()) return 0\n"
        "            val jsonStr = fetchRequestsJson(context, baseUrl) ?: return 0\n"
        "            return checkRequestUpdates(context, jsonStr)\n"
        "        }\n\n"
        "        private fun fetchRequestsJson(context: Context, baseUrl: String): String? {\n"
        "            var conn: java.net.HttpURLConnection? = null\n"
        "            val prefs = context.getSharedPreferences(\"NumeronPrefs\", Context.MODE_PRIVATE)\n"
        "            return try {\n"
        "                val cookies = CookieManager.getInstance().getCookie(baseUrl)\n"
        "                if (cookies.isNullOrBlank()) {\n"
        "                    prefs.edit().putString(\"last_requests_check_status\", \"NO_COOKIES\").apply()\n"
        "                    return null\n"
        "                }\n"
        "                conn = (java.net.URL(\"$baseUrl/PersonRequests/Read\").openConnection() as java.net.HttpURLConnection).apply {\n"
        "                    requestMethod = \"POST\"\n"
        "                    instanceFollowRedirects = false\n"
        "                    setRequestProperty(\"Cookie\", cookies)\n"
        "                    setRequestProperty(\"Content-Type\", \"application/x-www-form-urlencoded; charset=UTF-8\")\n"
        "                    setRequestProperty(\"Accept\", \"application/json, text/javascript, */*; q=0.01\")\n"
        "                    setRequestProperty(\"X-Requested-With\", \"XMLHttpRequest\")\n"
        "                    setRequestProperty(\n"
        "                        \"User-Agent\",\n"
        "                        \"Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36\"\n"
        "                    )\n"
        "                    doOutput = true\n"
        "                    connectTimeout = 15000\n"
        "                    readTimeout = 15000\n"
        "                }\n"
        "                java.io.OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { writer ->\n"
        "                    writer.write(\"sort=&page=1&pageSize=100&group=&filter=&selectedFilter=active\")\n"
        "                    writer.flush()\n"
        "                }\n"
        "                val code = conn.responseCode\n"
        "                val body = if (code == 200) {\n"
        "                    conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }\n"
        "                } else {\n"
        "                    null\n"
        "                }\n"
        "                if (body != null && body.trim().startsWith(\"{\")) {\n"
        "                    body\n"
        "                } else {\n"
        "                    prefs.edit().putString(\"last_requests_check_status\", \"HTTP_$code\").apply()\n"
        "                    null\n"
        "                }\n"
        "            } catch (e: Exception) {\n"
        "                prefs.edit().putString(\"last_requests_check_status\", \"ERR:${e.javaClass.simpleName}\").apply()\n"
        "                null\n"
        "            } finally {\n"
        "                conn?.disconnect()\n"
        "            }\n"
        "        }\n\n"
        "        private fun parseStatusCode(item: JSONObject): Int {\n"
        "            val fromStr = item.optString(\"Status\", \"\").trim().toIntOrNull()\n"
        "                ?: item.optString(\"StatusId\", \"\").trim().toIntOrNull()\n"
        "            if (fromStr != null) return fromStr\n"
        "            val fromInt = item.optInt(\"Status\", -1)\n"
        "            return if (fromInt > 0) fromInt else item.optInt(\"StatusId\", -1)\n"
        "        }\n\n"
        "        private fun resolveRequestStatusCode(rawStatus: Int, statusDesc: String): Int {\n"
        "            if (rawStatus == 40 || rawStatus == 50 || rawStatus == 80) return rawStatus\n"
        "            val lower = statusDesc.trim().lowercase()\n"
        "            if (lower.isEmpty()) return rawStatus\n"
        "            return when {\n"
        "                lower.contains(\"odottaa\") || lower.contains(\"pending\") || lower.contains(\"waiting\") || lower.contains(\"väntar\") -> 10\n"
        "                lower.contains(\"osittain\") || lower.contains(\"partial\") || lower.contains(\"delvis\") -> 40\n"
        "                lower.contains(\"hylätty\") || lower.contains(\"reject\") || lower.contains(\"denied\") || lower.contains(\"avslag\") -> 80\n"
        "                lower.contains(\"hyväksytty\") || lower.contains(\"approved\") || lower.contains(\"godkänd\") -> 50\n"
        "                else -> rawStatus\n"
        "            }\n"
        "        }\n\n"
        "        private fun fallbackStatusLabel(statusId: Int, en: Boolean): String = when (statusId) {\n"
        "            40 -> if (en) \"Partially approved\" else \"Osittain hyväksytty\"\n"
        "            50 -> if (en) \"Approved\" else \"Hyväksytty\"\n"
        "            80 -> if (en) \"Rejected\" else \"Hylätty\"\n"
        "            else -> \"\"\n"
        "        }\n\n"
        "        private fun parseDotNetDateMs(raw: String): Long? {\n"
        "            val match = Regex(\"/Date\\\\((-?\\\\d+)\\\\)/\").find(raw.trim()) ?: return null\n"
        "            return match.groupValues[1].toLongOrNull()\n"
        "        }\n\n"
        "        private fun checkRequestUpdates(context: Context, jsonStr: String): Int {\n"
        "            var sentCount = 0\n"
        "            try {\n"
        "                val prefs = context.getSharedPreferences(\"NumeronPrefs\", Context.MODE_PRIVATE)\n"
        "                val notifiedIds = prefs.getStringSet(\"notified_request_ids\", emptySet())?.toMutableSet() ?: mutableSetOf()\n"
        "                val baselineInitialized = prefs.getBoolean(\"requests_baseline_initialized\", false) || notifiedIds.isNotEmpty()\n"
        "                val nowMs = System.currentTimeMillis()\n"
        "                var changed = false\n"
        "                var processedFound = 0\n\n"
        "                val root = JSONObject(jsonStr)\n"
        "                val dataArray = root.optJSONArray(\"data\") ?: root.optJSONArray(\"Data\") ?: return 0\n"
        "                val en = DemoModeHelper.isEnglish(context)\n\n"
        "                for (i in 0 until dataArray.length()) {\n"
        "                    val item = dataArray.optJSONObject(i) ?: continue\n"
        "                    val id = item.optInt(\"Id\", -1).let { if (it > 0) it else item.optInt(\"RowId\", -1) }\n"
        "                    val rawStatus = parseStatusCode(item)\n"
        "                    val typeName = item.optString(\"Type\", if (en) \"Request\" else \"Toive\")\n"
        "                    val rawDesc = item.optString(\"StatusDescription\", \"\").trim()\n"
        "                    val statusId = resolveRequestStatusCode(rawStatus, rawDesc)\n"
        "                    val statusDesc = rawDesc.ifEmpty { fallbackStatusLabel(statusId, en) }\n"
        "                    val dateStr = formatRequestDate(item.optString(\"DateFrom\", \"\"))\n"
        "                    val bodyText = if (dateStr.isNotEmpty()) \"$typeName ($dateStr)\" else typeName\n"
        "                    val approvedMs = parseDotNetDateMs(item.optString(\"ApprovedDate\", \"\"))\n"
        "                    val approvedRecently = approvedMs != null && (nowMs - approvedMs) in 0L..(24L * 60L * 60L * 1000L)\n\n"
        "                    if (id > 0 && (statusId == 50 || statusId == 80 || statusId == 40)) {\n"
        "                        processedFound++\n"
        "                        val key = \"${id}_$statusId\"\n"
        "                        if (!notifiedIds.contains(key)) {\n"
        "                            notifiedIds.add(key)\n"
        "                            changed = true\n"
        "                            if (baselineInitialized || approvedRecently) {\n"
        "                                showRequestDecisionNotification(\n"
        "                                    context,\n"
        "                                    if (en) \"Request processed: $statusDesc\" else \"Toive käsitelty: $statusDesc\",\n"
        "                                    bodyText,\n"
        "                                    id\n"
        "                                )\n"
        "                                sentCount++\n"
        "                            }\n"
        "                        }\n"
        "                    }\n"
        "                }\n"
        "                prefs.edit().apply {\n"
        "                    putString(\"last_requests_check_status\", \"OK:${dataArray.length()}/$processedFound\")\n"
        "                    if (changed || !baselineInitialized) {\n"
        "                        putStringSet(\"notified_request_ids\", notifiedIds)\n"
        "                        putBoolean(\"requests_baseline_initialized\", true)\n"
        "                    }\n"
        "                }.apply()\n"
        "            } catch (_: Exception) {\n"
        "            }\n"
        "            return sentCount\n"
        "        }\n\n"
        "        private fun formatRequestDate(raw: String): String {\n"
        "            val trimmed = raw.trim()\n"
        "            if (trimmed.isEmpty() || trimmed.equals(\"null\", ignoreCase = true)) return \"\"\n"
        "            val fmt = java.time.format.DateTimeFormatter.ofPattern(\"dd.MM.yyyy\")\n"
        "            val ms = parseDotNetDateMs(trimmed)\n"
        "            if (ms != null) {\n"
        "                return java.time.Instant.ofEpochMilli(ms)\n"
        "                    .atZone(java.time.ZoneId.systemDefault())\n"
        "                    .toLocalDate()\n"
        "                    .format(fmt)\n"
        "            }\n"
        "            val isoMatch = Regex(\"^(\\\\d{4}-\\\\d{2}-\\\\d{2})\").find(trimmed)\n"
        "            if (isoMatch != null) {\n"
        "                return try {\n"
        "                    LocalDate.parse(isoMatch.groupValues[1]).format(fmt)\n"
        "                } catch (_: Exception) {\n"
        "                    \"\"\n"
        "                }\n"
        "            }\n"
        "            val fiMatch = Regex(\"^\\\\d{1,2}\\\\.\\\\d{1,2}\\\\.\\\\d{4}\").find(trimmed)\n"
        "            return fiMatch?.value ?: \"\"\n"
        "        }\n"
        "    }\n"
        "}"
    )

    text = replace_once(
        text,
        old_notif_tail,
        new_notif_tail,
        "Jaettu toiveiden tarkistus (tarkka Read-POST, merkkijono-Status, korjattu baseline + ApprovedDate)"
    )

    old_worker_call = (
        "            if (trackRequests) {\n"
        "                fetchRequestsJson(baseUrl)?.let { checkRequestUpdates(it) }\n"
        "            }"
    )
    new_worker_call = (
        "            if (trackRequests) {\n"
        "                ShiftReminderReceiver.syncRequestsAndNotify(appContext, baseUrl)\n"
        "            }"
    )
    text = replace_once(
        text,
        old_worker_call,
        new_worker_call,
        "BackgroundSyncWorker käyttää jaettua syncRequestsAndNotify-metodia"
    )

    old_worker_helpers = (
        "\n    private fun fetchRequestsJson(baseUrl: String): String? {\n"
        "        var conn: java.net.HttpURLConnection? = null\n"
        "        return try {\n"
        "            val cookies = CookieManager.getInstance().getCookie(baseUrl)\n"
        "            if (cookies.isNullOrBlank()) return null\n"
        "            conn = (java.net.URL(\"$baseUrl/PersonRequests/Read?selectedFilter=active\").openConnection() as java.net.HttpURLConnection).apply {\n"
        "                requestMethod = \"POST\"\n"
        "                setRequestProperty(\"Cookie\", cookies)\n"
        "                setRequestProperty(\"Content-Type\", \"application/x-www-form-urlencoded; charset=UTF-8\")\n"
        "                setRequestProperty(\"X-Requested-With\", \"XMLHttpRequest\")\n"
        "                doOutput = true\n"
        "                connectTimeout = 15000\n"
        "                readTimeout = 15000\n"
        "            }\n"
        "            java.io.OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { writer ->\n"
        "                writer.write(\"page=1&pageSize=50\")\n"
        "                writer.flush()\n"
        "            }\n"
        "            val text = if (conn.responseCode == 200) {\n"
        "                conn.inputStream.bufferedReader().use { it.readText() }\n"
        "            } else {\n"
        "                null\n"
        "            }\n"
        "            if (text != null && text.trim().startsWith(\"{\")) text else null\n"
        "        } catch (_: Exception) {\n"
        "            null\n"
        "        } finally {\n"
        "            conn?.disconnect()\n"
        "        }\n"
        "    }\n\n"
        "    private fun checkRequestUpdates(jsonStr: String) {\n"
        "        try {\n"
        "            val prefs = appContext.getSharedPreferences(\"NumeronPrefs\", Context.MODE_PRIVATE)\n"
        "            val baselineInitialized = prefs.getBoolean(\"requests_baseline_initialized\", false)\n"
        "            val notifiedIds = prefs.getStringSet(\"notified_request_ids\", emptySet())?.toMutableSet() ?: mutableSetOf()\n"
        "            var changed = false\n\n"
        "            val root = JSONObject(jsonStr)\n"
        "            val dataArray = root.optJSONArray(\"data\") ?: return\n\n"
        "            for (i in 0 until dataArray.length()) {\n"
        "                val item = dataArray.optJSONObject(i) ?: continue\n"
        "                val id = item.optInt(\"Id\", -1)\n"
        "                val statusId = item.optInt(\"Status\", -1)\n"
        "                val typeName = item.optString(\"Type\", \"Toive\")\n"
        "                val statusDesc = item.optString(\"StatusDescription\", \"\")\n"
        "                val dateStr = formatRequestDate(item.optString(\"DateFrom\", \"\"))\n"
        "                val bodyText = if (dateStr.isNotEmpty()) \"$typeName ($dateStr)\" else typeName\n\n"
        "                if (id > 0 && (statusId == 50 || statusId == 80 || statusId == 40)) {\n"
        "                    val key = \"${id}_$statusId\"\n"
        "                    if (!notifiedIds.contains(key)) {\n"
        "                        notifiedIds.add(key)\n"
        "                        changed = true\n"
        "                        if (baselineInitialized) {\n"
        "                            ShiftReminderReceiver.showRequestDecisionNotification(\n"
        "                                appContext,\n"
        "                                if (DemoModeHelper.isEnglish(appContext)) \"Request processed: $statusDesc\" else \"Toive käsitelty: $statusDesc\",\n"
        "                                bodyText,\n"
        "                                id\n"
        "                            )\n"
        "                        }\n"
        "                    }\n"
        "                }\n"
        "            }\n"
        "            if (changed || !baselineInitialized) {\n"
        "                prefs.edit()\n"
        "                    .putStringSet(\"notified_request_ids\", notifiedIds)\n"
        "                    .putBoolean(\"requests_baseline_initialized\", true)\n"
        "                    .apply()\n"
        "            }\n"
        "        } catch (_: Exception) {\n"
        "        }\n"
        "    }\n\n"
        "    private fun formatRequestDate(raw: String): String {\n"
        "        val trimmed = raw.trim()\n"
        "        if (trimmed.isEmpty() || trimmed.equals(\"null\", ignoreCase = true)) return \"\"\n"
        "        val fmt = java.time.format.DateTimeFormatter.ofPattern(\"dd.MM.yyyy\")\n"
        "        val msMatch = Regex(\"/Date\\\\((-?\\\\d+)\\\\)/\").find(trimmed)\n"
        "        if (msMatch != null) {\n"
        "            val ms = msMatch.groupValues[1].toLongOrNull() ?: return \"\"\n"
        "            return java.time.Instant.ofEpochMilli(ms)\n"
        "                .atZone(java.time.ZoneId.systemDefault())\n"
        "                .toLocalDate()\n"
        "                .format(fmt)\n"
        "        }\n"
        "        val isoMatch = Regex(\"^(\\\\d{4}-\\\\d{2}-\\\\d{2})\").find(trimmed)\n"
        "        if (isoMatch != null) {\n"
        "            return try {\n"
        "                LocalDate.parse(isoMatch.groupValues[1]).format(fmt)\n"
        "            } catch (_: Exception) {\n"
        "                \"\"\n"
        "            }\n"
        "        }\n"
        "        val fiMatch = Regex(\"^\\\\d{1,2}\\\\.\\\\d{1,2}\\\\.\\\\d{4}\").find(trimmed)\n"
        "        return fiMatch?.value ?: \"\"\n"
        "    }\n"
    )
    if old_worker_helpers in text:
        text = text.replace(old_worker_helpers, "", 1)
        print("  [PÄIVITETTY] Poistettu vanhat duplikaattifunktiot BackgroundSyncWorkerista")
    else:
        print("  [OK - jo sovellettu] Vanhat apufunktiot jo poistettu BackgroundSyncWorkerista")

    if text != orig:
        write_kt(path, text, nl)
        return True
    return False


def patch_main_activity(path: Path) -> bool:
    text, nl = read_kt(path)
    orig = text

    old_class_header = (
        "class MainActivity : AppCompatActivity() {\n\n"
        "    private lateinit var webView: WebView"
    )
    new_class_header = (
        "class MainActivity : AppCompatActivity() {\n\n"
        "    companion object {\n"
        "        @Volatile\n"
        "        private var cachedSafeDarkCss: String? = null\n\n"
        "        private val BLOCKED_CSS_PATTERNS = listOf(\n"
        "            \"/content/css/cssvisma\",\n"
        "            \"/content/css/login.css\",\n"
        "            \"/content/css/calendar.css\",\n"
        "            \"/content/css/buttons.css\",\n"
        "            \"/bundles/cssworktimestamping\",\n"
        "            \"/content/css/worktimestamping.css\",\n"
        "            \"/content/css/listlayout.css\",\n"
        "            \"fonts.googleapis.com\"\n"
        "        )\n"
        "    }\n\n"
        "    private lateinit var webView: WebView"
    )
    text = replace_once(
        text,
        old_class_header,
        new_class_header,
        "Lisätty companion object (CSS-välimuisti + vakioitu estolista)"
    )

    old_oncreate_bg = (
        "        requestNeededPermissions()\n"
        "        ShiftReminderReceiver.ensureBackgroundSyncScheduled(this)\n\n"
        "        scope.launch(Dispatchers.IO) {\n"
        "            CalendarSyncHelper.scheduleShiftReminders(this@MainActivity)\n"
        "        }\n\n"
        "        webView = findViewById(R.id.webView)"
    )
    new_oncreate_bg = (
        "        requestNeededPermissions()\n\n"
        "        webView = findViewById(R.id.webView)"
    )
    text = replace_once(
        text,
        old_oncreate_bg,
        new_oncreate_bg,
        "Poistettu synkroninen WorkManager-kutsu onCreate-pääsäikeestä"
    )

    old_oncreate_tail = (
        "        if (intent?.getBooleanExtra(\"OPEN_CALENDAR_CHANGES\", false) == true) {\n"
        "            intent.removeExtra(\"OPEN_CALENDAR_CHANGES\")\n"
        "            CalendarChangeTracker.showManageChangesDialog(this)\n"
        "        }\n"
        "    }"
    )
    new_oncreate_tail = (
        "        if (intent?.getBooleanExtra(\"OPEN_CALENDAR_CHANGES\", false) == true) {\n"
        "            intent.removeExtra(\"OPEN_CALENDAR_CHANGES\")\n"
        "            CalendarChangeTracker.showManageChangesDialog(this)\n"
        "        }\n\n"
        "        scope.launch(Dispatchers.IO) {\n"
        "            SecureCredentialManager.getUsername(this@MainActivity)\n"
        "            ShiftReminderReceiver.ensureBackgroundSyncScheduled(this@MainActivity)\n"
        "            CalendarSyncHelper.scheduleShiftReminders(this@MainActivity)\n"
        "        }\n"
        "    }"
    )
    text = replace_once(
        text,
        old_oncreate_tail,
        new_oncreate_tail,
        "Taustatehtävät ja Keystore-esilämmitys ajetaan IO-säikeessä WebView-latauksen jälkeen"
    )

    old_session_age = "                val maxSessionAgeMs = if (isAutoStamping) 10L * 60 * 1000L else 25L * 60 * 1000L"
    new_session_age = "                val maxSessionAgeMs = if (isAutoStamping) 10L * 60 * 1000L else 4L * 60 * 60 * 1000L"
    text = replace_once(
        text,
        old_session_age,
        new_session_age,
        "Normaalin navigoinnin maxSessionAgeMs 25 min -> 4 h"
    )

    old_intercept = (
        "                if (url.contains(\"amplitude.com\")) {\n"
        "                    return WebResourceResponse(\n"
        "                        \"application/javascript\",\n"
        "                        \"UTF-8\",\n"
        "                        ByteArrayInputStream(ByteArray(0))\n"
        "                    )\n"
        "                }\n\n"
        "                val blockedCssPatterns = listOf(\n"
        "                    \"/content/css/cssvisma\",\n"
        "                    \"/content/css/login.css\",\n"
        "                    \"/content/css/calendar.css\",\n"
        "                    \"/content/css/buttons.css\",\n"
        "                    \"/bundles/cssworktimestamping\",\n"
        "                    \"/content/css/worktimestamping.css\",\n"
        "                    \"/content/css/listlayout.css\",\n"
        "                    \"fonts.googleapis.com\"\n"
        "                )\n\n"
        "                if (blockedCssPatterns.any { url.contains(it) }) {"
    )
    new_intercept = (
        "                if (url.contains(\"amplitude\")) {\n"
        "                    return WebResourceResponse(\n"
        "                        \"application/javascript\",\n"
        "                        \"UTF-8\",\n"
        "                        ByteArrayInputStream(ByteArray(0))\n"
        "                    )\n"
        "                }\n\n"
        "                if (BLOCKED_CSS_PATTERNS.any { url.contains(it) }) {"
    )
    text = replace_once(
        text,
        old_intercept,
        new_intercept,
        "Paikallisen amplitude-min.js:n esto + vakioitu CSS-estolista"
    )

    old_reveal = "                val revealDelay = if (url.contains(\"/Calendar\", ignoreCase = true)) 280L else 180L"
    new_reveal = "                val revealDelay = if (url.contains(\"/Calendar\", ignoreCase = true)) 120L else 60L"
    text = replace_once(
        text,
        old_reveal,
        new_reveal,
        "Lyhennetty revealDelay (120 ms / 60 ms)"
    )

    old_css_start = '        val css = """'
    new_css_start = '        val safeCss = cachedSafeDarkCss ?: """'
    text = replace_once(
        text,
        old_css_start,
        new_css_start,
        "Tumman teeman CSS-välimuistin alku"
    )

    old_css_end = (
        '        """.trimIndent().replace("\\n", " ")\n\n'
        '        val safeCss = css\n'
        '            .replace("\\r", " ")\n'
        '            .replace("\\n", " ")\n'
        '            .replace("\\\\", "\\\\\\\\")\n'
        '            .replace("\'", "\\\\\'")'
    )
    new_css_end = (
        '        """.trimIndent()\n'
        '            .replace("\\r", " ")\n'
        '            .replace("\\n", " ")\n'
        '            .replace("\\\\", "\\\\\\\\")\n'
        '            .replace("\'", "\\\\\'")\n'
        '            .also { cachedSafeDarkCss = it }'
    )
    text = replace_once(
        text,
        old_css_end,
        new_css_end,
        "Tumman teeman CSS-välimuistin tallennus"
    )

    old_manual_sync = (
        "            CalendarSyncHelper.scheduleShiftReminders(this@MainActivity, calId)\n\n"
        "            withContext(Dispatchers.Main) {"
    )
    new_manual_sync = (
        "            CalendarSyncHelper.scheduleShiftReminders(this@MainActivity, calId)\n"
        "            if (prefs.getBoolean(\"track_requests\", true) && baseUrl.isNotBlank()) {\n"
        "                ShiftReminderReceiver.syncRequestsAndNotify(this@MainActivity, baseUrl)\n"
        "            }\n\n"
        "            withContext(Dispatchers.Main) {"
    )
    text = replace_once(
        text,
        old_manual_sync,
        new_manual_sync,
        "Toiveiden tilan tarkistus myös manuaalisessa synkronoinnissa"
    )

    if text != orig:
        write_kt(path, text, nl)
        return True
    return False


def main() -> int:
    changed = 0

    sr_path = find_file("ShiftReminderReceiver.kt")
    if sr_path is None:
        print("[EI LÖYTYNYT] ShiftReminderReceiver.kt")
    else:
        print(f"Käsitellään: {sr_path}")
        if patch_shift_reminder_receiver(sr_path):
            changed += 1

    ma_path = find_file("MainActivity.kt")
    if ma_path is None:
        print("[EI LÖYTYNYT] MainActivity.kt")
    else:
        print(f"Käsitellään: {ma_path}")
        if patch_main_activity(ma_path):
            changed += 1

    print(f"\nValmis! Muokattuja tiedostoja: {changed}.")
    print("Muista nostaa build.gradle(.kts) versionCode-arvoa +1 ennen Play Store -julkaisua.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
