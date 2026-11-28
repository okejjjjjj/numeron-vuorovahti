package fi.numeron.vuorovahti

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

object SecureCredentialManager {

    private const val PREFS_FILE = "secure_numeron_prefs"
    private const val KEY_USERNAME = "secure_username"
    private const val KEY_PASSWORD = "secure_password"

    @Volatile
    private var cachedEncryptedPrefs: SharedPreferences? = null

    internal fun getSharedEncryptedPrefs(context: Context): SharedPreferences? = getEncryptedPrefs(context)

    private fun getEncryptedPrefs(context: Context): SharedPreferences? {
        cachedEncryptedPrefs?.let { return it }
        return synchronized(this) {
            cachedEncryptedPrefs?.let { return@synchronized it }
            val appCtx = context.applicationContext
            fun createPrefs(): SharedPreferences {
                val masterKey = MasterKey.Builder(appCtx, MasterKey.DEFAULT_MASTER_KEY_ALIAS)
                    .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                    .build()
                return EncryptedSharedPreferences.create(
                    appCtx,
                    PREFS_FILE,
                    masterKey,
                    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
                )
            }
            try {
                createPrefs().also { cachedEncryptedPrefs = it }
            } catch (_: Exception) {
                try {
                    appCtx.deleteSharedPreferences(PREFS_FILE)
                    val ks = java.security.KeyStore.getInstance("AndroidKeyStore")
                    ks.load(null)
                    if (ks.containsAlias(MasterKey.DEFAULT_MASTER_KEY_ALIAS)) {
                        ks.deleteEntry(MasterKey.DEFAULT_MASTER_KEY_ALIAS)
                    }
                    createPrefs().also { cachedEncryptedPrefs = it }
                } catch (_: Exception) {
                    null
                }
            }
        }
    }

    private fun migrateLegacyIfNeeded(context: Context) {
        val legacyPrefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val legacyUser = legacyPrefs.getString("username", null)
        val legacyPass = legacyPrefs.getString("password", null)
        if (!legacyUser.isNullOrEmpty() || !legacyPass.isNullOrEmpty()) {
            val enc = getEncryptedPrefs(context)
            if (enc != null) {
                enc.edit().apply {
                    if (!legacyUser.isNullOrEmpty() && enc.getString(KEY_USERNAME, null).isNullOrEmpty()) {
                        putString(KEY_USERNAME, legacyUser)
                    }
                    if (!legacyPass.isNullOrEmpty() && enc.getString(KEY_PASSWORD, null).isNullOrEmpty()) {
                        putString(KEY_PASSWORD, legacyPass)
                    }
                    apply()
                }
                legacyPrefs.edit().remove("username").remove("password").apply()
            }
        }
    }

    fun saveCredentials(context: Context, username: String, password: String) {
        getEncryptedPrefs(context)?.edit()?.apply {
            if (username.isEmpty()) remove(KEY_USERNAME) else putString(KEY_USERNAME, username)
            if (password.isEmpty()) remove(KEY_PASSWORD) else putString(KEY_PASSWORD, password)
            apply()
        }
        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .remove("username")
            .remove("password")
            .apply()
    }

    fun getUsername(context: Context): String? {
        migrateLegacyIfNeeded(context)
        getEncryptedPrefs(context)?.getString(KEY_USERNAME, null)?.let { if (it.isNotEmpty()) return it }
        return context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE).getString("username", null)
    }

    fun getPassword(context: Context): String? {
        migrateLegacyIfNeeded(context)
        getEncryptedPrefs(context)?.getString(KEY_PASSWORD, null)?.let { if (it.isNotEmpty()) return it }
        return context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE).getString("password", null)
    }

    fun clearCredentials(context: Context) {
        getEncryptedPrefs(context)?.edit()?.clear()?.apply()
        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE).edit()
            .remove("username")
            .remove("password")
            .apply()
    }
}
