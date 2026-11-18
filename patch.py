#!/usr/bin/env python3
import pathlib
import re
import sys


def read_normalized(path: pathlib.Path) -> tuple[str, str]:
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    return normalized, newline


def write_preserved(path: pathlib.Path, content: str, newline: str) -> None:
    if newline != "\n":
        content = content.replace("\n", newline)
    path.write_bytes(content.encode("utf-8"))


def find_target(rel_path: str, filename: str) -> pathlib.Path | None:
    direct = pathlib.Path(rel_path)
    if direct.exists():
        return direct
    local = pathlib.Path(filename)
    if local.exists():
        return local
    matches = sorted(pathlib.Path(".").rglob(filename))
    return matches[0] if matches else None


def find_gradle_with_version() -> pathlib.Path | None:
    priority_candidates = [
        pathlib.Path("app/build.gradle.kts"),
        pathlib.Path("app/build.gradle"),
        pathlib.Path("build.gradle.kts"),
        pathlib.Path("build.gradle"),
    ]
    for candidate in priority_candidates:
        if candidate.exists():
            text, _ = read_normalized(candidate)
            if "versionCode" in text:
                return candidate

    for pattern in ("**/build.gradle.kts", "**/build.gradle"):
        for candidate in sorted(pathlib.Path(".").glob(pattern)):
            text, _ = read_normalized(candidate)
            if "versionCode" in text:
                return candidate

    return None


def verify_kotlin_delimiters(path: pathlib.Path, content: str) -> None:
    if content.count("{") != content.count("}"):
        print(
            f"[VIRHE] Aaltosulkeiden määrä ei täsmää tiedostossa {path} ({content.count('{')} vs {content.count('}')}).",
            file=sys.stderr,
        )
        sys.exit(1)
    if content.count("(") != content.count(")"):
        print(
            f"[VIRHE] Kaarisulkeiden määrä ei täsmää tiedostossa {path} ({content.count('(')} vs {content.count(')')}).",
            file=sys.stderr,
        )
        sys.exit(1)


def patch_main_activity(path: pathlib.Path) -> bool:
    content, newline = read_normalized(path)

    old_block = """    private fun requestNeededPermissions() {
        val perms = mutableListOf(
            Manifest.permission.READ_CALENDAR,
            Manifest.permission.WRITE_CALENDAR
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            perms.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        val missing = perms.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 101)
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val alarmManager = getSystemService(Context.ALARM_SERVICE) as android.app.AlarmManager
            val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            if (!alarmManager.canScheduleExactAlarms() && !prefs.getBoolean("exact_alarm_prompted", false)) {
                prefs.edit().putBoolean("exact_alarm_prompted", true).apply()
                Toast.makeText(
                    this,
                    "Salli tarkat hälytykset, jotta vuoromuistutukset tulevat ajallaan",
                    Toast.LENGTH_LONG
                ).show()
                try {
                    startActivity(
                        Intent(
                            android.provider.Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                            android.net.Uri.parse("package:$packageName")
                        )
                    )
                } catch (_: Exception) {
                }
            }
        }
    }"""

    new_block = """    private fun requestNeededPermissions() {
        val perms = mutableListOf(
            Manifest.permission.READ_CALENDAR,
            Manifest.permission.WRITE_CALENDAR
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            perms.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        val missing = perms.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 101)
        }
    }"""

    if "ACTION_REQUEST_SCHEDULE_EXACT_ALARM" not in content:
        print(f"[INFO] Ensikäynnistyksen hälytyslupakehotus on jo poistettu: {path}")
        return False

    if old_block not in content:
        print(
            f"[VIRHE] requestNeededPermissions()-lohkoa ei löytynyt odotetussa muodossa: {path}",
            file=sys.stderr,
        )
        sys.exit(1)

    updated = content.replace(old_block, new_block, 1)
    verify_kotlin_delimiters(path, updated)
    write_preserved(path, updated, newline)
    print(f"[OK] Poistettu ensikäynnistyksen automaattinen hälytyslupakehotus: {path}")
    return True


