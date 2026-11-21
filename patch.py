import os
import shutil
import sys

OLD_IS_ENGLISH = '''    fun isEnglish(context: Context): Boolean {
        if (!isDemoEnabled(context)) return false
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val saved = prefs.getString("demo_language", null)
        return when (saved) {
            "en" -> true
            "fi" -> false
            else -> !Locale.getDefault().language.equals("fi", ignoreCase = true)
        }
    }'''

NEW_IS_ENGLISH = '''    fun isEnglish(context: Context): Boolean {
        if (isDemoEnabled(context)) {
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            when (prefs.getString("demo_language", null)) {
                "en" -> return true
                "fi" -> return false
            }
        }
        val sysLang = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.N) {
            context.resources.configuration.locales.get(0)?.language ?: Locale.getDefault().language
        } else {
            @Suppress("DEPRECATION")
            context.resources.configuration.locale?.language ?: Locale.getDefault().language
        }
        return !sysLang.equals("fi", ignoreCase = true)
    }'''

MAIN_REPLACEMENTS = [
    (
        'Toast.makeText(this, "Aseta ensin organisaatiotunnus asetuksista", Toast.LENGTH_LONG).show()',
        'Toast.makeText(this, if (DemoModeHelper.isEnglish(this)) "Set organization ID in settings first" else "Aseta ensin organisaatiotunnus asetuksista", Toast.LENGTH_LONG).show()'
    ),
    (
        '''            if (isTest) {
                val dir = if (isEnding) "Ulos" else "Sisään"
                Toast.makeText(
                    this,
                    "Testi-ilmoitus ($dir): Oikeaa leimausta ei suoritettu",
                    Toast.LENGTH_LONG
                ).show()
                return
            }

            pendingAction = if (isEnding) Action.STAMP_OUT else Action.STAMP_IN
            Toast.makeText(this, "Suoritetaan automaattinen leimaus...", Toast.LENGTH_SHORT).show()''',
        '''            if (isTest) {
                val en = DemoModeHelper.isEnglish(this)
                val dir = if (en) (if (isEnding) "Out" else "In") else (if (isEnding) "Ulos" else "Sisään")
                val msg = if (en) "Test notification ($dir): No real stamp was performed" else "Testi-ilmoitus ($dir): Oikeaa leimausta ei suoritettu"
                Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
                return
            }

            pendingAction = if (isEnding) Action.STAMP_OUT else Action.STAMP_IN
            val autoMsg = if (DemoModeHelper.isEnglish(this)) "Performing automatic stamp..." else "Suoritetaan automaattinen leimaus..."
            Toast.makeText(this, autoMsg, Toast.LENGTH_SHORT).show()'''
    ),
    (
        'Toast.makeText(this, "Istunto vanhentunut – kirjaudutaan uudelleen ja leimataan...", Toast.LENGTH_SHORT).show()',
        'Toast.makeText(this, if (DemoModeHelper.isEnglish(this)) "Session expired – re-authenticating and stamping..." else "Istunto vanhentunut – kirjaudutaan uudelleen ja leimataan...", Toast.LENGTH_SHORT).show()'
    ),
    (
        '''                    Toast.makeText(this, "Leimataan ($targetText)...", Toast.LENGTH_SHORT).show()
                    verifyStampAndClose(targetText, beforeBtn, beforeRow, 0)
                }
                status == "WRONG_DIRECTION" -> {
                    pendingAction = Action.NONE
                    inFlightStampAction = Action.NONE
                    Toast.makeText(this, "Olet jo leimannut tilaan: $targetText", Toast.LENGTH_LONG).show()''',
        '''                    val en = DemoModeHelper.isEnglish(this)
                    val dirLabel = if (en) (if (targetText == "Sisään") "In" else "Out") else targetText
                    Toast.makeText(this, if (en) "Stamping ($dirLabel)..." else "Leimataan ($targetText)...", Toast.LENGTH_SHORT).show()
                    verifyStampAndClose(targetText, beforeBtn, beforeRow, 0)
                }
                status == "WRONG_DIRECTION" -> {
                    pendingAction = Action.NONE
                    inFlightStampAction = Action.NONE
                    val en = DemoModeHelper.isEnglish(this)
                    val dirLabel = if (en) (if (targetText == "Sisään") "In" else "Out") else targetText
                    Toast.makeText(this, if (en) "Already clocked $dirLabel" else "Olet jo leimannut tilaan: $targetText", Toast.LENGTH_LONG).show()'''
    ),
    (
        '''                    Toast.makeText(
                        this,
                        "Leimausta ei voitu vahvistaa automaattisesti – tarkista tila ruudulta",
                        Toast.LENGTH_LONG
                    ).show()''',
        '''                    Toast.makeText(
                        this,
                        if (DemoModeHelper.isEnglish(this)) "Could not verify stamp automatically – please check status on screen" else "Leimausta ei voitu vahvistaa automaattisesti – tarkista tila ruudulta",
                        Toast.LENGTH_LONG
                    ).show()'''
    ),
    (
        '''                        withContext(Dispatchers.Main) {
                            Toast.makeText(
                                this@MainActivity,
                                "Työvuorojen luku epäonnistui – kalenteria ei muutettu",
                                Toast.LENGTH_LONG
                            ).show()
                        }''',
        '''                        withContext(Dispatchers.Main) {
                            Toast.makeText(
                                this@MainActivity,
                                if (DemoModeHelper.isEnglish(this@MainActivity)) "Failed to read shifts – calendar was not modified" else "Työvuorojen luku epäonnistui – kalenteria ei muutettu",
                                Toast.LENGTH_LONG
                            ).show()
                        }'''
    ),
    (
        '''                    withContext(Dispatchers.Main) {
                        if (syncCalendar && calId == null) {
                            Toast.makeText(
                                this@MainActivity,
                                "Vuorot haettu (${allShifts.size} kpl), mutta kalenteria ei ole valittu",
                                Toast.LENGTH_LONG
                            ).show()
                        } else if (changes.isNotEmpty()) {
                            Toast.makeText(
                                this@MainActivity,
                                "Kalenteria päivitetty: ${CalendarChangeTracker.formatSummary(changes)}",
                                Toast.LENGTH_LONG
                            ).show()
                            CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                        } else {
                            val msg = if (syncCalendar) {
                                "Kalenteri on ajan tasalla (${allShifts.size} vuoroa)"
                            } else {
                                "Työvuorot ja muistutukset päivitetty (${allShifts.size} vuoroa)"
                            }
                            Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                        }
                    }''',
        '''                    withContext(Dispatchers.Main) {
                        val en = DemoModeHelper.isEnglish(this@MainActivity)
                        if (syncCalendar && calId == null) {
                            Toast.makeText(
                                this@MainActivity,
                                if (en) "Shifts fetched (${allShifts.size}), but no calendar is selected" else "Vuorot haettu (${allShifts.size} kpl), mutta kalenteria ei ole valittu",
                                Toast.LENGTH_LONG
                            ).show()
                        } else if (changes.isNotEmpty()) {
                            Toast.makeText(
                                this@MainActivity,
                                if (en) "Calendar updated: ${CalendarChangeTracker.formatSummary(changes)}" else "Kalenteria päivitetty: ${CalendarChangeTracker.formatSummary(changes)}",
                                Toast.LENGTH_LONG
                            ).show()
                            CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                        } else {
                            val msg = if (syncCalendar) {
                                if (en) "Calendar is up to date (${allShifts.size} shifts)" else "Kalenteri on ajan tasalla (${allShifts.size} vuoroa)"
                            } else {
                                if (en) "Shifts and reminders updated (${allShifts.size} shifts)" else "Työvuorot ja muistutukset päivitetty (${allShifts.size} vuoroa)"
                            }
                            Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                        }
                    }'''
    ),
]

