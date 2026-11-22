#!/usr/bin/env python3
"""
Numeron Vuorovahti - Koottu korjaus- ja optimointipatch.
Helposti peruttavissa Gitissä: git revert HEAD, git checkout -- . tai python3 patch.py --revert
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

BACKUP_DIR = Path(".patch_backups")
IGNORED_DIRS = {".git", ".gradle", "build", ".idea", ".patch_backups"}


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

    old_login_sig = "private fun handleAutoLogin() {"
    new_login_sig = "private fun handleAutoLogin(attempt: Int = 0) {"
    text = replace_exact(text, old_login_sig, new_login_sig, "MainActivity: handleAutoLogin yritysparametri", path)

    old_login_retry = "webView.postDelayed({ handleAutoLogin() }, 300L)"
    new_login_retry = "if (attempt < 15) { webView.postDelayed({ handleAutoLogin(attempt + 1) }, 300L) }"
    text = replace_exact(text, old_login_retry, new_login_retry, "MainActivity: handleAutoLogin max 15 yritystä", path)

    old_cal_obs = """                        var calObs = new MutationObserver(function() {
                            runCalendarCleanup();
                        });"""
    new_cal_obs = """                        var calCleanupTimer = null;
                        var calObs = new MutationObserver(function() {
                            if (calCleanupTimer) clearTimeout(calCleanupTimer);
                            calCleanupTimer = setTimeout(function() { runCalendarCleanup(); }, 80);
                        });"""
    text = replace_exact(text, old_cal_obs, new_cal_obs, "MainActivity: setupCalendarCleanup 80ms debounce", path)

    old_nav = """            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition
                val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)"""
    new_nav = """            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition
                navigateJob?.cancel()
                val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)"""
    text = replace_exact(text, old_nav, new_nav, "MainActivity: navigateToTab varmista vanhan jobin peruutus", path)

    if text != orig:
        backup_file(path)
        path.write_text(text, encoding="utf-8")
        return True
    return False


def patch_background_auth_helper(path: Path) -> bool:
    orig = path.read_text(encoding="utf-8")
    text = orig

    old_cookie_fn = """        fun persistUpdatedCookies(updated: Map<String, String>, original: Map<String, String>) {
            if (updated == original) return
            val cm = CookieManager.getInstance()"""
    new_cookie_fn = """        fun persistUpdatedCookies(updated: Map<String, String>, original: Map<String, String>) = synchronized(cookieSyncLock) {
            if (updated == original) return
            val cm = CookieManager.getInstance()"""
    text = replace_exact(text, old_cookie_fn, new_cookie_fn, "BackgroundAuthHelper: synkronoi persistUpdatedCookies", path)

    if text != orig:
        backup_file(path)
        path.write_text(text, encoding="utf-8")
        return True
    return False


def patch_calendar_change_tracker(path: Path) -> bool:
    orig = path.read_text(encoding="utf-8")
    text = orig

    old_revert_block = """                btnRevert.setOnClickListener {
                    if (revertSingleChangeAndSave(context, item)) {
                        Toast.makeText(context, "Muutos peruttu: ${item.title}", Toast.LENGTH_SHORT).show()
                        dialogRef?.dismiss()
                        onChanged?.invoke()
                        showManageChangesDialog(context, onChanged)
                    } else {
                        Toast.makeText(context, "Muutoksen peruminen epäonnistui", Toast.LENGTH_SHORT).show()
                    }
                }"""

    new_revert_block = """                btnRevert.setOnClickListener {
                    btnRevert.isEnabled = false
                    kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
                        val ok = revertSingleChangeAndSave(context, item)
                        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                            if (ok) {
                                Toast.makeText(context, "Muutos peruttu: ${item.title}", Toast.LENGTH_SHORT).show()
                                dialogRef?.dismiss()
                                onChanged?.invoke()
                                showManageChangesDialog(context, onChanged)
                            } else {
                                btnRevert.isEnabled = true
                                Toast.makeText(context, "Muutoksen peruminen epäonnistui", Toast.LENGTH_SHORT).show()
                            }
                        }
                    }
                }"""

    text = replace_exact(text, old_revert_block, new_revert_block, "CalendarChangeTracker: revertSingleChangeAndSave taustasäikeeseen", path)

    if text != orig:
        backup_file(path)
        path.write_text(text, encoding="utf-8")
        return True
    return False


def patch_quick_stamp_activity(path: Path) -> bool:
    orig = path.read_text(encoding="utf-8")
    text = orig

    old_fields = "    private var timeoutRunnable: Runnable? = null"
    new_fields = """    private var timeoutRunnable: Runnable? = null
    private var closeRunnable: Runnable? = null"""
    text = replace_exact(text, old_fields, new_fields, "QuickStampActivity: lisää closeRunnable-kenttä", path)

    old_post_close = """        mainHandler.postDelayed({
            finishCleanly()
        }, closeDelayMs)"""
    new_post_close = """        closeRunnable?.let { mainHandler.removeCallbacks(it) }
        val r = Runnable { finishCleanly() }
        closeRunnable = r
        mainHandler.postDelayed(r, closeDelayMs)"""
    text = replace_exact(text, old_post_close, new_post_close, "QuickStampActivity: tallenna closeRunnable", path)

    old_cancel_to = """    private fun cancelTimeout() {
        timeoutRunnable?.let { mainHandler.removeCallbacks(it) }
        timeoutRunnable = null
    }"""
    new_cancel_to = """    private fun cancelTimeout() {
        timeoutRunnable?.let { mainHandler.removeCallbacks(it) }
        timeoutRunnable = null
        closeRunnable?.let { mainHandler.removeCallbacks(it) }
        closeRunnable = null
    }"""
    text = replace_exact(text, old_cancel_to, new_cancel_to, "QuickStampActivity: peruuta closeRunnable cancelTimeoutissa", path)

    if text != orig:
        backup_file(path)
        path.write_text(text, encoding="utf-8")
        return True
    return False


def patch_numeron_parser(path: Path) -> bool:
    orig = path.read_text(encoding="utf-8")
    text = orig

    old_extract = """    fun extractCircleDates(html: String): Set<LocalDate> {
        val doc = Jsoup.parse(html)"""
    new_extract = """    fun extractCircleDates(html: String): Set<LocalDate> = extractCircleDatesFromDoc(Jsoup.parse(html))

    fun extractCircleDatesFromDoc(doc: org.jsoup.nodes.Document): Set<LocalDate> {"""
    text = replace_exact(text, old_extract, new_extract, "NumeronParser: extractCircleDatesFromDoc-ylikuormitus", path)

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
    print("Käynnistetään Numeron Vuorovahti -korjauspatch...")
    ensure_gitignore_entry(".patch_backups/")

    targets = [
        ("MainActivity.kt", patch_main_activity),
        ("BackgroundAuthHelper.kt", patch_background_auth_helper),
        ("CalendarChangeTracker.kt", patch_calendar_change_tracker),
        ("QuickStampActivity.kt", patch_quick_stamp_activity),
        ("NumeronParser.kt", patch_numeron_parser),
    ]

    changed_files = 0
    for filename, fn in targets:
        path = find_file(filename)
        if path is None:
            print(f"[EI LÖYTYNYT] {filename}")
            continue
        print(f"Käsitellään: {path}")
        if fn(path):
            changed_files += 1

    if bump_version_code():
        changed_files += 1

    print(f"\nValmis! Muokattuja tiedostoja: {changed_files}.")
    print("Peruminen Gitissä: git revert HEAD  (tai: git checkout -- . / python3 patch.py --revert)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Numeron Vuorovahti korjauspatch")
    parser.add_argument("--revert", action="store_true", help="Palauta alkuperäiset tiedostot varmuuskopioista")
    args = parser.parse_args()
    if args.revert:
        return revert_all()
    return apply_all()


if __name__ == "__main__":
    sys.exit(main())
