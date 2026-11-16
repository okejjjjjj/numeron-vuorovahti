#!/usr/bin/env python3
import os
import re

def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    normalized = content.replace("\r\n", "\n")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(normalized)
    print(f"Päivitetty: {path}")

main_path = "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt"
if os.path.exists(main_path):
    with open(main_path, "r", encoding="utf-8") as f:
        code = f.read()

    # 1. Päivitetään handleAutoLogin käyttämään regexiä (varmasti osuu kohdilleen)
    pattern_login = r'private fun handleAutoLogin\(\) \{.*?\n    \}'
    new_handle_login = """private fun handleAutoLogin() {
        val user = (SecureCredentialManager.getUsername(this) ?: "").replace("\\\\", "\\\\\\\\").replace("'", "\\\\'")
        val pass = (SecureCredentialManager.getPassword(this) ?: "").replace("\\\\", "\\\\").replace("'", "\\\\'")
        if (user.isEmpty() || pass.isEmpty()) return

        val js = \"\"\"
            (function() {
                // Klikataan evästehyväksyntä pois tieltä jos löytyy
                var cookieBtn = Array.from(document.querySelectorAll('button, a')).find(el => el.innerText.includes('Hyväksy'));
                if (cookieBtn) { cookieBtn.click(); }

                var u = document.getElementById('Username');
                var p = document.getElementById('Password');
                var f = document.getElementById('LoginForm');
                if (u && p && f) {
                    u.value = '$user';
                    p.value = '$pass';
                    u.dispatchEvent(new Event('input', { bubbles: true }));
                    p.dispatchEvent(new Event('input', { bubbles: true }));
                    f.submit();
                    return 'SUBMITTED';
                }
                return 'WAITING';
            })();
        \"\"\".trimIndent()

        webView.evaluateJavascript(js) { res ->
            if (res?.contains("WAITING") == true) {
                webView.postDelayed({ handleAutoLogin() }, 300L)
            }
        }
    }"""

    if re.search(pattern_login, code, re.DOTALL):
        code = re.sub(pattern_login, new_handle_login, code, flags=re.DOTALL)
        print("handleAutoLogin päivitetty onnistuneesti.")
    else:
        print("Virhe: handleAutoLogin-metodia ei löytynyt.")

    # 2. Varmistetaan, että splash-peittokuva on päällä kirjautumisen ajan onPageFinished-vaiheessa
    old_branch = 'url.contains("/Login/Login", ignoreCase = true) -> handleAutoLogin()'
    new_branch = '''url.contains("/Login/Login", ignoreCase = true) -> {
                        startSnapshotTransition()
                        handleAutoLogin()
                    }'''

    if old_branch in code:
        code = code.replace(old_branch, new_branch)
        print("Kirjautumisen splash-ohjaus päivitetty.")

    write_file(main_path, code)
    print("MainActivity.kt korjattu valmiiksi!")
