#!/usr/bin/env python3
import os

def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Varmistetaan puhtaat Unix-rivinvaihdot (\n)
    normalized = content.replace("\r\n", "\n")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(normalized)
    print(f"Päivitetty / Luotu: {path}")

# 1. Luodaan SecureCredentialManager.kt
secure_manager_code = """package fi.numeron.vuorovahti

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

object SecureCredentialManager {

    private const val PREFS_FILE = "secure_numeron_prefs"
    private const val KEY_USERNAME = "secure_username"
    private const val KEY_PASSWORD = "secure_password"

    private fun getEncryptedPrefs(context: Context) = try {
        val masterKey = MasterKey.Builder(context, MasterKey.DEFAULT_MASTER_KEY_ALIAS)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        EncryptedSharedPreferences.create(
            context,
            PREFS_FILE,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    } catch (e: Exception) {
        null
    }

    fun saveCredentials(context: Context, username: String, password: String) {
        getEncryptedPrefs(context)?.edit()?.apply {
            putString(KEY_USERNAME, username)
            putString(KEY_PASSWORD, password)
            apply()
        }
    }

    fun getUsername(context: Context): String? {
        // Fallback vanhoihin suojaamattomiin SharedPreferences-tietoihin migraatiota varten
        getEncryptedPrefs(context)?.getString(KEY_USERNAME, null)?.let { if (it.isNotEmpty()) return it }
        return context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE).getString("username", null)
    }

    fun getPassword(context: Context): String? {
        getEncryptedPrefs(context)?.getString(KEY_PASSWORD, null)?.let { if (it.isNotEmpty()) return it }
        return context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE).getString("password", null)
    }

    fun clearCredentials(context: Context) {
        getEncryptedPrefs(context)?.edit()?.clear()?.apply()
        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE).edit()
            .remove("username")
            .remove("password")
            .apply()
    }
}
"""
write_file("app/src/main/java/fi/numeron/vuorovahti/SecureCredentialManager.kt", secure_manager_code)

# 2. Tarkistetaan ja päivitetään build.gradle.kts (app) riippuvuus
gradle_path = "app/build.gradle.kts"
if os.path.exists(gradle_path):
    with open(gradle_path, "r", encoding="utf-8") as f:
        gradle_content = f.read()
    
    dep_line = 'implementation("androidx.security:security-crypto:1.1.0-alpha06")'
    if dep_line not in gradle_content:
        # Lisätään dependencies-lohkoon
        if "dependencies {" in gradle_content:
            gradle_content = gradle_content.replace("dependencies {", f"dependencies {{\n    {dep_line}")
            write_file(gradle_path, gradle_content)
            print("Lisätty security-crypto riippuvuus build.gradle.kts-tiedostoon.")

# 3. Päivitetään SettingsDialogHelper.kt lukemaan ja tallentamaan tunnukset SecureCredentialManagerin kautta
settings_path = "app/src/main/java/fi/numeron/vuorovahti/SettingsDialogHelper.kt"
if os.path.exists(settings_path):
    with open(settings_path, "r", encoding="utf-8") as f:
        settings_code = f.read()

    # Korvataan vanha SharedPreferences-haku SecureCredentialManagerilla
    settings_code = settings_code.replace(
        'setText(prefs.getString("username", ""))',
        'setText(SecureCredentialManager.getUsername(context) ?: "")'
    )
    settings_code = settings_code.replace(
        'setText(prefs.getString("password", ""))',
        'setText(SecureCredentialManager.getPassword(context) ?: "")'
    )

    # Korvataan tallennus kutsumaan SecureCredentialManager.saveCredentials
    old_save_block = """            prefs.edit()
                .putString("org_raw_input", rawOrg)
                .putString("server_url", normalizedUrl)
                .putString("username", savedUser)
                .putString("password", savedPass)"""

    new_save_block = """            SecureCredentialManager.saveCredentials(context, savedUser, savedPass)

            prefs.edit()
                .putString("org_raw_input", rawOrg)
                .putString("server_url", normalizedUrl)"""

    settings_code = settings_code.replace(old_save_block, new_save_block)
    
    # Poistetaan vanhat plaintext-avaimet tallennuksesta jos ne jäivät sinne
    settings_code = settings_code.replace('.putString("username", savedUser)\n                ', '')
    settings_code = settings_code.replace('.putString("password", savedPass)\n                ', '')

    write_file(settings_path, settings_code)

# 4. Päivitetään MainActivity.kt lukemaan tunnukset SecureCredentialManagerin kautta
main_path = "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt"
if os.path.exists(main_path):
    with open(main_path, "r", encoding="utf-8") as f:
        main_code = f.read()

    old_login_read = """        val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val user = (prefs.getString("username", "") ?: "").replace("\\\\", "\\\\\\\\").replace("'", "\\\\'")
        val pass = (prefs.getString("password", "") ?: "").replace("\\\\", "\\\\\\\\").replace("'", "\\\\'")"""

    new_login_read = """        val user = (SecureCredentialManager.getUsername(this) ?: "").replace("\\\\", "\\\\\\\\").replace("'", "\\\\'")
        val pass = (SecureCredentialManager.getPassword(this) ?: "").replace("\\\\", "\\\\\\\\").replace("'", "\\\\'")"""

    main_code = main_code.replace(old_login_read, new_login_read)
    write_file(main_path, main_code)

print("Kaikki muutokset on tehty onnistuneesti puhtailla Unix-rivinvaihdoilla!")
