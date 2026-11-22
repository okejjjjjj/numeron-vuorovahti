package fi.numeron.vuorovahti

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
        val user = (SecureCredentialManager.getUsername(context) ?: "").trim()
        val pass = SecureCredentialManager.getPassword(context) ?: ""

        if (user.isEmpty() || pass.isEmpty() || (org.isEmpty() && serverUrl.isEmpty())) {
            return true
        }
        if (UrlNormalizer.isDemoInput(org) || UrlNormalizer.isDemoInput(serverUrl)) {
            return true
        }
        return isDemoCredentials(org.ifEmpty { serverUrl }, user, pass)
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
                val safeDate = android.text.TextUtils.htmlEncode(p[0])
                val safeType = android.text.TextUtils.htmlEncode(p[1])
                val safeStatus = android.text.TextUtils.htmlEncode(p[2])
                """<tr>
                    <td>$safeDate</td>
                    <td><strong>$safeType</strong></td>
                    <td><span class="$badgeClass">$safeStatus</span></td>
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
                            <span class="itemName">${item.label}</span>
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
            val yest = LocalDate.now().minusDays(1).format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
            val defaultHistory = "$yest | 14:30 | Ulos\n$yest | 07:00 | Sisään"
            val oldHistory = prefs.getString("demo_stamp_history", defaultHistory) ?: defaultHistory
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
            val today = LocalDate.now()
            val fmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")
            val defaultRequests = if (en) {
                "${today.plusDays(5).format(fmt)} | Annual leave | Approved\n${today.plusDays(12).format(fmt)} | Day off | Pending approval"
            } else {
                "${today.plusDays(5).format(fmt)} | Vuosiloma | Hyväksytty\n${today.plusDays(12).format(fmt)} | Vapaapäivä | Odottaa käsittelyä"
            }
            val oldList = prefs.getString("demo_requests", defaultRequests) ?: defaultRequests
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
