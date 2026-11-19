package fi.numeron.vuorovahti

import android.content.Context

object UrlNormalizer {

    fun isDemoInput(rawInput: String?): Boolean {
        return rawInput?.trim()?.equals("demo", ignoreCase = true) == true
    }

    /**
     * Muuntaa käyttäjän syötteen aina validiksi Numeron WFM -perusosoitteeksi.
     * Esimerkit:
     * - "demo" -> "demo"
     * - "demo" -> "https://demo.numeronwfm.com"
     * - "Hyvinvointialue Demo" -> "https://demo.numeronwfm.com"
     * - "demo.numeronwfm.com/Login" -> "https://demo.numeronwfm.com"
     * - "https://oma.yritys.fi/wfm" -> "https://oma.yritys.fi/wfm" (jos oma domain)
     */
    fun normalizeOrgUrl(rawInput: String?): String {
        val trimmed = rawInput?.trim() ?: ""
        if (trimmed.isEmpty()) return ""
        if (trimmed.equals("demo", ignoreCase = true)) return "demo"

        val lower = trimmed.lowercase()
        val isNumeronHost = lower.contains("numeronwfm.com") || lower.contains("numeronwfm.fi")

        // Jos käyttäjä syötti oman custom-domainin protokollalla, säilytetään polun kirjainkoko
        if ((lower.startsWith("http://") || lower.startsWith("https://")) && !isNumeronHost) {
            return trimmed.trimEnd('/')
        }

        // Jos käyttäjä syötti oman domainin ilman protokollaa (esim. wfm.yritys.fi)
        if (!isNumeronHost && !trimmed.contains(" ") && trimmed.substringBefore("/").contains(".")) {
            return "https://${trimmed.trimEnd('/')}"
        }

        // Poistetaan protokolla, polut ja pääteosa, jotta jäljelle jää pelkkä organisaatiotunnus
        val orgSlug = lower
            .removePrefix("https://")
            .removePrefix("http://")
            .substringBefore("/")
            .substringBefore("?")
            .removeSuffix(".numeronwfm.com")
            .removeSuffix(".numeronwfm.fi")
            .replace("\\s+".toRegex(), "")
            .replace("[^a-z0-9-]".toRegex(), "")

        if (orgSlug.isEmpty()) return ""

        return "https://$orgSlug.numeronwfm.com"
    }

    fun getSavedBaseUrl(context: Context): String {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val raw = prefs.getString("server_url", "") ?: ""
        return normalizeOrgUrl(raw)
    }
}
