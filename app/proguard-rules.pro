-keepattributes JavascriptInterface
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}

# Ohitetaan Tink / security-crypto -kirjaston käännösaikaiset annotaatiot
-dontwarn javax.annotation.**
-dontwarn com.google.errorprone.annotations.**
