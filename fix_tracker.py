#!/usr/bin/env python3
import os
import re

TRACKER_PATH = os.path.join(
    "app", "src", "main", "java", "fi", "numeron", "vuorovahti", "CalendarChangeTracker.kt"
)

with open(TRACKER_PATH, "r", encoding="utf-8") as f:
    content = f.read()

idx = content.find("saveChang")
if idx == -1:
    raise RuntimeError("Katkennutta 'saveChang'-kohtaa ei löytynyt tiedostosta.")

prefix = content[:idx]
lines = prefix.splitlines()

print("--- Katkeamiskohta (rivit -15 .. loppu) ---")
for i, line in enumerate(lines[-15:], start=max(1, len(lines) - 14)):
    print(f"{i}: {line}")

recent_block = "\n".join(lines[-20:])
list_var = "updated"
for candidate in ["updatedList", "updated", "remaining", "newList", "changes", "list", "items"]:
    if re.search(rf"\b{candidate}\b", recent_block):
        list_var = candidate
        break

func_headers = re.findall(r"fun\s+\w+\s*\([^)]*\)\s*(?::\s*([A-Za-z0-9_<>?]+))?", prefix)
last_return_type = func_headers[-1] if func_headers else "Boolean"

if last_return_type == "Boolean":
    tail_fix = f"""saveChanges(context, {list_var})
            true
        }} catch (_: Exception) {{
            false
        }}
    }}
"""
else:
    tail_fix = f"""saveChanges(context, {list_var})
        }} catch (_: Exception) {{
        }}
    }}
"""

