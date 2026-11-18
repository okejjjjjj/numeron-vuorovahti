#!/usr/bin/env python3
import pathlib
import sys

def main():
    path = pathlib.Path("app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt")
    if not path.exists():
        matches = list(pathlib.Path(".").rglob("MainActivity.kt"))
        if matches:
            path = matches[0]
        else:
            print("MainActivity.kt ei löytynyt!", file=sys.stderr)
            sys.exit(1)
            
    content = path.read_text(encoding="utf-8")
    
    old_snippet = """                if (!window._forgotStampHelperInstalled) {
                    window._forgotStampHelperInstalled = true;
                    document.addEventListener('click', function(e) {
                        var btn = e.target && e.target.closest('#forgottenStampButton');
                        if (btn) {
                            setTimeout(function() {
                                var panel = document.getElementById('forgotStampPanel');
                                if (panel) {
                                    var topVal = panel.style.top || '';
                                    if (panel.classList.contains('minimized') || !topVal || topVal === '100%') {
                                        panel.classList.remove('minimized');
                                        panel.classList.add('force-open');
                                        panel.style.top = '0px';
                                    }
                                }
                            }, 350);
                        }
                        var cancelBtn = e.target && e.target.closest('#cancelPunchForgottenButton, #cancelPunchForgottenButtonHeader');
                        if (cancelBtn) {
                            var panel = document.getElementById('forgotStampPanel');
                            if (panel) {
                                panel.classList.remove('force-open');
                                panel.classList.add('minimized');
                                panel.style.top = '100%';
                            }
                        }
                    }, true);
                }"""

    new_snippet = """                if (!window._forgotStampHelperInstalled) {
                    window._forgotStampHelperInstalled = true;
                    document.addEventListener('click', function(e) {
                        var btn = e.target && e.target.closest('#forgottenStampButton');
                        if (btn) {
                            var panel = document.getElementById('forgotStampPanel');
                            if (panel) {
                                panel.classList.remove('minimized');
                                panel.classList.add('force-open');
                            }
                        }
                        var cancelBtn = e.target && e.target.closest('#cancelPunchForgottenButton, #cancelPunchForgottenButtonHeader');
                        if (cancelBtn) {
                            var panel = document.getElementById('forgotStampPanel');
                            if (panel) {
                                panel.classList.remove('force-open');
                                panel.classList.add('minimized');
                            }
                        }
                    }, true);
                }"""

    if old_snippet in content:
        content = content.replace(old_snippet, new_snippet, 1)
        path.write_text(content, encoding="utf-8")
        print("[OK] Paikkaus ajettu: Unohtuneen leiman viive ja pomppiminen poistettu.")
    else:
        print("[INFO] Muutosta ei tarvittu tai koodilohkoa ei löytynyt sellaisenaan.")

if __name__ == "__main__":
    main()
