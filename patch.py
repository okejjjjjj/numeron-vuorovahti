import os
import sys

CIRCLE_CSS = '''            .month-day-header {
                display: flex !important;
                align-items: center !important;
                justify-content: space-between !important;
            }
            .month-day-header .hidden {
                display: none !important;
            }
            .month-day-header .circle {
                display: inline-block !important;
                width: 6px !important;
                height: 6px !important;
                min-width: 6px !important;
                border-radius: 50% !important;
                background-color: #F59E0B !important;
                box-shadow: 0 0 0 1px rgba(245, 158, 11, 0.35) !important;
                margin-right: 4px !important;
                flex-shrink: 0 !important;
            }'''

ANCHOR_AFTER_CLEANUP = '''            .month-item.absence.vuorovahti-other {
                background-color: #334155 !important;
                border: 1px solid #64748B !important;
                color: #F1F5F9 !important;
            }'''

ANCHOR_FALLBACK = '''            .month-item.work .itemName {
                display: none !important;
            }'''


def find_file(filename):
    default_path = os.path.join("app", "src", "main", "java", "fi", "numeron", "vuorovahti", filename)
    if os.path.isfile(default_path):
        return default_path
    for root, _, files in os.walk("."):
        if filename in files:
            return os.path.join(root, filename)
    return None


def main():
    main_path = find_file("MainActivity.kt")
    if not main_path:
        print("VIRHE: MainActivity.kt ei löytynyt.")
        sys.exit(1)

    with open(main_path, "r", encoding="utf-8") as f:
        src = f.read()

    if ".month-day-header .circle" in src:
        print(f"Ei muutoksia (jo päivitetty): {main_path}")
        return

    if ANCHOR_AFTER_CLEANUP in src:
        src = src.replace(ANCHOR_AFTER_CLEANUP, ANCHOR_AFTER_CLEANUP + "\n" + CIRCLE_CSS, 1)
    elif ANCHOR_FALLBACK in src:
        src = src.replace(ANCHOR_FALLBACK, ANCHOR_FALLBACK + "\n" + CIRCLE_CSS, 1)
    else:
        print("VIRHE: Sopivaa CSS-ankkuria ei löytynyt tiedostosta MainActivity.kt.")
        sys.exit(1)

    with open(main_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)

    print(f"Päivitetty: {main_path}")


if __name__ == "__main__":
    main()
