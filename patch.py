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


def patch_shift_reminder_receiver() -> None:
    path = find_file("ShiftReminderReceiver.kt")
    src = path.read_text(encoding="utf-8")

    old_fn = r"""        fun computeNextOfficeHourSyncMs(nowMs: Long = System.currentTimeMillis()): Long {
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
        }"""

    new_fn = r"""        fun computeNextOfficeHourSyncMs(nowMs: Long = System.currentTimeMillis()): Long {
            val zone = java.time.ZoneId.systemDefault()
            val now = java.time.Instant.ofEpochMilli(nowMs).atZone(zone).toLocalDateTime()
            val baseDate = now.toLocalDate()
            val minAllowed = now.plusMinutes(5)
            val windows = listOf(
                Pair(java.time.LocalTime.of(10, 15), java.time.LocalTime.of(11, 0)),
                Pair(java.time.LocalTime.of(14, 30), java.time.LocalTime.of(15, 0))
            )

            for (dayOffset in 0..7) {
                val date = baseDate.plusDays(dayOffset.toLong())
                val dow = date.dayOfWeek
                if (dow == java.time.DayOfWeek.SATURDAY || dow == java.time.DayOfWeek.SUNDAY) continue
                for ((startTime, endTime) in windows) {
                    val windowStart = java.time.LocalDateTime.of(date, startTime)
                    if (dayOffset == 0 && !now.isBefore(windowStart)) continue

                    val windowEnd = java.time.LocalDateTime.of(date, endTime)
                    val earliest = if (minAllowed.isAfter(windowStart)) minAllowed else windowStart
                    val spanSeconds = java.time.Duration.between(earliest, windowEnd).seconds.coerceAtLeast(0L)
                    val randomOffsetSec = if (spanSeconds > 0L) {
                        kotlin.random.Random.nextLong(0L, spanSeconds + 1L)
                    } else {
                        0L
                    }
                    val candidate = earliest.plusSeconds(randomOffsetSec)
                    return candidate.atZone(zone).toInstant().toEpochMilli()
                }
            }
            return nowMs + TimeUnit.HOURS.toMillis(12)
        }"""

    src = replace_exact(path, src, old_fn, new_fn)
    verify_kotlin_delimiters(path, src)
    path.write_text(src, encoding="utf-8")
    print(f"Päivitetty: {path}")


def patch_settings_dialog_helper() -> None:
    path = find_file("SettingsDialogHelper.kt")
    src = path.read_text(encoding="utf-8")

    new_str = 'if (en) "Weekdays at 10:15–11:00 and 14:30–15:00" else "Arkisin klo 10:15–11:00 ja 14:30–15:00"'
    updated = re.sub(
        r'if \(en\) "Weekdays [^"]+" else "Arkisin [^"]+"',
        new_str,
        src
    )
    if updated == src:
        raise RuntimeError("[SettingsDialogHelper.kt] Korvattavia aikataulutekstejä ei löytynyt.")

    verify_kotlin_delimiters(path, updated)
    path.write_text(updated, encoding="utf-8")
    print(f"Päivitetty: {path}")


def main() -> None:
    patch_shift_reminder_receiver()
    patch_settings_dialog_helper()
    increment_version()


if __name__ == "__main__":
    main()
