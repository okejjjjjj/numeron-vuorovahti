#!/usr/bin/env python3
"""
Numeron Vuorovahti – Selkeä napakka teksti testi-ilmoituksen leimausnappiin.
"""

import os
import sys
from pathlib import Path

IGNORED_DIRS = {".git", ".gradle", "build", ".idea", ".patch_backups"}


def find_file(filename: str) -> Path | None:
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        if filename in files:
            return Path(root) / filename
    return None


def replace_exact(content: str, old: str, new: str, label: str, file_path: Path) -> str:
    if new in content:
        print(f"  [OK - jo käytössä] {label}")
        return content
    if old not in content:
        print(f"  [OHITETTU - ankkuria ei löytynyt] {label} ({file_path})")
        return content
    print(f"  [PÄIVITETTY] {label}")
    return content.replace(old, new, 1)


def patch_receiver(path: Path) -> bool:
    orig = path.read_text(encoding="utf-8")
    text = orig

    old_block = """        val fullButtonLabel = if (en) {
            if (isEnding) "CLOCK OUT" else "CLOCK IN"
        } else {
            if (isEnding) "LEIMAA ULOS" else "LEIMAA SISÄÄN"
        }
        val shortButtonLabel = if (en) {
            if (isEnding) "OUT" else "IN"
        } else {
            if (isEnding) "ULOS" else "SISÄÄN"
        }"""

    new_block = """        val fullButtonLabel = if (isTest) {
            if (en) "TEST (NO STAMP)" else "TESTI (EI LEIMAA)"
        } else if (en) {
            if (isEnding) "CLOCK OUT" else "CLOCK IN"
        } else {
            if (isEnding) "LEIMAA ULOS" else "LEIMAA SISÄÄN"
        }
        val shortButtonLabel = if (isTest) {
            if (en) "TEST" else "TESTI"
        } else if (en) {
            if (isEnding) "OUT" else "IN"
        } else {
            if (isEnding) "ULOS" else "SISÄÄN"
        }"""

    text = replace_exact(text, old_block, new_block, "ShiftReminderReceiver: napakka testi-ilmoituksen nappiteksti", path)

    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> int:
    print("Käynnistetään Numeron Vuorovahti -testinapin päivityspatch...")
    receiver_path = find_file("ShiftReminderReceiver.kt")
    if receiver_path is None:
        print("[EI LÖYTYNYT] ShiftReminderReceiver.kt")
        return 1

    print(f"Käsitellään: {receiver_path}")
    changed = patch_receiver(receiver_path)
    print(f"\nValmis! Muokattuja tiedostoja: {1 if changed else 0}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
