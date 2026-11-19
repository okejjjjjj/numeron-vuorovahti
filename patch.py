#!/usr/bin/env python3
import pathlib
import re


REPLACEMENTS = [
    (re.compile(r"Outokumpu\s+Onni", re.IGNORECASE), "Keskusyksikkö Helmi"),
    (re.compile(r"Siun\s+sote", re.IGNORECASE), "Hyvinvointialue Demo"),
    (re.compile(r"siunsote", re.IGNORECASE), "demo"),
]


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


def main() -> None:
    root = pathlib.Path("app/src") if pathlib.Path("app/src").exists() else pathlib.Path(".")
    modified_count = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {".kt", ".xml"}:
            continue

        original = path.read_text(encoding="utf-8")
        updated = original
        for pattern, replacement in REPLACEMENTS:
            updated = pattern.sub(replacement, updated)

        if updated != original:
            if path.suffix == ".kt":
                verify_kotlin_delimiters(path, updated)
            path.write_text(updated, encoding="utf-8")
            print(f"Päivitetty: {path}")
            modified_count += 1

    if modified_count == 0:
        print("Ei korvattavia mainintoja löytynyt.")
    else:
        increment_version()


if __name__ == "__main__":
    main()
