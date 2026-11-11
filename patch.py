import pathlib

# 1. Varmistetaan proguard-säännöt
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

# 2. Varmistetaan että build.gradle LUKEE proguard-tiedostoa
for file_name in ["app/build.gradle.kts", "app/build.gradle"]:
    gf = pathlib.Path(file_name)
    if gf.exists():
        c = gf.read_text(encoding="utf-8")
        
        # Käännetään minify päälle (varmuuden vuoksi, jos aiempi peruuntui)
        c = c.replace("isMinifyEnabled = false", "isMinifyEnabled = true\n            isShrinkResources = true")
        c = c.replace("minifyEnabled false", "minifyEnabled true\n            shrinkResources true")
        
        # Lisätään tiedostoviittaus (Kotlin DSL)
        if "isMinifyEnabled = true" in c and "proguard-rules.pro" not in c:
            c = c.replace("isMinifyEnabled = true", 'isMinifyEnabled = true\n            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")')
            
        # Lisätään tiedostoviittaus (Groovy)
        if "minifyEnabled true" in c and "proguard-rules.pro" not in c:
            c = c.replace("minifyEnabled true", "minifyEnabled true\n            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'")
            
        gf.write_text(c, encoding="utf-8")
        print(f"{file_name} päivitetty käyttämään omia ProGuard-sääntöjä!")
