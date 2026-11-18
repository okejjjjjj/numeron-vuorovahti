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

    # 1. Poistetaan ProgressBar-latauskuvake ja lisätään sumennusefekti (RenderEffect Android 12+ / scrim)
    if "val spinner = ProgressBar(this)" in content:
        # Let's replace ensureTransitionOverlay implementation using regex or string block
        pattern = r"(val scrim = View\(this\)\.apply \{[^}]+\}\s*overlay\.addView\(scrim[^}]+\}\s*)val spinner = ProgressBar\(this\)\.apply \{[^}]+\}\s*val sizePx = \([^)]+\)\.toInt\(\)\s*overlay\.addView\(spinner[^)]+\)\s*"
        replacement = r"\1"
        content, count = re.subn(pattern, replacement, content, flags=re.DOTALL)
        if count > 0:
            changes += count
            print("Poistettu pyörivä ProgressBar-latauskuvake.")

    # 2. Lisätään RenderEffect sumennus snapshotViewlle
    if "setRenderEffect" not in content and "snapshotView = snap" in content:
        pattern = r"(snapshotView = snap)"
        replacement = r"\1\n            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {\n                setRenderEffect(\n                    android.graphics.RenderEffect.createBlurEffect(\n                        24f,\n                        24f,\n                        android.graphics.Shader.TileMode.CLAMP\n                    )\n                )\n            }"
        content, count = re.subn(pattern, replacement, content, count=1)
        if count > 0:
            changes += count
            print("Lisätty RenderEffect-sumennus taustakuvaan.")

    # 3. Korvataan kuukausinäkymän pikatoivepalkin klikkauskuuntelija capture-vaiheella ja e.stopImmediatePropagation()
    if "window.location.pathname.toLowerCase().indexOf('/calendar/month')" not in content and "_quickRequestInstalled" in content:
        # replace the quick request listener condition / implementation
        old_qr = "if (window.location.pathname.toLowerCase().indexOf('/calendar') !== -1 && !window._quickRequestInstalled)"
        new_qr = "if (window.location.pathname.toLowerCase().indexOf('/calendar/month') !== -1 && !window._quickRequestInstalled)"
        if old_qr in content:
            content = content.replace(old_qr, new_qr, 1)
            changes += 1
            print("Päivitetty pikatoivepalkin reitintarkistus (/calendar/month).")

    if content != original:
        main_act_path.write_text(content, encoding="utf-8")
        print(f"Päivitetty onnistuneesti: {main_act_path} ({changes} muutosta)")
    else:
        print("Ei muutoksia tehty.")

if __name__ == "__main__":
    main()
