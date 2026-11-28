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
        srl.setProgressBackgroundColorSchemeColor(Color.parseColor("#182332"))
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
