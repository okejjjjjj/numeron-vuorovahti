#!/usr/bin/env python3
"""
Numeron Vuorovahti – ShiftReminderReceiver.kt toiveilmoitusten tarkennus (patch.py).
Päivittää nykyisen ShiftReminderReceiver.kt-tiedoston käyttämään:
- puhdasta POST /PersonRequests/Read -osoitetta (ilman query-parametria)
- merkkijonomuotoisen Status-kentän ("50") lukemista
- korjattua baseline-logiikkaa ja 24 h ApprovedDate-tarkistusta
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

    # 1. Poistetaan query-parametri URL:stä (selectedFilter lähtee jo POST-rungossa)
    old_url = 'java.net.URL("$baseUrl/PersonRequests/Read?selectedFilter=active")'
    new_url = 'java.net.URL("$baseUrl/PersonRequests/Read")'
    text = replace_once(
        text,
        old_url,
        new_url,
        "Read-kutsu ilman query-parametria (/PersonRequests/Read)"
    )

    # 2. Lisätään parseStatusCode merkkijonomuotoiselle Status-kentälle ("50")
    old_resolve = "        private fun resolveRequestStatusCode(rawStatus: Int, statusDesc: String): Int {"
    new_resolve = (
        "        private fun parseStatusCode(item: JSONObject): Int {\n"
        '            val fromStr = item.optString("Status", "").trim().toIntOrNull()\n'
        '                ?: item.optString("StatusId", "").trim().toIntOrNull()\n'
        "            if (fromStr != null) return fromStr\n"
        '            val fromInt = item.optInt("Status", -1)\n'
        '            return if (fromInt > 0) fromInt else item.optInt("StatusId", -1)\n'
        "        }\n\n"
        "        private fun resolveRequestStatusCode(rawStatus: Int, statusDesc: String): Int {"
    )
    text = replace_once(
        text,
        old_resolve,
        new_resolve,
        "Merkkijono-Status-kentän jäsentäjä (parseStatusCode)"
    )

    # 3. Korjataan baselineInitialized, ApprovedDate-tarkistus ja parseStatusCode käyttö checkRequestUpdates-metodissa
    old_check = (
        "        private fun checkRequestUpdates(context: Context, jsonStr: String): Int {\n"
        "            var sentCount = 0\n"
        "            try {\n"
        '                val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n'
        '                val baselineInitialized = prefs.getBoolean("requests_baseline_initialized", false)\n'
        '                val notifiedIds = prefs.getStringSet("notified_request_ids", emptySet())?.toMutableSet() ?: mutableSetOf()\n'
        "                var changed = false\n"
        "                var processedFound = 0\n\n"
        "                val root = JSONObject(jsonStr)\n"
        '                val dataArray = root.optJSONArray("data") ?: root.optJSONArray("Data") ?: return 0\n'
        "                val en = DemoModeHelper.isEnglish(context)\n\n"
        "                for (i in 0 until dataArray.length()) {\n"
        "                    val item = dataArray.optJSONObject(i) ?: continue\n"
        '                    val id = item.optInt("Id", -1).let { if (it > 0) it else item.optInt("RowId", -1) }\n'
        '                    val rawStatus = item.optInt("Status", -1).let { if (it > 0) it else item.optInt("StatusId", -1) }\n'
        '                    val typeName = item.optString("Type", if (en) "Request" else "Toive")\n'
        '                    val rawDesc = item.optString("StatusDescription", "").trim()\n'
        "                    val statusId = resolveRequestStatusCode(rawStatus, rawDesc)\n"
        "                    val statusDesc = rawDesc.ifEmpty { fallbackStatusLabel(statusId, en) }\n"
        '                    val dateStr = formatRequestDate(item.optString("DateFrom", ""))\n'
        '                    val bodyText = if (dateStr.isNotEmpty()) "$typeName ($dateStr)" else typeName\n\n'
        "                    if (id > 0 && (statusId == 50 || statusId == 80 || statusId == 40)) {\n"
        "                        processedFound++\n"
        '                        val key = "${id}_$statusId"\n'
        "                        if (!notifiedIds.contains(key)) {\n"
        "                            notifiedIds.add(key)\n"
        "                            changed = true\n"
        "                            if (baselineInitialized) {\n"
        "                                showRequestDecisionNotification(\n"
        "                                    context,\n"
        '                                    if (en) "Request processed: $statusDesc" else "Toive käsitelty: $statusDesc",\n'
        "                                    bodyText,\n"
        "                                    id\n"
        "                                )\n"
        "                                sentCount++\n"
        "                            }\n"
        "                        }\n"
        "                    }\n"
        "                }"
    )

    new_check = (
        "        private fun parseDotNetDateMs(raw: String): Long? {\n"
        '            val match = Regex("/Date\\\\((-?\\\\d+)\\\\)/").find(raw.trim()) ?: return null\n'
        "            return match.groupValues[1].toLongOrNull()\n"
        "        }\n\n"
        "        private fun checkRequestUpdates(context: Context, jsonStr: String): Int {\n"
        "            var sentCount = 0\n"
        "            try {\n"
        '                val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)\n'
        '                val notifiedIds = prefs.getStringSet("notified_request_ids", emptySet())?.toMutableSet() ?: mutableSetOf()\n'
        '                val baselineInitialized = prefs.getBoolean("requests_baseline_initialized", false) || notifiedIds.isNotEmpty()\n'
        "                val nowMs = System.currentTimeMillis()\n"
        "                var changed = false\n"
        "                var processedFound = 0\n\n"
        "                val root = JSONObject(jsonStr)\n"
        '                val dataArray = root.optJSONArray("data") ?: root.optJSONArray("Data") ?: return 0\n'
        "                val en = DemoModeHelper.isEnglish(context)\n\n"
        "                for (i in 0 until dataArray.length()) {\n"
        "                    val item = dataArray.optJSONObject(i) ?: continue\n"
        '                    val id = item.optInt("Id", -1).let { if (it > 0) it else item.optInt("RowId", -1) }\n'
        "                    val rawStatus = parseStatusCode(item)\n"
        '                    val typeName = item.optString("Type", if (en) "Request" else "Toive")\n'
        '                    val rawDesc = item.optString("StatusDescription", "").trim()\n'
        "                    val statusId = resolveRequestStatusCode(rawStatus, rawDesc)\n"
        "                    val statusDesc = rawDesc.ifEmpty { fallbackStatusLabel(statusId, en) }\n"
        '                    val dateStr = formatRequestDate(item.optString("DateFrom", ""))\n'
        '                    val bodyText = if (dateStr.isNotEmpty()) "$typeName ($dateStr)" else typeName\n'
        '                    val approvedMs = parseDotNetDateMs(item.optString("ApprovedDate", ""))\n'
        "                    val approvedRecently = approvedMs != null && (nowMs - approvedMs) in 0L..(24L * 60L * 60L * 1000L)\n\n"
        "                    if (id > 0 && (statusId == 50 || statusId == 80 || statusId == 40)) {\n"
        "                        processedFound++\n"
        '                        val key = "${id}_$statusId"\n'
        "                        if (!notifiedIds.contains(key)) {\n"
        "                            notifiedIds.add(key)\n"
        "                            changed = true\n"
        "                            if (baselineInitialized || approvedRecently) {\n"
        "                                showRequestDecisionNotification(\n"
        "                                    context,\n"
        '                                    if (en) "Request processed: $statusDesc" else "Toive käsitelty: $statusDesc",\n'
        "                                    bodyText,\n"
        "                                    id\n"
        "                                )\n"
        "                                sentCount++\n"
        "                            }\n"
        "                        }\n"
        "                    }\n"
        "                }"
    )

    text = replace_once(
        text,
        old_check,
        new_check,
        "checkRequestUpdates (parseStatusCode, korjattu baseline + 24 h ApprovedDate)"
    )

    # 4. Hyödynnetään parseDotNetDateMs myös formatRequestDate-metodissa
    old_fmt = (
        '            val msMatch = Regex("/Date\\\\((-?\\\\d+)\\\\)/").find(trimmed)\n'
        "            if (msMatch != null) {\n"
        '                val ms = msMatch.groupValues[1].toLongOrNull() ?: return ""'
    )
    new_fmt = (
        "            val ms = parseDotNetDateMs(trimmed)\n"
        "            if (ms != null) {"
    )
    text = replace_once(
        text,
        old_fmt,
        new_fmt,
        "formatRequestDate käyttää parseDotNetDateMs-apufunktiota"
    )

    if text != orig:
        write_kt(path, text, nl)
        return True
    return False


def main() -> int:
    sr_path = find_file("ShiftReminderReceiver.kt")
    if sr_path is None:
        print("[EI LÖYTYNYT] ShiftReminderReceiver.kt")
        return 1

    print(f"Käsitellään: {sr_path}")
    changed = patch_shift_reminder_receiver(sr_path)
    print(f"\nValmis! Muokattuja tiedostoja: {1 if changed else 0}.")
    print("Muista nostaa build.gradle(.kts) versionCode-arvoa +1 ennen Play Store -julkaisua.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