def patch_settings_dialog_helper(path: pathlib.Path) -> bool:
    content, newline = read_normalized(path)

    if "fun openExactAlarmSettings()" in content or "exactAlarmNoticeBox" in content:
        print(f"[INFO] Tarkkojen hälytysten valinnainen asetuslinkitys on jo lisätty: {path}")
        return False

    replacements = [
        (
            """        fun addStatusRow(parent: LinearLayout, title: String, value: String, subValue: String? = null) {
            val box = LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                background = makeCardBg("#111923", "#233040", 8)
                setPadding(dp(12), dp(9), dp(12), dp(9))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    bottomMargin = dp(8)
                }
            }
            box.addView(TextView(context).apply {
                text = title
                textSize = 11f
                setTextColor(Color.parseColor("#94A3B8"))
            })
            box.addView(TextView(context).apply {
                text = value
                textSize = 14f
                setTypeface(null, Typeface.BOLD)
                setTextColor(Color.parseColor("#F1F5F9"))
                setPadding(0, dp(2), 0, 0)
            })
            if (!subValue.isNullOrEmpty()) {
                box.addView(TextView(context).apply {
                    text = subValue
                    textSize = 12f
                    setTextColor(Color.parseColor("#38BDF8"))
                    setPadding(0, dp(2), 0, 0)
                })
            }
            parent.addView(box)
        }""",
            """        fun canScheduleExactAlarmsCompat(): Boolean {
            return if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
                (context.getSystemService(Context.ALARM_SERVICE) as android.app.AlarmManager).canScheduleExactAlarms()
            } else {
                true
            }
        }

        fun openExactAlarmSettings() {
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
                try {
                    context.startActivity(
                        android.content.Intent(
                            android.provider.Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                            android.net.Uri.parse("package:${context.packageName}")
                        ).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                    )
                } catch (_: Exception) {
                }
            }
        }

        fun addStatusRow(parent: LinearLayout, title: String, value: String, subValue: String? = null): Pair<TextView, TextView> {
            val box = LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                background = makeCardBg("#111923", "#233040", 8)
                setPadding(dp(12), dp(9), dp(12), dp(9))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    bottomMargin = dp(8)
                }
            }
            box.addView(TextView(context).apply {
                text = title
                textSize = 11f
                setTextColor(Color.parseColor("#94A3B8"))
            })
            val valueTv = TextView(context).apply {
                text = value
                textSize = 14f
                setTypeface(null, Typeface.BOLD)
                setTextColor(Color.parseColor("#F1F5F9"))
                setPadding(0, dp(2), 0, 0)
            }
            box.addView(valueTv)
            val subTv = TextView(context).apply {
                text = subValue ?: ""
                textSize = 12f
                setTextColor(Color.parseColor("#38BDF8"))
                setPadding(0, dp(2), 0, 0)
                visibility = if (!subValue.isNullOrEmpty()) View.VISIBLE else View.GONE
            }
            box.addView(subTv)
            parent.addView(box)
            return Pair(valueTv, subTv)
        }""",
        ),
        (
            """        addStatusRow(
            statusCard,
            "Seuraava leimausnotifikaatio lähetetään",
            when {
                !initialShiftReminders -> "Leimausmuistutukset pois käytöstä"
                nextNotifMs > System.currentTimeMillis() -> formatTimestamp(nextNotifMs, "")
                else -> "Ei tulevia ajoitettuja hälytyksiä"
            },
            if (initialShiftReminders && nextNotifMs > System.currentTimeMillis()) nextNotifLabel else null
        )

        val exactAlarmAllowed = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            (context.getSystemService(Context.ALARM_SERVICE) as android.app.AlarmManager).canScheduleExactAlarms()
        } else {
            true
        }
        addStatusRow(
            statusCard,
            "Tarkat vuorohälytykset",
            if (exactAlarmAllowed) "Sallittu" else "Rajoitettu – napauta salliaksesi",
            if (exactAlarmAllowed) null else "Avaa järjestelmän hälytysasetukset"
        )
        if (!exactAlarmAllowed && android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            statusCard.getChildAt(statusCard.childCount - 1).setOnClickListener {
                try {
                    context.startActivity(
                        android.content.Intent(
                            android.provider.Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                            android.net.Uri.parse("package:${context.packageName}")
                        ).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                    )
                } catch (_: Exception) {
                }
            }
        }

        val powerManager = context.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        val ignoringBatteryOpt = powerManager.isIgnoringBatteryOptimizations(context.packageName)
        addStatusRow(
            statusCard,
            "Akun virransäästörajoitukset",
            if (ignoringBatteryOpt) "Ei rajoitettu (taustasynkronointi aktiivinen)" else "Optimoitu – napauta poistaaksesi rajoitus",
            if (ignoringBatteryOpt) null else "Varmistaa tausta-ajojen toiminnan lepotilassa"
        )""",
            """        val (nextNotifValueTv, nextNotifSubTv) = addStatusRow(
            statusCard,
            "Seuraava leimausnotifikaatio lähetetään",
            when {
                !initialShiftReminders -> "Leimausmuistutukset pois käytöstä"
                nextNotifMs > System.currentTimeMillis() -> formatTimestamp(nextNotifMs, "")
                else -> "Ei tulevia ajoitettuja hälytyksiä"
            },
            if (initialShiftReminders && nextNotifMs > System.currentTimeMillis()) nextNotifLabel else null
        )

        val exactAlarmAllowed = canScheduleExactAlarmsCompat()
        val (exactAlarmValueTv, exactAlarmSubTv) = addStatusRow(
            statusCard,
            "Tarkat vuorohälytykset",
            if (exactAlarmAllowed) "Sallittu – muistutukset hälyttävät minuutilleen" else "Valinnainen (rajoitettu) – napauta salliaksesi",
            if (exactAlarmAllowed) {
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) "Napauta avataksesi hälytysasetukset" else null
            } else {
                "Varmistaa minuutintarkat vuoromuistutukset"
            }
        )
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            statusCard.getChildAt(statusCard.childCount - 1).setOnClickListener {
                openExactAlarmSettings()
            }
        }

        val powerManager = context.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        val ignoringBatteryOpt = powerManager.isIgnoringBatteryOptimizations(context.packageName)
        val (batteryOptValueTv, batteryOptSubTv) = addStatusRow(
            statusCard,
            "Akun virransäästörajoitukset",
            if (ignoringBatteryOpt) "Ei rajoitettu (taustasynkronointi aktiivinen)" else "Optimoitu – napauta poistaaksesi rajoitus",
            if (ignoringBatteryOpt) null else "Varmistaa tausta-ajojen toiminnan lepotilassa"
        )""",
        ),
        (
            """        reminderDetailsContainer.addView(createLabel("Muistutus ennen vuoroa (min)"))
        val editReminder = EditText(context).apply {
            setText(prefs.getInt("reminder_minutes", 30).toString())
            inputType = InputType.TYPE_CLASS_NUMBER
            isSingleLine = true
            styleEditText(this)
        }
        reminderDetailsContainer.addView(editReminder)
        actionCard.addView(reminderDetailsContainer)""",
            """        reminderDetailsContainer.addView(createLabel("Muistutus ennen vuoroa (min)"))
        val editReminder = EditText(context).apply {
            setText(prefs.getInt("reminder_minutes", 30).toString())
            inputType = InputType.TYPE_CLASS_NUMBER
            isSingleLine = true
            styleEditText(this)
        }
        reminderDetailsContainer.addView(editReminder)

        val exactAlarmNoticeBox = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            background = makeCardBg("#111923", "#2A394A", 8)
            setPadding(dp(12), dp(10), dp(12), dp(10))
            visibility = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S && !canScheduleExactAlarmsCompat()) {
                View.VISIBLE
            } else {
                View.GONE
            }
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                topMargin = dp(10)
            }
            setOnClickListener {
                openExactAlarmSettings()
            }
        }
        exactAlarmNoticeBox.addView(TextView(context).apply {
            text = "Tarkat vuorohälytykset (valinnainen)"
            textSize = 13f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#F1F5F9"))
        })
        exactAlarmNoticeBox.addView(TextView(context).apply {
            text = "Muistutukset toimivat ilmankin, mutta sallimalla tarkat hälytykset ne tulevat minuutilleen. Napauta avataksesi asetukset →"
            textSize = 12f
            setTextColor(Color.parseColor("#38BDF8"))
            setPadding(0, dp(3), 0, 0)
        })
        reminderDetailsContainer.addView(exactAlarmNoticeBox)

        actionCard.addView(reminderDetailsContainer)""",
        ),
        (
            """        dialog.setOnDismissListener { billingHelper.destroy() }
        dialog.show()""",
            """        var lastKnownExactAlarmAllowed = canScheduleExactAlarmsCompat()

        fun refreshSystemPermissionStates() {
            val nowExactAllowed = canScheduleExactAlarmsCompat()
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
                if (nowExactAllowed) {
                    exactAlarmValueTv.text = "Sallittu – muistutukset hälyttävät minuutilleen"
                    exactAlarmValueTv.setTextColor(Color.parseColor("#34D399"))
                    exactAlarmSubTv.text = "Napauta avataksesi hälytysasetukset"
                    exactAlarmSubTv.visibility = View.VISIBLE
                    exactAlarmNoticeBox.visibility = View.GONE
                } else {
                    exactAlarmValueTv.text = "Valinnainen (rajoitettu) – napauta salliaksesi"
                    exactAlarmValueTv.setTextColor(Color.parseColor("#F1F5F9"))
                    exactAlarmSubTv.text = "Varmistaa minuutintarkat vuoromuistutukset"
                    exactAlarmSubTv.visibility = View.VISIBLE
                    exactAlarmNoticeBox.visibility = View.VISIBLE
                }
            } else {
                exactAlarmValueTv.text = "Sallittu"
                exactAlarmValueTv.setTextColor(Color.parseColor("#34D399"))
                exactAlarmSubTv.visibility = View.GONE
                exactAlarmNoticeBox.visibility = View.GONE
            }

            val nowIgnoringBattery = powerManager.isIgnoringBatteryOptimizations(context.packageName)
            if (nowIgnoringBattery) {
                batteryOptValueTv.text = "Ei rajoitettu (taustasynkronointi aktiivinen)"
                batteryOptValueTv.setTextColor(Color.parseColor("#34D399"))
                batteryOptSubTv.visibility = View.GONE
            } else {
                batteryOptValueTv.text = "Optimoitu – napauta poistaaksesi rajoitus"
                batteryOptValueTv.setTextColor(Color.parseColor("#F1F5F9"))
                batteryOptSubTv.text = "Varmistaa tausta-ajojen toiminnan lepotilassa"
                batteryOptSubTv.visibility = View.VISIBLE
            }

            if (!lastKnownExactAlarmAllowed && nowExactAllowed) {
                CalendarSyncHelper.scheduleShiftReminders(context)
                val updatedNextMs = prefs.getLong("next_reminder_ms", 0L)
                val updatedNextLabel = prefs.getString("next_reminder_label", "") ?: ""
                val remindersOn = switchShiftReminders.isChecked
                nextNotifValueTv.text = when {
                    !remindersOn -> "Leimausmuistutukset pois käytöstä"
                    updatedNextMs > System.currentTimeMillis() -> formatTimestamp(updatedNextMs, "")
                    else -> "Ei tulevia ajoitettuja hälytyksiä"
                }
                if (remindersOn && updatedNextMs > System.currentTimeMillis() && updatedNextLabel.isNotEmpty()) {
                    nextNotifSubTv.text = updatedNextLabel
                    nextNotifSubTv.visibility = View.VISIBLE
                } else {
                    nextNotifSubTv.visibility = View.GONE
                }
            }
            lastKnownExactAlarmAllowed = nowExactAllowed
        }

        refreshSystemPermissionStates()

        rootContainer.viewTreeObserver.addOnWindowFocusChangeListener { hasFocus ->
            if (hasFocus) {
                refreshSystemPermissionStates()
            }
        }

        dialog.setOnDismissListener { billingHelper.destroy() }
        dialog.show()""",
        ),
    ]

    updated = content
    for idx, (old, new) in enumerate(replacements, start=1):
        if old not in updated:
            print(
                f"[VIRHE] Ankkurikohtaa #{idx} ei löytynyt tiedostosta {path}. Muutoksia ei tallennettu.",
                file=sys.stderr,
            )
            sys.exit(1)
        updated = updated.replace(old, new, 1)

    verify_kotlin_delimiters(path, updated)
    write_preserved(path, updated, newline)
    print(f"[OK] Päivitetty tarkkojen hälytysten asetukset ja automaattinen tilapäivitys: {path}")
    return True


