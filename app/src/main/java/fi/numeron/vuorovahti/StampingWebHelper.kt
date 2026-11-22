package fi.numeron.vuorovahti

import org.json.JSONObject
import org.json.JSONTokener

/**
 * Jaettu JS- ja tilantarkistuslogiikka MainActivitylle ja QuickStampActivitylle.
 */
object StampingWebHelper {

    fun buildClickStampJs(wantIn: Boolean): String {
        val expectedDir = if (wantIn) "IN" else "OUT"
        val wordPattern = if (wantIn) {
            "(?:^|[^a-zäöå])(sisään|in)(?:$|[^a-zäöå])"
        } else {
            "(?:^|[^a-zäöå])(ulos|out)(?:$|[^a-zäöå])"
        }
        return """
        (function() {
            var btn = document.getElementById('punchButton');
            if (!btn) return JSON.stringify({ status: 'NO_BUTTON' });
            var btnText = (btn.innerText || btn.textContent || '').trim();
            if (!btnText) return JSON.stringify({ status: 'NO_BUTTON' });

            var dirEl = document.querySelector('[data-next-stamp-direction]');
            var nextDir = dirEl ? (dirEl.getAttribute('data-next-stamp-direction') || '').trim().toUpperCase() : '';

            var firstRow = '';
            var firstRowId = '';
            var rowEl = document.querySelector('#table-latest-stamps tbody tr, #table-latest-stamps tr');
            if (rowEl) {
                firstRow = (rowEl.innerText || rowEl.textContent || '').replace(/\s+/g, ' ').trim();
                var idInput = rowEl.querySelector('input[name^="RowID_"]');
                if (idInput && idInput.value) firstRowId = String(idInput.value).trim();
            }

            var matchesDir = false;
            if (nextDir === 'IN' || nextDir === 'OUT') {
                matchesDir = (nextDir === '$expectedDir');
            } else {
                var rx = new RegExp('$wordPattern', 'i');
                matchesDir = rx.test(btnText);
            }

            if (matchesDir) {
                btn.click();
                return JSON.stringify({ status: 'CLICKED', dir: nextDir, btn: btnText, row: firstRow, rowId: firstRowId });
            } else {
                return JSON.stringify({ status: 'WRONG_DIRECTION', dir: nextDir, btn: btnText, row: firstRow, rowId: firstRowId });
            }
        })();
        """.trimIndent()
    }

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
            var dirEl = document.querySelector('[data-next-stamp-direction]');
            var nextDir = dirEl ? (dirEl.getAttribute('data-next-stamp-direction') || '').trim().toUpperCase() : '';
            var btn = document.getElementById('punchButton');
            var btnText = btn ? (btn.innerText || btn.textContent || '').trim() : '';
            var firstRow = '';
            var firstRowId = '';
            var rowEl = document.querySelector('#table-latest-stamps tbody tr, #table-latest-stamps tr');
            if (rowEl) {
                firstRow = (rowEl.innerText || rowEl.textContent || '').replace(/\s+/g, ' ').trim();
                var idInput = rowEl.querySelector('input[name^="RowID_"]');
                if (idInput && idInput.value) firstRowId = String(idInput.value).trim();
            }
            return JSON.stringify({ dir: nextDir, btn: btnText, row: firstRow, rowId: firstRowId, expired: expired });
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
        wantIn: Boolean,
        beforeDir: String,
        beforeBtn: String,
        beforeRow: String,
        beforeRowId: String,
        nowDir: String,
        nowBtn: String,
        nowRow: String,
        nowRowId: String
    ): Boolean {
        val oppositeDir = if (wantIn) "OUT" else "IN"
        val dirFlipped = nowDir.equals(oppositeDir, ignoreCase = true) &&
            !nowDir.equals(beforeDir, ignoreCase = true)
        val rowIdChanged = nowRowId.isNotEmpty() && nowRowId != beforeRowId
        val targetRegex = if (wantIn) {
            Regex("(?:^|[^a-zäöå])(sisään|in)(?:$|[^a-zäöå])", RegexOption.IGNORE_CASE)
        } else {
            Regex("(?:^|[^a-zäöå])(ulos|out)(?:$|[^a-zäöå])", RegexOption.IGNORE_CASE)
        }
        val buttonFlipped = nowBtn.isNotEmpty() && nowBtn != beforeBtn && !targetRegex.containsMatchIn(nowBtn)
        val rowUpdated = nowRow.isNotEmpty() && nowRow != beforeRow
        return dirFlipped || rowIdChanged || buttonFlipped || rowUpdated
    }
}
