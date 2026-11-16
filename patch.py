#!/usr/bin/env python3
import os

def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    normalized = content.replace("\r\n", "\n")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(normalized)
    print(f"Päivitetty: {path}")

gradle_path = "app/build.gradle.kts"
if os.path.exists(gradle_path):
    with open(gradle_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Tarkistetaan, onko signingConfigs jo lisätty
    if "signingConfigs" not in content:
        # Etsitään android { lohko ja lisätään signingConfigs sinne
        old_android_block = "android {"
        new_android_block = """android {
    signingConfigs {
        create("release") {
            storeFile = file("release-key.jks")
            storePassword = System.getenv("KEYSTORE_PASSWORD")
            keyAlias = System.getenv("KEY_ALIAS")
            keyPassword = System.getenv("KEY_PASSWORD")
        }
    }"""

        content = content.replace(old_android_block, new_android_block, 1)

        # Kytketään signingConfig release buildTypeen
        old_release_block = """    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }"""

        new_release_block = """    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }"""

        content = content.replace(old_release_block, new_release_block, 1)
        write_file(gradle_path, content)
        print("signingConfigs lisätty onnistuneesti app/build.gradle.kts-tiedostoon!")
    else:
        print("signingConfigs löytyy jo ennestään build.gradle.kts-tiedostosta.")
