package fi.numeron.vuorovahti

import android.content.Context
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.util.Locale

object DemoModeHelper {

    fun isDemoCredentials(org: String, user: String, pass: String): Boolean {
        val cleanOrg = org.trim().trimEnd('/')
        val isDemoOrg = cleanOrg.equals("demo", ignoreCase = true) ||
            cleanOrg.equals("demo.numeronwfm.com", ignoreCase = true) ||
            cleanOrg.equals("https://demo.numeronwfm.com", ignoreCase = true)
        return isDemoOrg &&
            user.trim().equals("demo", ignoreCase = true) &&
            pass.trim().equals("demo", ignoreCase = true)
    }

    fun isDemoEnabled(context: Context): Boolean {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val org = (prefs.getString("org_raw_input", "") ?: "").trim()
        val serverUrl = (prefs.getString("server_url", "") ?: "").trim()

        if (org.isEmpty() && serverUrl.isEmpty()) {
            return true
        }
        if (UrlNormalizer.isDemoInput(org) || UrlNormalizer.isDemoInput(serverUrl)) {
            return true
        }
        if (prefs.contains("demo_mode")) {
            return prefs.getBoolean("demo_mode", true)
        }
        val user = (SecureCredentialManager.getUsername(context) ?: "").trim()
        val pass = SecureCredentialManager.getPassword(context) ?: ""
        val demo = user.isEmpty() || pass.isEmpty() || isDemoCredentials(org.ifEmpty { serverUrl }, user, pass)
        prefs.edit().putBoolean("demo_mode", demo).apply()
        return demo
    }

    fun isEnglish(context: Context): Boolean {
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
    }

    fun setDemoLanguage(context: Context, lang: String) {
        val normalized = if (lang.equals("en", ignoreCase = true)) "en" else "fi"
        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putString("demo_language", normalized)
            .apply()
    }

    fun generateDemoWorkShifts(context: Context): List<WorkShift> {
        val en = isEnglish(context)
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val variant = prefs.getInt("demo_shift_variant", 0)
        val today = LocalDate.now()

        val shiftTitle = if (en) "Work Shift" else "Työvuoro"
        val unitName = if (en) "Central Care Unit Helmi" else "Keskusyksikkö Helmi"
        val morningDesc = if (en) "Morning • Nurse" else "Aamu • Hoitaja"
        val eveningDesc = if (en) "Evening • Nurse" else "Ilta • Hoitaja"
        val nightDesc = if (en) "Night • Nurse" else "Yö • Hoitaja"
        val leaveTitle = if (en) "Annual Leave (Demo)" else "Vuosiloma (Demo)"

        return if (variant % 2 == 0) {
            listOf(
                WorkShift(shiftTitle, LocalDateTime.of(today.plusDays(1), LocalTime.of(7, 0)), LocalDateTime.of(today.plusDays(1), LocalTime.of(15, 0)), false, unitName, morningDesc),
                WorkShift(shiftTitle, LocalDateTime.of(today.plusDays(2), LocalTime.of(13, 0)), LocalDateTime.of(today.plusDays(2), LocalTime.of(21, 0)), false, unitName, eveningDesc),
                WorkShift(shiftTitle, LocalDateTime.of(today.plusDays(3), LocalTime.of(21, 0)), LocalDateTime.of(today.plusDays(4), LocalTime.of(7, 0)), false, unitName, nightDesc),
                WorkShift(leaveTitle, today.plusDays(5).atStartOfDay(), today.plusDays(7).atStartOfDay(), true)
            )
        } else {
            listOf(
                WorkShift(shiftTitle, LocalDateTime.of(today.plusDays(1), LocalTime.of(13, 0)), LocalDateTime.of(today.plusDays(1), LocalTime.of(21, 0)), false, unitName, eveningDesc),
                WorkShift(shiftTitle, LocalDateTime.of(today.plusDays(2), LocalTime.of(13, 0)), LocalDateTime.of(today.plusDays(2), LocalTime.of(21, 0)), false, unitName, eveningDesc),
                WorkShift(shiftTitle, LocalDateTime.of(today.plusDays(4), LocalTime.of(7, 0)), LocalDateTime.of(today.plusDays(4), LocalTime.of(15, 0)), false, unitName, morningDesc),
                WorkShift(leaveTitle, today.plusDays(5).atStartOfDay(), today.plusDays(7).atStartOfDay(), true)
            )
        }
    }
}
