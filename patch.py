#!/usr/bin/env python3
import pathlib
import re
import sys

def find_file(candidates):
    for c in candidates:
        p = pathlib.Path(c)
        if p.exists():
            return p
    return None

def main():
    main_act_path = find_file([
        "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt",
        "MainActivity.kt",
        "MainActivity.kt.txt"
    ])
    if not main_act_path:
        print("Virhe: MainActivity.kt-tiedostoa ei löytynyt.", file=sys.stderr)
        sys.exit(1)

    content = main_act_path.read_text(encoding="utf-8")
    original = content
    changes = 0

    # Poistetaan pyörivä ProgressBar-latauskuvake
    if "val spinner = ProgressBar(this)" in content:
        pattern = r"(val scrim = View\(this\)\.apply \{[^}]+\}\s*overlay\.addView\(scrim[^}]+\}\s*)val spinner = ProgressBar\(this\)\.apply \{[^}]+\}\s*val sizePx = \([^)]+\)\.toInt\(\)\s*overlay\.addView\(spinner[^)]+\)\s*"
        replacement = r"\1"
        content, count = re.subn(pattern, replacement, content, flags=re.DOTALL)
        if count > 0:
            changes += count
            print("Poistettu pyörivä ProgressBar-latauskuvake.")

    if content != original:
        main_act_path.write_text(content, encoding="utf-8")
        print(f"Päivitetty onnistuneesti: {main_act_path} ({changes} muutosta)")
    else:
        print("Ei muutoksia tehty.")

if __name__ == "__main__":
    main()
