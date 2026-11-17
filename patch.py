#!/usr/bin/env python3
import pathlib
import sys
import re

def main():
    settings_path = pathlib.Path("SettingsDialogHelper.kt.txt")
    if not settings_path.exists():
        alt = pathlib.Path("app/src/main/java/fi/numeron/vuorovahti/SettingsDialogHelper.kt")
        if alt.exists():
            settings_path = alt
        else:
            print("Virhe: SettingsDialogHelper-tiedostoa ei löytynyt.", file=sys.stderr)
            sys.exit(1)

    content = settings_path.read_text(encoding="utf-8")
    original = content

    # Lisätään vastuuvapauslauseke asetussivun alalaitaan (ennen rootContainer.addView(rootContainer tai dialogin luontia))
    disclaimer_code = '''        // Vastuuvapauslauseke (epävirallinen sovellus)
        val tvDisclaimer = TextView(context).apply {
            text = "Tämä on itsenäinen, epävirallinen kolmannen osapuolen asiakassovellus. Numeron vuorovahti ei ole millään tavalla sidoksissa Vismaan, Numeroniin tai muihin mahdollisiin tahoihin."
            textSize = 11f
            setTextColor(Color.parseColor("#64748B"))
            gravity = Gravity.CENTER
            setPadding(dp(16), dp(12), dp(16), dp(12))
        }
        rootContainer.addView(tvDisclaimer)

'''

    # Etsitään kohta, johon alapalkki (footerBar) tai dialogi lisätään, ja lisätään vastuuvapauslauseke juuri ennen footerBar-lisäystä
    target_pattern = 'rootContainer.addView(footerBar)'
    if target_pattern in content and 'epävirallinen' not in content:
        content = content.replace(target_pattern, disclaimer_code + '        ' + target_pattern, 1)

    if content != original:
        settings_path.write_text(content, encoding="utf-8")
        print(f"Päivitetty onnistuneesti: {settings_path}")
    else:
        print("Ei muutoksia tehtävänä tai vastuuvapauslauseke oli jo lisätty.")

    # Nostetaan build.gradle.kts -tiedoston versionCode-arvoa pienellä pykälällä
    for gradle_path in [pathlib.Path("build.gradle.kts.txt"), pathlib.Path("app/build.gradle.kts"), pathlib.Path("build.gradle")]:
        if gradle_path.exists():
            g_content = gradle_path.read_text(encoding="utf-8")
            match = re.search(r'versionCode\s*=\s*(\d+)', g_content)
            if match:
                old_code = int(match.group(1))
                new_code = old_code + 1
                g_content = g_content.replace(f"versionCode = {old_code}", f"versionCode = {new_code}")
                gradle_path.write_text(g_content, encoding="utf-8")
                print(f"Nostettu versionCode arvosta {old_code} arvoon {new_code} ({gradle_path})")
                break

if __name__ == "__main__":
    main()
