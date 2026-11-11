import pathlib, re

# 1. Päivitetään SettingsActivity.kt asettamaan versio suoraan kustomoidun layoutin tekstiin
sa_path = pathlib.Path("app/src/main/java/fi/oma/numeron/SettingsActivity.kt")
if sa_path.exists():
    sa = sa_path.read_text(encoding="utf-8")
    
    # Etsitään aiempi näkymätön title-komento ja korvataan se elementin etsinnällä
    old_logic = r'val version = pInfo\.versionName\s*title = "Asetukset \(v\$version\)"'
    
    new_logic = """val version = pInfo.versionName
            
            // Etsitään ruudulta tekstikenttä, jossa lukee "Asetukset", ja lisätään versio siihen
            val rootView = findViewById<android.view.ViewGroup>(android.R.id.content)
            fun updateLabels(v: android.view.View) {
                if (v is android.widget.TextView) {
                    if (v.text.toString().trim().equals("Asetukset", ignoreCase = true)) {
                        v.text = "Asetukset (v$version)"
                    }
                } else if (v is android.view.ViewGroup) {
                    for (i in 0 until v.childCount) updateLabels(v.getChildAt(i))
                }
            }
            rootView.post { updateLabels(rootView) }"""
            
    sa = re.sub(old_logic, new_logic, sa)
    sa_path.write_text(sa, encoding="utf-8")
    print("SettingsActivity.kt päivitetty (Versionumero injektoitu suoraan näkymään).")

# 2. Nostetaan versionumeroa Play Storea varten
for file_name in ["app/build.gradle.kts", "app/build.gradle"]:
    gf = pathlib.Path(file_name)
    if gf.exists():
        c = gf.read_text(encoding="utf-8")
        
        vc_match = re.search(r'versionCode(?:\s*=\s*|\s+)(\d+)', c)
        if vc_match:
            old_vc = int(vc_match.group(1))
            new_vc = old_vc + 1
            c = re.sub(rf'(versionCode(?:\s*=\s*|\s+)){old_vc}\b', rf'\g<1>{new_vc}', c)
            
        vn_match = re.search(r'versionName(?:\s*=\s*|\s+)["\']([^"\']+)["\']', c)
        if vn_match:
            old_vn = vn_match.group(1)
            parts = old_vn.split('.')
            if parts[-1].isdigit():
                parts[-1] = str(int(parts[-1]) + 1)
                new_vn = ".".join(parts)
                c = re.sub(rf'(versionName(?:\s*=\s*|\s+)["\']){old_vn}(["\'])', rf'\g<1>{new_vn}\g<2>', c)
                
        gf.write_text(c, encoding="utf-8")
        print(f"{file_name} päivitetty (Versiot nostettu).")
