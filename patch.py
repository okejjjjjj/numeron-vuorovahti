#!/usr/bin/env python3
import pathlib
import sys
import re

def main():
    main_act_path = pathlib.Path("app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt")
    if not main_act_path.exists():
        alt = pathlib.Path("MainActivity.kt")
        if alt.exists():
            main_act_path = alt
        else:
            print(f"Virhe: Tiedostoa {main_act_path} ei löytynyt.", file=sys.stderr)
            sys.exit(1)

    content = main_act_path.read_text(encoding="utf-8")
    original = content

    # 1. Poistetaan #numeron-balance-card CSS-lohkot joustavasti regexillä
    content = re.sub(r'\s*#numeron-balance-card\s*\{[^}]*\}', '', content)
    content = re.sub(r'\s*#numeron-balance-card\s+\.bal-[a-z]+\s*\{[^}]*\}', '', content, flags=re.IGNORECASE)

    # 2. Poistetaan saldon JS-latauslohko injektiosta kokonaan
    js_pattern = re.compile(r'// === SALDO LEIMAUSSIVUN YLÄOSAAN.*?(?=// === SUORA|\Z)', re.DOTALL)
    content = js_pattern.sub('', content)

    # 3. Varmistetaan että mahdolliset DOM-viittaukset eivät aiheuta ongelmia
    content = re.sub(r"document\.getElementById\('numeron-balance-card'\)", "false", content)

    if content != original:
        main_act_path.write_text(content, encoding="utf-8")
        print(f"Päivitetty onnistuneesti (saldokysely poistettu): {main_act_path}")
    else:
        print("Ei muutoksia tehtävänä tai saldokyselyä ei löytynyt.")

    # 4. Nostetaan automaattisesti build.gradle / build.gradle.kts -tiedoston versionCode-arvoa pienellä pykälällä
    for gradle_path in [pathlib.Path("app/build.gradle"), pathlib.Path("app/build.gradle.kts"), pathlib.Path("build.gradle")]:
        if gradle_path.exists():
            g_content = gradle_path.read_text(encoding="utf-8")
            match = re.search(r'versionCode\s+(\d+)', g_content)
            if match:
                old_code = int(match.group(1))
                new_code = old_code + 1
                g_content = g_content.replace(f"versionCode {old_code}", f"versionCode {new_code}")
                gradle_path.write_text(g_content, encoding="utf-8")
                print(f"Nostettu versionCode arvosta {old_code} arvoon {new_code} ({gradle_path})")
                break

if __name__ == "__main__":
    main()
