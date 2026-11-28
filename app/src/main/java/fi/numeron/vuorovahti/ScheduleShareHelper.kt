package fi.numeron.vuorovahti

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.util.TypedValue
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.core.content.FileProvider
import java.io.File
import java.io.FileOutputStream
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

object ScheduleShareHelper {

    private val fiDow = arrayOf("Ma", "Ti", "Ke", "To", "Pe", "La", "Su")
    private val enDow = arrayOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    private val shortDateFmt = DateTimeFormatter.ofPattern("d.M.")
    private val fullDateFmt = DateTimeFormatter.ofPattern("d.M.yyyy")

    fun showShareDialog(
        context: Context,
        ym: YearMonth,
        monthTitle: String,
        allDayMap: Map<LocalDate, CalendarDisplayDay>,
        periodStart: LocalDate,
        periodEnd: LocalDate
    ) {
        val en = DemoModeHelper.isEnglish(context)
        val dp = { v: Int -> UiStyleHelper.dp(context, v) }
        val cardBg = UiStyleHelper.cardHex(context)
        val btnBg = UiStyleHelper.headerCellHex(context)
        val borderHex = UiStyleHelper.borderStrongHex(context)

        val root = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor(cardBg))
            setPadding(dp(18), dp(16), dp(18), dp(14))
        }

        root.addView(
            TextView(context).apply {
                text = if (en) "SHARE SCHEDULE" else "JAA VUOROLISTA"
                setTextColor(Color.parseColor("#38BDF8"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
                setTypeface(null, Typeface.BOLD)
                setPadding(0, 0, 0, dp(10))
            }
        )

        val periodLabel = "${periodStart.format(shortDateFmt)}–${periodEnd.format(shortDateFmt)}"
        val periodTitle = if (en) "Shift period $periodLabel" else "Työvuorolista $periodLabel"
        val monthStart = ym.atDay(1)
        val monthEnd = ym.atEndOfMonth()

        val dialog = AlertDialog.Builder(context)
            .setView(root)
            .create()

        fun addOptionButton(label: String, primary: Boolean, onClick: () -> Unit) {
            val btn = Button(context).apply {
                text = label
                isAllCaps = false
                setTextColor(if (primary) Color.WHITE else Color.parseColor("#E2E8F0"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 13.5f)
                setTypeface(null, Typeface.BOLD)
                background = if (primary) {
                    UiStyleHelper.rippleRoundedBg(context, "#1982C4", "#38BDF8", 9f, "#44FFFFFF")
                } else {
                    UiStyleHelper.rippleRoundedBg(context, btnBg, borderHex, 9f)
                }
                setPadding(dp(12), dp(10), dp(12), dp(10))
                setOnClickListener {
                    dialog.dismiss()
                    onClick()
                }
            }
            root.addView(
                btn,
                LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    bottomMargin = dp(8)
                }
            )
        }

        addOptionButton(
            if (en) "🖼 Share 3-week period as image ($periodLabel)" else "🖼 Jaa 3 vko työvuorolista kuvana ($periodLabel)",
            primary = true
        ) {
            shareAsPng(context, periodTitle, periodStart, periodEnd, allDayMap)
        }

        addOptionButton(
            if (en) "📝 Share 3-week period as text ($periodLabel)" else "📝 Jaa 3 vko työvuorolista tekstinä ($periodLabel)",
            primary = false
        ) {
            shareAsText(context, periodTitle, periodStart, periodEnd, allDayMap)
        }

        addOptionButton(
            if (en) "🖼 Share month as image ($monthTitle)" else "🖼 Jaa kuukausi kuvana ($monthTitle)",
            primary = false
        ) {
            shareAsPng(context, monthTitle, monthStart, monthEnd, allDayMap)
        }

        addOptionButton(
            if (en) "📝 Share month as text ($monthTitle)" else "📝 Jaa kuukausi tekstinä ($monthTitle)",
            primary = false
        ) {
            shareAsText(context, monthTitle, monthStart, monthEnd, allDayMap)
        }

        val btnCancel = Button(context).apply {
            text = if (en) "Cancel" else "Peruuta"
            isAllCaps = false
            setTextColor(Color.parseColor("#94A3B8"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            background = UiStyleHelper.rippleTransparentBg(context, 8f)
            setOnClickListener { dialog.dismiss() }
        }
        root.addView(
            btnCancel,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        )

        dialog.window?.setBackgroundDrawable(UiStyleHelper.roundedBg(context, cardBg, "#38BDF8", 14f))
        dialog.show()
    }

    fun sharePeriodDirectly(
        context: Context,
        periodStart: LocalDate,
        periodEnd: LocalDate,
        allDayMap: Map<LocalDate, CalendarDisplayDay>,
        asImage: Boolean
    ) {
        val en = DemoModeHelper.isEnglish(context)
        val rangeLabel = "${periodStart.format(shortDateFmt)}–${periodEnd.format(shortDateFmt)}"
        val title = if (en) "Shift period $rangeLabel" else "Työvuorolista $rangeLabel"
        if (asImage) {
            shareAsPng(context, title, periodStart, periodEnd, allDayMap)
        } else {
            shareAsText(context, title, periodStart, periodEnd, allDayMap)
        }
    }

    fun shareAsText(
        context: Context,
        title: String,
        startDate: LocalDate,
        endDate: LocalDate,
        allDayMap: Map<LocalDate, CalendarDisplayDay>
    ) {
        val en = DemoModeHelper.isEnglish(context)
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val showHolidays = prefs.getBoolean("show_finnish_holidays", true)
        val dows = if (en) enDow else fiDow

        val sb = StringBuilder()
        sb.append(title).append("\n")
        sb.append("${startDate.format(fullDateFmt)} – ${endDate.format(fullDateFmt)}\n")
        sb.append("────────────────────\n")

        var totalMin = 0
        var shiftCount = 0
        var d = startDate
        while (!d.isAfter(endDate)) {
            val day = allDayMap[d]
            val holiday = if (showHolidays) FinnishHolidays.getHolidayName(d, en) else null
            val hasShifts = day != null && day.shifts.isNotEmpty()
            val hasAbs = day != null && day.absences.isNotEmpty()

            if (hasShifts || hasAbs || holiday != null) {
                val dow = dows[d.dayOfWeek.value - 1]
                val dStr = d.format(shortDateFmt)
                val items = mutableListOf<String>()

                day?.shifts?.forEach { s ->
                    shiftCount++
                    val dur = if (s.endMinutes >= s.startMinutes) {
                        s.endMinutes - s.startMinutes
                    } else {
                        (24 * 60 - s.startMinutes) + s.endMinutes
                    }
                    totalMin += dur
                    val loc = s.location.takeIf { it.isNotBlank() }?.let { " ($it)" }.orEmpty()
                    items.add("${s.startText}–${s.endText}$loc")
                }
                day?.absences?.forEach { a ->
                    items.add(a.title)
                }
                if (holiday != null) {
                    items.add("[$holiday]")
                }
                sb.append("$dow $dStr  ${items.joinToString(" • ")}\n")
            }
            d = d.plusDays(1)
        }

        if (shiftCount > 0) {
            val hoursStr = formatHours(totalMin, en)
            val word = if (en) (if (shiftCount == 1) "shift" else "shifts") else (if (shiftCount == 1) "vuoro" else "vuoroa")
            sb.append("────────────────────\n")
            sb.append(if (en) "Total: $shiftCount $word • $hoursStr h" else "Yhteensä: $shiftCount $word • $hoursStr h")
        } else {
            sb.append(if (en) "No scheduled shifts." else "Ei merkittyjä työvuoroja.")
        }

        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_SUBJECT, title)
            putExtra(Intent.EXTRA_TEXT, sb.toString())
        }
        try {
            context.startActivity(Intent.createChooser(intent, if (en) "Share schedule" else "Jaa vuorolista"))
        } catch (_: Exception) {
            Toast.makeText(
                context,
                if (en) "No app found for sharing" else "Jakosovellusta ei löytynyt",
                Toast.LENGTH_SHORT
            ).show()
        }
    }

    fun shareAsPng(
        context: Context,
        title: String,
        startDate: LocalDate,
        endDate: LocalDate,
        allDayMap: Map<LocalDate, CalendarDisplayDay>
    ) {
        val en = DemoModeHelper.isEnglish(context)
        try {
            val bitmap = renderScheduleBitmap(context, title, startDate, endDate, allDayMap)
            val outDir = File(context.cacheDir, "shared_schedules").apply { mkdirs() }
            val outFile = File(outDir, "vuorolista_${startDate}_${endDate}.png")
            FileOutputStream(outFile).use { fos ->
                bitmap.compress(Bitmap.CompressFormat.PNG, 95, fos)
            }
            bitmap.recycle()

            val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", outFile)
            val intent = Intent(Intent.ACTION_SEND).apply {
                type = "image/png"
                putExtra(Intent.EXTRA_STREAM, uri)
                putExtra(Intent.EXTRA_SUBJECT, title)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            context.startActivity(Intent.createChooser(intent, if (en) "Share schedule image" else "Jaa vuorolistakuva"))
        } catch (_: Exception) {
            Toast.makeText(
                context,
                if (en) "Failed to create schedule image" else "Vuorolistakuvan luonti epäonnistui",
                Toast.LENGTH_SHORT
            ).show()
        }
    }

    private fun renderScheduleBitmap(
        context: Context,
        title: String,
        startDate: LocalDate,
        endDate: LocalDate,
        allDayMap: Map<LocalDate, CalendarDisplayDay>
    ): Bitmap {
        val en = DemoModeHelper.isEnglish(context)
        val prefs = context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
        val morningRgb = prefs.getInt("color_morning_rgb", SettingsDialogHelper.DEFAULT_MORNING_RGB)
        val eveningRgb = prefs.getInt("color_evening_rgb", SettingsDialogHelper.DEFAULT_EVENING_RGB)
        val nightRgb = prefs.getInt("color_night_rgb", SettingsDialogHelper.DEFAULT_NIGHT_RGB)
        val showHolidays = prefs.getBoolean("show_finnish_holidays", true)

        val gridStart = startDate.with(DayOfWeek.MONDAY)
        val gridEnd = endDate.with(DayOfWeek.SUNDAY)
        val weekCount = ((ChronoUnit.DAYS.between(gridStart, gridEnd) / 7L) + 1L).toInt().coerceAtLeast(1)

        val width = 1080
        val pad = 32
        val headerH = 122
        val dowH = 44
        val rowH = 132
        val footerH = 88
        val height = pad + headerH + dowH + (weekCount * rowH) + footerH + pad

        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val bgColor = Color.parseColor(UiStyleHelper.bgHex(context))
        val cardColor = Color.parseColor(UiStyleHelper.cardHex(context))
        val borderColor = Color.parseColor(UiStyleHelper.borderHex(context))
        canvas.drawColor(bgColor)

        val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
        val strokePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 2f
            color = borderColor
        }
        val titlePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#F1F5F9")
            textSize = 40f
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        }
        val subPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#38BDF8")
            textSize = 24f
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        }
        val dowPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#CBD5E1")
            textSize = 22f
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            textAlign = Paint.Align.CENTER
        }
        val dayNumPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            textSize = 22f
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        }
        val badgeTextPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            textSize = 19f
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            textAlign = Paint.Align.CENTER
        }
        val smallPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            textSize = 16f
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        }

        // Otsikko
        val rangeSub = "${startDate.format(fullDateFmt)} – ${endDate.format(fullDateFmt)}"
        canvas.drawText(title, pad.toFloat(), (pad + 46).toFloat(), titlePaint)
        canvas.drawText(rangeSub, pad.toFloat(), (pad + 86).toFloat(), subPaint)

        val tableLeft = pad.toFloat()
        val tableWidth = (width - pad * 2).toFloat()
        val colW = tableWidth / 7f
        var y = (pad + headerH).toFloat()

        // Viikonpäiväotsikot
        val dows = if (en) enDow else fiDow
        for (c in 0..6) {
            val x = tableLeft + c * colW
            val rect = RectF(x, y, x + colW, y + dowH)
            fillPaint.color = Color.parseColor(if (c >= 5) "#1E2B3D" else "#233040")
            canvas.drawRect(rect, fillPaint)
            canvas.drawRect(rect, strokePaint)
            dowPaint.color = Color.parseColor(if (c >= 5) "#93C5FD" else "#CBD5E1")
            canvas.drawText(dows[c], x + colW / 2f, y + dowH * 0.68f, dowPaint)
        }
        y += dowH

        var shiftCount = 0
        var totalMinutes = 0
        var morningCount = 0
        var eveningCount = 0
        var nightCount = 0

        var cursor = gridStart
        for (w in 0 until weekCount) {
            for (c in 0..6) {
                val date = cursor.plusDays(c.toLong())
                val inRange = !date.isBefore(startDate) && !date.isAfter(endDate)
                val isWeekend = (c == 5 || c == 6)
                val holidayName = if (showHolidays && inRange) FinnishHolidays.getHolidayName(date, en) else null
                val dayData = if (inRange) allDayMap[date] else null

                val x = tableLeft + c * colW
                val rect = RectF(x, y, x + colW, y + rowH)
                fillPaint.color = when {
                    !inRange -> Color.parseColor(UiStyleHelper.otherMonthCellHex(context))
                    holidayName != null -> Color.parseColor(UiStyleHelper.holidayCellHex(context))
                    isWeekend -> Color.parseColor(UiStyleHelper.weekendCellHex(context))
                    else -> cardColor
                }
                canvas.drawRect(rect, fillPaint)
                canvas.drawRect(rect, strokePaint)

                // Päivänumero
                dayNumPaint.color = when {
                    !inRange -> Color.parseColor("#475569")
                    holidayName != null -> Color.parseColor("#F87171")
                    isWeekend -> Color.parseColor("#93C5FD")
                    else -> Color.parseColor("#F1F5F9")
                }
                canvas.drawText(date.dayOfMonth.toString(), x + 10f, y + 28f, dayNumPaint)

                var itemY = y + 36f
                if (holidayName != null) {
                    smallPaint.color = Color.parseColor("#FCA5A5")
                    val clipped = clipText(holidayName, smallPaint, colW - 16f)
                    canvas.drawText(clipped, x + 8f, itemY + 14f, smallPaint)
                    itemY += 22f
                }

                // Poissaolot
                dayData?.absences?.take(1)?.forEach { absItem ->
                    val bgHex = when (absItem.kind) {
                        "vacation" -> "#15803D"
                        "sick" -> "#B91C1C"
                        else -> "#334155"
                    }
                    val badgeRect = RectF(x + 6f, itemY, x + colW - 6f, itemY + 30f)
                    fillPaint.color = Color.parseColor(bgHex)
                    canvas.drawRoundRect(badgeRect, 8f, 8f, fillPaint)
                    smallPaint.color = Color.WHITE
                    val clipped = clipText(absItem.title, smallPaint, colW - 20f)
                    canvas.drawText(clipped, x + 10f, itemY + 21f, smallPaint)
                    itemY += 34f
                }

                // Työvuorot
                dayData?.shifts?.take(2)?.forEach { shift ->
                    shiftCount++
                    val dur = if (shift.endMinutes >= shift.startMinutes) {
                        shift.endMinutes - shift.startMinutes
                    } else {
                        (24 * 60 - shift.startMinutes) + shift.endMinutes
                    }
                    totalMinutes += dur
                    val crossesMidnight = shift.endMinutes < shift.startMinutes
                    val bgRgb = when {
                        crossesMidnight || shift.startMinutes >= 20 * 60 || shift.startMinutes < 4 * 60 -> {
                            nightCount++
                            nightRgb
                        }
                        shift.startMinutes >= 11 * 60 + 30 -> {
                            eveningCount++
                            eveningRgb
                        }
                        else -> {
                            morningCount++
                            morningRgb
                        }
                    }
                    val lum = 0.299 * Color.red(bgRgb) + 0.587 * Color.green(bgRgb) + 0.114 * Color.blue(bgRgb)
                    val fg = if (lum > 150.0) Color.parseColor("#0F1722") else Color.WHITE

                    val badgeH = 54f
                    val badgeRect = RectF(x + 6f, itemY, x + colW - 6f, (itemY + badgeH).coerceAtMost(y + rowH - 6f))
                    fillPaint.color = bgRgb
                    canvas.drawRoundRect(badgeRect, 8f, 8f, fillPaint)
                    badgeTextPaint.color = fg
                    canvas.drawText(shift.startText, x + colW / 2f, itemY + 23f, badgeTextPaint)
                    canvas.drawText(shift.endText, x + colW / 2f, itemY + 46f, badgeTextPaint)
                    itemY += badgeH + 6f
                }
            }
            y += rowH
            cursor = cursor.plusWeeks(1)
        }

        // Alakooste
        val footerRect = RectF(tableLeft, y + 14f, tableLeft + tableWidth, y + footerH - 4f)
        fillPaint.color = cardColor
        canvas.drawRoundRect(footerRect, 14f, 14f, fillPaint)
        canvas.drawRoundRect(footerRect, 14f, 14f, strokePaint)

        val summaryPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#E2E8F0")
            textSize = 23f
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            textAlign = Paint.Align.CENTER
        }
        val summaryText = if (shiftCount > 0) {
            val hoursStr = formatHours(totalMinutes, en)
            val word = if (en) (if (shiftCount == 1) "shift" else "shifts") else (if (shiftCount == 1) "vuoro" else "vuoroa")
            val parts = mutableListOf<String>()
            if (morningCount > 0) parts.add(if (en) "$morningCount morn" else "$morningCount aamu")
            if (eveningCount > 0) parts.add(if (en) "$eveningCount eve" else "$eveningCount ilta")
            if (nightCount > 0) parts.add(if (en) "$nightCount night" else "$nightCount yö")
            val breakdown = if (parts.isNotEmpty()) "  •  ${parts.joinToString(" / ")}" else ""
            "$shiftCount $word • $hoursStr h$breakdown"
        } else {
            if (en) "No scheduled shifts" else "Ei merkittyjä vuoroja"
        }
        canvas.drawText(summaryText, width / 2f, y + 58f, summaryPaint)

        return bitmap
    }

    private fun clipText(text: String, paint: Paint, maxWidth: Float): String {
        if (paint.measureText(text) <= maxWidth) return text
        var end = text.length
        while (end > 1 && paint.measureText(text.substring(0, end) + "…") > maxWidth) {
            end--
        }
        return text.substring(0, end) + "…"
    }

    fun formatHours(totalMinutes: Int, en: Boolean): String {
        return if (totalMinutes % 60 == 0) {
            "${totalMinutes / 60}"
        } else {
            String.format("%.1f", totalMinutes / 60.0).replace(".", if (en) "." else ",")
        }
    }
}
