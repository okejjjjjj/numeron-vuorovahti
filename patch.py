import pathlib, re

print("Aloitetaan Master Patchin ajaminen...")

# =========================================================
# 1. MAINACTIVITY: KÄYTTÖLIITTYMÄ & SYNKKALOGIIKKA
# =========================================================
ma_path = pathlib.Path("app/src/main/java/fi/oma/numeron/MainActivity.kt")
if ma_path.exists():
    ma = ma_path.read_text(encoding="utf-8")

    # 1.1 Suurennetaan napit
    old_nav_btn = 'textSize = 11.5f\n                setTextColor(Color.WHITE)\n                isAllCaps = false\n                setPadding(6, 8, 6, 8)'
    new_nav_btn = 'textSize = 13.5f\n                setTextColor(Color.WHITE)\n                isAllCaps = false\n                setPadding(12, 32, 12, 32)'
    ma = ma.replace(old_nav_btn, new_nav_btn)
    ma = ma.replace('createNavButton("⚙", 0.55f)', 'createNavButton("⚙", 0.68f)')
    ma = ma.replace('createNavButton("✕", 0.55f)', 'createNavButton("✕", 0.68f)')

    # 1.2 9 viikon kelaus
    ma = ma.replace("pagesRemainingToSync = 3", "pagesRemainingToSync = 8")
    ma = ma.replace("pagesRemainingToSync = if (isDemoActive) 0 else 3", "pagesRemainingToSync = if (isDemoActive) 0 else 8")

    # 1.3 Tyhjennetään kokonaan vapaat viikot oikein (poistetaan vanha processDayContent catch-lause)
    ma = re.sub(r'(private fun processDayContent\([^\n]+\n)\s*try \{ syncedDatesInBatch\.add\(LocalDate\.of\(y, m, d\)\) \} catch \(_: Exception\) \{\}\n', r'\1', ma)
    if "if (matches.size >= 5 || found > 0)" not in ma:
        ma = re.sub(r'(private fun processListBlock\([^\n]+\n)\s*try \{ syncedDatesInBatch\.add\(LocalDate\.of\(y, m, d\)\) \} catch \(_: Exception\) \{\}\n', r'\1', ma)
        old_loop = '                val res = processListBlock(calId, d, mo, yr, pageText.substring(sIdx, eIdx).trim(), fmt, vacationDays)\n                found += res.first; added += res.second\n            }\n            added += saveGroupedVacations(calId, vacationDays)\n            if (found > 0) return Pair(found, added)'
        new_loop = '                val res = processListBlock(calId, d, mo, yr, pageText.substring(sIdx, eIdx).trim(), fmt, vacationDays)\n                found += res.first; added += res.second\n            }\n            if (matches.size >= 5 || found > 0) {\n                for (i in matches.indices) {\n                    val m = matches[i]\n                    val d = (m.groupValues[1].ifEmpty { m.groupValues[4] }).toIntOrNull() ?: continue\n                    val mo = (m.groupValues[2].ifEmpty { m.groupValues[5] }).toIntOrNull() ?: continue\n                    val rawYr = (m.groupValues[3].ifEmpty { m.groupValues[6] }).toIntOrNull()\n                    val yr = rawYr ?: if (mo < LocalDate.now().monthValue - 1 && LocalDate.now().monthValue >= 10) LocalDate.now().year + 1 else if (targetMonth == 12 && mo == 1) targetYear + 1 else if (targetMonth == 1 && mo == 12) targetYear - 1 else targetYear\n                    try { syncedDatesInBatch.add(LocalDate.of(yr, mo, d)) } catch (_: Exception) {}\n                }\n            }\n            added += saveGroupedVacations(calId, vacationDays)\n            if (found > 0) return Pair(found, added)'
        ma = ma.replace(old_loop, new_loop)

    # 1.4 Työvuoro-otsikon pakotus kalenteriin
    if 'put(CalendarContract.Events.TITLE, "Työvuoro")' not in ma:
        ma = ma.replace('val v = ContentValues().apply {\n            put(CalendarContract.Events.DTSTART, sMs)', 'val v = ContentValues().apply {\n            put(CalendarContract.Events.TITLE, "Työvuoro")\n            put(CalendarContract.Events.DTSTART, sMs)')

    # 1.5 Piilo-WebViewin kirjautumis-ohitus timeoutissa
    old_bg_client = 'if (u.contains("/Calendar/", ignoreCase = true) && !u.contains("login", ignoreCase = true)) {'
    new_bg_client = 'if (u.contains("login", ignoreCase = true) || u.contains("auth", ignoreCase = true)) {\n                              cleanupSilentSync()\n                              return\n                          }\n                          if (u.contains("/Calendar/", ignoreCase = true)) {'
    ma = ma.replace(old_bg_client, new_bg_client)

    # 1.6 Yhteenvetoikkunan lataus intentistä
    if "private var pendingSummaryDialog = false" not in ma:
        ma = ma.replace("private var pendingAutoStamp = false", "private var pendingSummaryDialog = false\n    private var pendingAutoStamp = false")
    ma = re.sub(r'if \(intent\?\.getBooleanExtra\("OPEN_SYNC_SUMMARY", false\) == true[^\{]*\{[^\}]*\}', 'if (intent?.getBooleanExtra("OPEN_SYNC_SUMMARY", false) == true) {\n            intent.removeExtra("OPEN_SYNC_SUMMARY")\n            pendingSummaryDialog = true\n        }', ma)
    if "if (pendingSummaryDialog)" not in ma:
        ma = ma.replace("super.onResume()", "super.onResume()\n        if (pendingSummaryDialog) {\n            pendingSummaryDialog = false\n            webView.postDelayed({ showSyncSummaryDialog() }, 300)\n        }")

    # 1.7 Vanhojen värikutsujen siivous, Importit ja Edge-to-Edge, Ilmoituslupa ja ActionBar piilotus
    ma = re.sub(r'window\.statusBarColor\s*=\s*.*?\n', '', ma)
    ma = re.sub(r'window\.navigationBarColor\s*=\s*.*?\n', '', ma)
    
    if "import androidx.activity.enableEdgeToEdge" not in ma:
        ma = ma.replace("import android.os.Bundle", "import android.os.Bundle\nimport androidx.activity.enableEdgeToEdge\nimport androidx.core.view.ViewCompat\nimport androidx.core.view.WindowInsetsCompat")

    if "enableEdgeToEdge()" not in ma:
        setup_code = """
        enableEdgeToEdge()
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 1002)
            }
        }
        try { supportActionBar?.hide() } catch (_: Exception) {}
        try { actionBar?.hide() } catch (_: Exception) {}
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(android.R.id.content)) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }"""
        ma = re.sub(r'(super\.onCreate\(savedInstanceState\))', rf'\1{setup_code}', ma)

    ma_path.write_text(ma, encoding="utf-8")
    print("MainActivity.kt Master Patch ajettu!")

