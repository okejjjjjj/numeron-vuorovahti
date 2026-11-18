#!/usr/bin/env python3
import pathlib
import re
import sys

def find_file(candidates):
    for c in candidates:
        p = pathlib.Path(c)
        if p.exists():
            return p
    return None

def main():
    main_act_path = find_file([
        "app/src/main/java/fi/numeron/vuorovahti/MainActivity.kt",
        "MainActivity.kt",
        "MainActivity.kt.txt"
    ])
    if not main_act_path:
        print("Virhe: MainActivity.kt-tiedostoa ei löytynyt.", file=sys.stderr)
        sys.exit(1)

    content = main_act_path.read_text(encoding="utf-8")
    original = content

    # 1. Lisätään dashboardRedirectCount-laskuri ikuisten uudelleenohjausten estämiseksi
    if "dashboardRedirectCount" not in content:
        tab_anchor = "    private var currentTab: Tab = Tab.STAMP"
        if tab_anchor in content:
            content = content.replace(
                tab_anchor,
                tab_anchor + "\n    private var dashboardRedirectCount: Int = 0",
                1
            )

    # 2. Lisätään resolveResumeUrl-apufunktio, joka päättelee oikean kohdesivun
    # (keskeneräinen leimaus, kalenterisynkronointi tai aktiivinen välilehti)
    resume_helper = """
    private fun resolveResumeUrl(baseUrl: String): String {
        return when {
            pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT -> "$baseUrl/WorktimeStamping"
            pendingAction == Action.SYNC_CALENDAR -> "$baseUrl/Calendar/Month"
            currentTab == Tab.REQUESTS -> "$baseUrl/PersonRequests/List"
            currentTab == Tab.SHIFTS -> "$baseUrl/Calendar/Month"
            else -> "$baseUrl/WorktimeStamping"
        }
    }
"""
    if "private fun resolveResumeUrl(" not in content:
        base_url_anchor = "    private fun getBaseUrl(): String {"
        if base_url_anchor in content:
            content = content.replace(
                base_url_anchor,
                resume_helper + "\n" + base_url_anchor,
                1
            )

    # 3. Päivitetään handleWebSessionExpired käyttämään resolveResumeUrl-funktiota
    old_recovery_target = """                    val targetUrl = if (pendingAction == Action.STAMP_IN || pendingAction == Action.STAMP_OUT) {
                        "$baseUrl/WorktimeStamping"
                    } else {
                        webView.url ?: "$baseUrl/WorktimeStamping"
                    }"""
    new_recovery_target = "                    val targetUrl = resolveResumeUrl(baseUrl)"
    if old_recovery_target in content:
        content = content.replace(old_recovery_target, new_recovery_target, 1)

    # 4. Nollataan dashboardRedirectCount kun saavutaan varsinaiselle kohdesivulle
    old_session_ts_block = """                if (!url.contains("/Login/", ignoreCase = true)) {
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                }"""
    new_session_ts_block = """                if (!url.contains("/Login/", ignoreCase = true) && !url.contains("/InfraDashboard", ignoreCase = true)) {
                    dashboardRedirectCount = 0
                }
                if (!url.contains("/Login/", ignoreCase = true)) {
                    getSharedPreferences("NumeronPrefs", Context.MODE_PRIVATE)
                        .edit()
                        .putLong("last_valid_session_ms", System.currentTimeMillis())
                        .apply()
                }"""
    if "dashboardRedirectCount = 0" not in content and old_session_ts_block in content:
        content = content.replace(old_session_ts_block, new_session_ts_block, 1)

    # 5. Lisätään InfraDashboard / InfraDashboardNew.aspx -ohjaus onPageFinished-metodiin
    dashboard_branch = """                    url.contains("/InfraDashboard", ignoreCase = true) -> {
                        val baseUrl = getBaseUrl()
                        if (baseUrl.isNotEmpty() && dashboardRedirectCount < 3) {
                            dashboardRedirectCount++
                            startSnapshotTransition()
                            webView.loadUrl(resolveResumeUrl(baseUrl))
                            return
                        }
                    }
"""
    stamping_branch_anchor = '                    url.contains("/WorktimeStamping", ignoreCase = true) -> {'
    if 'url.contains("/InfraDashboard"' not in content and stamping_branch_anchor in content:
        content = content.replace(
            stamping_branch_anchor,
            dashboard_branch + stamping_branch_anchor,
            1
        )

    if content != original:
        main_act_path.write_text(content, encoding="utf-8")
        print(f"Päivitetty onnistuneesti (InfraDashboardNew-uudelleenohjaus): {main_act_path}")
    else:
        print("Ei muutoksia tehtävänä tai korjaus oli jo lisätty.")

    # 6. Nostetaan versionCode yhdellä pykälällä
    gradle_path = find_file([
        "app/build.gradle.kts",
        "app/build.gradle",
        "build.gradle.kts",
        "build.gradle.kts.txt"
    ])
    if gradle_path:
        g_content = gradle_path.read_text(encoding="utf-8")
        vc_match = re.search(r'versionCode\s*=\s*(\d+)', g_content)
        if vc_match:
            old_code = int(vc_match.group(1))
            new_code = old_code + 1
            g_content = g_content.replace(f"versionCode = {old_code}", f"versionCode = {new_code}", 1)
            gradle_path.write_text(g_content, encoding="utf-8")
            print(f"Nostettu versionCode: {old_code} -> {new_code} ({gradle_path})")

if __name__ == "__main__":
    main()
