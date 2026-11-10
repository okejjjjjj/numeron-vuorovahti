import pathlib, re

d = pathlib.Path("app/src/main/java/fi/oma/numeron")

def read_k(name):
    return (d / name).read_text(encoding="utf-8")

def write_k(name, content):
    (d / name).write_text(content, encoding="utf-8")
    print(f"Päivitetty: {name}")

# ---------------------------------------------------------
# 1. SettingsActivity.kt: poista vain istuntoevästeet testissä
# ---------------------------------------------------------
sa = read_k("SettingsActivity.kt")
if "cookieManager.removeAllCookies" in sa:
    sa = sa.replace("cookieManager.removeAllCookies", "cookieManager.removeSessionCookies")
    write_k("SettingsActivity.kt", sa)

# ---------------------------------------------------------
# 2. SettingsManager.kt: turvallinen Demo-URL
# ---------------------------------------------------------
sm = read_k("SettingsManager.kt")
if "demo_shifts.html" not in sm:
    sm = sm.replace(
        "fun getBaseUrl(context: Context): String {",
        'fun getBaseUrl(context: Context): String {\n        if (VuorovahtiHelper.isDemoMode(getUsername(context), getPassword(context))) return "file:///android_asset/demo_shifts.html"'
    )
    write_k("SettingsManager.kt", sm)

# ---------------------------------------------------------
# 3. ShiftAlarmReceiver.kt: kiinteä reqCode
# ---------------------------------------------------------
sar = read_k("ShiftAlarmReceiver.kt")
if "val reqCode = (System.currentTimeMillis() / 1000L).toInt()" in sar:
    sar = sar.replace(
        "val reqCode = (System.currentTimeMillis() / 1000L).toInt()",
        "val reqCode = if (isEnding) 2002 else 1001"
    )
    write_k("ShiftAlarmReceiver.kt", sar)

# ---------------------------------------------------------
# 4. MainActivity.kt
# ---------------------------------------------------------
ma = read_k("MainActivity.kt")

# Korjataan edellisen ajon rikkomat rivinvaihdot merkkijonojen sisällä
ma = ma.replace(
    'text = "[$badgeText]$dateStr  klo $timeStr\n$title"',
    r'text = "[$badgeText]$dateStr  klo $timeStr\n$title"'
)
ma = re.sub(
    r'!\["\n\r\]\*',
    r'[^\\n\\r]*',
    ma
)

# Poistetaan vanha suora scheduleShiftAlarms-kutsu saveWorkShiftistä
ma = re.sub(r'^\s*scheduleShiftAlarms\(.*\)\n', '', ma, flags=re.M)

# Korjataan taustasynkan tyhjä taulukko oikeaksi soluluvuksi
old_silent_call = 'AndroidSilentBridge.onSilentData("[]", document.body ? document.body.innerText : "", window.location.href);'
new_silent_call = 'var cells=[]; var tds=document.querySelectorAll("td"); for(var j=0;j<tds.length;j++){var td=tds[j]; var cls=(td.className||"").toLowerCase(); if(/week|vk|wk/.test(cls)) continue; cells.push({text:(td.innerText||"").trim(), isOther:/other|old|new|disabled|off|outside|gray|grey/.test(cls), extra:""});} AndroidSilentBridge.onSilentData(JSON.stringify(cells), document.body ? document.body.innerText : "", window.location.href);'
if old_silent_call in ma:
    ma = ma.replace(old_silent_call, new_silent_call)

# Lisätään JSONObject- ja AlertDialog-importit jos puuttuvat
if "import org.json.JSONObject" not in ma:
    ma = ma.replace(
        "import org.json.JSONArray",
        "import org.json.JSONArray\nimport org.json.JSONObject\nimport android.app.AlertDialog\nimport android.content.ContentUris"
    )

# Lisätään muutoslistan tallennusmuuttuja MainActivityyn
if "private val syncChangesList" not in ma:
    ma = ma.replace(
        "private val syncedDatesInBatch = mutableSetOf<LocalDate>()",
        "private data class SyncChangeItem(val eventId: Long, val type: String, val dateStr: String, val timeStr: String, val title: String)\n    private val syncChangesList = mutableListOf<SyncChangeItem>()\n    private val syncedDatesInBatch = mutableSetOf<LocalDate>()"
    )

# Nollataan syncChangesList aina kun syncedDatesInBatch nollataan (vain jos ei ole jo lisätty)
if "syncChangesList.clear()" not in ma:
    ma = ma.replace(
        "syncedDatesInBatch.clear()",
        "syncedDatesInBatch.clear()\n            syncChangesList.clear()"
    )

# A) Päivitetään insertEvent palauttamaan Long? ja varmistamaan väri
old_insert = r"""    private fun insertEvent(calId: Long, title: String, loc: String, desc: String, sMs: Long, eMs: Long, allDay: Boolean, startHour: Int = 8) {
        val v = ContentValues().apply {
            put(CalendarContract.Events.DTSTART, sMs); put(CalendarContract.Events.DTEND, eMs)
            put(CalendarContract.Events.TITLE, title); put(CalendarContract.Events.EVENT_LOCATION, loc)
            put(CalendarContract.Events.DESCRIPTION, desc); put(CalendarContract.Events.CALENDAR_ID, calId)
            put(CalendarContract.Events.ALL_DAY, if (allDay) 1 else 0)
            put(CalendarContract.Events.EVENT_TIMEZONE, if (allDay) "UTC" else ZoneId.systemDefault().id)
            VuorovahtiHelper.applyShiftColor(this, if (allDay) "Loma" else desc.ifEmpty { title }, startHour)
        }
        try {
            
