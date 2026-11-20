#!/usr/bin/env python3
import pathlib
import re


def find_file(filename: str) -> pathlib.Path:
    direct = pathlib.Path(filename)
    if direct.exists():
        return direct
    matches = list(pathlib.Path(".").rglob(filename))
    if matches:
        return matches[0]
    raise FileNotFoundError(f"Tiedostoa {filename} ei löytynyt!")


def verify_kotlin_delimiters(path: pathlib.Path, content: str) -> None:
    cleaned = re.sub(r'""".*?"""', '', content, flags=re.DOTALL)
    cleaned = re.sub(r'"(?:\\.|[^"\\])*"', '', cleaned)
    if cleaned.count("{") != cleaned.count("}"):
        raise RuntimeError(
            f"[{path.name}] Aaltosulkeiden määrä ei täsmää ({cleaned.count('{')} vs {cleaned.count('}')})"
        )
    if cleaned.count("(") != cleaned.count(")"):
        raise RuntimeError(
            f"[{path.name}] Kaarisulkeiden määrä ei täsmää ({cleaned.count('(')} vs {cleaned.count(')')})"
        )


def replace_exact(path: pathlib.Path, content: str, old: str, new: str) -> str:
    if old not in content:
        raise RuntimeError(f"[{path.name}] Korvattavaa lohkoa ei löytynyt:\n{old[:140]}...")
    return content.replace(old, new, 1)


def increment_version() -> None:
    gradle_candidates = [
        pathlib.Path("app/build.gradle.kts"),
        pathlib.Path("app/build.gradle"),
    ]
    gradle_file = next((p for p in gradle_candidates if p.exists()), None)
    if not gradle_file:
        matches = list(pathlib.Path(".").rglob("build.gradle*"))
        gradle_file = next((p for p in matches if "app" in p.parts), None)

    if not gradle_file:
        print("Varoitus: app/build.gradle(.kts) ei löytynyt, versionumeroa ei päivitetty.")
        return

    text = gradle_file.read_text(encoding="utf-8")

    vc_match = re.search(r'(versionCode\s*=?\s*)(\d+)', text)
    if vc_match:
        old_vc = int(vc_match.group(2))
        new_vc = old_vc + 1
        text = text[:vc_match.start(2)] + str(new_vc) + text[vc_match.end(2):]
        print(f"Päivitetty versionCode: {old_vc} -> {new_vc}")

    vn_match = re.search(r'(versionName\s*=?\s*")(\d+(?:\.\d+)*)(")', text)
    if vn_match:
        parts = vn_match.group(2).split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        new_vn = ".".join(parts)
        text = text[:vn_match.start(2)] + new_vn + text[vn_match.end(2):]
        print(f"Päivitetty versionName: {vn_match.group(2)} -> {new_vn}")

    gradle_file.write_text(text, encoding="utf-8")


