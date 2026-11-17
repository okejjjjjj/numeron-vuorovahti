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
def replace_idempotent(content: str, old: str, new: str, label: str) -> str:
    if new in content:
        return content
    if old not in content:
        raise RuntimeError(f"Hakulohkoa ei löytynyt ({label})")
    return content.replace(old, new, 1)


def update_calendar_change_tracker():
    path = "app/src/main/java/fi/numeron/vuorovahti/CalendarChangeTracker.kt"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    orig = content

    old_model = """data class CalendarChangeItem(
    val id: String,
    val type: ChangeType,
    val calendarId: Long,
    val eventId: Long?, // Nykyisen kalenteritapahtuman ID (ADDED / MODIFIED)
    val title: String,
    val startMs: Long,
    val endMs: Long,
    val isAllDay: Boolean,
    // Edeltävät arvot kumoamista varten (MODIFIED / REMOVED)
    val prevTitle: String? = null,
    val prevStartMs: Long? = null,
    val prevEndMs: Long? = null,
    val prevIsAllDay: Boolean = false,
    val timestampMs: Long = System.currentTimeMillis()
) {
    fun toJson(): JSONObject = JSONObject().apply {
        put("id", id)
        put("type", type.name)
        put("calendarId", calendarId)
        put("eventId", eventId ?: -1L)
        put("title", title)
        put("startMs", startMs)
        put("endMs", endMs)
        put("isAllDay", isAllDay)
        if (prevTitle != null) put("prevTitle", prevTitle)
        if (prevStartMs != null) put("prevStartMs", prevStartMs)
        if (prevEndMs != null) put("prevEndMs", prevEndMs)
        put("prevIsAllDay", prevIsAllDay)
        put("timestampMs", timestampMs)
    }

    companion object {
        fun fromJson(obj: JSONObject): CalendarChangeItem {
            val evId = obj.optLong("eventId", -1L)
            return CalendarChangeItem(
                id = obj.getString("id"),
                type = ChangeType.valueOf(obj.getString("type")),
                calendarId = obj.getLong("calendarId"),
                eventId = if (evId > 0) evId else null,
                title = obj.getString("title"),
                startMs = obj.getLong("startMs"),
                endMs = obj.getLong("endMs"),
                isAllDay = obj.getBoolean("isAllDay"),
                prevTitle = if (obj.has("prevTitle")) obj.getString("prevTitle") else null,
                prevStartMs = if (obj.has("prevStartMs")) obj.getLong("prevStartMs") else null,
                prevEndMs = if (obj.has("prevEndMs")) obj.getLong("prevEndMs") else null,
                prevIsAllDay = obj.optBoolean("prevIsAllDay", false),
                timestampMs = obj.optLong("timestampMs", System.currentTimeMillis())
            )
        }
    }
}"""

    new_model = """data class CalendarChangeItem(
    val id: String,
    val type: ChangeType,
    val calendarId: Long,
    val eventId: Long?, // Nykyisen kalenteritapahtuman ID (ADDED / MODIFIED)
    val title: String,
    val startMs: Long,
    val endMs: Long,
    val isAllDay: Boolean,
    val location: String = "",
    val description: String = "",
    // Edeltävät arvot kumoamista ja vertailua varten (MODIFIED / REMOVED)
    val prevTitle: String? = null,
    val prevStartMs: Long? = null,
    val prevEndMs: Long? = null,
    val prevIsAllDay: Boolean = false,
    val prevLocation: String? = null,
    val prevDescription: String? = null,
    val timestampMs: Long = System.currentTimeMillis()
) {
    fun toJson(): JSONObject = JSONObject().apply {
        put("id", id)
        put("type", type.name)
        put("calendarId", calendarId)
        put("eventId", eventId ?: -1L)
        put("title", title)
        put("startMs", startMs)
        put("endMs", endMs)
        put("isAllDay", isAllDay)
        put("location", location)
        put("description", description)
        if (prevTitle != null) put("prevTitle", prevTitle)
        if (prevStartMs != null) put("prevStartMs", prevStartMs)
        if (prevEndMs != null) put("prevEndMs", prevEndMs)
        put("prevIsAllDay", prevIsAllDay)
        if (prevLocation != null) put("prevLocation", prevLocation)
        if (prevDescription != null) put("prevDescription", prevDescription)
        put("timestampMs", timestampMs)
    }

    companion object {
        fun fromJson(obj: JSONObject): CalendarChangeItem {
            val evId = obj.optLong("eventId", -1L)
            return CalendarChangeItem(
                id = obj.getString("id"),
                type = ChangeType.valueOf(obj.getString("type")),
                calendarId = obj.getLong("calendarId"),
                eventId = if (evId > 0) evId else null,
                title = obj.getString("title"),
                startMs = obj.getLong("startMs"),
                endMs = obj.getLong("endMs"),
                isAllDay = obj.getBoolean("isAllDay"),
                location = obj.optString("location", ""),
                description = obj.optString("description", ""),
                prevTitle = if (obj.has("prevTitle")) obj.getString("prevTitle") else null,
                prevStartMs = if (obj.has("prevStartMs")) obj.getLong("prevStartMs") else null,
                prevEndMs = if (obj.has("prevEndMs")) obj.getLong("prevEndMs") else null,
                prevIsAllDay = obj.optBoolean("prevIsAllDay", false),
                prevLocation = if (obj.has("prevLocation")) obj.getString("prevLocation") else null,
                prevDescription = if (obj.has("prevDescription")) obj.getString("prevDescription") else null,
                timestampMs = obj.optLong("timestampMs", System.currentTimeMillis())
            )
        }
    }
}"""

    content = replace_idempotent(content, old_model, new_model, "CalendarChangeItem model")

    old_format = """    fun formatChangeDisplay(item: CalendarChangeItem): String {
        val tag = when (item.type) {
            ChangeType.ADDED -> "[LISÄTTY]"
            ChangeType.MODIFIED -> "[MUOKATTU]"
            ChangeType.REMOVED -> "[POISTETTU]"
        }
        val dateFmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")
        val timeFmt = DateTimeFormatter.ofPattern("HH:mm")
        val whenStr = if (item.isAllDay) {
            val sDate = Instant.ofEpochMilli(item.startMs).atZone(ZoneOffset.UTC).toLocalDate()
            val eDate = Instant.ofEpochMilli(item.endMs).atZone(ZoneOffset.UTC).toLocalDate().minusDays(1)
            if (eDate.isAfter(sDate)) {
                "${sDate.format(dateFmt)} – ${eDate.format(dateFmt)} (koko päivä)"
            } else {
                "${sDate.format(dateFmt)} (koko päivä)"
            }
        } else {
            val sDt = Instant.ofEpochMilli(item.startMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
            val eDt = Instant.ofEpochMilli(item.endMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
            "${sDt.format(dateFmt)} klo ${sDt.format(timeFmt)}–${eDt.format(timeFmt)}"
        }
        return "$tag ${item.title}\\n$whenStr"
    }"""

    new_format = """    private fun formatRange(startMs: Long, endMs: Long, isAllDay: Boolean): String {
        val dateFmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")
        val timeFmt = DateTimeFormatter.ofPattern("HH:mm")
        return if (isAllDay) {
            val sDate = Instant.ofEpochMilli(startMs).atZone(ZoneOffset.UTC).toLocalDate()
            val eDate = Instant.ofEpochMilli(endMs).atZone(ZoneOffset.UTC).toLocalDate().minusDays(1)
            if (eDate.isAfter(sDate)) {
                "${sDate.format(dateFmt)} – ${eDate.format(dateFmt)} (koko päivä)"
            } else {
                "${sDate.format(dateFmt)} (koko päivä)"
            }
        } else {
            val sDt = Instant.ofEpochMilli(startMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
            val eDt = Instant.ofEpochMilli(endMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
            if (sDt.toLocalDate() == eDt.toLocalDate()) {
                "${sDt.format(dateFmt)} klo ${sDt.format(timeFmt)}–${eDt.format(timeFmt)}"
            } else {
                "${sDt.format(dateFmt)} klo ${sDt.format(timeFmt)} – ${eDt.format(dateFmt)} klo ${eDt.format(timeFmt)}"
            }
        }
    }

    private fun extractUserNote(desc: String): String {
        return desc.substringBefore(CalendarSyncHelper.EVENT_DESCRIPTION_TAG).trim()
    }

    fun buildModificationDiffLines(item: CalendarChangeItem): List<String> {
        if (item.type != ChangeType.MODIFIED) return emptyList()
        val diffs = mutableListOf<String>()

        val oldTitle = item.prevTitle?.trim()
        if (!oldTitle.isNullOrEmpty() && oldTitle != item.title.trim()) {
            diffs.add("Otsikko: $oldTitle → ${item.title}")
        }

        val prevStart = item.prevStartMs
        val prevEnd = item.prevEndMs
        if (prevStart != null && prevEnd != null &&
            (prevStart != item.startMs || prevEnd != item.endMs || item.prevIsAllDay != item.isAllDay)
        ) {
            val dateFmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")
            val timeFmt = DateTimeFormatter.ofPattern("HH:mm")
            if (!item.prevIsAllDay && !item.isAllDay) {
                val oldStartDt = Instant.ofEpochMilli(prevStart).atZone(ZoneId.systemDefault()).toLocalDateTime()
                val oldEndDt = Instant.ofEpochMilli(prevEnd).atZone(ZoneId.systemDefault()).toLocalDateTime()
                val newStartDt = Instant.ofEpochMilli(item.startMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
                val newEndDt = Instant.ofEpochMilli(item.endMs).atZone(ZoneId.systemDefault()).toLocalDateTime()

                if (oldStartDt.toLocalDate() == newStartDt.toLocalDate() &&
                    oldEndDt.toLocalDate() == newEndDt.toLocalDate()
                ) {
                    val oldTime = "klo ${oldStartDt.format(timeFmt)}–${oldEndDt.format(timeFmt)}"
                    val newTime = "klo ${newStartDt.format(timeFmt)}–${newEndDt.format(timeFmt)}"
                    diffs.add("Kellonaika (${newStartDt.format(dateFmt)}): $oldTime → $newTime")
                } else {
                    val oldFull = formatRange(prevStart, prevEnd, false)
                    val newFull = formatRange(item.startMs, item.endMs, false)
                    diffs.add("Ajankohta: $oldFull → $newFull")
                }
            } else {
                val oldFull = formatRange(prevStart, prevEnd, item.prevIsAllDay)
                val newFull = formatRange(item.startMs, item.endMs, item.isAllDay)
                diffs.add("Ajankohta: $oldFull → $newFull")
            }
        }

        val oldLoc = item.prevLocation?.trim()
        val newLoc = item.location.trim()
        if (oldLoc != null && oldLoc != newLoc) {
            val fromStr = oldLoc.ifEmpty { "(tyhjä)" }
            val toStr = newLoc.ifEmpty { "(tyhjä)" }
            diffs.add("Sijainti: $fromStr → $toStr")
        }

        val prevDescRaw = item.prevDescription
        if (prevDescRaw != null) {
            val oldNote = extractUserNote(prevDescRaw)
            val newNote = extractUserNote(item.description)
            if (oldNote != newNote) {
                val fromStr = oldNote.ifEmpty { "(tyhjä)" }
                val toStr = newNote.ifEmpty { "(tyhjä)" }
                diffs.add("Lisätiedot: $fromStr → $toStr")
            }
        }

        return diffs
    }

    fun formatNotificationLine(item: CalendarChangeItem): String {
        val whenStr = formatRange(item.startMs, item.endMs, item.isAllDay)
        return when (item.type) {
            ChangeType.ADDED -> "+ ${item.title} ($whenStr)"
            ChangeType.REMOVED -> "- ${item.title} ($whenStr)"
            ChangeType.MODIFIED -> {
                val diffs = buildModificationDiffLines(item)
                if (diffs.isNotEmpty()) {
                    "~ ${item.title}: ${diffs.joinToString("; ")}"
                } else {
                    "~ ${item.title} ($whenStr)"
                }
            }
        }
    }

    fun formatChangeDisplay(item: CalendarChangeItem): String {
        val tag = when (item.type) {
            ChangeType.ADDED -> "[LISÄTTY]"
            ChangeType.MODIFIED -> "[MUOKATTU]"
            ChangeType.REMOVED -> "[POISTETTU]"
        }
        val whenStr = formatRange(item.startMs, item.endMs, item.isAllDay)
        if (item.type == ChangeType.MODIFIED) {
            val diffs = buildModificationDiffLines(item)
            if (diffs.isNotEmpty()) {
                return "$tag ${item.title}\\n$whenStr\\n${diffs.joinToString("\\n")}"
            }
        }
        return "$tag ${item.title}\\n$whenStr"
    }"""

    content = replace_idempotent(content, old_format, new_format, "formatChangeDisplay diff output")

    old_revert_mod = """                        val values = ContentValues().apply {
                            put(CalendarContract.Events.TITLE, prevTitle)
                            put(CalendarContract.Events.DTSTART, prevStart)
                            put(CalendarContract.Events.DTEND, prevEnd)
                            put(CalendarContract.Events.ALL_DAY, if (item.prevIsAllDay) 1 else 0)
                            put(
                                CalendarContract.Events.EVENT_TIMEZONE,
                                if (item.prevIsAllDay) "UTC" else ZoneId.systemDefault().id
                            )
                        }"""

    new_revert_mod = """                        val values = ContentValues().apply {
                            put(CalendarContract.Events.TITLE, prevTitle)
                            if (item.prevLocation != null) {
                                put(CalendarContract.Events.EVENT_LOCATION, item.prevLocation)
                            }
                            if (item.prevDescription != null) {
                                put(CalendarContract.Events.DESCRIPTION, item.prevDescription)
                            }
                            put(CalendarContract.Events.DTSTART, prevStart)
                            put(CalendarContract.Events.DTEND, prevEnd)
                            put(CalendarContract.Events.ALL_DAY, if (item.prevIsAllDay) 1 else 0)
                            put(
                                CalendarContract.Events.EVENT_TIMEZONE,
                                if (item.prevIsAllDay) "UTC" else ZoneId.systemDefault().id
                            )
                        }"""

    content = replace_idempotent(content, old_revert_mod, new_revert_mod, "revertSingleChange location & description")

    if content != orig:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        print(f"Päivitetty: {path}")
    else:
        print(f"Jo ajan tasalla: {path}")


