#!/usr/bin/env python3
import os
import re


# ==============================================================================
# PYSYVÄ OSIO: Versionumeron automaattinen nosto (+1)
# ==============================================================================
def bump_version_code():
    gradle_path = "app/build.gradle.kts"
    if not os.path.exists(gradle_path):
        print(f"Ohitetaan: {gradle_path} ei löytynyt.")
        return

    with open(gradle_path, "r", encoding="utf-8") as f:
        content = f.read()

    def increment(match):
        old_code = int(match.group(1))
        new_code = old_code + 1
        print(f"Päivitetään versionCode: {old_code} -> {new_code}")
        return f"versionCode = {new_code}"

    updated, count = re.subn(r"versionCode\s*=\s*(\d+)", increment, content, count=1)
    if count > 0:
        with open(gradle_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated)


# ==============================================================================
# === POISTETTAVA KORJAUSOSIO ALKAA (Poista kun muutokset on ajettu) ===
# ==============================================================================
def apply_reliability_fixes():
    # 1. ShiftReminderReceiver.kt: avaa MainActivity suoraan PendingIntent.getActivity-kutsulla
    receiver_path = "app/src/main/java/fi/numeron/vuorovahti/ShiftReminderReceiver.kt"
    if os.path.exists(receiver_path):
        with open(receiver_path, "r", encoding="utf-8") as f:
            rec = f.read()

        old_pi = """        val stampIntent = Intent(context, ShiftReminderReceiver::class.java).apply {
            action = ACTION_QUICK_STAMP
            putExtra("IS_ENDING", isEnding)
            putExtra("IS_TEST", isTest)
            putExtra("NOTIF_ID", notifId)
        }
        val stampPi = PendingIntent.getBroadcast(
            context,
            notifId,
            stampIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )"""

        new_pi = """        val stampIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("AUTO_STAMP", true)
            putExtra("IS_ENDING", isEnding)
            putExtra("IS_TEST", isTest)
            putExtra("NOTIF_ID", notifId)
        }
        val stampPi = PendingIntent.getActivity(
            context,
            notifId,
            stampIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )"""

        if old_pi in rec:
            rec = rec.replace(old_pi, new_pi, 1)
            with open(receiver_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(rec)
            print(f"Päivitetty: {receiver_path}")

    # 2. MainActivity.kt: leimauksen vahvistus, istunnon aikaleima, ilmoituksen poisto ja hälytyslupa
    main_path = "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt"
    if os.path.exists(main_path):
        with open(main_path, "r", encoding="utf-8") as f:
            main = f.read()

        orig_main = main

        # 2a. Ilmoituksen poisto avattaessa
        old_intent_fn = """    private fun handleIncomingIntent(intent: Intent?) {
        if (intent?.getBooleanExtra("AUTO_STAMP", false) == true) {
            val isEnding = intent.getBooleanExtra("IS_ENDING", false)
            val isTest = intent.getBooleanExtra("IS_TEST", false)
            intent.removeExtra("AUTO_STAMP")
            intent.removeExtra("IS_TEST")"""

        new_intent_fn = """    private fun handleIncomingIntent(intent: Intent?) {
        val notifId = intent?.getIntExtra("NOTIF_ID", -1) ?: -1
        if (notifId > 0) {
            intent?.removeExtra("NOTIF_ID")
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
            nm.cancel(notifId)
        }

        if (intent?.getBooleanExtra("AUTO_STAMP", false) == true) {
            val isEnding = intent.getBooleanExtra("IS_ENDING", false)
            val isTest = intent.getBooleanExtra("IS_TEST", false)
            intent.removeExtra("AUTO_STAMP")
            intent.removeExtra("IS_TEST")"""

        if old_intent_fn in main and 'getIntExtra("NOTIF_ID"' not in main:
            main = main.replace(old_intent_fn, new_intent_fn, 1)

        # 2b. Tarkkojen hälytysten luvan tarkistus (Android 12+)
        old_perms_fn = """        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 101)
        }
    }"""

        new_perms_fn = """        if (missing.isNotEmpty()) {
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

        if old_perms_fn in main and "canScheduleExactAlarms" not in main:
            main = main.replace(old_perms_fn, new_perms_fn, 1)

        # 2c. Päivitä last_valid_session_ms onPageFinished-metodissa + paluu leimaussivulle
        old_page_finished = """                injectDarkTheme(view)
                CookieManager.getInstance().flush()

                when {
                    url.contains("/Login/Login", ignoreCase = true) -> {
                        startSnapshotTransition()
                        handleAutoLogin()
                    }
                    url.contains("/WorktimeStamping", ignoreCase = true) -> {
                        setActiveTab(btnNavStamp)
                        handleStampingPage()
                    }
                    url.contains("/PersonRequests", ignoreCase = true) -> {
                        setActiveTab(btnNavRequests)
                    }
                    url.contains("/Calendar", ignoreCase = true) -> {
                        setActiveTab(btnNavShifts)
                        handleCalendarPage()
                    }
                }"""

        new_page_finished = """                injectDarkTheme(view)
                CookieManager.getInstance().flush()
                if (!url.contains("/Login/", ignoreCase = true)) {
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                }

                when {
                    url.contains("/Login/Login", ignoreCase = true) -> {
                        startSnapshotTransition()
                        handleAutoLogin()
                    }
                    url.contains("/WorktimeStamping", ignoreCase = true) -> {
                        setActiveTab(btnNavStamp)
                        handleStampingPage()
                    }
                    url.contains("/PersonRequests", ignoreCase = true) -> {
                        setActiveTab(btnNavRequests)
                    }
                    url.contains("/Calendar", ignoreCase = true) -> {
                        setActiveTab(btnNavShifts)
                        handleCalendarPage()
                    }
                    pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> {
                        webView.loadUrl("${getBaseUrl()}/WorktimeStamping")
                    }
                }"""

        if old_page_finished in main:
            main = main.replace(old_page_finished, new_page_finished, 1)

        # 2d. Leimauksen DOM-vahvistus ennen sovelluksen sulkemista
        old_stamp_fn = """    private fun handleStampingPage() {
        if (pendingAction != Action.STAMP_IN && pendingAction != Action.STAMP_OUT) return

        val targetText = if (pendingAction == Action.STAMP_IN) "Sisään" else "Ulos"
        pendingAction = Action.NONE

        val js = \"\"\"
            (function() {
                var btn = document.getElementById('punchButton');
                if (!btn) return 'NO_BUTTON';
                var btnText = btn.innerText.trim();
                if (btnText.indexOf('$targetText') !== -1) {
                    btn.click();
                    return 'STAMPED_' + btnText;
                } else {
                    return 'WRONG_DIRECTION_' + btnText;
                }
            })();
        \"\"\".trimIndent()

        webView.evaluateJavascript(js) { result ->
            val cleanResult = result.replace("\\"", "")
            when {
                cleanResult.startsWith("STAMPED_") -> {
                    Toast.makeText(this, "Leimaus suoritettu ($targetText)", Toast.LENGTH_SHORT).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                }
                cleanResult.startsWith("WRONG_DIRECTION_") -> {
                    Toast.makeText(this, "Olet jo leimannut tilaan: $targetText", Toast.LENGTH_LONG).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                }
            }
        }
    }"""

        new_stamp_fn = """    private fun handleStampingPage(attempt: Int = 0) {
        if (pendingAction != Action.STAMP_IN && pendingAction != Action.STAMP_OUT) return

        val targetText = if (pendingAction == Action.STAMP_IN) "Sisään" else "Ulos"
        val targetLower = targetText.lowercase()

        val js = \"\"\"
            (function() {
                var btn = document.getElementById('punchButton');
                if (!btn) return JSON.stringify({ status: 'NO_BUTTON' });
                var btnText = (btn.innerText || btn.textContent || '').trim();
                if (!btnText) return JSON.stringify({ status: 'NO_BUTTON' });
                var firstRow = '';
                var rowEl = document.querySelector('#table-latest-stamps tbody tr, #table-latest-stamps tr');
                if (rowEl) {
                    firstRow = (rowEl.innerText || rowEl.textContent || '').replace(/\\s+/g, ' ').trim();
                }
                if (btnText.toLowerCase().indexOf('$targetLower') !== -1) {
                    btn.click();
                    return JSON.stringify({ status: 'CLICKED', btn: btnText, row: firstRow });
                } else {
                    return JSON.stringify({ status: 'WRONG_DIRECTION', btn: btnText, row: firstRow });
                }
            })();
        \"\"\".trimIndent()

        webView.evaluateJavascript(js) { rawResult ->
            val unescaped = try {
                if (rawResult != null && rawResult != "null") JSONTokener(rawResult).nextValue() as? String else null
            } catch (_: Exception) {
                null
            }
            val obj = try {
                if (unescaped != null) org.json.JSONObject(unescaped) else null
            } catch (_: Exception) {
                null
            }
            val status = obj?.optString("status", "") ?: ""

            when {
                status == "CLICKED" -> {
                    pendingAction = Action.NONE
                    val beforeBtn = obj?.optString("btn", "") ?: ""
                    val beforeRow = obj?.optString("row", "") ?: ""
                    Toast.makeText(this, "Leimataan ($targetText)...", Toast.LENGTH_SHORT).show()
                    verifyStampAndClose(targetText, beforeBtn, beforeRow, 0)
                }
                status == "WRONG_DIRECTION" -> {
                    pendingAction = Action.NONE
                    Toast.makeText(this, "Olet jo leimannut tilaan: $targetText", Toast.LENGTH_LONG).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                }
                status == "NO_BUTTON" && attempt < 10 -> {
                    webView.postDelayed({ handleStampingPage(attempt + 1) }, 300L)
                }
                else -> {
                    pendingAction = Action.NONE
                }
            }
        }
    }

    private fun verifyStampAndClose(
        targetText: String,
        beforeBtn: String,
        beforeRow: String,
        checkAttempt: Int
    ) {
        val targetLower = targetText.lowercase()
        val verifyJs = \"\"\"
            (function() {
                var btn = document.getElementById('punchButton');
                var btnText = btn ? (btn.innerText || btn.textContent || '').trim() : '';
                var rowEl = document.querySelector('#table-latest-stamps tbody tr, #table-latest-stamps tr');
                var firstRow = rowEl ? (rowEl.innerText || rowEl.textContent || '').replace(/\\s+/g, ' ').trim() : '';
                return JSON.stringify({ btn: btnText, row: firstRow });
            })();
        \"\"\".trimIndent()

        webView.postDelayed({
            if (isFinishing || isDestroyed) return@postDelayed
            webView.evaluateJavascript(verifyJs) { rawResult ->
                val unescaped = try {
                    if (rawResult != null && rawResult != "null") JSONTokener(rawResult).nextValue() as? String else null
                } catch (_: Exception) {
                    null
                }
                val obj = try {
                    if (unescaped != null) org.json.JSONObject(unescaped) else null
                } catch (_: Exception) {
                    null
                }
                val nowBtn = obj?.optString("btn", "") ?: ""
                val nowRow = obj?.optString("row", "") ?: ""

                val buttonFlipped = nowBtn.isNotEmpty() && nowBtn != beforeBtn &&
                    nowBtn.lowercase().indexOf(targetLower) == -1
                val rowUpdated = nowRow.isNotEmpty() && nowRow != beforeRow

                if (buttonFlipped || rowUpdated) {
                    CookieManager.getInstance().flush()
                    Toast.makeText(this, "Leimaus vahvistettu ($targetText)", Toast.LENGTH_SHORT).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 600L)
                } else if (checkAttempt < 25) {
                    verifyStampAndClose(targetText, beforeBtn, beforeRow, checkAttempt + 1)
                } else {
                    Toast.makeText(
                        this,
                        "Leimausta ei voitu vahvistaa automaattisesti – tarkista tila ruudulta",
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        }, 300L)
    }"""

        if old_stamp_fn in main:
            main = main.replace(old_stamp_fn, new_stamp_fn, 1)

        if main != orig_main:
            with open(main_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(main)
            print(f"Päivitetty: {main_path}")

    # 3. SettingsDialogHelper.kt: tarkat hälytykset ja akun virransäästön tila + pikapainikkeet
    settings_path = "app/src/main/java/fi/numeron/vuorovahti/SettingsDialogHelper.kt"
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            set_content = f.read()

        old_status_end = """        addStatusRow(
            statusCard,
            "Seuraava leimausnotifikaatio lähetetään",
            if (nextNotifMs > System.currentTimeMillis()) formatTimestamp(nextNotifMs, "") else "Ei tulevia ajoitettuja hälytyksiä",
            if (nextNotifMs > System.currentTimeMillis()) nextNotifLabel else null
        )"""

        new_status_end = """        addStatusRow(
            statusCard,
            "Seuraava leimausnotifikaatio lähetetään",
            if (nextNotifMs > System.currentTimeMillis()) formatTimestamp(nextNotifMs, "") else "Ei tulevia ajoitettuja hälytyksiä",
            if (nextNotifMs > System.currentTimeMillis()) nextNotifLabel else null
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

        if old_status_end in set_content and "Tarkat vuorohälytykset" not in set_content:
            set_content = set_content.replace(old_status_end, new_status_end, 1)
            with open(settings_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(set_content)
            print(f"Päivitetty: {settings_path}")
# ==============================================================================
# === POISTETTAVA KORJAUSOSIO PÄÄTTYY ===
# ==============================================================================


if __name__ == "__main__":
    bump_version_code()
    apply_reliability_fixes()