# =========================================================
# 2. SETTINGSACTIVITY: VERSIONUMERO & PÄIVITYS
# =========================================================
sa_path = pathlib.Path("app/src/main/java/fi/oma/numeron/SettingsActivity.kt")
if sa_path.exists():
    sa = sa_path.read_text(encoding="utf-8")
    if "import com.google.android.play.core.appupdate." not in sa:
        imports = "\nimport com.google.android.play.core.appupdate.AppUpdateManagerFactory\nimport com.google.android.play.core.install.model.UpdateAvailability\nimport android.app.AlertDialog\nimport android.net.Uri\nimport android.content.Intent\n"
        sa = sa.replace("import android.os.Bundle", f"import android.os.Bundle{imports}")
        
    if "AppUpdateManagerFactory.create" not in sa:
        update_code = """
        try {
            val pInfo = packageManager.getPackageInfo(packageName, 0)
            val version = pInfo.versionName
            val rootView = findViewById<android.view.ViewGroup>(android.R.id.content)
            fun updateLabels(v: android.view.View) {
                if (v is android.widget.TextView && v.text.toString().trim().equals("Asetukset", ignoreCase = true)) {
                    v.text = "Asetukset (v$version)"
                } else if (v is android.view.ViewGroup) {
                    for (i in 0 until v.childCount) updateLabels(v.getChildAt(i))
                }
            }
            rootView.post { updateLabels(rootView) }
            
            val appUpdateManager = AppUpdateManagerFactory.create(this)
            appUpdateManager.appUpdateInfo.addOnSuccessListener { info ->
                if (info.updateAvailability() == UpdateAvailability.UPDATE_AVAILABLE) {
                    AlertDialog.Builder(this).setTitle("Päivitys saatavilla!").setMessage("Uusi versio Vuorovahdista on saatavilla.")
                        .setPositiveButton("Päivitä") { _, _ -> startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=$packageName"))) }
                        .setNegativeButton("Myöhemmin", null).show()
                }
            }
        } catch (e: Exception) {}
"""
        sa = re.sub(r'(override fun onCreate\(savedInstanceState: Bundle\?\) \{[^}]+setContentView[^}]+)', rf'\1\n{update_code}', sa)
    sa_path.write_text(sa, encoding="utf-8")
    print("SettingsActivity.kt Master Patch ajettu!")

