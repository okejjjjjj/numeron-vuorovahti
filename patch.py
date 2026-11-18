#!/usr/bin/env python3
import pathlib
import sys

def main():
    path = pathlib.Path("app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt")
    if not path.exists():
        matches = list(pathlib.Path(".").rglob("MainActivity.kt"))
        if matches:
            path = matches[0]
        else:
            print("MainActivity.kt ei löytynyt!", file=sys.stderr)
            sys.exit(1)

    content = path.read_text(encoding="utf-8")

    broken_variants = [
        "ProgressBar(this, null, android.R.style.Widget_ProgressBar_Medium)",
        "ProgressBar(this, null, android.R.attr.progressBarStyleMedium)",
    ]

    updated = False
    for variant in broken_variants:
        if variant in content:
            content = content.replace(variant, "ProgressBar(this)", 1)
            updated = True

    if updated:
        assert content.count("{") == content.count("}"), "Aaltosulkeet eivät täsmää!"
        assert content.count("(") == content.count(")"), "Kaarisulkeet eivät täsmää!"
        path.write_text(content, encoding="utf-8")
        print("[OK] ProgressBar-kutsu korjattu muotoon ProgressBar(this).")
    else:
        print("[INFO] Korjattavaa riviä ei löytynyt.")

if __name__ == "__main__":
    main()