def update_calendar_sync_helper():
    path = "app/src/main/java/fi/numeron/vuorovahti/CalendarSyncHelper.kt"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    orig = content

    old_update_block = """                resolver.update(uri, values, null, null)

                detectedChanges.add(
                    CalendarChangeItem(
                        id = UUID.randomUUID().toString(),
                        type = ChangeType.MODIFIED,
                        calendarId = calendarId,
                        eventId = targetMatch.eventId,
                        title = desiredTitle,
                        startMs = effectiveStartMs,
                        endMs = newEndMs,
                        isAllDay = shift.isAllDayLeave,
                        prevTitle = targetMatch.title,
                        prevStartMs = targetMatch.startMs,
                        prevEndMs = targetMatch.endMs,
                        prevIsAllDay = targetMatch.isAllDay
                    )
                )"""

    new_update_block = """                resolver.update(uri, values, null, null)

                val contentChanged =
                    targetMatch.title != desiredTitle ||
                    targetMatch.location != shift.location ||
                    targetMatch.description != fullDescription ||
                    targetMatch.startMs != effectiveStartMs ||
                    targetMatch.endMs != newEndMs ||
                    targetMatch.isAllDay != shift.isAllDayLeave

                if (contentChanged) {
                    detectedChanges.add(
                        CalendarChangeItem(
                            id = UUID.randomUUID().toString(),
                            type = ChangeType.MODIFIED,
                            calendarId = calendarId,
                            eventId = targetMatch.eventId,
                            title = desiredTitle,
                            startMs = effectiveStartMs,
                            endMs = newEndMs,
                            isAllDay = shift.isAllDayLeave,
                            location = shift.location,
                            description = fullDescription,
                            prevTitle = targetMatch.title,
                            prevStartMs = targetMatch.startMs,
                            prevEndMs = targetMatch.endMs,
                            prevIsAllDay = targetMatch.isAllDay,
                            prevLocation = targetMatch.location,
                            prevDescription = targetMatch.description
                        )
                    )
                }"""

    content = replace_idempotent(content, old_update_block, new_update_block, "MODIFIED CalendarChangeItem details")

    old_add_block = """                detectedChanges.add(
                    CalendarChangeItem(
                        id = UUID.randomUUID().toString(),
                        type = ChangeType.ADDED,
                        calendarId = calendarId,
                        eventId = newEventId,
                        title = desiredTitle,
                        startMs = newStartMs,
                        endMs = newEndMs,
                        isAllDay = shift.isAllDayLeave
                    )
                )"""

    new_add_block = """                detectedChanges.add(
                    CalendarChangeItem(
                        id = UUID.randomUUID().toString(),
                        type = ChangeType.ADDED,
                        calendarId = calendarId,
                        eventId = newEventId,
                        title = desiredTitle,
                        startMs = newStartMs,
                        endMs = newEndMs,
                        isAllDay = shift.isAllDayLeave,
                        location = shift.location,
                        description = fullDescription
                    )
                )"""

    content = replace_idempotent(content, old_add_block, new_add_block, "ADDED CalendarChangeItem details")

    old_rem_block = """            detectedChanges.add(
                CalendarChangeItem(
                    id = UUID.randomUUID().toString(),
                    type = ChangeType.REMOVED,
                    calendarId = calendarId,
                    eventId = null,
                    title = removedEx.title,
                    startMs = removedEx.startMs,
                    endMs = removedEx.endMs,
                    isAllDay = removedEx.isAllDay,
                    prevTitle = removedEx.title,
                    prevStartMs = removedEx.startMs,
                    prevEndMs = removedEx.endMs,
                    prevIsAllDay = removedEx.isAllDay
                )
            )"""

    new_rem_block = """            detectedChanges.add(
                CalendarChangeItem(
                    id = UUID.randomUUID().toString(),
                    type = ChangeType.REMOVED,
                    calendarId = calendarId,
                    eventId = null,
                    title = removedEx.title,
                    startMs = removedEx.startMs,
                    endMs = removedEx.endMs,
                    isAllDay = removedEx.isAllDay,
                    location = removedEx.location,
                    description = removedEx.description,
                    prevTitle = removedEx.title,
                    prevStartMs = removedEx.startMs,
                    prevEndMs = removedEx.endMs,
                    prevIsAllDay = removedEx.isAllDay,
                    prevLocation = removedEx.location,
                    prevDescription = removedEx.description
                )
            )"""

    content = replace_idempotent(content, old_rem_block, new_rem_block, "REMOVED CalendarChangeItem details")

    if content != orig:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        print(f"Päivitetty: {path}")
    else:
        print(f"Jo ajan tasalla: {path}")