DEMO_MODE_HELPER_KT = r'''package fi.numeron.vuorovahti

import android.content.Context
import android.webkit.JavascriptInterface
import android.widget.Toast
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.time.temporal.TemporalAdjusters
import java.time.temporal.WeekFields
import java.util.Locale

object DemoModeHelper {

    fun isDemoCredentials(org: String, user: String, pass: String): Boolean {
        return org.trim().equals("demo", ignoreCase = true) &&
            user.trim().equals("demo", ignoreCase = true) &&
            pass.trim().equals("demo", ignoreCase = true)
    }

    fun isDemoEnabled(context: Context): Boolean {
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val org = (prefs.getString("org_raw_input", "") ?: "").trim()
        val serverUrl = (prefs.getString("server_url", "") ?: "").trim()
        val user = (SecureCredentialManager.getUsername(context) ?: "").trim()
        val pass = SecureCredentialManager.getPassword(context) ?: ""

        if (user.isEmpty() || pass.isEmpty() || (org.isEmpty() && serverUrl.isEmpty())) {
            return true
        }
        return isDemoCredentials(org.ifEmpty { serverUrl }, user, pass)
    }

    fun isEnglish(context: Context): Boolean {
        if (!isDemoEnabled(context)) return false
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val saved = prefs.getString("demo_language", null)
        return when (saved) {
            "en" -> true
            "fi" -> false
            else -> !Locale.getDefault().language.equals("fi", ignoreCase = true)
        }
    }

    fun setDemoLanguage(context: Context, lang: String) {
        val normalized = if (lang.equals("en", ignoreCase = true)) "en" else "fi"
        context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .edit()
            .putString("demo_language", normalized)
            .apply()
    }

    private fun langSwitchHtml(en: Boolean): String {
        val fiStyle = if (!en) {
            "background:#1982C4;color:#FFFFFF;"
        } else {
            "background:#182332;color:#94A3B8;"
        }
        val enStyle = if (en) {
            "background:#1982C4;color:#FFFFFF;"
        } else {
            "background:#182332;color:#94A3B8;"
        }
        return """
            <div style="display:inline-flex;border-radius:8px;overflow:hidden;border:1px solid #2A394A;">
                <button type="button" onclick="DemoBridge.setLanguage('fi')" style="$fiStyle border:0;padding:4px 9px;font-size:11px;font-weight:700;cursor:pointer;">FI</button>
                <button type="button" onclick="DemoBridge.setLanguage('en')" style="$enStyle border:0;padding:4px 9px;font-size:11px;font-weight:700;cursor:pointer;">EN</button>
            </div>
        """.trimIndent()
    }

    private fun appDarkHead(title: String, extraCss: String = ""): String {
        return """
        <!DOCTYPE html>
        <html class="notranslate" translate="no">
        <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>$title</title>
            <style>
                * { box-sizing: border-box; }
                html, body {
                    background-color: #0F1722;
                    color: #F1F5F9;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    font-size: 14px;
                    line-height: 1.4;
                    margin: 0;
                    padding: 0;
                }
                .container {
                    padding: 12px;
                    width: 100%;
                    max-width: 100%;
                }
                .page-header-row {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin: 4px 0 12px 0;
                }
                h1, h2, h3 {
                    color: #F1F5F9;
                    font-size: 20px;
                    font-weight: 600;
                    margin: 0;
                }
                .panel {
                    background-color: #182332;
                    border: 1px solid #2A394A;
                    border-radius: 12px;
                    color: #F1F5F9;
                    padding: 14px;
                    margin-bottom: 14px;
                }
                .form-group {
                    margin-bottom: 12px;
                }
                .form-label {
                    display: block;
                    color: #CBD5E1;
                    font-size: 13px;
                    font-weight: 500;
                    margin-bottom: 4px;
                }
                .required-star {
                    color: #F87171;
                    margin-left: 2px;
                }
                .form-control {
                    display: block;
                    width: 100%;
                    background-color: #111923;
                    color: #FFFFFF;
                    border: 1px solid #37475A;
                    border-radius: 8px;
                    padding: 9px 12px;
                    font-size: 14px;
                    outline: none;
                }
                .form-control::placeholder {
                    color: #64748B;
                }
                .form-control:disabled {
                    opacity: 0.45;
                }
                .input-group {
                    display: flex;
                    width: 100%;
                }
                .input-group .form-control {
                    border-top-right-radius: 0;
                    border-bottom-right-radius: 0;
                }
                .input-group-addon {
                    background-color: #233040;
                    border: 1px solid #37475A;
                    border-left: 0;
                    color: #38BDF8;
                    border-radius: 0 8px 8px 0;
                    padding: 0 10px;
                    display: flex;
                    align-items: center;
                    font-size: 14px;
                }
                .btn {
                    display: inline-block;
                    background-color: #233040;
                    color: #F1F5F9;
                    border: 1px solid #37475A;
                    border-radius: 8px;
                    padding: 10px 14px;
                    font-size: 14px;
                    font-weight: 600;
                    text-align: center;
                    cursor: pointer;
                    text-decoration: none;
                }
                .btn:active {
                    opacity: 0.85;
                }
                .btn-primary {
                    background-color: #1982C4;
                    border-color: #1982C4;
                    color: #FFFFFF;
                }
                .btn-stamp-in {
                    background-color: #2E7D32;
                    border-color: #2E7D32;
                    color: #FFFFFF;
                    border-radius: 10px;
                    padding: 12px;
                    font-size: 15px;
                    font-weight: 700;
                    width: 100%;
                }
                .btn-stamp-out {
                    background-color: #B91C1C;
                    border-color: #B91C1C;
                    color: #FFFFFF;
                    border-radius: 10px;
                    padding: 12px;
                    font-size: 15px;
                    font-weight: 700;
                    width: 100%;
                }
                .section-caption {
                    display: block;
                    font-size: 12px;
                    text-transform: uppercase;
                    letter-spacing: 0.05em;
                    color: #94A3B8;
                    margin-bottom: 6px;
                    font-weight: 600;
                }
                .table {
                    width: 100%;
                    border-collapse: collapse;
                    background-color: transparent;
                    color: #F1F5F9;
                }
                .table th, .table td {
                    border-top: 1px solid #2A394A;
                    color: #F1F5F9;
                    padding: 10px 6px;
                    text-align: left;
                    font-size: 13px;
                }
                .table thead th {
                    border-top: 0;
                    color: #94A3B8;
                    font-size: 12px;
                    text-transform: uppercase;
                    letter-spacing: 0.04em;
                }
                .badge {
                    display: inline-block;
                    padding: 3px 8px;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 700;
                }
                .badge-ok {
                    background-color: rgba(34, 197, 94, 0.18);
                    color: #4ADE80;
                    border: 1px solid rgba(74, 222, 128, 0.35);
                }
                .badge-wait {
                    background-color: rgba(245, 158, 11, 0.18);
                    color: #FBBF24;
                    border: 1px solid rgba(251, 191, 36, 0.35);
                }
                hr {
                    border: 0;
                    border-top: 1px solid #2A394A;
                    margin: 14px 0;
                }
                $extraCss
            </style>
        </head>
        """.trimIndent()
    }

    fun getDemoStampingHtml(context: Context): String {
        val en = isEnglish(context)
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val isStampedIn = prefs.getBoolean("demo_stamped_in", false)
        val today = LocalDate.now()
        val fmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")

        val defaultHistory = "${today.minusDays(1).format(fmt)} | 14:30 | Ulos\n${today.minusDays(1).format(fmt)} | 07:00 | Sisään"
        val history = prefs.getString("demo_stamp_history", defaultHistory) ?: defaultHistory

        val pageTitle = if (en) "Time Stamping" else "Työaikaleimaus"
        val btnText = if (isStampedIn) {
            if (en) "Clock Out" else "Leimaa Ulos"
        } else {
            if (en) "Clock In" else "Leimaa Sisään"
        }
        val btnClass = if (isStampedIn) "btn btn-stamp-out" else "btn btn-stamp-in"
        val statusBadge = if (isStampedIn) {
            val lbl = if (en) "Clocked in" else "Sisäänleimattuna"
            """<span class="badge badge-ok">$lbl</span>"""
        } else {
            val lbl = if (en) "Clocked out" else "Ulosleimattuna"
            """<span class="badge badge-wait">$lbl</span>"""
        }

        val rowsHtml = history.split("\n").filter { it.isNotBlank() }.joinToString("") { line ->
            val p = line.split("|").map { it.trim() }
            if (p.size >= 3) {
                val isIn = p[2].equals("Sisään", ignoreCase = true) || p[2].equals("In", ignoreCase = true)
                val typeColor = if (isIn) "#4ADE80" else "#F87171"
                val dirLabel = if (en) (if (isIn) "In" else "Out") else (if (isIn) "Sisään" else "Ulos")
                """<tr>
                    <td>${p[0]}</td>
                    <td><strong>${p[1]}</strong></td>
                    <td style="color:$typeColor;font-weight:700;">$dirLabel</td>
                </tr>"""
            } else ""
        }

        val todayCaption = if (en) "Today (${today.format(fmt)})" else "Tänään (${today.format(fmt)})"
        val workplaceText = if (en) "Central Care Unit Helmi" else "Keskusyksikkö Helmi"
        val roleText = if (en) "Morning • Nurse" else "Aamu • Hoitaja"
        val reasonLabel = if (en) "Reason code" else "Syykoodi"
        val reasonOpt0 = if (en) "Regular working hours" else "Normaali työaika"
        val reasonOpt1 = if (en) "Flextime" else "Liukuma"
        val reasonOpt2 = if (en) "Work errand" else "Työasiointi"
        val commentLabel = if (en) "Comment" else "Kommentti"
        val commentHint = if (en) "Optional note..." else "Valinnainen lisätieto..."
        val recentCaption = if (en) "Recent stamps" else "Viimeisimmät leimaukset"
        val tabLabel = if (en) "Stamps" else "Leimaukset"
        val thDate = if (en) "Date" else "Päivämäärä"
        val thTime = if (en) "Time" else "Aika"
        val thDir = if (en) "Direction" else "Suunta"

        val extraCss = """
            .punching-shift-times {
                display: block;
                font-size: 24px;
                font-weight: 700;
                color: #FFFFFF;
                line-height: 1.25;
                margin-bottom: 6px;
            }
            .punching-shift-workplace {
                display: block;
                font-size: 16px;
                font-weight: 600;
                color: #38BDF8;
                line-height: 1.3;
                margin-bottom: 2px;
            }
            .punching-shift-role {
                display: block;
                font-size: 14px;
                font-weight: 500;
                color: #CBD5E1;
                line-height: 1.3;
            }
            .nav-tabs-wts {
                list-style: none;
                padding: 0;
                margin: 0 0 8px 0;
                border-bottom: 1px solid #2A394A;
                display: flex;
            }
            .nav-tabs-wts li span {
                display: inline-block;
                padding: 6px 12px;
                color: #F1F5F9;
                border-bottom: 2px solid #2196F3;
                font-weight: 600;
                font-size: 13px;
            }
        """.trimIndent()

        return """
        ${appDarkHead(pageTitle, extraCss)}
        <body>
            <div class="container">
                <div class="page-header-row">
                    <h1>$pageTitle</h1>
                    ${langSwitchHtml(en)}
                </div>

                <div class="panel">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                        <span class="section-caption" style="margin:0;">$todayCaption</span>
                        $statusBadge
                    </div>
                    <span class="punching-shift-times">07:00 - 15:00</span>
                    <span class="punching-shift-workplace">$workplaceText</span>
                    <span class="punching-shift-role">$roleText</span>
                </div>

                <div class="panel">
                    <div class="form-group">
                        <label class="form-label" for="stampReason">$reasonLabel</label>
                        <select id="stampReason" class="form-control">
                            <option value="0">$reasonOpt0</option>
                            <option value="1">$reasonOpt1</option>
                            <option value="2">$reasonOpt2</option>
                        </select>
                    </div>
                    <div class="form-group" style="margin-bottom:16px;">
                        <label class="form-label" for="stampInfo">$commentLabel</label>
                        <input id="stampInfo" type="text" class="form-control" placeholder="$commentHint" />
                    </div>
                    <button id="punchButton" type="button" onclick="DemoBridge.toggleStamp()" class="$btnClass">
                        $btnText
                    </button>
                </div>

                <div class="panel">
                    <span class="section-caption">$recentCaption</span>
                    <ul class="nav-tabs-wts">
                        <li><span>$tabLabel</span></li>
                    </ul>
                    <table id="table-latest-stamps" class="table">
                        <thead>
                            <tr>
                                <th>$thDate</th>
                                <th>$thTime</th>
                                <th>$thDir</th>
                            </tr>
                        </thead>
                        <tbody>
                            $rowsHtml
                        </tbody>
                    </table>
                </div>
            </div>
        </body>
        </html>
        """.trimIndent()
    }

    fun getDemoRequestsHtml(context: Context): String {
        val en = isEnglish(context)
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val today = LocalDate.now()
        val fmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")
        val defaultDateStr = today.plusDays(10).format(fmt)

        val defaultRequests = if (en) {
            "${today.plusDays(5).format(fmt)} | Annual leave | Approved\n${today.plusDays(12).format(fmt)} | Day off | Pending approval"
        } else {
            "${today.plusDays(5).format(fmt)} | Vuosiloma | Hyväksytty\n${today.plusDays(12).format(fmt)} | Vapaapäivä | Odottaa käsittelyä"
        }
        val reqList = prefs.getString("demo_requests", defaultRequests) ?: defaultRequests

        val itemsHtml = reqList.split("\n").filter { it.isNotBlank() }.joinToString("") { line ->
            val p = line.split("|").map { it.trim() }
            if (p.size >= 3) {
                val badgeClass = if (
                    p[2].contains("Hyväksytty", ignoreCase = true) ||
                    p[2].contains("Approved", ignoreCase = true)
                ) "badge badge-ok" else "badge badge-wait"
                """<tr>
                    <td>${p[0]}</td>
                    <td><strong>${p[1]}</strong></td>
                    <td><span class="$badgeClass">${p[2]}</span></td>
                </tr>"""
            } else ""
        }

        val pageTitle = if (en) "Shift Requests" else "Toiveet"
        val reqTypeLabel = if (en) "Request type" else "Toivetyyppi"
        val optionsHtml = if (en) {
            """
            <option value="Morning or day off">Morning or day off</option>
            <option value="Morning shift">Morning shift</option>
            <option value="No morning shift">No morning shift</option>
            <option value="No evening shift">No evening shift</option>
            <option value="No long shift">No long shift</option>
            <option value="No day off">No day off</option>
            <option value="No night shift">No night shift</option>
            <option value="Evening or day off">Evening or day off</option>
            <option value="Evening shift">Evening shift</option>
            <option value="Training">Training</option>
            <option value="Shortened day">Shortened day</option>
            <option value="Long shift">Long shift</option>
            <option value="U-Shift">U-Shift</option>
            <option value="Day off" selected="selected">Day off</option>
            <option value="Weekend off (Sat & Sun)">Weekend off (Sat &amp; Sun)</option>
            <option value="Night or day off">Night or day off</option>
            <option value="Night shift">Night shift</option>
            <option value="Annual leave">Annual leave</option>
            """.trimIndent()
        } else {
            """
            <option value="Aamu tai vapaa">Aamu tai vapaa</option>
            <option value="Aamuvuoro">Aamuvuoro</option>
            <option value="Ei aamuvuoroa">Ei aamuvuoroa</option>
            <option value="Ei iltavuoroa">Ei iltavuoroa</option>
            <option value="Ei pitkää päivää">Ei pitkää päivää</option>
            <option value="Ei vapaapäivää">Ei vapaapäivää</option>
            <option value="Ei yövuoroa">Ei yövuoroa</option>
            <option value="Ilta tai vapaa">Ilta tai vapaa</option>
            <option value="Iltavuoro">Iltavuoro</option>
            <option value="Koulutus">Koulutus</option>
            <option value="Lyhennys (päivätyö)">Lyhennys (päivätyö)</option>
            <option value="Pitkä päivä">Pitkä päivä</option>
            <option value="U-Vuoro">U-Vuoro</option>
            <option value="Vapaapäivä" selected="selected">Vapaapäivä</option>
            <option value="Viikonloppuvapaa (la&su)">Viikonloppuvapaa (la&amp;su)</option>
            <option value="Yö tai vapaa">Yö tai vapaa</option>
            <option value="Yövuoro">Yövuoro</option>
            <option value="Vuosiloma">Vuosiloma</option>
            """.trimIndent()
        }

        val fullDayLabel = if (en) "Full day" else "Koko päivän"
        val startsLabel = if (en) "Starts" else "Alkaa"
        val endsLabel = if (en) "Ends" else "Päättyy"
        val infoLabel = if (en) "Note" else "Info"
        val microcopyHtml = if (en) {
            """Characters left <span id="NumbersOfChar">255</span> • Please do not enter sensitive personal data."""
        } else {
            """Merkkejä jäljellä <span id="NumbersOfChar">255</span> • Ethän kirjoita arkaluontoista henkilötietoa, kiitos!"""
        }
        val saveLabel = if (en) "Save" else "Tallenna"
        val cancelLabel = if (en) "Cancel" else "Peruuta"
        val myRequestsCaption = if (en) "My requests" else "Omat toiveet"
        val thDate = if (en) "Date" else "Päivämäärä"
        val thType = if (en) "Request type" else "Toivetyyppi"
        val thStatus = if (en) "Status" else "Tila"

        val extraCss = """
            .two-col { display: flex; gap: 8px; }
            .two-col > div { flex: 1; }
            .microcopy { font-size: 11px; color: #94A3B8; margin-top: 6px; }
            .switch-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 4px 0;
            }
            .toggle-pill {
                width: 50px;
                height: 28px;
                border-radius: 14px;
                background-color: #1982C4;
                border: 1px solid #38BDF8;
                position: relative;
                cursor: pointer;
                transition: background-color 0.2s;
            }
            .toggle-pill.off {
                background-color: #233040;
                border-color: #475569;
            }
            .toggle-knob {
                width: 22px;
                height: 22px;
                border-radius: 50%;
                background-color: #FFFFFF;
                position: absolute;
                top: 2px;
                left: 24px;
                transition: left 0.2s;
            }
            .toggle-pill.off .toggle-knob {
                left: 2px;
            }
            .footer-actions {
                display: flex;
                flex-direction: column;
                gap: 8px;
                margin-top: 14px;
            }
        """.trimIndent()

        return """
        ${appDarkHead(pageTitle, extraCss)}
        <body>
            <div class="container">
                <div class="page-header-row">
                    <h1>$pageTitle</h1>
                    ${langSwitchHtml(en)}
                </div>

                <div class="panel">
                    <div class="form-group">
                        <label class="form-label" for="PersonRequestTypeId">$reqTypeLabel<span class="required-star">*</span></label>
                        <select class="form-control" id="PersonRequestTypeId">
                            $optionsHtml
                        </select>
                    </div>

                    <hr />

                    <div class="form-group">
                        <div class="switch-row">
                            <span class="form-label" style="margin:0;">$fullDayLabel</span>
                            <div id="FullDaySwitch" class="toggle-pill" onclick="toggleFullDaySwitch()">
                                <div class="toggle-knob"></div>
                            </div>
                        </div>
                    </div>

                    <div class="form-group">
                        <label class="form-label">$startsLabel<span class="required-star">*</span></label>
                        <div class="two-col">
                            <div class="input-group">
                                <input class="form-control" id="DateFromInput" type="text" value="$defaultDateStr" />
                                <span class="input-group-addon">📅</span>
                            </div>
                            <div class="input-group">
                                <input class="form-control" id="TimeFromInput" type="text" value="08:00:00" disabled />
                                <span class="input-group-addon">🕒</span>
                            </div>
                        </div>
                    </div>

                    <div class="form-group">
                        <label class="form-label">$endsLabel<span class="required-star">*</span></label>
                        <div class="two-col">
                            <div class="input-group">
                                <input class="form-control" id="DateToInput" type="text" value="$defaultDateStr" />
                                <span class="input-group-addon">📅</span>
                            </div>
                            <div class="input-group">
                                <input class="form-control" id="TimeToInput" type="text" value="16:00:00" disabled />
                                <span class="input-group-addon">🕒</span>
                            </div>
                        </div>
                    </div>

                    <hr />

                    <div class="form-group" style="margin-bottom:0;">
                        <label class="form-label" for="InfoTextArea">$infoLabel</label>
                        <textarea class="form-control" id="InfoTextArea" maxlength="255" rows="2" oninput="document.getElementById('NumbersOfChar').textContent = (255 - this.value.length);"></textarea>
                        <div class="microcopy">$microcopyHtml</div>
                    </div>

                    <div class="footer-actions">
                        <button id="SaveSingleRequestBtn" type="button" class="btn btn-primary" style="width:100%;padding:12px;" onclick="submitDemoRequest()">
                            $saveLabel
                        </button>
                        <button type="button" class="btn" style="width:100%;" onclick="document.getElementById('InfoTextArea').value='';document.getElementById('NumbersOfChar').textContent='255';">
                            $cancelLabel
                        </button>
                    </div>
                </div>

                <div class="panel">
                    <span class="section-caption">$myRequestsCaption</span>
                    <table class="table">
                        <thead>
                            <tr>
                                <th>$thDate</th>
                                <th>$thType</th>
                                <th>$thStatus</th>
                            </tr>
                        </thead>
                        <tbody>
                            $itemsHtml
                        </tbody>
                    </table>
                </div>
            </div>
            <script>
                var fullDayActive = true;
                function toggleFullDaySwitch() {
                    fullDayActive = !fullDayActive;
                    var sw = document.getElementById('FullDaySwitch');
                    if (fullDayActive) {
                        sw.classList.remove('off');
                    } else {
                        sw.classList.add('off');
                    }
                    document.getElementById('TimeFromInput').disabled = fullDayActive;
                    document.getElementById('TimeToInput').disabled = fullDayActive;
                }
                function submitDemoRequest() {
                    var type = document.getElementById('PersonRequestTypeId').value;
                    var dateVal = document.getElementById('DateFromInput').value || '$defaultDateStr';
                    if (DemoBridge.addRequestWithDate) {
                        DemoBridge.addRequestWithDate(type, dateVal);
                    } else {
                        DemoBridge.addRequest(type);
                    }
                }
            </script>
        </body>
        </html>
        """.trimIndent()
    }

    fun getDemoShiftsHtml(context: Context): String {
        val en = isEnglish(context)
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val variant = prefs.getInt("demo_shift_variant", 0)
        val today = LocalDate.now()
        val ym = YearMonth.from(today)

        val monthNames = if (en) {
            listOf(
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"
            )
        } else {
            listOf(
                "Tammikuu", "Helmikuu", "Maaliskuu", "Huhtikuu", "Toukokuu", "Kesäkuu",
                "Heinäkuu", "Elokuu", "Syyskuu", "Lokakuu", "Marraskuu", "Joulukuu"
            )
        }
        val monthTitle = "${monthNames[ym.monthValue - 1]} ${ym.year}"
        val leaveCellLabel = if (en) "Leave" else "Loma"

        data class CalCellItem(val isAbsence: Boolean, val times: String, val label: String)
        val itemMap = mutableMapOf<LocalDate, CalCellItem>()

        // Toteutuneita mallivuoroja kuukauden alkuun
        val samplePastDays = listOf(2, 3, 7, 8, 12, 13)
        for (d in samplePastDays) {
            if (d <= ym.lengthOfMonth()) {
                val dt = ym.atDay(d)
                if (dt.isBefore(today)) {
                    val isEvening = (d % 2 == 0)
                    itemMap[dt] = if (isEvening) {
                        CalCellItem(false, "12:45-20:30", if (en) "Evening" else "Ilta")
                    } else {
                        CalCellItem(false, "07:00-14:30", if (en) "Morning" else "Aamu")
                    }
                }
            }
        }

        // Tulevat demovuorot (täsmäävät generateDemoWorkShifts-listaan)
        if (variant % 2 == 0) {
            itemMap[today.plusDays(1)] = CalCellItem(false, "07:00-15:00", if (en) "Morning" else "Aamu")
            itemMap[today.plusDays(2)] = CalCellItem(false, "13:00-21:00", if (en) "Evening" else "Ilta")
            itemMap[today.plusDays(3)] = CalCellItem(false, "21:00-07:00", if (en) "Night" else "Yö")
            itemMap[today.plusDays(5)] = CalCellItem(true, leaveCellLabel, if (en) "Annual leave" else "Vuosiloma")
            itemMap[today.plusDays(6)] = CalCellItem(true, leaveCellLabel, if (en) "Annual leave" else "Vuosiloma")
        } else {
            itemMap[today.plusDays(1)] = CalCellItem(false, "13:00-21:00", if (en) "Evening (Changed)" else "Ilta (Muuttunut)")
            itemMap[today.plusDays(2)] = CalCellItem(false, "13:00-21:00", if (en) "Evening" else "Ilta")
            itemMap[today.plusDays(4)] = CalCellItem(false, "07:00-15:00", if (en) "Morning (New)" else "Aamu (Uusi)")
            itemMap[today.plusDays(5)] = CalCellItem(true, leaveCellLabel, if (en) "Annual leave" else "Vuosiloma")
            itemMap[today.plusDays(6)] = CalCellItem(true, leaveCellLabel, if (en) "Annual leave" else "Vuosiloma")
        }

        val firstOfMonth = ym.atDay(1)
        val lastOfMonth = ym.atEndOfMonth()
        val gridStart = firstOfMonth.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
        val gridEnd = lastOfMonth.with(TemporalAdjusters.nextOrSame(DayOfWeek.SUNDAY))
        val weekFields = WeekFields.of(Locale("fi", "FI"))

        val weeksHtml = StringBuilder()
        var cursor = gridStart
        while (!cursor.isAfter(gridEnd)) {
            val weekNum = cursor.get(weekFields.weekOfWeekBasedYear())
            weeksHtml.append("""<tr class="month-week"><td class="month-week-number">$weekNum</td>""")
            for (i in 0 until 7) {
                val cellDate = cursor.plusDays(i.toLong())
                val isDiffMonth = cellDate.monthValue != ym.monthValue
                val isPast = cellDate.isBefore(today)
                val isToday = cellDate.isEqual(today)

                val tdClasses = buildList {
                    add("month-day")
                    if (isPast) add("past-day")
                    if (isDiffMonth) add("day-different-month")
                    if (isToday) add("todayTd")
                }.joinToString(" ")

                val item = itemMap[cellDate]
                val itemHtml = when {
                    item == null -> ""
                    item.isAbsence -> """
                        <div class="month-item absence">
                            <span class="itemTimes">${item.times}</span>
                        </div>
                    """.trimIndent()
                    else -> """
                        <div class="month-item work">
                            <span class="itemTimes">${item.times}</span>
                        </div>
                    """.trimIndent()
                }

                weeksHtml.append(
                    """<td class="$tdClasses" data-day="${cellDate.dayOfMonth}">
                        <div class="month-day-header">
                            <span class="dayNum">${cellDate.dayOfMonth}</span>
                        </div>
                        $itemHtml
                    </td>"""
                )
            }
            weeksHtml.append("</tr>")
            cursor = cursor.plusWeeks(1)
        }

        val pageTitle = if (en) "Shifts" else "Työvuorot"
        val dayHeadersHtml = if (en) {
            "<td>Wk</td><td>Mon</td><td>Tue</td><td>Wed</td><td>Thu</td><td>Fri</td><td>Sat</td><td>Sun</td>"
        } else {
            "<td>Vk</td><td>Ma</td><td>Ti</td><td>Ke</td><td>To</td><td>Pe</td><td>La</td><td>Su</td>"
        }
        val toolsCaption = if (en) "Demo mode calendar actions" else "Demotilan kalenteritoiminnot"
        val btnExportText = if (en) "Export demo shifts to phone calendar" else "Vie demovuorot puhelimen kalenteriin"
        val btnSimulateText = if (en) "Simulate shift change & sync (test undo)" else "Simuloi vuoromuutos ja synkronoi (testaa perumista)"
        val btnManageText = if (en) "Manage / Undo calendar changes" else "Hallitse / Peru kalenterimuutoksia"

        val extraCss = """
            .calendar-heading {
                display: flex;
                justify-content: space-between;
                align-items: center;
                background-color: #182332;
                border: 1px solid #2A394A;
                border-radius: 12px;
                padding: 8px 12px;
                margin-bottom: 12px;
            }
            .monthSelector {
                display: flex;
                align-items: center;
                gap: 10px;
            }
            #monthText {
                color: #F1F5F9;
                font-size: 17px;
                font-weight: 600;
                margin: 0;
            }
            .nav-arrow {
                color: #38BDF8;
                font-size: 15px;
                user-select: none;
            }
            .month-table {
                width: 100%;
                table-layout: fixed;
                border-collapse: collapse;
                background-color: #182332;
                margin-bottom: 14px;
            }
            .month-week-days td {
                background-color: #233040;
                color: #CBD5E1;
                font-weight: 600;
                font-size: 12px;
                padding: 6px 2px;
                border: 1px solid #2A394A;
                text-align: center;
            }
            .month-week-number {
                width: 26px;
                background-color: #131C28;
                color: #64748B;
                font-size: 11px;
                text-align: center;
                vertical-align: top;
                padding-top: 6px;
                border: 1px solid #2A394A;
            }
            td.month-day {
                background-color: #182332;
                border: 1px solid #2A394A;
                vertical-align: top;
                height: 68px;
                padding: 2px;
            }
            td.month-day.past-day, td.month-day.day-different-month {
                background-color: #121A24;
            }
            td.month-day.todayTd {
                background-color: #1E3A5F;
                border: 1px solid #38BDF8;
            }
            .month-day-header {
                margin-bottom: 2px;
            }
            .dayNum {
                color: #F1F5F9;
                font-size: 12px;
                font-weight: 600;
                padding-left: 3px;
            }
            td.day-different-month .dayNum {
                color: #64748B;
            }
            .month-item.work {
                background-color: #0284C7;
                color: #FFFFFF;
                border-radius: 4px;
                padding: 2px 3px;
                margin-bottom: 2px;
                font-size: 10px;
                line-height: 1.2;
                overflow: hidden;
            }
            td.month-day.past-day .month-item.work {
                opacity: 0.75;
            }
            .month-item.absence {
                background-color: #D97706;
                color: #FFFFFF;
                border-radius: 4px;
                padding: 2px 3px;
                margin-bottom: 2px;
                font-size: 10px;
                line-height: 1.2;
                overflow: hidden;
            }
            .itemTimes {
                display: block;
                color: #FFFFFF;
                font-weight: 600;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .demo-tools-grid {
                display: flex;
                flex-direction: column;
                gap: 8px;
            }
        """.trimIndent()

        return """
        ${appDarkHead(pageTitle, extraCss)}
        <body>
            <div class="container">
                <div class="calendar-heading">
                    <div class="monthSelector">
                        <span class="nav-arrow">◀</span>
                        <span id="monthText">$monthTitle</span>
                        <span class="nav-arrow">▶</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:6px;">
                        ${langSwitchHtml(en)}
                        <span class="badge badge-ok">DEMO</span>
                    </div>
                </div>

                <table class="month-table">
                    <tbody>
                        <tr class="month-week-days">
                            $dayHeadersHtml
                        </tr>
                        $weeksHtml
                    </tbody>
                </table>

                <div class="panel">
                    <span class="section-caption">$toolsCaption</span>
                    <div class="demo-tools-grid">
                        <button type="button" onclick="DemoBridge.syncDemoCalendar()" class="btn btn-primary" style="width:100%;">
                            $btnExportText
                        </button>
                        <button type="button" onclick="DemoBridge.simulateShiftUpdateAndSync()" class="btn" style="width:100%;border-color:#F59E0B;color:#FBBF24;">
                            $btnSimulateText
                        </button>
                        <button type="button" onclick="DemoBridge.openChangesManager()" class="btn" style="width:100%;">
                            $btnManageText
                        </button>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """.trimIndent()
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

    class DemoJsBridge(
        private val context: Context,
        private val onReloadNeeded: () -> Unit,
        private val onSyncRequested: () -> Unit,
        private val onManageChangesRequested: () -> Unit
    ) {
        @JavascriptInterface
        fun setLanguage(lang: String) {
            setDemoLanguage(context, lang)
            onReloadNeeded()
        }

        @JavascriptInterface
        fun toggleStamp() {
            val en = isEnglish(context)
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val current = prefs.getBoolean("demo_stamped_in", false)
            val nextState = !current
            val actionLabel = if (en) {
                if (nextState) "In" else "Out"
            } else {
                if (nextState) "Sisään" else "Ulos"
            }

            val nowDate = LocalDate.now().format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
            val nowTime = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
            val oldHistory = prefs.getString("demo_stamp_history", "") ?: ""
            val newHistory = "$nowDate | $nowTime | $actionLabel\n$oldHistory"

            prefs.edit()
                .putBoolean("demo_stamped_in", nextState)
                .putString("demo_stamp_history", newHistory)
                .apply()

            android.os.Handler(android.os.Looper.getMainLooper()).post {
                val msg = if (en) {
                    "Demo stamp recorded: $actionLabel ($nowTime)"
                } else {
                    "Demoleimaus suoritettu: $actionLabel ($nowTime)"
                }
                Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()
            }
            onReloadNeeded()
        }

        @JavascriptInterface
        fun addRequest(type: String) {
            val dateStr = LocalDate.now().plusDays(10).format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
            addRequestWithDate(type, dateStr)
        }

        @JavascriptInterface
        fun addRequestWithDate(type: String, dateStr: String) {
            val en = isEnglish(context)
            val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val cleanDate = dateStr.trim().ifEmpty {
                LocalDate.now().plusDays(10).format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
            }
            val statusLabel = if (en) "Pending approval" else "Odottaa käsittelyä"
            val oldList = prefs.getString("demo_requests", "") ?: ""
            val newList = "$cleanDate | $type | $statusLabel\n$oldList"
            prefs.edit().putString("demo_requests", newList).apply()

            android.os.Handler(android.os.Looper.getMainLooper()).post {
                val msg = if (en) {
                    "Demo request added: $type ($cleanDate)"
                } else {
                    "Demotoive lisätty: $type ($cleanDate)"
                }
                Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()
            }
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
'''


