package fi.numeron.vuorovahti

import android.content.Context
import android.webkit.JavascriptInterface
import android.widget.Toast
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.format.DateTimeFormatter

object DemoModeHelper {

    fun isDemoEnabled(context: Context): Boolean {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val user = prefs.getString("username", "") ?: ""
        return prefs.getBoolean("demo_mode", user.isEmpty())
    }

    fun getDemoStampingHtml(context: Context): String {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val isStampedIn = prefs.getBoolean("demo_stamped_in", false)
        val history = prefs.getString("demo_stamp_history", "14.11.2026 | 14:04 | Ulos\n14.11.2026 | 07:01 | Sisään") ?: ""

        val btnText = if (isStampedIn) "Leimaa Ulos" else "Leimaa Sisään"
        val btnColor = if (isStampedIn) "#C62828" else "#1982C4"
        val todayShift = "Aamuvuoro 07:00 - 15:00 (Demotila)"

        val rowsHtml = history.split("\n").filter { it.isNotBlank() }.joinToString("") { line ->
            val p = line.split("|").map { it.trim() }
            if (p.size >= 3) {
                """<div style="display:flex;justify-content:space-between;padding:10px;border-bottom:1px solid #2A394A;color:#E0E6ED;">
                    <span>${p[0]}</span><span>${p[1]}</span><span style="font-weight:bold;">${p[2]}</span>
                </div>"""
            } else ""
        }

        return """
        <!DOCTYPE html>
        <html>
        <head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="background:#0F1722;color:#E0E6ED;font-family:sans-serif;padding:12px;margin:0;">
            <div style="background:#182332;border:1px solid #2A394A;border-radius:12px;padding:14px;margin-bottom:14px;">
                <div style="font-size:11px;color:#90A4AE;text-transform:uppercase;">TÄNÄÄN</div>
                <div style="font-size:15px;font-weight:bold;margin-top:4px;">$todayShift</div>
            </div>

            <div style="background:#182332;border:1px solid #2A394A;border-radius:12px;padding:16px;margin-bottom:14px;">
                <div style="font-size:13px;color:#90A4AE;margin-bottom:12px;">LEIMAUS (DEMOTILA)</div>
                <div style="font-size:13px;margin-bottom:4px;">Syykoodi</div>
                <select style="width:100%;padding:10px;background:#111923;color:#FFF;border:1px solid #37475A;border-radius:8px;margin-bottom:12px;">
                    <option>Normaali työaika</option>
                    <option>Liukuma</option>
                </select>
                <div style="font-size:13px;margin-bottom:4px;">Lisätiedot</div>
                <input type="text" placeholder="Kirjoita selite tarvittaessa" style="width:100%;box-sizing:border-box;padding:10px;background:#111923;color:#FFF;border:1px solid #37475A;border-radius:8px;margin-bottom:16px;" />
                <button id="punchButton" onclick="DemoBridge.toggleStamp()" style="width:100%;padding:14px;background:$btnColor;color:#FFF;border:none;border-radius:10px;font-size:16px;font-weight:bold;">
                    $btnText
                </button>
            </div>

            <div style="background:#182332;border:1px solid #2A394A;border-radius:12px;padding:14px;">
                <div style="font-size:13px;color:#90A4AE;margin-bottom:8px;">VIIMEISIMMÄT TAPAHTUMAT</div>
                $rowsHtml
            </div>
        </body>
        </html>
        """.trimIndent()
    }

