#!/usr/bin/env python3
import pathlib
import re
import sys


def find_target(rel_path: str, filename: str) -> pathlib.Path | None:
    direct = pathlib.Path(rel_path)
    if direct.exists():
        return direct
    local = pathlib.Path(filename)
    if local.exists():
        return local
    matches = sorted(pathlib.Path(".").rglob(filename))
    return matches[0] if matches else None


def fix_main_activity(path: pathlib.Path) -> bool:
    content = path.read_text(encoding="utf-8")
    original = content

    # Poistetaan vahingossa Kotlin-koodin sekaan (""".trimIndent() jälkeen) jäänyt JS-lohko
    broken_block_pattern = re.compile(
        r'("""\.trimIndent\(\))\s*// === PÄIVÄNTOIVOTUS KIRJAUTUMISNÄKYMÄÄN ===.*?\n([ \t]*view\?\.evaluateJavascript\(js, null\))',
        re.DOTALL,
    )
    content = broken_block_pattern.sub(r"\1\n\n\2", content)

    if content != original:
        path.write_text(content, encoding="utf-8")
        print(f"[OK] Korjattu syntaksivirhe tiedostosta: {path}")
        return True

    print(f"[INFO] Ei korjattavaa tiedostossa: {path}")
    return False


def patch_quick_stamp_activity(path: pathlib.Path) -> bool:
    content = path.read_text(encoding="utf-8")
    if "fun buildGreeting(" in content or "lateinit var greetingText" in content:
        print(f"[INFO] Päiväntoivotus on jo lisätty tiedostoon: {path}")
        return False

    replacements = [
        (
            "    private lateinit var statusText: TextView\n",
            "    private lateinit var statusText: TextView\n    private lateinit var greetingText: TextView\n",
        ),
        (
            """        card.addView(statusText)

        val webHolder = FrameLayout(this).apply {""",
            """        card.addView(statusText)

        val greetingBg = GradientDrawable().apply {
            setColor(Color.parseColor("#111923"))
            setStroke(dp(1), Color.parseColor("#2A394A"))
            cornerRadius = dp(10).toFloat()
        }

        greetingText = TextView(this).apply {
            text = buildGreeting(isEnding = false)
            textSize = 13f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#38BDF8"))
            background = greetingBg
            gravity = Gravity.CENTER
            setPadding(dp(12), dp(8), dp(12), dp(8))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                topMargin = dp(14)
            }
        }
        card.addView(greetingText)

        val webHolder = FrameLayout(this).apply {""",
        ),
        (
            """    private fun resetToLoadingUi() {
        progressBar.visibility = View.VISIBLE
        statusBadge.visibility = View.GONE
    }""",
            """    private fun buildGreeting(isEnding: Boolean): String {
        val hour = LocalTime.now().hour
        return if (isEnding) {
            when (hour) {
                in 5..10 -> "Hyvää huomenta, kiitos työvuorosta!"
                in 11..16 -> "Hyvää loppupäivää, kiitos työvuorosta!"
                in 17..21 -> "Hyvää iltaa, kiitos työvuorosta!"
                else -> "Hyvää yötä, kiitos työvuorosta!"
            }
        } else {
            when (hour) {
                in 4..9 -> "Hyvää huomenta ja mukavaa työvuoroa!"
                in 10..13 -> "Hyvää päivää ja mukavaa työvuoroa!"
                in 14..17 -> "Hyvää iltapäivää ja mukavaa työvuoroa!"
                in 18..21 -> "Hyvää iltaa ja tsemppiä vuoroon!"
                else -> "Hyvää yötä ja tsemppiä yövuoroon!"
            }
        }
    }

    private fun resetToLoadingUi() {
        progressBar.visibility = View.VISIBLE
        statusBadge.visibility = View.GONE
        greetingText.visibility = View.VISIBLE
    }""",
        ),
        (
            """        statusBadge.text = badgeText
        statusBadge.setTextColor(Color.parseColor(badgeTextHex))
        statusBadge.visibility = View.VISIBLE

        titleText.text = title""",
            """        statusBadge.text = badgeText
        statusBadge.setTextColor(Color.parseColor(badgeTextHex))
        statusBadge.visibility = View.VISIBLE

        if (badgeText == "!" && badgeFillHex != "#1E3A5F") {
            greetingText.visibility = View.GONE
        }

        titleText.text = title""",
        ),
        (
            """        val targetText = if (isEnding) "Ulos" else "Sisään"
        val actionTitle = if (isEnding) "Leimataan ulos" else "Leimataan sisään"

        titleText.text = actionTitle""",
            """        val targetText = if (isEnding) "Ulos" else "Sisään"
        val actionTitle = if (isEnding) "Leimataan ulos" else "Leimataan sisään"

        greetingText.text = buildGreeting(isEnding)
        greetingText.visibility = View.VISIBLE

        titleText.text = actionTitle""",
        ),
    ]

    updated = content
    for idx, (old, new) in enumerate(replacements, start=1):
        if old not in updated:
            print(
                f"[VIRHE] Ankkurikohtaa #{idx} ei löytynyt tiedostosta {path}. Muutoksia ei tallennettu.",
                file=sys.stderr,
            )
            sys.exit(1)
        updated = updated.replace(old, new, 1)

    path.write_text(updated, encoding="utf-8")
    print(f"[OK] Lisätty päiväntoivotus tiedostoon: {path}")
    return True


def main() -> None:
    main_path = find_target(
        "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt",
        "MainActivity.kt",
    )
    quick_stamp_path = find_target(
        "app/src/main/java/fi/numeron/vuorovahti/QuickStampActivity.kt",
        "QuickStampActivity.kt",
    )

    if not main_path and not quick_stamp_path:
        print(
            "Virhe: MainActivity.kt- tai QuickStampActivity.kt-tiedostoa ei löytynyt.",
            file=sys.stderr,
        )
        sys.exit(1)

    if main_path:
        fix_main_activity(main_path)
    else:
        print("[VAROITUS] MainActivity.kt-tiedostoa ei löytynyt.")

    if quick_stamp_path:
        patch_quick_stamp_activity(quick_stamp_path)
    else:
        print("[VAROITUS] QuickStampActivity.kt-tiedostoa ei löytynyt.")


if __name__ == "__main__":
    main()
