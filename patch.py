import re

gradle_path = "app/build.gradle.kts"
if os.path.exists(gradle_path):
    with open(gradle_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Etsitään versionCode ja kasvatetaan arvoa yhdellä
    def increment_version_code(match):
        old_code = int(match.group(1))
        new_code = old_code + 1
        print(f"Päivitetään versionCode: {old_code} -> {new_code}")
        return f"versionCode = {new_code}"

    content, count = re.subn(r'versionCode\s*=\s*(\d+)', increment_version_code, content)
    
    if count > 0:
        with open(gradle_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("Versionumero päivitetty onnistuneesti.")
