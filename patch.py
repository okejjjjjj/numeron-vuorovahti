import pathlib, re

ma_path = pathlib.Path("app/src/main/java/fi/oma/numeron/MainActivity.kt")
ma = ma_path.read_text(encoding="utf-8")

# ---------------------------------------------------------
# 1. Suurennetaan alarivin navigointipainikkeet
# ---------------------------------------------------------
old_nav_btn = "\n".join([
    '        fun createNavButton(label: String, weight: Float = 1f, action: () -> Unit): Button {',
    '            return Button(this).apply {',
    '                text = label',
    '                textSize = 11.5f',
    '                setTextColor(Color.WHITE)',
    '                isAllCaps = false',
    '                setPadding(6, 8, 6, 8)',
    '                minHeight = 0',
    '                minimumHeight = 0',
    '                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, weight).apply {',
    '                    marginStart = 5',
    '                    marginEnd = 5',
    '                }',
    '                setOnClickListener { action() }',
    '            }',
    '        }'
])

new_nav_btn = "\n".join([
    '        fun createNavButton(label: String, weight: Float = 1f, action: () -> Unit): Button {',
    '            return Button(this).apply {',
    '                text = label',
    '                textSize = 13.5f',
    '                setTextColor(Color.WHITE)',
    '                isAllCaps = false',
    '                setPadding(12, 32, 12, 32)',
    '                minHeight = 0',
    '                minimumHeight = 0',
    '                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, weight).apply {',
    '                    marginStart = 6',
    '                    marginEnd = 6',
    '                }',
    '                setOnClickListener { action() }',
    '            }',
    '        }'
])

if old_nav_btn in ma:
    ma = ma.replace(old_nav_btn, new_nav_btn)

# Levennetään hieman Asetukset- ja Sulje-nappeja, jotta ne eivät ole liian kapeita
ma = ma.replace('createNavButton("⚙", 0.55f)', 'createNavButton("⚙", 0.68f)')
ma = ma.replace('createNavButton("✕", 0.55f)', 'createNavButton("✕", 0.68f)')

# ---------------------------------------------------------
# 2. 9 viikon kelaus & Numeronin priorisointi kalenterin yli
# ---------------------------------------------------------
ma = ma.replace("pagesRemainingToSync = 3", "pagesRemainingToSync = 8")
ma = ma.replace("pagesRemainingToSync = if (isDemoActive) 0 else 3", "pagesRemainingToSync = if (isDemoActive) 0 else 8")

# Estetään kuukausiruudukkoa lisäämästä reunasoluja poistolistalle
ma = re.sub(
    r'(private fun processDayContent\([^\n]+\n)\s*try \{ syncedDatesInBatch\.add\(LocalDate\.of\(y, m, d\)\) \} catch \(_: Exception\) \{\}\n',
    r'\1',
    ma
)

# Luettelonäkymässä (parseListView) merkitään viikon päivät tarkistetuiksi aina kun sivulla on
# täysi viikko (matches.size >= 5), jolloin myös kokonaan vapaaksi muuttuneen viikon vanhat vuorot poistuvat
old_found_guard = "if (found > 0) {\n                for (i in matches.indices) {"
new_found_guard = "if (matches.size >= 5 || found > 0) {\n                for (i in matches.indices) {"
ma = ma.replace(old_found_guard, new_found_guard)

# Jos edellinen patch ei vielä siirtänyt syncedDatesInBatch-lisäystä parseListViewiin, tehdään se nyt:
if "if (matches.size >= 5 || found > 0)" not in ma:
    ma = re.sub(
        r'(private fun processListBlock\([^\n]+\n)\s*try \{ syncedDatesInBatch\.add\(LocalDate\.of\(y, m, d\)\) \} catch \(_: Exception\) \{\}\n',
        r'\1',
        ma
    )
    old_loop = "\n".join([
        '                val res = processListBlock(calId, d, mo, yr, pageText.substring(sIdx, eIdx).trim(), fmt, vacationDays)',
        '                found += res.first; added += res.second',
        '            }',
        '            added += saveGroupedVacations(calId, vacationDays)',
        '            if (found > 0) return Pair(found, added)'
    ])
    new_loop = "\n".join([
        '                val res = processListBlock(calId, d, mo, yr, pageText.substring(sIdx, eIdx).trim(), fmt, vacationDays)',
        '                found += res.first; added += res.second',
        '            }',
        '            if (matches.size >= 5 || found > 0) {',
        '                for (i in matches.indices) {',
        '                    val m = matches[i]',
        '                    val d = (m.groupValues[1].ifEmpty { m.groupValues[4] }).toIntOrNull() ?: continue',
        '                    val mo = (m.groupValues[2].ifEmpty { m.groupValues[5] }).toIntOrNull() ?: continue',
        '                    val rawYr = (m.groupValues[3].ifEmpty { m.groupValues[6] }).toIntOrNull()',
        '                    val yr = rawYr ?: if (mo < LocalDate.now().monthValue - 1 && LocalDate.now().monthValue >= 10) LocalDate.now().year + 1 else if (targetMonth == 12 && mo == 1) targetYear + 1 else if (targetMonth == 1 && mo == 12) targetYear - 1 else targetYear',
        '                    try { syncedDatesInBatch.add(LocalDate.of(yr, mo, d)) } catch (_: Exception) {}',
        '                }',
        '            }',
        '            added += saveGroupedVacations(calId, vacationDays)',
        '            if (found > 0) return Pair(found, added)'
    ])
    ma = ma.replace(old_loop, new_loop)

