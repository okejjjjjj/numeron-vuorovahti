#!/usr/bin/env python3
import os

def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    normalized = content.replace("\r\n", "\n")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(normalized)
    print(f"Päivitetty: {path}")

# Päivitetään DemoModeHelper.kt käyttämään SecureCredentialManageria
demo_helper_path = "app/src/main/java/fi/numeron/vuorovahti/DemoModeHelper.kt"
if os.path.exists(demo_helper_path):
    with open(demo_helper_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Korvataan isDemoEnabled-metodi tarkistamaan salatut tunnukset
    old_method = """    fun isDemoEnabled(context: Context): Boolean {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val org = (prefs.getString("org_raw_input", "") ?: "").trim()
        val serverUrl = (prefs.getString("server_url", "") ?: "").trim()
        val user = (prefs.getString("username", "") ?: "").trim()
        val pass = prefs.getString("password", "") ?: ""

        // Aktivoituu käynnistettäessä, jos tunnuksia ei ole asetettu TAI tunnukset ovat "demo"
        if (user.isEmpty() || pass.isEmpty() || (org.isEmpty() && serverUrl.isEmpty())) {
            return true
        }
        return isDemoCredentials(org.ifEmpty { serverUrl }, user, pass)
    }"""

    new_method = """    fun isDemoEnabled(context: Context): Boolean {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val org = (prefs.getString("org_raw_input", "") ?: "").trim()
        val serverUrl = (prefs.getString("server_url", "") ?: "").trim()
        val user = (SecureCredentialManager.getUsername(context) ?: "").trim()
        val pass = SecureCredentialManager.getPassword(context) ?: ""

        // Aktivoituu käynnistettäessä, jos tunnuksia ei ole asetettu TAI tunnukset ovat "demo"
        if (user.isEmpty() || pass.isEmpty() || (org.isEmpty() && serverUrl.isEmpty())) {
            return true
        }
        return isDemoCredentials(org.ifEmpty { serverUrl }, user, pass)
    }"""

    if old_method in content:
        content = content.replace(old_method, new_method)
        write_file(demo_helper_path, content)
        print("DemoModeHelper.kt päivitetty käyttämään SecureCredentialManageria.")
    else:
        print("Varoitus: isDemoEnabled-metodin rakennetta ei löytynyt täsmällisesti, tarkista DemoModeHelper.kt.")

print("Korjaus valmis!")
