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
# === POISTETTAVA KORJAUSOSIO ALKAA (Poista kun muutos on ajettu) ===
# ==============================================================================
def fix_notification_stamp_button():
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

    # 2. MainActivity.kt: sulje ilmoitus, varmista ohjaus leimaussivulle ja odota painiketta
    main_path = "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt"
    if os.path.exists(main_path):
        with open(main_path, "r", encoding="utf-8") as f:
            main = f.read()

        orig_main = main

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

        old_when_end = """                    url.contains("/Calendar", ignoreCase = true) -> {
                        setActiveTab(btnNavShifts)
                        handleCalendarPage()
                    }
                }"""

        new_when_end = """                    url.contains("/Calendar", ignoreCase = true) -> {
                        setActiveTab(btnNavShifts)
                        handleCalendarPage()
                    }
                    pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> {
                        webView.loadUrl("${getBaseUrl()}/WorktimeStamping")
                    }
                }"""

        if old_when_end in main and "pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT ->" not in main:
            main = main.replace(old_when_end, new_when_end, 1)

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
                if (!btn) return 'NO_BUTTON';
                var btnText = (btn.innerText || btn.textContent || '').trim();
                if (!btnText) return 'NO_BUTTON';
                if (btnText.toLowerCase().indexOf('$targetLower') !== -1) {
                    btn.click();
                    return 'STAMPED_' + btnText;
                } else {
                    return 'WRONG_DIRECTION_' + btnText;
                }
            })();
        \"\"\".trimIndent()

        webView.evaluateJavascript(js) { result ->
            val cleanResult = (result ?: "").replace("\\"", "")
            when {
                cleanResult.startsWith("STAMPED_") -> {
                    pendingAction = Action.NONE
                    Toast.makeText(this, "Leimaus suoritettu ($targetText)", Toast.LENGTH_SHORT).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                }
                cleanResult.startsWith("WRONG_DIRECTION_") -> {
                    pendingAction = Action.NONE
                    Toast.makeText(this, "Olet jo leimannut tilaan: $targetText", Toast.LENGTH_LONG).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)
                }
                cleanResult == "NO_BUTTON" && attempt < 10 -> {
                    webView.postDelayed({ handleStampingPage(attempt + 1) }, 300L)
                }
                else -> {
                    pendingAction = Action.NONE
                }
            }
        }
    }"""

        if old_stamp_fn in main:
            main = main.replace(old_stamp_fn, new_stamp_fn, 1)

        if main != orig_main:
            with open(main_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(main)
            print(f"Päivitetty: {main_path}")
# ==============================================================================
# === POISTETTAVA KORJAUSOSIO PÄÄTTYY ===
# ==============================================================================


if __name__ == "__main__":
    bump_version_code()
    fix_notification_stamp_button()
