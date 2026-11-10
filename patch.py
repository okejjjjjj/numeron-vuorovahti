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
# 4. MainActivity.kt:
#    - Turhan scheduleShiftAlarms-kutsun poisto
#    - Taustasynkan soluluku kuntoon
#    - A) Värikoodauksen varmistus (myös uudelleensynkassa)
#    - B) Klikattava ilmoitus + Yhteenvetoikkuna (Peruuta / Muokkaa)
# ---------------------------------------------------------
ma = read_k("MainActivity.kt")

# Poistetaan vanha suora scheduleShiftAlarms-kutsu saveWorkShiftistä
ma = re.sub(r'^\s*scheduleShiftAlarms\(.*\)\n', '', ma, flags=re.M)

# Korjataan taustasynkan tyhjä taulukko oikeaksi soluluvuksi
old_silent_call = 'AndroidSilentBridge.onSilentData("[]", document.body ? document.body.innerText : "", window.location.href);'
new_silent_call = 'var cells=[]; var tds=document.querySelectorAll("td"); for(var j=0;j<tds.length;j++){var td=tds[j]; var cls=(td.className||"").toLowerCase(); if(/week|vk|wk/.test(cls)) continue; cells.push({text:(td.innerText||"").trim(), isOther:/other|old|new|disabled|off|outside|gray|grey/.test(cls), extra:""});} AndroidSilentBridge.onSilentData(JSON.stringify(cells), document.body ? document.body.innerText : "", window.location.href);'
if old_silent_call in ma:
    ma = ma.replace(old_silent_call, new_silent_call)

# Lisätään JSONObject- ja AlertDialog-importit jos puuttuvat
if "import org.json.JSONObject" not in ma:
    ma = ma.replace("import org.json.JSONArray", "import org.json.JSONArray\nimport org.json.JSONObject\nimport android.app.AlertDialog\nimport android.content.ContentUris")

# Lisätään muutoslistan tallennusmuuttuja MainActivityyn
if "private val syncChangesList" not in ma:
    ma = ma.replace(
        "private val syncedDatesInBatch = mutableSetOf<LocalDate>()",
        "private data class SyncChangeItem(val eventId: Long, val type: String, val dateStr: String, val timeStr: String, val title: String)\n    private val syncChangesList = mutableListOf<SyncChangeItem>()\n    private val syncedDatesInBatch = mutableSetOf<LocalDate>()"
    )

# Nollataan syncChangesList aina kun syncedDatesInBatch nollataan
ma = ma.replace(
    "syncedDatesInBatch.clear()",
    "syncedDatesInBatch.clear()\n            syncChangesList.clear()"
)

# A) Päivitetään insertEvent palauttamaan Long? (luodun tapahtuman ID) ja varmistamaan väri
old_insert = """    private fun insertEvent(calId: Long, title: String, loc: String, desc: String, sMs: Long, eMs: Long, allDay: Boolean, startHour: Int = 8) {
        val v = ContentValues().apply {
            put(CalendarContract.Events.DTSTART, sMs); put(CalendarContract.Events.DTEND, eMs)
            put(CalendarContract.Events.TITLE, title); put(CalendarContract.Events.EVENT_LOCATION, loc)
            put(CalendarContract.Events.DESCRIPTION, desc); put(CalendarContract.Events.CALENDAR_ID, calId)
            put(CalendarContract.Events.ALL_DAY, if (allDay) 1 else 0)
            put(CalendarContract.Events.EVENT_TIMEZONE, if (allDay) "UTC" else ZoneId.systemDefault().id)
            VuorovahtiHelper.applyShiftColor(this, if (allDay) "Loma" else desc.ifEmpty { title }, startHour)
        }
        try {
            contentResolver.insert(CalendarContract.Events.CONTENT_URI, v)
        } catch (_: Exception) {
            v.remove(CalendarContract.Events.EVENT_COLOR)
            contentResolver.insert(CalendarContract.Events.CONTENT_URI, v)
        }
    }"""

