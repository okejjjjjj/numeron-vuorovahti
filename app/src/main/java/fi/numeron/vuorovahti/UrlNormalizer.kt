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
     * - "siunsote" -> "https://siunsote.numeronwfm.com"
     * - "Siun Sote" -> "https://siunsote.numeronwfm.com"
     * - "siunsote.numeronwfm.com/Login" -> "https://siunsote.numeronwfm.com"
     * - "https://oma.yritys.fi/wfm" -> "https://oma.yritys.fi/wfm" (jos oma domain)
     */
    fun normalizeOrgUrl(rawInput: String?): String {
        val cleaned = rawInput?.trim()?.lowercase() ?: ""
        if (cleaned.isEmpty()) return ""
        if (cleaned == "demo") return "demo"

        // Jos käyttäjä syötti täyden custom-domainin (joka ei ole numeronwfm.com), säilytetään se
        if ((cleaned.startsWith("http://") || cleaned.startsWith("https://")) && !cleaned.contains("numeronwfm.com")) {
            return cleaned.trimEnd('/')
        }

        // Poistetaan protokolla, polut ja pääteosa, jotta jäljelle jää pelkkä organisaatiotunnus
        val orgSlug = cleaned
            .removePrefix("https://")
            .removePrefix("http://")
            .substringBefore("/")
            .substringBefore("?")
            .removeSuffix(".numeronwfm.com")
            .removeSuffix(".numeronwfm.fi")
            .replace("\\s+".toRegex(), "") // Poistaa välilyönnit (esim. "Siun sote" -> "siunsote")
            .replace("[^a-z0-9-]".toRegex(), "") // Poistaa erikoismerkit

        if (orgSlug.isEmpty()) return ""

        return "https://$orgSlug.numeronwfm.com"
    }

    fun getSavedBaseUrl(context: Context): String {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val raw = prefs.getString("server_url", "") ?: ""
        return normalizeOrgUrl(raw)
    }
}