    fun getDemoRequestsHtml(context: Context): String {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val reqList = prefs.getString("demo_requests", "24.11.2026 | Vuosiloma | Hyväksytty\n02.12.2026 | Toivevapaa | Odottaa käsittelyä") ?: ""

        val itemsHtml = reqList.split("\n").filter { it.isNotBlank() }.joinToString("") { line ->
            val p = line.split("|").map { it.trim() }
            if (p.size >= 3) {
                val badgeColor = if (p[2].contains("Hyväksytty")) "#2E7D32" else "#D97706"
                """<div style="background:#182332;border:1px solid #2A394A;border-radius:10px;padding:12px;margin-bottom:10px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <strong style="font-size:15px;">${p[1]}</strong>
                        <span style="background:$badgeColor;color:#FFF;padding:3px 8px;border-radius:6px;font-size:12px;">${p[2]}</span>
                    </div>
                    <div style="color:#90A4AE;font-size:13px;margin-top:6px;">Päivämäärä: ${p[0]}</div>
                </div>"""
            } else ""
        }

        return """
        <!DOCTYPE html>
        <html>
        <head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="background:#0F1722;color:#E0E6ED;font-family:sans-serif;padding:12px;margin:0;">
            <div style="background:#182332;border:1px solid #2A394A;border-radius:12px;padding:14px;margin-bottom:14px;">
                <div style="font-size:15px;font-weight:bold;margin-bottom:10px;">Uusi toive (Demotila)</div>
                <select id="reqType" style="width:100%;padding:10px;background:#111923;color:#FFF;border:1px solid #37475A;border-radius:8px;margin-bottom:10px;">
                    <option value="Toivevapaa">Toivevapaa (TV)</option>
                    <option value="Vuosiloma">Vuosiloma</option>
                    <option value="Aamuvuorotoive">Aamuvuorotoive</option>
                </select>
                <button onclick="DemoBridge.addRequest(document.getElementById('reqType').value)" style="width:100%;padding:12px;background:#1982C4;color:#FFF;border:none;border-radius:8px;font-weight:bold;">
                    Lähetä toive
                </button>
            </div>
            <div style="font-size:13px;color:#90A4AE;margin-bottom:8px;">OMAT TOIVEET</div>
            $itemsHtml
        </body>
        </html>
        """.trimIndent()
    }

    fun getDemoShiftsHtml(context: Context): String {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val variant = prefs.getInt("demo_shift_variant", 0)
        val today = LocalDate.now()
        val fmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")

        val shifts = if (variant % 2 == 0) {
            listOf(
                Triple(today.plusDays(1).format(fmt), "Aamuvuoro", "07:00 - 15:00"),
                Triple(today.plusDays(2).format(fmt), "Iltavuoro", "13:00 - 21:00"),
                Triple(today.plusDays(3).format(fmt), "Yövuoro", "21:00 - 07:00"),
                Triple(today.plusDays(5).format(fmt), "Vuosiloma", "Koko päivä"),
                Triple(today.plusDays(6).format(fmt), "Vuosiloma", "Koko päivä")
            )
        } else {
            listOf(
                Triple(today.plusDays(1).format(fmt), "Iltavuoro (Muuttunut)", "13:00 - 21:00"),
                Triple(today.plusDays(2).format(fmt), "Iltavuoro", "13:00 - 21:00"),
                Triple(today.plusDays(4).format(fmt), "Aamuvuoro (Uusi)", "07:00 - 15:00"),
                Triple(today.plusDays(5).format(fmt), "Vuosiloma", "Koko päivä"),
                Triple(today.plusDays(6).format(fmt), "Vuosiloma", "Koko päivä")
            )
        }

        val rows = shifts.joinToString("") { (date, name, time) ->
            """<div style="background:#182332;border:1px solid #2A394A;border-radius:10px;padding:12px;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <div style="font-weight:bold;font-size:15px;">$name</div>
                    <div style="color:#90A4AE;font-size:13px;">$date</div>
                </div>
                <div style="color:#64B5F6;font-weight:bold;">$time</div>
            </div>"""
        }

        return """
        <!DOCTYPE html>
        <html>
        <head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="background:#0F1722;color:#E0E6ED;font-family:sans-serif;padding:12px;margin:0;">
            <div style="font-size:16px;font-weight:bold;margin-bottom:12px;">Julkaistut työvuorot (Demotila)</div>
            $rows
            <button onclick="DemoBridge.syncDemoCalendar()" style="width:100%;padding:14px;background:#2E7D32;color:#FFF;border:none;border-radius:10px;font-weight:bold;margin-top:8px;">
                Vie demovuorot puhelimen kalenteriin
            </button>
            <button onclick="DemoBridge.simulateShiftUpdateAndSync()" style="width:100%;padding:12px;background:#D97706;color:#FFF;border:none;border-radius:10px;font-weight:bold;margin-top:10px;">
                Simuloi vuoromuutos ja synkronoi (testaa perumista)
            </button>
            <button onclick="DemoBridge.openChangesManager()" style="width:100%;padding:12px;background:#222E3C;color:#E0E6ED;border:1px solid #37475A;border-radius:10px;font-weight:bold;margin-top:10px;">
                Hallitse / Peru kalenterimuutoksia
            </button>
        </body>
        </html>
        """.trimIndent()
    }

