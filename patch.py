import pathlib, re

# 1. Korjataan Edge-to-Edge (Reunasta reunaan -näyttö Android 15 varten)
d = pathlib.Path("app/src/main/java/fi/oma/numeron")
ma_path = d / "MainActivity.kt"
if ma_path.exists():
    ma = ma_path.read_text(encoding="utf-8")

    if "import androidx.activity.enableEdgeToEdge" not in ma:
        ma = ma.replace(
            "import android.os.Bundle",
            "import android.os.Bundle\nimport androidx.activity.enableEdgeToEdge\nimport androidx.core.view.ViewCompat\nimport androidx.core.view.WindowInsetsCompat"
        )

    if "enableEdgeToEdge()" not in ma:
        ma = re.sub(
            r'(override fun onCreate\(savedInstanceState: Bundle\?\) \{)',
            r'\1\n        enableEdgeToEdge()',
            ma
        )
        
        ma = re.sub(
            r'(super\.onCreate\(savedInstanceState\))',
            r'\1\n        ViewCompat.setOnApplyWindowInsetsListener(findViewById(android.R.id.content)) { v, insets ->\n            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())\n            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)\n            insets\n        }',
            ma
        )

    ma_path.write_text(ma, encoding="utf-8")
    print("MainActivity.kt päivitetty Edge-to-Edge -tuella!")

# 2. Varmistetaan Proguard-säännöt (omat luokat + R8 virheiden ohitus)
pg_path = pathlib.Path("app/proguard-rules.pro")
pg = pg_path.read_text(encoding="utf-8") if pg_path.exists() else ""

rules = """
# R8 ohitussäännöt Google Tinkille
-dontwarn javax.annotation.**
-dontwarn javax.annotation.concurrent.**

# Suojataan omat luokat ja JS-silta (tärkeä WebViewille)
-keep class fi.oma.numeron.** { *; }
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
"""
if "-dontwarn javax.annotation" not in pg:
    pg_path.write_text(pg + rules, encoding="utf-8")
    print("proguard-rules.pro luotu/päivitetty.")

# 3. Kytketään R8 päälle ja kerrotaan Gradlelle mistä säännöt löytyvät
for file_name in ["app/build.gradle.kts", "app/build.gradle"]:
    gf = pathlib.Path(file_name)
    if gf.exists():
        c = gf.read_text(encoding="utf-8")
        
        c = c.replace("isMinifyEnabled = false", "isMinifyEnabled = true\n            isShrinkResources = true")
        c = c.replace("minifyEnabled false", "minifyEnabled true\n            shrinkResources true")
        
        if "isMinifyEnabled = true" in c and "proguard-rules.pro" not in c:
            c = c.replace("isMinifyEnabled = true", 'isMinifyEnabled = true\n            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")')
            
        if "minifyEnabled true" in c and "proguard-rules.pro" not in c:
            c = c.replace("minifyEnabled true", "minifyEnabled true\n            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'")
            
        gf.write_text(c, encoding="utf-8")
        print(f"{file_name} päivitetty käyttämään omia ProGuard-sääntöjä!")
