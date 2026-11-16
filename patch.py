#!/usr/bin/env python3
import os
import re
import sys

def find_main_activity():
    for root, dirs, files in os.walk("."):
        if "MainActivity.kt" in files:
            return os.path.join(root, "MainActivity.kt")
    return None

def patch_main_activity(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original_content = content

    # 1. Päivitetään getBaseUrl()
    old_get_base_url = re.compile(
        r'private\s+fun\s+getBaseUrl\(\)\s*:\s*String\s*\{.*?
\s*\}',
        re.DOTALL
    )
    new_get_base_url = """private fun getBaseUrl(): String {
        return UrlNormalizer.getSavedBaseUrl(this)
    }"""

    if old_get_base_url.search(content):
        content = old_get_base_url.sub(new_get_base_url, content, count=1)
        print("[OK] getBaseUrl() päivitetty.")
    else:
        print("[VAROITUS] getBaseUrl()-metodia ei löytynyt.")

    # 2. Päivitetään navigateToTab()-metodin URL-osoitteen muodostus ja tyhjän osoitteen tarkistus
    old_nav_else = re.compile(
        r'\}\s*else\s*\{\s*val\s+baseUrl\s*=\s*getBaseUrl\(\)\s*val\s+url\s*=\s*when\s*\(tab\)\s*\{.*?\}\s*webView\.loadUrl\(url\)\s*\}',
        re.DOTALL
    )
    new_nav_else = """} else {
            val baseUrl = getBaseUrl()
            if (baseUrl.isEmpty()) {
                endBlurTransition()
                Toast.makeText(this, "Aseta ensin organisaatiotunnus asetuksista", Toast.LENGTH_LONG).show()
                btnNavSettings.performClick()
                return
            }
            val url = when (tab) {
                Tab.STAMP -> "$baseUrl/WorktimeStamping"
                Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
                Tab.SHIFTS -> "$baseUrl/Calendar/Month"
            }
            webView.loadUrl(url)
        }"""

    if old_nav_else.search(content):
        content = old_nav_else.sub(new_nav_else, content, count=1)
        print("[OK] navigateToTab() päivitetty tyhjän organisaatiotunnuksen tarkistuksella.")
    else:
        print("[VAROITUS] navigateToTab() else-lohkoa ei löytynyt odotetussa muodossa.")

    # 3. Päivitetään handleAutoLogin() suojaamaan erikoismerkit
    old_auto_login = re.compile(
        r'private\s+fun\s+handleAutoLogin\(\)\s*\{.*?webView\.evaluateJavascript\(js,\s*null\)\s*\}',
        re.DOTALL
    )
    new_auto_login = """private fun handleAutoLogin() {
        val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val user = (prefs.getString("username", "") ?: "").replace("\\", "\\\\").replace("'", "\\'")
        val pass = (prefs.getString("password", "") ?: "").replace("\\", "\\\\").replace("'", "\\'")
        if (user.isEmpty() || pass.isEmpty()) return

        val js = """
            (function() {
                var u = document.getElementById('Username');
                var p = document.getElementById('Password');
                var f = document.getElementById('LoginForm');
                if (u && p && f && u.value === '') {
                    u.value = '$user';
                    p.value = '$pass';
                    f.submit();
                }
            })();
        """.trimIndent()
        webView.evaluateJavascript(js, null)
    }"""

    if old_auto_login.search(content):
        content = old_auto_login.sub(new_auto_login, content, count=1)
        print("[OK] handleAutoLogin() päivitetty erikoismerkkien suojauksella.")
    else:
        print("[VAROITUS] handleAutoLogin()-metodia ei löytynyt.")

    # Varmistetaan Toast-import
    if "import android.widget.Toast" not in content:
        content = content.replace(
            "import android.os.Bundle",
            "import android.os.Bundle
import android.widget.Toast",
            1
        )
        print("[OK] Lisätty import android.widget.Toast.")

    if content != original_content:
        backup_path = filepath + ".bak"
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(original_content)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[VALMIS] Muutokset tallennettu tiedostoon: {filepath} (varmuuskopio: {backup_path})")
    else:
        print("[EI MUUTOKSIA] Tiedostoa ei muutettu.")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else find_main_activity()
    if not target or not os.path.exists(target):
        print("Virhe: MainActivity.kt-tiedostoa ei löytynyt. Anna polku argumenttina: python3 patch.py polku/MainActivity.kt")
        sys.exit(1)
    patch_main_activity(target)
