import os
import re


def find_file(filename):
    for root, _, files in os.walk("."):
        if filename in files:
            return os.path.join(root, filename)
    return None


def fix_settings_dialog_helper(path):
    if not path or not os.path.exists(path):
        print("VIRHE: SettingsDialogHelper.kt ei löytynyt.")
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    broken_tail = (
        "        } catch (_: Exception) {\n"
        "        }\n"
        "        return fallbackSavedMs\n"
        "    }\n"
    )

    if broken_tail in content:
        updated = content.replace(broken_tail, "", 1)
    else:
        # Varmistetaan myös mahdollinen \r\n-rivinvaihto
        broken_tail_crlf = broken_tail.replace("\n", "\r\n")
        if broken_tail_crlf in content:
            updated = content.replace(broken_tail_crlf, "", 1)
        else:
            print("HUOM: Odottamatonta rikkinäistä häntää ei löytynyt sellaisenaan; tarkistetaan aaltosulut.")
            updated = content

    assert "fun showSettingsDialog(" in updated, "VIRHE: showSettingsDialog puuttuu SettingsDialogHelper.kt:stä!"
    assert updated.count("{") == updated.count("}"), (
        f"VIRHE: Aaltosulut eivät ole tasan ({{={updated.count('{')}, }}={updated.count('}')})"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)
    print(f"OK: {path} korjattu ja varmistettu ({{={updated.count('{')}, }}={updated.count('}')}).")


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
