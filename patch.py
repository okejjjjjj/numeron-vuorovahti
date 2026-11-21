import os
import re


def find_file(filename):
    for root, _, files in os.walk("."):
        if filename in files:
            return os.path.join(root, filename)
    return None


def patch_manifest(path):
    if not path or not os.path.exists(path):
        print("HUOM: AndroidManifest.xml ei löytynyt.")
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    updated = re.sub(
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

    # 1. Poista canScheduleExactAlarmsCompat()
    updated, _ = re.subn(
        r"\n[ \t]*fun canScheduleExactAlarmsCompat\(\): Boolean \{.*?\n[ \t]*\}",
        "",
        updated,
        flags=re.DOTALL,
    )

    # 2. Poista openExactAlarmSettings()
    updated, _ = re.subn(
        r"\n[ \t]*fun openExactAlarmSettings\(\) \{.*?\n[ \t]*\}",
        "",
        updated,
        flags=re.DOTALL,
    )

    # 3. Poista 'Tarkat vuorohälytykset' -statusrivi ja sen klikkikuuntelija
    updated, _ = re.subn(
        r"\n[ \t]*val exactAlarmAllowed = canScheduleExactAlarmsCompat\(\).*?\n[ \t]*\}\n",
        "\n",
        updated,
        flags=re.DOTALL,
    )

    # 4. Poista duplikaatti exactAlarmNoticeBox reminderDetailsContainerista
    updated, _ = re.subn(
        r"\n[ \t]*val exactAlarmNoticeBox = LinearLayout\(context\)\.apply \{.*?\n[ \t]*reminderDetailsContainer\.addView\(exactAlarmNoticeBox\)",
        "",
        updated,
        flags=re.DOTALL,
    )

    # 5. Poista tarkkojen hälytysten tilapäivitys refreshSystemPermissionStates-funktiosta
    updated, _ = re.sub(
        r"\n[ \t]*var lastKnownExactAlarmAllowed = canScheduleExactAlarmsCompat\(\)",
        "",
        updated,
    )
    updated, _ = re.sub(
        r"\n[ \t]*val nowExactAllowed = canScheduleExactAlarmsCompat\(\)\n[ \t]*if \(android\.os\.Build\.VERSION\.SDK_INT >= android\.os\.Build\.VERSION_CODES\.S\) \{.*?\n[ \t]*\} else \{.*?\n[ \t]*\}",
        "",
        updated,
        flags=re.DOTALL,
    )
    updated, _ = re.sub(
        r"\n[ \t]*if \(!lastKnownExactAlarmAllowed && nowExactAllowed\) \{.*?\n[ \t]*\}\n[ \t]*lastKnownExactAlarmAllowed = nowExactAllowed",
        "",
        updated,
        flags=re.DOTALL,
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
        updated = re.sub(
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
