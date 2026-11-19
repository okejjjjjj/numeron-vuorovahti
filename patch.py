#!/usr/bin/env python3
import pathlib
import re

def find_file(filename: str) -> pathlib.Path:
    direct = pathlib.Path(filename)
    if direct.exists():
        return direct
    matches = list(pathlib.Path(".").rglob(filename))
    if matches:
        return matches[0]
    raise FileNotFoundError(f"Tiedostoa {filename} ei löytynyt!")

def verify_kotlin_delimiters(path: pathlib.Path, content: str) -> None:
    cleaned = re.sub(r'""".*?"""', '', content, flags=re.DOTALL)
    cleaned = re.sub(r'"(?:\\.|[^"\\])*"', '', cleaned)
    if cleaned.count("{") != cleaned.count("}"):
        raise RuntimeError(f"[{path.name}] Aaltosulkeiden määrä ei täsmää ({cleaned.count('{')} vs {cleaned.count('}')})")
    if cleaned.count("(") != cleaned.count(")"):
        raise RuntimeError(f"[{path.name}] Kaarisulkeiden määrä ei täsmää ({cleaned.count('(')} vs {cleaned.count(')')})")

def patch_manifest() -> None:
    path = find_file("AndroidManifest.xml")
    content = path.read_text(encoding="utf-8")
    perm = '<uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />'
    if perm not in content:
        anchor = '<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />'
        if anchor not in content:
            raise RuntimeError("AndroidManifest.xml: ankkuririviä RECEIVE_BOOT_COMPLETED ei löytynyt.")
        content = content.replace(anchor, f"{anchor}\n    {perm}", 1)
        path.write_text(content, encoding="utf-8")
        print(f"[OK] {path}: Lisätty REQUEST_IGNORE_BATTERY_OPTIMIZATIONS -lupa.")
    else:
        print(f"[OK] {path}: REQUEST_IGNORE_BATTERY_OPTIMIZATIONS on jo olemassa.")

def patch_settings_dialog() -> None:
    path = find_file("SettingsDialogHelper.kt")
    content = path.read_text(encoding="utf-8")

    old_block = """        val powerManager = context.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        val ignoringBatteryOpt = powerManager.isIgnoringBatteryOptimizations(context.packageName)
        val (batteryOptValueTv, batteryOptSubTv) = addStatusRow(
            statusCard,
            "Akun virransäästörajoitukset",
            if (ignoringBatteryOpt) "Ei rajoitettu (taustasynkronointi aktiivinen)" else "Optimoitu – napauta poistaaksesi rajoitus",
            if (ignoringBatteryOpt) null else "Varmistaa tausta-ajojen toiminnan lepotilassa"
        )
        if (!ignoringBatteryOpt) {
            statusCard.getChildAt(statusCard.childCount - 1).setOnClickListener {
                try {
                    context.startActivity(
                        android.content.Intent(
                            android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                            android.net.Uri.parse("package:${context.packageName}")
                        ).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                    )
                } catch (_: Exception) {
                }
            }
        }"""

    new_block = """        val powerManager = context.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        val ignoringBatteryOpt = powerManager.isIgnoringBatteryOptimizations(context.packageName)
        val (batteryOptValueTv, batteryOptSubTv) = addStatusRow(
            statusCard,
            "Akun virransäästörajoitukset",
            if (ignoringBatteryOpt) "Ei rajoitettu (taustasynkronointi aktiivinen)" else "Optimoitu – napauta poistaaksesi rajoitus",
            if (ignoringBatteryOpt) "Napauta avataksesi virransäästöasetukset" else "Varmistaa tausta-ajojen toiminnan lepotilassa"
        )
        statusCard.getChildAt(statusCard.childCount - 1).setOnClickListener {
            openBatteryOptimizationSettings()
        }"""

    if old_block in content:
        content = content.replace(old_block, new_block, 1)
    elif new_block not in content:
        raise RuntimeError("SettingsDialogHelper.kt: Virransäästörivin koodilohkoa ei löytynyt.")

    old_helper = """        fun openBatteryOptimizationSettings() {
            val pkgUri = android.net.Uri.parse("package:${context.packageName}")
            val openedDirect = launchSystemSettingsIntent(
                android.content.Intent(
                    android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                    pkgUri
                )
            )
            if (!openedDirect) {"""

    new_helper = """        fun openBatteryOptimizationSettings() {
            val pkgUri = android.net.Uri.parse("package:${context.packageName}")
            val isAlreadyIgnored = (context.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager)
                .isIgnoringBatteryOptimizations(context.packageName)
            val openedDirect = if (!isAlreadyIgnored) {
                launchSystemSettingsIntent(
                    android.content.Intent(
                        android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                        pkgUri
                    )
                )
            } else {
                false
            }
            if (!openedDirect) {"""

    if old_helper in content:
        content = content.replace(old_helper, new_helper, 1)
    elif new_helper not in content:
        raise RuntimeError("SettingsDialogHelper.kt: openBatteryOptimizationSettings-funktiota ei löytynyt.")

    verify_kotlin_delimiters(path, content)
    path.write_text(content, encoding="utf-8")
    print(f"[OK] {path}: Korjattu virransäästöasetusten avaus.")

