#!/usr/bin/env python3
"""
Numeron Vuorovahti – Leimausten muotoilun säilyttäminen "Näytä lisää" -painalluksen jälkeen.

Peruttavissa Gitissä:
  git revert HEAD
  tai: git checkout -- .
  tai: python3 patch.py --revert
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

BACKUP_DIR = Path(".patch_backups")
IGNORED_DIRS = {".git", ".gradle", "build", ".idea", ".patch_backups", ".patch_backups"}


def find_file(filename: str) -> Path | None:
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        if filename in files:
            return Path(root) / filename
    return None


def backup_file(path: Path) -> None:
    dest = BACKUP_DIR / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(path, dest)


def ensure_gitignore_entry(entry: str) -> None:
    gitignore = Path(".gitignore")
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines()]
        if entry not in lines:
            suffix = "" if content.endswith("\n") or content == "" else "\n"
            gitignore.write_text(content + suffix + entry + "\n", encoding="utf-8")


def revert_all() -> int:
    if not BACKUP_DIR.exists():
        print("Ei varmuuskopioita kansiossa .patch_backups/. Käytä komentoa: git checkout -- .")
        return 1
    restored = 0
    for root, _, files in os.walk(BACKUP_DIR):
        for f in files:
            backup_path = Path(root) / f
            rel_path = backup_path.relative_to(BACKUP_DIR)
            shutil.copy2(backup_path, rel_path)
            print(f"[PALAUTETTU] {rel_path}")
            restored += 1
    shutil.rmtree(BACKUP_DIR, ignore_errors=True)
    print(f"Valmis. Palautettiin {restored} tiedostoa.")
    return 0


def replace_exact(content: str, old: str, new: str, label: str, file_path: Path) -> str:
    if new in content:
        print(f"  [OK - jo käytössä] {label}")
        return content
    if old not in content:
        print(f"  [OHITETTU - ankkuria ei löytynyt] {label} ({file_path})")
        return content
    print(f"  [PÄIVITETTY] {label}")
    return content.replace(old, new, 1)


def patch_main_activity(path: Path) -> bool:
    orig = path.read_text(encoding="utf-8")
    text = orig

    old_expose = """                        applyStampingColors();
                        var stampTblForColor = document.getElementById('table-latest-stamps');"""
    new_expose = """                        window.vvApplyStampingColors = applyStampingColors;
                        applyStampingColors();
                        var stampTblForColor = document.getElementById('table-latest-stamps');"""
    text = replace_exact(text, old_expose, new_expose, "MainActivity: altista vvApplyStampingColors", path)

    old_reveal = """                    function revealHiddenStampRows() {
                        var hiddenRows = document.querySelectorAll('#table-latest-stamps tr.hidden, #table-latest-stamps tr.hide, #table-latest-stamps tr[style*="display: none"], #table-latest-stamps tr[style*="display:none"]');
                        for (var i = 0; i < hiddenRows.length; i++) {
                            hiddenRows[i].classList.remove('hidden', 'hide');
                            hiddenRows[i].style.display = 'table-row';
                        }
                    }"""
    new_reveal = """                    function revealHiddenStampRows() {
                        var hiddenRows = document.querySelectorAll('#table-latest-stamps tr.hidden, #table-latest-stamps tr.hide, #table-latest-stamps tr[style*="display: none"], #table-latest-stamps tr[style*="display:none"]');
                        for (var i = 0; i < hiddenRows.length; i++) {
                            hiddenRows[i].classList.remove('hidden', 'hide');
                            hiddenRows[i].style.display = 'table-row';
                        }
                        if (typeof window.vvApplyStampingColors === 'function') {
                            window.vvApplyStampingColors();
                        }
                    }"""
    text = replace_exact(text, old_reveal, new_reveal, "MainActivity: päivitä kapselit revealHiddenStampRowsissa", path)

    old_show_more = """                        if (isShowMoreTrigger(e.target)) {
                            revealHiddenStampRows();
                            setTimeout(revealHiddenStampRows, 150);
                            setTimeout(revealHiddenStampRows, 500);
                        }"""
    new_show_more = """                        if (isShowMoreTrigger(e.target)) {
                            revealHiddenStampRows();
                            setTimeout(revealHiddenStampRows, 150);
                            setTimeout(revealHiddenStampRows, 500);
                            setTimeout(revealHiddenStampRows, 1100);
                        }"""
    text = replace_exact(text, old_show_more, new_show_more, "MainActivity: varmista jälkikäteen latautuvien rivien muotoilu", path)

    if text != orig:
        backup_file(path)
        path.write_text(text, encoding="utf-8")
        return True
    return False


def bump_version_code() -> bool:
    for gradle_name in ("build.gradle.kts", "build.gradle"):
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            if gradle_name in files:
                p = Path(root) / gradle_name
                content = p.read_text(encoding="utf-8")
                m = re.search(r'(versionCode\s*=?\s*)(\d+)', content)
                if m:
                    old_vc = int(m.group(2))
                    new_vc = old_vc + 1
                    updated = content[:m.start()] + f"{m.group(1)}{new_vc}" + content[m.end():]
                    backup_file(p)
                    p.write_text(updated, encoding="utf-8")
                    print(f"[VERSIO] {p}: versionCode {old_vc} -> {new_vc}")
                    return True
    return False


def apply_all() -> int:
    print("Käynnistetään Numeron Vuorovahti -leimausmuotoilun korjauspatch...")
    ensure_gitignore_entry(".patch_backups/")

    changed_files = 0
    main_path = find_file("MainActivity.kt")
    if main_path is None:
        print("[EI LÖYTYNYT] MainActivity.kt")
    else:
        print(f"Käsitellään: {main_path}")
        if patch_main_activity(main_path):
            changed_files += 1

    if bump_version_code():
        changed_files += 1

    print(f"\nValmis! Muokattuja tiedostoja: {changed_files}.")
    print("Peruminen Gitissä: git revert HEAD  (tai: git checkout -- . / python3 patch.py --revert)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Numeron Vuorovahti leimausmuotoilun korjauspatch")
    parser.add_argument("--revert", action="store_true", help="Palauta alkuperäiset tiedostot varmuuskopioista")
    args = parser.parse_args()
    if args.revert:
        return revert_all()
    return apply_all()


if __name__ == "__main__":
    sys.exit(main())
