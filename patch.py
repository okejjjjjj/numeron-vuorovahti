#!/usr/bin/env python3
import pathlib
import re


def find_file(filename: str) -> pathlib.Path:
    direct = pathlib.Path(filename)
    if direct.exists():
        return direct
    matches = list(pathlib.Path(".").rglob(filename))
    if matches:
        return matches[0]
    raise FileNotFoundError(f"Tiedostoa {filename} ei löytynyt!")


def verify_kotlin_delimiters(path: pathlib.Path, content: str) -> None:
    cleaned = re.sub(r'""".*?"""', '', content, flags=re.DOTALL)
    cleaned = re.sub(r'"(?:\\.|[^"\\])*"', '', cleaned)
    if cleaned.count("{") != cleaned.count("}"):
        raise RuntimeError(
            f"[{path.name}] Aaltosulkeiden määrä ei täsmää ({cleaned.count('{')} vs {cleaned.count('}')})"
        )
    if cleaned.count("(") != cleaned.count(")"):
        raise RuntimeError(
            f"[{path.name}] Kaarisulkeiden määrä ei täsmää ({cleaned.count('(')} vs {cleaned.count(')')})"
        )


def replace_exact(path: pathlib.Path, content: str, old: str, new: str) -> str:
    if old not in content:
        raise RuntimeError(f"[{path.name}] Korvattavaa lohkoa ei löytynyt:\n{old[:140]}...")
    return content.replace(old, new, 1)


def increment_version() -> None:
    gradle_candidates = [
        pathlib.Path("app/build.gradle.kts"),
        pathlib.Path("app/build.gradle"),
    ]
    gradle_file = next((p for p in gradle_candidates if p.exists()), None)
    if not gradle_file:
        matches = list(pathlib.Path(".").rglob("build.gradle*"))
        gradle_file = next((p for p in matches if "app" in p.parts), None)

    if not gradle_file:
        print("Varoitus: app/build.gradle(.kts) ei löytynyt, versionumeroa ei päivitetty.")
        return

    text = gradle_file.read_text(encoding="utf-8")

    vc_match = re.search(r'(versionCode\s*=?\s*)(\d+)', text)
    if vc_match:
        old_vc = int(vc_match.group(2))
        new_vc = old_vc + 1
        text = text[:vc_match.start(2)] + str(new_vc) + text[vc_match.end(2):]
        print(f"Päivitetty versionCode: {old_vc} -> {new_vc}")

    vn_match = re.search(r'(versionName\s*=?\s*")(\d+(?:\.\d+)*)(")', text)
    if vn_match:
        parts = vn_match.group(2).split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        new_vn = ".".join(parts)
        text = text[:vn_match.start(2)] + new_vn + text[vn_match.end(2):]
        print(f"Päivitetty versionName: {vn_match.group(2)} -> {new_vn}")

    gradle_file.write_text(text, encoding="utf-8")


def patch_main_activity() -> None:
    path = find_file("MainActivity.kt")
    src = path.read_text(encoding="utf-8")

    old_heading_css = r"""            h1, h2, h3, h4, .h1, .h2, .h3, .h4 {
                color: #F1F5F9 !important;
                font-size: 20px !important;
                font-weight: 600 !important;
                margin-top: 4px !important;
                margin-bottom: 12px !important;
            }"""

    new_heading_css = r"""            h1, h2, h3, h4, .h1, .h2, .h3, .h4 {
                color: #F1F5F9 !important;
                font-size: 20px !important;
                font-weight: 600 !important;
                margin-top: 4px !important;
                margin-bottom: 12px !important;
            }
            .container h1:not(#monthText), .container-fluid h1:not(#monthText),
            .container .h1:not(#monthText), .container-fluid .h1:not(#monthText) {
                display: none !important;
            }"""

    src = replace_exact(path, src, old_heading_css, new_heading_css)
    verify_kotlin_delimiters(path, src)
    path.write_text(src, encoding="utf-8")
    print(f"Päivitetty: {path}")


def main() -> None:
    patch_main_activity()
    increment_version()


if __name__ == "__main__":
    main()
