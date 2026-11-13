import pathlib, re

print("Aloitetaan patch-ajo...")

# =====================================================================
# OSA 1: VERSIONUMERON NOSTO (GRADLE)
# Tämä osa nostaa sovelluksen versionCodea ja versionNamea automaattisesti.
# =====================================================================
print("\n--- Osa 1: Versionumeroiden päivitys ---")
for file_name in ["app/build.gradle.kts", "app/build.gradle"]:
    gf = pathlib.Path(file_name)
    if gf.exists():
        c = gf.read_text(encoding="utf-8")
        
        # Nosta versionCode (esim. versionCode 14 -> 15)
        vc_match = re.search(r'versionCode(?:\s*=\s*|\s+)(\d+)', c)
        if vc_match:
            new_vc = int(vc_match.group(1)) + 1
            c = re.sub(rf'(versionCode(?:\s*=\s*|\s+)){vc_match.group(1)}\b', rf'\g<1>{new_vc}', c)
            print(f" -> versionCode päivitetty: {vc_match.group(1)} -> {new_vc}")
            
        # Nosta versionName (esim. versionName "1.0.4" -> "1.0.5")
        vn_match = re.search(r'versionName(?:\s*=\s*|\s+)["\']([^"\']+)["\']', c)
        if vn_match:
            parts = vn_match.group(1).split('.')
            if parts[-1].isdigit():
                parts[-1] = str(int(parts[-1]) + 1)
                new_vn = ".".join(parts)
                c = re.sub(rf'(versionName(?:\s*=\s*|\s+)["\']){vn_match.group(1)}(["\'])', rf'\g<1>{new_vn}\g<2>', c)
                print(f" -> versionName päivitetty: {vn_match.group(1)} -> {new_vn}")
                
        gf.write_text(c, encoding="utf-8")
        print(f"Gradle-päivitys valmis ({file_name}).")


# =====================================================================
# OSA 2: UI- JA ULKONÄKÖMUUTOKSET
# =====================================================================
# HUOM! Voit poistaa KAIKEN koodin tästä alaspäin, jos haluat jatkossa 
# käyttää skriptiä vain versionumeroiden nostamiseen.
# =====================================================================
print("\n--- Osa 2: UI-muutokset (Teema ja yläpalkin piilotus) ---")
ma_path = pathlib.Path("app/src/main/java/fi/oma/numeron/MainActivity.kt")
if ma_path.exists():
    ma = ma_path.read_text(encoding="utf-8")
    
    # 2.1 Lisätään CSS-injektio (tumma teema ja Visman palkin poisto)
    if "val darkThemeCss =" not in ma:
        target_css_anchor = "view?.loadUrl(urlStamping)\n                        return\n                    }"
        css_code = """
                    // --- UUSI: TÄYDELLINEN ULKONÄÖN MUOKKAUS (TUMMA TEEMA & YLÄPALKIN POISTO) ---
                    val darkThemeCss = \"\"\"
                        var style = document.createElement('style');
                        style.type = 'text/css';
                        style.innerHTML = `
                            .navbar, .navbar-default, .top-bar, .app-header, header, nav { display: none !important; }
                            body { padding-top: 0 !important; }
                            #page-wrapper, .main-container, .wrapper { margin: 0 !important; padding: 16px !important; }
                            body, html, .wrapper, #wrapper, #page-wrapper, .gray-bg { background-color: #0F172A !important; color: #E2E8F0 !important; }
                            .panel, .card, .well, .box, .ibox, .ibox-content, .panel-body, .panel-heading {
                                background-color: #1E293B !important; border: 1px solid #334155 !important;
                                border-radius: 16px !important; color: #E2E8F0 !important; box-shadow: none !important;
                            }
                            .panel-heading, .panel-title, .ibox-title {
                                background-color: transparent !important; border-bottom: 1px solid #334155 !important;
                                color: #38BDF8 !important; font-weight: bold !important;
                            }
                            .btn, button, input[type="submit"], input[type="button"] {
                                background: #0284C7 !important; color: #FFFFFF !important; border: none !important;
                                border-radius: 12px !important; box-shadow: none !important; text-shadow: none !important;
                            }
                            input, select, textarea, .form-control {
                                background-color: #0F172A !important; color: #FFFFFF !important;
                                border: 1px solid #334155 !important; border-radius: 8px !important;
                            }
                            h1, h2, h3, h4, h5, label, span, div, p, strong, b, i { color: #E2E8F0 !important; }
                            table, th, td { border-color: #334155 !important; color: #E2E8F0 !important; }
                            th { background-color: #1E293B !important; }
                        `;
                        document.head.appendChild(style);
                    \"\"\".trimIndent()
                    view?.evaluateJavascript(darkThemeCss, null)
"""
        ma = ma.replace(target_css_anchor, target_css_anchor + "\n" + css_code)
        
    # 2.2 Poistetaan kokonaan vanha PDF-latausroska ja PdfBridge-rajapinta
    ma = re.sub(r'// --- TÄSSÄ ON UUSI PDF:N PELASTAJA.*?(?=if \(currentUrl\.contains\("/PersonRequests/")', '', ma, flags=re.DOTALL)
    ma = re.sub(r'// --- UUSI PDF-RAJAPINTA.*?\}, "PdfBridge"\)', '', ma, flags=re.DOTALL)
    
    # 2.3 Piilotetaan Saldot-sarake leimaussivulla (jos ei vielä ole piilotettu)
    if "hideBalancesJs" not in ma:
        stamping_target = "if (currentUrl.contains(\"/WorktimeStamping\", ignoreCase = true)) {"
        stamping_code = """if (currentUrl.contains("/WorktimeStamping", ignoreCase = true)) {
                        // --- Saldot-sarakkeen piilotus ---
                        val hideBalancesJs = \"\"\"
                            setTimeout(function() {
                                var headers = document.querySelectorAll('th, td, div');
                                for (var i = 0; i < headers.length; i++) {
                                    var el = headers[i];
                                    if ((el.innerText || '').trim().toLowerCase().indexOf('saldo') === 0) {
                                        if (el.tagName.toLowerCase() === 'th' || el.tagName.toLowerCase() === 'td') {
                                            var table = el.closest('table');
                                            if (table) {
                                                var idx = el.cellIndex;
                                                for (var r = 0; r < table.rows.length; r++) {
                                                    if (table.rows[r].cells.length > idx) table.rows[r].cells[idx].style.display = 'none';
                                                }
                                            }
                                        } else el.style.display = 'none';
                                    }
                                }
                            }, 300);
                        \"\"\".trimIndent()
                        view?.evaluateJavascript(hideBalancesJs, null)
"""
        ma = ma.replace(stamping_target, stamping_code)
        
    ma_path.write_text(ma, encoding="utf-8")
    print("UI-muutokset viety onnistuneesti MainActivity.kt -tiedostoon!")

print("\nKaikki valmista! Voit nyt kääntää sovelluksen.")
