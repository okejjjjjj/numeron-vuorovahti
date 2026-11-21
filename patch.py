import os
import re


def find_file(filename):
    for root, _, files in os.walk("."):
        if filename in files:
            return os.path.join(root, filename)
    return None


def remove_function_by_braces(content, func_signature_prefix):
    idx = content.find(func_signature_prefix)
    if idx == -1:
        return content, False

    # Etsitään funktion aloittava '{'
    open_brace_idx = content.find("{", idx)
    if open_brace_idx == -1:
        return content, False

    depth = 0
    in_string = False
    escape = False
    end_idx = -1

    for i in range(open_brace_idx, len(content)):
        ch = content[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_idx = i
                break

    if end_idx == -1:
        return content, False

    # Laajennetaan poisto rivin alkuun ja rivinvaihdon loppuun
    start_line = content.rfind("\n", 0, idx)
    if start_line == -1:
        start_line = 0
    end_line = content.find("\n", end_idx)
    if end_line == -1:
        end_line = len(content)
    else:
        end_line += 1

    new_content = content[:start_line] + "\n" + content[end_line:]
    return new_content, True


def fix_settings_dialog_helper(path):
    if not path or not os.path.exists(path):
        print("HUOM: SettingsDialogHelper.kt ei löytynyt.")
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    updated, removed = remove_function_by_braces(content, "private fun resolveNextSyncMs(")

    # Jos tiedosto on rikki aiemmasta osittaisesta poistosta, tarkistetaan onko 'showSettingsDialog' vielä olemassa
    if not removed and "fun showSettingsDialog(" not in content:
        print("VAROITUS: SettingsDialogHelper.kt näyttää pahasti vaurioituneelta — palauta se gitistä (git checkout -- SettingsDialogHelper.kt) ja aja skripti uudelleen.")
        return

    if updated != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(updated)
        print(f"OK: {path} korjattu (resolveNextSyncMs poistettu siististi).")
    else:
        print(f"OK: {path} ei vaatinut muutoksia.")


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
    fix_settings_dialog_helper(find_file("SettingsDialogHelper.kt"))
    bump_version_code()
    print("\nValmis!")
