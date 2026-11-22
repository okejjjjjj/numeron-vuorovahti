#!/usr/bin/env python3
"""
Numeron Vuorovahti – Akunkulutuksen optimointipatch.

Peruttavissa Gitissä:
  git revert HEAD
  tai: git checkout -- .
  tai: python3 patch.py --revert

Toteutetaan ilman uusia ulkoisia riippuvuuksia (ei kotlinx.coroutines-lisäyksiä
tiedostoihin, joissa sitä ei entuudestaan ole), jotta kääntäminen on varmaa.

Optimoinnit:
1. MainActivity.kt:
   - onPause() / onResume(): WebView.onPause() + pauseTimers() taustalle mentäessä
     ja resumeTimers() + onResume() palattaessa (katkaisee JS-ajastimet ja
     renderöinnin, kun ruutu ei ole näkyvissä).
   - injectDarkTheme(): suojataan samalle URL:lle toistuvalta injektoinnilta
     (onPageCommitVisible + onPageFinished ajoivat raskaan skriptin kahdesti
     jokaisella sivulatauksella).
   - setupCalendarCleanup(): lisätään 80 ms debounce MutationObserveriin, ettei
     jokainen yksittäinen DOM-muutos aja koko kuukausitaulukon läpikäyntiä.
   - handleAutoLogin(): 15 yrityksen yläraja (estää ikuisen 300 ms silmukan).
   - navigateToTab(): varmistetaan vanhan korutiinin peruutus siirtymän sisällä.
2. BackgroundAuthHelper.kt:
   - ensureAuthenticatedSession(): lisätään lyhyt muistivälimuisti (90 s) ja
     lukitus, jotta peräkkäiset tai rinnakkaiset kutsut eivät tee turhaa
     GET + POST + CookieManager.flush() -verkkokierrosta.
   - persistUpdatedCookies(): synkronoidaan cookieSyncLock-lukolla.
3. CalendarChangeTracker.kt:
   - btnRevert: ajetaan levytallennus ja kalenteri-I/O taustasäikeessä
     (Executors.newSingleThreadExecutor) ja päivitetään UI pääsäikeessä.
4. build.gradle(.kts):
   - nostetaan versionCode-arvoa yhdellä (+1).
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

    # 1. Lisätään apukenttä toistuvan teemainjektoinnin välttämiseksi samalla sivulatauksella
    old_field = "    private var isAutoSubmittingLogin: Boolean = false"
    new_field = """    private var isAutoSubmittingLogin: Boolean = false
    private var lastThemedUrl: String? = null
    private var lastThemedAtMs: Long = 0L"""
    text = replace_exact(text, old_field, new_field, "MainActivity: lastThemedUrl-välimuistikentät", path)

    # 2. Nollataan teemavälimuisti uuden sivun alkaessa
    old_page_started = """            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                super.onPageStarted(view, url, favicon)
                startSnapshotTransition()
            }"""
    new_page_started = """            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                super.onPageStarted(view, url, favicon)
                lastThemedUrl = null
                startSnapshotTransition()
            }"""
    text = replace_exact(text, old_page_started, new_page_started, "MainActivity: nollaa lastThemedUrl onPageStartedissa", path)

    # 3. Estetään saman sivun turha tuplainjektointi (onPageCommitVisible + onPageFinished)
    old_inject_sig = '    private fun injectDarkTheme(view: WebView?) {\n        val css = """'
    new_inject_sig = (
        '    private fun injectDarkTheme(view: WebView?) {\n'
        '        val currentUrl = view?.url\n'
        '        val nowMs = System.currentTimeMillis()\n'
        '        if (!currentUrl.isNullOrEmpty() && currentUrl == lastThemedUrl && (nowMs - lastThemedAtMs) < 1500L) {\n'
        '            return\n'
        '        }\n'
        '        lastThemedUrl = currentUrl\n'
        '        lastThemedAtMs = nowMs\n'
        '        val css = """'
    )
    text = replace_exact(text, old_inject_sig, new_inject_sig, "MainActivity: estä injectDarkTheme-tupla-ajo", path)

    # 4. 80 ms debounce kalenterin MutationObserveriin
    old_cal_obs = """                        var calObs = new MutationObserver(function() {
                            runCalendarCleanup();
                        });"""
    new_cal_obs = """                        var calCleanupTimer = null;
                        var calObs = new MutationObserver(function() {
                            if (calCleanupTimer) clearTimeout(calCleanupTimer);
                            calCleanupTimer = setTimeout(function() { runCalendarCleanup(); }, 80);
                        });"""
    text = replace_exact(text, old_cal_obs, new_cal_obs, "MainActivity: setupCalendarCleanup 80ms debounce", path)

    # 5. handleAutoLogin max 15 yritystä
    old_login_sig = "private fun handleAutoLogin() {"
    new_login_sig = "private fun handleAutoLogin(attempt: Int = 0) {"
    text = replace_exact(text, old_login_sig, new_login_sig, "MainActivity: handleAutoLogin yritysparametri", path)

    old_login_retry = "webView.postDelayed({ handleAutoLogin() }, 300L)"
    new_login_retry = "if (attempt < 15) { webView.postDelayed({ handleAutoLogin(attempt + 1) }, 300L) }"
    text = replace_exact(text, old_login_retry, new_login_retry, "MainActivity: handleAutoLogin max 15 yritystä", path)

    # 6. navigateToTab vanhan korutiinin varmistettu peruutus
    old_nav = """            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition
                val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)"""
    new_nav = """            startSnapshotTransition {
                if (token != navigationToken) return@startSnapshotTransition
                navigateJob?.cancel()
                val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)"""
    text = replace_exact(text, old_nav, new_nav, "MainActivity: navigateToTab varmista vanhan jobin peruutus", path)

    # 7. WebView'n pysäytys taustalle mentäessä (säästää CPU:ta ja akkua)
    old_destroy = """    override fun onDestroy() {"""
    new_lifecycle = """    override fun onPause() {
        try {
            webView.onPause()
            webView.pauseTimers()
        } catch (_: Exception) {}
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        try {
            webView.resumeTimers()
            webView.onResume()
        } catch (_: Exception) {}
    }

    override fun onDestroy() {"""
    text = replace_exact(text, old_destroy, new_lifecycle, "MainActivity: onPause/onResume WebView-virransäästö", path)

    if text != orig:
        backup_file(path)
        path.write_text(text, encoding="utf-8")
        return True
    return False


