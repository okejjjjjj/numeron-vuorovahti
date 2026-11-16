#!/usr/bin/env python3
import os
import re

BASE_DIR = os.path.join("app", "src", "main", "java", "fi", "numeron", "vuorovahti")
TRACKER_PATH = os.path.join(BASE_DIR, "CalendarChangeTracker.kt")

with open(TRACKER_PATH, "r", encoding="utf-8") as f:
    content = f.read()

print("=== Nykyisen CalendarChangeTracker.kt:n alku ===")
for i, line in enumerate(content.splitlines()[:115], start=1):
    print(f"{i}: {line}")

for fname in ["CalendarSyncHelper.kt", "MainActivity.kt", "ShiftReminderReceiver.kt"]:
    fpath = os.path.join(BASE_DIR, fname)
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            src = f.read()
        refs = [line.strip() for line in src.splitlines() if "CalendarChangeTracker" in line or "CalendarChangeItem" in line]
        if refs:
            print(f"=== Viittaukset tiedostossa {fname} ===")
            for r in refs:
                print("  ", r)

m_key = re.search(r'private\s+const\s+val\s+KEY_CHANGES\s*=\s*"[^"]+"\s*\n', content)
if not m_key:
    raise RuntimeError("KEY_CHANGES-vakiota ei löytynyt tiedostosta CalendarChangeTracker.kt")

prefix = content[:m_key.end()]

m_prefs = re.search(r'private\s+const\s+val\s+(?!KEY_CHANGES)(\w+)\s*=\s*"[^"]+"', prefix)
prefs_const = m_prefs.group(1) if m_prefs else '"NumeronPrefs"'

m_dc = re.search(r'data\s+class\s+CalendarChangeItem\s*\((.*?)\)', prefix, flags=re.DOTALL)
if not m_dc:
    raise RuntimeError("data class CalendarChangeItem -määrittelyä ei löytynyt")

raw_params = m_dc.group(1)
fields = []
for part in raw_params.split(","):
    line = part.strip()
    if not line or line.startswith("//"):
        continue
    m_p = re.search(r'(?:val|var)\s+(\w+)\s*:\s*([^=]+?)(?:\s*=\s*(.+))?$', line)
    if m_p:
        fname = m_p.group(1).strip()
        ftype = m_p.group(2).strip()
        fdef = m_p.group(3).strip() if m_p.group(3) else None
        fields.append((fname, ftype, fdef))

print("=== Parsitut CalendarChangeItem-kentät ===")
for f_info in fields:
    print("  ", f_info)

field_map = {f[0]: (f[1], f[2]) for f in fields}
field_names = set(field_map.keys())

save_lines = []
for fname, ftype, _ in fields:
    base_type = ftype.rstrip("?")
    is_null = ftype.endswith("?")
    if base_type == "ChangeType":
        save_lines.append(f'            obj.put("{fname}", item.{fname}.name)')
    elif base_type == "String":
        val_expr = f'item.{fname} ?: ""' if is_null else f'item.{fname}'
        save_lines.append(f'            obj.put("{fname}", {val_expr})')
    elif base_type == "Long":
        val_expr = f'item.{fname} ?: 0L' if is_null else f'item.{fname}'
        save_lines.append(f'            obj.put("{fname}", {val_expr})')
    elif base_type == "Int":
        val_expr = f'item.{fname} ?: 0' if is_null else f'item.{fname}'
        save_lines.append(f'            obj.put("{fname}", {val_expr})')
    elif base_type == "Boolean":
        val_expr = f'item.{fname} ?: false' if is_null else f'item.{fname}'
        save_lines.append(f'            obj.put("{fname}", {val_expr})')