SETTINGS_DIALOG_HELPER_KT = r'''package fi.numeron.vuorovahti

import android.Manifest
import android.app.AlertDialog
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.provider.CalendarContract
import android.content.res.ColorStateList
import android.text.InputType
import android.text.method.PasswordTransformationMethod
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.Switch
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.work.WorkManager
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

data class CalendarOption(
    val id: Long,
    val name: String,
    val accountName: String,
    val accountType: String,
    val isEnglish: Boolean = false
) {
    override fun toString(): String {
        val typeTag = if (accountType == "com.google") "Google" else if (isEnglish) "Local" else "Paikallinen"
        return "$name ($accountName) [$typeTag]"
    }
}

data class ShiftColorChoice(
    val name: String,
    val rgb: Int,
    val enName: String = name,
    val isEnglish: Boolean = false
) {
    override fun toString(): String = if (isEnglish) enName else name
}

object SettingsDialogHelper {

    val SHIFT_COLOR_CHOICES = listOf(
        ShiftColorChoice("Basilika (Vihreä)", Color.rgb(11, 128, 67), "Basil (Green)"),
        ShiftColorChoice("Salvia (Vaaleanvihreä)", Color.rgb(51, 182, 121), "Sage (Light green)"),
        ShiftColorChoice("Mandariini (Oranssi)", Color.rgb(244, 81, 30), "Tangerine (Orange)"),
        ShiftColorChoice("Banaani (Keltainen)", Color.rgb(246, 191, 38), "Banana (Yellow)"),
        ShiftColorChoice("Viinirypäle (Lila)", Color.rgb(142, 36, 170), "Grape (Purple)"),
        ShiftColorChoice("Mustikka (Sininen)", Color.rgb(63, 81, 181), "Blueberry (Blue)"),
        ShiftColorChoice("Riikinkukko (Turkoosi)", Color.rgb(3, 155, 229), "Peacock (Turquoise)"),
        ShiftColorChoice("Flamingo (Vaaleanpunainen)", Color.rgb(230, 124, 115), "Flamingo (Pink)"),
        ShiftColorChoice("Tomaatti (Punainen)", Color.rgb(213, 0, 0), "Tomato (Red)"),
        ShiftColorChoice("Grafiitti (Harmaa)", Color.rgb(97, 97, 97), "Graphite (Gray)")
    )

    val DEFAULT_MORNING_RGB = Color.rgb(11, 128, 67)
    val DEFAULT_EVENING_RGB = Color.rgb(244, 81, 30)
    val DEFAULT_NIGHT_RGB = Color.rgb(142, 36, 170)

    fun getAvailableCalendars(context: Context): List<CalendarOption> {
        val en = DemoModeHelper.isEnglish(context)
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED) {
            return emptyList()
        }
        val list = mutableListOf<CalendarOption>()
        val projection = arrayOf(
            CalendarContract.Calendars._ID,
            CalendarContract.Calendars.CALENDAR_DISPLAY_NAME,
            CalendarContract.Calendars.ACCOUNT_NAME,
            CalendarContract.Calendars.ACCOUNT_TYPE,
            CalendarContract.Calendars.IS_PRIMARY
        )
        val selection = "${CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL} >= ? AND ${CalendarContract.Calendars.VISIBLE} = 1"
        val selectionArgs = arrayOf(CalendarContract.Calendars.CAL_ACCESS_CONTRIBUTOR.toString())

        context.contentResolver.query(
            CalendarContract.Calendars.CONTENT_URI,
            projection,
            selection,
            selectionArgs,
            null
        )?.use { cursor ->
            while (cursor.moveToNext()) {
                val id = cursor.getLong(0)
                val name = cursor.getString(1) ?: (if (en) "Calendar" else "Kalenteri")
                val account = cursor.getString(2) ?: ""
                val accountType = cursor.getString(3) ?: ""
                val isPrimary = cursor.getInt(4) == 1
                list.add(CalendarOption(id, name, account, accountType, en))
                if (accountType == "com.google" && (isPrimary || name.equals(account, ignoreCase = true))) {
                    val item = list.removeAt(list.lastIndex)
                    list.add(0, item)
                }
            }
        }
        return list.sortedBy { if (it.accountType == "com.google") 0 else 1 }
    }

    private fun formatTimestamp(ms: Long, fallback: String, en: Boolean = false): String {
        if (ms <= 0L) return fallback
        val fmt = DateTimeFormatter.ofPattern(if (en) "dd.MM.yyyy 'at' HH:mm" else "dd.MM.yyyy 'klo' HH:mm")
        return Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).format(fmt)
    }

    private fun resolveNextSyncMs(context: Context, fallbackSavedMs: Long): Long {
        try {
            val infos = WorkManager.getInstance(context)
                .getWorkInfosForUniqueWork("NumeronVuorovahtiSync")
                .get()
            val nextRun = infos.firstOrNull { !it.state.isFinished }?.nextScheduleTimeMillis ?: 0L
            if (nextRun > System.currentTimeMillis() && nextRun < Long.MAX_VALUE) {
                return nextRun
            }
        } catch (_: Exception) {
        }
        return fallbackSavedMs
    }

    fun showSettingsDialog(
        context: Context,
        onManualSync: () -> Unit,
        onManageChanges: () -> Unit,
        onTestNotification: () -> Unit,
        onSaved: () -> Unit
    ) {
        val en = DemoModeHelper.isEnglish(context)
        val isDemoActive = DemoModeHelper.isDemoEnabled(context)
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val density = context.resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()

        fun makeCardBg(fillHex: String = "#182332", strokeHex: String = "#2A394A", radiusDp: Int = 12): GradientDrawable {
            return GradientDrawable().apply {
                setColor(Color.parseColor(fillHex))
                setStroke(dp(1), Color.parseColor(strokeHex))
                cornerRadius = dp(radiusDp).toFloat()
            }
        }

        val rootContainer = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#0F1722"))
        }

        val headerBar = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(20), dp(18), dp(20), dp(14))
        }
        val headerTitleCol = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }
        headerTitleCol.addView(TextView(context).apply {
            text = if (en) "Vuorovahti – Settings" else "Vuorovahti – Asetukset"
            textSize = 19f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#F1F5F9"))
        })
        headerTitleCol.addView(TextView(context).apply {
            text = if (en) "Credentials, calendar sync & notifications" else "Tunnukset, kalenterisynkronointi ja ilmoitukset"
            textSize = 12f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, dp(2), 0, 0)
        })
        headerBar.addView(headerTitleCol)

        var dialogRef: AlertDialog? = null

        if (isDemoActive) {
            val langPill = LinearLayout(context).apply {
                orientation = LinearLayout.HORIZONTAL
                background = makeCardBg("#111923", "#2A394A", 8)
                setPadding(dp(2), dp(2), dp(2), dp(2))
            }
            fun makeLangBtn(label: String, targetLang: String, active: Boolean): TextView {
                return TextView(context).apply {
                    text = label
                    textSize = 11f
                    setTypeface(null, Typeface.BOLD)
                    setTextColor(Color.parseColor(if (active) "#FFFFFF" else "#94A3B8"))
                    setPadding(dp(9), dp(5), dp(9), dp(5))
                    if (active) {
                        background = makeCardBg("#1982C4", "#38BDF8", 6)
                    }
                    setOnClickListener {
                        DemoModeHelper.setDemoLanguage(context, targetLang)
                        dialogRef?.dismiss()
                        onSaved()
                        showSettingsDialog(context, onManualSync, onManageChanges, onTestNotification, onSaved)
                    }
                }
            }
            langPill.addView(makeLangBtn("FI", "fi", !en))
            langPill.addView(makeLangBtn("EN", "en", en))
            headerBar.addView(langPill)
        }

        rootContainer.addView(headerBar)

        val divider = View(context).apply {
            setBackgroundColor(Color.parseColor("#2A394A"))
        }
        rootContainer.addView(divider, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)))

        val scrollView = ScrollView(context).apply {
            isFillViewport = true
        }
        val layout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(14), dp(16), dp(16))
        }
        scrollView.addView(layout)
        rootContainer.addView(scrollView, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))

        fun createSectionCard(title: String): LinearLayout {
            val card = LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                background = makeCardBg("#182332", "#2A394A", 12)
                setPadding(dp(16), dp(14), dp(16), dp(16))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    bottomMargin = dp(14)
                }
            }
            val sectionHeader = TextView(context).apply {
                text = title.uppercase()
                textSize = 11f
                letterSpacing = 0.06f
                setTypeface(null, Typeface.BOLD)
                setTextColor(Color.parseColor("#38BDF8"))
                setPadding(0, 0, 0, dp(8))
            }
            card.addView(sectionHeader)
            layout.addView(card)
            return card
        }

        fun createLabel(text: String): TextView = TextView(context).apply {
            this.text = text
            textSize = 13f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, dp(10), 0, dp(5))
        }

        fun styleEditText(et: EditText) {
            et.background = makeCardBg("#111923", "#37475A", 8)
            et.setTextColor(Color.parseColor("#F1F5F9"))
            et.setHintTextColor(Color.parseColor("#64748B"))
            et.setPadding(dp(12), dp(10), dp(12), dp(10))
            et.textSize = 14f
        }

        fun styleButton(btn: Button, bgHex: String = "#233040", strokeHex: String = "#37475A", textHex: String = "#F1F5F9") {
            btn.background = makeCardBg(bgHex, strokeHex, 8)
            btn.setTextColor(Color.parseColor(textHex))
            btn.isAllCaps = false
            btn.textSize = 14f
            btn.setTypeface(null, Typeface.BOLD)
            btn.setPadding(dp(14), dp(11), dp(14), dp(11))
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                topMargin = dp(10)
            }
            btn.layoutParams = lp
        }

        fun styleSpinner(spinner: Spinner) {
            spinner.background = makeCardBg("#111923", "#37475A", 8)
            spinner.setPadding(dp(8), dp(6), dp(8), dp(6))
        }

        fun createToggleRow(
            parent: LinearLayout,
            title: String,
            subtitle: String,
            initialChecked: Boolean,
            onToggle: ((Boolean) -> Unit)? = null
        ): Switch {
            val row = LinearLayout(context).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                background = makeCardBg("#111923", "#2A394A", 8)
                setPadding(dp(12), dp(10), dp(12), dp(10))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    topMargin = dp(6)
                    bottomMargin = dp(4)
                }
            }

            val textCol = LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
                    marginEnd = dp(10)
                }
            }
            textCol.addView(TextView(context).apply {
                text = title
                textSize = 14f
                setTypeface(null, Typeface.BOLD)
                setTextColor(Color.parseColor("#F1F5F9"))
            })
            textCol.addView(TextView(context).apply {
                text = subtitle
                textSize = 12f
                setTextColor(Color.parseColor("#94A3B8"))
                setPadding(0, dp(2), 0, 0)
            })

            val sw = Switch(context).apply {
                isChecked = initialChecked
                thumbTintList = ColorStateList(
                    arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()),
                    intArrayOf(Color.parseColor("#38BDF8"), Color.parseColor("#94A3B8"))
                )
                trackTintList = ColorStateList(
                    arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()),
                    intArrayOf(Color.parseColor("#1E3A5F"), Color.parseColor("#233040"))
                )
                setOnCheckedChangeListener { _, checked ->
                    onToggle?.invoke(checked)
                }
            }

            row.setOnClickListener {
                sw.isChecked = !sw.isChecked
            }

            row.addView(textCol)
            row.addView(sw)
            parent.addView(row)
            return sw
        }

        fun createDarkAdapter(items: List<Any>): ArrayAdapter<Any> {
            return object : ArrayAdapter<Any>(context, android.R.layout.simple_spinner_item, items) {
                override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
                    val tv = super.getView(position, convertView, parent) as TextView
                    tv.setTextColor(Color.parseColor("#F1F5F9"))
                    tv.textSize = 14f
                    return tv
                }

                override fun getDropDownView(position: Int, convertView: View?, parent: ViewGroup): View {
                    val tv = super.getDropDownView(position, convertView, parent) as TextView
                    tv.setBackgroundColor(Color.parseColor("#1E293B"))
                    tv.setTextColor(Color.parseColor("#F1F5F9"))
                    tv.setPadding(dp(14), dp(12), dp(14), dp(12))
                    tv.textSize = 14f
                    return tv
                }
            }
        }

        // === KORTTI 1: TILA JA AIKATAULUT ===
        val statusCard = createSectionCard(if (en) "Status and schedules" else "Tila ja aikataulut")

        val initialSyncCalendar = prefs.getBoolean("sync_calendar_enabled", true)
        val initialShiftReminders = prefs.getBoolean("shift_reminders_enabled", true)
        val initialTrackRequests = prefs.getBoolean("track_requests", true)
        val anyBackgroundEnabled = initialSyncCalendar || initialShiftReminders || initialTrackRequests

        val lastSyncMs = prefs.getLong("last_calendar_sync_ms", 0L)
        val lastNotifMs = prefs.getLong("last_reminder_sent_ms", 0L)
        val lastNotifLabel = prefs.getString("last_reminder_sent_label", "") ?: ""
        val nextNotifMs = prefs.getLong("next_reminder_ms", 0L)
        val nextNotifLabel = prefs.getString("next_reminder_label", "") ?: ""

        fun canScheduleExactAlarmsCompat(): Boolean {
            return if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
                (context.getSystemService(Context.ALARM_SERVICE) as android.app.AlarmManager).canScheduleExactAlarms()
            } else {
                true
            }
        }

        fun launchSystemSettingsIntent(intent: android.content.Intent): Boolean {
            return try {
                if (context !is android.app.Activity) {
                    intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                context.startActivity(intent)
                true
            } catch (_: Exception) {
                false
            }
        }

        fun openExactAlarmSettings() {
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
                val pkgUri = android.net.Uri.parse("package:${context.packageName}")
                val opened = launchSystemSettingsIntent(
                    android.content.Intent(
                        android.provider.Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                        pkgUri
                    )
                )
                if (!opened) {
                    launchSystemSettingsIntent(
                        android.content.Intent(
                            android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                            pkgUri
                        )
                    )
                }
            }
        }

        fun openBatteryOptimizationSettings() {
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
        }

        fun addStatusRow(parent: LinearLayout, title: String, value: String, subValue: String? = null): Pair<TextView, TextView> {
            val box = LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                background = makeCardBg("#111923", "#233040", 8)
                setPadding(dp(12), dp(9), dp(12), dp(9))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    bottomMargin = dp(8)
                }
            }
            box.addView(TextView(context).apply {
                text = title
                textSize = 11f
                setTextColor(Color.parseColor("#94A3B8"))
            })
            val valueTv = TextView(context).apply {
                text = value
                textSize = 14f
                setTypeface(null, Typeface.BOLD)
                setTextColor(Color.parseColor("#F1F5F9"))
                setPadding(0, dp(2), 0, 0)
            }
            box.addView(valueTv)
            val subTv = TextView(context).apply {
                text = subValue ?: ""
                textSize = 12f
                setTextColor(Color.parseColor("#38BDF8"))
                setPadding(0, dp(2), 0, 0)
                visibility = if (!subValue.isNullOrEmpty()) View.VISIBLE else View.GONE
            }
            box.addView(subTv)
            parent.addView(box)
            return Pair(valueTv, subTv)
        }

        addStatusRow(
            statusCard,
            if (en) "Shifts and calendar checked" else "Työvuorot ja kalenteri tarkistettu",
            formatTimestamp(lastSyncMs, if (en) "Not checked yet" else "Ei vielä tarkistettu", en)
        )
        val (nextSyncValueTv, _) = addStatusRow(
            statusCard,
            if (en) "Next automatic check" else "Seuraava automaattinen tarkistus",
            if (!anyBackgroundEnabled) {
                if (en) "Disabled" else "Pois käytöstä"
            } else {
                formatTimestamp(
                    prefs.getLong("next_calendar_sync_ms", 0L),
                    if (en) "Weekdays at 09:30 and 14:30" else "Arkisin klo 09:30 ja 14:30",
                    en
                )
            }
        )
        if (anyBackgroundEnabled) {
            try {
                val future = WorkManager.getInstance(context).getWorkInfosForUniqueWork("NumeronVuorovahtiSync")
                future.addListener({
                    try {
                        val infos = future.get()
                        val nextRun = infos.firstOrNull { !it.state.isFinished }?.nextScheduleTimeMillis ?: 0L
                        if (nextRun > System.currentTimeMillis() && nextRun < Long.MAX_VALUE) {
                            nextSyncValueTv.text = formatTimestamp(
                                nextRun,
                                if (en) "Weekdays at 09:30 and 14:30" else "Arkisin klo 09:30 ja 14:30",
                                en
                            )
                        }
                    } catch (_: Exception) {
                    }
                }, ContextCompat.getMainExecutor(context))
            } catch (_: Exception) {
            }
        }
        addStatusRow(
            statusCard,
            if (en) "Last stamp notification sent" else "Edellinen leimausnotifikaatio lähetetty",
            formatTimestamp(lastNotifMs, if (en) "Not sent yet" else "Ei vielä lähetetty", en),
            if (lastNotifMs > 0L) lastNotifLabel else null
        )
        val (nextNotifValueTv, nextNotifSubTv) = addStatusRow(
            statusCard,
            if (en) "Next stamp notification scheduled" else "Seuraava leimausnotifikaatio lähetetään",
            when {
                !initialShiftReminders -> if (en) "Stamp reminders disabled" else "Leimausmuistutukset pois käytöstä"
                nextNotifMs > System.currentTimeMillis() -> formatTimestamp(nextNotifMs, "", en)
                else -> if (en) "No upcoming scheduled alarms" else "Ei tulevia ajoitettuja hälytyksiä"
            },
            if (initialShiftReminders && nextNotifMs > System.currentTimeMillis()) nextNotifLabel else null
        )

        val exactAlarmAllowed = canScheduleExactAlarmsCompat()
        val (exactAlarmValueTv, exactAlarmSubTv) = addStatusRow(
            statusCard,
            if (en) "Exact shift alarms" else "Tarkat vuorohälytykset",
            if (exactAlarmAllowed) {
                if (en) "Allowed – reminders trigger on the exact minute" else "Sallittu – muistutukset hälyttävät minuutilleen"
            } else {
                if (en) "Optional (restricted) – tap to allow" else "Valinnainen (rajoitettu) – napauta salliaksesi"
            },
            if (exactAlarmAllowed) {
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
                    if (en) "Tap to open alarm settings" else "Napauta avataksesi hälytysasetukset"
                } else null
            } else {
                if (en) "Ensures minute-accurate shift reminders" else "Varmistaa minuutintarkat vuoromuistutukset"
            }
        )
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            statusCard.getChildAt(statusCard.childCount - 1).setOnClickListener {
                openExactAlarmSettings()
            }
        }

        val powerManager = context.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        val ignoringBatteryOpt = powerManager.isIgnoringBatteryOptimizations(context.packageName)
        val (batteryOptValueTv, batteryOptSubTv) = addStatusRow(
            statusCard,
            if (en) "Battery optimization" else "Akun virransäästörajoitukset",
            if (ignoringBatteryOpt) {
                if (en) "Unrestricted (background sync active)" else "Ei rajoitettu (taustasynkronointi aktiivinen)"
            } else {
                if (en) "Optimized – tap to remove restriction" else "Optimoitu – napauta poistaaksesi rajoitus"
            },
            if (ignoringBatteryOpt) {
                if (en) "Tap to open battery settings" else "Napauta avataksesi virransäästöasetukset"
            } else {
                if (en) "Ensures background sync works in sleep mode" else "Varmistaa tausta-ajojen toiminnan lepotilassa"
            }
        )
        statusCard.getChildAt(statusCard.childCount - 1).setOnClickListener {
            openBatteryOptimizationSettings()
        }

        // === KORTTI 2: KIRJAUTUMINEN JA YHTEYS ===
        val authCard = createSectionCard(if (en) "Login and connection" else "Kirjautuminen ja yhteys")

        authCard.addView(createLabel(if (en) "Organization ID (e.g. demo)" else "Organisaatiotunnus (esim. demo)"))
        val editOrg = EditText(context).apply {
            hint = "demo"
            setText(prefs.getString("org_raw_input", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            isSingleLine = true
            styleEditText(this)
        }
        authCard.addView(editOrg)

        authCard.addView(createLabel(if (en) "Username" else "Käyttäjätunnus"))
        val editUser = EditText(context).apply {
            hint = if (en) "Username" else "Käyttäjätunnus"
            setText(SecureCredentialManager.getUsername(context) ?: "")
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            isSingleLine = true
            styleEditText(this)
        }
        authCard.addView(editUser)

        val existingPassword = SecureCredentialManager.getPassword(context) ?: ""
        val hasSavedPassword = existingPassword.isNotEmpty()

        authCard.addView(createLabel(if (en) "Password" else "Salasana"))
        val editPass = EditText(context).apply {
            hint = if (hasSavedPassword) {
                if (en) "•••••••• (saved – type new to change)" else "•••••••• (tallennettu – kirjoita uusi vaihtaaksesi)"
            } else {
                if (en) "Password" else "Salasana"
            }
            setText("")
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            transformationMethod = PasswordTransformationMethod.getInstance()
            isSingleLine = true
            styleEditText(this)
        }
        authCard.addView(editPass)

        val tvTestStatus = TextView(context).apply {
            text = ""
            textSize = 13f
            setPadding(0, dp(8), 0, dp(2))
        }

        val btnTestCredentials = Button(context).apply {
            text = if (en) "Test connection and credentials" else "Testaa yhteys ja tunnukset"
            styleButton(this, "#1E3A5F", "#0284C7", "#E0F2FE")
            setOnClickListener {
                val normalizedUrl = UrlNormalizer.normalizeOrgUrl(editOrg.text.toString())
                val user = editUser.text.toString().trim()
                val typedPass = editPass.text.toString()
                val pass = if (typedPass.isNotEmpty()) typedPass else existingPassword

                if (normalizedUrl.isEmpty()) {
                    tvTestStatus.setTextColor(Color.parseColor("#EF4444"))
                    tvTestStatus.text = if (en) "Error: Enter organization ID." else "Virhe: Syötä organisaatiotunnus."
                    return@setOnClickListener
                }
                if (user.isEmpty() || pass.isEmpty()) {
                    tvTestStatus.setTextColor(Color.parseColor("#EF4444"))
                    tvTestStatus.text = if (en) "Error: Enter username and password." else "Virhe: Syötä käyttäjätunnus ja salasana."
                    return@setOnClickListener
                }
                if (DemoModeHelper.isDemoCredentials(editOrg.text.toString(), user, pass)) {
                    tvTestStatus.setTextColor(Color.parseColor("#10B981"))
                    tvTestStatus.text = if (en) {
                        "Demo mode recognized! Save settings to enable demo mode."
                    } else {
                        "Demotila tunnistettu! Tallenna asetukset ottaaksesi demotilan käyttöön."
                    }
                    return@setOnClickListener
                }

                isEnabled = false
                tvTestStatus.setTextColor(Color.parseColor("#38BDF8"))
                tvTestStatus.text = if (en) "Testing address $normalizedUrl..." else "Testataan osoitetta $normalizedUrl..."

                testLoginWithHiddenWebView(context, normalizedUrl, user, pass) { success, message ->
                    isEnabled = true
                    tvTestStatus.setTextColor(
                        if (success) Color.parseColor("#10B981") else Color.parseColor("#EF4444")
                    )
                    tvTestStatus.text = message
                }
            }
        }
        authCard.addView(btnTestCredentials)
        authCard.addView(tvTestStatus)

        // === KORTTI 3: KALENTERISYNRONOINTI JA VÄRIKOODIT ===
        val calCard = createSectionCard(if (en) "Calendar sync and color codes" else "Kalenterisynkronointi ja värikoodit")

        val calDetailsContainer = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            visibility = if (initialSyncCalendar) View.VISIBLE else View.GONE
        }

        val switchSyncCalendar = createToggleRow(
            parent = calCard,
            title = if (en) "Sync shifts to Google Calendar" else "Synkronoi työvuorot Google-kalenteriin",
            subtitle = if (en) "Automatically export work shifts and leaves to the selected calendar" else "Vie työvuorot ja poissaolot valittuun kalenteriin automaattisesti",
            initialChecked = initialSyncCalendar
        ) { enabled ->
            calDetailsContainer.visibility = if (enabled) View.VISIBLE else View.GONE
        }

        calDetailsContainer.addView(createLabel(if (en) "Target calendar" else "Kohdekalenteri"))
        val calendars = getAvailableCalendars(context)
        val spinnerCalendar = Spinner(context).apply { styleSpinner(this) }
        if (calendars.isNotEmpty()) {
            spinnerCalendar.adapter = createDarkAdapter(calendars)
            val savedCalId = prefs.getLong("calendar_id", -1L)
            val idx = calendars.indexOfFirst { it.id == savedCalId }
            spinnerCalendar.setSelection(if (idx >= 0) idx else 0)
        }
        calDetailsContainer.addView(spinnerCalendar)

        calDetailsContainer.addView(createLabel(if (en) "Person tag for shared calendar (optional, e.g. Alex)" else "Henkilötunniste yhteiskalenteriin (valinnainen, esim. Jukka)"))
        val editUserTag = EditText(context).apply {
            hint = if (en) "Leave empty for personal calendar" else "Jätä tyhjäksi omassa kalenterissa"
            setText(prefs.getString("calendar_user_tag", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_WORDS
            isSingleLine = true
            styleEditText(this)
        }
        calDetailsContainer.addView(editUserTag)

        val localizedColors = SHIFT_COLOR_CHOICES.map { it.copy(isEnglish = en) }

        fun createColorSpinner(savedRgb: Int): Spinner {
            val spinner = Spinner(context).apply { styleSpinner(this) }
            spinner.adapter = createDarkAdapter(localizedColors)
            val idx = localizedColors.indexOfFirst { it.rgb == savedRgb }
            if (idx >= 0) spinner.setSelection(idx)
            return spinner
        }

        calDetailsContainer.addView(createLabel(if (en) "Morning shift color" else "Aamuvuoron väri"))
        val spinnerMorningColor = createColorSpinner(prefs.getInt("color_morning_rgb", DEFAULT_MORNING_RGB))
        calDetailsContainer.addView(spinnerMorningColor)

        calDetailsContainer.addView(createLabel(if (en) "Evening shift color" else "Iltavuoron väri"))
        val spinnerEveningColor = createColorSpinner(prefs.getInt("color_evening_rgb", DEFAULT_EVENING_RGB))
        calDetailsContainer.addView(spinnerEveningColor)

        calDetailsContainer.addView(createLabel(if (en) "Night shift color" else "Yövuoron väri"))
        val spinnerNightColor = createColorSpinner(prefs.getInt("color_night_rgb", DEFAULT_NIGHT_RGB))
        calDetailsContainer.addView(spinnerNightColor)

        calCard.addView(calDetailsContainer)

        // === KORTTI 4: MUISTUTUKSET JA ILMOITUKSET ===
        val actionCard = createSectionCard(if (en) "Reminders and notifications" else "Muistutukset ja ilmoitukset")

        val reminderDetailsContainer = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            visibility = if (initialShiftReminders) View.VISIBLE else View.GONE
        }

        val switchShiftReminders = createToggleRow(
            parent = actionCard,
            title = if (en) "Shift stamp reminders" else "Työvuorojen leimausmuistutukset",
            subtitle = if (en) "Notification before shift start and end with quick-stamp action (works without calendar sync)" else "Ilmoitus ennen vuoron alkua ja loppua pikaleimauspainikkeella (toimii myös ilman kalenterisynkronointia)",
            initialChecked = initialShiftReminders
        ) { enabled ->
            reminderDetailsContainer.visibility = if (enabled) View.VISIBLE else View.GONE
        }

        reminderDetailsContainer.addView(createLabel(if (en) "Reminder before shift (min)" else "Muistutus ennen vuoroa (min)"))
        val editReminder = EditText(context).apply {
            setText(prefs.getInt("reminder_minutes", 30).toString())
            inputType = InputType.TYPE_CLASS_NUMBER
            isSingleLine = true
            styleEditText(this)
        }
        reminderDetailsContainer.addView(editReminder)

        val exactAlarmNoticeBox = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            background = makeCardBg("#111923", "#2A394A", 8)
            setPadding(dp(12), dp(10), dp(12), dp(10))
            visibility = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S && !canScheduleExactAlarmsCompat()) {
                View.VISIBLE
            } else {
                View.GONE
            }
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                topMargin = dp(10)
            }
            setOnClickListener {
                openExactAlarmSettings()
            }
        }
        exactAlarmNoticeBox.addView(TextView(context).apply {
            text = if (en) "Exact shift alarms (optional)" else "Tarkat vuorohälytykset (valinnainen)"
            textSize = 13f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#F1F5F9"))
        })
        exactAlarmNoticeBox.addView(TextView(context).apply {
            text = if (en) {
                "Reminders work without it, but enabling exact alarms ensures minute-accurate delivery. Tap to open settings →"
            } else {
                "Muistutukset toimivat ilmankin, mutta sallimalla tarkat hälytykset ne tulevat minuutilleen. Napauta avataksesi asetukset →"
            }
            textSize = 12f
            setTextColor(Color.parseColor("#38BDF8"))
            setPadding(0, dp(3), 0, 0)
        })
        reminderDetailsContainer.addView(exactAlarmNoticeBox)

        actionCard.addView(reminderDetailsContainer)

        val switchTrackRequests = createToggleRow(
            parent = actionCard,
            title = if (en) "Notify about processed requests" else "Ilmoita käsitellyistä toiveista",
            subtitle = if (en) "Sends a notification when your shift or leave request is approved or rejected" else "Lähettää ilmoituksen, kun työvuoro- tai lomatoiveesi hyväksytään tai hylätään",
            initialChecked = initialTrackRequests
        )

        val btnSync = Button(context).apply {
            text = if (en) "Fetch and update shifts now" else "Hae ja päivitä työvuorot nyt"
            styleButton(this, "#1982C4", "#38BDF8", "#FFFFFF")
        }
        actionCard.addView(btnSync)

        val btnChanges = Button(context).apply {
            text = if (en) "Manage calendar changes" else "Hallitse kalenterimuutoksia"
            styleButton(this, "#233040", "#37475A", "#F1F5F9")
        }
        actionCard.addView(btnChanges)

        val btnTestNotif = Button(context).apply {
            text = if (en) "Send test notification" else "Lähetä testi-ilmoitus"
            styleButton(this, "#233040", "#37475A", "#F1F5F9")
        }
        actionCard.addView(btnTestNotif)

        // === KORTTI 5: VAPAAEHTOINEN TUKI (GOOGLE PLAY BILLING) ===
        val supportCard = createSectionCard(if (en) "Support app development" else "Tue sovelluksen kehitystä")

        supportCard.addView(TextView(context).apply {
            text = if (en) {
                "Vuorovahti is a free, independent hobby project. All features are always available to everyone. If you wish, you can support development with a voluntary one-time tip:"
            } else {
                "Vuorovahti on maksuton ja itsenäinen harrastusprojekti. Kaikki ominaisuudet ovat aina kaikkien käytössä. Halutessasi voit tukea kehitystä vapaaehtoisella kertamaksulla:"
            }
            textSize = 12.5f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, 0, 0, dp(8))
        })

        val tvSupportStatus = TextView(context).apply {
            text = if (en) "Fetching support options from Google Play..." else "Haetaan tukivaihtoehtoja Google Playsta..."
            textSize = 12f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, dp(2), 0, dp(4))
        }
        supportCard.addView(tvSupportStatus)

        val tipButtonsContainer = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
        }
        supportCard.addView(tipButtonsContainer)

        lateinit var billingHelper: SupportBillingHelper

        val btnFallbackSupport = Button(context).apply {
            text = if (en) "☕ Buy the developer a coffee" else "☕ Tarjoa kehittäjälle kahvit"
            styleButton(this, "#1E3A5F", "#0284C7", "#E0F2FE")
            setOnClickListener {
                tvSupportStatus.setTextColor(Color.parseColor("#38BDF8"))
                tvSupportStatus.text = if (en) "Connecting to Google Play..." else "Yhdistetään Google Playhin..."
                billingHelper.startConnection()
            }
        }
        tipButtonsContainer.addView(btnFallbackSupport)

        billingHelper = SupportBillingHelper(
            context = context,
            onProductsLoaded = { products ->
                tvSupportStatus.setTextColor(Color.parseColor("#94A3B8"))
                tvSupportStatus.text = if (en) "Choose a one-time tip (Google Play):" else "Valitse sopiva kertatuki (Google Play):"
                tipButtonsContainer.removeAllViews()

                val icons = listOf("☕", "🥐", "🍲")
                products.forEachIndexed { index, product ->
                    val price = product.oneTimePurchaseOfferDetails?.formattedPrice ?: ""
                    val title = product.name.ifBlank { if (en) "Support development" else "Tue kehitystä" }
                    val icon = icons.getOrElse(index) { "☕" }
                    val btnTier = Button(context).apply {
                        text = if (price.isNotEmpty()) "$icon $title — $price" else "$icon $title"
                        styleButton(this, "#1E3A5F", "#0284C7", "#E0F2FE")
                        setOnClickListener {
                            billingHelper.launchPurchase(product)
                        }
                    }
                    tipButtonsContainer.addView(btnTier)
                }
            },
            onStatusMessage = { msg, isSuccess ->
                tvSupportStatus.setTextColor(
                    Color.parseColor(if (isSuccess) "#10B981" else "#94A3B8")
                )
                tvSupportStatus.text = msg
            }
        )
        billingHelper.startConnection()

        // Alapalkki: Peruuta ja Tallenna
        val bottomDivider = View(context).apply {
            setBackgroundColor(Color.parseColor("#2A394A"))
        }
        rootContainer.addView(bottomDivider, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)))

        val footerBar = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(16), dp(12), dp(16), dp(12))
        }

        val btnCancel = Button(context).apply {
            text = if (en) "Cancel" else "Peruuta"
            background = makeCardBg("#233040", "#37475A", 8)
            setTextColor(Color.parseColor("#CBD5E1"))
            isAllCaps = false
            textSize = 14f
            setPadding(dp(18), dp(10), dp(18), dp(10))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                marginEnd = dp(10)
            }
        }

        val btnSave = Button(context).apply {
            text = if (en) "Save" else "Tallenna"
            background = makeCardBg("#1982C4", "#38BDF8", 8)
            setTextColor(Color.parseColor("#FFFFFF"))
            isAllCaps = false
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            setPadding(dp(22), dp(10), dp(22), dp(10))
        }

        footerBar.addView(btnCancel)
        footerBar.addView(btnSave)

        // Vastuuvapauslauseke (epävirallinen sovellus)
        val tvDisclaimer = TextView(context).apply {
            text = if (en) {
                "This is an independent, unofficial third-party client application. Numeron vuorovahti is not affiliated with Visma, Numeron, or any other entity."
            } else {
                "Tämä on itsenäinen, epävirallinen kolmannen osapuolen asiakassovellus. Numeron vuorovahti ei ole millään tavalla sidoksissa Vismaan, Numeroniin tai muihin mahdollisiin tahoihin."
            }
            textSize = 11f
            setTextColor(Color.parseColor("#64748B"))
            gravity = Gravity.CENTER
            setPadding(dp(16), dp(12), dp(16), dp(12))
        }
        rootContainer.addView(tvDisclaimer)

        rootContainer.addView(footerBar)

        val dialog = AlertDialog.Builder(context)
            .setView(rootContainer)
            .create()
        dialogRef = dialog

        dialog.window?.setBackgroundDrawable(makeCardBg("#0F1722", "#2A394A", 14))

        btnSync.setOnClickListener {
            dialog.dismiss()
            onManualSync()
        }

        btnChanges.setOnClickListener {
            dialog.dismiss()
            onManageChanges()
        }

        btnTestNotif.setOnClickListener {
            onTestNotification()
        }

        btnCancel.setOnClickListener {
            dialog.dismiss()
        }

        btnSave.setOnClickListener {
            val rawOrg = editOrg.text.toString().trim()
            val normalizedUrl = UrlNormalizer.normalizeOrgUrl(rawOrg)
            val selectedCal = spinnerCalendar.selectedItem as? CalendarOption
            val userTag = editUserTag.text.toString().trim()
            val reminderMins = editReminder.text.toString().toIntOrNull() ?: 30

            val morningRgb = (spinnerMorningColor.selectedItem as? ShiftColorChoice)?.rgb ?: DEFAULT_MORNING_RGB
            val eveningRgb = (spinnerEveningColor.selectedItem as? ShiftColorChoice)?.rgb ?: DEFAULT_EVENING_RGB
            val nightRgb = (spinnerNightColor.selectedItem as? ShiftColorChoice)?.rgb ?: DEFAULT_NIGHT_RGB

            val savedUser = editUser.text.toString().trim()
            val typedPass = editPass.text.toString()
            val savedPass = when {
                savedUser.isEmpty() -> ""
                typedPass.isNotEmpty() -> typedPass
                else -> existingPassword
            }
            val newSyncCalendar = switchSyncCalendar.isChecked
            val newShiftReminders = switchShiftReminders.isChecked
            val newTrackRequests = switchTrackRequests.isChecked

            val isDemo = savedUser.isEmpty() || savedPass.isEmpty() || rawOrg.isEmpty() ||
                DemoModeHelper.isDemoCredentials(rawOrg, savedUser, savedPass)

            SecureCredentialManager.saveCredentials(context, savedUser, savedPass)

            prefs.edit()
                .putString("org_raw_input", rawOrg)
                .putString("server_url", normalizedUrl)
                .putBoolean("demo_mode", isDemo)
                .putBoolean("sync_calendar_enabled", newSyncCalendar)
                .putBoolean("shift_reminders_enabled", newShiftReminders)
                .putBoolean("track_requests", newTrackRequests)
                .putString("calendar_user_tag", userTag)
                .putInt("reminder_minutes", reminderMins)
                .putInt("color_morning_rgb", morningRgb)
                .putInt("color_evening_rgb", eveningRgb)
                .putInt("color_night_rgb", nightRgb)
                .apply {
                    if (selectedCal != null) putLong("calendar_id", selectedCal.id)
                }
                .apply()

            val turnedOnSync = !initialSyncCalendar && newSyncCalendar
            val missingCacheForReminders = newShiftReminders && !CalendarSyncHelper.hasCachedShifts(context)
            val shouldTriggerSync = turnedOnSync || (!initialShiftReminders && missingCacheForReminders)

            fun finishSave(forceSync: Boolean = false) {
                dialog.dismiss()
                onSaved()
                if ((shouldTriggerSync || forceSync) && !isDemo && savedUser.isNotEmpty() && savedPass.isNotEmpty() && normalizedUrl.isNotEmpty()) {
                    ShiftReminderReceiver.triggerImmediateSync(context)
                }
            }

            if (initialSyncCalendar && !newSyncCalendar) {
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
            }
        }

        var lastKnownExactAlarmAllowed = canScheduleExactAlarmsCompat()

        fun refreshSystemPermissionStates() {
            val nowExactAllowed = canScheduleExactAlarmsCompat()
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
                if (nowExactAllowed) {
                    exactAlarmValueTv.text = if (en) "Allowed – reminders trigger on the exact minute" else "Sallittu – muistutukset hälyttävät minuutilleen"
                    exactAlarmValueTv.setTextColor(Color.parseColor("#34D399"))
                    exactAlarmSubTv.text = if (en) "Tap to open alarm settings" else "Napauta avataksesi hälytysasetukset"
                    exactAlarmSubTv.visibility = View.VISIBLE
                    exactAlarmNoticeBox.visibility = View.GONE
                } else {
                    exactAlarmValueTv.text = if (en) "Optional (restricted) – tap to allow" else "Valinnainen (rajoitettu) – napauta salliaksesi"
                    exactAlarmValueTv.setTextColor(Color.parseColor("#F1F5F9"))
                    exactAlarmSubTv.text = if (en) "Ensures minute-accurate shift reminders" else "Varmistaa minuutintarkat vuoromuistutukset"
                    exactAlarmSubTv.visibility = View.VISIBLE
                    exactAlarmNoticeBox.visibility = View.VISIBLE
                }
            } else {
                exactAlarmValueTv.text = if (en) "Allowed" else "Sallittu"
                exactAlarmValueTv.setTextColor(Color.parseColor("#34D399"))
                exactAlarmSubTv.visibility = View.GONE
                exactAlarmNoticeBox.visibility = View.GONE
            }

            val nowIgnoringBattery = powerManager.isIgnoringBatteryOptimizations(context.packageName)
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

            if (!lastKnownExactAlarmAllowed && nowExactAllowed) {
                CalendarSyncHelper.scheduleShiftReminders(context)
                val updatedNextMs = prefs.getLong("next_reminder_ms", 0L)
                val updatedNextLabel = prefs.getString("next_reminder_label", "") ?: ""
                val remindersOn = switchShiftReminders.isChecked
                nextNotifValueTv.text = when {
                    !remindersOn -> if (en) "Stamp reminders disabled" else "Leimausmuistutukset pois käytöstä"
                    updatedNextMs > System.currentTimeMillis() -> formatTimestamp(updatedNextMs, "", en)
                    else -> if (en) "No upcoming scheduled alarms" else "Ei tulevia ajoitettuja hälytyksiä"
                }
                if (remindersOn && updatedNextMs > System.currentTimeMillis() && updatedNextLabel.isNotEmpty()) {
                    nextNotifSubTv.text = updatedNextLabel
                    nextNotifSubTv.visibility = View.VISIBLE
                } else {
                    nextNotifSubTv.visibility = View.GONE
                }
            }
            lastKnownExactAlarmAllowed = nowExactAllowed
        }

        refreshSystemPermissionStates()

        rootContainer.viewTreeObserver.addOnWindowFocusChangeListener { hasFocus ->
            if (hasFocus) {
                refreshSystemPermissionStates()
            }
        }

        dialog.setOnDismissListener { billingHelper.destroy() }
        dialog.show()
    }

    private fun testLoginWithHiddenWebView(
        @Suppress("UNUSED_PARAMETER") context: Context,
        baseUrl: String,
        username: String,
        password: String,
        callback: (Boolean, String) -> Unit
    ) {
        CoroutineScope(Dispatchers.IO).launch {
            val (success, msg) = BackgroundAuthHelper.testCredentials(baseUrl, username, password)
            withContext(Dispatchers.Main) {
                callback(success, msg)
            }
        }
    }
}
'''