new_insert = """    private fun applyColorWithFallback(v: ContentValues, calId: Long, label: String, startHour: Int) {
        val targetColor = VuorovahtiHelper.getShiftEventColor(label, startHour)
        v.put(CalendarContract.Events.EVENT_COLOR, targetColor)
        try {
            var accountName = ""
            var accountType = ""
            contentResolver.query(
                CalendarContract.Calendars.CONTENT_URI,
                arrayOf(CalendarContract.Calendars.ACCOUNT_NAME, CalendarContract.Calendars.ACCOUNT_TYPE),
                "${CalendarContract.Calendars._ID} = ?",
                arrayOf(calId.toString()),
                null
            )?.use { c ->
                if (c.moveToFirst()) {
                    accountName = c.getString(0) ?: ""
                    accountType = c.getString(1) ?: ""
                }
            }
            if (accountName.isNotEmpty() && accountType.isNotEmpty()) {
                var bestKey: String? = null
                var bestDist = Int.MAX_VALUE
                val r1 = Color.red(targetColor); val g1 = Color.green(targetColor); val b1 = Color.blue(targetColor)
                contentResolver.query(
                    CalendarContract.Colors.CONTENT_URI,
                    arrayOf(CalendarContract.Colors.COLOR_KEY, CalendarContract.Colors.COLOR),
                    "${CalendarContract.Colors.ACCOUNT_NAME} = ? AND ${CalendarContract.Colors.ACCOUNT_TYPE} = ? AND ${CalendarContract.Colors.COLOR_TYPE} = ?",
                    arrayOf(accountName, accountType, CalendarContract.Colors.TYPE_EVENT.toString()),
                    null
                )?.use { cc ->
                    while (cc.moveToNext()) {
                        val key = cc.getString(0) ?: continue
                        val col = cc.getInt(1)
                        val dist = (r1 - Color.red(col)) * (r1 - Color.red(col)) +
                                   (g1 - Color.green(col)) * (g1 - Color.green(col)) +
                                   (b1 - Color.blue(col)) * (b1 - Color.blue(col))
                        if (dist < bestDist) {
                            bestDist = dist
                            bestKey = key
                        }
                    }
                }
                if (bestKey != null) {
                    v.put(CalendarContract.Events.EVENT_COLOR_KEY, bestKey)
                }
            }
        } catch (_: Exception) {}
    }

    private fun insertEvent(calId: Long, title: String, loc: String, desc: String, sMs: Long, eMs: Long, allDay: Boolean, startHour: Int = 8): Long? {
        val colorLabel = if (allDay) "Loma" else desc.ifEmpty { title }
        val v = ContentValues().apply {
            put(CalendarContract.Events.DTSTART, sMs); put(CalendarContract.Events.DTEND, eMs)
            put(CalendarContract.Events.TITLE, title); put(CalendarContract.Events.EVENT_LOCATION, loc)
            put(CalendarContract.Events.DESCRIPTION, desc); put(CalendarContract.Events.CALENDAR_ID, calId)
            put(CalendarContract.Events.ALL_DAY, if (allDay) 1 else 0)
            put(CalendarContract.Events.EVENT_TIMEZONE, if (allDay) "UTC" else ZoneId.systemDefault().id)
            applyColorWithFallback(this, calId, colorLabel, startHour)
        }
        return try {
            contentResolver.insert(CalendarContract.Events.CONTENT_URI, v)?.lastPathSegment?.toLongOrNull()
        } catch (_: Exception) {
            v.remove(CalendarContract.Events.EVENT_COLOR_KEY)
            try {
                contentResolver.insert(CalendarContract.Events.CONTENT_URI, v)?.lastPathSegment?.toLongOrNull()
            } catch (_: Exception) {
                v.remove(CalendarContract.Events.EVENT_COLOR)
                contentResolver.insert(CalendarContract.Events.CONTENT_URI, v)?.lastPathSegment?.toLongOrNull()
            }
        }
    }"""

if old_insert in ma:
    ma = ma.replace(old_insert, new_insert)

# Päivitetään saveWorkShift, updateEvent ja reconcileRemovedShifts tallentamaan muutokset ja varmistamaan värit
old_save_update = """            if (exId == null) {
                insertEvent(calId, "Työvuoro", loc, desc, sMs, eMs, false, sDt.hour)
                true
            } else {
                updateEvent(exId, loc, desc, sMs, eMs, sDt.hour)
            }
        } catch (e: Exception) { false }
    }"""

