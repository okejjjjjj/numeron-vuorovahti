#!/usr/bin/env python3
"""
Numeron Vuorovahti – jatkokorjaukset ja parannukset (patch 2).
Olettaa, että ensimmäinen patch.py on jo ajettu.

Käyttö:
    python3 patch.py --dry-run   # Tarkistaa osumat muuttamatta tiedostoja
    python3 patch.py             # Ajaa muutokset
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

IGNORED_DIRS = {".git", ".patch_backups", ".gradle", ".idea", "build", "node_modules", "__pycache__"}

DATA_EXTRACTION_RULES_XML = '''<?xml version="1.0" encoding="utf-8"?>
<data-extraction-rules>
    <cloud-backup>
        <exclude domain="sharedpref" path="secure_numeron_prefs.xml" />
    </cloud-backup>
    <device-transfer>
        <exclude domain="sharedpref" path="secure_numeron_prefs.xml" />
    </device-transfer>
</data-extraction-rules>
'''


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
    text = replace_once(text, "versionCode = 113", "versionCode = 114", "build.gradle:versionCode")
    text = replace_once(text, 'versionName = "3.2.9"', 'versionName = "3.2.10"', "build.gradle:versionName")
    return text


def patch_manifest(text: str) -> str:
    text = replace_once(
        text,
        r'''<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="fi.numeron.vuorovahti">''',
        r'''<manifest xmlns:android="http://schemas.android.com/apk/res/android">''',
        "AndroidManifest:remove_deprecated_package",
    )

    text = replace_once(
        text,
        r'''<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
    <uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />''',
        r'''    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />''',
        "AndroidManifest:remove_battery_opt_permission",
    )

    text = replace_once(
        text,
        r'''    <application
        android:allowBackup="true"
        android:fullBackupContent="@xml/backup_rules"''',
        r'''    <application
        android:allowBackup="true"
        android:fullBackupContent="@xml/backup_rules"
        android:dataExtractionRules="@xml/data_extraction_rules"''',
        "AndroidManifest:add_data_extraction_rules",
    )
    return text


def patch_backup_rules(text: str) -> str:
    if "secure_numeron_prefs.xml" in text:
        return text
    return replace_once(
        text,
        "</full-backup-content>",
        '    <exclude domain="sharedpref" path="secure_numeron_prefs.xml" />\n</full-backup-content>',
        "backup_rules:exclude_secure_prefs",
    )


def patch_calendar_sync_helper(text: str) -> str:
    text = replace_once(
        text,
        r'''object CalendarSyncHelper {

    const val EVENT_DESCRIPTION_TAG = "Synkronoitu Numeron Vuorovahti -sovelluksesta"''',
        r'''object CalendarSyncHelper {

    const val EVENT_DESCRIPTION_TAG = "Synkronoitu Numeron Vuorovahti -sovelluksesta"
    private val syncLock = Any()''',
        "CalendarSyncHelper:syncLock_field",
    )

    text = replace_once(
        text,
        r'''    fun syncShiftsToCalendar(context: Context, calendarId: Long, shifts: List<WorkShift>): List<CalendarChangeItem> {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_CALENDAR) != PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return emptyList()
        }

        val resolver = context.contentResolver
        val now = LocalDateTime.now()
        val nowMs = now.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
        val colorKeys = resolveGoogleShiftColorKeys(context, calendarId)
        val userTag = getUserTag(context)

        // Jo alkaneita työvuoroja ei ylikirjoiteta toteutuneilla leimausajoilla;
        // koko päivän lomat huomioidaan päättymishetkeen saakka.
        val upcomingShifts = shifts.filter { shift ->
            if (shift.isAllDayLeave) shift.end.isAfter(now) else shift.start.isAfter(now)
        }''',
        r'''    fun syncShiftsToCalendar(
        context: Context,
        calendarId: Long,
        shifts: List<WorkShift>
    ): List<CalendarChangeItem> = synchronized(syncLock) {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_CALENDAR) != PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return@synchronized emptyList()
        }

        val resolver = context.contentResolver
        val now = LocalDateTime.now()
        val today = now.toLocalDate()
        val nowMs = now.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
        val todayStartUtcMs = today.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli()
        val queryMinEndMs = minOf(nowMs, todayStartUtcMs)
        val colorKeys = resolveGoogleShiftColorKeys(context, calendarId)
        val userTag = getUserTag(context)

        // Jo alkaneita työvuoroja ei ylikirjoiteta toteutuneilla leimausajoilla;
        // koko päivän lomat suodatetaan paikallisen päivän ja UTC-keskiyön mukaan.
        val upcomingShifts = shifts.filter { shift ->
            if (shift.isAllDayLeave) shift.end.toLocalDate().isAfter(today) else shift.start.isAfter(now)
        }''',
        "CalendarSyncHelper:lock_and_utc_allday_bounds",
    )

    text = replace_once(
        text,
        r'''        val selectionArgs = arrayOf(calendarId.toString(), nowMs.toString())

        resolver.query(CalendarContract.Events.CONTENT_URI, projection, selection, selectionArgs, null)?.use { c ->
            while (c.moveToNext()) {
                val id = c.getLong(0)
                val title = c.getString(1) ?: ""
                val loc = c.getString(2) ?: ""
                val desc = c.getString(3) ?: ""
                val cKey = c.getString(4)
                val sMs = c.getLong(5)
                val eMs = c.getLong(6)
                val allDay = c.getInt(7) == 1

                if (belongsToAnotherUser(desc, userTag)) {
                    continue
                }''',
        r'''        val selectionArgs = arrayOf(calendarId.toString(), queryMinEndMs.toString())

        resolver.query(CalendarContract.Events.CONTENT_URI, projection, selection, selectionArgs, null)?.use { c ->
            while (c.moveToNext()) {
                val id = c.getLong(0)
                val title = c.getString(1) ?: ""
                val loc = c.getString(2) ?: ""
                val desc = c.getString(3) ?: ""
                val cKey = c.getString(4)
                val sMs = c.getLong(5)
                val eMs = c.getLong(6)
                val allDay = c.getInt(7) == 1

                if (allDay && eMs <= todayStartUtcMs) continue
                if (!allDay && eMs <= nowMs) continue

                if (belongsToAnotherUser(desc, userTag)) {
                    continue
                }''',
        "CalendarSyncHelper:filter_existing_events_utc",
    )

    text = replace_once(
        text,
        r'''        for (removedEx in unmatchedOwned) {
            if (removedEx.startMs <= nowMs) continue''',
        r'''        for (removedEx in unmatchedOwned) {
            val alreadyStarted = if (removedEx.isAllDay) {
                removedEx.startMs <= todayStartUtcMs
            } else {
                removedEx.startMs <= nowMs
            }
            if (alreadyStarted) continue''',
        "CalendarSyncHelper:unmatchedOwned_utc_check",
    )

    text = replace_once(
        text,
        r'''        if (detectedChanges.isNotEmpty()) {
            CalendarChangeTracker.mergeChanges(context, detectedChanges)
        }

        return detectedChanges
    }''',
        r'''        if (detectedChanges.isNotEmpty()) {
            CalendarChangeTracker.mergeChanges(context, detectedChanges)
        }

        detectedChanges
    }''',
        "CalendarSyncHelper:synchronized_return",
    )
    return text


def patch_numeron_parser(text: str) -> str:
    text = replace_once(
        text,
        r'''                if (isTrainingAbsence(nameText)) {
                    for (offset in 0 until spanDays) {
                        trainingTitleByDate[date.plusDays(offset.toLong())] = nameText
                    }
                } else {''',
        r'''                if (isTrainingAbsence(nameText)) {
                    for (offset in 0 until spanDays) {
                        val targetDate = date.plusDays(offset.toLong())
                        if (targetDate.monthValue == currentMonth && targetDate.year == currentYear) {
                            trainingTitleByDate[targetDate] = nameText
                        }
                    }
                } else {''',
        "NumeronParser:training_month_boundary",
    )
    return text


def patch_main_activity(text: str) -> str:
    text = replace_once(
        text,
        r'''        setupWebView()
        setupBottomBar()
        handleIncomingIntent(intent)''',
        r'''        setupWebView()
        setupBottomBar()
        setupBackNavigation()
        handleIncomingIntent(intent)''',
        "MainActivity:register_back_navigation",
    )

    text = replace_once(
        text,
        r'''        btnNavClose.setOnClickListener {
            finishAndRemoveTask()
        }
    }''',
        r'''        btnNavClose.setOnClickListener {
            finishAndRemoveTask()
        }
    }

    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(
            this,
            object : androidx.activity.OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    if (::webView.isInitialized && webView.canGoBack()) {
                        startSnapshotTransition()
                        webView.goBack()
                    } else {
                        isEnabled = false
                        onBackPressedDispatcher.onBackPressed()
                    }
                }
            }
        )
    }''',
        "MainActivity:setupBackNavigation_impl",
    )

    text = replace_once(
        text,
        r'''        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 101)
        }
    }''',
        r'''        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 101)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 101 && grantResults.any { it == PackageManager.PERMISSION_GRANTED }) {
            CalendarSyncHelper.scheduleShiftReminders(this)
            ShiftReminderReceiver.ensureBackgroundSyncScheduled(this)
            val calGranted = ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.READ_CALENDAR
            ) == PackageManager.PERMISSION_GRANTED
            if (calGranted &&
                !DemoModeHelper.isDemoEnabled(this) &&
                !CalendarSyncHelper.hasCachedShifts(this) &&
                getBaseUrl().isNotEmpty()
            ) {
                ShiftReminderReceiver.triggerImmediateSync(this)
            }
        }
    }''',
        "MainActivity:onRequestPermissionsResult",
    )

    text = replace_once(
        text,
        r'''        webView.addJavascriptInterface(
            object {
                @android.webkit.JavascriptInterface
                fun onSessionExpired() {
                    runOnUiThread {
                        handleWebSessionExpired()
                    }
                }
            },
            "SessionBridge"
        )''',
        r'''        webView.addJavascriptInterface(
            object {
                @android.webkit.JavascriptInterface
                fun onSessionExpired() {
                    runOnUiThread {
                        handleWebSessionExpired()
                    }
                }

                @android.webkit.JavascriptInterface
                fun onSessionExpiringSoon() {
                    runOnUiThread {
                        handleWebSessionExpiringSoon()
                    }
                }
            },
            "SessionBridge"
        )''',
        "MainActivity:sessionBridge_expiring_soon",
    )

    text = replace_once(
        text,
        r'''            override fun onReceivedHttpError(
                view: WebView?,
                request: WebResourceRequest?,
                errorResponse: WebResourceResponse?
            ) {
                super.onReceivedHttpError(view, request, errorResponse)
                if (request?.isForMainFrame == true) {
                    endSnapshotTransition()
                    val status = errorResponse?.statusCode ?: 0
                    if (status >= 400) {
                        Toast.makeText(this@MainActivity, "Palvelinvirhe HTTP $status", Toast.LENGTH_LONG).show()
                    }
                }
            }''',
        r'''            override fun onReceivedHttpError(
                view: WebView?,
                request: WebResourceRequest?,
                errorResponse: WebResourceResponse?
            ) {
                super.onReceivedHttpError(view, request, errorResponse)
                if (request?.isForMainFrame == true) {
                    val status = errorResponse?.statusCode ?: 0
                    if (status == 401 || status == 403) {
                        handleWebSessionExpired()
                        return
                    }
                    endSnapshotTransition()
                    if (status >= 400) {
                        Toast.makeText(this@MainActivity, "Palvelinvirhe HTTP $status", Toast.LENGTH_LONG).show()
                    }
                }
            }''',
        "MainActivity:http_401_403_recovery",
    )

    text = replace_once(
        text,
        r'''            .alert-warning {
                background-color: #3B2810 !important;
                border-color: #F59E0B !important;
                color: #FEF3C7 !important;
            }''',
        r'''            .alert-warning {
                background-color: #3B2810 !important;
                border-color: #F59E0B !important;
                color: #FEF3C7 !important;
            }
            .alert-success {
                background-color: #0F2E26 !important;
                border-color: #10B981 !important;
                color: #D1FAE5 !important;
            }
            .alert-info {
                background-color: #1E3A5F !important;
                border-color: #38BDF8 !important;
                color: #E0F2FE !important;
            }
            .modal-header .close,
            .alert .close,
            button.close {
                color: #F1F5F9 !important;
                text-shadow: none !important;
                opacity: 0.85 !important;
            }''',
        "MainActivity:dark_theme_modal_close_and_alerts",
    )

    text = replace_once(
        text,
        r'''                    function checkSessionModal() {
                        if (window._sessionExpiredHandled) return;
                        var expired = false;
                        var candidates = document.querySelectorAll('#session-expired-modal, #sessionExpiredModal, #SessionExpiredModal, .modal, [role="dialog"]');
                        for (var i = 0; i < candidates.length; i++) {
                            var m = candidates[i];
                            var style = window.getComputedStyle(m);
                            var isVisible = (m.offsetParent !== null) || (style && style.display !== 'none' && style.visibility !== 'hidden' && parseFloat(style.opacity || '1') > 0);
                            if (!isVisible) continue;
                            var txt = (m.innerText || m.textContent || '').toLowerCase();
                            if (m.id === 'session-expired-modal' || m.id === 'sessionExpiredModal' || txt.indexOf('istunto vanhentunut') !== -1 || txt.indexOf('session expired') !== -1) {
                                expired = true;
                                break;
                            }
                        }
                        if (expired) {
                            window._sessionExpiredHandled = true;
                            if (window.SessionBridge && typeof window.SessionBridge.onSessionExpired === 'function') {
                                window.SessionBridge.onSessionExpired();
                            } else {
                                window.location.href = '/Login/Login';
                            }
                        }
                    }''',
        r'''                    function checkSessionModal() {
                        if (window._sessionExpiredHandled) return;
                        var expired = false;
                        var soonModal = null;
                        var candidates = document.querySelectorAll('#session-expired-modal, #sessionExpiredModal, #SessionExpiredModal, #session-expiring-soon-modal, .modal, [role="dialog"]');
                        for (var i = 0; i < candidates.length; i++) {
                            var m = candidates[i];
                            var style = window.getComputedStyle(m);
                            var isVisible = (m.offsetParent !== null) || (style && style.display !== 'none' && style.visibility !== 'hidden' && parseFloat(style.opacity || '1') > 0);
                            if (!isVisible) continue;
                            var txt = (m.innerText || m.textContent || '').toLowerCase();
                            if (m.id === 'session-expired-modal' || m.id === 'sessionExpiredModal' || txt.indexOf('istunto vanhentunut') !== -1 || txt.indexOf('session expired') !== -1) {
                                expired = true;
                                break;
                            }
                            if (m.id === 'session-expiring-soon-modal' || txt.indexOf('istunto päättyy pian') !== -1) {
                                soonModal = m;
                            }
                        }
                        if (expired) {
                            window._sessionExpiredHandled = true;
                            if (window.SessionBridge && typeof window.SessionBridge.onSessionExpired === 'function') {
                                window.SessionBridge.onSessionExpired();
                            } else {
                                window.location.href = '/Login/Login';
                            }
                        } else if (soonModal && !window._sessionExpiringHandled) {
                            window._sessionExpiringHandled = true;
                            try {
                                if (typeof window.HideSessionExpirationSoonNotify === 'function') {
                                    window.HideSessionExpirationSoonNotify();
                                }
                                if (window.jQuery) {
                                    window.jQuery(soonModal).modal('hide');
                                } else {
                                    soonModal.style.display = 'none';
                                }
                            } catch (_err) {}
                            if (window.SessionBridge && typeof window.SessionBridge.onSessionExpiringSoon === 'function') {
                                window.SessionBridge.onSessionExpiringSoon();
                            }
                        }
                    }''',
        "MainActivity:detect_session_expiring_soon",
    )

    text = replace_once(
        text,
        r'''                    var monthsFi = {
                        'tammikuu': 1, 'helmikuu': 2, 'maaliskuu': 3, 'huhtikuu': 4,
                        'toukokuu': 5, 'kesäkuu': 6, 'heinäkuu': 7, 'elokuu': 8,
                        'syyskuu': 9, 'lokakuu': 10, 'marraskuu': 11, 'joulukuu': 12
                    };''',
        r'''                    var monthsFi = {
                        'tammikuu': 1, 'helmikuu': 2, 'maaliskuu': 3, 'huhtikuu': 4,
                        'toukokuu': 5, 'kesäkuu': 6, 'heinäkuu': 7, 'elokuu': 8,
                        'syyskuu': 9, 'lokakuu': 10, 'marraskuu': 11, 'joulukuu': 12,
                        'january': 1, 'february': 2, 'march': 3, 'april': 4,
                        'may': 5, 'june': 6, 'july': 7, 'august': 8,
                        'september': 9, 'october': 10, 'november': 11, 'december': 12,
                        'januari': 1, 'februari': 2, 'mars': 3, 'maj': 5,
                        'juni': 6, 'juli': 7, 'augusti': 8, 'oktober': 10
                    };''',
        "MainActivity:quick_request_multilingual_months",
    )

    text = replace_once(
        text,
        r'''    private fun handleWebSessionExpired() {''',
        r'''    private fun handleWebSessionExpiringSoon() {
        val now = System.currentTimeMillis()
        if (now - lastSessionRecoveryMs < 15_000L) return
        lastSessionRecoveryMs = now
        val baseUrl = getBaseUrl()
        if (baseUrl.isEmpty() || DemoModeHelper.isDemoEnabled(this)) return

        scope.launch {
            val ok = BackgroundAuthHelper.ensureAuthenticatedSession(
                this@MainActivity,
                forceRefresh = true
            )
            if (ok) {
                getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                    .edit()
                    .putLong("last_valid_session_ms", System.currentTimeMillis())
                    .apply()
            }
        }
    }

    private fun handleWebSessionExpired() {''',
        "MainActivity:handleWebSessionExpiringSoon_impl",
    )

    text = replace_once(
        text,
        r'''        webView.evaluateJavascript("document.documentElement.outerHTML") { rawHtml ->
            if (rawHtml == null || rawHtml == "null") return@evaluateJavascript
            val unescapedHtml = JSONTokener(rawHtml).nextValue() as? String ?: return@evaluateJavascript''',
        r'''        webView.evaluateJavascript("document.documentElement.outerHTML") { rawHtml ->
            if (rawHtml == null || rawHtml == "null") return@evaluateJavascript
            val unescapedHtml = try {
                JSONTokener(rawHtml).nextValue() as? String
            } catch (_: Exception) {
                null
            } ?: run {
                pendingAction = Action.NONE
                collectedCalendarHtml.clear()
                return@evaluateJavascript
            }''',
        "MainActivity:handleCalendarPage_safe_json",
    )
    return text


def patch_calendar_change_tracker(text: str) -> str:
    text = replace_once(
        text,
        r'''            if (updateSingleEvent(context, item, titleStr, finalStartMs, finalEndMs, allDay)) {
                Toast.makeText(context, "Tapahtuma päivitetty kalenteriin", Toast.LENGTH_SHORT).show()
                dialog.dismiss()
                onSaved()
            } else {
                Toast.makeText(context, "Tapahtuman päivitys epäonnistui", Toast.LENGTH_SHORT).show()
            }''',
        r'''            btnSave.isEnabled = false
            val appCtx = context.applicationContext
            val exec = java.util.concurrent.Executors.newSingleThreadExecutor()
            exec.execute {
                val ok = try {
                    updateSingleEvent(appCtx, item, titleStr, finalStartMs, finalEndMs, allDay)
                } finally {
                    exec.shutdown()
                }
                android.os.Handler(android.os.Looper.getMainLooper()).post {
                    val act = context as? android.app.Activity
                    if (act != null && (act.isFinishing || act.isDestroyed)) return@post
                    if (ok) {
                        Toast.makeText(appCtx, "Tapahtuma päivitetty kalenteriin", Toast.LENGTH_SHORT).show()
                        if (dialog.isShowing) {
                            dialog.dismiss()
                        }
                        onSaved()
                    } else {
                        btnSave.isEnabled = true
                        Toast.makeText(appCtx, "Tapahtuman päivitys epäonnistui", Toast.LENGTH_SHORT).show()
                    }
                }
            }''',
        "CalendarChangeTracker:updateSingleEvent_off_main_thread",
    )
    return text


def patch_settings_dialog_helper(text: str) -> str:
    text = replace_once(
        text,
        r'''        fun openBatteryOptimizationSettings() {
            val pkgUri = android.net.Uri.parse("package:${context.packageName}")
            val isAlreadyIgnored = (context.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager)
                .isIgnoringBatteryOptimizations(context.packageName)
            val openedDirect = if (!isAlreadyIgnored) {
                launchSystemSettingsIntent(
                    android.content.Intent(
                        android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                        pkgUri
                    )
                )
            } else {
                false
            }
            if (!openedDirect) {
                val openedList = launchSystemSettingsIntent(
                    android.content.Intent(
                        android.provider.Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS
                    )
                )
                if (!openedList) {
                    launchSystemSettingsIntent(
                        android.content.Intent(
                            android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                            pkgUri
                        )
                    )
                }
            }
        }''',
        r'''        fun openBatteryOptimizationSettings() {
            val pkgUri = android.net.Uri.parse("package:${context.packageName}")
            val openedList = launchSystemSettingsIntent(
                android.content.Intent(
                    android.provider.Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS
                )
            )
            if (!openedList) {
                launchSystemSettingsIntent(
                    android.content.Intent(
                        android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        pkgUri
                    )
                )
            }
        }

        fun openNotificationSettings() {
            val pkgUri = android.net.Uri.parse("package:${context.packageName}")
            val notifIntent = android.content.Intent(
                android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS
            ).apply {
                putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, context.packageName)
            }
            if (!launchSystemSettingsIntent(notifIntent)) {
                launchSystemSettingsIntent(
                    android.content.Intent(
                        android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        pkgUri
                    )
                )
            }
        }

        fun areAppNotificationsAllowed(): Boolean {
            val hasRuntimePerm = android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.TIRAMISU ||
                ContextCompat.checkSelfPermission(
                    context,
                    Manifest.permission.POST_NOTIFICATIONS
                ) == PackageManager.PERMISSION_GRANTED
            return hasRuntimePerm &&
                androidx.core.app.NotificationManagerCompat.from(context).areNotificationsEnabled()
        }''',
        "SettingsDialogHelper:battery_and_notification_intents",
    )

    text = replace_once(
        text,
        r'''        statusCard.getChildAt(statusCard.childCount - 1).setOnClickListener {
            openBatteryOptimizationSettings()
        }''',
        r'''        statusCard.getChildAt(statusCard.childCount - 1).setOnClickListener {
            openBatteryOptimizationSettings()
        }

        val (notifPermValueTv, notifPermSubTv) = addStatusRow(
            statusCard,
            if (en) "Notification permission" else "Ilmoitusten tila",
            "",
            ""
        )
        statusCard.getChildAt(statusCard.childCount - 1).setOnClickListener {
            openNotificationSettings()
        }''',
        "SettingsDialogHelper:notif_status_row",
    )

    text = replace_once(
        text,
        r'''        val btnChanges = Button(context).apply {
            text = if (en) "Manage calendar changes" else "Hallitse kalenterimuutoksia"
            styleButton(this, "#233040", "#37475A", "#F1F5F9")
        }''',
        r'''        val pendingChangesCount = CalendarChangeTracker.getLastChanges(context).size
        val btnChanges = Button(context).apply {
            val baseLabel = if (en) "Manage calendar changes" else "Hallitse kalenterimuutoksia"
            text = if (pendingChangesCount > 0) "$baseLabel ($pendingChangesCount)" else baseLabel
            styleButton(this, "#233040", "#37475A", "#F1F5F9")
        }''',
        "SettingsDialogHelper:changes_count_badge",
    )

    text = replace_once(
        text,
        r'''            if (initialSyncCalendar && !newSyncCalendar) {
                val targetCalId = selectedCal?.id ?: CalendarSyncHelper.getTargetCalendarId(context)
                val futureCount = if (targetCalId != null) {
                    CalendarSyncHelper.countFutureSyncedEvents(context, targetCalId)
                } else {
                    0
                }
                if (targetCalId != null && futureCount > 0) {
                    AlertDialog.Builder(context)
                        .setTitle(if (en) "Delete calendar events?" else "Poistetaanko kalenterimerkinnät?")
                        .setMessage(
                            if (en) {
                                "Calendar sync was disabled. Do you want to delete the upcoming events added by this app to Google Calendar ($futureCount events)?"
                            } else {
                                "Kalenterisynkronointi otettiin pois käytöstä. Haluatko poistaa sovelluksen Google-kalenteriin lisäämät tulevat merkinnät ($futureCount kpl)?"
                            }
                        )
                        .setPositiveButton(if (en) "Delete events" else "Poista merkinnät") { _, _ ->
                            CalendarSyncHelper.deleteFutureSyncedEvents(context, targetCalId)
                            finishSave(forceSync = missingCacheForReminders)
                        }
                        .setNegativeButton(if (en) "Keep in calendar" else "Jätä kalenteriin") { _, _ ->
                            finishSave()
                        }
                        .setCancelable(false)
                        .show()
                } else {
                    finishSave()
                }
            } else {
                finishSave()
            }''',
        r'''            if (initialSyncCalendar && !newSyncCalendar) {
                btnSave.isEnabled = false
                val appCtx = context.applicationContext
                CoroutineScope(Dispatchers.IO).launch {
                    val targetCalId = selectedCal?.id ?: CalendarSyncHelper.getTargetCalendarId(appCtx)
                    val futureCount = if (targetCalId != null) {
                        CalendarSyncHelper.countFutureSyncedEvents(appCtx, targetCalId)
                    } else {
                        0
                    }
                    withContext(Dispatchers.Main) {
                        val act = context as? android.app.Activity
                        if (act != null && (act.isFinishing || act.isDestroyed)) return@withContext
                        if (targetCalId != null && futureCount > 0) {
                            AlertDialog.Builder(context)
                                .setTitle(if (en) "Delete calendar events?" else "Poistetaanko kalenterimerkinnät?")
                                .setMessage(
                                    if (en) {
                                        "Calendar sync was disabled. Do you want to delete the upcoming events added by this app to Google Calendar ($futureCount events)?"
                                    } else {
                                        "Kalenterisynkronointi otettiin pois käytöstä. Haluatko poistaa sovelluksen Google-kalenteriin lisäämät tulevat merkinnät ($futureCount kpl)?"
                                    }
                                )
                                .setPositiveButton(if (en) "Delete events" else "Poista merkinnät") { _, _ ->
                                    CoroutineScope(Dispatchers.IO).launch {
                                        CalendarSyncHelper.deleteFutureSyncedEvents(appCtx, targetCalId)
                                        withContext(Dispatchers.Main) {
                                            val curAct = context as? android.app.Activity
                                            if (curAct == null || (!curAct.isFinishing && !curAct.isDestroyed)) {
                                                finishSave(forceSync = missingCacheForReminders)
                                            }
                                        }
                                    }
                                }
                                .setNegativeButton(if (en) "Keep in calendar" else "Jätä kalenteriin") { _, _ ->
                                    finishSave()
                                }
                                .setCancelable(false)
                                .show()
                        } else {
                            finishSave()
                        }
                    }
                }
            } else {
                finishSave()
            }''',
        "SettingsDialogHelper:calendar_delete_off_main_thread",
    )

    text = replace_once(
        text,
        r'''            val nowIgnoringBattery = powerManager.isIgnoringBatteryOptimizations(context.packageName)
            if (nowIgnoringBattery) {
                batteryOptValueTv.text = if (en) "Unrestricted (background sync active)" else "Ei rajoitettu (taustasynkronointi aktiivinen)"
                batteryOptValueTv.setTextColor(Color.parseColor("#34D399"))
                batteryOptSubTv.text = if (en) "Tap to open battery settings" else "Napauta avataksesi virransäästöasetukset"
                batteryOptSubTv.visibility = View.VISIBLE
            } else {
                batteryOptValueTv.text = if (en) "Optimized – tap to remove restriction" else "Optimoitu – napauta poistaaksesi rajoitus"
                batteryOptValueTv.setTextColor(Color.parseColor("#F1F5F9"))
                batteryOptSubTv.text = if (en) "Ensures background sync works in sleep mode" else "Varmistaa tausta-ajojen toiminnan lepotilassa"
                batteryOptSubTv.visibility = View.VISIBLE
            }''',
        r'''            val nowIgnoringBattery = powerManager.isIgnoringBatteryOptimizations(context.packageName)
            if (nowIgnoringBattery) {
                batteryOptValueTv.text = if (en) "Unrestricted (background sync active)" else "Ei rajoitettu (taustasynkronointi aktiivinen)"
                batteryOptValueTv.setTextColor(Color.parseColor("#34D399"))
                batteryOptSubTv.text = if (en) "Tap to open battery settings" else "Napauta avataksesi virransäästöasetukset"
                batteryOptSubTv.visibility = View.VISIBLE
            } else {
                batteryOptValueTv.text = if (en) "Optimized – tap to remove restriction" else "Optimoitu – napauta poistaaksesi rajoitus"
                batteryOptValueTv.setTextColor(Color.parseColor("#F1F5F9"))
                batteryOptSubTv.text = if (en) "Ensures background sync works in sleep mode" else "Varmistaa tausta-ajojen toiminnan lepotilassa"
                batteryOptSubTv.visibility = View.VISIBLE
            }

            val notifsAllowed = areAppNotificationsAllowed()
            if (notifsAllowed) {
                notifPermValueTv.text = if (en) "Enabled" else "Käytössä"
                notifPermValueTv.setTextColor(Color.parseColor("#34D399"))
                notifPermSubTv.text = if (en) "Tap to open notification settings" else "Napauta avataksesi ilmoitusasetukset"
                notifPermSubTv.visibility = View.VISIBLE
            } else {
                notifPermValueTv.text = if (en) "Blocked – tap to enable" else "Estetty – napauta ottaaksesi käyttöön"
                notifPermValueTv.setTextColor(Color.parseColor("#F87171"))
                notifPermSubTv.text = if (en) "Required for shift and calendar alerts" else "Vaaditaan leimaus- ja kalenteri-ilmoituksiin"
                notifPermSubTv.visibility = View.VISIBLE
            }''',
        "SettingsDialogHelper:refresh_notif_status",
    )
    return text


def patch_shift_reminder_receiver(text: str) -> str:
    text = replace_once(
        text,
        r'''import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.RemoteViews
import android.widget.Toast
import androidx.core.app.NotificationCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.json.JSONTokener
import java.time.LocalDate
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume''',
        r'''import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.webkit.CookieManager
import android.widget.RemoteViews
import android.widget.Toast
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.NetworkType
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.time.LocalDate
import java.util.concurrent.TimeUnit''',
        "ShiftReminderReceiver:clean_imports",
    )

    text = replace_once(
        text,
        r'''        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channelId = "numeron_vuorovahti_reminders"

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "Työvuoro- ja kalenteri-ilmoitukset",
                NotificationManager.IMPORTANCE_HIGH
            )
            nm.createNotificationChannel(channel)
        }''',
        r'''        if (!canPostNotifications(context)) {
            if (!isTest && rescheduleNext) {
                CalendarSyncHelper.scheduleShiftReminders(context)
            }
            return
        }

        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channelId = "numeron_vuorovahti_reminders"

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "Työvuoro- ja kalenteri-ilmoitukset",
                NotificationManager.IMPORTANCE_HIGH
            )
            nm.createNotificationChannel(channel)
        }''',
        "ShiftReminderReceiver:check_notif_perm_reminder",
    )

    text = replace_once(
        text,
        r'''        const val NOTIF_ID_CALENDAR_CHANGES = 4001

        fun showCalendarChangesNotification(context: Context, changes: List<CalendarChangeItem>) {
            if (changes.isEmpty()) return''',
        r'''        const val NOTIF_ID_CALENDAR_CHANGES = 4001

        fun canPostNotifications(context: Context): Boolean {
            val hasPerm = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
                ContextCompat.checkSelfPermission(
                    context,
                    Manifest.permission.POST_NOTIFICATIONS
                ) == PackageManager.PERMISSION_GRANTED
            return hasPerm && NotificationManagerCompat.from(context).areNotificationsEnabled()
        }

        fun showCalendarChangesNotification(context: Context, changes: List<CalendarChangeItem>) {
            if (changes.isEmpty() || !canPostNotifications(context)) return''',
        "ShiftReminderReceiver:canPostNotifications_and_cal_changes",
    )

    text = replace_once(
        text,
        r'''        fun showRequestDecisionNotification(context: Context, title: String, body: String, id: Int) {
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager''',
        r'''        fun showRequestDecisionNotification(context: Context, title: String, body: String, id: Int) {
            if (!canPostNotifications(context)) return
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager''',
        "ShiftReminderReceiver:check_notif_perm_requests",
    )

    text = replace_once(
        text,
        r'''                val id = item.optInt("Id", -1)
                val statusId = item.optInt("Status", -1)
                val typeName = item.optString("Type", "Toive")
                val statusDesc = item.optString("StatusDescription", "")

                if (id > 0 && (statusId == 50 || statusId == 80 || statusId == 40)) {
                    val key = "${id}_$statusId"
                    if (!notifiedIds.contains(key)) {
                        notifiedIds.add(key)
                        changed = true
                        if (baselineInitialized) {
                            ShiftReminderReceiver.showRequestDecisionNotification(
                                appContext,
                                if (DemoModeHelper.isEnglish(appContext)) "Request processed: $statusDesc" else "Toive käsitelty: $statusDesc",
                                typeName,
                                id
                            )
                        }
                    }
                }''',
        r'''                val id = item.optInt("Id", -1)
                val statusId = item.optInt("Status", -1)
                val typeName = item.optString("Type", "Toive")
                val statusDesc = item.optString("StatusDescription", "")
                val dateStr = formatRequestDate(item.optString("DateFrom", ""))
                val bodyText = if (dateStr.isNotEmpty()) "$typeName ($dateStr)" else typeName

                if (id > 0 && (statusId == 50 || statusId == 80 || statusId == 40)) {
                    val key = "${id}_$statusId"
                    if (!notifiedIds.contains(key)) {
                        notifiedIds.add(key)
                        changed = true
                        if (baselineInitialized) {
                            ShiftReminderReceiver.showRequestDecisionNotification(
                                appContext,
                                if (DemoModeHelper.isEnglish(appContext)) "Request processed: $statusDesc" else "Toive käsitelty: $statusDesc",
                                bodyText,
                                id
                            )
                        }
                    }
                }''',
        "ShiftReminderReceiver:request_date_in_notification",
    )

    text = replace_once(
        text,
        r'''            if (changed || !baselineInitialized) {
                prefs.edit()
                    .putStringSet("notified_request_ids", notifiedIds)
                    .putBoolean("requests_baseline_initialized", true)
                    .apply()
            }
        } catch (_: Exception) {
        }
    }
}''',
        r'''            if (changed || !baselineInitialized) {
                prefs.edit()
                    .putStringSet("notified_request_ids", notifiedIds)
                    .putBoolean("requests_baseline_initialized", true)
                    .apply()
            }
        } catch (_: Exception) {
        }
    }

    private fun formatRequestDate(raw: String): String {
        val trimmed = raw.trim()
        if (trimmed.isEmpty() || trimmed.equals("null", ignoreCase = true)) return ""
        val fmt = java.time.format.DateTimeFormatter.ofPattern("dd.MM.yyyy")
        val msMatch = Regex("/Date\\((-?\\d+)\\)/").find(trimmed)
        if (msMatch != null) {
            val ms = msMatch.groupValues[1].toLongOrNull() ?: return ""
            return java.time.Instant.ofEpochMilli(ms)
                .atZone(java.time.ZoneId.systemDefault())
                .toLocalDate()
                .format(fmt)
        }
        val isoMatch = Regex("^(\\d{4}-\\d{2}-\\d{2})").find(trimmed)
        if (isoMatch != null) {
            return try {
                LocalDate.parse(isoMatch.groupValues[1]).format(fmt)
            } catch (_: Exception) {
                ""
            }
        }
        val fiMatch = Regex("^\\d{1,2}\\.\\d{1,2}\\.\\d{4}").find(trimmed)
        return fiMatch?.value ?: ""
    }
}''',
        "ShiftReminderReceiver:formatRequestDate_helper",
    )
    return text


def patch_support_billing_helper(text: str) -> str:
    text = replace_once(
        text,
        r'''    private val mainHandler = Handler(Looper.getMainLooper())

    @Volatile
    private var isDestroyed = false

    private val billingClient: BillingClient = BillingClient.newBuilder(context)''',
        r'''    private val appContext: Context = context.applicationContext
    private val mainHandler = Handler(Looper.getMainLooper())
    private val pendingConsumes = java.util.concurrent.atomic.AtomicInteger(0)

    @Volatile
    private var isDestroyed = false

    private val billingClient: BillingClient = BillingClient.newBuilder(appContext)''',
        "SupportBillingHelper:appContext_and_pendingConsumes",
    )

    text = replace_once(
        text,
        r'''            billingClient.consumeAsync(consumeParams) { billingResult, _ ->
                if (isDestroyed) return@consumeAsync
                if (billingResult.responseCode == BillingClient.BillingResponseCode.OK) {
                    postStatus("Lämmin kiitos tuestasi! ☕", true)
                } else {
                    postStatus("Tuki rekisteröitiin, mutta kuittaus viivästyi (koodi ${billingResult.responseCode}).", false)
                }
            }''',
        r'''            pendingConsumes.incrementAndGet()
            billingClient.consumeAsync(consumeParams) { billingResult, _ ->
                try {
                    if (!isDestroyed) {
                        if (billingResult.responseCode == BillingClient.BillingResponseCode.OK) {
                            postStatus("Lämmin kiitos tuestasi! ☕", true)
                        } else {
                            postStatus("Tuki rekisteröitiin, mutta kuittaus viivästyi (koodi ${billingResult.responseCode}).", false)
                        }
                    }
                } finally {
                    if (pendingConsumes.decrementAndGet() <= 0 && isDestroyed) {
                        endConnectionSafe()
                    }
                }
            }''',
        "SupportBillingHelper:finish_consume_after_destroy",
    )

    text = replace_once(
        text,
        r'''    fun destroy() {
        isDestroyed = true
        try {
            if (billingClient.connectionState != BillingClient.ConnectionState.CLOSED) {
                billingClient.endConnection()
            }
        } catch (_: Exception) {
        }
    }''',
        r'''    private fun endConnectionSafe() {
        try {
            if (billingClient.connectionState != BillingClient.ConnectionState.CLOSED) {
                billingClient.endConnection()
            }
        } catch (_: Exception) {
        }
    }

    fun destroy() {
        isDestroyed = true
        if (pendingConsumes.get() <= 0) {
            endConnectionSafe()
        }
    }''',
        "SupportBillingHelper:defer_endConnection_during_consume",
    )
    return text


PATCH_PLAN = [
    ("build.gradle.kts", 'applicationId = "com.numeron_vuorovahti"', patch_build_gradle),
    ("AndroidManifest.xml", "fi.numeron.vuorovahti", patch_manifest),
    ("CalendarSyncHelper.kt", "object CalendarSyncHelper", patch_calendar_sync_helper),
    ("NumeronParser.kt", "object NumeronParser", patch_numeron_parser),
    ("MainActivity.kt", "class MainActivity", patch_main_activity),
    ("CalendarChangeTracker.kt", "object CalendarChangeTracker", patch_calendar_change_tracker),
    ("SettingsDialogHelper.kt", "object SettingsDialogHelper", patch_settings_dialog_helper),
    ("ShiftReminderReceiver.kt", "class ShiftReminderReceiver", patch_shift_reminder_receiver),
    ("SupportBillingHelper.kt", "class SupportBillingHelper", patch_support_billing_helper),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Numeron Vuorovahti patch 2")
    parser.add_argument("--root", default=".", help="Projektin juurikansio")
    parser.add_argument("--dry-run", action="store_true", help="Tarkista muutokset kirjoittamatta tiedostoja")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    staged_writes: list[tuple[Path, str, str]] = []

    for filename, marker, patch_fn in PATCH_PLAN:
        path = find_file(root, filename, marker)
        raw_text = path.read_bytes().decode("utf-8")
        eol = "\r\n" if "\r\n" in raw_text else "\n"
        normalized = raw_text.replace("\r\n", "\n")

        patched = patch_fn(normalized)
        if patched == normalized:
            raise RuntimeError(f"[{filename}] Tiedostoon ei tullut muutoksia.")

        staged_writes.append((path, patched.replace("\n", eol), filename))
        print(f"OK: {path.relative_to(root)}")

    # Varmuuskopiosäännöt (backup_rules.xml + uusi data_extraction_rules.xml)
    backup_path = find_file(root, "backup_rules.xml")
    backup_raw = backup_path.read_bytes().decode("utf-8")
    backup_eol = "\r\n" if "\r\n" in backup_raw else "\n"
    backup_norm = backup_raw.replace("\r\n", "\n")
    backup_patched = patch_backup_rules(backup_norm)
    if backup_patched != backup_norm:
        staged_writes.append((backup_path, backup_patched.replace("\n", backup_eol), "backup_rules.xml"))
        print(f"OK: {backup_path.relative_to(root)}")
    else:
        print(f"OK (jo ajan tasalla): {backup_path.relative_to(root)}")

    extraction_path = backup_path.parent / "data_extraction_rules.xml"
    staged_writes.append((extraction_path, DATA_EXTRACTION_RULES_XML.replace("\n", backup_eol), "data_extraction_rules.xml"))
    action_lbl = "PÄIVITYS" if extraction_path.exists() else "UUSI"
    print(f"OK ({action_lbl}): {extraction_path.relative_to(root)}")

    if args.dry_run:
        print(f"\nDRY-RUN OK: {len(staged_writes)} tiedostoa valmiina, mitään ei kirjoitettu.")
        return 0

    for path, final_text, _ in staged_writes:
        path.write_text(final_text, encoding="utf-8")

    print(f"\nVALMIS: {len(staged_writes)} tiedostoa päivitetty/luotu onnistuneesti.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"VIRHE: {exc}", file=sys.stderr)
        sys.exit(1)