def patch_main_activity() -> None:
    path = find_file("MainActivity.kt")
    src = path.read_text(encoding="utf-8")

    old_banner = r"""    private fun updateDemoBanner() {
        bannerDemoMode.visibility = if (DemoModeHelper.isDemoEnabled(this)) View.VISIBLE else View.GONE
    }"""

    new_banner = r"""    private fun updateDemoBanner() {
        val isDemo = DemoModeHelper.isDemoEnabled(this)
        val en = DemoModeHelper.isEnglish(this)
        bannerDemoMode.visibility = if (isDemo) View.VISIBLE else View.GONE
        bannerDemoMode.text = if (en) {
            "DEMO MODE ACTIVE – Try stamping, shifts & notifications"
        } else {
            "DEMOTILA AKTIIVINEN – Kokeile leimausta, vuoroja ja ilmoituksia"
        }
        btnNavStamp.text = if (en) "Stamp" else "Leimaus"
        btnNavRequests.text = if (en) "Requests" else "Toiveet"
        btnNavShifts.text = if (en) "Shifts" else "Vuorot"
    }"""

    old_test_notif = r"""    private fun triggerTestReminderNotification() {
        val timeStr = LocalTime.now().plusMinutes(30).format(DateTimeFormatter.ofPattern("HH:mm"))
        ShiftReminderReceiver().showReminderNotification(
            context = this,
            shiftTitle = "Aamuvuoro (Testi-ilmoitus)",
            timeStr = timeStr,
            isEnding = false,
            isTest = true
        )
    }"""

    new_test_notif = r"""    private fun triggerTestReminderNotification() {
        val en = DemoModeHelper.isEnglish(this)
        val timeStr = LocalTime.now().plusMinutes(30).format(DateTimeFormatter.ofPattern("HH:mm"))
        ShiftReminderReceiver().showReminderNotification(
            context = this,
            shiftTitle = if (en) "Morning Shift (Test notification)" else "Aamuvuoro (Testi-ilmoitus)",
            timeStr = timeStr,
            isEnding = false,
            isTest = true
        )
    }"""

    old_demo_sync_toasts = r"""                withContext(Dispatchers.Main) {
                    if (syncCalendar && calId == null) {
                        Toast.makeText(this@MainActivity, "Kalenterioikeus tai kalenteri puuttuu", Toast.LENGTH_LONG).show()
                    } else if (changes.isNotEmpty()) {
                        Toast.makeText(
                            this@MainActivity,
                            "Kalenterimuutokset: ${CalendarChangeTracker.formatSummary(changes)}",
                            Toast.LENGTH_LONG
                        ).show()
                        CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                    } else {
                        val msg = if (syncCalendar) {
                            "Demovuorot ovat jo ajan tasalla kalenterissa"
                        } else {
                            "Demovuorot ja muistutukset päivitetty (${demoShifts.size} vuoroa)"
                        }
                        Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                    }
                }"""

    new_demo_sync_toasts = r"""                withContext(Dispatchers.Main) {
                    val en = DemoModeHelper.isEnglish(this@MainActivity)
                    if (syncCalendar && calId == null) {
                        Toast.makeText(
                            this@MainActivity,
                            if (en) "Calendar permission or calendar missing" else "Kalenterioikeus tai kalenteri puuttuu",
                            Toast.LENGTH_LONG
                        ).show()
                    } else if (changes.isNotEmpty()) {
                        Toast.makeText(
                            this@MainActivity,
                            if (en) "Calendar changes: ${CalendarChangeTracker.formatSummary(changes)}" else "Kalenterimuutokset: ${CalendarChangeTracker.formatSummary(changes)}",
                            Toast.LENGTH_LONG
                        ).show()
                        CalendarChangeTracker.showManageChangesDialog(this@MainActivity)
                    } else {
                        val msg = if (syncCalendar) {
                            if (en) "Demo shifts are already up to date in calendar" else "Demovuorot ovat jo ajan tasalla kalenterissa"
                        } else {
                            if (en) "Demo shifts and reminders updated (${demoShifts.size} shifts)" else "Demovuorot ja muistutukset päivitetty (${demoShifts.size} vuoroa)"
                        }
                        Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                    }
                }"""

    old_demo_autostamp = r"""            } else {
                val stateStr = if (wantIn) "Sisään" else "Ulos"
                Toast.makeText(this, "Demotila: Olet jo leimannut tilaan $stateStr", Toast.LENGTH_SHORT).show()
                webView.postDelayed({ finishAndRemoveTask() }, 1200L)
            }"""

    new_demo_autostamp = r"""            } else {
                val en = DemoModeHelper.isEnglish(this)
                val stateStr = if (en) (if (wantIn) "In" else "Out") else (if (wantIn) "Sisään" else "Ulos")
                val msg = if (en) "Demo mode: Already clocked $stateStr" else "Demotila: Olet jo leimannut tilaan $stateStr"
                Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
                webView.postDelayed({ finishAndRemoveTask() }, 1200L)
            }"""

    src = replace_exact(path, src, old_banner, new_banner)
    src = replace_exact(path, src, old_test_notif, new_test_notif)
    src = replace_exact(path, src, old_demo_sync_toasts, new_demo_sync_toasts)
    src = replace_exact(path, src, old_demo_autostamp, new_demo_autostamp)
    verify_kotlin_delimiters(path, src)
    path.write_text(src, encoding="utf-8")
    print(f"Päivitetty: {path}")


