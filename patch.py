import os
import re


def find_file(filename):
    for root, _, files in os.walk("."):
        if filename in files:
            return os.path.join(root, filename)
    return None


def remove_brace_block(text: str, marker: str) -> str:
    idx = text.find(marker)
    if idx == -1:
        return text

    line_start = text.rfind("\n", 0, idx)
    block_start = 0 if line_start == -1 else line_start

    brace_idx = text.find("{", idx)
    if brace_idx == -1:
        return text

    depth = 0
    pos = brace_idx
    while pos < len(text):
        ch = text[pos]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_pos = pos + 1
                while end_pos < len(text) and text[end_pos] in ("\r", "\n"):
                    end_pos += 1
                return text[:block_start] + "\n" + text[end_pos:]
        pos += 1

    return text


def remove_exact_alarm_status_block(text: str) -> str:
    start_marker = "val exactAlarmAllowed = canScheduleExactAlarmsCompat()"
    start_idx = text.find(start_marker)
    if start_idx == -1:
        return text

    line_start = text.rfind("\n", 0, start_idx)
    block_start = 0 if line_start == -1 else line_start

    if_marker = "if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {"
    if_idx = text.find(if_marker, start_idx)
    if if_idx == -1:
        return text

    brace_start = text.find("{", if_idx)
    depth = 0
    pos = brace_start
    while pos < len(text):
        if text[pos] == "{":
            depth += 1
        elif text[pos] == "}":
            depth -= 1
            if depth == 0:
                end_pos = pos + 1
                while end_pos < len(text) and text[end_pos] in ("\r", "\n"):
                    end_pos += 1
                return text[:block_start] + "\n" + text[end_pos:]
        pos += 1

    return text


def remove_exact_alarm_notice_box(text: str) -> str:
    marker = "val exactAlarmNoticeBox = LinearLayout(context).apply {"
    idx = text.find(marker)
    if idx == -1:
        return text

    line_start = text.rfind("\n", 0, idx)
    block_start = 0 if line_start == -1 else line_start

    add_view_marker = "reminderDetailsContainer.addView(exactAlarmNoticeBox)"
    add_idx = text.find(add_view_marker, idx)
    if add_idx == -1:
        return text

    end_pos = add_idx + len(add_view_marker)
    while end_pos < len(text) and text[end_pos] in ("\r", "\n"):
        end_pos += 1

    return text[:block_start] + "\n" + text[end_pos:]


def remove_now_exact_allowed_block(text: str) -> str:
    marker = "val nowExactAllowed = canScheduleExactAlarmsCompat()"
    idx = text.find(marker)
    if idx == -1:
        return text

    line_start = text.rfind("\n", 0, idx)
    block_start = 0 if line_start == -1 else line_start

    if_marker = "if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {"
    if_idx = text.find(if_marker, idx)
    if if_idx == -1:
        return text

    brace_start = text.find("{", if_idx)
    depth = 0
    pos = brace_start
    while pos < len(text):
        if text[pos] == "{":
            depth += 1
        elif text[pos] == "}":
            depth -= 1
            if depth == 0:
                end_pos = pos + 1
                while end_pos < len(text) and text[end_pos] in ("\r", "\n"):
                    end_pos += 1
                return text[:block_start] + "\n" + text[end_pos:]
        pos += 1

    return text


def patch_manifest(path):
    if not path or not os.path.exists(path):
        print("HUOM: AndroidManifest.xml ei löytynyt.")
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    updated, _ = re.subn(
        r"[ \t]*<uses-permission\s+android:name=\"android\.permission\.(?:SCHEDULE_EXACT_ALARM|USE_EXACT_ALARM)\"\s*/>\s*\r?\n?",
        "",
        content,
    )

    if updated != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(updated)
        print(f"OK: {path} — SCHEDULE_EXACT_ALARM poistettu.")
    else:
        print(f"OK: {path} — ei SCHEDULE_EXACT_ALARM-riviä poistettavana.")


