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


def patch_numeron_parser() -> None:
    path = find_file("NumeronParser.kt")
    src = path.read_text(encoding="utf-8")

    old_block = r"""    private fun parseShiftText(rawName: String): ParsedShiftText {
        val cleaned = rawName.trim().replace(Regex("^\\d+\\s*"), "").trim()
        val tokens = cleaned.split(Regex("\\s+")).filter { it.isNotBlank() }
        if (tokens.isEmpty()) {
            return ParsedShiftText(location = "", shiftName = "", role = "")
        }"""

    new_block = r"""    private fun parseShiftText(rawName: String): ParsedShiftText {
        val cleaned = rawName.trim().replace(Regex("^\\d+\\s*"), "").trim()
        if (cleaned.isEmpty()) {
            return ParsedShiftText(location = "", shiftName = "", role = "")
        }
        val noWorkRegex = Regex(
            "^(ei\\s+suunniteltuja\\s+töitä|ei\\s+(työ)?vuoroa|vapaa|vapaapäivä|vuosiloma|sairausloma|poissaolo)",
            RegexOption.IGNORE_CASE
        )
        if (noWorkRegex.containsMatchIn(cleaned)) {
            val formatted = cleaned.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
            return ParsedShiftText(location = formatted, shiftName = "", role = "")
        }
        val tokens = cleaned.split(Regex("\\s+")).filter { it.isNotBlank() }
        if (tokens.isEmpty()) {
            return ParsedShiftText(location = "", shiftName = "", role = "")
        }"""

    src = replace_exact(path, src, old_block, new_block)
    verify_kotlin_delimiters(path, src)
    path.write_text(src, encoding="utf-8")
    print(f"Päivitetty: {path}")


def main() -> None:
    patch_numeron_parser()
    increment_version()


if __name__ == "__main__":
    main()