def patch_shift_reminder_receiver() -> None:
    path = find_file("ShiftReminderReceiver.kt")
    src = path.read_text(encoding="utf-8")

    old_revert_block = r"""                        val count = CalendarChangeTracker.revertAllChanges(appCtx)
                        withContext(Dispatchers.Main) {
                            Toast.makeText(appCtx, "Peruttu $count kalenterimuutosta", Toast.LENGTH_LONG).show()
                        }"""

    new_revert_block = r"""                        val count = CalendarChangeTracker.revertAllChanges(appCtx)
                        val en = DemoModeHelper.isEnglish(appCtx)
                        withContext(Dispatchers.Main) {
                            val msg = if (en) "Reverted $count calendar changes" else "Peruttu $count kalenterimuutosta"
                            Toast.makeText(appCtx, msg, Toast.LENGTH_LONG).show()
                        }"""

    old_notif_labels = r"""        val notifId = if (isEnding) 2002 else 1001
        val fullButtonLabel = if (isEnding) "LEIMAA ULOS" else "LEIMAA SISÄÄN"
        val shortButtonLabel = if (isEnding) "ULOS" else "SISÄÄN"
        val contentTitle = if (isEnding) "Vuoro päättyy klo $timeStr" else "Vuoro alkaa klo $timeStr"
        val btnBgRes = if (isEnding) R.drawable.bg_notif_btn_out else R.drawable.bg_notif_btn_in

        val dirTag = if (isEnding) "Ulos" else "Sisään"
        val testSuffix = if (isTest) " [Testi]" else "" """.rstrip()

    new_notif_labels = r"""        val en = DemoModeHelper.isEnglish(context)
        val notifId = if (isEnding) 2002 else 1001
        val fullButtonLabel = if (en) {
            if (isEnding) "CLOCK OUT" else "CLOCK IN"
        } else {
            if (isEnding) "LEIMAA ULOS" else "LEIMAA SISÄÄN"
        }
        val shortButtonLabel = if (en) {
            if (isEnding) "OUT" else "IN"
        } else {
            if (isEnding) "ULOS" else "SISÄÄN"
        }
        val contentTitle = if (en) {
            if (isEnding) "Shift ends at $timeStr" else "Shift starts at $timeStr"
        } else {
            if (isEnding) "Vuoro päättyy klo $timeStr" else "Vuoro alkaa klo $timeStr"
        }
        val btnBgRes = if (isEnding) R.drawable.bg_notif_btn_out else R.drawable.bg_notif_btn_in

        val dirTag = if (en) {
            if (isEnding) "Out" else "In"
        } else {
            if (isEnding) "Ulos" else "Sisään"
        }
        val testSuffix = if (isTest) (if (en) " [Test]" else " [Testi]") else "" """.rstrip()

    old_cal_changes_notif = r"""            val summary = CalendarChangeTracker.formatSummary(changes)
            val shownItems = changes.take(6).map { CalendarChangeTracker.formatNotificationLine(it) }.toMutableList()
            if (changes.size > 6) {
                shownItems.add("...ja ${changes.size - 6} muuta muutosta")
            }
            val detailsLines = shownItems.joinToString("\n")
            val collapsedText = shownItems.firstOrNull()
                ?: "Napauta muokataksesi tai peruaksesi yksittäisiä muutoksia" """.rstrip()

    new_cal_changes_notif = r"""            val en = DemoModeHelper.isEnglish(context)
            val summary = CalendarChangeTracker.formatSummary(changes)
            val shownItems = changes.take(6).map { CalendarChangeTracker.formatNotificationLine(it) }.toMutableList()
            if (changes.size > 6) {
                shownItems.add(
                    if (en) "...and ${changes.size - 6} more changes" else "...ja ${changes.size - 6} muuta muutosta"
                )
            }
            val detailsLines = shownItems.joinToString("\n")
            val collapsedText = shownItems.firstOrNull()
                ?: if (en) "Tap to edit or undo individual changes" else "Napauta muokataksesi tai peruaksesi yksittäisiä muutoksia" """.rstrip()

    old_cal_notif_builder = r"""            val notification = NotificationCompat.Builder(context, channelId)
                .setSmallIcon(android.R.drawable.ic_menu_my_calendar)
                .setContentTitle("Google-kalenteria päivitetty ($summary)")
                .setContentText(collapsedText)
                .setStyle(NotificationCompat.BigTextStyle().bigText(detailsLines))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .setContentIntent(managePi)
                .addAction(android.R.drawable.ic_menu_edit, "Muokkaa / Peru", managePi)
                .addAction(android.R.drawable.ic_menu_revert, "Peru kaikki", revertAllPi)
                .build()"""

    new_cal_notif_builder = r"""            val notification = NotificationCompat.Builder(context, channelId)
                .setSmallIcon(android.R.drawable.ic_menu_my_calendar)
                .setContentTitle(
                    if (en) "Google Calendar updated ($summary)" else "Google-kalenteria päivitetty ($summary)"
                )
                .setContentText(collapsedText)
                .setStyle(NotificationCompat.BigTextStyle().bigText(detailsLines))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .setContentIntent(managePi)
                .addAction(android.R.drawable.ic_menu_edit, if (en) "Edit / Undo" else "Muokkaa / Peru", managePi)
                .addAction(android.R.drawable.ic_menu_revert, if (en) "Undo all" else "Peru kaikki", revertAllPi)
                .build()"""

    src = replace_exact(path, src, old_revert_block, new_revert_block)
    src = replace_exact(path, src, old_notif_labels, new_notif_labels)
    src = replace_exact(path, src, old_cal_changes_notif, new_cal_changes_notif)
    src = replace_exact(path, src, old_cal_notif_builder, new_cal_notif_builder)
    verify_kotlin_delimiters(path, src)
    path.write_text(src, encoding="utf-8")
    print(f"Päivitetty: {path}")