load_args = []
for fname, ftype, _ in fields:
    base_type = ftype.rstrip("?")
    is_null = ftype.endswith("?")
    if base_type == "ChangeType":
        load_args.append(f'                        {fname} = ChangeType.valueOf(obj.optString("{fname}", "ADDED"))')
    elif base_type == "String":
        if is_null:
            load_args.append(f'                        {fname} = obj.optString("{fname}", "").ifEmpty {{ null }}')
        else:
            load_args.append(f'                        {fname} = obj.optString("{fname}", "")')
    elif base_type == "Long":
        load_args.append(f'                        {fname} = obj.optLong("{fname}", 0L)')
    elif base_type == "Int":
        load_args.append(f'                        {fname} = obj.optInt("{fname}", 0)')
    elif base_type == "Boolean":
        load_args.append(f'                        {fname} = obj.optBoolean("{fname}", false)')

def read_long(name):
    ftype, _ = field_map[name]
    return f"item.{name} ?: 0L" if ftype.endswith("?") else f"item.{name}"

def read_int(name):
    ftype, _ = field_map[name]
    return f"item.{name} ?: 0" if ftype.endswith("?") else f"item.{name}"

def read_bool(name):
    ftype, _ = field_map[name]
    return f"item.{name} ?: item.isAllDay" if ftype.endswith("?") else f"item.{name}"

event_id_field = "eventId" if "eventId" in field_names else ("id" if "id" in field_names else None)
cal_id_field = "calendarId" if "calendarId" in field_names else None
desc_field = "description" if "description" in field_names else None
color_field = "eventColor" if "eventColor" in field_names else ("color" if "color" in field_names else None)
has_old_fields = all(k in field_names for k in ["oldTitle", "oldStartMs", "oldEndMs"])

if event_id_field:
    eid_expr = read_long(event_id_field)
    delete_by_id_code = f"""
                    val eid = {eid_expr}
                    if (eid > 0L) {{
                        val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, eid)
                        if (resolver.delete(uri, null, null) > 0) {{
                            removedFromCal = true
                        }}
                    }}"""
    update_by_id_code = f"""
            val eid = {eid_expr}
            if (eid > 0L) {{
                val uri = ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, eid)
                if (resolver.update(uri, values, null, null) > 0) {{
                    updatedInCal = true
                }}
            }}"""
else:
    delete_by_id_code = ""
    update_by_id_code = ""

if has_old_fields:
    old_start_expr = read_long("oldStartMs")
    old_end_expr = read_long("oldEndMs")
    old_all_day_expr = read_bool("oldIsAllDay") if "oldIsAllDay" in field_names else "item.isAllDay"
    revert_modified_code = f"""
                    val prevTitle = item.oldTitle
                    val prevStart = {old_start_expr}
                    val prevEnd = {old_end_expr}
                    val prevAllDay = {old_all_day_expr}
                    if (!prevTitle.isNullOrEmpty() && prevStart > 0L && prevEnd > 0L) {{
                        val values = ContentValues().apply {{
                            put(CalendarContract.Events.TITLE, prevTitle)
                            put(CalendarContract.Events.DTSTART, prevStart)
                            put(CalendarContract.Events.DTEND, prevEnd)
                            put(CalendarContract.Events.ALL_DAY, if (prevAllDay) 1 else 0)
                            put(
                                CalendarContract.Events.EVENT_TIMEZONE,
                                if (prevAllDay) "UTC" else ZoneId.systemDefault().id
                            )
                        }}
                        var restored = false{update_by_id_code.replace("updatedInCal", "restored")}
                        if (!restored) {{
                            val sel = "${{CalendarContract.Events.TITLE}} = ? AND ${{CalendarContract.Events.DTSTART}} = ?"
                            val args = arrayOf(item.title, item.startMs.toString())
                            resolver.update(CalendarContract.Events.CONTENT_URI, values, sel, args)
                        }}
                    }}"""
else:
    revert_modified_code = """
                    // Ei tallennettuja vanhoja kenttiä muokkauksen palautukseen"""

if cal_id_field:
    cid_expr = read_long(cal_id_field)
    cal_id_block = f"val savedCalId = {cid_expr}\n                    val targetCalId = if (savedCalId > 0L) savedCalId else (CalendarSyncHelper.getTargetCalendarId(context) ?: -1L)"
else:
    cal_id_block = "val targetCalId = CalendarSyncHelper.getTargetCalendarId(context) ?: -1L"

