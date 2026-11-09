import pathlib, re

d = pathlib.Path("app/src/main/java/fi/oma/numeron")

def update(filename, old, new):
    p = d / filename
    txt = p.read_text(encoding="utf-8")
    if old in txt:
        p.write_text(txt.replace(old, new), encoding="utf-8")
        print(f"Päivitetty: {filename}")

# 1. SettingsActivity.kt: poista vain istuntoevästeet testissä
update(
    "SettingsActivity.kt",
    "cookieManager.removeAllCookies",
    "cookieManager.removeSessionCookies"
)

# 2. SettingsManager.kt: turvallinen Demo-URL
sm_path = d / "SettingsManager.kt"
sm_txt = sm_path.read_text(encoding="utf-8")
if "demo_shifts.html" not in sm_txt:
    update(
        "SettingsManager.kt",
        "fun getBaseUrl(context: Context): String {",
        'fun getBaseUrl(context: Context): String {\n        if (VuorovahtiHelper.isDemoMode(getUsername(context), getPassword(context))) return "file:///android_asset/demo_shifts.html"'
    )

# 3. ShiftAlarmReceiver.kt: kiinteä reqCode
update(
    "ShiftAlarmReceiver.kt",
    "val reqCode = (System.currentTimeMillis() / 1000L).toInt()",
    "val reqCode = if (isEnding) 2002 else 1001"
)

# 4. MainActivity.kt: turhan tuplahälytyksen poisto & taustasynkan suojaus
ma_path = d / "MainActivity.kt"
ma_txt = ma_path.read_text(encoding="utf-8")
ma_txt = re.sub(r'^\s*scheduleShiftAlarms\(.*\)\n', '', ma_txt, flags=re.M)
ma_txt = ma_txt.replace("var silentPagesLeft = 1", "var silentPagesLeft = 0")
ma_path.write_text(ma_txt, encoding="utf-8")
