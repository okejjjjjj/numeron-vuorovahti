import pathlib, re

print("Ajetaan patch.py...")


# =========================================================
# VERSIONUMERON NOSTO
# =========================================================
for file_name in ["app/build.gradle.kts", "app/build.gradle"]:
    gf = pathlib.Path(file_name)
    if gf.exists():
        c = gf.read_text(encoding="utf-8")
        updated = False

        vc_match = re.search(r'versionCode(?:\s*=\s*|\s+)(\d+)', c)
        if vc_match:
            old_vc = int(vc_match.group(1))
            new_vc = old_vc + 1
            c = re.sub(rf'(versionCode(?:\s*=\s*|\s+)){old_vc}\b', rf'\g<1>{new_vc}', c, count=1)
            print(f"versionCode: {old_vc} -> {new_vc}")
            updated = True

        vn_match = re.search(r'versionName(?:\s*=\s*|\s+)["\']([^"\']+)["\']', c)
        if vn_match:
            old_vn = vn_match.group(1)
            parts = old_vn.split('.')
            if parts[-1].isdigit():
                parts[-1] = str(int(parts[-1]) + 1)
                new_vn = ".".join(parts)
                c = re.sub(rf'(versionName(?:\s*=\s*|\s+)["\']){re.escape(old_vn)}(["\'])', rf'\g<1>{new_vn}\g<2>', c, count=1)
                print(f"versionName: {old_vn} -> {new_vn}")
                updated = True

        if updated:
            gf.write_text(c, encoding="utf-8", newline="\n")
            print(f"Päivitettiin {file_name}")