extra_insert_lines = []
if desc_field:
    extra_insert_lines.append(f'                            if (!item.{desc_field}.isNullOrEmpty()) put(CalendarContract.Events.DESCRIPTION, item.{desc_field})')
if color_field:
    c_expr = read_int(color_field)
    extra_insert_lines.append(f'                            val evCol = {c_expr}\n                            if (evCol != 0) put(CalendarContract.Events.EVENT_COLOR, evCol)')
extra_insert_block = "\n".join(extra_insert_lines)

required_imports = [
    "import android.app.AlertDialog",
    "import android.app.DatePickerDialog",
    "import android.app.TimePickerDialog",
    "import android.content.ContentUris",
    "import android.content.ContentValues",
    "import android.content.Context",
    "import android.graphics.Color",
    "import android.graphics.Typeface",
    "import android.graphics.drawable.GradientDrawable",
    "import android.provider.CalendarContract",
    "import android.text.InputType",
    "import android.view.Gravity",
    "import android.view.View",
    "import android.view.ViewGroup",
    "import android.widget.Button",
    "import android.widget.CheckBox",
    "import android.widget.EditText",
    "import android.widget.LinearLayout",
    "import android.widget.ScrollView",
    "import android.widget.TextView",
    "import android.widget.Toast",
    "import org.json.JSONArray",
    "import org.json.JSONObject",
    "import java.time.Instant",
    "import java.time.ZoneId",
    "import java.time.ZoneOffset",
    "import java.time.format.DateTimeFormatter",
]
for imp in required_imports:
    if imp not in prefix:
        prefix = prefix.replace("import android.content.Context\n", f"import android.content.Context\n{imp}\n", 1)

