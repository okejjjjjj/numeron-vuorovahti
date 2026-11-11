import pathlib, re

# ---------------------------------------------------------
# 1. Korjataan Edge-to-Edge (Reunasta reunaan -näyttö Android 15 varten)
# ---------------------------------------------------------
d = pathlib.Path("app/src/main/java/fi/oma/numeron")
ma_path = d / "MainActivity.kt"
if ma_path.exists():
    ma = ma_path.read_text(encoding="utf-8")

    # Lisätään tarvittavat importit
    if "import androidx.activity.enableEdgeToEdge" not in ma:
        ma = ma.replace(
            "import android.os.Bundle",
            "import android.os.Bundle\nimport androidx.activity.enableEdgeToEdge\nimport androidx.core.view.ViewCompat\nimport androidx.core.view.WindowInsetsCompat"
        )

    # Lisätään enableEdgeToEdge() heti onCreate-metodin alkuun
    if "enableEdgeToEdge()" not in ma:
        ma = re.sub(
            r'(override fun onCreate\(savedInstanceState: Bundle\?\) \{)',
            r'\1\n        enableEdgeToEdge()',
            ma
        )
        
        # Lisätään kuuntelija, joka estää sisältöä jäämästä tilapalkin tai navigointipainikkeiden alle
        ma = re.sub(
            r'(super\.onCreate\(savedInstanceState\))',
            r'\1\n        ViewCompat.setOnApplyWindowInsetsListener(findViewById(android.R.id.content)) { v, insets ->\n            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())\n            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)\n            insets\n        }',
            ma
        )

    ma_path.write_text(ma, encoding="utf-8")
    print("MainActivity.kt päivitetty Edge-to-Edge -tuella!")

# ---------------------------------------------------------
# 2. Laitetaan R8/ProGuard obfuskointi päälle (DEX-optimointi)
# ---------------------------------------------------------
build_gradle_kts = pathlib.Path("app/build.gradle.kts")
build_gradle = pathlib.Path("app/build.gradle")

target_gradle = build_gradle_kts if build_gradle_kts.exists() else build_gradle

if target_gradle.exists():
    bg = target_gradle.read_text(encoding="utf-8")
    
    # Kytketään minify (obfuskointi) ja resurssien kutistus päälle
    if "isMinifyEnabled = false" in bg or "minifyEnabled false" in bg:
        bg = bg.replace("isMinifyEnabled = false", "isMinifyEnabled = true\n            isShrinkResources = true")
        bg = bg.replace("minifyEnabled false", "minifyEnabled true\n            shrinkResources true")
        target_gradle.write_text(bg, encoding="utf-8")
        print(f"{target_gradle.name} päivitetty: Obfuskointi kytketty päälle!")
    else:
        print(f"Obfuskointi oli jo päällä tiedostossa {target_gradle.name}.")

# ---------------------------------------------------------
# 3. Suojataan omat luokat obfuskoinnilta (estää WebView-siltaa rikkoutumasta)
# ---------------------------------------------------------
proguard_path = pathlib.Path("app/proguard-rules.pro")
if proguard_path.exists():
    pg = proguard_path.read_text(encoding="utf-8")
    safe_rules = "\n# Numeron Vuorovahti suojaukset\n-keep class fi.oma.numeron.** { *; }\n-keepclassmembers class * {\n    @android.webkit.JavascriptInterface <methods>;\n}\n"
    
    if "fi.oma.numeron" not in pg:
        proguard_path.write_text(pg + safe_rules, encoding="utf-8")
        print("proguard-rules.pro päivitetty: JS-silta suojattu!")
