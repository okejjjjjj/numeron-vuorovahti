#!/usr/bin/env python3
"""
Numeron Vuorovahti – patch 4:
- MainActivity: erottaa CSS- ja DOM-alustuksen (onPageCommitVisible vs. onPageFinished),
  varmistaa observerien kiinnittymisen sekä lisää vuorojen värikoodauksen kuukausi- ja luettelonäkymään
- DemoModeHelper: samat vuorovärit demotilan kuukausinäkymään
- CalendarSyncHelper: kaksivaiheinen täsmäytys saman päivän useille vuoroille +
  muistutusten päivitys tulevien tapahtumien poiston yhteydessä
- NumeronParser: kuun vaihteen yli ulottuva yövuoro 1. päivän aamuyönä
- BackgroundAuthHelper: stopAfterRedirect = true taustakirjautumisessa
- ShiftReminderReceiver: toiveilmoitusten turvallinen ID-avaruus
- CalendarChangeTracker: vanhojen muutoslokimerkintöjen automaattinen karsinta
- QuickStampActivity: taustan vahinkosulkemisen esto aktiivisen leimauksen aikana
- build.gradle.kts: versionCode 116 / versionName 3.2.12

Käyttö:
    python3 patch.py --dry-run
    python3 patch.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

IGNORED_DIRS = {".git", ".gradle", ".idea", ".patch_backups", "build", "node_modules", "__pycache__"}


def find_file(root: Path, filename: str, must_contain: str | None = None) -> Path:
    matches: list[Path] = []
    for p in root.rglob(filename):
        if any(part in IGNORED_DIRS for part in p.parts):
            continue
        if must_contain is None or must_contain in p.read_text(encoding="utf-8", errors="ignore"):
            matches.append(p)
    if len(matches) != 1:
        raise RuntimeError(
            f"Odotettiin täsmälleen yhtä '{filename}'-tiedostoa, löytyi {len(matches)}: {matches}"
        )
    return matches[0]


def replace_once(content: str, old: str, new: str, label: str) -> str:
    count = content.count(old)
    if count != 1:
        raise RuntimeError(
            f"[{label}] Odotettiin 1 osumaa, löytyi {count}. Tarkista tiedoston versio."
        )
    return content.replace(old, new, 1)


def patch_build_gradle(text: str) -> str:
    text = replace_once(text, "versionCode = 115", "versionCode = 116", "build.gradle:versionCode")
    text = replace_once(text, 'versionName = "3.2.11"', 'versionName = "3.2.12"', "build.gradle:versionName")
    return text


def patch_background_auth_helper(text: str) -> str:
    return replace_once(
        text,
        r'''            // 2. Lähetä kirjautumislomake (pysäytetään 302-ohjaukseen ilman raskaan kohdesivun latausta)
            val loginResp = executeRequest(
                urlString = postUrl,
                method = "POST",
                cookieStore = cookieStore,
                postBody = encodedBody,
                stopAfterRedirect = false
            ) ?: return@withContext false''',
        r'''            // 2. Lähetä kirjautumislomake (pysäytetään 302-ohjaukseen ilman raskaan kohdesivun latausta)
            val loginResp = executeRequest(
                urlString = postUrl,
                method = "POST",
                cookieStore = cookieStore,
                postBody = encodedBody,
                stopAfterRedirect = true
            ) ?: return@withContext false''',
        "BackgroundAuthHelper:stopAfterRedirect_true",
    )


def patch_main_activity(text: str) -> str:
    text = replace_once(
        text,
        r'''            override fun onPageCommitVisible(view: WebView?, url: String?) {
                super.onPageCommitVisible(view, url)
                if (url != null && !url.startsWith("https://demo.local/")) {
                    injectDarkTheme(view)
                }
            }''',
        r'''            override fun onPageCommitVisible(view: WebView?, url: String?) {
                super.onPageCommitVisible(view, url)
                if (url != null && !url.startsWith("https://demo.local/")) {
                    injectDarkTheme(view, forceDomInit = false)
                }
            }''',
        "MainActivity:onPageCommitVisible_forceDomInit",
    )

    text = replace_once(
        text,
        r'''                injectDarkTheme(view)
                CookieManager.getInstance().flush()''',
        r'''                injectDarkTheme(view, forceDomInit = true)
                CookieManager.getInstance().flush()''',
        "MainActivity:onPageFinished_forceDomInit",
    )

    text = replace_once(
        text,
        r'''        private fun injectDarkTheme(view: WebView?) {
        val currentUrl = view?.url
        val nowMs = System.currentTimeMillis()
        if (!currentUrl.isNullOrEmpty() && currentUrl == lastThemedUrl && (nowMs - lastThemedAtMs) < 1500L) {
            return
        }
        lastThemedUrl = currentUrl
        lastThemedAtMs = nowMs''',
        r'''    private fun injectDarkTheme(view: WebView?, forceDomInit: Boolean = false) {
        val currentUrl = view?.url
        val nowMs = System.currentTimeMillis()
        if (!forceDomInit && !currentUrl.isNullOrEmpty() && currentUrl == lastThemedUrl && (nowMs - lastThemedAtMs) < 1500L) {
            return
        }
        lastThemedUrl = currentUrl
        lastThemedAtMs = nowMs

        val themePrefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val morningRgb = themePrefs.getInt("color_morning_rgb", SettingsDialogHelper.DEFAULT_MORNING_RGB)
        val eveningRgb = themePrefs.getInt("color_evening_rgb", SettingsDialogHelper.DEFAULT_EVENING_RGB)
        val nightRgb = themePrefs.getInt("color_night_rgb", SettingsDialogHelper.DEFAULT_NIGHT_RGB)
        fun rgbToHex(rgb: Int): String = String.format("#%06X", 0xFFFFFF and rgb)
        fun contrastFg(rgb: Int): String {
            val lum = 0.299 * Color.red(rgb) + 0.587 * Color.green(rgb) + 0.114 * Color.blue(rgb)
            return if (lum > 150.0) "#0F1722" else "#FFFFFF"
        }
        val morningBg = rgbToHex(morningRgb)
        val morningFg = contrastFg(morningRgb)
        val eveningBg = rgbToHex(eveningRgb)
        val eveningFg = contrastFg(eveningRgb)
        val nightBg = rgbToHex(nightRgb)
        val nightFg = contrastFg(nightRgb)''',
        "MainActivity:injectDarkTheme_header_and_colors",
    )

    text = replace_once(
        text,
        r'''                    applyShiftFormat();
                    if (!window._todayShiftObserverInstalled) {
                        window._todayShiftObserverInstalled = true;
                        var target = document.querySelector('.punching-shift-container') || document.body;
                        if (target && typeof MutationObserver !== 'undefined') {
                            var obs = new MutationObserver(function() {
                                applyShiftFormat();
                            });
                            obs.observe(target, { childList: true, subtree: true, characterData: true });
                        }
                    }''',
        r'''                    applyShiftFormat();
                    if (typeof MutationObserver !== 'undefined') {
                        var shiftTarget = document.querySelector('.punching-shift-container');
                        if (shiftTarget && !shiftTarget._vvShiftObs) {
                            shiftTarget._vvShiftObs = true;
                            new MutationObserver(function() {
                                applyShiftFormat();
                            }).observe(shiftTarget, { childList: true, subtree: true, characterData: true });
                        }
                    }''',
        "MainActivity:todayShiftObserver_resilient",
    )

    text = replace_once(
        text,
        r'''                    checkSessionModal();
                    if (document.body && typeof MutationObserver !== 'undefined') {
                        var sessionObs = new MutationObserver(checkSessionModal);
                        sessionObs.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class'] });
                    }
                }''',
        r'''                    window._vvCheckSessionModal = checkSessionModal;
                    checkSessionModal();
                }
                if (window._vvCheckSessionModal && document.body && !document.body._vvSessionObs && typeof MutationObserver !== 'undefined') {
                    document.body._vvSessionObs = true;
                    new MutationObserver(window._vvCheckSessionModal).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class'] });
                }''',
        "MainActivity:sessionWatchObserver_resilient",
    )

    text = replace_once(
        text,
        r'''                    watchStampPageDom();
                }''',
        r'''                    window._vvWatchStampPageDom = watchStampPageDom;
                    watchStampPageDom();
                }
                if (typeof window._vvWatchStampPageDom === 'function') {
                    window._vvWatchStampPageDom();
                }''',
        "MainActivity:watchStampPageDom_rerun_on_finish",
    )

    text = replace_once(
        text,
        r'''                    function runCalendarCleanup() {
                        cleanMonthTable();
                        cleanListView();
                    }''',
        r'''                    function pickShiftColor(timesText) {
                        var m = (timesText || '').match(/(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})/);
                        if (!m) return null;
                        var sMin = parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
                        var eMin = parseInt(m[3], 10) * 60 + parseInt(m[4], 10);
                        var crossesMidnight = eMin < sMin;
                        if (crossesMidnight || sMin >= 20 * 60 || sMin < 4 * 60) {
                            return { bg: '$nightBg', fg: '$nightFg' };
                        }
                        if (sMin >= 11 * 60 + 30) {
                            return { bg: '$eveningBg', fg: '$eveningFg' };
                        }
                        return { bg: '$morningBg', fg: '$morningFg' };
                    }

                    function colorWorkShifts() {
                        var monthItems = document.querySelectorAll('.month-item.work');
                        for (var i = 0; i < monthItems.length; i++) {
                            var item = monthItems[i];
                            var timesEl = item.querySelector('.itemTimes');
                            var rawTimes = timesEl ? (timesEl.textContent || '') : (item.textContent || '');
                            var col = pickShiftColor(rawTimes);
                            if (col) {
                                item.style.setProperty('background-color', col.bg, 'important');
                                item.style.setProperty('color', col.fg, 'important');
                                if (timesEl) {
                                    timesEl.style.setProperty('color', col.fg, 'important');
                                }
                            }
                        }

                        var listItems = document.querySelectorAll('.schedule-item-container.schedule-item-work');
                        for (var j = 0; j < listItems.length; j++) {
                            var box = listItems[j];
                            var ltEl = box.querySelector('.schedule-item-times');
                            var lCol = pickShiftColor(ltEl ? (ltEl.textContent || '') : '');
                            if (lCol) {
                                box.style.setProperty('border-left-color', lCol.bg, 'important');
                            }
                        }
                    }

                    function runCalendarCleanup() {
                        cleanMonthTable();
                        cleanListView();
                        colorWorkShifts();
                    }''',
        "MainActivity:calendar_shift_color_coding",
    )
    return text


def patch_demo_mode_helper(text: str) -> str:
    return replace_once(
        text,
        r'''                val item = itemMap[cellDate]
                val itemHtml = when {
                    item == null -> ""
                    item.isAbsence -> """
                        <div class="month-item absence">
                            <span class="itemName">${item.label}</span>
                            <span class="itemTimes">${item.times}</span>
                        </div>
                    """.trimIndent()
                    else -> """
                        <div class="month-item work">
                            <span class="itemTimes">${item.times}</span>
                        </div>
                    """.trimIndent()
                }''',
        r'''                val item = itemMap[cellDate]
                val itemHtml = when {
                    item == null -> ""
                    item.isAbsence -> """
                        <div class="month-item absence">
                            <span class="itemName">${item.label}</span>
                            <span class="itemTimes">${item.times}</span>
                        </div>
                    """.trimIndent()
                    else -> {
                        val mRgb = prefs.getInt("color_morning_rgb", SettingsDialogHelper.DEFAULT_MORNING_RGB)
                        val eRgb = prefs.getInt("color_evening_rgb", SettingsDialogHelper.DEFAULT_EVENING_RGB)
                        val nRgb = prefs.getInt("color_night_rgb", SettingsDialogHelper.DEFAULT_NIGHT_RGB)
                        val tm = Regex("(\\d{1,2}):(\\d{2})\\s*-\\s*(\\d{1,2}):(\\d{2})").find(item.times)
                        val chosenRgb = if (tm != null) {
                            val sMin = tm.groupValues[1].toInt() * 60 + tm.groupValues[2].toInt()
                            val eMin = tm.groupValues[3].toInt() * 60 + tm.groupValues[4].toInt()
                            when {
                                eMin < sMin || sMin >= 20 * 60 || sMin < 4 * 60 -> nRgb
                                sMin >= 11 * 60 + 30 -> eRgb
                                else -> mRgb
                            }
                        } else {
                            mRgb
                        }
                        val bgHex = String.format("#%06X", 0xFFFFFF and chosenRgb)
                        val lum = 0.299 * android.graphics.Color.red(chosenRgb) +
                            0.587 * android.graphics.Color.green(chosenRgb) +
                            0.114 * android.graphics.Color.blue(chosenRgb)
                        val fgHex = if (lum > 150.0) "#0F1722" else "#FFFFFF"
                        """
                        <div class="month-item work" style="background-color:$bgHex;color:$fgHex;">
                            <span class="itemTimes" style="color:$fgHex;">${item.times}</span>
                        </div>
                    """.trimIndent()
                    }
                }''',
        "DemoModeHelper:demo_shift_color_coding",
    )


def patch_calendar_sync_helper(text: str) -> str:
    text = replace_once(
        text,
        r'''    private data class ExistingEvent(
        val eventId: Long,
        val title: String,
        val location: String,
        val description: String,
        val colorKey: String?,
        val startMs: Long,
        val endMs: Long,
        val isAllDay: Boolean,
        val isOwnedByApp: Boolean
    )''',
        r'''    private data class ExistingEvent(
        val eventId: Long,
        val title: String,
        val location: String,
        val description: String,
        val colorKey: String?,
        val startMs: Long,
        val endMs: Long,
        val isAllDay: Boolean,
        val isOwnedByApp: Boolean
    )

    private data class PreparedShift(
        val shift: WorkShift,
        val newStartMs: Long,
        val newEndMs: Long,
        val desiredTitle: String,
        val fullDescription: String,
        val desiredColorKey: String?
    )''',
        "CalendarSyncHelper:add_PreparedShift",
    )

    text = replace_once(
        text,
        r'''        val unmatchedOwned = ownedEvents.toMutableList()
        val unmatchedExternal = unownedCandidateEvents.toMutableList()
        val detectedChanges = mutableListOf<CalendarChangeItem>()

        for (shift in upcomingShifts) {
            val newStartMs = if (shift.isAllDayLeave) {
                shift.start.toInstant(ZoneOffset.UTC).toEpochMilli()
            } else {
                shift.start.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            }
            val newEndMs = if (shift.isAllDayLeave) {
                shift.end.toInstant(ZoneOffset.UTC).toEpochMilli()
            } else {
                shift.end.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            }
            val desiredTitle = formatShiftTitle(shift.title, userTag)
            val fullDescription = buildFullDescription(shift.description, userTag)
            val desiredColorKey = pickColorKeyForShift(shift, colorKeys)

            val exactMatch = unmatchedOwned.firstOrNull {
                it.title == desiredTitle &&
                it.location == shift.location &&
                it.description == fullDescription &&
                it.colorKey == desiredColorKey &&
                it.startMs == newStartMs &&
                it.endMs == newEndMs &&
                it.isAllDay == shift.isAllDayLeave
            }

            if (exactMatch != null) {
                unmatchedOwned.remove(exactMatch)
                continue
            }

            if (shift.isAllDayLeave) {
                val coveringOwned = unmatchedOwned.firstOrNull { ex ->
                    ex.isAllDay &&
                    ex.title.equals(desiredTitle, ignoreCase = true) &&
                    ex.startMs < newStartMs &&
                    ex.endMs == newEndMs
                }
                if (coveringOwned != null) {
                    unmatchedOwned.remove(coveringOwned)
                    continue
                }
                val coveringExternal = unmatchedExternal.firstOrNull { ex ->
                    ex.isAllDay &&
                    ex.title.equals(desiredTitle, ignoreCase = true) &&
                    ex.startMs < newStartMs &&
                    ex.endMs == newEndMs
                }
                if (coveringExternal != null) {
                    unmatchedExternal.remove(coveringExternal)
                    continue
                }
            }

            val sameDayOwned = unmatchedOwned.firstOrNull { ex ->
                ex.isAllDay == shift.isAllDayLeave &&
                isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave) &&
                (!shift.isAllDayLeave || ex.title.equals(desiredTitle, ignoreCase = true) || ex.startMs == newStartMs)
            } ?: unmatchedOwned.firstOrNull { ex ->
                shift.isAllDayLeave &&
                ex.isAllDay &&
                ex.title.equals(desiredTitle, ignoreCase = true) &&
                ex.startMs < newStartMs &&
                ex.endMs > newStartMs
            } ?: unmatchedOwned.firstOrNull { ex ->
                ex.isAllDay == shift.isAllDayLeave && isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave)
            }

            val sameDayExternal = if (sameDayOwned == null) {
                unmatchedExternal.firstOrNull { ex ->
                    ex.isAllDay == shift.isAllDayLeave &&
                    isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave) &&
                    looksLikeShiftOrLeave(ex.title, desiredTitle, userTag)
                }
            } else {
                null
            }

            val targetMatch = sameDayOwned ?: sameDayExternal

            if (targetMatch != null) {
                if (sameDayOwned != null) {
                    unmatchedOwned.remove(sameDayOwned)
                } else if (sameDayExternal != null) {
                    unmatchedExternal.remove(sameDayExternal)
                }

                val effectiveStartMs = if (shift.isAllDayLeave && targetMatch.startMs < newStartMs) {
                    targetMatch.startMs
                } else {
                    newStartMs
                }
                val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, targetMatch.eventId)
                val values = ContentValues().apply {
                    put(CalendarContract.Events.TITLE, desiredTitle)
                    put(CalendarContract.Events.EVENT_LOCATION, shift.location)
                    put(CalendarContract.Events.DESCRIPTION, fullDescription)
                    if (desiredColorKey != null) {
                        put(CalendarContract.Events.EVENT_COLOR_KEY, desiredColorKey)
                    } else {
                        putNull(CalendarContract.Events.EVENT_COLOR_KEY)
                    }
                    put(CalendarContract.Events.ALL_DAY, if (shift.isAllDayLeave) 1 else 0)
                    put(CalendarContract.Events.EVENT_TIMEZONE, if (shift.isAllDayLeave) "UTC" else TimeZone.getDefault().id)
                    put(CalendarContract.Events.DTSTART, effectiveStartMs)
                    put(CalendarContract.Events.DTEND, newEndMs)
                }
                resolver.update(uri, values, null, null)

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
                }
            } else {
                val values = ContentValues().apply {
                    put(CalendarContract.Events.CALENDAR_ID, calendarId)
                    put(CalendarContract.Events.TITLE, desiredTitle)
                    put(CalendarContract.Events.EVENT_LOCATION, shift.location)
                    put(CalendarContract.Events.DESCRIPTION, fullDescription)
                    if (desiredColorKey != null) {
                        put(CalendarContract.Events.EVENT_COLOR_KEY, desiredColorKey)
                    }
                    put(CalendarContract.Events.ALL_DAY, if (shift.isAllDayLeave) 1 else 0)
                    put(CalendarContract.Events.EVENT_TIMEZONE, if (shift.isAllDayLeave) "UTC" else TimeZone.getDefault().id)
                    put(CalendarContract.Events.DTSTART, newStartMs)
                    put(CalendarContract.Events.DTEND, newEndMs)
                }
                val insertedUri = resolver.insert(CalendarContract.Events.CONTENT_URI, values)
                val newEventId = insertedUri?.lastPathSegment?.toLongOrNull()

                detectedChanges.add(
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
                )
            }
        }''',
        r'''        val unmatchedOwned = ownedEvents.toMutableList()
        val unmatchedExternal = unownedCandidateEvents.toMutableList()
        val detectedChanges = mutableListOf<CalendarChangeItem>()

        val preparedShifts = upcomingShifts.map { shift ->
            val newStartMs = if (shift.isAllDayLeave) {
                shift.start.toInstant(ZoneOffset.UTC).toEpochMilli()
            } else {
                shift.start.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            }
            val newEndMs = if (shift.isAllDayLeave) {
                shift.end.toInstant(ZoneOffset.UTC).toEpochMilli()
            } else {
                shift.end.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            }
            PreparedShift(
                shift = shift,
                newStartMs = newStartMs,
                newEndMs = newEndMs,
                desiredTitle = formatShiftTitle(shift.title, userTag),
                fullDescription = buildFullDescription(shift.description, userTag),
                desiredColorKey = pickColorKeyForShift(shift, colorKeys)
            )
        }

        // Vaihe 1: Tarkat osumat ja kattavat koko päivän lomat pois ennen saman päivän täsmäytystä
        val pendingShifts = mutableListOf<PreparedShift>()
        for (prep in preparedShifts) {
            val shift = prep.shift
            val exactMatch = unmatchedOwned.firstOrNull {
                it.title == prep.desiredTitle &&
                it.location == shift.location &&
                it.description == prep.fullDescription &&
                it.colorKey == prep.desiredColorKey &&
                it.startMs == prep.newStartMs &&
                it.endMs == prep.newEndMs &&
                it.isAllDay == shift.isAllDayLeave
            }
            if (exactMatch != null) {
                unmatchedOwned.remove(exactMatch)
                continue
            }

            if (shift.isAllDayLeave) {
                val coveringOwned = unmatchedOwned.firstOrNull { ex ->
                    ex.isAllDay &&
                    ex.title.equals(prep.desiredTitle, ignoreCase = true) &&
                    ex.startMs < prep.newStartMs &&
                    ex.endMs == prep.newEndMs
                }
                if (coveringOwned != null) {
                    unmatchedOwned.remove(coveringOwned)
                    continue
                }
                val coveringExternal = unmatchedExternal.firstOrNull { ex ->
                    ex.isAllDay &&
                    ex.title.equals(prep.desiredTitle, ignoreCase = true) &&
                    ex.startMs < prep.newStartMs &&
                    ex.endMs == prep.newEndMs
                }
                if (coveringExternal != null) {
                    unmatchedExternal.remove(coveringExternal)
                    continue
                }
            }

            pendingShifts.add(prep)
        }

        // Vaihe 2: Saman päivän täsmäytys (lähimmän aloitusajan mukaan) sekä uusien lisäys
        for (prep in pendingShifts) {
            val shift = prep.shift
            val newStartMs = prep.newStartMs
            val newEndMs = prep.newEndMs
            val desiredTitle = prep.desiredTitle
            val fullDescription = prep.fullDescription
            val desiredColorKey = prep.desiredColorKey

            val sameDayOwned = unmatchedOwned
                .filter { ex ->
                    ex.isAllDay == shift.isAllDayLeave &&
                    isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave) &&
                    (!shift.isAllDayLeave || ex.title.equals(desiredTitle, ignoreCase = true) || ex.startMs == newStartMs)
                }
                .minByOrNull { kotlin.math.abs(it.startMs - newStartMs) }
                ?: unmatchedOwned.firstOrNull { ex ->
                    shift.isAllDayLeave &&
                    ex.isAllDay &&
                    ex.title.equals(desiredTitle, ignoreCase = true) &&
                    ex.startMs < newStartMs &&
                    ex.endMs > newStartMs
                }
                ?: unmatchedOwned
                    .filter { ex ->
                        ex.isAllDay == shift.isAllDayLeave && isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave)
                    }
                    .minByOrNull { kotlin.math.abs(it.startMs - newStartMs) }

            val sameDayExternal = if (sameDayOwned == null) {
                unmatchedExternal
                    .filter { ex ->
                        ex.isAllDay == shift.isAllDayLeave &&
                        isSameCalendarDay(ex.startMs, newStartMs, shift.isAllDayLeave) &&
                        looksLikeShiftOrLeave(ex.title, desiredTitle, userTag)
                    }
                    .minByOrNull { kotlin.math.abs(it.startMs - newStartMs) }
            } else {
                null
            }

            val targetMatch = sameDayOwned ?: sameDayExternal

            if (targetMatch != null) {
                if (sameDayOwned != null) {
                    unmatchedOwned.remove(sameDayOwned)
                } else if (sameDayExternal != null) {
                    unmatchedExternal.remove(sameDayExternal)
                }

                val effectiveStartMs = if (shift.isAllDayLeave && targetMatch.startMs < newStartMs) {
                    targetMatch.startMs
                } else {
                    newStartMs
                }
                val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, targetMatch.eventId)
                val values = ContentValues().apply {
                    put(CalendarContract.Events.TITLE, desiredTitle)
                    put(CalendarContract.Events.EVENT_LOCATION, shift.location)
                    put(CalendarContract.Events.DESCRIPTION, fullDescription)
                    if (desiredColorKey != null) {
                        put(CalendarContract.Events.EVENT_COLOR_KEY, desiredColorKey)
                    } else {
                        putNull(CalendarContract.Events.EVENT_COLOR_KEY)
                    }
                    put(CalendarContract.Events.ALL_DAY, if (shift.isAllDayLeave) 1 else 0)
                    put(CalendarContract.Events.EVENT_TIMEZONE, if (shift.isAllDayLeave) "UTC" else TimeZone.getDefault().id)
                    put(CalendarContract.Events.DTSTART, effectiveStartMs)
                    put(CalendarContract.Events.DTEND, newEndMs)
                }
                resolver.update(uri, values, null, null)

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
                }
            } else {
                val values = ContentValues().apply {
                    put(CalendarContract.Events.CALENDAR_ID, calendarId)
                    put(CalendarContract.Events.TITLE, desiredTitle)
                    put(CalendarContract.Events.EVENT_LOCATION, shift.location)
                    put(CalendarContract.Events.DESCRIPTION, fullDescription)
                    if (desiredColorKey != null) {
                        put(CalendarContract.Events.EVENT_COLOR_KEY, desiredColorKey)
                    }
                    put(CalendarContract.Events.ALL_DAY, if (shift.isAllDayLeave) 1 else 0)
                    put(CalendarContract.Events.EVENT_TIMEZONE, if (shift.isAllDayLeave) "UTC" else TimeZone.getDefault().id)
                    put(CalendarContract.Events.DTSTART, newStartMs)
                    put(CalendarContract.Events.DTEND, newEndMs)
                }
                val insertedUri = resolver.insert(CalendarContract.Events.CONTENT_URI, values)
                val newEventId = insertedUri?.lastPathSegment?.toLongOrNull()

                detectedChanges.add(
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
                )
            }
        }''',
        "CalendarSyncHelper:two_phase_shift_matching",
    )

    text = replace_once(
        text,
        r'''        if (toDeleteIds.isNotEmpty()) {
            CalendarChangeTracker.saveChanges(context, emptyList())
        }
        return toDeleteIds.size''',
        r'''        if (toDeleteIds.isNotEmpty()) {
            CalendarChangeTracker.saveChanges(context, emptyList())
            scheduleShiftReminders(context, calendarId)
        }
        return toDeleteIds.size''',
        "CalendarSyncHelper:reschedule_after_delete",
    )
    return text


def patch_numeron_parser(text: str) -> str:
    return replace_once(
        text,
        r'''        for (cell in dayCells) {
            if (cell.hasClass("day-different-month")) continue

            val dayNum = cell.selectFirst(".dayNum")?.text()?.trim()?.toIntOrNull() ?: continue
            val date = LocalDate.of(currentYear, currentMonth, dayNum)

            // Sallitaan eilinen yövuorojen varalta, jotka päättyvät tänään nykyhetken jälkeen
            if (date.isBefore(today.minusDays(1))) continue''',
        r'''        val yesterday = today.minusDays(1)
        val allowPrevMonthOverflow = today.dayOfMonth == 1 &&
            currentYear == today.year &&
            currentMonth == today.monthValue
        val prevMonthYm = java.time.YearMonth.of(currentYear, currentMonth).minusMonths(1)

        for (cell in dayCells) {
            val dayNum = cell.selectFirst(".dayNum")?.text()?.trim()?.toIntOrNull() ?: continue
            val date = if (cell.hasClass("day-different-month")) {
                if (!allowPrevMonthOverflow || dayNum < 20 || dayNum > prevMonthYm.lengthOfMonth()) continue
                val overflowDate = prevMonthYm.atDay(dayNum)
                if (overflowDate != yesterday) continue
                overflowDate
            } else {
                try {
                    LocalDate.of(currentYear, currentMonth, dayNum)
                } catch (_: Exception) {
                    continue
                }
            }

            // Sallitaan eilinen yövuorojen varalta, jotka päättyvät tänään nykyhetken jälkeen
            if (date.isBefore(yesterday)) continue''',
        "NumeronParser:month_boundary_overnight_shift",
    )


def patch_shift_reminder_receiver(text: str) -> str:
    return replace_once(
        text,
        r'''            val pi = PendingIntent.getActivity(
                context, 3000 + id, openIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            val notif = NotificationCompat.Builder(context, channelId)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(title)
                .setContentText(body)
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                .setAutoCancel(true)
                .setContentIntent(pi)
                .build()
            nm.notify(3000 + id, notif)''',
        r'''            val notifId = 100_000 + (id and 0x7FFF)
            val pi = PendingIntent.getActivity(
                context, notifId, openIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            val notif = NotificationCompat.Builder(context, channelId)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(title)
                .setContentText(body)
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                .setAutoCancel(true)
                .setContentIntent(pi)
                .build()
            nm.notify(notifId, notif)''',
        "ShiftReminderReceiver:safe_request_notif_id",
    )


def patch_calendar_change_tracker(text: str) -> str:
    return replace_once(
        text,
        r'''            existing.add(item)
        }
        saveChanges(context, existing)''',
        r'''            existing.add(item)
        }
        val nowMs = System.currentTimeMillis()
        val maxAgeCutoffMs = nowMs - 30L * 24 * 60 * 60 * 1000L
        val endedCutoffMs = nowMs - 7L * 24 * 60 * 60 * 1000L
        val pruned = existing
            .filter { it.timestampMs >= maxAgeCutoffMs && it.endMs >= endedCutoffMs }
            .takeLast(50)
        saveChanges(context, pruned)''',
        "CalendarChangeTracker:prune_old_changes",
    )


def patch_quick_stamp_activity(text: str) -> str:
    return replace_once(
        text,
        r'''            setBackgroundColor(Color.TRANSPARENT)
            setOnClickListener {
                finishCleanly()
            }''',
        r'''            setBackgroundColor(Color.TRANSPARENT)
            setOnClickListener {
                if (isCompleted) {
                    finishCleanly()
                }
            }''',
        "QuickStampActivity:prevent_accidental_dismiss",
    )


PATCH_PLAN = [
    ("build.gradle.kts", 'applicationId = "com.numeron_vuorovahti"', patch_build_gradle),
    ("BackgroundAuthHelper.kt", "object BackgroundAuthHelper", patch_background_auth_helper),
    ("MainActivity.kt", "class MainActivity", patch_main_activity),
    ("DemoModeHelper.kt", "object DemoModeHelper", patch_demo_mode_helper),
    ("CalendarSyncHelper.kt", "object CalendarSyncHelper", patch_calendar_sync_helper),
    ("NumeronParser.kt", "object NumeronParser", patch_numeron_parser),
    ("ShiftReminderReceiver.kt", "class ShiftReminderReceiver", patch_shift_reminder_receiver),
    ("CalendarChangeTracker.kt", "object CalendarChangeTracker", patch_calendar_change_tracker),
    ("QuickStampActivity.kt", "class QuickStampActivity", patch_quick_stamp_activity),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Numeron Vuorovahti patch 4")
    parser.add_argument("--root", default=".", help="Projektin juurikansio")
    parser.add_argument("--dry-run", action="store_true", help="Tarkista muutokset kirjoittamatta tiedostoja")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    staged_writes: list[tuple[Path, str]] = []

    for filename, marker, patch_fn in PATCH_PLAN:
        path = find_file(root, filename, marker)
        raw_text = path.read_bytes().decode("utf-8")
        eol = "\r\n" if "\r\n" in raw_text else "\n"
        normalized = raw_text.replace("\r\n", "\n")

        patched = patch_fn(normalized)
        if patched == normalized:
            raise RuntimeError(f"[{filename}] Tiedostoon ei tullut muutoksia.")

        staged_writes.append((path, patched.replace("\n", eol)))
        print(f"OK: {path.relative_to(root)}")

    if args.dry_run:
        print(f"\nDRY-RUN OK: {len(staged_writes)} tiedostoa valmiina, mitään ei kirjoitettu.")
        return 0

    for path, final_text in staged_writes:
        path.write_text(final_text, encoding="utf-8")

    print(f"\nVALMIS: {len(staged_writes)} tiedostoa päivitetty onnistuneesti.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"VIRHE: {exc}", file=sys.stderr)
        sys.exit(1)
