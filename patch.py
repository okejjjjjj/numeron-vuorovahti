#!/usr/bin/env python3
import pathlib
import sys
import re

def main():
    # 1. Lisätään AndroidManifest.xml:ään viittaus varmuuskopiosääntöihin, jos sitä ei vielä ole
    manifest_path = pathlib.Path("app/src/main/AndroidManifest.xml")
    if not manifest_path.exists():
        manifest_path = pathlib.Path("AndroidManifest.xml")

    if manifest_path.exists():
        m_content = manifest_path.read_text(encoding="utf-8")
        if "fullBackupContent" not in m_content:
            # Lisätään android:fullBackupContent="@xml/backup_rules" android:allowBackup="true" yhteyteen
            m_content = m_content.replace(
                'android:allowBackup="true"',
                'android:allowBackup="true"\n        android:fullBackupContent="@xml/backup_rules"'
            )
            manifest_path.write_text(m_content, encoding="utf-8")
            print(f"Päivitetty Manifest: {manifest_path}")

    # 2. Luodaan res/xml/backup_rules.xml -tiedosto, joka varmuuskopioi SharedPreferences-tiedoston (NumeronPrefs.xml)
    xml_dir = pathlib.Path("app/src/main/res/xml")
    xml_dir.mkdir(parents=True, exist_ok=True)
    backup_rules_path = xml_dir / "backup_rules.xml"
    
    backup_rules_content = '''<?xml version="1.0" encoding="utf-8"?>
<full-backup-content>
    <!-- Varmuuskopioidaan sovelluksen SharedPreferences-asetukset (organisaatiotunnus ym.) -->
    <include domain="sharedpref" path="NumeronPrefs.xml" />
</full-backup-content>
'''
    backup_rules_path.write_text(backup_rules_content, encoding="utf-8")
    print(f"Luotu/päivitetty varmuuskopiosäännöt: {backup_rules_path}")

    # 3. Nostetaan versionCode-arvoa pienellä pykälällä build.gradle.kts -tiedostosta
    for gradle_path in [pathlib.Path("app/build.gradle.kts"), pathlib.Path("app/build.gradle"), pathlib.Path("build.gradle.kts")]:
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
