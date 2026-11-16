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
def patch_receiver_prelogin():
    receiver_path = "app/src/main/java/fi/numeron/vuorovahti/ShiftReminderReceiver.kt"
    if not os.path.exists(receiver_path):
        print(f"Ohitetaan: {receiver_path} ei löytynyt.")
        return

    with open(receiver_path, "r", encoding="utf-8") as f:
        content = f.read()

    orig_content = content

    # 1. Lisää puuttuva launch-import
    old_import = "import kotlinx.coroutines.Dispatchers"
    new_import = "import kotlinx.coroutines.CoroutineScope\nimport kotlinx.coroutines.Dispatchers\nimport kotlinx.coroutines.launch"
    if "import kotlinx.coroutines.launch" not in content and old_import in content:
        content = content.replace(old_import, new_import, 1)

    # 2. Lisää taustakirjautuminen vuoroilmoituksen yhteyteen
    old_block = """        // 4. Ajastettu tai testattu työvuorohälytys laukesi
        val title = intent.getStringExtra("SHIFT_TITLE") ?: "Työvuoro"
        val timeStr = intent.getStringExtra("SHIFT_TIME") ?: ""
        val isEnding = intent.getBooleanExtra("IS_ENDING", false)

        showReminderNotification(context, title, timeStr, isEnding)"""

    new_block = """        // 4. Ajastettu tai testattu työvuorohälytys laukesi
        val title = intent.getStringExtra("SHIFT_TITLE") ?: "Työvuoro"
        val timeStr = intent.getStringExtra("SHIFT_TIME") ?: ""
        val isEnding = intent.getBooleanExtra("IS_ENDING", false)

        showReminderNotification(context, title, timeStr, isEnding)

        val appCtx = context.applicationContext
        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                BackgroundAuthHelper.ensureAuthenticatedSession(appCtx)
            } finally {
                pendingResult.finish()
            }
        }"""

    if old_block in content:
        content = content.replace(old_block, new_block, 1)

    if content != orig_content:
        with open(receiver_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        print(f"Päivitetty: {receiver_path}")
    else:
        print("Muutosta ei tehty (lohkoa ei löytynyt tai se on jo päivitetty).")
# ==============================================================================
# === POISTETTAVA KORJAUSOSIO PÄÄTTYY ===
# ==============================================================================


if __name__ == "__main__":
    bump_version_code()
    patch_receiver_prelogin()
