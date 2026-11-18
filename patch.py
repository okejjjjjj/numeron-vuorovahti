#!/usr/bin/env python3
import pathlib
import sys

def find_file(candidates):
    for c in candidates:
        p = pathlib.Path(c)
        if p.exists():
            return p
    return None

def main():
    main_act_path = find_file([
        "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt",
        "MainActivity.kt",
        "MainActivity.kt.txt"
    ])
    if not main_act_path:
        print("Virhe: MainActivity.kt-tiedostoa ei löytynyt.", file=sys.stderr)
        sys.exit(1)

    content = main_act_path.read_text(encoding="utf-8")
    original = content

    # 1. Poistetaan mahdollinen virheellisesti leimaussivulle lisätty toivotus
    shift_greeting_block = """                // === LISÄTTÄVÄT PÄIVÄNTOIVOTUKSET TYÖVUOROILLE ===
                (function addShiftGreeting() {
                    var container = document.querySelector('.punching-shift-container');
                    if (!container || document.getElementById('numeron-login-greeting')) return;
                    var hour = new Date().getHours();
                    var greeting = "Hyvää työpäivää!";
                    if (hour < 10) greeting = "Hyvää huomenta, mukavaa työvirettä!";
                    else if (hour >= 14 && hour < 20) greeting = "Hyvää iltapäivää, jaksuja vuoroon!";
                    else if (hour >= 20 || hour < 4) greeting = "Hyvää iltaa ja tsemppiä vuoroon!";

                    var greetDiv = document.createElement('div');
                    greetDiv.id = 'numeron-login-greeting';
                    greetDiv.style.cssText = 'font-size:13px;color:#38BDF8;font-weight:600;margin-bottom:8px;padding:6px 10px;background:#111923;border:1px solid #2A394A;border-radius:8px;';
                    greetDiv.textContent = '✨ ' + greeting;
                    container.insertBefore(greetDiv, container.firstChild);
                })();"""
    content = content.replace(shift_greeting_block, "")

    # 2. Varmistetaan että kirjautumisnäytön toivotus on mukana (lisätään injectDarkTheme-metodiin ennen view?.evaluateJavascript)
    login_greeting_js = """
                // === PÄIVÄNTOIVOTUS KIRJAUTUMISNÄKYMÄÄN ===
                if (window.location.pathname.toLowerCase().indexOf('/login') !== -1) {
                    var blurBox = document.querySelector('.blurbox h1') || document.querySelector('.whitebox');
                    if (blurBox && !document.getElementById('numeron-login-greeting')) {
                        var hour = new Date().getHours();
                        var greeting = "Hyvää päivää!";
                        if (hour < 10) greeting = "Hyvää huomenta!";
                        else if (hour >= 14 && hour < 20) greeting = "Hyvää iltapäivää!";
                        else if (hour >= 20 || hour < 4) greeting = "Hyvää iltaa!";

                        var greetDiv = document.createElement('div');
                        greetDiv.id = 'numeron-login-greeting';
                        greetDiv.style.cssText = 'text-align:center;font-size:16px;color:#38BDF8;font-weight:600;margin-bottom:14px;padding:8px;background:#182332;border:1px solid #2A394A;border-radius:10px;';
                        greetDiv.textContent = '✨ ' + greeting + ' Tervetuloa Vuorovahtiin';
                        blurBox.parentNode.insertBefore(greetDiv, blurBox);
                    }
                }
    """

    target_pattern = "view?.evaluateJavascript(js, null)"
    if target_pattern in content and "numeron-login-greeting" not in content:
        content = content.replace(target_pattern, login_greeting_js + "\n        " + target_pattern, 1)

    if content != original:
        main_act_path.write_text(content, encoding="utf-8")
        print(f"Päivitetty tiedosto onnistuneesti: {main_act_path}")
    else:
        print("Ei muutoksia tehty.")

if __name__ == "__main__":
    main()
