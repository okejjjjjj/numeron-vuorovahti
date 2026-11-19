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
        raise RuntimeError(
            f"[{path.name}] Aaltosulkeiden määrä ei täsmää ({cleaned.count('{')} vs {cleaned.count('}')})"
        )
    if cleaned.count("(") != cleaned.count(")"):
        raise RuntimeError(
            f"[{path.name}] Kaarisulkeiden määrä ei täsmää ({cleaned.count('(')} vs {cleaned.count(')')})"
        )


def replace_exact(path: pathlib.Path, content: str, old: str, new: str) -> str:
    if old not in content:
        raise RuntimeError(f"[{path.name}] Korvattavaa lohkoa ei löytynyt:\n{old[:120]}...")
    return content.replace(old, new, 1)


def increment_version() -> None:
    gradle_candidates = [
        pathlib.Path("app/build.gradle.kts"),
        pathlib.Path("app/build.gradle"),
    ]
    gradle_file = next((p for p in gradle_candidates if p.exists()), None)
    if not gradle_file:
        matches = list(pathlib.Path(".").rglob("build.gradle*"))
        gradle_file = next((p for p in matches if "app" in p.parts), None)

    if not gradle_file:
        print("Varoitus: app/build.gradle(.kts) ei löytynyt, versionumeroa ei päivitetty.")
        return

    text = gradle_file.read_text(encoding="utf-8")

    vc_match = re.search(r'(versionCode\s*=?\s*)(\d+)', text)
    if vc_match:
        old_vc = int(vc_match.group(2))
        new_vc = old_vc + 1
        text = text[:vc_match.start(2)] + str(new_vc) + text[vc_match.end(2):]
        print(f"Päivitetty versionCode: {old_vc} -> {new_vc}")

    vn_match = re.search(r'(versionName\s*=?\s*")(\d+(?:\.\d+)*)(")', text)
    if vn_match:
        parts = vn_match.group(2).split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        new_vn = ".".join(parts)
        text = text[:vn_match.start(2)] + new_vn + text[vn_match.end(2):]
        print(f"Päivitetty versionName: {vn_match.group(2)} -> {new_vn}")

    gradle_file.write_text(text, encoding="utf-8")


def main() -> None:
    cal_helper = find_file("CalendarSyncHelper.kt")
    cal_src = cal_helper.read_text(encoding="utf-8")

    old_schedule_block = """            if (!continuesFromPrev) {
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

    new_schedule_block = """            if (!continuesFromPrev) {
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
            }"""

    old_alarm_fn = """    private fun setExactAlarmSafe(
        context: Context,
        alarmManager: AlarmManager,
        triggerMs: Long,
        title: String,
        timeStr: String,
        isEnding: Boolean
    ): Int {
        val reqCode = ((triggerMs / 60_000L).toInt() * 2) + (if (isEnding) 1 else 0)
        val intent = Intent(context, ShiftReminderReceiver.InternalReceiver::class.java).apply {
            action = ShiftReminderReceiver.ACTION_SHIFT_REMINDER
            putExtra("SHIFT_TITLE", title)
            putExtra("SHIFT_TIME", timeStr)
            putExtra("IS_ENDING", isEnding)
        }"""

    new_alarm_fn = """    private fun setExactAlarmSafe(
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
        }"""

    cal_src = replace_exact(cal_helper, cal_src, old_schedule_block, new_schedule_block)
    cal_src = replace_exact(cal_helper, cal_src, old_alarm_fn, new_alarm_fn)
    verify_kotlin_delimiters(cal_helper, cal_src)
    cal_helper.write_text(cal_src, encoding="utf-8")
    print(f"Päivitetty: {cal_helper}")

    receiver_file = find_file("ShiftReminderReceiver.kt")
    rec_src = receiver_file.read_text(encoding="utf-8")

    old_receiver_block = """            if (action != ACTION_SHIFT_REMINDER) return

            val title = intent.getStringExtra("SHIFT_TITLE") ?: "Työvuoro"
            val timeStr = intent.getStringExtra("SHIFT_TIME") ?: ""
            val isEnding = intent.getBooleanExtra("IS_ENDING", false)

            ShiftReminderReceiver().showReminderNotification(context, title, timeStr, isEnding)"""

    new_receiver_block = """            if (action != ACTION_SHIFT_REMINDER) return

            val title = intent.getStringExtra("SHIFT_TITLE") ?: "Työvuoro"
            val timeStr = intent.getStringExtra("SHIFT_TIME") ?: ""
            val isEnding = intent.getBooleanExtra("IS_ENDING", false)
            val shiftStartMs = intent.getLongExtra("SHIFT_START_MS", 0L)

            if (!isEnding && shiftStartMs > 0L) {
                context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                    .edit()
                    .putLong("notified_ongoing_start_ms", shiftStartMs)
                    .apply()
            }

            ShiftReminderReceiver().showReminderNotification(context, title, timeStr, isEnding)"""

    rec_src = replace_exact(receiver_file, rec_src, old_receiver_block, new_receiver_block)
    verify_kotlin_delimiters(receiver_file, rec_src)
    receiver_file.write_text(rec_src, encoding="utf-8")
    print(f"Päivitetty: {receiver_file}")

    increment_version()


if __name__ == "__main__":
    main()