# Varmistetaan että updateEvent pakottaa aina myös otsikon "Työvuoro", jos joku on muokannut sitä kalenterissa
if 'put(CalendarContract.Events.TITLE, "Työvuoro")' not in ma:
    ma = ma.replace(
        "val v = ContentValues().apply {\n            put(CalendarContract.Events.DTSTART, sMs)",
        'val v = ContentValues().apply {\n            put(CalendarContract.Events.TITLE, "Työvuoro")\n            put(CalendarContract.Events.DTSTART, sMs)'
    )

# ---------------------------------------------------------
# 3. Taustasynkan välitön lopetus jos istunto on vanhentunut
# ---------------------------------------------------------
old_bg_client = 'if (u.contains("/Calendar/", ignoreCase = true) && !u.contains("login", ignoreCase = true)) {'
new_bg_client = """if (u.contains("login", ignoreCase = true) || u.contains("auth", ignoreCase = true)) {
                              cleanupSilentSync()
                              return
                          }
                          if (u.contains("/Calendar/", ignoreCase = true)) {"""
if old_bg_client in ma:
    ma = ma.replace(old_bg_client, new_bg_client)

# ---------------------------------------------------------
# 4. Yhteenvetoikkunan & ilmoituksen varmistus
# ---------------------------------------------------------
if "private var pendingSummaryDialog = false" not in ma:
    ma = ma.replace(
        "private var pendingAutoStamp = false",
        "private var pendingSummaryDialog = false\n    private var pendingAutoStamp = false"
    )

ma = re.sub(
    r'if \(intent\?\.getBooleanExtra\("OPEN_SYNC_SUMMARY", false\) == true[^\{]*\{[^\}]*\}',
    'if (intent?.getBooleanExtra("OPEN_SYNC_SUMMARY", false) == true) {\n            intent.removeExtra("OPEN_SYNC_SUMMARY")\n            pendingSummaryDialog = true\n        }',
    ma
)

if "if (pendingSummaryDialog)" not in ma:
    ma = ma.replace(
        "super.onResume()",
        "super.onResume()\n        if (pendingSummaryDialog) {\n            pendingSummaryDialog = false\n            webView.postDelayed({ showSyncSummaryDialog() }, 300)\n        }"
    )

ma_path.write_text(ma, encoding="utf-8")
print("MainActivity.kt paivitetty!")

# ---------------------------------------------------------
# 5. AndroidManifest.xml: Näytönkäännön kestävyys (ei kaada dialogia)
# ---------------------------------------------------------
manifest_path = pathlib.Path("app/src/main/AndroidManifest.xml")
if manifest_path.exists():
    mf = manifest_path.read_text(encoding="utf-8")
    if 'android:name=".MainActivity"' in mf and 'android:configChanges=' not in mf:
        mf = mf.replace(
            'android:name=".MainActivity"',
            'android:name=".MainActivity"\n            android:configChanges="orientation|screenSize|keyboardHidden"'
        )
        manifest_path.write_text(mf, encoding="utf-8")
        print("AndroidManifest.xml paivitetty!")

# ---------------------------------------------------------
# 6. gradle.properties: Hiljennetään compileSdk=36 varoitus
# ---------------------------------------------------------
gp_path = pathlib.Path("gradle.properties")
gp = gp_path.read_text(encoding="utf-8") if gp_path.exists() else ""
if "android.suppressUnsupportedCompileSdk=36" not in gp:
    gp = gp.rstrip() + "\nandroid.suppressUnsupportedCompileSdk=36\n"
    gp_path.write_text(gp, encoding="utf-8")
    print("gradle.properties paivitetty!")
