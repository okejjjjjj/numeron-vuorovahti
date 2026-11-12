# R8 ohitussäännöt Google Tinkille
-dontwarn javax.annotation.**
-dontwarn javax.annotation.concurrent.**

# Suojataan omat luokat ja JS-silta (tärkeä WebViewille)
-keep class fi.oma.numeron.** { *; }
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