    fun generateDemoWorkShifts(context: Context): List<WorkShift> {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val variant = prefs.getInt("demo_shift_variant", 0)
        val today = LocalDate.now()

        return if (variant % 2 == 0) {
            listOf(
                WorkShift("Työvuoro", LocalDateTime.of(today.plusDays(1), LocalTime.of(7, 0)), LocalDateTime.of(today.plusDays(1), LocalTime.of(15, 0)), false, "Outokumpu Onni", "Aamu • Hoitaja"),
                WorkShift("Työvuoro", LocalDateTime.of(today.plusDays(2), LocalTime.of(13, 0)), LocalDateTime.of(today.plusDays(2), LocalTime.of(21, 0)), false, "Outokumpu Onni", "Ilta • Hoitaja"),
                WorkShift("Työvuoro", LocalDateTime.of(today.plusDays(3), LocalTime.of(21, 0)), LocalDateTime.of(today.plusDays(4), LocalTime.of(7, 0)), false, "Outokumpu Onni", "Yö • Hoitaja"),
                WorkShift("Vuosiloma (Demo)", today.plusDays(5).atStartOfDay(), today.plusDays(7).atStartOfDay(), true)
            )
        } else {
            listOf(
                WorkShift("Työvuoro", LocalDateTime.of(today.plusDays(1), LocalTime.of(13, 0)), LocalDateTime.of(today.plusDays(1), LocalTime.of(21, 0)), false, "Outokumpu Onni", "Ilta • Hoitaja"),
                WorkShift("Työvuoro", LocalDateTime.of(today.plusDays(2), LocalTime.of(13, 0)), LocalDateTime.of(today.plusDays(2), LocalTime.of(21, 0)), false, "Outokumpu Onni", "Ilta • Hoitaja"),
                WorkShift("Työvuoro", LocalDateTime.of(today.plusDays(4), LocalTime.of(7, 0)), LocalDateTime.of(today.plusDays(4), LocalTime.of(15, 0)), false, "Outokumpu Onni", "Aamu • Hoitaja"),
                WorkShift("Vuosiloma (Demo)", today.plusDays(5).atStartOfDay(), today.plusDays(7).atStartOfDay(), true)
            )
        }
    }

    class DemoJsBridge(
        private val context: Context,
        private val onReloadNeeded: () -> Unit,
        private val onSyncRequested: () -> Unit,
        private val onManageChangesRequested: () -> Unit
    ) {
        @JavascriptInterface
        fun toggleStamp() {
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val current = prefs.getBoolean("demo_stamped_in", false)
            val nextState = !current
            val actionLabel = if (nextState) "Sisään" else "Ulos"

            val nowDate = LocalDate.now().format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
            val nowTime = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
            val oldHistory = prefs.getString("demo_stamp_history", "") ?: ""
            val newHistory = "$nowDate | $nowTime | $actionLabel\n$oldHistory"

            prefs.edit()
                .putBoolean("demo_stamped_in", nextState)
                .putString("demo_stamp_history", newHistory)
                .apply()

            Toast.makeText(context, "Demoleimaus suoritettu: $actionLabel ($nowTime)", Toast.LENGTH_SHORT).show()
            onReloadNeeded()
        }

        @JavascriptInterface
        fun addRequest(type: String) {
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val dateStr = LocalDate.now().plusDays(10).format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
            val oldList = prefs.getString("demo_requests", "") ?: ""
            val newList = "$dateStr | $type | Odottaa käsittelyä\n$oldList"
            prefs.edit().putString("demo_requests", newList).apply()

            Toast.makeText(context, "Demotoive lisätty: $type", Toast.LENGTH_SHORT).show()
            onReloadNeeded()
        }

        @JavascriptInterface
        fun syncDemoCalendar() {
            onSyncRequested()
        }

        @JavascriptInterface
        fun simulateShiftUpdateAndSync() {
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val nextVar = prefs.getInt("demo_shift_variant", 0) + 1
            prefs.edit().putInt("demo_shift_variant", nextVar).apply()
            onReloadNeeded()
            onSyncRequested()
        }

        @JavascriptInterface
        fun openChangesManager() {
            onManageChangesRequested()
        }
    }
}
