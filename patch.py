#!/usr/bin/env python3
"""
Numeron Vuorovahti – Koottu korjaus- ja optimointipatch.

Suunniteltu siten, että kaikki muutokset ovat atomisia, idempotentteja ja
helposti peruttavissa Gitissä (yksi selkeä commit tai `python3 patch.py --revert`
varmuuskopioista / git checkoutilla).

Korjaukset ja optimoinnit:
1. MainActivity.kt:
   - navigateToTab: korutiinin ja snapshot-siirtymän synkronointi (estää päällekkäiset välilehtilataukset)
   - handleAutoLogin: yritysraja (max 15 yritystä) ikuisen silmukan estämiseksi
   - setupCalendarCleanup: 80 ms debounce MutationObserverille DOM-kuorman pienentämiseksi
   - build.gradle(.kts): pieni versionCode-korotus (+1) jos tiedosto löytyy
2. BackgroundAuthHelper.kt:
   - persistUpdatedCookies: synkronointi olemassa olevalla cookieSyncLock-lukolla
3. CalendarChangeTracker.kt:
   - revertSingleChange: I/O-operaatio taustasäikeeseen (Dispatchers.IO)
4. QuickStampActivity.kt:
   - closeRunnable-viitteen tallennus ja peruutus onNewIntent / finishCleanly -vaiheissa
5. NumeronParser.kt:
   - Jsoup.parse-kutsun välttäminen kahteen kertaan (extractCircleDates hyödyntää valmista Documentia)
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

BACKUP_DIR = Path(".patch_backups")


def find_file(filename: str) -> Path | None:
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in {".git", ".gradle", "build", ".idea", ".patch_backups"}]
        if filename in files:
            return Path(root) / filename
    return None


def backup_file(path: Path) -> None:
    dest = BACKUP_DIR / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(path, dest)


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

    # 1a. Lisää attempt-parametri ja korjaa handleAutoLogin yritysrajalla
    old_login_sig = "private fun handleAutoLogin(view: WebView?) {"
    new_login_sig = "private fun handleAutoLogin(view: WebView?, attempt: Int = 0) {"
    text = replace_exact(text, old_login_sig, new_login_sig, "MainActivity: handleAutoLogin yritysparametri", path)

    old_login_retry = "mainHandler.postDelayed({ handleAutoLogin(view) }, 300L)"
    new_login_retry = "if (attempt < 15) { mainHandler.postDelayed({ handleAutoLogin(view, attempt + 1) }, 300L) }"
    text = replace_exact(text, old_login_retry, new_login_retry, "MainActivity: handleAutoLogin max 15 yritystä", path)

    # 1b. Debounce setupCalendarCleanup MutationObserveriin
    old_cal_obs = """                const obs = new MutationObserver(() => {
                    runCalendarCleanup();
                });"""
    new_cal_obs = """                let cleanupTimer = null;
                const obs = new MutationObserver(() => {
                    if (cleanupTimer) clearTimeout(cleanupTimer);
                    cleanupTimer = setTimeout(() => { runCalendarCleanup(); }, 80);
                });"""
    text = replace_exact(text, old_cal_obs, new_cal_obs, "MainActivity: setupCalendarCleanup 80ms debounce", path)

    # 1c. Varmista navigateToTab-korutiinin peruutus heti kutsun alussa
    old_nav = """        navigateJob?.cancel()
        startSnapshotTransition {
            navigateJob = scope.launch {"""
    new_nav = """        navigateJob?.cancel()
        val currentNavToken = ++navigationToken
        startSnapshotTransition {
            if (currentNavToken != navigationToken) return@startSnapshotTransition
            navigateJob?.cancel()
            navigateJob = scope.launch {"""
    text = replace_exact(text, old_nav, new_nav, "MainActivity: navigateToTab kilpa-ajon esto", path)

    if text != orig:
        backup_file(path)
        path.write_text(text, encoding="utf-8")
        return True
    return False


def patch_background_auth_helper(path: Path) -> bool:
    orig = path.read_text(encoding="utf-8")
    text = orig

    old_cookie_fn = """    private fun persistUpdatedCookies(url: String, conn: HttpURLConnection) {
        val cm = CookieManager.getInstance()"""
    new_cookie_fn = """    private fun persistUpdatedCookies(url: String, conn: HttpURLConnection) = synchronized(cookieSyncLock) {
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

    if "btnRevert.setOnClickListener" in text and "btnRevert.isEnabled = false" not in text:
        pattern = re.compile(
            r'(btnRevert\.setOnClickListener\s*\{\s*)'
            r'(val ok = revertSingleChange\(context, item\)\s*'
            r'dialog\.dismiss\(\)\s*'
            r'Toast\.makeText\([^\n]+\)\.show\(\)\s*'
            r'if \(ok\) \{\s*showManageChangesDialog\(context, onAllReverted\)\s*\})',
            re.MULTILINE
        )
        m = pattern.search(text)
        if m:
            replacement = (
                "btnRevert.setOnClickListener {\n"
                "                btnRevert.isEnabled = false\n"
                "                kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {\n"
                "                    val ok = revertSingleChange(context, item)\n"
                "                    kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {\n"
                "                        dialog.dismiss()\n"
                '                        Toast.makeText(context, if (ok) "Muutos peruttu" else "Peruminen epäonnistui", Toast.LENGTH_SHORT).show()\n'
                "                        if (ok) {\n"
                "                            showManageChangesDialog(context, onAllReverted)\n"
                "                        }\n"
                "                    }\n"
                "                }"
            )
            text = text[:m.start()] + replacement + text[m.end():]
            print("  [PÄIVITETTY] CalendarChangeTracker: revertSingleChange taustasäikeeseen")
        else:
            print("  [OHITETTU] CalendarChangeTracker: revertSingleChange-lohko poikkesi odotetusta")

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
            dirs[:] = [d for d in dirs if d not in {".git", ".gradle", "build", ".idea", ".patch_backups"}]
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
    print("Peruminen Gitissä: git checkout -- .  (tai: python3 patch.py --revert)")
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
