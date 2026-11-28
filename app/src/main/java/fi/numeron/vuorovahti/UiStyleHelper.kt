package fi.numeron.vuorovahti

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.LayerDrawable
import android.graphics.drawable.RippleDrawable
import android.util.TypedValue
import android.view.Gravity
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

object UiStyleHelper {

    fun isAmoled(context: Context): Boolean {
        return context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
            .getBoolean("amoled_black_theme", false)
    }

    fun bgHex(context: Context): String = if (isAmoled(context)) "#000000" else "#0F1722"
    fun barHex(context: Context): String = if (isAmoled(context)) "#000000" else "#0B111A"
    fun cardHex(context: Context): String = if (isAmoled(context)) "#0B0E14" else "#182332"
    fun cardAltHex(context: Context): String = if (isAmoled(context)) "#05070A" else "#111923"
    fun headerCellHex(context: Context): String = if (isAmoled(context)) "#111722" else "#233040"
    fun weekendHeaderHex(context: Context): String = if (isAmoled(context)) "#0E1624" else "#1E2B3D"
    fun borderHex(context: Context): String = if (isAmoled(context)) "#1F2937" else "#2A394A"
    fun borderStrongHex(context: Context): String = if (isAmoled(context)) "#2B384A" else "#37475A"
    fun weekendCellHex(context: Context): String = if (isAmoled(context)) "#080C12" else "#15202E"
    fun pastCellHex(context: Context): String = if (isAmoled(context)) "#040608" else "#121A24"
    fun pastWeekendCellHex(context: Context): String = if (isAmoled(context)) "#06090E" else "#111924"
    fun otherMonthCellHex(context: Context): String = if (isAmoled(context)) "#020304" else "#101720"
    fun weekColHex(context: Context): String = if (isAmoled(context)) "#06080C" else "#131C28"
    fun periodBarStartHex(context: Context): String = if (isAmoled(context)) "#0C1522" else "#162436"
    fun periodBarMidHex(context: Context): String = if (isAmoled(context)) "#070B12" else "#121B28"
    fun holidayCellHex(context: Context): String = if (isAmoled(context)) "#190B0E" else "#241822"
    fun todayCellHex(context: Context): String = if (isAmoled(context)) "#102844" else "#1E3A5F"

    fun dp(context: Context, value: Int): Int {
        return TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP,
            value.toFloat(),
            context.resources.displayMetrics
        ).toInt()
    }

    fun dpF(context: Context, value: Float): Float {
        return TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP,
            value,
            context.resources.displayMetrics
        )
    }

    fun roundedBg(
        context: Context,
        fillHex: String,
        strokeHex: String,
        radiusDp: Float,
        strokeWidthDp: Int = 1
    ): GradientDrawable {
        return GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = dpF(context, radiusDp)
            setColor(Color.parseColor(fillHex))
            if (strokeWidthDp > 0) {
                setStroke(dp(context, strokeWidthDp), Color.parseColor(strokeHex))
            }
        }
    }

    fun rippleRoundedBg(
        context: Context,
        fillHex: String,
        strokeHex: String,
        radiusDp: Float,
        rippleHex: String = "#3338BDF8",
        strokeWidthDp: Int = 1
    ): Drawable {
        val content = roundedBg(context, fillHex, strokeHex, radiusDp, strokeWidthDp)
        val mask = GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = dpF(context, radiusDp)
            setColor(Color.WHITE)
        }
        return RippleDrawable(ColorStateList.valueOf(Color.parseColor(rippleHex)), content, mask)
    }

    fun rippleTransparentBg(
        context: Context,
        radiusDp: Float = 8f,
        rippleHex: String = "#2A38BDF8"
    ): Drawable {
        val mask = GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = dpF(context, radiusDp)
            setColor(Color.WHITE)
        }
        return RippleDrawable(ColorStateList.valueOf(Color.parseColor(rippleHex)), null, mask)
    }

    fun cellBg(
        context: Context,
        fillHex: String,
        strokeHex: String,
        leftAccentHex: String? = null
    ): Drawable {
        val base = GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            setColor(Color.parseColor(fillHex))
            setStroke(1, Color.parseColor(strokeHex))
        }
        if (leftAccentHex == null) return base
        val accent = GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            setColor(Color.parseColor(leftAccentHex))
        }
        return LayerDrawable(arrayOf(base, accent)).apply {
            setLayerWidth(1, dp(context, 3))
            setLayerGravity(1, Gravity.START or Gravity.FILL_VERTICAL)
        }
    }

    fun rippleCellBg(
        context: Context,
        fillHex: String,
        strokeHex: String,
        rippleHex: String = "#2638BDF8"
    ): Drawable {
        val base = GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            setColor(Color.parseColor(fillHex))
            setStroke(1, Color.parseColor(strokeHex))
        }
        val mask = GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            setColor(Color.WHITE)
        }
        return RippleDrawable(ColorStateList.valueOf(Color.parseColor(rippleHex)), base, mask)
    }

    fun configureSwipeRefresh(srl: SwipeRefreshLayout) {
        srl.setProgressBackgroundColorSchemeColor(Color.parseColor(cardHex(srl.context)))
        srl.setColorSchemeColors(
            Color.parseColor("#38BDF8"),
            Color.parseColor("#22C55E")
        )
    }

    fun formatUpdatedLabel(context: Context, savedAtMs: Long, isCache: Boolean): String {
        if (savedAtMs <= 0L) return ""
        val en = DemoModeHelper.isEnglish(context)
        val zone = ZoneId.systemDefault()
        val dt = Instant.ofEpochMilli(savedAtMs).atZone(zone).toLocalDateTime()
        val timePart = if (dt.toLocalDate() == LocalDate.now()) {
            dt.format(DateTimeFormatter.ofPattern("HH:mm"))
        } else {
            dt.format(DateTimeFormatter.ofPattern("dd.MM. HH:mm"))
        }
        return if (isCache) {
            if (en) "Cached $timePart" else "Välimuisti $timePart"
        } else {
            if (en) "Updated $timePart" else "Päivitetty $timePart"
        }
    }
}
