import os
from PIL import Image, ImageDraw

# Etsitään ladattu lähdekuva
SOURCE_CANDIDATES = ["icon_source.png", "icon_source.jpg", "icon_source.jpeg", "icon_source.webp"]
source_file = next((f for f in SOURCE_CANDIDATES if os.path.exists(f)), None)

if source_file:
    RES_DIR = os.path.join("app", "src", "main", "res")
    img = Image.open(source_file).convert("RGBA")

    # Rajataan keskeltä neliö (koska kuva 2 on 16:9-laajakuva, jossa ikoni on keskellä)
    w, h = img.size
    side = int(min(w, h) * 0.78)  # Poistaa reunoilta tyhjän taustan ikonin ympäriltä
    left = (w - side) // 2
    top = (h - side) // 2
    cropped = img.crop((left, top, left + side, top + side))

    # Luodaan pyöreä versio (ic_launcher_round)
    mask = Image.new("L", (side, side), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, side, side), fill=255)
    round_img = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    round_img.paste(cropped, (0, 0), mask=mask)

    # Androidin vaaditut tiheydet ja pikselikoot
    densities = {
        "mipmap-mdpi": 48,
        "mipmap-hdpi": 72,
        "mipmap-xhdpi": 96,
        "mipmap-xxhdpi": 144,
        "mipmap-xxxhdpi": 192,
    }

    for folder, size in densities.items():
        out_dir = os.path.join(RES_DIR, folder)
        os.makedirs(out_dir, exist_ok=True)
        cropped.resize((size, size), Image.Resampling.LANCZOS).save(os.path.join(out_dir, "ic_launcher.png"))
        round_img.resize((size, size), Image.Resampling.LANCZOS).save(os.path.join(out_dir, "ic_launcher_round.png"))

    # Adaptiivinen ikoni (Android 8.0+) -> mipmap-anydpi-v26
    anydpi_dir = os.path.join(RES_DIR, "mipmap-anydpi-v26")
    drawable_dir = os.path.join(RES_DIR, "drawable")
    os.makedirs(anydpi_dir, exist_ok=True)
    os.makedirs(drawable_dir, exist_ok=True)

    # Etualan kuva (432x432 px turvamarginaaleilla)
    fg_canvas = Image.new("RGBA", (432, 432), (24, 34, 48, 255))
    inner = cropped.resize((320, 320), Image.Resampling.LANCZOS)
    fg_canvas.paste(inner, (56, 56), inner)
    fg_canvas.save(os.path.join(drawable_dir, "ic_launcher_foreground.png"))

    adaptive_xml = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background"/>
    <foreground android:drawable="@drawable/ic_launcher_foreground"/>
</adaptive-icon>
"""
    with open(os.path.join(anydpi_dir, "ic_launcher.xml"), "w", encoding="utf-8") as f:
        f.write(adaptive_xml)
    with open(os.path.join(anydpi_dir, "ic_launcher_round.xml"), "w", encoding="utf-8") as f:
        f.write(adaptive_xml)

    values_dir = os.path.join(RES_DIR, "values")
    os.makedirs(values_dir, exist_ok=True)
    with open(os.path.join(values_dir, "ic_launcher_background.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#182230</color>\n</resources>\n')

    print("Sovelluskuvakkeet generoitu onnistuneesti!")
