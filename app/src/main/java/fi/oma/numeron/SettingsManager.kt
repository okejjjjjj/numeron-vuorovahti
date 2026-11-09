package fi.oma.numeron

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

object SettingsManager {
    @Volatile
    private var cachedPrefs: SharedPreferences? = null

    private fun getPrefs(context: Context): SharedPreferences {
        cachedPrefs?.let { return it }
        synchronized(this) {
            cachedPrefs?.let { return it }
            val appCtx = context.applicationContext
            val prefs = try {
                val masterKey = MasterKey.Builder(appCtx)
                    .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                    .build()
                EncryptedSharedPreferences.create(
                    appCtx,
                    "numeron_secure_prefs",
                    masterKey,
                    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
                )
            } catch (e: Exception) {
                appCtx.getSharedPreferences("numeron_prefs", Context.MODE_PRIVATE)
            }
            cachedPrefs = prefs
            return prefs
        }
    }

    fun hasValidOrganization(context: Context): Boolean =
        getOrganizationRaw(context).trim().isNotEmpty() ||
        getUsername(context).trim().equals("demo", ignoreCase = true)

    fun isFirstRun(context: Context): Boolean =
        !getPrefs(context).contains("settings_initialized") || !hasValidOrganization(context)

    fun getOrganizationRaw(context: Context): String =
        getPrefs(context).getString("org_domain", "") ?: ""

    fun getBaseUrl(context: Context): String {
        if (VuorovahtiHelper.isDemoMode(getUsername(context), getPassword(context))) return "file:///android_asset/demo_shifts.html"
        val raw = getOrganizationRaw(context).trim().lowercase()
            .removePrefix("https://")
            .removePrefix("http://")
            .substringBefore("/")
            .substringBefore("?")
            .trim()
        if (raw.isEmpty()) return "about:blank"
        return if (raw.contains(".")) "https://$raw" else "https://$raw.numeronwfm.com"
    }

    fun getUsername(context: Context): String = getPrefs(context).getString("username", "") ?: ""
    fun getPassword(context: Context): String = getPrefs(context).getString("password", "") ?: ""

    fun isBiometricEnabled(context: Context): Boolean =
        getPrefs(context).getBoolean("biometric_enabled", true)

    fun isAutoSyncEnabled(context: Context): Boolean =
        getPrefs(context).getBoolean("auto_sync_enabled", true)

    fun isStampNotificationEnabled(context: Context): Boolean =
        getPrefs(context).getBoolean("stamp_notif_enabled", true)

    fun getTargetCalendarId(context: Context): Long =
        getPrefs(context).getLong("target_calendar_id", -1L)

    fun saveAll(
        context: Context,
        org: String,
        user: String,
        pass: String,
        biometric: Boolean,
        autoSync: Boolean,
        stampNotif: Boolean,
        calendarId: Long
    ) {
        getPrefs(context).edit().apply {
            putBoolean("settings_initialized", true)
            val cleanOrg = org.trim()
                .removePrefix("https://")
                .removePrefix("http://")
                .substringBefore("/")
                .substringBefore("?")
                .trim()
            putString("org_domain", cleanOrg)
            putString("username", user.trim())
            putString("password", pass)
            putBoolean("biometric_enabled", biometric)
            putBoolean("auto_sync_enabled", autoSync)
            putBoolean("stamp_notif_enabled", stampNotif)
            putLong("target_calendar_id", calendarId)
            apply()
        }
    }
}
