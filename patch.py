import pathlib, re

d = pathlib.Path("app/src/main/java/fi/oma/numeron")
ma_path = d / "MainActivity.kt"
ma = ma_path.read_text(encoding="utf-8")

# 1. Estetään tarpeettomat poistot: reconcileRemovedShifts poistaa vuoroja 
# vain jos synkronoituja päiviä löytyi vähintään 5 (suojaa vajailta taustapakeilta)
old_reconcile_check = "private fun reconcileRemovedShifts(calId: Long): Int {"
new_reconcile_check = """private fun reconcileRemovedShifts(calId: Long): Int {
        if (syncedDatesInBatch.size < 5) return 0"""
if old_reconcile_check in ma and "syncedDatesInBatch.size < 5" not in ma:
    ma = ma.replace(old_reconcile_check, new_reconcile_check)

# 2. Varmistetaan, että ilmoituksen klikkaus (OPEN_SYNC_SUMMARY) avaa varmasti yhteenvedon
# riippumatta siitä, milloin MainActivity herää taustalta.
old_intent_check = 'if (intent?.getBooleanExtra("OPEN_SYNC_SUMMARY", false) == true) {'
new_intent_check = """if (intent?.getBooleanExtra("OPEN_SYNC_SUMMARY", false) == true || getIntent().getBooleanExtra("OPEN_SYNC_SUMMARY", false) == true) {
            intent?.removeExtra("OPEN_SYNC_SUMMARY")
            getIntent().removeExtra("OPEN_SYNC_SUMMARY")
            webView.postDelayed({ showSyncSummaryDialog() }, 500)"""

if old_intent_check in ma:
    ma = ma.replace(old_intent_check, new_intent_check)
elif "OPEN_SYNC_SUMMARY" in ma:
    # Jos tarkistus on jo olemassa, varmistetaan että se käyttää postDelayed-viivettä
    ma = ma.replace(
        'if (intent?.getBooleanExtra("OPEN_SYNC_SUMMARY", false) == true) {\n            intent.removeExtra("OPEN_SYNC_SUMMARY")\n            showSyncSummaryDialog()\n        }',
        new_intent_check + "\n        }"
    )

ma_path.write_text(ma, encoding="utf-8")
print("patch.py päivitetty onnistuneesti!")
