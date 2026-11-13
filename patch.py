import pathlib, re

print("Aloitetaan patch-ajo...")

# =====================================================================
# OSA 1: VERSIONUMERON NOSTO (GRADLE)
# Tämä osa nostaa sovelluksen versionCodea ja versionNamea automaattisesti.
# =====================================================================
print("\n--- Osa 1: Versionumeroiden päivitys ---")
for file_name in ["app/build.gradle.kts", "app/build.gradle"]:
    gf = pathlib.Path(file_name)
    if gf.exists():
        c = gf.read_text(encoding="utf-8")
        
        # Nosta versionCode (esim. versionCode 14 -> 15)
        vc_match = re.search(r'versionCode(?:\s*=\s*|\s+)(\d+)', c)
        if vc_match:
            new_vc = int(vc_match.group(1)) + 1
            c = re.sub(rf'(versionCode(?:\s*=\s*|\s+)){vc_match.group(1)}\b', rf'\g<1>{new_vc}', c)
            print(f" -> versionCode päivitetty: {vc_match.group(1)} -> {new_vc}")
            
        # Nosta versionName (esim. versionName "1.0.4" -> "1.0.5")
        vn_match = re.search(r'versionName(?:\s*=\s*|\s+)["\']([^"\']+)["\']', c)
        if vn_match:
            parts = vn_match.group(1).split('.')
            if parts[-1].isdigit():
                parts[-1] = str(int(parts[-1]) + 1)
                new_vn = ".".join(parts)
                c = re.sub(rf'(versionName(?:\s*=\s*|\s+)["\']){vn_match.group(1)}(["\'])', rf'\g<1>{new_vn}\g<2>', c)
                print(f" -> versionName päivitetty: {vn_match.group(1)} -> {new_vn}")
                
        gf.write_text(c, encoding="utf-8")
        print(f"Gradle-päivitys valmis ({file_name}).")