new_save_update = """            if (exId == null) {
                val newId = insertEvent(calId, "Työvuoro", loc, desc, sMs, eMs, false, sDt.hour)
                if (newId != null) {
                    syncChangesList.add(SyncChangeItem(newId, "ADDED", dateStr, "$startStr - $endStr", desc.ifEmpty { "Työvuoro" }))
                }
                newId != null
            } else {
                val updated = updateEvent(calId, exId, loc, desc, sMs, eMs, sDt.hour)
                if (updated) {
                    syncChangesList.add(SyncChangeItem(exId, "UPDATED", dateStr, "$startStr - $endStr", desc.ifEmpty { "Työvuoro" }))
                }
                updated
            }
        } catch (e: Exception) { false }
    }"""

if old_save_update in ma:
    ma = ma.replace(old_save_update, new_save_update)

old_update_fn = """    private fun updateEvent(eventId: Long, loc: String, desc: String, sMs: Long, eMs: Long, startHour: Int): Boolean {
        var curLoc = ""
        var curDesc = ""
        var curStart = 0L
        var curEnd = 0L
        contentResolver.query(
            CalendarContract.Events.CONTENT_URI,
            arrayOf(CalendarContract.Events.EVENT_LOCATION, CalendarContract.Events.DESCRIPTION, CalendarContract.Events.DTSTART, CalendarContract.Events.DTEND),
            "${CalendarContract.Events._ID} = ?",
            arrayOf(eventId.toString()),
            null
        )?.use {
            if (it.moveToFirst()) {
                curLoc = it.getString(0) ?: ""
                curDesc = it.getString(1) ?: ""
                curStart = it.getLong(2)
                curEnd = it.getLong(3)
            }
        }
        val timeChanged = (curStart != sMs || curEnd != eMs)
        val textChanged = (loc.isNotEmpty() && (curLoc != loc || curDesc != desc))
        if (!timeChanged && !textChanged) return false

        val v = ContentValues().apply {
            put(CalendarContract.Events.DTSTART, sMs)
            put(CalendarContract.Events.DTEND, eMs)
            if (loc.isNotEmpty()) put(CalendarContract.Events.EVENT_LOCATION, loc)
            if (desc.isNotEmpty()) put(CalendarContract.Events.DESCRIPTION, desc)
            VuorovahtiHelper.applyShiftColor(this, desc.ifEmpty { "Työvuoro" }, startHour)
        }
        return try {
            contentResolver.update(CalendarContract.Events.CONTENT_URI, v, "${CalendarContract.Events._ID} = ?", arrayOf(eventId.toString())) > 0
        } catch (_: Exception) {
            v.remove(CalendarContract.Events.EVENT_COLOR)
            contentResolver.update(CalendarContract.Events.CONTENT_URI, v, "${CalendarContract.Events._ID} = ?", arrayOf(eventId.toString())) > 0
        }
    }"""

new_update_fn = """    private fun updateEvent(calId: Long, eventId: Long, loc: String, desc: String, sMs: Long, eMs: Long, startHour: Int): Boolean {
        var curLoc = ""
        var curDesc = ""
        var curStart = 0L
        var curEnd = 0L
        var curColor = 0
        contentResolver.query(
            CalendarContract.Events.CONTENT_URI,
            arrayOf(CalendarContract.Events.EVENT_LOCATION, CalendarContract.Events.DESCRIPTION, CalendarContract.Events.DTSTART, CalendarContract.Events.DTEND, CalendarContract.Events.EVENT_COLOR),
            "${CalendarContract.Events._ID} = ?",
            arrayOf(eventId.toString()),
            null
        )?.use {
            if (it.moveToFirst()) {
                curLoc = it.getString(0) ?: ""
                curDesc = it.getString(1) ?: ""
                curStart = it.getLong(2)
                curEnd = it.getLong(3)
                curColor = if (!it.isNull(4)) it.getInt(4) else 0
            }
        }
        val targetColor = VuorovahtiHelper.getShiftEventColor(desc.ifEmpty { "Työvuoro" }, startHour)
        val timeChanged = (curStart != sMs || curEnd != eMs)
        val textChanged = (loc.isNotEmpty() && (curLoc != loc || curDesc != desc))
        val colorMissing = (curColor != targetColor)

        if (!timeChanged && !textChanged && !colorMissing) return false

        val v = ContentValues().apply {
            put(CalendarContract.Events.DTSTART, sMs)
            put(CalendarContract.Events.DTEND, eMs)
            if (loc.isNotEmpty()) put(CalendarContract.Events.EVENT_LOCATION, loc)
            if (desc.isNotEmpty()) put(CalendarContract.Events.DESCRIPTION, desc)
            applyColorWithFallback(this, calId, desc.ifEmpty { "Työvuoro" }, startHour)
        }
        try {
            contentResolver.update(CalendarContract.Events.CONTENT_URI, v, "${CalendarContract.Events._ID} = ?", arrayOf(eventId.toString()))
        } catch (_: Exception) {
            v.remove(CalendarContract.Events.EVENT_COLOR_KEY)
            try {
                contentResolver.update(CalendarContract.Events.CONTENT_URI, v, "${CalendarContract.Events._ID} = ?", arrayOf(eventId.toString()))
            } catch (_: Exception) {
                v.remove(CalendarContract.Events.EVENT_COLOR)
                contentResolver.update(CalendarContract.Events.CONTENT_URI, v, "${CalendarContract.Events._ID} = ?", arrayOf(eventId.toString()))
            }
        }
        return timeChanged || textChanged
    }"""

