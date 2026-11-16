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
def patch_splash_login():
    main_path = "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt"
    if not os.path.exists(main_path):
        print(f"Ohitetaan: {main_path} ei löytynyt.")
        return

    with open(main_path, "r", encoding="utf-8") as f:
        content = f.read()

    old_block = """            startSnapshotTransition {
                webView.loadUrl(url)
            }"""

    new_block = """            startSnapshotTransition {
                val existingCookies = CookieManager.getInstance().getCookie(baseUrl)
                if (existingCookies.isNullOrBlank()) {
                    scope.launch {
                        BackgroundAuthHelper.ensureAuthenticatedSession(this@MainActivity)
                        webView.loadUrl(url)
                    }
                } else {
                    webView.loadUrl(url)
                }
            }"""

    if old_block in content:
        updated = content.replace(old_block, new_block, 1)
        with open(main_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated)
        print(f"Päivitetty: {main_path}")
    else:
        print("Muutosta ei tehty (lohkoa ei löytynyt tai se on jo päivitetty).")
# ==============================================================================
# === POISTETTAVA KORJAUSOSIO PÄÄTTYY ===
# ==============================================================================


if __name__ == "__main__":
    bump_version_code()
    patch_splash_login()