def patch_settings_dialog_helper(path):
    if not path or not os.path.exists(path):
        print("HUOM: SettingsDialogHelper.kt ei löytynyt.")
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    updated = content
    updated = remove_brace_block(updated, "fun canScheduleExactAlarmsCompat(): Boolean {")
    updated = remove_brace_block(updated, "fun openExactAlarmSettings() {")
    updated = remove_exact_alarm_status_block(updated)
    updated = remove_exact_alarm_notice_box(updated)

    updated, _ = re.subn(
        r"\r?\n[ \t]*var lastKnownExactAlarmAllowed = canScheduleExactAlarmsCompat\(\)",
        "",
        updated,
    )
    updated = remove_now_exact_allowed_block(updated)
    updated = remove_brace_block(updated, "if (!lastKnownExactAlarmAllowed && nowExactAllowed) {")
    updated, _ = re.subn(
        r"\r?\n[ \t]*lastKnownExactAlarmAllowed = nowExactAllowed",
        "",
        updated,
    )

    assert "fun showSettingsDialog(" in updated, "VIRHE: showSettingsDialog puuttuu SettingsDialogHelper.kt:stä!"
    assert updated.count("{") == updated.count("}"), (
        f"VIRHE: SettingsDialogHelper.kt aaltosulut eivät ole tasan ({{={updated.count('{')}, }}={updated.count('}')})"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)
    print(
        f"OK: {path} — tarkat vuorohälytykset ja duplikaatti poistettu ({{={updated.count('{')}, }}={updated.count('}')})."
    )


def patch_calendar_sync_helper(path):
    if not path or not os.path.exists(path):
        print("HUOM: CalendarSyncHelper.kt ei löytynyt.")
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    old_block = (
        "        try {\n"
        "            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !alarmManager.canScheduleExactAlarms()) {\n"
        "                alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerMs, pi)\n"
        "            } else {\n"
        "                alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerMs, pi)\n"
        "            }\n"
        "        } catch (_: SecurityException) {\n"
        "            alarmManager.set(AlarmManager.RTC_WAKEUP, triggerMs, pi)\n"
        "        }"
    )

    new_block = (
        "        try {\n"
        "            alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerMs, pi)\n"
        "        } catch (_: SecurityException) {\n"
        "            alarmManager.set(AlarmManager.RTC_WAKEUP, triggerMs, pi)\n"
        "        }"
    )

    if old_block in content:
        updated = content.replace(old_block, new_block, 1)
    else:
        updated, _ = re.subn(
            r"if \(Build\.VERSION\.SDK_INT >= Build\.VERSION_CODES\.S && !alarmManager\.canScheduleExactAlarms\(\)\) \{\s*"
            r"alarmManager\.setAndAllowWhileIdle\(AlarmManager\.RTC_WAKEUP, triggerMs, pi\)\s*"
            r"\}\s*else\s*\{\s*"
            r"alarmManager\.setExactAndAllowWhileIdle\(AlarmManager\.RTC_WAKEUP, triggerMs, pi\)\s*"
            r"\}",
            "alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerMs, pi)",
            content,
            count=1,
        )

    assert updated.count("{") == updated.count("}"), (
        f"VIRHE: CalendarSyncHelper.kt aaltosulut eivät ole tasan ({{={updated.count('{')}, }}={updated.count('}')})"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)
    print(f"OK: {path} — setExactAlarmSafe päivitetty.")


def bump_version_code():
    for candidate in ["app/build.gradle.kts", "app/build.gradle"]:
        if os.path.exists(candidate):
            with open(candidate, "r", encoding="utf-8") as f:
                gradle = f.read()
            match = re.search(r"(versionCode\s*=?\s*)(\d+)", gradle)
            if match:
                old_vc = int(match.group(2))
                new_vc = old_vc + 1
                gradle = gradle[: match.start(2)] + str(new_vc) + gradle[match.end(2) :]
                with open(candidate, "w", encoding="utf-8") as f:
                    f.write(gradle)
                print(f"OK: {candidate} versionCode päivitetty: {old_vc} -> {new_vc}")
            return


if __name__ == "__main__":
    patch_manifest(find_file("AndroidManifest.xml"))
    patch_settings_dialog_helper(find_file("SettingsDialogHelper.kt"))
    patch_calendar_sync_helper(find_file("CalendarSyncHelper.kt"))
    bump_version_code()
    print("\nValmis!")
