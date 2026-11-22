#!/usr/bin/env python3
"""
Numeron Vuorovahti – kuukausinäkymän viikkosarakkeen kavennus.

Käyttö:
    python3 patch.py --dry-run
    python3 patch.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

IGNORED_DIRS = {".git", "patch_backups", ".gradle", ".idea", "build", "node_modules", "__pycache__"}


def find_file(root: Path, filename: str, must_contain: str | None = None) -> Path:
    matches: list[Path] = []
    for p in root.rglob(filename):
        if any(part in IGNORED_DIRS for part in p.parts):
            continue
        if must_contain is None or must_contain in p.read_text(encoding="utf-8", errors="ignore"):
            matches.append(p)
    if len(matches) != 1:
        raise RuntimeError(
            f"Odotettiin täsmälleen yhtä '{filename}'-tiedostoa, löytyi {len(matches)}: {matches}"
        )
    return matches[0]


def replace_once(content: str, old: str, new: str, label: str) -> str:
    count = content.count(old)
    if count != 1:
        raise RuntimeError(
            f"[{label}] Odotettiin 1 osumaa, löytyi {count}. Tarkista tiedoston versio."
        )
    return content.replace(old, new, 1)


def patch_main_activity(text: str) -> str:
    return replace_once(
        text,
        r'''            .month-week-days td {
                background-color: #233040 !important;
                color: #CBD5E1 !important;
                font-weight: 600 !important;
                font-size: 12px !important;
                padding: 6px 2px !important;
                border: 1px solid #2A394A !important;
                text-align: center !important;
            }
            .month-week-number {
                width: 26px !important;
                background-color: #131C28 !important;
                color: #64748B !important;
                font-size: 11px !important;
                text-align: center !important;
                vertical-align: top !important;
                padding-top: 6px !important;
                border: 1px solid #2A394A !important;
            }''',
        r'''            .month-week-days td {
                background-color: #233040 !important;
                color: #CBD5E1 !important;
                font-weight: 600 !important;
                font-size: 12px !important;
                padding: 6px 2px !important;
                border: 1px solid #2A394A !important;
                text-align: center !important;
            }
            .month-week-days td:first-child {
                width: 24px !important;
                padding-left: 1px !important;
                padding-right: 1px !important;
                font-size: 10px !important;
                white-space: nowrap !important;
            }
            .month-week-number {
                width: 24px !important;
                background-color: #131C28 !important;
                color: #64748B !important;
                font-size: 10px !important;
                text-align: center !important;
                vertical-align: top !important;
                padding: 6px 1px 0 1px !important;
                border: 1px solid #2A394A !important;
            }''',
        "MainActivity:narrow_week_column",
    )


def patch_demo_mode_helper(text: str) -> str:
    return replace_once(
        text,
        r'''            .month-week-days td {
                background-color: #233040;
                color: #CBD5E1;
                font-weight: 600;
                font-size: 12px;
                padding: 6px 2px;
                border: 1px solid #2A394A;
                text-align: center;
            }
            .month-week-number {
                width: 26px;
                background-color: #131C28;
                color: #64748B;
                font-size: 11px;
                text-align: center;
                vertical-align: top;
                padding-top: 6px;
                border: 1px solid #2A394A;
            }''',
        r'''            .month-week-days td {
                background-color: #233040;
                color: #CBD5E1;
                font-weight: 600;
                font-size: 12px;
                padding: 6px 2px;
                border: 1px solid #2A394A;
                text-align: center;
            }
            .month-week-days td:first-child {
                width: 24px;
                padding-left: 1px;
                padding-right: 1px;
                font-size: 10px;
                white-space: nowrap;
            }
            .month-week-number {
                width: 24px;
                background-color: #131C28;
                color: #64748B;
                font-size: 10px;
                text-align: center;
                vertical-align: top;
                padding: 6px 1px 0 1px;
                border: 1px solid #2A394A;
            }''',
        "DemoModeHelper:narrow_week_column",
    )


def patch_build_gradle(text: str) -> str:
    text = replace_once(text, "versionCode = 114", "versionCode = 115", "build.gradle:versionCode")
    text = replace_once(text, 'versionName = "3.2.10"', 'versionName = "3.2.11"', "build.gradle:versionName")
    return text


PATCH_PLAN = [
    ("MainActivity.kt", "class MainActivity", patch_main_activity),
    ("DemoModeHelper.kt", "object DemoModeHelper", patch_demo_mode_helper),
    ("build.gradle.kts", 'applicationId = "com.numeron_vuorovahti"', patch_build_gradle),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Kaventa kuukausinäkymän viikkosarakkeen")
    parser.add_argument("--root", default=".", help="Projektin juurikansio")
    parser.add_argument("--dry-run", action="store_true", help="Tarkista muutokset kirjoittamatta tiedostoja")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    staged_writes: list[tuple[Path, str]] = []

    for filename, marker, patch_fn in PATCH_PLAN:
        path = find_file(root, filename, marker)
        raw_text = path.read_bytes().decode("utf-8")
        eol = "\r\n" if "\r\n" in raw_text else "\n"
        normalized = raw_text.replace("\r\n", "\n")

        patched = patch_fn(normalized)
        if patched == normalized:
            raise RuntimeError(f"[{filename}] Tiedostoon ei tullut muutoksia.")

        staged_writes.append((path, patched.replace("\n", eol)))
        print(f"OK: {path.relative_to(root)}")

    if args.dry_run:
        print(f"\nDRY-RUN OK: {len(staged_writes)} tiedostoa valmiina.")
        return 0

    for path, final_text in staged_writes:
        path.write_text(final_text, encoding="utf-8")

    print(f"\nVALMIS: {len(staged_writes)} tiedostoa päivitetty.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"VIRHE: {exc}", file=sys.stderr)
        sys.exit(1)