RECEIVER_REPLACEMENTS = [
    (
        'val title = intent.getStringExtra("SHIFT_TITLE") ?: "Työvuoro"',
        'val title = intent.getStringExtra("SHIFT_TITLE") ?: if (DemoModeHelper.isEnglish(context)) "Work Shift" else "Työvuoro"'
    ),
    (
        '"Toive käsitelty: $statusDesc",',
        'if (DemoModeHelper.isEnglish(appContext)) "Request processed: $statusDesc" else "Toive käsitelty: $statusDesc",'
    ),
]


def find_file(filename):
    default_path = os.path.join("app", "src", "main", "java", "fi", "numeron", "vuorovahti", filename)
    if os.path.isfile(default_path):
        return default_path
    for root, _, files in os.walk("."):
        if filename in files:
            return os.path.join(root, filename)
    return None


def update_file(path, replacements):
    if not path or not os.path.isfile(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    changed = False
    for old, new in replacements:
        if new in src:
            continue
        if old in src:
            src = src.replace(old, new, 1)
            changed = True
    if changed:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(src)
        print(f"Päivitetty: {path}")
    else:
        print(f"Ei muutoksia (jo ajan tasalla): {path}")
    return changed


def migrate_res_strings():
    res_dir = os.path.join("app", "src", "main", "res")
    default_strings = os.path.join(res_dir, "values", "strings.xml")
    en_strings = os.path.join(res_dir, "values-en", "strings.xml")
    fi_dir = os.path.join(res_dir, "values-fi")
    fi_strings = os.path.join(fi_dir, "strings.xml")

    if os.path.isfile(default_strings) and os.path.isfile(en_strings):
        os.makedirs(fi_dir, exist_ok=True)
        shutil.move(default_strings, fi_strings)
        shutil.move(en_strings, default_strings)
        try:
            os.rmdir(os.path.join(res_dir, "values-en"))
        except OSError:
            pass
        print("Päivitetty resurssikansiot: values/strings.xml -> values-fi/strings.xml ja values-en/strings.xml -> values/strings.xml")


def main():
    demo_path = find_file("DemoModeHelper.kt")
    if not demo_path:
        print("VIRHE: DemoModeHelper.kt ei löytynyt.")
        sys.exit(1)

    with open(demo_path, "r", encoding="utf-8") as f:
        demo_src = f.read()

    if NEW_IS_ENGLISH not in demo_src:
        if OLD_IS_ENGLISH not in demo_src:
            print("VIRHE: DemoModeHelper.isEnglish-funktiota ei löytynyt odotetussa muodossa.")
            sys.exit(1)
        demo_src = demo_src.replace(OLD_IS_ENGLISH, NEW_IS_ENGLISH, 1)
        with open(demo_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(demo_src)
        print(f"Päivitetty: {demo_path}")
    else:
        print(f"Ei muutoksia (jo ajan tasalla): {demo_path}")

    update_file(find_file("MainActivity.kt"), MAIN_REPLACEMENTS)
    update_file(find_file("ShiftReminderReceiver.kt"), RECEIVER_REPLACEMENTS)
    migrate_res_strings()


if __name__ == "__main__":
    main()
