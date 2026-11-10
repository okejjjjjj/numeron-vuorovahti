import pathlib, re

# 1. Korjataan MainActivity.kt:ssa katkennut merkkijono (rivit 1474-1475)
ma_path = pathlib.Path("app/src/main/java/fi/oma/numeron/MainActivity.kt")
ma = ma_path.read_text(encoding="utf-8")

# Yhdistetään kahdelle riville katkennut text = "[$badgeText] ... \n $title"
ma = re.sub(
    r'text\s*=\s*"\[\$badgeText\][^\n"]*?\n\s*\$title"',
    'val nl = System.lineSeparator()\n                    text = "[$badgeText]  $dateStr  klo $timeStr" + nl + title',
    ma
)

# Varmuuden vuoksi korjataan mikä tahansa muukin kahdelle riville katkennut "text = ..."-lainaus
ma = re.sub(
    r'(text\s*=\s*"[^"\n]+)\n\s*([^"\n]+")',
    r'\1 — \2',
    ma
)

# Jos extractDirectVacationRanges-regexissä on katkennut rivi, korjataan sekin
ma = re.sub(
    r'\[\^\n\r\]\*',
    r'[^\\n\\r]*',
    ma
)

ma_path.write_text(ma, encoding="utf-8")
print("MainActivity.kt merkkijonot korjattu!")

# 2. Hiljennetään compileSdk=36 varoitus gradle.properties-tiedostossa
gp_path = pathlib.Path("gradle.properties")
gp = gp_path.read_text(encoding="utf-8") if gp_path.exists() else ""
if "android.suppressUnsupportedCompileSdk=36" not in gp:
    gp = gp.rstrip() + "\nandroid.suppressUnsupportedCompileSdk=36\n"
    gp_path.write_text(gp, encoding="utf-8")
    print("gradle.properties paivitetty!")
