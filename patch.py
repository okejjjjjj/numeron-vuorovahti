#!/usr/bin/env python3
import pathlib
import re
import sys

def find_file(candidates):
    for c in candidates:
        p = pathlib.Path(c)
        if p.exists():
            return p
    return None

def patch_main_activity():
    path = find_file([
        "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt",
        "MainActivity.kt",
        "MainActivity.kt.txt"
    ])
    if not path:
        print("Varoitus: MainActivity.kt ei löytynyt.")
        return False

    content = path.read_text(encoding="utf-8")
    original = content

    # 1. Poistetaan Toast leimauksen vahvistuksesta ja pidennetään viivettä ennen sulkeutumista (esim. 1500L)
    old_verify_block = """                if (buttonFlipped || rowUpdated) {
                    inFlightStampAction = Action.NONE
                    CookieManager.getInstance().flush()
                    Toast.makeText(this, "Leimaus vahvistettu ($targetText)", Toast.LENGTH_SHORT).show()
                    webView.postDelayed({ finishAndRemoveTask() }, 600L)"""

    new_verify_block = """                if (buttonFlipped || rowUpdated) {
                    inFlightStampAction = Action.NONE
                    CookieManager.getInstance().flush()
                    // Poistettu ylimääräinen Toast, luotetaan visuaaliseen tilaan
                    webView.postDelayed({ finishAndRemoveTask() }, 1500L)"""

    if old_verify_block in content:
        content = content.replace(old_verify_block, new_verify_block)

    # 2. Lisätään dynaaminen päiväntoivotus JS-injektioon (injectDarkTheme)
    old_js_inject = "style.innerHTML = '$safeCss';"
    new_js_inject = """style.innerHTML = '$safeCss';
                // === LISÄTTÄVÄT PÄIVÄNTOIVOTUKSET TYÖVUOROILLE ===
                (function addShiftGreeting() {
                    var container = document.querySelector('.punching-shift-container');
                    if (!container || document.getElementById('numeron-shift-greeting')) return;
                    var hour = new Date().getHours();
                    var greeting = "Hyvää työpäivää!";
                    if (hour < 10) greeting = "Hyvää huomenta, mukavaa työvirettä!";
                    else if (hour >= 14 && hour < 20) greeting = "Hyvää iltapäivää, jaksuja vuoroon!";
                    else if (hour >= 20 || hour < 4) greeting = "Hyvää iltaa ja tsemppiä vuoroon!";

                    var greetDiv = document.createElement('div');
                    greetDiv.id = 'numeron-shift-greeting';
                    greetDiv.style.cssText = 'font-size:13px;color:#38BDF8;font-weight:600;margin-bottom:8px;padding:6px 10px;background:#111923;border:1px solid #2A394A;border-radius:8px;';
                    greetDiv.textContent = '✨ ' + greeting;
                    container.insertBefore(greetDiv, container.firstChild);
                })();"""

    if old_js_inject in content and "numeron-shift-greeting" not in content:
        content = content.replace(old_js_inject, new_js_inject, 1)

    if content != original:
        path.write_text(content, encoding="utf-8")
        print("MainActivity.kt päivitetty onnistuneesti.")
        return True
    else:
        print("Ei muutoksia MainActivity.kt-tiedostoon.")
        return False

def patch_calendar_tracker():
    path = find_file([
        "app/src/main/java/fi/numeron/vuorovahti/CalendarChangeTracker.kt",
        "CalendarChangeTracker.kt",
        "CalendarChangeTracker.kt.txt"
    ])
    if not path:
        print("Varoitus: CalendarChangeTracker.kt ei löytynyt.")
        return False

    content = path.read_text(encoding="utf-8")
    original = content

    # Lisätään "Hyväksy" (Tallenna/Sulje) -painike kalenterimuutosten dialogiin
    old_footer = """        val btnClose = Button(context).apply {
            text = "Sulje\"
            isAllCaps = false
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            background = makeCardBg("#1982C4", "#38BDF8", 8)
            setTextColor(Color.parseColor("#FFFFFF"))
            setPadding(dp(20), dp(10), dp(20), dp(10))
            setOnClickListener { dialogRef?.dismiss() }
        }
        footerBar.addView(btnClose)"""

    new_footer = """        val btnAccept = Button(context).apply {
            text = "Hyväksy"
            isAllCaps = false
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            background = makeCardBg("#10B981", "#34D399", 8)
            setTextColor(Color.parseColor("#FFFFFF"))
            setPadding(dp(18), dp(10), dp(18), dp(10))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { marginEnd = dp(8) }
            setOnClickListener {
                dialogRef?.dismiss()
                onChanged?.invoke()
            }
        }
        footerBar.addView(btnAccept)

        val btnClose = Button(context).apply {
            text = "Sulje"
            isAllCaps = false
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            background = makeCardBg("#1982C4", "#38BDF8", 8)
            setTextColor(Color.parseColor("#FFFFFF"))
            setPadding(dp(20), dp(10), dp(20), dp(10))
            setOnClickListener { dialogRef?.dismiss() }
        }
        footerBar.addView(btnClose)"""

    if old_footer in content:
        content = content.replace(old_footer, new_footer)

    if content != original:
        path.write_text(content, encoding="utf-8")
        print("CalendarChangeTracker.kt päivitetty onnistuneesti.")
        return True
    else:
        print("Ei muutoksia CalendarChangeTracker.kt-tiedostoon.")
        return False

def main():
    m_ok = patch_main_activity()
    c_ok = patch_calendar_tracker()
    if m_ok or c_ok:
        print("Patch-ajo suoritettu valmiiksi.")
    else:
        print("Ei tehty mitään muutoksia tiedostoihin.")

if __name__ == "__main__":
    main()
