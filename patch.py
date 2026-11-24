#!/usr/bin/env python3
"""
Numeron Vuorovahti – asetussivun versiotieto, Play-päivityskehotus ja tietoturvaselosteen linkki.
Toimii sekä puhtaalle pohjalle että päivittämään aiemmin asetetun PRIVACY_POLICY_URL-osoitteen.

Käyttö:
    python3 patch.py --dry-run
    python3 patch.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

IGNORED_DIRS = {".git", ".gradle", ".idea", "build", "node_modules", ".patch_backups", "__pycache__"}
DEFAULT_PRIVACY_URL = "https://github.com/okejjjjjj/numeron-vuorovahti/blob/main/privacy.md"


def find_file(root: Path, filename: str, must_contain: str | None = None) -> Path:
    matches: list[Path] = []
    for p in root.rglob(filename):
        if any(part in IGNORED_DIRS for part in p.parts):
            continue
        if must_contain is None or must_contain in p.read_text(encoding="utf-8", errors="ignore"):
            matches.append(p)
    if len(matches) != 1:
        raise RuntimeError(
            f"Odotettiin täsmälleen yhtä '{filename}'-tiedostoa, löytyi {len(matches)}: {matches}"
        )
    return matches[0]


def replace_once(content: str, old: str, new: str, label: str) -> str:
    count = content.count(old)
    if count != 1:
        raise RuntimeError(
            f"[{label}] Odotettiin 1 osumaa, löytyi {count}. Tarkista tiedoston versio."
        )
    return content.replace(old, new, 1)


def bump_version(text: str) -> str:
    m_code = re.search(r"versionCode\s*=\s*(\d+)", text)
    if not m_code:
        raise RuntimeError("[build.gradle:versionCode] versionCode-määritystä ei löytynyt.")
    old_code = int(m_code.group(1))
    text = text[: m_code.start()] + f"versionCode = {old_code + 1}" + text[m_code.end() :]

    m_name = re.search(r'versionName\s*=\s*"(\d+)\.(\d+)\.(\d+)"', text)
    if not m_name:
        raise RuntimeError("[build.gradle:versionName] versionName-määritystä ei löytynyt.")
    major, minor, patch = int(m_name.group(1)), int(m_name.group(2)), int(m_name.group(3))
    new_name = f"{major}.{minor}.{patch + 1}"
    text = text[: m_name.start()] + f'versionName = "{new_name}"' + text[m_name.end() :]
    print(
        f"  Versio päivitetty: {old_code} -> {old_code + 1}, "
        f"{m_name.group(1)}.{m_name.group(2)}.{m_name.group(3)} -> {new_name}"
    )
    return text


def patch_build_gradle(text: str) -> str:
    text = bump_version(text)
    if "com.google.android.play:app-update" not in text:
        updated, count = re.subn(
            r'^([ \t]*)(implementation\("com\.android\.billingclient:billing:[^"]+"\))',
            r'\1\2\n\1implementation("com.google.android.play:app-update:2.1.0")',
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if count != 1:
            raise RuntimeError("[build.gradle:add_app_update_dep] billing-riippuvuusriviä ei löytynyt.")
        text = updated
    return text


def make_settings_patcher(privacy_url: str):
    escaped_url = privacy_url.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")

    def patch_settings_dialog_helper(text: str) -> str:
        # Jos aiempi patch on jo ajettu, päivitetään pelkkä tietoturvaselosteen osoite
        if "const val PRIVACY_POLICY_URL =" in text:
            updated, count = re.subn(
                r'const val PRIVACY_POLICY_URL\s*=\s*"[^"]*"',
                'const val PRIVACY_POLICY_URL = "' + escaped_url + '"',
                text,
                count=1,
            )
            if count != 1:
                raise RuntimeError(
                    "[SettingsDialogHelper:update_privacy_url] PRIVACY_POLICY_URL-riviä ei voitu päivittää."
                )
            return updated

        old_header = (
            "object SettingsDialogHelper {\n\n"
            "    val SHIFT_COLOR_CHOICES = listOf("
        )
        new_header = (
            "object SettingsDialogHelper {\n\n"
            '    const val PRIVACY_POLICY_URL = "' + escaped_url + '"\n\n'
            "    val SHIFT_COLOR_CHOICES = listOf("
        )
        text = replace_once(
            text,
            old_header,
            new_header,
            "SettingsDialogHelper:privacy_url_const",
        )

        text = replace_once(
            text,
            '''        fun launchSystemSettingsIntent(intent: android.content.Intent): Boolean {
            return try {
                if (context !is android.app.Activity) {
                    intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                context.startActivity(intent)
                true
            } catch (_: Exception) {
                false
            }
        }''',
            '''        fun launchSystemSettingsIntent(intent: android.content.Intent): Boolean {
            return try {
                if (context !is android.app.Activity) {
                    intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                context.startActivity(intent)
                true
            } catch (_: Exception) {
                false
            }
        }

        fun openPlayStorePage() {
            val pkg = context.packageName
            val marketIntent = android.content.Intent(
                android.content.Intent.ACTION_VIEW,
                android.net.Uri.parse("market://details?id=$pkg")
            )
            if (!launchSystemSettingsIntent(marketIntent)) {
                launchSystemSettingsIntent(
                    android.content.Intent(
                        android.content.Intent.ACTION_VIEW,
                        android.net.Uri.parse("https://play.google.com/store/apps/details?id=$pkg")
                    )
                )
            }
        }

        fun openPrivacyPolicy() {
            val url = PRIVACY_POLICY_URL.trim()
            val isConfigured = url.startsWith("https://") || url.startsWith("http://")
            if (isConfigured) {
                val opened = launchSystemSettingsIntent(
                    android.content.Intent(
                        android.content.Intent.ACTION_VIEW,
                        android.net.Uri.parse(url)
                    )
                )
                if (!opened) {
                    android.widget.Toast.makeText(
                        context,
                        if (en) "Could not open browser" else "Selainta ei voitu avata",
                        android.widget.Toast.LENGTH_SHORT
                    ).show()
                }
            } else {
                android.widget.Toast.makeText(
                    context,
                    if (en) "Privacy policy URL is not configured yet" else "Tietoturvaselosteen osoitetta ei ole vielä määritetty",
                    android.widget.Toast.LENGTH_LONG
                ).show()
            }
        }

        // Korostettu päivityskehotus ylimmäksi, näytetään vain jos Play-kaupassa on uudempi versio
        val updateBanner = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            background = makeCardBg("#3B2810", "#F59E0B", 12)
            setPadding(dp(16), dp(14), dp(16), dp(14))
            visibility = View.GONE
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                bottomMargin = dp(14)
            }
        }
        updateBanner.addView(TextView(context).apply {
            text = if (en) "UPDATE AVAILABLE" else "PÄIVITYS SAATAVILLA"
            textSize = 11f
            letterSpacing = 0.06f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#FBBF24"))
        })
        val updateBannerSubTv = TextView(context).apply {
            text = if (en) {
                "Your app version is outdated. Update to the latest version from Google Play."
            } else {
                "Käytössäsi ei ole uusin versio. Suosittelemme päivittämään sovelluksen Google Playsta."
            }
            textSize = 13f
            setTextColor(Color.parseColor("#FEF3C7"))
            setPadding(0, dp(4), 0, dp(8))
        }
        updateBanner.addView(updateBannerSubTv)
        val btnBannerUpdate = Button(context).apply {
            text = if (en) "Update on Google Play" else "Päivitä Google Playsta"
            styleButton(this, "#D97706", "#FBBF24", "#FFFFFF")
            (layoutParams as? LinearLayout.LayoutParams)?.topMargin = dp(2)
            setOnClickListener { openPlayStorePage() }
        }
        updateBanner.addView(btnBannerUpdate)
        layout.addView(updateBanner, 0)''',
            "SettingsDialogHelper:update_banner_and_links",
        )

        text = replace_once(
            text,
            '''        authCard.addView(TextView(context).apply {
            text = if (en) {
                "Credentials are stored only on your device and sent solely to the Numeron address you enter. They are never shared with third parties or external servers."
            } else {
                "Tunnukset tallennetaan vain laitteellesi ja välitetään ainoastaan antamaasi Numeron-osoitteeseen. Niitä ei tallenneta tai jaeta ulkopuolisille palvelimille."
            }
            textSize = 11f
            setTextColor(Color.parseColor("#64748B"))
            setPadding(0, dp(8), 0, dp(2))
        })''',
            '''        authCard.addView(TextView(context).apply {
            text = if (en) {
                "Credentials are stored only on your device and sent solely to the Numeron address you enter. They are never shared with third parties or external servers."
            } else {
                "Tunnukset tallennetaan vain laitteellesi ja välitetään ainoastaan antamaasi Numeron-osoitteeseen. Niitä ei tallenneta tai jaeta ulkopuolisille palvelimille."
            }
            textSize = 11f
            setTextColor(Color.parseColor("#64748B"))
            setPadding(0, dp(8), 0, dp(4))
        })
        authCard.addView(TextView(context).apply {
            text = if (en) "Read privacy policy →" else "Lue tietoturvaseloste →"
            textSize = 12.5f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.parseColor("#38BDF8"))
            paintFlags = paintFlags or android.graphics.Paint.UNDERLINE_TEXT_FLAG
            setPadding(0, dp(4), 0, dp(4))
            setOnClickListener { openPrivacyPolicy() }
        })''',
            "SettingsDialogHelper:authCard_privacy_link",
        )

        text = replace_once(
            text,
            '''        billingHelper.startConnection()

        // Alapalkki: Peruuta ja Tallenna''',
            '''        billingHelper.startConnection()

        // === KORTTI 6: TIETOJA JA TIETOTURVA ===
        val aboutCard = createSectionCard(if (en) "About and privacy" else "Tietoja ja tietoturva")

        val (installedVersionName, installedVersionCode) = try {
            val pInfo = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
                context.packageManager.getPackageInfo(
                    context.packageName,
                    PackageManager.PackageInfoFlags.of(0)
                )
            } else {
                @Suppress("DEPRECATION")
                context.packageManager.getPackageInfo(context.packageName, 0)
            }
            val vCode = androidx.core.content.pm.PackageInfoCompat.getLongVersionCode(pInfo)
            (pInfo.versionName ?: "?") to vCode
        } catch (_: Exception) {
            "?" to 0L
        }

        val (_, versionSubTv) = addStatusRow(
            aboutCard,
            if (en) "App version" else "Sovelluksen versio",
            "v$installedVersionName ($installedVersionCode)",
            if (en) "Checking for updates..." else "Tarkistetaan päivityksiä..."
        )
        aboutCard.getChildAt(aboutCard.childCount - 1).setOnClickListener {
            openPlayStorePage()
        }

        val btnUpdateApp = Button(context).apply {
            text = if (en) "Update to latest version (Google Play)" else "Päivitä uusimpaan versioon (Google Play)"
            styleButton(this, "#D97706", "#FBBF24", "#FFFFFF")
            visibility = View.GONE
            setOnClickListener { openPlayStorePage() }
        }
        aboutCard.addView(btnUpdateApp)

        val btnPrivacyPolicy = Button(context).apply {
            text = if (en) "Privacy policy" else "Tietoturvaseloste"
            styleButton(this, "#233040", "#37475A", "#38BDF8")
            setOnClickListener { openPrivacyPolicy() }
        }
        aboutCard.addView(btnPrivacyPolicy)

        var isDialogDismissed = false

        fun checkForAppUpdate() {
            try {
                val appUpdateManager = com.google.android.play.core.appupdate.AppUpdateManagerFactory.create(
                    context.applicationContext
                )
                appUpdateManager.appUpdateInfo
                    .addOnSuccessListener { info ->
                        val act = context as? android.app.Activity
                        if (isDialogDismissed || (act != null && (act.isFinishing || act.isDestroyed))) {
                            return@addOnSuccessListener
                        }
                        val availability = info.updateAvailability()
                        val updateAvailable =
                            availability == com.google.android.play.core.install.model.UpdateAvailability.UPDATE_AVAILABLE ||
                            availability == com.google.android.play.core.install.model.UpdateAvailability.DEVELOPER_TRIGGERED_UPDATE_IN_PROGRESS

                        if (updateAvailable) {
                            val availCode = info.availableVersionCode()
                            updateBanner.visibility = View.VISIBLE
                            updateBannerSubTv.text = if (en) {
                                "A newer version (build $availCode) is available on Google Play. Please update for the latest fixes."
                            } else {
                                "Uudempi versio (koontiversio $availCode) on saatavilla Google Playssa. Päivitä sovellus saadaksesi uusimmat korjaukset."
                            }
                            versionSubTv.text = if (en) {
                                "Outdated – update available (build $availCode)"
                            } else {
                                "Vanhentunut – uusi versio saatavilla (koontiversio $availCode)"
                            }
                            versionSubTv.setTextColor(Color.parseColor("#FBBF24"))
                            versionSubTv.visibility = View.VISIBLE
                            btnUpdateApp.visibility = View.VISIBLE
                        } else {
                            versionSubTv.text = if (en) "Up to date" else "Sovellus on ajan tasalla"
                            versionSubTv.setTextColor(Color.parseColor("#34D399"))
                            versionSubTv.visibility = View.VISIBLE
                        }
                    }
                    .addOnFailureListener {
                        val act = context as? android.app.Activity
                        if (isDialogDismissed || (act != null && (act.isFinishing || act.isDestroyed))) {
                            return@addOnFailureListener
                        }
                        versionSubTv.text = if (en) {
                            "Tap to check Google Play for updates"
                        } else {
                            "Napauta tarkistaaksesi päivitykset Google Playsta"
                        }
                        versionSubTv.setTextColor(Color.parseColor("#94A3B8"))
                        versionSubTv.visibility = View.VISIBLE
                    }
            } catch (_: Exception) {
                versionSubTv.text = if (en) {
                    "Tap to check Google Play for updates"
                } else {
                    "Napauta tarkistaaksesi päivitykset Google Playsta"
                }
                versionSubTv.setTextColor(Color.parseColor("#94A3B8"))
                versionSubTv.visibility = View.VISIBLE
            }
        }

        // Alapalkki: Peruuta ja Tallenna''',
            "SettingsDialogHelper:about_card_and_update_check",
        )

        text = replace_once(
            text,
            '''        dialog.setOnDismissListener {''',
            '''        dialog.setOnDismissListener {
            isDialogDismissed = true''',
            "SettingsDialogHelper:mark_dismissed",
        )

        text = replace_once(
            text,
            '''        dialog.show()''',
            '''        dialog.show()
        checkForAppUpdate()''',
            "SettingsDialogHelper:trigger_update_check",
        )
        return text

    return patch_settings_dialog_helper


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lisää asetussivulle sovelluksen versionumero, päivityskehotus ja tietoturvaselosteen linkki"
    )
    parser.add_argument("--root", default=".", help="Projektin juurikansio")
    parser.add_argument(
        "--privacy-url",
        default=DEFAULT_PRIVACY_URL,
        help="Julkinen HTTPS-osoite tietoturvaselosteeseen",
    )
    parser.add_argument("--dry-run", action="store_true", help="Tarkista muutokset kirjoittamatta tiedostoja")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    patch_plan = [
        ("build.gradle.kts", 'applicationId = "com.numeron_vuorovahti"', patch_build_gradle),
        ("SettingsDialogHelper.kt", "object SettingsDialogHelper", make_settings_patcher(args.privacy_url)),
    ]

    staged_writes: list[tuple[Path, str]] = []

    for filename, marker, patch_fn in patch_plan:
        path = find_file(root, filename, marker)
        raw_text = path.read_bytes().decode("utf-8")
        eol = "\r\n" if "\r\n" in raw_text else "\n"
        normalized = raw_text.replace("\r\n", "\n")

        patched = patch_fn(normalized)
        if patched == normalized:
            print(f"OK (jo ajan tasalla): {path.relative_to(root)}")
            continue

        staged_writes.append((path, patched.replace("\n", eol)))
        print(f"OK: {path.relative_to(root)}")

    if not staged_writes:
        print("\nKaikki tiedostot olivat jo ajan tasalla.")
        return 0

    if args.dry_run:
        print(f"\nDRY-RUN OK: {len(staged_writes)} tiedostoa valmiina, mitään ei kirjoitettu.")
        return 0

    for path, final_text in staged_writes:
        path.write_text(final_text, encoding="utf-8")

    print(f"\nVALMIS: {len(staged_writes)} tiedostoa päivitetty onnistuneesti.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"VIRHE: {exc}", file=sys.stderr)
        sys.exit(1)
