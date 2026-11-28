#!/usr/bin/env python3
"""
Numeron Vuorovahti (V2) – Työvuorolistapalkin yhtenäistys (patch_period_summary.py):
- NativeShiftsView.kt:
  * 3 viikon työvuorolistapalkkiin sama järjestys kuin kuukausikoosteeseen (vuorot • tunnit • aamu / ilta / yö)
  * 3 viikon jakson yhteenvetodialogiin sama järjestys (vuorot • tunnit)
- app/build.gradle.kts: versionCode +1, versionName +1 (idempotentti)
"""

import re
import sys
from pathlib import Path


def find_file(filename: str) -> Path | None:
    candidates = [
        Path("app/src/main/java/fi/numeron/vuorovahti") / filename,
        Path("src/main/java/fi/numeron/vuorovahti") / filename,
        Path("app") / filename,
        Path(filename),
    ]
    for c in candidates:
        if c.exists():
            return c
    for p in Path(".").rglob(filename):
        if ".git" not in p.parts and "build" not in p.parts:
            return p
    return None


def read_text_keep_nl(path: Path) -> tuple[str, str]:
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def write_text_keep_nl(path: Path, content: str, newline: str) -> None:
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


def patch_native_shifts_view(path: Path) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    # 1. 3 viikon jakson klikkausdialogin järjestys: vuorot ensin, sitten tunnit
    old_dialog_summary = """            summaryBox.addView(
                TextView(context).apply {
                    text = "$hoursStr h  •  ${stats.shiftCount} $word"
                    setTextColor(Color.WHITE)
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
                    setTypeface(null, Typeface.BOLD)
                }
            )
            val parts = mutableListOf<String>()
            if (stats.morningCount > 0) parts.add(if (en) "${stats.morningCount} morning" else "${stats.morningCount} aamua")
            if (stats.eveningCount > 0) parts.add(if (en) "${stats.eveningCount} evening" else "${stats.eveningCount} iltaa")
            if (stats.nightCount > 0) parts.add(if (en) "${stats.nightCount} night" else "${stats.nightCount} yötä")
            if (parts.isNotEmpty()) {
                summaryBox.addView(
                    TextView(context).apply {
                        text = parts.joinToString(" • ")"""

    new_dialog_summary = """            summaryBox.addView(
                TextView(context).apply {
                    text = "${stats.shiftCount} $word  •  $hoursStr h"
                    setTextColor(Color.WHITE)
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
                    setTypeface(null, Typeface.BOLD)
                }
            )
            val parts = mutableListOf<String>()
            if (stats.morningCount > 0) parts.add(if (en) "${stats.morningCount} morn" else "${stats.morningCount} aamu")
            if (stats.eveningCount > 0) parts.add(if (en) "${stats.eveningCount} eve" else "${stats.eveningCount} ilta")
            if (stats.nightCount > 0) parts.add(if (en) "${stats.nightCount} night" else "${stats.nightCount} yö")
            if (parts.isNotEmpty()) {
                summaryBox.addView(
                    TextView(context).apply {
                        text = parts.joinToString(" / ")"""

    text = replace_once(
        text,
        old_dialog_summary,
        new_dialog_summary,
        "NativeShiftsView: jaksoyhteenvetodialogin järjestys (vuorot • tunnit)"
    )

    # 2. 3 viikon työvuorolistapalkki: vuorot • tunnit • aamu / ilta / yö
    old_period_bar = """                periodBar.addView(pTv, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))

                if (pStats.shiftCount > 0) {
                    val pHours = ScheduleShareHelper.formatHours(pStats.totalMinutes, en)
                    val unitShort = if (en) "sh" else "v"
                    val hTv = TextView(context).apply {
                        text = "$pHours h • ${pStats.shiftCount} $unitShort"
                        setTextColor(Color.parseColor(if (isPeriodStartRow) "#E2E8F0" else "#94A3B8"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 10.5f)
                        setTypeface(null, Typeface.BOLD)
                    }
                    periodBar.addView(hTv, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))
                }"""

    new_period_bar = """                periodBar.addView(pTv, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))

                if (pStats.shiftCount > 0) {
                    val pHours = ScheduleShareHelper.formatHours(pStats.totalMinutes, en)
                    val unitShort = if (en) "sh" else "v"
                    val pBreakdownParts = mutableListOf<String>()
                    if (pStats.morningCount > 0) pBreakdownParts.add(if (en) "${pStats.morningCount} morn" else "${pStats.morningCount} aamu")
                    if (pStats.eveningCount > 0) pBreakdownParts.add(if (en) "${pStats.eveningCount} eve" else "${pStats.eveningCount} ilta")
                    if (pStats.nightCount > 0) pBreakdownParts.add(if (en) "${pStats.nightCount} night" else "${pStats.nightCount} yö")
                    val pBreakdownSuffix = if (pBreakdownParts.isNotEmpty()) " • ${pBreakdownParts.joinToString(" / ")}" else ""

                    val hTv = TextView(context).apply {
                        text = "${pStats.shiftCount} $unitShort • $pHours h$pBreakdownSuffix"
                        gravity = Gravity.END
                        setTextColor(Color.parseColor(if (isPeriodStartRow) "#E2E8F0" else "#94A3B8"))
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 10f)
                        setTypeface(null, Typeface.BOLD)
                    }
                    periodBar.addView(
                        hTv,
                        LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f).apply {
                            marginStart = dp(6)
                        }
                    )
                }"""

    text = replace_once(
        text,
        old_period_bar,
        new_period_bar,
        "NativeShiftsView: 3 vko työvuorolistapalkkiin järjestys (vuorot • tunnit • aamu / ilta / yö)"
    )

    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def patch_build_gradle(path: Path, should_bump: bool) -> bool:
    text, nl = read_text_keep_nl(path)
    orig = text

    if should_bump:
        m_code = re.search(r"versionCode\s*=\s*(\d+)", text)
        if m_code:
            old_code = int(m_code.group(1))
            new_code = old_code + 1
            text = text[:m_code.start()] + f"versionCode = {new_code}" + text[m_code.end():]
            print(f"  [PÄIVITETTY] versionCode {old_code} -> {new_code}")

        m_name = re.search(r'versionName\s*=\s*"(\d+)\.(\d+)\.(\d+)"', text)
        if m_name:
            maj, minor, patch_num = int(m_name.group(1)), int(m_name.group(2)), int(m_name.group(3))
            old_name = f"{maj}.{minor}.{patch_num}"
            new_name = f"{maj}.{minor}.{patch_num + 1}"
            text = text[:m_name.start()] + f'versionName = "{new_name}"' + text[m_name.end():]
            print(f'  [PÄIVITETTY] versionName "{old_name}" -> "{new_name}"')
    else:
        print("  [OK - jo sovellettu] versiota ei koroteta toistuvassa ajossa")

    if text != orig:
        write_text_keep_nl(path, text, nl)
        return True
    return False


def main() -> int:
    changed = 0

    ns_path = find_file("NativeShiftsView.kt")
    if ns_path is None:
        print("[VIRHE] NativeShiftsView.kt ei löytynyt!")
        return 1

    print(f"Käsitellään: {ns_path}")
    shifts_changed = patch_native_shifts_view(ns_path)
    if shifts_changed:
        changed += 1

    gr_path = find_file("build.gradle.kts")
    if gr_path is not None:
        print(f"Käsitellään: {gr_path}")
        if patch_build_gradle(gr_path, should_bump=shifts_changed):
            changed += 1
    else:
        print("[EI LÖYTYNYT] build.gradle.kts")

    print(f"\nValmis! Muokattuja tiedostoja: {changed}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
