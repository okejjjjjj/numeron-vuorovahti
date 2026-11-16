#!/usr/bin/env python3
import os
import re


# ==============================================================================
# PYSYVÄ OSIO: Versionumeron automaattinen nosto (+1)
# ==============================================================================
def bump_version_code():
    gradle_path = "app/build.gradle.kts"
    if not os.path.exists(gradle_path):
        print(f"Ohitetaan: {gradle_path} ei löytynyt.")
        return

    with open(gradle_path, "r", encoding="utf-8") as f:
        content = f.read()

    def increment(match):
        old_code = int(match.group(1))
        new_code = old_code + 1
        print(f"Päivitetään versionCode: {old_code} -> {new_code}")
        return f"versionCode = {new_code}"

    updated, count = re.subn(r"versionCode\s*=\s*(\d+)", increment, content, count=1)
    if count > 0:
        with open(gradle_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated)


# ==============================================================================
# === POISTETTAVA KORJAUSOSIO ALKAA (Poista kun muutokset on ajettu) ===
# ==============================================================================
def apply_fixes():
    # 1. MainActivity.kt: istunnon iän tarkistus (11 h) ja #session-expired-modal ohitus
    main_path = "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt"
    if os.path.exists(main_path):
        with open(main_path, "r", encoding="utf-8") as f:
            content = f.read()

        orig = content

        old_nav = """            startSnapshotTransition {
                val existingCookies = CookieManager.getInstance().getCookie(baseUrl)
                if (existingCookies.isNullOrBlank()) {
                    scope.launch {
                        BackgroundAuthHelper.ensureAuthenticatedSession(this@MainActivity)
                        webView.loadUrl(url)
                    }
                } else {
                    webView.loadUrl(url)
                }
            }"""

        new_nav = """            startSnapshotTransition {
                val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                val lastSessionMs = prefs.getLong("last_valid_session_ms", 0L)
                val sessionAgeMs = System.currentTimeMillis() - lastSessionMs
                val existingCookies = CookieManager.getInstance().getCookie(baseUrl)

                if (existingCookies.isNullOrBlank() || sessionAgeMs > 11L * 60 * 60 * 1000L) {
                    scope.launch {
                        val ok = BackgroundAuthHelper.ensureAuthenticatedSession(this@MainActivity)
                        if (ok) {
                            prefs.edit().putLong("last_valid_session_ms", System.currentTimeMillis()).apply()
                        }
                        webView.loadUrl(url)
                    }
                } else {
                    webView.loadUrl(url)
                }
            }"""

        if old_nav in content:
            content = content.replace(old_nav, new_nav, 1)

        old_finished = """                injectDarkTheme(view)
                CookieManager.getInstance().flush()

                when {"""

        new_finished = """                injectDarkTheme(view)
                CookieManager.getInstance().flush()
                if (!url.contains("/Login/", ignoreCase = true)) {
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                }

                when {"""

        if old_finished in content and "last_valid_session_ms" not in content:
            content = content.replace(old_finished, new_finished, 1)

        old_js_end = """                style.innerHTML = '$safeCss';
            })();"""

        new_js_end = """                style.innerHTML = '$safeCss';
                if (!window._sessionWatchInstalled) {
                    window._sessionWatchInstalled = true;
                    setInterval(function() {
                        var modal = document.getElementById('session-expired-modal');
                        if (modal && (modal.classList.contains('in') || modal.classList.contains('show') || modal.style.display === 'block')) {
                            window.location.href = '/Login/Login';
                        }
                    }, 300);
                }
            })();"""

        if old_js_end in content and "_sessionWatchInstalled" not in content:
            content = content.replace(old_js_end, new_js_end, 1)

        if content != orig:
            with open(main_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            print(f"Päivitetty: {main_path}")

    # 2. ShiftReminderReceiver.kt: virka-ajan ajoitus (ma-pe 09:30 ja 14:30) + välitön REPLACE
    receiver_path = "app/src/main/java/fi/numeron/vuorovahti/ShiftReminderReceiver.kt"
    if os.path.exists(receiver_path):
        with open(receiver_path, "r", encoding="utf-8") as f:
            rec = f.read()

        orig_rec = rec

        old_schedule = """        fun ensureBackgroundSyncScheduled(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val syncRequest = PeriodicWorkRequestBuilder<BackgroundSyncWorker>(12, TimeUnit.HOURS)
                .setConstraints(constraints)
                .build()

            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                "NumeronVuorovahtiSync",
                ExistingPeriodicWorkPolicy.KEEP,
                syncRequest
            )
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            if (prefs.getLong("next_calendar_sync_ms", 0L) <= System.currentTimeMillis()) {
                prefs.edit()
                    .putLong("next_calendar_sync_ms", System.currentTimeMillis() + TimeUnit.HOURS.toMillis(12))
                    .apply()
            }
        }"""

        new_schedule = """        fun computeNextOfficeHourSyncMs(nowMs: Long = System.currentTimeMillis()): Long {
            val zone = java.time.ZoneId.systemDefault()
            val now = java.time.Instant.ofEpochMilli(nowMs).atZone(zone).toLocalDateTime()
            val candidateDate = now.toLocalDate()
            val slots = listOf(java.time.LocalTime.of(9, 30), java.time.LocalTime.of(14, 30))

            for (dayOffset in 0..7) {
                val date = candidateDate.plusDays(dayOffset.toLong())
                val dow = date.dayOfWeek
                if (dow == java.time.DayOfWeek.SATURDAY || dow == java.time.DayOfWeek.SUNDAY) continue
                for (slot in slots) {
                    val candidate = java.time.LocalDateTime.of(date, slot)
                    if (candidate.isAfter(now.plusMinutes(5))) {
                        return candidate.atZone(zone).toInstant().toEpochMilli()
                    }
                }
            }
            return nowMs + TimeUnit.HOURS.toMillis(12)
        }

        fun ensureBackgroundSyncScheduled(context: Context) {
            val nowMs = System.currentTimeMillis()
            val nextTargetMs = computeNextOfficeHourSyncMs(nowMs)
            val delayMs = (nextTargetMs - nowMs).coerceAtLeast(60_000L)

            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val syncRequest = androidx.work.OneTimeWorkRequestBuilder<BackgroundSyncWorker>()
                .setInitialDelay(delayMs, TimeUnit.MILLISECONDS)
                .setConstraints(constraints)
                .build()

            WorkManager.getInstance(context).enqueueUniqueWork(
                "NumeronVuorovahtiSync",
                androidx.work.ExistingWorkPolicy.REPLACE,
                syncRequest
            )

            context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                .edit()
                .putLong("next_calendar_sync_ms", nextTargetMs)
                .apply()
        }"""

        if old_schedule in rec:
            rec = rec.replace(old_schedule, new_schedule, 1)

        old_worker_reschedule = """            CalendarSyncHelper.scheduleShiftReminders(appContext, calId)
            val nowMs = System.currentTimeMillis()
            prefs.edit()
                .putLong("last_calendar_sync_ms", nowMs)
                .putLong("next_calendar_sync_ms", nowMs + TimeUnit.HOURS.toMillis(12))
                .apply()
            Result.success()"""

        new_worker_reschedule = """            CalendarSyncHelper.scheduleShiftReminders(appContext, calId)
            val nowMs = System.currentTimeMillis()
            prefs.edit()
                .putLong("last_calendar_sync_ms", nowMs)
                .putLong("last_valid_session_ms", nowMs)
                .apply()
            ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext)
            Result.success()"""

        if old_worker_reschedule in rec:
            rec = rec.replace(old_worker_reschedule, new_worker_reschedule, 1)

        old_worker_retry = """        } else {
            Result.retry()
        }"""

        new_worker_retry = """        } else {
            ShiftReminderReceiver.ensureBackgroundSyncScheduled(appContext)
            Result.success()
        }"""

        if old_worker_retry in rec and "computeNextOfficeHourSyncMs" in rec:
            rec = rec.replace(old_worker_retry, new_worker_retry, 1)

        if rec != orig_rec:
            with open(receiver_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(rec)
            print(f"Päivitetty: {receiver_path}")

    # 3. SettingsDialogHelper.kt: päivitä varateksti virka-ajan mukaiseksi
    settings_path = "app/src/main/java/fi/numeron/vuorovahti/SettingsDialogHelper.kt"
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            set_content = f.read()

        old_label = '"Automaattinen tarkistus (12 h välein)"'
        new_label = '"Arkisin klo 09:30 ja 14:30"'
        if old_label in set_content:
            set_content = set_content.replace(old_label, new_label, 1)
            with open(settings_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(set_content)
            print(f"Päivitetty: {settings_path}")
# ==============================================================================
# === POISTETTAVA KORJAUSOSIO PÄÄTTYY ===
# ==============================================================================


if __name__ == "__main__":
    bump_version_code()
    apply_fixes()