# =========================================================
# 3. UPDATERECEIVER & MANIFEST: HERÄTYS & LUVAT
# =========================================================
receiver_path = pathlib.Path("app/src/main/java/fi/oma/numeron/UpdateReceiver.kt")
if receiver_path.parent.exists():
    receiver_path.write_text("""package fi.oma.numeron
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
class UpdateReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_MY_PACKAGE_REPLACED || intent.action == Intent.ACTION_BOOT_COMPLETED) {
            try { VuorovahtiHelper.ensureRemindersFromCalendar(context) } catch (e: Exception) {}
        }
    }
}""", encoding="utf-8")

manifest_path = pathlib.Path("app/src/main/AndroidManifest.xml")
if manifest_path.exists():
    mf = manifest_path.read_text(encoding="utf-8")
    if "RECEIVE_BOOT_COMPLETED" not in mf:
        mf = mf.replace("<application", '<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />\n    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />\n    <application')
    if ".UpdateReceiver" not in mf:
        mf = mf.replace("</application>", '    <receiver android:name=".UpdateReceiver" android:exported="true"><intent-filter><action android:name="android.intent.action.MY_PACKAGE_REPLACED" /><action android:name="android.intent.action.BOOT_COMPLETED" /></intent-filter></receiver>\n    </application>')
    if 'android:name=".MainActivity"' in mf and 'android:configChanges=' not in mf:
        mf = mf.replace('android:name=".MainActivity"', 'android:name=".MainActivity"\n            android:configChanges="orientation|screenSize|keyboardHidden"')
    manifest_path.write_text(mf, encoding="utf-8")
    print("AndroidManifest.xml ja UpdateReceiver Master Patch ajettu!")

# =========================================================
# 4. GRADLE & PROGUARD: OBFUSKOINTI, KIRJASTOT & VERSIO
# =========================================================
pg_path = pathlib.Path("app/proguard-rules.pro")
pg_path.write_text("-dontwarn javax.annotation.**\n-dontwarn javax.annotation.concurrent.**\n-keep class fi.oma.numeron.** { *; }\n-keepclassmembers class * { @android.webkit.JavascriptInterface <methods>; }\n", encoding="utf-8")

for file_name in ["app/build.gradle.kts", "app/build.gradle"]:
    gf = pathlib.Path(file_name)
    if gf.exists():
        c = gf.read_text(encoding="utf-8")
        
        c = c.replace("isMinifyEnabled = false", "isMinifyEnabled = true\n            isShrinkResources = true")
        c = c.replace("minifyEnabled false", "minifyEnabled true\n            shrinkResources true")
        if "isMinifyEnabled = true" in c and "proguard-rules.pro" not in c:
            c = c.replace("isMinifyEnabled = true", 'isMinifyEnabled = true\n            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")')
        if "minifyEnabled true" in c and "proguard-rules.pro" not in c:
            c = c.replace("minifyEnabled true", "minifyEnabled true\n            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'")
            
        c = re.sub(r'com\.google\.android\.material:material:1\.\d+\.\d+', 'com.google.android.material:material:1.12.0', c)
        if "com.google.android.play:app-update" not in c:
            c = re.sub(r'(dependencies\s*\{)', r'\1\n    implementation("com.google.android.play:app-update:2.1.0")\n    implementation("com.google.android.play:app-update-ktx:2.1.0")', c)

        vc_match = re.search(r'versionCode(?:\s*=\s*|\s+)(\d+)', c)
        if vc_match:
            new_vc = int(vc_match.group(1)) + 1
            c = re.sub(rf'(versionCode(?:\s*=\s*|\s+)){vc_match.group(1)}\b', rf'\g<1>{new_vc}', c)
            
        vn_match = re.search(r'versionName(?:\s*=\s*|\s+)["\']([^"\']+)["\']', c)
        if vn_match:
            parts = vn_match.group(1).split('.')
            if parts[-1].isdigit():
                parts[-1] = str(int(parts[-1]) + 1)
                c = re.sub(rf'(versionName(?:\s*=\s*|\s+)["\']){vn_match.group(1)}(["\'])', rf'\g<1>{".".join(parts)}\g<2>', c)
                
        gf.write_text(c, encoding="utf-8")
        print("Gradle ja ProGuard Master Patch ajettu!")
