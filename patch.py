import pathlib, re

print("Ajetaan patch.py...")

# =========================================================
# [POISTETTAVA OSIO ALKU: ÄÄKKÖSTEN JA MERKISTÖN KORJAUS]
# Poista tämä osio tästä merkistä alla olevaan LOPPU-merkkiin
# asti, kun merkistö on kunnossa repossa.
# =========================================================
def fix_encoding_and_umlauts():
    mojibake_map = {
        "Ã¤": "ä",
        "Ã¶": "ö",
        "Ã¥": "å",
        "Ã„": "Ä",
        "Ã–": "Ö",
        "Ã…": "Å",
        "â€“": "–",
        "â€”": "—",
        "â€º": "›",
        "âš™": "⚙",
        "âœ“": "✓",
        "âœ•": "✕",
        "Â»": "»",
    }
    mojibake_markers = tuple(mojibake_map.keys())

    def repair_line(line: str) -> str:
        if not any(m in line for m in mojibake_markers):
            return line
        for enc in ("cp1252", "latin1"):
            try:
                return line.encode(enc).decode("utf-8")
            except Exception:
                continue
        fixed = line
        for bad, good in mojibake_map.items():
            fixed = fixed.replace(bad, good)
        return fixed

    base_dir = pathlib.Path("app/src/main")
    if not base_dir.exists():
        return

    for pattern in ("*.kt", "*.xml"):
        for file_path in base_dir.rglob(pattern):
            raw = file_path.read_bytes()
            changed = False

            # Poistetaan mahdollinen UTF-8 BOM
            if raw.startswith(b"\xef\xbb\xbf"):
                raw = raw[3:]
                changed = True

            # 1) Jos tiedosto on Windows-1252 / ISO-8859-1 -muodossa (ei kelvollista UTF-8:aa)
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("cp1252")
                changed = True

            # 2) Jos tiedostossa on tuplakoodattuja ääkkösiä (esim. Ã¤, Ã¶, Ã„, Ã–)
            if any(m in text for m in mojibake_markers):
                try:
                    repaired = text.encode("cp1252").decode("utf-8")
                except Exception:
                    repaired = "\n".join(repair_line(line) for line in text.splitlines())
                    if text.endswith("\n"):
                        repaired += "\n"
                if repaired != text:
                    text = repaired
                    changed = True

            if changed:
                file_path.write_text(text, encoding="utf-8", newline="\n")
                print(f"Korjattiin ääkköset / UTF-8: {file_path}")

fix_encoding_and_umlauts()
# =========================================================
# [POISTETTAVA OSIO LOPPU: ÄÄKKÖSTEN JA MERKISTÖN KORJAUS]
# =========================================================

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