if old_update_fn in ma:
    ma = ma.replace(old_update_fn, new_update_fn)

# Tallennetaan myös poistetut vuorot yhteenvetoon reconcileRemovedShifts-funktiossa
old_reconcile_query = """            contentResolver.query(
                CalendarContract.Events.CONTENT_URI,
                arrayOf(CalendarContract.Events._ID, CalendarContract.Events.DTSTART, CalendarContract.Events.DTEND),
                sel,
                args,
                null
            )?.use { c ->
                while (c.moveToNext()) {
                    val id = c.getLong(0)
                    val sMs = c.getLong(1)
                    val eMs = c.getLong(2)
                    if (sMs > now && !syncedShiftRangesInBatch.contains(Pair(sMs, eMs))) {
                        idsToDelete.add(id)
                    }
                }
            }"""

new_reconcile_query = """            val timeFmt = DateTimeFormatter.ofPattern("HH:mm")
            val dateStr = "${date.dayOfMonth}.${date.monthValue}.${date.year}"
            contentResolver.query(
                CalendarContract.Events.CONTENT_URI,
                arrayOf(CalendarContract.Events._ID, CalendarContract.Events.DTSTART, CalendarContract.Events.DTEND, CalendarContract.Events.DESCRIPTION),
                sel,
                args,
                null
            )?.use { c ->
                while (c.moveToNext()) {
                    val id = c.getLong(0)
                    val sMs = c.getLong(1)
                    val eMs = c.getLong(2)
                    val desc = c.getString(3) ?: "Työvuoro"
                    if (sMs > now && !syncedShiftRangesInBatch.contains(Pair(sMs, eMs))) {
                        idsToDelete.add(id)
                        val sStr = Instant.ofEpochMilli(sMs).atZone(zone).toLocalTime().format(timeFmt)
                        val eStr = Instant.ofEpochMilli(eMs).atZone(zone).toLocalTime().format(timeFmt)
                        syncChangesList.add(SyncChangeItem(id, "REMOVED", dateStr, "$sStr - $eStr", desc.ifEmpty { "Työvuoro" }))
                    }
                }
            }"""

if old_reconcile_query in ma:
    ma = ma.replace(old_reconcile_query, new_reconcile_query)

# B) Päivitetään sendNewShiftsAddedNotification klikattavaksi + rakennetaan showSyncSummaryDialog
old_notif_fn = """    private fun sendNewShiftsAddedNotification(addedCount: Int) {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channelId = "numeron_list_channel"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(NotificationChannel(channelId, "Uudet työvuorolistat", NotificationManager.IMPORTANCE_HIGH))
        }
        val notif = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(R.drawable.ic_launcher)
            .setSubText("Numeron Vuorovahti")
            .setContentTitle("Uudet työvuorot päivitetty!")
            .setContentText("Kalenteriin vietiin $addedCount uutta tai muuttunutta työvuoroa/lomaa.")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .build()
        nm.notify(3004, notif)
    }"""

