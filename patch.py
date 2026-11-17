#!/usr/bin/env python3
import pathlib
import sys
import re

def main():
    main_act_path = pathlib.Path("app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt")
    if not main_act_path.exists():
        alt = pathlib.Path("MainActivity.kt")
        if alt.exists():
            main_act_path = alt
        else:
            print(f"Virhe: Tiedostoa {main_act_path} ei löytynyt.", file=sys.stderr)
            sys.exit(1)

    content = main_act_path.read_text(encoding="utf-8")
    original = content

    # 1. Korjataan saldojen haku fetchillä niin, että käsitellään vastaus HTML:nä (.text()) JSONin sijaan
    old_fetch_block = """                        fetch('/WorktimeStamping/GetPersonBalance', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                                'X-Requested-With': 'XMLHttpRequest'
                            },
                            body: '__RequestVerificationToken=' + encodeURIComponent(token)
                        })
                        .then(function(r) { return r.json(); })
                        .then(function(data) {
                            var valEl = document.getElementById('numeron-balance-val');
                            if (!valEl) return;
                            var raw = (data && (data.Balance || data.balance || data.FormattedBalance || data.formattedBalance || data.TotalBalance || data.totalBalance || data.Value || data.value));
                            if (raw === undefined || raw === null) {
                                // Jos kentän nimi vaihtelee, etsitään ensimmäinen saldoa muistuttava arvo
                                if (typeof data === 'string' || typeof data === 'number') {
                                    raw = data;
                                } else if (data && typeof data === 'object') {
                                    for (var k in data) {
                                        if (Object.prototype.hasOwnProperty.call(data, k) && k.toLowerCase().indexOf('balance') !== -1 && data[k] !== null) {
                                            raw = data[k];
                                            break;
                                        }
                                    }
                                }
                            }
                            if (raw !== undefined && raw !== null && String(raw).trim() !== '') {
                                var txt = String(raw).trim();
                                valEl.textContent = txt;
                                if (txt.indexOf('-') === 0) {
                                    valEl.style.color = '#F87171';
                                } else {
                                    valEl.style.color = '#34D399';
                                }
                            } else {
                                card.style.display = 'none';
                            }
                        })"""

    new_fetch_block = """                        fetch('/WorktimeStamping/GetPersonBalance', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                                'X-Requested-With': 'XMLHttpRequest'
                            },
                            body: '__RequestVerificationToken=' + encodeURIComponent(token)
                        })
                        .then(function(r) { return r.text(); })
                        .then(function(htmlText) {
                            var valEl = document.getElementById('numeron-balance-val');
                            if (!valEl) return;
                            if (htmlText && htmlText.trim() !== '') {
                                valEl.innerHTML = htmlText;
                            } else {
                                card.style.display = 'none';
                            }
                        })"""

    if old_fetch_block in content:
        content = content.replace(old_fetch_block, new_fetch_block, 1)

    if content != original:
        main_act_path.write_text(content, encoding="utf-8")
        print(f"Päivitetty onnistuneesti: {main_act_path}")
    else:
        print("Ei muutoksia tehtävänä tai korjattavaa lohkoa ei löytynyt sellaisenaan.")

    # 2. Nostetaan automaattisesti build.gradle / build.gradle.kts -tiedoston versionCode-arvoa pienellä pykälällä
    for gradle_path in [pathlib.Path("app/build.gradle"), pathlib.Path("app/build.gradle.kts"), pathlib.Path("build.gradle")]:
        if gradle_path.exists():
            g_content = gradle_path.read_text(encoding="utf-8")
            match = re.search(r'versionCode\s+(\d+)', g_content)
            if match:
                old_code = int(match.group(1))
                new_code = old_code + 1
                g_content = g_content.replace(f"versionCode {old_code}", f"versionCode {new_code}")
                gradle_path.write_text(g_content, encoding="utf-8")
                print(f"Nostettu versionCode arvosta {old_code} arvoon {new_code} ({gradle_path})")
                break

if __name__ == "__main__":
    main()
