#!/usr/bin/env python3
import pathlib
import sys

def main():
    path = pathlib.Path("app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt")
    if not path.exists():
        matches = list(pathlib.Path(".").rglob("MainActivity.kt"))
        if matches:
            path = matches[0]
        else:
            print("MainActivity.kt ei löytynyt!", file=sys.stderr)
            sys.exit(1)
            
    content = path.read_text(encoding="utf-8")
    
    old_overlay = '''        val scrim = View(this).apply {
            setBackgroundColor(Color.parseColor("#660F1722"))
        }
        overlay.addView(
            scrim,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )

        rootContent.addView(overlay, FrameLayout.LayoutParams(webView.width, webView.height))'''

    new_overlay = '''        val scrim = View(this).apply {
            setBackgroundColor(Color.parseColor("#660F1722"))
        }
        overlay.addView(
            scrim,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )

        val progressBar = ProgressBar(this, null, android.R.attr.progressBarStyleMedium).apply {
            isIndeterminate = true
            indeterminateTintList = ColorStateList.valueOf(Color.parseColor("#38BDF8"))
        }
        val spinnerParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            gravity = Gravity.CENTER
        }
        overlay.addView(progressBar, spinnerParams)

        rootContent.addView(overlay, FrameLayout.LayoutParams(webView.width, webView.height))'''

    if old_overlay in content:
        content = content.replace(old_overlay, new_overlay, 1)
        path.write_text(content, encoding="utf-8")
        print("[OK] Latausindikaattori lisätty onnistuneesti.")
    else:
        print("[INFO] Muutosta ei tarvittu tai kohdetta ei löytynyt sellaisenaan.")

if __name__ == "__main__":
    main()