def patch_quick_stamp_activity() -> None:
    path = find_file("QuickStampActivity.kt")
    src = path.read_text(encoding="utf-8")

    old_greeting_fn = r"""    private fun buildGreeting(isEnding: Boolean): String {
        val hour = LocalTime.now().hour
        val options = if (isEnding) {"""

    new_greeting_fn = r"""    private fun buildGreeting(isEnding: Boolean): String {
        val en = DemoModeHelper.isEnglish(this)
        val hour = LocalTime.now().hour
        if (en) {
            val enOptions = if (isEnding) {
                when (hour) {
                    in 5..10 -> listOf(
                        "Good morning, thank you for the night shift!",
                        "Morning has arrived – get some well-earned rest!",
                        "Night shift complete, have a restful day!"
                    )
                    in 11..16 -> listOf(
                        "Thanks for your shift, enjoy the rest of your day!",
                        "Shift wrapped up – have a great afternoon!",
                        "Work done for now, enjoy your time off!"
                    )
                    in 17..21 -> listOf(
                        "Good evening, thank you for your shift!",
                        "Evening shift done – have a relaxing evening!",
                        "Thanks for today's shift, enjoy your evening!"
                    )
                    else -> listOf(
                        "Good night, thank you for your shift!",
                        "Thanks for the late shift, sleep well!",
                        "Shift complete – have a peaceful night!"
                    )
                }
            } else {
                when (hour) {
                    in 4..9 -> listOf(
                        "Good morning and have a great shift!",
                        "Morning! Wishing you a smooth and steady shift!",
                        "Have a pleasant morning shift!"
                    )
                    in 10..13 -> listOf(
                        "Good day and have a smooth shift!",
                        "Wishing you a productive day shift!",
                        "Have a great shift today!"
                    )
                    in 14..17 -> listOf(
                        "Good afternoon and have a great evening shift!",
                        "Wishing you a smooth evening shift!",
                        "Have a pleasant afternoon and evening shift!"
                    )
                    in 18..21 -> listOf(
                        "Good evening and have a smooth shift!",
                        "Wishing you a calm and steady evening!",
                        "Have a great shift tonight!"
                    )
                    else -> listOf(
                        "Good night and have a smooth night shift!",
                        "Wishing you a calm and steady night shift!",
                        "Have a great night shift!"
                    )
                }
            }
            return enOptions.random()
        }
        val options = if (isEnding) {"""

    old_process_intent = r"""        val isEnding = incoming?.getBooleanExtra("IS_ENDING", false) ?: false
        val isTest = incoming?.getBooleanExtra("IS_TEST", false) ?: false
        val targetText = if (isEnding) "Ulos" else "Sisään"
        val actionTitle = if (isEnding) "Leimataan ulos" else "Leimataan sisään"

        greetingText.text = buildGreeting(isEnding)
        greetingText.visibility = View.VISIBLE

        titleText.text = actionTitle
        progressBar.indeterminateTintList = ColorStateList.valueOf(
            Color.parseColor(if (isEnding) "#F97316" else "#38BDF8")
        )

        if (isTest) {
            statusText.text = "Testi-ilmoitus ($targetText)…"
            activeJob = scope.launch {
                delay(650L)
                showFinalState(
                    title = "Testi-ilmoitus ($targetText)",
                    subtitle = "Oikeaa leimausta ei suoritettu",
                    badgeText = "✓",
                    badgeFillHex = "#0F2E26",
                    badgeStrokeHex = "#10B981",
                    badgeTextHex = "#34D399",
                    closeDelayMs = 1400L
                )
            }
            return
        }"""

    new_process_intent = r"""        val en = DemoModeHelper.isEnglish(this)
        val isEnding = incoming?.getBooleanExtra("IS_ENDING", false) ?: false
        val isTest = incoming?.getBooleanExtra("IS_TEST", false) ?: false
        val targetText = if (en) {
            if (isEnding) "Out" else "In"
        } else {
            if (isEnding) "Ulos" else "Sisään"
        }
        val actionTitle = if (en) {
            if (isEnding) "Clocking out" else "Clocking in"
        } else {
            if (isEnding) "Leimataan ulos" else "Leimataan sisään"
        }

        greetingText.text = buildGreeting(isEnding)
        greetingText.visibility = View.VISIBLE

        titleText.text = actionTitle
        progressBar.indeterminateTintList = ColorStateList.valueOf(
            Color.parseColor(if (isEnding) "#F97316" else "#38BDF8")
        )

        if (isTest) {
            statusText.text = if (en) "Test notification ($targetText)…" else "Testi-ilmoitus ($targetText)…"
            activeJob = scope.launch {
                delay(650L)
                showFinalState(
                    title = if (en) "Test notification ($targetText)" else "Testi-ilmoitus ($targetText)",
                    subtitle = if (en) "No actual stamp was recorded" else "Oikeaa leimausta ei suoritettu",
                    badgeText = "✓",
                    badgeFillHex = "#0F2E26",
                    badgeStrokeHex = "#10B981",
                    badgeTextHex = "#34D399",
                    closeDelayMs = 1400L
                )
            }
            return
        }"""

    old_demo_quick_stamp = r"""    private fun handleDemoQuickStamp(wantIn: Boolean, targetText: String) {
        statusText.text = "Suoritetaan demoleimaus…"
        activeJob = scope.launch {
            delay(550L)
            val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val currentlyIn = prefs.getBoolean("demo_stamped_in", false)
            if (wantIn != currentlyIn) {
                val nowDate = LocalDate.now().format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
                val nowTime = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
                val oldHistory = prefs.getString("demo_stamp_history", "") ?: ""
                val newHistory = "$nowDate | $nowTime | $targetText\n$oldHistory"
                prefs.edit()
                    .putBoolean("demo_stamped_in", wantIn)
                    .putString("demo_stamp_history", newHistory)
                    .apply()

                showFinalState(
                    title = "Demoleimaus vahvistettu",
                    subtitle = "$targetText • klo $nowTime",
                    badgeText = "✓",
                    badgeFillHex = "#0F2E26",
                    badgeStrokeHex = "#10B981",
                    badgeTextHex = "#34D399",
                    closeDelayMs = 1200L
                )
            } else {
                showFinalState(
                    title = "Ei leimattu",
                    subtitle = "Demotila: Olet jo tilassa $targetText",
                    badgeText = "!",
                    badgeFillHex = "#1E3A5F",
                    badgeStrokeHex = "#38BDF8",
                    badgeTextHex = "#7DD3FC",
                    closeDelayMs = 1400L
                )
            }
        }
    }"""

    new_demo_quick_stamp = r"""    private fun handleDemoQuickStamp(wantIn: Boolean, targetText: String) {
        val en = DemoModeHelper.isEnglish(this)
        statusText.text = if (en) "Recording demo stamp…" else "Suoritetaan demoleimaus…"
        activeJob = scope.launch {
            delay(550L)
            val prefs = getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            val currentlyIn = prefs.getBoolean("demo_stamped_in", false)
            if (wantIn != currentlyIn) {
                val nowDate = LocalDate.now().format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
                val nowTime = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
                val oldHistory = prefs.getString("demo_stamp_history", "") ?: ""
                val newHistory = "$nowDate | $nowTime | $targetText\n$oldHistory"
                prefs.edit()
                    .putBoolean("demo_stamped_in", wantIn)
                    .putString("demo_stamp_history", newHistory)
                    .apply()

                showFinalState(
                    title = if (en) "Demo stamp confirmed" else "Demoleimaus vahvistettu",
                    subtitle = if (en) "$targetText • at $nowTime" else "$targetText • klo $nowTime",
                    badgeText = "✓",
                    badgeFillHex = "#0F2E26",
                    badgeStrokeHex = "#10B981",
                    badgeTextHex = "#34D399",
                    closeDelayMs = 1200L
                )
            } else {
                showFinalState(
                    title = if (en) "Not stamped" else "Ei leimattu",
                    subtitle = if (en) "Demo mode: Already clocked $targetText" else "Demotila: Olet jo tilassa $targetText",
                    badgeText = "!",
                    badgeFillHex = "#1E3A5F",
                    badgeStrokeHex = "#38BDF8",
                    badgeTextHex = "#7DD3FC",
                    closeDelayMs = 1400L
                )
            }
        }
    }"""

    src = replace_exact(path, src, old_greeting_fn, new_greeting_fn)
    src = replace_exact(path, src, old_process_intent, new_process_intent)
    src = replace_exact(path, src, old_demo_quick_stamp, new_demo_quick_stamp)
    verify_kotlin_delimiters(path, src)
    path.write_text(src, encoding="utf-8")
    print(f"Päivitetty: {path}")


def main() -> None:
    demo_path = find_file("DemoModeHelper.kt")
    verify_kotlin_delimiters(demo_path, DEMO_MODE_HELPER_KT)
    demo_path.write_text(DEMO_MODE_HELPER_KT.lstrip("\n"), encoding="utf-8")
    print(f"Päivitetty: {demo_path}")

    settings_path = find_file("SettingsDialogHelper.kt")
    verify_kotlin_delimiters(settings_path, SETTINGS_DIALOG_HELPER_KT)
    settings_path.write_text(SETTINGS_DIALOG_HELPER_KT.lstrip("\n"), encoding="utf-8")
    print(f"Päivitetty: {settings_path}")

    patch_main_activity()
    patch_shift_reminder_receiver()
    patch_quick_stamp_activity()
    increment_version()


if __name__ == "__main__":
    main()
