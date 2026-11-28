package fi.numeron.vuorovahti

import android.app.PendingIntent
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService

class QuickStampTileService : TileService() {

    override fun onStartListening() {
        super.onStartListening()
        updateTileAppearance()
    }

    override fun onClick() {
        super.onClick()
        val isEnding = resolveNextIsOut(this)
        val intent = Intent(this, QuickStampActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("AUTO_STAMP", true)
            putExtra("IS_ENDING", isEnding)
            putExtra("IS_TEST", false)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            val pi = PendingIntent.getActivity(
                this,
                7701,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            startActivityAndCollapse(pi)
        } else {
            @Suppress("DEPRECATION")
            startActivityAndCollapse(intent)
        }
    }

    private fun updateTileAppearance() {
        val tile = qsTile ?: return
        val en = DemoModeHelper.isEnglish(this)
        val isOutNext = resolveNextIsOut(this)
        val hasKnownState = hasKnownStampDirection(this)

        tile.label = when {
            !hasKnownState -> if (en) "Quick stamp" else "Pikaleimaus"
            isOutNext -> if (en) "Clock out" else "Leimaa ulos"
            else -> if (en) "Clock in" else "Leimaa sisään"
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            tile.subtitle = when {
                !hasKnownState -> "Vuorovahti"
                isOutNext -> if (en) "Clocked in" else "Töissä"
                else -> if (en) "Clocked out" else "Ulkona"
            }
        }
        tile.state = if (hasKnownState && isOutNext) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE
        tile.updateTile()
    }

    companion object {
        private fun hasKnownStampDirection(context: Context): Boolean {
            if (DemoModeHelper.isDemoEnabled(context)) return true
            val cached = NumeronApiClient.loadCachedStampingState(context)
            return cached != null && (cached.nextDirection == "IN" || cached.nextDirection == "OUT")
        }

        private fun resolveNextIsOut(context: Context): Boolean {
            if (DemoModeHelper.isDemoEnabled(context)) {
                return context.getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                    .getBoolean("demo_stamped_in", false)
            }
            val cached = NumeronApiClient.loadCachedStampingState(context)
            return cached?.nextDirection?.equals("OUT", ignoreCase = true) == true
        }

        fun requestTileUpdate(context: Context) {
            try {
                requestListeningState(
                    context.applicationContext,
                    ComponentName(context.applicationContext, QuickStampTileService::class.java)
                )
            } catch (_: Exception) {
            }
        }
    }
}
