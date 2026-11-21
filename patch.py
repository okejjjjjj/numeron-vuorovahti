import os
import re


def find_file(filename):
    for root, _, files in os.walk("."):
        if filename in files:
            return os.path.join(root, filename)
    return None


def patch_background_auth_helper(path):
    if not path or not os.path.exists(path):
        print("HUOM: BackgroundAuthHelper.kt ei löytynyt, ohitetaan.")
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    updated = content

    if "stopAfterRedirect = true" in updated:
        updated = updated.replace("stopAfterRedirect = true", "stopAfterRedirect = false", 1)

    if "cookieSyncLock" not in updated:
        obj_match = re.search(r"(object\s+BackgroundAuthHelper\s*\{)", updated)
        if obj_match:
            updated = updated.replace(
                obj_match.group(1),
                f"{obj_match.group(1)}\n    private val cookieSyncLock = Any()",
                1,
            )

        persist_pattern = re.compile(
            r"(private\s+fun\s+persistUpdatedCookies\([^\)]*\)\s*\{)(.*?)(\n    \})",
            re.DOTALL,
        )
        if persist_pattern.search(updated):
            updated = persist_pattern.sub(
                r"\1\n        synchronized(cookieSyncLock) {\2\n        }\3",
                updated,
                count=1,
            )
        else:
            updated = re.sub(
                r"(CookieManager\.getInstance\(\)\.setCookie\([^\n]+\))",
                r"synchronized(cookieSyncLock) { \1; CookieManager.getInstance().flush() }",
                updated,
            )

    if updated != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(updated)
        print(f"OK: {path} päivitetty.")
    else:
        print(f"OK: {path} ei vaatinut muutoksia.")


def patch_settings_dialog_helper(path):
    if not path or not os.path.exists(path):
        print("HUOM: SettingsDialogHelper.kt ei löytynyt, ohitetaan.")
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        r"\n\s*private fun resolveNextSyncMs\([^\)]*\):\s*Long\s*\{.*?\n\s*\}\n",
        re.DOTALL,
    )
    new_content, count = pattern.subn("\n", content, count=1)

    if count > 0:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"OK: {path} — poistettu käyttämätön resolveNextSyncMs (.get()).")
    else:
        print(f"OK: {path} — resolveNextSyncMs ei tarvinnut muutoksia.")


def patch_calendar_sync_helper(path):
    if not path or not os.path.exists(path):
        print("HUOM: CalendarSyncHelper.kt ei löytynyt, ohitetaan.")
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    old_cached_line = "val shiftRoleInfo = shift.description.lineSequence().firstOrNull()?.trim().orEmpty()"
    new_cached_line = (
        "val shiftRoleInfo = shift.description.substringBefore(EVENT_DESCRIPTION_TAG)"
        ".lineSequence().firstOrNull()?.trim().orEmpty()"
    )

    if old_cached_line in content:
        updated = content.replace(old_cached_line, new_cached_line, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(updated)
        print(f"OK: {path} — cachedShifts-kuvaus siistitty.")
    else:
        print(f"OK: {path} — ei muutettavaa cachedShifts-rivissä.")


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
    patch_background_auth_helper(find_file("BackgroundAuthHelper.kt"))
    patch_settings_dialog_helper(find_file("SettingsDialogHelper.kt"))
    patch_calendar_sync_helper(find_file("CalendarSyncHelper.kt"))
    bump_version_code()
    print("\nValmis!")