def patch_background_auth_helper(path: Path) -> bool:
    orig = path.read_text(encoding="utf-8")
    text = orig

    # 1. Estetään turhat peräkkäiset kirjautumiskierrokset 90 sekunnin sisällä onnistuneesta
    old_lock = "    private val cookieSyncLock = Any()"
    new_lock = """    private val cookieSyncLock = Any()
    @Volatile
    private var lastAuthSuccessMs: Long = 0L
    @Volatile
    private var lastAuthBaseUrl: String = "" """.rstrip()
    text = replace_exact(text, old_lock, new_lock, "BackgroundAuthHelper: sessiovälimuistin kentät", path)

    old_ensure_start = """        if (baseUrl.isBlank() || username.isBlank() || password.isBlank()) {
            return@withContext false
        }"""
    new_ensure_start = """        if (baseUrl.isBlank() || username.isBlank() || password.isBlank()) {
            return@withContext false
        }

        val nowMs = System.currentTimeMillis()
        val cachedCookies = try {
            CookieManager.getInstance().getCookie(baseUrl)
        } catch (_: Exception) {
            null
        }
        if (!cachedCookies.isNullOrBlank() &&
            baseUrl == lastAuthBaseUrl &&
            (nowMs - lastAuthSuccessMs) < 90_000L
        ) {
            return@withContext true
        }"""
    text = replace_exact(text, old_ensure_start, new_ensure_start, "BackgroundAuthHelper: ohita turha uusintakirjautuminen (90s)", path)

    old_ensure_end = """            cm.flush()

            true"""
    new_ensure_end = """            cm.flush()
            lastAuthBaseUrl = baseUrl
            lastAuthSuccessMs = System.currentTimeMillis()

            true"""
    text = replace_exact(text, old_ensure_end, new_ensure_end, "BackgroundAuthHelper: päivitä lastAuthSuccessMs", path)

    # 2. Synkronoidaan rinnakkaisten pyyntöjen evästepäivitykset
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
                    java.util.concurrent.Executors.newSingleThreadExecutor().execute {
                        val ok = revertSingleChangeAndSave(context, item)
                        android.os.Handler(android.os.Looper.getMainLooper()).post {
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
    print("Käynnistetään Numeron Vuorovahti -akkuoptimointipatch...")
    ensure_gitignore_entry(".patch_backups/")

    targets = [
        ("MainActivity.kt", patch_main_activity),
        ("BackgroundAuthHelper.kt", patch_background_auth_helper),
        ("CalendarChangeTracker.kt", patch_calendar_change_tracker),
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
    parser = argparse.ArgumentParser(description="Numeron Vuorovahti akkuoptimointipatch")
    parser.add_argument("--revert", action="store_true", help="Palauta alkuperäiset tiedostot varmuuskopioista")
    args = parser.parse_args()
    if args.revert:
        return revert_all()
    return apply_all()


if __name__ == "__main__":
    sys.exit(main())