def bump_version(path: pathlib.Path) -> bool:
    content, newline = read_normalized(path)

    code_pattern = re.compile(r"^([ \t]*versionCode\s*(?:=\s*|\s+))(\d+)([ \t]*(?://.*)?)$", re.MULTILINE)
    code_match = code_pattern.search(content)
    if not code_match:
        print(f"[VIRHE] versionCode-määritystä ei löytynyt tiedostosta: {path}", file=sys.stderr)
        sys.exit(1)

    old_code = int(code_match.group(2))
    new_code = old_code + 1
    updated = code_pattern.sub(
        lambda m: f"{m.group(1)}{new_code}{m.group(3)}",
        content,
        count=1,
    )

    name_pattern = re.compile(
        r'^([ \t]*versionName\s*(?:=\s*|\s+))(["\'])([^"\']+)(["\'])([ \t]*(?://.*)?)$',
        re.MULTILINE,
    )
    name_match = name_pattern.search(updated)
    version_name_info = ""
    if name_match:
        old_name = name_match.group(3)
        parts_match = re.match(r"^(.*?)(\d+)([^\d]*)$", old_name)
        if parts_match:
            new_name = f"{parts_match.group(1)}{int(parts_match.group(2)) + 1}{parts_match.group(3)}"
            updated = name_pattern.sub(
                lambda m: f"{m.group(1)}{m.group(2)}{new_name}{m.group(4)}{m.group(5)}",
                updated,
                count=1,
            )
            version_name_info = f', versionName "{old_name}" -> "{new_name}"'
        else:
            version_name_info = f' (versionName "{old_name}" jätettiin ennalleen)'

    write_preserved(path, updated, newline)
    print(f"[OK] Nostettu sovellusversio ({path}): versionCode {old_code} -> {new_code}{version_name_info}")
    return True


def main() -> None:
    main_path = find_target(
        "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt",
        "MainActivity.kt",
    )
    settings_path = find_target(
        "app/src/main/java/fi/numeron/vuorovahti/SettingsDialogHelper.kt",
        "SettingsDialogHelper.kt",
    )
    gradle_path = find_gradle_with_version()

    if not main_path and not settings_path and not gradle_path:
        print(
            "Virhe: Projektitiedostoja (MainActivity.kt, SettingsDialogHelper.kt tai build.gradle(.kts)) ei löytynyt.",
            file=sys.stderr,
        )
        sys.exit(1)

    if main_path:
        patch_main_activity(main_path)
    else:
        print("[VAROITUS] MainActivity.kt-tiedostoa ei löytynyt.")

    if settings_path:
        patch_settings_dialog_helper(settings_path)
    else:
        print("[VAROITUS] SettingsDialogHelper.kt-tiedostoa ei löytynyt.")

    if gradle_path:
        bump_version(gradle_path)
    else:
        print("[VAROITUS] build.gradle(.kts)-tiedostoa versionumerolla ei löytynyt.")


if __name__ == "__main__":
    main()