def patch_numeron_parser() -> None:
    path = find_file("NumeronParser.kt")
    content = path.read_text(encoding="utf-8")

    old_block = """        for (cell in dayCells) {
            if (cell.hasClass("past-day") || cell.hasClass("day-different-month")) continue

            val dayNum = cell.selectFirst(".dayNum")?.text()?.trim()?.toIntOrNull() ?: continue
            val date = LocalDate.of(currentYear, currentMonth, dayNum)

            if (date.isBefore(today)) continue

            cell.select(".month-item.work").forEach { item ->
                val timesText = item.selectFirst(".itemTimes")?.text()?.trim() ?: ""
                val rawNameText = item.selectFirst(".itemName")?.text()?.trim() ?: ""

                val timeParts = timesText.split("-").map { it.trim() }
                if (timeParts.size == 2) {
                    val startTime = try {
                        LocalTime.parse(timeParts[0], DateTimeFormatter.ofPattern("H:mm"))
                    } catch (_: Exception) {
                        return@forEach
                    }
                    val endTime = try {
                        LocalTime.parse(timeParts[1], DateTimeFormatter.ofPattern("H:mm"))
                    } catch (_: Exception) {
                        return@forEach
                    }

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
        }"""

    new_block = """        for (cell in dayCells) {
            if (cell.hasClass("day-different-month")) continue

            val dayNum = cell.selectFirst(".dayNum")?.text()?.trim()?.toIntOrNull() ?: continue
            val date = LocalDate.of(currentYear, currentMonth, dayNum)

            // Sallitaan eilinen yövuorojen varalta, jotka päättyvät tänään nykyhetken jälkeen
            if (date.isBefore(today.minusDays(1))) continue

            cell.select(".month-item.work").forEach { item ->
                val timesText = item.selectFirst(".itemTimes")?.text()?.trim() ?: ""
                val rawNameText = item.selectFirst(".itemName")?.text()?.trim() ?: ""

                val timeParts = timesText.split("-").map { it.trim() }
                if (timeParts.size == 2) {
                    val startTime = try {
                        LocalTime.parse(timeParts[0], DateTimeFormatter.ofPattern("H:mm"))
                    } catch (_: Exception) {
                        return@forEach
                    }
                    val endTime = try {
                        LocalTime.parse(timeParts[1], DateTimeFormatter.ofPattern("H:mm"))
                    } catch (_: Exception) {
                        return@forEach
                    }

                    val startDateTime = LocalDateTime.of(date, startTime)
                    var endDate = date
                    if (endTime.isBefore(startTime)) {
                        endDate = date.plusDays(1)
                    }
                    val endDateTime = LocalDateTime.of(endDate, endTime)

                    // Huomioidaan tulevat sekä parhaillaan meneillään olevat työvuorot
                    if (!endDateTime.isAfter(now)) return@forEach

                    val parsed = parseShiftText(rawNameText)
                    val comment = listOf(parsed.shiftName, parsed.role)
                        .filter { it.isNotBlank() }
                        .joinToString(" • ")

                    shifts.add(
                        WorkShift(
                            title = "Työvuoro",
                            start = startDateTime,
                            end = endDateTime,
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
                val leaveEnd = date.plusDays(1).atStartOfDay()
                if (!leaveEnd.isAfter(now)) return@forEach

                shifts.add(
                    WorkShift(
                        title = nameText,
                        start = leaveStart,
                        end = leaveEnd,
                        isAllDayLeave = true,
                        location = "",
                        description = ""
                    )
                )
            }
        }"""

    if old_block in content:
        content = content.replace(old_block, new_block, 1)
    elif new_block not in content:
        raise RuntimeError("NumeronParser.kt: Vuorojen parsintalohkoa ei löytynyt.")

    verify_kotlin_delimiters(path, content)
    path.write_text(content, encoding="utf-8")
    print(f"[OK] {path}: Meneillään olevat työvuorot ja poissaolot otettu mukaan.")

def patch_shift_reminder_receiver() -> None:
    path = find_file("ShiftReminderReceiver.kt")
    content = path.read_text(encoding="utf-8")

    old_sig = """    fun showReminderNotification(
        context: Context,
        shiftTitle: String,
        timeStr: String,
        isEnding: Boolean,
        isTest: Boolean = false
    ) {"""

    new_sig = """    fun showReminderNotification(
        context: Context,
        shiftTitle: String,
        timeStr: String,
        isEnding: Boolean,
        isTest: Boolean = false,
        rescheduleNext: Boolean = true
    ) {"""

    if old_sig in content:
        content = content.replace(old_sig, new_sig, 1)
    elif new_sig not in content:
        raise RuntimeError("ShiftReminderReceiver.kt: showReminderNotification-signatuuria ei löytynyt.")

    old_resched = """        if (!isTest) {
            CalendarSyncHelper.scheduleShiftReminders(context)
        }"""

    new_resched = """        if (!isTest && rescheduleNext) {
            CalendarSyncHelper.scheduleShiftReminders(context)
        }"""

    if old_resched in content:
        content = content.replace(old_resched, new_resched, 1)
    elif new_resched not in content:
        raise RuntimeError("ShiftReminderReceiver.kt: rescheduleNext-kohtaa ei löytynyt.")

    verify_kotlin_delimiters(path, content)
    path.write_text(content, encoding="utf-8")
    print(f"[OK] {path}: Lisätty rescheduleNext-parametri välittömiä muistutuksia varten.")

