import pathlib, re

# 1. Päivitetään build.gradle -tiedostojen kirjastoriippuvuudet (Material Components & Play Core) ja nostetaan versiota
for file_name in ["app/build.gradle.kts", "app/build.gradle"]:
    gf = pathlib.Path(file_name)
    if gf.exists():
        c = gf.read_text(encoding="utf-8")
        
        # Yritetään päivittää Material Components -kirjasto uudempaan versioon (korjaa vanhentuneet Window-kutsut)
        c = re.sub(r'com\.google\.android\.material:material:1\.\d+\.\d+', 'com.google.android.material:material:1.12.0', c)
        
        # Lisätään Play Core -kirjasto päivitystarkistusta varten, jos ei ole
        if "com.google.android.play:app-update" not in c:
            c = re.sub(
                r'(dependencies\s*\{)', 
                r'\1\n    implementation("com.google.android.play:app-update:2.1.0")\n    implementation("com.google.android.play:app-update-ktx:2.1.0")', 
                c
            )

        # Versionumero ylös
        vc_match = re.search(r'versionCode(?:\s*=\s*|\s+)(\d+)', c)
        if vc_match:
            old_vc = int(vc_match.group(1))
            new_vc = old_vc + 1
            c = re.sub(rf'(versionCode(?:\s*=\s*|\s+)){old_vc}\b', rf'\g<1>{new_vc}', c)
            
        vn_match = re.search(r'versionName(?:\s*=\s*|\s+)["\']([^"\']+)["\']', c)
        if vn_match:
            old_vn = vn_match.group(1)
            parts = old_vn.split('.')
            if parts[-1].isdigit():
                parts[-1] = str(int(parts[-1]) + 1)
                new_vn = ".".join(parts)
                c = re.sub(rf'(versionName(?:\s*=\s*|\s+)["\']){old_vn}(["\'])', rf'\g<1>{new_vn}\g<2>', c)
                
        gf.write_text(c, encoding="utf-8")
        print(f"{file_name} päivitetty (Material, Play Core + versiot).")

# 2. Varmistetaan, ettei MainActivity.kt sisällä vanhentuneita värikutsuja
ma_path = pathlib.Path("app/src/main/java/fi/oma/numeron/MainActivity.kt")
if ma_path.exists():
    ma = ma_path.read_text(encoding="utf-8")
    
    # Poistetaan mahdolliset suorat setStatusBarColor ja setNavigationBarColor -kutsut
    ma = re.sub(r'window\.statusBarColor\s*=\s*.*?\n', '', ma)
    ma = re.sub(r'window\.navigationBarColor\s*=\s*.*?\n', '', ma)
    
    ma_path.write_text(ma, encoding="utf-8")
    print("MainActivity.kt siivottu vanhoista värikutsuista.")

# 3. Luodaan UpdateReceiver.kt (Herättää sovelluksen päivityksen ja boottauksen jälkeen)
receiver_path = pathlib.Path("app/src/main/java/fi/oma/numeron/UpdateReceiver.kt")
receiver_code = """package fi.oma.numeron

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class UpdateReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        // Herätetään sovellus kun se on päivitetty tai puhelin on käynnistetty uudelleen
        if (action == Intent.ACTION_MY_PACKAGE_REPLACED || action == Intent.ACTION_BOOT_COMPLETED) {
            try {
                // Palautetaan leimausmuistutukset takaisin tulille
                VuorovahtiHelper.ensureRemindersFromCalendar(context)
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }
}
"""
if receiver_path.parent.exists():
    receiver_path.write_text(receiver_code, encoding="utf-8")
    print("UpdateReceiver.kt luotu (Automaattinen herätys lisätty)!")

# 4. Lisätään Manifestiin luvat ja uusi taustakuuntelija
manifest_path = pathlib.Path("app/src/main/AndroidManifest.xml")
if manifest_path.exists():
    mf = manifest_path.read_text(encoding="utf-8")
    
    # Lupa käynnistyä puhelimen boottauksen yhteydessä
    if "RECEIVE_BOOT_COMPLETED" not in mf:
        mf = mf.replace("<application", '<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />\n    <application')
        
    # Rekisteröidään uusi UpdateReceiver
    if ".UpdateReceiver" not in mf:
        receiver_xml = """
        <receiver android:name=".UpdateReceiver" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MY_PACKAGE_REPLACED" />
                <action android:name="android.intent.action.BOOT_COMPLETED" />
            </intent-filter>
        </receiver>
        """
        mf = mf.replace("</application>", f"{receiver_xml}\n    </application>")
        
    manifest_path.write_text(mf, encoding="utf-8")
    print("AndroidManifest.xml päivitetty (Luvat ja Receiver)!")

# 5. Injektoidaan versionumero ja päivitystarkistus SettingsActivityyn
sa_path = pathlib.Path("app/src/main/java/fi/oma/numeron/SettingsActivity.kt")
if sa_path.exists():
    sa = sa_path.read_text(encoding="utf-8")
    
    # Importit Google Play Corelle
    if "import com.google.android.play.core.appupdate." not in sa:
        imports = """
import com.google.android.play.core.appupdate.AppUpdateManagerFactory
import com.google.android.play.core.install.model.UpdateAvailability
import android.app.AlertDialog
import android.net.Uri
import android.content.Intent
import android.widget.Toast
"""
        sa = sa.replace("import android.os.Bundle", f"import android.os.Bundle\n{imports}")
        
    # Injektoidaan onCreate-metodiin koodi, joka tarkistaa version ja päivitykset
    if "AppUpdateManagerFactory.create" not in sa:
        update_check_code = """
        // 1. Haetaan nykyinen versionumero ja näytetään se otsikossa
        try {
            val pInfo = packageManager.getPackageInfo(packageName, 0)
            val version = pInfo.versionName
            title = "Asetukset (v$version)"
        } catch (e: Exception) {}

        // 2. Tarkistetaan onko Play Kaupassa uudempaa versiota
        try {
            val appUpdateManager = AppUpdateManagerFactory.create(this)
            val appUpdateInfoTask = appUpdateManager.appUpdateInfo
            appUpdateInfoTask.addOnSuccessListener { appUpdateInfo ->
                if (appUpdateInfo.updateAvailability() == UpdateAvailability.UPDATE_AVAILABLE) {
                    title = "$title - PÄIVITYS SAATAVILLA"
                    AlertDialog.Builder(this)
                        .setTitle("Päivitys saatavilla!")
                        .setMessage("Uudempi versio Numeron Vuorovahdista on saatavilla Play Kaupassa. Haluatko päivittää nyt?")
                        .setPositiveButton("Päivitä") { _, _ ->
                            try {
                                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=$packageName")))
                            } catch (e: Exception) {
                                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=$packageName")))
                            }
                        }
                        .setNegativeButton("Myöhemmin", null)
                        .show()
                }
            }
        } catch (e: Exception) {}
"""
        sa = re.sub(
            r'(override fun onCreate\(savedInstanceState: Bundle\?\) \{[^}]+setContentView[^}]+)',
            rf'\1\n{update_check_code}',
            sa
        )
        sa_path.write_text(sa, encoding="utf-8")
        print("SettingsActivity.kt päivitetty (Versionumero ja automaattinen päivitystarkistus)!")
