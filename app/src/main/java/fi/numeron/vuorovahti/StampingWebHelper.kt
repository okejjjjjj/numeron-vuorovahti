package fi.numeron.vuorovahti

import org.json.JSONObject
import org.json.JSONTokener

/**
 * Jaettu JS- ja tilantarkistuslogiikka MainActivitylle ja QuickStampActivitylle.
 */
object StampingWebHelper {

    fun buildClickStampJs(targetLower: String): String = """
        (function() {
            var btn = document.getElementById('punchButton');
            if (!btn) return JSON.stringify({ status: 'NO_BUTTON' });
            var btnText = (btn.innerText || btn.textContent || '').trim();
            if (!btnText) return JSON.stringify({ status: 'NO_BUTTON' });
            var firstRow = '';
            var rowEl = document.querySelector('#table-latest-stamps tbody tr, #table-latest-stamps tr');
            if (rowEl) {
                firstRow = (rowEl.innerText || rowEl.textContent || '').replace(/\s+/g, ' ').trim();
            }
            if (btnText.toLowerCase().indexOf('$targetLower') !== -1) {
                btn.click();
                return JSON.stringify({ status: 'CLICKED', btn: btnText, row: firstRow });
            } else {
                return JSON.stringify({ status: 'WRONG_DIRECTION', btn: btnText, row: firstRow });
            }
        })();
    """.trimIndent()

    fun buildVerifyStampJs(): String = """
        (function() {
            var expired = false;
            var modals = document.querySelectorAll('#session-expired-modal, #sessionExpiredModal, #SessionExpiredModal, .modal, [role="dialog"]');
            for (var i = 0; i < modals.length; i++) {
                var m = modals[i];
                var st = window.getComputedStyle(m);
                var vis = (m.offsetParent !== null) || (st && st.display !== 'none' && st.visibility !== 'hidden');
                if (vis) {
                    var t = (m.innerText || m.textContent || '').toLowerCase();
                    if (m.id === 'session-expired-modal' || m.id === 'sessionExpiredModal' || t.indexOf('istunto vanhentunut') !== -1 || t.indexOf('session expired') !== -1) {
                        expired = true;
                        break;
                    }
                }
            }
            if (window.location.pathname.toLowerCase().indexOf('/login') !== -1) {
                expired = true;
            }
            var btn = document.getElementById('punchButton');
            var btnText = btn ? (btn.innerText || btn.textContent || '').trim() : '';
            var rowEl = document.querySelector('#table-latest-stamps tbody tr, #table-latest-stamps tr');
            var firstRow = rowEl ? (rowEl.innerText || rowEl.textContent || '').replace(/\s+/g, ' ').trim() : '';
            return JSON.stringify({ btn: btnText, row: firstRow, expired: expired });
        })();
    """.trimIndent()

    fun parseJsonResult(rawResult: String?): JSONObject? {
        return try {
            if (rawResult != null && rawResult != "null") {
                val unescaped = JSONTokener(rawResult).nextValue() as? String
                if (unescaped != null) JSONObject(unescaped) else null
            } else {
                null
            }
        } catch (_: Exception) {
            null
        }
    }

    fun isStampConfirmed(
        targetLower: String,
        beforeBtn: String,
        beforeRow: String,
        nowBtn: String,
        nowRow: String
    ): Boolean {
        val buttonFlipped = nowBtn.isNotEmpty() && nowBtn != beforeBtn &&
            nowBtn.lowercase().indexOf(targetLower) == -1
        val rowUpdated = nowRow.isNotEmpty() && nowRow != beforeRow
        return buttonFlipped || rowUpdated
    }
}