ui_methods = """
    fun showManageChangesDialog(context: Context, onChanged: (() -> Unit)? = null) {
        val changes = getLastChanges(context)
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
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(20), dp(18), dp(20), dp(14))
        }
        headerBar.addView(TextView(context).apply {
            text = "Kalenterimuutosten hallinta"
            textSize = 19f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#F1F5F9"))
        })
        headerBar.addView(TextView(context).apply {
            text = if (changes.isEmpty()) "Ei avoimia muutoksia" else "Yhteenveto: ${formatSummary(changes)}"
            textSize = 12f
            setTextColor(Color.parseColor("#38BDF8"))
            setPadding(0, dp(2), 0, 0)
        })
        rootContainer.addView(headerBar)

        val topDivider = View(context).apply { setBackgroundColor(Color.parseColor("#2A394A")) }
        rootContainer.addView(topDivider, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)))

        val scroll = ScrollView(context).apply { isFillViewport = true }
        val rootLayout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(14), dp(16), dp(16))
        }
        scroll.addView(rootLayout)
        rootContainer.addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))

        var dialogRef: AlertDialog? = null

        if (changes.isEmpty()) {
            val emptyBox = LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                background = makeCardBg("#182332", "#2A394A", 12)
                setPadding(dp(16), dp(20), dp(16), dp(20))
            }
            emptyBox.addView(TextView(context).apply {
                text = "Ei viimeisimpiä synkronoinnin tekemiä kalenterimuutoksia."
                setTextColor(Color.parseColor("#CBD5E1"))
                textSize = 14f
            })
            rootLayout.addView(emptyBox)
        } else {
            val headerTv = TextView(context).apply {
                text = "Voit perua yksittäisiä muutoksia, muokata niiden tietoja tai kumota kaikki kerralla:"
                setTextColor(Color.parseColor("#94A3B8"))
                textSize = 13f
                setPadding(0, 0, 0, dp(12))
            }
            rootLayout.addView(headerTv)

            for (item in changes) {
                val accentHex = when (item.type) {
                    ChangeType.ADDED -> "#10B981"
                    ChangeType.MODIFIED -> "#38BDF8"
                    ChangeType.REMOVED -> "#EF4444"
                }

                val card = LinearLayout(context).apply {
                    orientation = LinearLayout.VERTICAL
                    background = makeCardBg("#182332", "#2A394A", 12)
                    setPadding(dp(14), dp(14), dp(14), dp(14))
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT
                    ).apply {
                        bottomMargin = dp(12)
                    }
                }

                val badgeTv = TextView(context).apply {
                    text = when (item.type) {
                        ChangeType.ADDED -> "LISÄTTY"
                        ChangeType.MODIFIED -> "MUOKATTU"
                        ChangeType.REMOVED -> "POISTETTU"
                    }
                    textSize = 11f
                    letterSpacing = 0.05f
                    setTypeface(null, Typeface.BOLD)
                    setTextColor(Color.parseColor(accentHex))
                    setPadding(0, 0, 0, dp(4))
                }
                card.addView(badgeTv)

                val bodyLines = formatChangeDisplay(item).substringAfter("] ").trim()
                val infoTv = TextView(context).apply {
                    text = bodyLines
                    setTextColor(Color.parseColor("#F1F5F9"))
                    textSize = 14f
                }
                card.addView(infoTv)

                val btnRow = LinearLayout(context).apply {
                    orientation = LinearLayout.HORIZONTAL
                    setPadding(0, dp(12), 0, 0)
                }

                val btnEdit = Button(context).apply {
                    text = "Muokkaa"
                    isAllCaps = false
                    textSize = 13f
                    setTypeface(null, Typeface.BOLD)
                    background = makeCardBg("#1E3A5F", "#0284C7", 8)
                    setTextColor(Color.parseColor("#E0F2FE"))
                    setPadding(dp(14), dp(8), dp(14), dp(8))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
                        marginEnd = dp(8)
                    }
                }

                val btnRevert = Button(context).apply {
                    text = "Peru muutos"
                    isAllCaps = false
                    textSize = 13f
                    setTypeface(null, Typeface.BOLD)
                    background = makeCardBg("#3F1D24", "#DC2626", 8)
                    setTextColor(Color.parseColor("#FEE2E2"))
                    setPadding(dp(14), dp(8), dp(14), dp(8))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                }

                btnRow.addView(btnEdit)
                btnRow.addView(btnRevert)
                card.addView(btnRow)
                rootLayout.addView(card)

                btnEdit.setOnClickListener {
                    showEditEventDialog(context, item) {
                        dialogRef?.dismiss()
                        onChanged?.invoke()
                        showManageChangesDialog(context, onChanged)
                    }
                }

                btnRevert.setOnClickListener {
                    if (revertSingleChange(context, item)) {
                        Toast.makeText(context, "Muutos peruttu: ${item.title}", Toast.LENGTH_SHORT).show()
                        dialogRef?.dismiss()
                        onChanged?.invoke()
                        showManageChangesDialog(context, onChanged)
                    } else {
                        Toast.makeText(context, "Muutoksen peruminen epäonnistui", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }

        val bottomDivider = View(context).apply { setBackgroundColor(Color.parseColor("#2A394A")) }
        rootContainer.addView(bottomDivider, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)))

        val footerBar = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(16), dp(12), dp(16), dp(12))
        }

        if (changes.isNotEmpty()) {
            val btnRevertAll = Button(context).apply {
                text = "Peru kaikki (${changes.size})"
                isAllCaps = false
                textSize = 13f
                setTypeface(null, Typeface.BOLD)
                background = makeCardBg("#3F1D24", "#DC2626", 8)
                setTextColor(Color.parseColor("#FEE2E2"))
                setPadding(dp(14), dp(10), dp(14), dp(10))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    marginEnd = dp(10)
                }
                setOnClickListener {
                    val reverted = revertAllChanges(context)
                    Toast.makeText(context, "Peruttu $reverted kalenterimuutosta", Toast.LENGTH_LONG).show()
                    dialogRef?.dismiss()
                    onChanged?.invoke()
                }
            }
            footerBar.addView(btnRevertAll)
        }

        val btnClose = Button(context).apply {
            text = "Sulje"
            isAllCaps = false
            textSize = 14f
            setTypeface(null, Typeface.BOLD)
            background = makeCardBg("#1982C4", "#38BDF8", 8)
            setTextColor(Color.parseColor("#FFFFFF"))
            setPadding(dp(20), dp(10), dp(20), dp(10))
            setOnClickListener { dialogRef?.dismiss() }
        }
        footerBar.addView(btnClose)
        rootContainer.addView(footerBar)

        val dialog = AlertDialog.Builder(context)
            .setView(rootContainer)
            .create()
        dialogRef = dialog
        dialog.window?.setBackgroundDrawable(makeCardBg("#0F1722", "#2A394A", 14))
        dialog.show()
    }

    private fun showEditEventDialog(
        context: Context,
        item: CalendarChangeItem,
        onSaved: () -> Unit
    ) {
        val density = context.resources.displayMetrics.density
        fun dp(v: Int): Int = (v * density).toInt()

        fun makeCardBg(fillHex: String = "#182332", strokeHex: String = "#2A394A", radiusDp: Int = 10): GradientDrawable {
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
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(20), dp(16), dp(20), dp(14))
        }
        headerBar.addView(TextView(context).apply {
            text = "Muokkaa kalenteritapahtumaa"
            textSize = 18f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#F1F5F9"))
        })
        rootContainer.addView(headerBar)

        val layout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(14), dp(18), dp(14))
        }
        rootContainer.addView(layout)

        val lblTitle = TextView(context).apply {
            text = "Tapahtuman otsikko"
            textSize = 13f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, 0, 0, dp(6))
        }
        val inputTitle = EditText(context).apply {
            setText(item.title)
            inputType = InputType.TYPE_CLASS_TEXT
            background = makeCardBg("#111923", "#37475A", 8)
            setTextColor(Color.parseColor("#F1F5F9"))
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }

        val chkAllDay = CheckBox(context).apply {
            text = "Koko päivän tapahtuma (loma/vapaa)"
            isChecked = item.isAllDay
            setTextColor(Color.parseColor("#F1F5F9"))
            setPadding(dp(4), dp(12), 0, dp(12))
        }

        var selectedStart = if (item.isAllDay) {
            Instant.ofEpochMilli(item.startMs).atZone(ZoneOffset.UTC).toLocalDateTime()
        } else {
            Instant.ofEpochMilli(item.startMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
        }

        var selectedEnd = if (item.isAllDay) {
            Instant.ofEpochMilli(item.endMs).atZone(ZoneOffset.UTC).toLocalDateTime()
        } else {
            Instant.ofEpochMilli(item.endMs).atZone(ZoneId.systemDefault()).toLocalDateTime()
        }

        val dateFmt = DateTimeFormatter.ofPattern("dd.MM.yyyy")
        val timeFmt = DateTimeFormatter.ofPattern("HH:mm")

        fun stylePickerBtn(btn: Button) {
            btn.background = makeCardBg("#182332", "#37475A", 8)
            btn.setTextColor(Color.parseColor("#38BDF8"))
            btn.isAllCaps = false
            btn.textSize = 14f
            btn.setPadding(dp(12), dp(10), dp(12), dp(10))
            btn.layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                bottomMargin = dp(8)
            }
        }

        val btnStartDate = Button(context).apply {
            text = "Alkupäivä: ${selectedStart.format(dateFmt)}"
            stylePickerBtn(this)
        }
        val btnStartTime = Button(context).apply {
            text = "Alkuaika: ${selectedStart.format(timeFmt)}"
            stylePickerBtn(this)
        }
        val btnEndDate = Button(context).apply {
            text = "Loppupäivä: ${selectedEnd.format(dateFmt)}"
            stylePickerBtn(this)
        }
        val btnEndTime = Button(context).apply {
            text = "Loppuaika: ${selectedEnd.format(timeFmt)}"
            stylePickerBtn(this)
        }

        btnStartDate.setOnClickListener {
            DatePickerDialog(context, { _, y, m, d ->
                selectedStart = selectedStart.withYear(y).withMonth(m + 1).withDayOfMonth(d)
                btnStartDate.text = "Alkupäivä: ${selectedStart.format(dateFmt)}"
            }, selectedStart.year, selectedStart.monthValue - 1, selectedStart.dayOfMonth).show()
        }

        btnStartTime.setOnClickListener {
            TimePickerDialog(context, { _, h, min ->
                selectedStart = selectedStart.withHour(h).withMinute(min)
                btnStartTime.text = "Alkuaika: ${selectedStart.format(timeFmt)}"
            }, selectedStart.hour, selectedStart.minute, true).show()
        }

        btnEndDate.setOnClickListener {
            DatePickerDialog(context, { _, y, m, d ->
                selectedEnd = selectedEnd.withYear(y).withMonth(m + 1).withDayOfMonth(d)
                btnEndDate.text = "Loppupäivä: ${selectedEnd.format(dateFmt)}"
            }, selectedEnd.year, selectedEnd.monthValue - 1, selectedEnd.dayOfMonth).show()
        }

        btnEndTime.setOnClickListener {
            TimePickerDialog(context, { _, h, min ->
                selectedEnd = selectedEnd.withHour(h).withMinute(min)
                btnEndTime.text = "Loppuaika: ${selectedEnd.format(timeFmt)}"
            }, selectedEnd.hour, selectedEnd.minute, true).show()
        }

        layout.addView(lblTitle)
        layout.addView(inputTitle)
        layout.addView(chkAllDay)
        layout.addView(btnStartDate)
        layout.addView(btnStartTime)
        layout.addView(btnEndDate)
        layout.addView(btnEndTime)

        val footerBar = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
            setBackgroundColor(Color.parseColor("#182332"))
            setPadding(dp(16), dp(12), dp(16), dp(12))
        }

        val btnCancel = Button(context).apply {
            text = "Peruuta"
            isAllCaps = false
            background = makeCardBg("#233040", "#37475A", 8)
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(dp(16), dp(10), dp(16), dp(10))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                marginEnd = dp(10)
            }
        }

        val btnSave = Button(context).apply {
            text = "Tallenna"
            isAllCaps = false
            setTypeface(null, Typeface.BOLD)
            background = makeCardBg("#1982C4", "#38BDF8", 8)
            setTextColor(Color.parseColor("#FFFFFF"))
            setPadding(dp(20), dp(10), dp(20), dp(10))
        }

        footerBar.addView(btnCancel)
        footerBar.addView(btnSave)
        rootContainer.addView(footerBar)

        val dialog = AlertDialog.Builder(context)
            .setView(rootContainer)
            .create()
        dialog.window?.setBackgroundDrawable(makeCardBg("#0F1722", "#2A394A", 14))

        btnCancel.setOnClickListener { dialog.dismiss() }
        btnSave.setOnClickListener {
            val titleStr = inputTitle.text.toString().trim().ifEmpty { item.title }
            val allDay = chkAllDay.isChecked
            val finalStartMs: Long
            val finalEndMs: Long
            if (allDay) {
                val sDate = selectedStart.toLocalDate()
                var eDate = selectedEnd.toLocalDate()
                if (!eDate.isAfter(sDate)) eDate = sDate.plusDays(1)
                finalStartMs = sDate.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli()
                finalEndMs = eDate.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli()
            } else {
                finalStartMs = selectedStart.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
                var eDt = selectedEnd
                if (!eDt.isAfter(selectedStart)) eDt = selectedStart.plusHours(8)
                finalEndMs = eDt.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            }

            if (updateSingleEvent(context, item, titleStr, finalStartMs, finalEndMs, allDay)) {
                Toast.makeText(context, "Tapahtuma päivitetty kalenteriin", Toast.LENGTH_SHORT).show()
                dialog.dismiss()
                onSaved()
            } else {
                Toast.makeText(context, "Tapahtuman päivitys epäonnistui", Toast.LENGTH_SHORT).show()
            }
        }

        dialog.show()
    }
}
"""

fixed = prefix + tail_fix + ui_methods

open_braces = fixed.count("{")
close_braces = fixed.count("}")
if open_braces != close_braces:
    raise RuntimeError(f"Aaltosulkeet eivät täsmää: '{{' = {open_braces}, '}}' = {close_braces}")

with open(TRACKER_PATH, "w", encoding="utf-8") as f:
    f.write(fixed)

print(f"Korjattu onnistuneesti: {TRACKER_PATH} (listamuuttuja: {list_var}, aaltosulkeet: {open_braces}/{close_braces})")
