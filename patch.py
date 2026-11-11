import pathlib

proguard_path = pathlib.Path("app/proguard-rules.pro")
if proguard_path.exists():
    pg = proguard_path.read_text(encoding="utf-8")
    
    # Säännöt, joilla R8 ohittaa Google Tink -turvakirjaston harmittomat puutteet
    rules_to_add = "\n# Ohitetaan turvakirjaston puuttuvat annotaatiot\n-dontwarn javax.annotation.**\n-dontwarn javax.annotation.concurrent.**\n"
    
    if "-dontwarn javax.annotation.**" not in pg:
        proguard_path.write_text(pg + rules_to_add, encoding="utf-8")
        print("proguard-rules.pro päivitetty: R8 varoitukset korjattu!")
    else:
        print("Säännöt olivat jo kunnossa.")
