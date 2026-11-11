import pathlib, re

for file_name in ["app/build.gradle.kts", "app/build.gradle"]:
    gf = pathlib.Path(file_name)
    if gf.exists():
        c = gf.read_text(encoding="utf-8")
        
        # VersionCode automaattinen nosto (+1)
        vc_match = re.search(r'versionCode(?:\s*=\s*|\s+)(\d+)', c)
        if vc_match:
            old_vc = int(vc_match.group(1))
            new_vc = old_vc + 1
            c = re.sub(rf'(versionCode(?:\s*=\s*|\s+)){old_vc}\b', rf'\g<1>{new_vc}', c)
            print(f"versionCode nostettu: {old_vc} -> {new_vc}")

        # VersionName automaattinen nosto (esim. "1.0.4" -> "1.0.5")
        vn_match = re.search(r'versionName(?:\s*=\s*|\s+)["\']([^"\']+)["\']', c)
        if vn_match:
            old_vn = vn_match.group(1)
            parts = old_vn.split('.')
            if parts[-1].isdigit():
                parts[-1] = str(int(parts[-1]) + 1)
                new_vn = ".".join(parts)
                c = re.sub(rf'(versionName(?:\s*=\s*|\s+)["\']){old_vn}(["\'])', rf'\g<1>{new_vn}\g<2>', c)
                print(f"versionName nostettu: {old_vn} -> {new_vn}")

        gf.write_text(c, encoding="utf-8")
        print(f"{file_name} päivitetty (Versiot nostettu)!")