def update_shift_reminder_receiver():
    path = "app/src/main/java/fi/numeron/vuorovahti/ShiftReminderReceiver.kt"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    orig = content

    old_notif = """            val summary = CalendarChangeTracker.formatSummary(changes)
            val detailsLines = changes.take(5).joinToString("\\n") {
                val prefix = when (it.type) {
                    ChangeType.ADDED -> "+ "
                    ChangeType.MODIFIED -> "~ "
                    ChangeType.REMOVED -> "- "
                }
                "$prefix${it.title}"
            }"""

    new_notif = """            val summary = CalendarChangeTracker.formatSummary(changes)
            val shownItems = changes.take(6).map { CalendarChangeTracker.formatNotificationLine(it) }.toMutableList()
            if (changes.size > 6) {
                shownItems.add("...ja ${changes.size - 6} muuta muutosta")
            }
            val detailsLines = shownItems.joinToString("\\n")
            val collapsedText = shownItems.firstOrNull()
                ?: "Napauta muokataksesi tai peruaksesi yksittäisiä muutoksia\""""

    content = replace_idempotent(content, old_notif, new_notif, "ShiftReminderReceiver notification details")

    old_builder = """                .setContentTitle("Google-kalenteria päivitetty ($summary)")
                .setContentText("Napauta muokataksesi tai peruaksesi yksittäisiä muutoksia")
                .setStyle(NotificationCompat.BigTextStyle().bigText(detailsLines))"""

    new_builder = """                .setContentTitle("Google-kalenteria päivitetty ($summary)")
                .setContentText(collapsedText)
                .setStyle(NotificationCompat.BigTextStyle().bigText(detailsLines))"""

    content = replace_idempotent(content, old_builder, new_builder, "ShiftReminderReceiver NotificationCompat text")

    if content != orig:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        print(f"Päivitetty: {path}")
    else:
        print(f"Jo ajan tasalla: {path}")
# ==============================================================================
# === POISTETTAVA KORJAUSOSIO PÄÄTTYY ===
# ==============================================================================


if __name__ == "__main__":
    bump_version_code()
    update_calendar_change_tracker()
    update_calendar_sync_helper()
    update_shift_reminder_receiver()