generated_body = f"""
    fun saveChanges(context: Context, changes: List<CalendarChangeItem>) {{
        val arr = JSONArray()
        for (item in changes) {{
            val obj = JSONObject()
{chr(10).join(save_lines)}
            arr.put(obj)
        }}
        context.getSharedPreferences({prefs_const}, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_CHANGES, arr.toString())
            .apply()
    }}

    fun getLastChanges(context: Context): List<CalendarChangeItem> {{
        val raw = context.getSharedPreferences({prefs_const}, Context.MODE_PRIVATE)
            .getString(KEY_CHANGES, null) ?: return emptyList()
        val result = mutableListOf<CalendarChangeItem>()
        try {{
            val arr = JSONArray(raw)
            for (i in 0 until arr.length()) {{
                val obj = arr.getJSONObject(i)
                result.add(
                    CalendarChangeItem(
{("," + chr(10)).join(load_args)}
                    )
                )
            }}
        }} catch (_: Exception) {{
        }}
        return result
    }}

    fun clearChanges(context: Context) {{
        context.getSharedPreferences({prefs_const}, Context.MODE_PRIVATE)
            .edit()
            .remove(KEY_CHANGES)
            .apply()
    }}

    fun formatSummary(changes: List<CalendarChangeItem>): String {{
        if (changes.isEmpty()) return "Ei muutoksia"
        val added = changes.count {{ it.type == ChangeType.ADDED }}
        val modified = changes.count {{ it.type == ChangeType.MODIFIED }}
        val removed = changes.count {{ it.type == ChangeType.REMOVED }}
        val parts = mutableListOf<String>()
        if (added > 0) parts.add("$added lisätty")
        if (modified > 0) parts.add("$modified muokattu")
        if (removed > 0) parts.add("$removed poistettu")
        return parts.joinToString(", ")
    }}

    fun formatChangeDisplay(item: CalendarChangeItem): String {{
        val tag = when (item.type) {{
            ChangeType.ADDED -> "[LISÄTTY]"
            ChangeType.MODIFIED -> "[MUOKATTU]"
            ChangeType.REMOVED -> "[POISTETTU]"
        }}
        val dateFmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")
        val timeFmt = DateTimeFormatter.ofPattern("HH:mm")
        val whenStr = if (item.isAllDay) {{
            val sDate = Instant.ofEpochMilli(item.startMs).atZone(ZoneOffset.UTC).toLocalDate()
            val eDate = Instant.ofEpochMilli(item.endMs).atZone(ZoneOffset.UTC).toLocalDate().minusDays(1)
            if (eDate.isAfter(sDate)) {{
                "${{sDate.format(dateFmt)}} – ${{eDate.format(dateFmt)}} (koko päivä)"
            }} else {{
                "${{sDate.format(dateFmt)}} (koko päivä)"
            }}
        }} else {{
            val sDt = Instant.ofEpochMilli(item.startMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
            val eDt = Instant.ofEpochMilli(item.endMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
            "${{sDt.format(dateFmt)}} klo ${{sDt.format(timeFmt)}}–${{eDt.format(timeFmt)}}"
        }}
        return "$tag ${{item.title}}\\n$whenStr"
    }}

    fun revertSingleChange(context: Context, item: CalendarChangeItem): Boolean {{
        return try {{
            val resolver = context.contentResolver
            when (item.type) {{
                ChangeType.ADDED -> {{
                    var removedFromCal = false{delete_by_id_code}
                    if (!removedFromCal) {{
                        val sel = "${{CalendarContract.Events.TITLE}} = ? AND ${{CalendarContract.Events.DTSTART}} = ? AND ${{CalendarContract.Events.DTEND}} = ?"
                        val args = arrayOf(item.title, item.startMs.toString(), item.endMs.toString())
                        resolver.delete(CalendarContract.Events.CONTENT_URI, sel, args)
                    }}
                }}
                ChangeType.MODIFIED -> {{{revert_modified_code}
                }}
                ChangeType.REMOVED -> {{
                    {cal_id_block}
                    if (targetCalId > 0L) {{
                        val values = ContentValues().apply {{
                            put(CalendarContract.Events.CALENDAR_ID, targetCalId)
                            put(CalendarContract.Events.TITLE, item.title)
                            put(CalendarContract.Events.DTSTART, item.startMs)
                            put(CalendarContract.Events.DTEND, item.endMs)
                            put(CalendarContract.Events.ALL_DAY, if (item.isAllDay) 1 else 0)
                            put(
                                CalendarContract.Events.EVENT_TIMEZONE,
                                if (item.isAllDay) "UTC" else ZoneId.systemDefault().id
                            )
{extra_insert_block}
                        }}
                        resolver.insert(CalendarContract.Events.CONTENT_URI, values)
                    }}
                }}
            }}
            val remaining = getLastChanges(context).filterNot {{ it == item }}
            saveChanges(context, remaining)
            true
        }} catch (_: Exception) {{
            false
        }}
    }}

    fun revertAllChanges(context: Context): Int {{
        val current = getLastChanges(context).toList()
        var count = 0
        for (item in current) {{
            if (revertSingleChange(context, item)) {{
                count++
            }}
        }}
        return count
    }}

    fun updateSingleEvent(
        context: Context,
        item: CalendarChangeItem,
        newTitle: String,
        newStartMs: Long,
        newEndMs: Long,
        newIsAllDay: Boolean
    ): Boolean {{
        return try {{
            val resolver = context.contentResolver
            val values = ContentValues().apply {{
                put(CalendarContract.Events.TITLE, newTitle)
                put(CalendarContract.Events.DTSTART, newStartMs)
                put(CalendarContract.Events.DTEND, newEndMs)
                put(CalendarContract.Events.ALL_DAY, if (newIsAllDay) 1 else 0)
                put(
                    CalendarContract.Events.EVENT_TIMEZONE,
                    if (newIsAllDay) "UTC" else ZoneId.systemDefault().id
                )
            }}
            var updatedInCal = false{update_by_id_code}
            if (!updatedInCal) {{
                val sel = "${{CalendarContract.Events.TITLE}} = ? AND ${{CalendarContract.Events.DTSTART}} = ? AND ${{CalendarContract.Events.DTEND}} = ?"
                val args = arrayOf(item.title, item.startMs.toString(), item.endMs.toString())
                resolver.update(CalendarContract.Events.CONTENT_URI, values, sel, args)
            }}
            val updatedItem = item.copy(
                title = newTitle,
                startMs = newStartMs,
                endMs = newEndMs,
                isAllDay = newIsAllDay
            )
            val updatedList = getLastChanges(context).map {{ if (it == item) updatedItem else it }}
            saveChanges(context, updatedList)
            true
        }} catch (_: Exception) {{
            false
        }}
    }}

    fun showManageChangesDialog(context: Context, onChanged: (() -> Unit)? = null) {{
        val changes = getLastChanges(context)
        val density = context.resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()

        fun makeCardBg(fillHex: String = "#182332", strokeHex: String = "#2A394A", radiusDp: Int = 12): GradientDrawable {{
            return GradientDrawable().apply {{
                setColor(Color.parseColor(fillHex))
                setStroke(dp(1), Color.parseColor(strokeHex))
                cornerRadius = dp(radiusDp).toFloat()
            }}
        }}

        val rootContainer = LinearLayout(context).apply {{
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#0F1722"))
        }}

        val headerBar = LinearLayout(context).apply {{
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(20), dp(18), dp(20), dp(14))
        }}
        headerBar.addView(TextView(context).apply {{
            text = "Kalenterimuutosten hallinta"
            textSize = 19f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#F1F5F9"))
        }})
        headerBar.addView(TextView(context).apply {{
            text = if (changes.isEmpty()) "Ei avoimia muutoksia" else "Yhteenveto: ${{formatSummary(changes)}}"
            textSize = 12f
            setTextColor(Color.parseColor("#38BDF8"))
            setPadding(0, dp(2), 0, 0)
        }})
        rootContainer.addView(headerBar)

        val topDivider = View(context).apply {{ setBackgroundColor(Color.parseColor("#2A394A")) }}
        rootContainer.addView(topDivider, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)))

        val scroll = ScrollView(context).apply {{ isFillViewport = true }}
        val rootLayout = LinearLayout(context).apply {{
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(14), dp(16), dp(16))
        }}
        scroll.addView(rootLayout)
        rootContainer.addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))

        var dialogRef: AlertDialog? = null

        if (changes.isEmpty()) {{
            val emptyBox = LinearLayout(context).apply {{
                orientation = LinearLayout.VERTICAL
                background = makeCardBg("#182332", "#2A394A", 12)
                setPadding(dp(16), dp(20), dp(16), dp(20))
            }}
            emptyBox.addView(TextView(context).apply {{
                text = "Ei viimeisimpiä synkronoinnin tekemiä kalenterimuutoksia."
                setTextColor(Color.parseColor("#CBD5E1"))
                textSize = 14f
            }})
            rootLayout.addView(emptyBox)
        }} else {{
            val headerTv = TextView(context).apply {{
                text = "Voit perua yksittäisiä muutoksia, muokata niiden tietoja tai kumota kaikki kerralla:"
                setTextColor(Color.parseColor("#94A3B8"))
                textSize = 13f
                setPadding(0, 0, 0, dp(12))
            }}
            rootLayout.addView(headerTv)

            for (item in changes) {{
                val accentHex = when (item.type) {{
                    ChangeType.ADDED -> "#10B981"
                    ChangeType.MODIFIED -> "#38BDF8"
                    ChangeType.REMOVED -> "#EF4444"
                }}

                val card = LinearLayout(context).apply {{
                    orientation = LinearLayout.VERTICAL
                    background = makeCardBg("#182332", "#2A394A", 12)
                    setPadding(dp(14), dp(14), dp(14), dp(14))
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT
                    ).apply {{
                        bottomMargin = dp(12)
                    }}
                }}

                val badgeTv = TextView(context).apply {{
                    text = when (item.type) {{
                        ChangeType.ADDED -> "LISÄTTY"
                        ChangeType.MODIFIED -> "MUOKATTU"
                        ChangeType.REMOVED -> "POISTETTU"
                    }}
                    textSize = 11f
                    letterSpacing = 0.05f
                    setTypeface(null, Typeface.BOLD)
                    setTextColor(Color.parseColor(accentHex))
                    setPadding(0, 0, 0, dp(4))
                }}
                card.addView(badgeTv)

                val bodyLines = formatChangeDisplay(item).substringAfter("] ").trim()
                val infoTv = TextView(context).apply {{
                    text = bodyLines
                    setTextColor(Color.parseColor("#F1F5F9"))
                    textSize = 14f
                }}
                card.addView(infoTv)

                val btnRow = LinearLayout(context).apply {{
                    orientation = LinearLayout.HORIZONTAL
                    setPadding(0, dp(12), 0, 0)
                }}

                val btnEdit = Button(context).apply {{
                    text = "Muokkaa"
                    isAllCaps = false
                    textSize = 13f
                    setTypeface(null, Typeface.BOLD)
                    background = makeCardBg("#1E3A5F", "#0284C7", 8)
                    setTextColor(Color.parseColor("#E0F2FE"))
                    setPadding(dp(14), dp(8), dp(14), dp(8))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {{
                        marginEnd = dp(8)
                    }}
                }}

                val btnRevert = Button(context).apply {{
                    text = "Peru muutos"
                    isAllCaps = false
                    textSize = 13f
                    setTypeface(null, Typeface.BOLD)
                    background = makeCardBg("#3F1D24", "#DC2626", 8)
                    setTextColor(Color.parseColor("#FEE2E2"))
                    setPadding(dp(14), dp(8), dp(14), dp(8))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                }}

                btnRow.addView(btnEdit)
                btnRow.addView(btnRevert)
                card.addView(btnRow)
                rootLayout.addView(card)

                btnEdit.setOnClickListener {{
                    showEditEventDialog(context, item) {{
                        dialogRef?.dismiss()
                        onChanged?.invoke()
                        showManageChangesDialog(context, onChanged)
                    }}
                }}

                btnRevert.setOnClickListener {{
                    if (revertSingleChange(context, item)) {{
                        Toast.makeText(context, "Muutos peruttu: ${{item.title}}", Toast.LENGTH_SHORT).show()
                        dialogRef?.dismiss()
                        onChanged?.invoke()
                        showManageChangesDialog(context, onChanged)
                    }} else {{
                        Toast.makeText(context, "Muutoksen peruminen epäonnistui", Toast.LENGTH_SHORT).show()
                    }}
                }}
            }}
        }}

        val bottomDivider = View(context).apply {{ setBackgroundColor(Color.parseColor("#2A394A")) }}
        rootContainer.addView(bottomDivider, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)))

        val footerBar = LinearLayout(context).apply {{
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(16), dp(12), dp(16), dp(12))
        }}

        if (changes.isNotEmpty()) {{
            val btnRevertAll = Button(context).apply {{
                text = "Peru kaikki (${{changes.size}})"
                isAllCaps = false
                textSize = 13f
                setTypeface(null, Typeface.BOLD)
                background = makeCardBg("#3F1D24", "#DC2626", 8)
                setTextColor(Color.parseColor("#FEE2E2"))
                setPadding(dp(14), dp(10), dp(14), dp(10))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {{
                    marginEnd = dp(10)
                }}
                setOnClickListener {{
                    val reverted = revertAllChanges(context)
                    Toast.makeText(context, "Peruttu $reverted kalenterimuutosta", Toast.LENGTH_LONG).show()
                    dialogRef?.dismiss()
                    onChanged?.invoke()
                }}
            }}
            footerBar.addView(btnRevertAll)
        }}

        val btnClose = Button(context).apply {{
            text = "Sulje"
            isAllCaps = false
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            background = makeCardBg("#1982C4", "#38BDF8", 8)
            setTextColor(Color.parseColor("#FFFFFF"))
            setPadding(dp(20), dp(10), dp(20), dp(10))
            setOnClickListener {{ dialogRef?.dismiss() }}
        }}
        footerBar.addView(btnClose)
        rootContainer.addView(footerBar)

        val dialog = AlertDialog.Builder(context)
            .setView(rootContainer)
            .create()
        dialogRef = dialog
        dialog.window?.setBackgroundDrawable(makeCardBg("#0F1722", "#2A394A", 14))
        dialog.show()
    }}

    private fun showEditEventDialog(
        context: Context,
        item: CalendarChangeItem,
        onSaved: () -> Unit
    ) {{
        val density = context.resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()

        fun makeCardBg(fillHex: String = "#182332", strokeHex: String = "#2A394A", radiusDp: Int = 10): GradientDrawable {{
            return GradientDrawable().apply {{
                setColor(Color.parseColor(fillHex))
                setStroke(dp(1), Color.parseColor(strokeHex))
                cornerRadius = dp(radiusDp).toFloat()
            }}
        }}

        val rootContainer = LinearLayout(context).apply {{
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#0F1722"))
        }}

        val headerBar = LinearLayout(context).apply {{
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(20), dp(16), dp(20), dp(14))
        }}
        headerBar.addView(TextView(context).apply {{
            text = "Muokkaa kalenteritapahtumaa"
            textSize = 18f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#F1F5F9"))
        }})
        rootContainer.addView(headerBar)

        val layout = LinearLayout(context).apply {{
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(14), dp(18), dp(14))
        }}
        rootContainer.addView(layout)

        val lblTitle = TextView(context).apply {{
            text = "Tapahtuman otsikko"
            textSize = 13f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, 0, 0, dp(6))
        }}
        val inputTitle = EditText(context).apply {{
            setText(item.title)
            inputType = InputType.TYPE_CLASS_TEXT
            background = makeCardBg("#111923", "#37475A", 8)
            setTextColor(Color.parseColor("#F1F5F9"))
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }}

        val chkAllDay = CheckBox(context).apply {{
            text = "Koko päivän tapahtuma (loma/vapaa)"
            isChecked = item.isAllDay
            setTextColor(Color.parseColor("#F1F5F9"))
            setPadding(dp(4), dp(12), 0, dp(12))
        }}

        var selectedStart = if (item.isAllDay) {{
            Instant.ofEpochMilli(item.startMs).atZone(ZoneOffset.UTC).toLocalDateTime()
        }} else {{
            Instant.ofEpochMilli(item.startMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
        }}

        var selectedEnd = if (item.isAllDay) {{
            Instant.ofEpochMilli(item.endMs).atZone(ZoneOffset.UTC).toLocalDateTime()
        }} else {{
            Instant.ofEpochMilli(item.endMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
        }}

        val dateFmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")
        val timeFmt = DateTimeFormatter.ofPattern("HH:mm")

        fun stylePickerBtn(btn: Button) {{
            btn.background = makeCardBg("#182332", "#37475A", 8)
            btn.setTextColor(Color.parseColor("#38BDF8"))
            btn.isAllCaps = false
            btn.textSize = 14f
            btn.setPadding(dp(12), dp(10), dp(12), dp(10))
            btn.layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {{
                bottomMargin = dp(8)
            }}
        }}

        val btnStartDate = Button(context).apply {{
            text = "Alkupäivä: ${{selectedStart.format(dateFmt)}}"
            stylePickerBtn(this)
        }}
        val btnStartTime = Button(context).apply {{
            text = "Alkuaika: ${{selectedStart.format(timeFmt)}}"
            stylePickerBtn(this)
        }}
        val btnEndDate = Button(context).apply {{
            text = "Loppupäivä: ${{selectedEnd.format(dateFmt)}}"
            stylePickerBtn(this)
        }}
        val btnEndTime = Button(context).apply {{
            text = "Loppuaika: ${{selectedEnd.format(timeFmt)}}"
            stylePickerBtn(this)
        }}

        btnStartDate.setOnClickListener {{
            DatePickerDialog(context, {{ _, y, m, d ->
                selectedStart = selectedStart.withYear(y).withMonth(m + 1).withDayOfMonth(d)
                btnStartDate.text = "Alkupäivä: ${{selectedStart.format(dateFmt)}}"
            }}, selectedStart.year, selectedStart.monthValue - 1, selectedStart.dayOfMonth).show()
        }}

        btnStartTime.setOnClickListener {{
            TimePickerDialog(context, {{ _, h, min ->
                selectedStart = selectedStart.withHour(h).withMinute(min)
                btnStartTime.text = "Alkuaika: ${{selectedStart.format(timeFmt)}}"
            }}, selectedStart.hour, selectedStart.minute, true).show()
        }}

        btnEndDate.setOnClickListener {{
            DatePickerDialog(context, {{ _, y, m, d ->
                selectedEnd = selectedEnd.withYear(y).withMonth(m + 1).withDayOfMonth(d)
                btnEndDate.text = "Loppupäivä: ${{selectedEnd.format(dateFmt)}}"
            }}, selectedEnd.year, selectedEnd.monthValue - 1, selectedEnd.dayOfMonth).show()
        }}

        btnEndTime.setOnClickListener {{
            TimePickerDialog(context, {{ _, h, min ->
                selectedEnd = selectedEnd.withHour(h).withMinute(min)
                btnEndTime.text = "Loppuaika: ${{selectedEnd.format(timeFmt)}}"
            }}, selectedEnd.hour, selectedEnd.minute, true).show()
        }}

        layout.addView(lblTitle)
        layout.addView(inputTitle)
        layout.addView(chkAllDay)
        layout.addView(btnStartDate)
        layout.addView(btnStartTime)
        layout.addView(btnEndDate)
        layout.addView(btnEndTime)

        val footerBar = LinearLayout(context).apply {{
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(16), dp(12), dp(16), dp(12))
        }}

        val btnCancel = Button(context).apply {{
            text = "Peruuta"
            isAllCaps = false
            background = makeCardBg("#233040", "#37475A", 8)
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(dp(16), dp(10), dp(16), dp(10))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {{
                marginEnd = dp(10)
            }}
        }}

        val btnSave = Button(context).apply {{
            text = "Tallenna"
            isAllCaps = false
            setTypeface(null, Typeface.BOLD)
            background = makeCardBg("#1982C4", "#38BDF8", 8)
            setTextColor(Color.parseColor("#FFFFFF"))
            setPadding(dp(20), dp(10), dp(20), dp(10))
        }}

        footerBar.addView(btnCancel)
        footerBar.addView(btnSave)
        rootContainer.addView(footerBar)

        val dialog = AlertDialog.Builder(context)
            .setView(rootContainer)
            .create()
        dialog.window?.setBackgroundDrawable(makeCardBg("#0F1722", "#2A394A", 14))

        btnCancel.setOnClickListener {{ dialog.dismiss() }}
        btnSave.setOnClickListener {{
            val titleStr = inputTitle.text.toString().trim().ifEmpty {{ item.title }}
            val allDay = chkAllDay.isChecked
            val finalStartMs: Long
            val finalEndMs: Long
            if (allDay) {{
                val sDate = selectedStart.toLocalDate()
                var eDate = selectedEnd.toLocalDate()
                if (!eDate.isAfter(sDate)) eDate = sDate.plusDays(1)
                finalStartMs = sDate.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli()
                finalEndMs = eDate.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli()
            }} else {{
                finalStartMs = selectedStart.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
                var eDt = selectedEnd
                if (!eDt.isAfter(selectedStart)) eDt = selectedStart.plusHours(8)
                finalEndMs = eDt.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            }}

            if (updateSingleEvent(context, item, titleStr, finalStartMs, finalEndMs, allDay)) {{
                Toast.makeText(context, "Tapahtuma päivitetty kalenteriin", Toast.LENGTH_SHORT).show()
                dialog.dismiss()
                onSaved()
            }} else {{
                Toast.makeText(context, "Tapahtuman päivitys epäonnistui", Toast.LENGTH_SHORT).show()
            }}
        }}

        dialog.show()
    }}
}}
"""

fixed = prefix + generated_body

open_braces = fixed.count("{")
close_braces = fixed.count("}")
if open_braces != close_braces:
    raise RuntimeError(f"Aaltosulkeet eivät täsmää: '{{' = {open_braces}, '}}' = {close_braces}")

with open(TRACKER_PATH, "w", encoding="utf-8") as f:
    f.write(fixed)

print(f"CalendarChangeTracker.kt rakennettu kokonaan uudelleen! (aaltosulkeet: {open_braces}/{close_braces})")
