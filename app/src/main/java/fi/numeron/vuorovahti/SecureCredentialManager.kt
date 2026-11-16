package fi.numeron.vuorovahti

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

object SecureCredentialManager {

    private const val PREFS_FILE = "secure_numeron_prefs"
    private const val KEY_USERNAME = "secure_username"
    private const val KEY_PASSWORD = "secure_password"

    private fun getEncryptedPrefs(context: Context) = try {
        val masterKey = MasterKey.Builder(context, MasterKey.DEFAULT_MASTER_KEY_ALIAS)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        EncryptedSharedPreferences.create(
            context,
            PREFS_FILE,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    } catch (e: Exception) {
        null
    }

    fun saveCredentials(context: Context, username: String, password: String) {
        getEncryptedPrefs(context)?.edit()?.apply {
            putString(KEY_USERNAME, username)
            putString(KEY_PASSWORD, password)
            apply()
        }
    }

    fun getUsername(context: Context): String? {
        // Fallback vanhoihin suojaamattomiin SharedPreferences-tietoihin migraatiota varten
        getEncryptedPrefs(context)?.getString(KEY_USERNAME, null)?.let { if (it.isNotEmpty()) return it }
        return context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE).getString("username", null)
    }

    fun getPassword(context: Context): String? {
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
