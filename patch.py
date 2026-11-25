#!/usr/bin/env python3
"""
Numeron Vuorovahti – Kalenterien järjestyksen korjaus (patch.py).
Pitää ensimmäisenä lisätyn ensisijaisen Google-tilin listan kärjessä.
"""

import sys
from pathlib import Path


def find_file(filename: str) -> Path | None:
    candidates = [
        Path("app/src/main/java/fi/numeron/vuorovahti") / filename,
        Path("src/main/java/fi/numeron/vuorovahti") / filename,
        Path(filename),
    ]
    for c in candidates:
        if c.exists():
            return c
    for p in Path(".").rglob(filename):
        if ".git" not in p.parts and "build" not in p.parts:
            return p
    return None


def read_kt(path: Path) -> tuple[str, str]:
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def write_kt(path: Path, content: str, newline: str) -> None:
    normalized = content.replace("\r\n", "\n")
    if newline == "\r\n":
        normalized = normalized.replace("\n", "\r\n")
    path.write_bytes(normalized.encode("utf-8"))


def replace_once(content: str, old: str, new: str, label: str) -> str:
    if new in content:
        print(f"  [OK - jo sovellettu] {label}")
        return content
    if old not in content:
        print(f"  [VAROITUS - kohdetta ei löytynyt] {label}")
        return content
    print(f"  [PÄIVITETTY] {label}")
    return content.replace(old, new, 1)


def patch_settings_dialog_helper(path: Path) -> bool:
    text, nl = read_kt(path)
    orig = text

    old_list = "        val list = mutableListOf<CalendarOption>()"
    new_list = "        val list = mutableListOf<Pair<CalendarOption, Boolean>>()"
    text = replace_once(text, old_list, new_list, "Tallenna isPrimary-tieto listaan")

    old_loop = (
        "                list.add(CalendarOption(id, name, account, accountType, en))\n"
        '                if (accountType == "com.google" && isPrimary) {\n'
        "                    val item = list.removeAt(list.lastIndex)\n"
        "                    list.add(0, item)\n"
        "                }"
    )
    new_loop = "                list.add(CalendarOption(id, name, account, accountType, en) to isPrimary)"
    text = replace_once(text, old_loop, new_loop, "Poista käänteinen add(0, item) -siirtely")

    old_return = '        return list.sortedBy { if (it.accountType == "com.google") 0 else 1 }'
    new_return = (
        "        return list\n"
        "            .sortedWith(\n"
        "                compareBy<Pair<CalendarOption, Boolean>>(\n"
        '                    { if (it.first.accountType == "com.google") 0 else 1 },\n'
        "                    { if (it.second) 0 else 1 },\n"
        "                    { it.first.id }\n"
        "                )\n"
        "            )\n"
        "            .map { it.first }"
    )
    text = replace_once(text, old_return, new_return, "Monitasoinen lajittelu (Google -> isPrimary -> id)")

    if text != orig:
        write_kt(path, text, nl)
        return True
    return False


def main() -> int:
    path = find_file("SettingsDialogHelper.kt")
    if path is None:
        print("[EI LÖYTYNYT] SettingsDialogHelper.kt")
        return 1

    print(f"Käsitellään: {path}")
    changed = patch_settings_dialog_helper(path)
    print(f"Valmis! Muokattuja tiedostoja: {1 if changed else 0}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