new_notif_fn = """    private fun saveSyncChangesHistory() {
        val arr = JSONArray()
        for (item in syncChangesList) {
            val obj = JSONObject().apply {
                put("eventId", item.eventId)
                put("type", item.type)
                put("dateStr", item.dateStr)
                put("timeStr", item.timeStr)
                put("title", item.title)
            }
            arr.put(obj)
        }
        getSharedPreferences("vuorovahti_prefs", Context.MODE_PRIVATE)
            .edit()
            .putString("last_sync_changes_json", arr.toString())
            .apply()
    }

    private fun sendNewShiftsAddedNotification(addedCount: Int) {
        saveSyncChangesHistory()
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channelId = "numeron_list_channel"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(NotificationChannel(channelId, "Uudet työvuorolistat", NotificationManager.IMPORTANCE_HIGH))
        }
        val summaryIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra("OPEN_SYNC_SUMMARY", true)
        }
        val pi = PendingIntent.getActivity(
            this, 3004, summaryIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val removedTxt = if (totalRemovedInBatch > 0) ", poistettu $totalRemovedInBatch" else ""
        val notif = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(R.drawable.ic_launcher)
            .setSubText("Numeron Vuorovahti")
            .setContentTitle("Uudet työvuorot päivitetty!")
            .setContentText("Lisätty/muutettu $addedCount$removedTxt. Napauta tarkistaaksesi tai muokataksesi.")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()
        nm.notify(3004, notif)
    }

    private fun showSyncSummaryDialog() {
        val rawJson = getSharedPreferences("vuorovahti_prefs", Context.MODE_PRIVATE)
            .getString("last_sync_changes_json", "[]") ?: "[]"
        val arr = try { JSONArray(rawJson) } catch (_: Exception) { JSONArray() }

        val dp = { v: Int -> (v * resources.displayMetrics.density).toInt() }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(14))
            setBackgroundColor(Color.parseColor("#0F172A"))
        }

        root.addView(TextView(this).apply {
            text = "Viimeisimmän synkronoinnin muutokset"
            textSize = 18f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#38BDF8"))
            setPadding(0, 0, 0, dp(6))
        })

        root.addView(TextView(this).apply {
            text = "Voit muokata merkintää kalenterissa tai kumota yksittäisen lisäyksen."
            textSize = 12.5f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, 0, 0, dp(12))
        })

        val scroll = ScrollView(this).apply {
            layoutParams = LinearLayout.LayoutParams(-1, 0, 1f)
        }
        val listCol = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }

        if (arr.length() == 0) {
            listCol.addView(TextView(this).apply {
                text = "Ei tallennettuja yksittäisiä vuoromuutoksia viimeisimmässä erässä."
                textSize = 13.5f
                setTextColor(Color.parseColor("#CBD5E1"))
                setPadding(0, dp(12), 0, dp(12))
            })
        } else {
            for (i in 0 until arr.length()) {
                val obj = arr.getJSONObject(i)
                val evId = obj.optLong("eventId", -1L)
                val type = obj.optString("type", "ADDED")
                val dateStr = obj.optString("dateStr", "")
                val timeStr = obj.optString("timeStr", "")
                val title = obj.optString("title", "Työvuoro")

                val badgeText = when (type) {
                    "UPDATED" -> "MUUTETTU"
                    "REMOVED" -> "POISTETTU"
                    else -> "UUSI"
                }
                val badgeColor = when (type) {
                    "UPDATED" -> "#FB8C00"
                    "REMOVED" -> "#EF4444"
                    else -> "#10B981"
                }

                val itemCard = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    setPadding(dp(14), dp(12), dp(14), dp(12))
                    layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) }
                    background = GradientDrawable().apply {
                        cornerRadius = dp(12).toFloat()
                        setColor(Color.parseColor("#1E293B"))
                        setStroke(dp(1), Color.parseColor("#334155"))
                    }
                }

                val infoText = TextView(this).apply {
                    text = "[$badgeText]  $dateStr  klo $timeStr\n$title"
                    textSize = 13.5f
                    setTypeface(null, Typeface.BOLD)
                    setTextColor(Color.parseColor(badgeColor))
                }
                itemCard.addView(infoText)

                if (type != "REMOVED" && evId > 0L) {
                    val actRow = LinearLayout(this).apply {
                        orientation = LinearLayout.HORIZONTAL
                        gravity = Gravity.END
                        setPadding(0, dp(8), 0, 0)
                    }

                    val btnEdit = Button(this).apply {
                        text = "Muokkaa"
                        isAllCaps = false
                        textSize = 12f
                        setTextColor(Color.WHITE)
                        background = GradientDrawable().apply {
                            cornerRadius = dp(8).toFloat()
                            setColor(Color.parseColor("#0284C7"))
                        }
                        minHeight = 0; minimumHeight = 0
                        setPadding(dp(12), dp(6), dp(12), dp(6))
                        layoutParams = LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(8) }
                        setOnClickListener {
                            try {
                                val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, evId)
                                startActivity(Intent(Intent.ACTION_EDIT).apply { data = uri })
                            } catch (_: Exception) {
                                try {
                                    val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, evId)
                                    startActivity(Intent(Intent.ACTION_VIEW).apply { data = uri })
                                } catch (_: Exception) {}
                            }
                        }
                    }

                    val btnDelete = Button(this).apply {
                        text = "Peruuta / Poista"
                        isAllCaps = false
                        textSize = 12f
                        setTextColor(Color.WHITE)
                        background = GradientDrawable().apply {
                            cornerRadius = dp(8).toFloat()
                            setColor(Color.parseColor("#991B1B"))
                        }
                        minHeight = 0; minimumHeight = 0
                        setPadding(dp(12), dp(6), dp(12), dp(6))
                        setOnClickListener {
                            contentResolver.delete(
                                CalendarContract.Events.CONTENT_URI,
                                "${CalendarContract.Events._ID} = ?",
                                arrayOf(evId.toString())
                            )
                            VuorovahtiHelper.ensureRemindersFromCalendar(this@MainActivity)
                            VuorovahtiHelper.triggerConfirmHaptics(window.decorView)
                            infoText.text = "[PERUTTU]  $dateStr  klo $timeStr — Poistettu kalenterista"
                            infoText.setTextColor(Color.parseColor("#64748B"))
                            actRow.visibility = View.GONE
                        }
                    }

                    actRow.addView(btnEdit)
                    actRow.addView(btnDelete)
                    itemCard.addView(actRow)
                }

                listCol.addView(itemCard)
            }
        }

        scroll.addView(listCol)
        root.addView(scroll)

        val dlg = AlertDialog.Builder(this)
            .setView(root)
            .create()

        val btnCloseDlg = Button(this).apply {
            text = "Sulje"
            isAllCaps = false
            textSize = 14f
            setTextColor(Color.WHITE)
            background = GradientDrawable().apply {
                cornerRadius = dp(10).toFloat()
                setColor(Color.parseColor("#334155"))
            }
            layoutParams = LinearLayout.LayoutParams(-1, dp(44)).apply { topMargin = dp(10) }
            setOnClickListener { dlg.dismiss() }
        }
        root.addView(btnCloseDlg)
        dlg.show()
    }"""

if old_notif_fn in ma:
    ma = ma.replace(old_notif_fn, new_notif_fn)

# Kutsutaan sendNewShiftsAddedNotification myös jos vuoroja on poistettu, ja tallennetaan muutoslista aina
ma = ma.replace(
    "if (totalAddedInBatch > 0) sendNewShiftsAddedNotification(totalAddedInBatch)",
    "saveSyncChangesHistory()\n                              if (totalAddedInBatch > 0 || totalRemovedInBatch > 0) sendNewShiftsAddedNotification(totalAddedInBatch)"
)

# Avataan yhteenvetoikkuna kun ilmoitusta klikataan (handleIncomingIntent)
if "OPEN_SYNC_SUMMARY" not in ma:
    ma = ma.replace(
        'if (intent?.getBooleanExtra("AUTO_SYNC_NEW_LIST", false) == true) {',
        'if (intent?.getBooleanExtra("OPEN_SYNC_SUMMARY", false) == true) {\n            intent.removeExtra("OPEN_SYNC_SUMMARY")\n            webView.postDelayed({ showSyncSummaryDialog() }, 350)\n        }\n        if (intent?.getBooleanExtra("AUTO_SYNC_NEW_LIST", false) == true) {'
    )

write_k("MainActivity.kt", ma)