def patch_calendar_sync_helper() -> None:
    path = find_file("CalendarSyncHelper.kt")
    content = path.read_text(encoding="utf-8")

    old_upcoming = "        val upcomingShifts = shifts.filter { it.start.isAfter(now) }"
    new_upcoming = "        val upcomingShifts = shifts.filter { it.end.isAfter(now) }"
    if old_upcoming in content:
        content = content.replace(old_upcoming, new_upcoming, 1)
    elif new_upcoming not in content:
        raise RuntimeError("CalendarSyncHelper.kt: upcomingShifts-suodatinta ei löytynyt.")

    old_reminder_loop = """            if (!continuesFromPrev) {
                val startTrigger = current.startMs - (minutesBefore * 60_000L)
                if (startTrigger > now) {
                    val startStr = Instant.ofEpochMilli(current.startMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                    val code = setExactAlarmSafe(context, alarmManager, startTrigger, current.displayTitle, startStr, isEnding = false)
                    newReqCodes.add(code.toString())
                    if (startTrigger < earliestNextTriggerMs) {
                        earliestNextTriggerMs = startTrigger
                        earliestNextLabel = "Sisään (${current.displayTitle}, vuoro klo $startStr)"
                    }
                }
            }"""

    new_reminder_loop = """            if (!continuesFromPrev) {
                val startTrigger = current.startMs - (minutesBefore * 60_000L)
                val startStr = Instant.ofEpochMilli(current.startMs).atZone(ZoneId.systemDefault()).toLocalTime().format(timeFmt)
                if (startTrigger > now) {
                    val code = setExactAlarmSafe(context, alarmManager, startTrigger, current.displayTitle, startStr, isEnding = false)
                    newReqCodes.add(code.toString())
                    if (startTrigger < earliestNextTriggerMs) {
                        earliestNextTriggerMs = startTrigger
                        earliestNextLabel = "Sisään (${current.displayTitle}, vuoro klo $startStr)"
                    }
                } else if (current.endMs - now > 15L * 60_000L) {
                    // Vuoro on jo meneillään tai alkamassa hetken kuluttua eikä sisäänleimausmuistutusta ole vielä lähetetty
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
            }"""

    if old_reminder_loop in content:
        content = content.replace(old_reminder_loop, new_reminder_loop, 1)
    elif new_reminder_loop not in content:
        raise RuntimeError("CalendarSyncHelper.kt: Muistutusten ajastuslohkoa ei löytynyt.")

    verify_kotlin_delimiters(path, content)
    path.write_text(content, encoding="utf-8")
    print(f"[OK] {path}: Kalenterilisäys ja leimausmuistutus lisätty myös meneillään oleville vuoroille.")

def bump_version() -> None:
    gradle_files = sorted(
        list(pathlib.Path(".").rglob("build.gradle.kts")) + list(pathlib.Path(".").rglob("build.gradle")),
        key=lambda p: (0 if "app" in p.parts else 1, len(p.parts))
    )
    for gpath in gradle_files:
        text = gpath.read_text(encoding="utf-8")
        vc_match = re.search(r'(versionCode\s*=?\s*)(\d+)', text)
        if not vc_match:
            continue

        old_vc = int(vc_match.group(2))
        new_vc = old_vc + 1
        text = text[:vc_match.start(2)] + str(new_vc) + text[vc_match.end(2):]

        vn_3 = re.search(r'(versionName\s*=?\s*")(\d+\.\d+\.)(\d+)(")', text)
        if vn_3:
            new_vn = f"{vn_3.group(2)}{int(vn_3.group(3)) + 1}"
            text = text[:vn_3.start(2)] + new_vn + text[vn_3.end(3):]
        else:
            vn_2 = re.search(r'(versionName\s*=?\s*")(\d+\.\d+)(")', text)
            if not vn_2:
                raise RuntimeError(f"{gpath}: versionName-muotoa ei tunnistettu.")
            new_vn = f"{vn_2.group(2)}.1"
            text = text[:vn_2.start(2)] + new_vn + text[vn_2.end(2):]

        gpath.write_text(text, encoding="utf-8")
        print(f"[OK] {gpath}: versionCode {old_vc} -> {new_vc}, versionName -> {new_vn}")
        return

    raise RuntimeError("Yhtään build.gradle(.kts)-tiedostoa, jossa on versionCode, ei löytynyt!")

def main() -> None:
    patch_manifest()
    patch_settings_dialog()
    patch_numeron_parser()
    patch_shift_reminder_receiver()
    patch_calendar_sync_helper()
    bump_version()
    print("[VALMIS] Kaikki muutokset ja versionumeron nosto suoritettu.")

if __name__ == "__main__":
    main()
