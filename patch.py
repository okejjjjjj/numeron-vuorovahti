#!/usr/bin/env python3
import pathlib
import re
import sys

BILLING_HELPER_KT = """package fi.numeron.vuorovahti

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.os.Handler
import android.os.Looper
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.BillingClientStateListener
import com.android.billingclient.api.BillingFlowParams
import com.android.billingclient.api.BillingResult
import com.android.billingclient.api.ConsumeParams
import com.android.billingclient.api.PendingPurchasesParams
import com.android.billingclient.api.ProductDetails
import com.android.billingclient.api.Purchase
import com.android.billingclient.api.PurchasesUpdatedListener
import com.android.billingclient.api.QueryProductDetailsParams
import com.android.billingclient.api.QueryPurchasesParams

class SupportBillingHelper(
    private val context: Context,
    private val onProductsLoaded: (List<ProductDetails>) -> Unit,
    private val onStatusMessage: (String, Boolean) -> Unit
) : PurchasesUpdatedListener {

    companion object {
        // Luo nämä kertaluonteiset kulutustuotteet (In-app products) Google Play Consolessa
        val TIP_PRODUCT_IDS = listOf(
            "vuorovahti_tip_small",
            "vuorovahti_tip_medium",
            "vuorovahti_tip_large"
        )
    }

    private val mainHandler = Handler(Looper.getMainLooper())
    private var isDestroyed = false

    private val billingClient: BillingClient = BillingClient.newBuilder(context)
        .setListener(this)
        .enablePendingPurchases(
            PendingPurchasesParams.newBuilder()
                .enableOneTimeProducts()
                .build()
        )
        .build()

    fun startConnection() {
        if (isDestroyed) return
        if (billingClient.isReady) {
            queryTipProducts()
            return
        }

        billingClient.startConnection(object : BillingClientStateListener {
            override fun onBillingSetupFinished(billingResult: BillingResult) {
                if (isDestroyed) return
                if (billingResult.responseCode == BillingClient.BillingResponseCode.OK) {
                    queryTipProducts()
                    consumeUnfinishedPurchases()
                } else {
                    postStatus(
                        "Google Play -laskutus ei ole käytettävissä tässä asennuksessa.",
                        false
                    )
                }
            }

            override fun onBillingServiceDisconnected() {
                // Yhteys muodostetaan uudelleen tarvittaessa käyttäjän painaessa nappia
            }
        })
    }

    private fun queryTipProducts() {
        val productList = TIP_PRODUCT_IDS.map { productId ->
            QueryProductDetailsParams.Product.newBuilder()
                .setProductId(productId)
                .setProductType(BillingClient.ProductType.INAPP)
                .build()
        }

        val params = QueryProductDetailsParams.newBuilder()
            .setProductList(productList)
            .build()

        billingClient.queryProductDetailsAsync(params) { billingResult, productDetailsList ->
            if (isDestroyed) return@queryProductDetailsAsync
            if (billingResult.responseCode == BillingClient.BillingResponseCode.OK && productDetailsList.isNotEmpty()) {
                val sorted = productDetailsList.sortedBy {
                    it.oneTimePurchaseOfferDetails?.priceAmountMicros ?: 0L
                }
                mainHandler.post {
                    if (!isDestroyed) {
                        onProductsLoaded(sorted)
                    }
                }
            } else {
                postStatus(
                    "Tukivaihtoehtoja ei löytynyt vielä Google Playsta.",
                    false
                )
            }
        }
    }

    fun launchPurchase(productDetails: ProductDetails) {
        val activity = findActivity(context)
        if (activity == null) {
            postStatus("Maksuikkunaa ei voitu avata.", false)
            return
        }
        if (!billingClient.isReady) {
            postStatus("Yhdistetään Google Playhin, yritä hetken kuluttua uudelleen.", false)
            startConnection()
            return
        }

        val productDetailsParams = BillingFlowParams.ProductDetailsParams.newBuilder()
            .setProductDetails(productDetails)
            .build()

        val flowParams = BillingFlowParams.newBuilder()
            .setProductDetailsParamsList(listOf(productDetailsParams))
            .build()

        billingClient.launchBillingFlow(activity, flowParams)
    }

    override fun onPurchasesUpdated(billingResult: BillingResult, purchases: MutableList<Purchase>?) {
        if (isDestroyed) return
        when (billingResult.responseCode) {
            BillingClient.BillingResponseCode.OK -> {
                purchases?.forEach { handlePurchase(it) }
            }
            BillingClient.BillingResponseCode.USER_CANCELED -> {
                // Käyttäjä peruutti maksun – ei näytetä virheilmoitusta
            }
            else -> {
                postStatus(
                    "Maksutapahtuma keskeytyi (koodi ${billingResult.responseCode}).",
                    false
                )
            }
        }
    }

    private fun handlePurchase(purchase: Purchase) {
        if (purchase.purchaseState == Purchase.PurchaseState.PURCHASED) {
            // Kulutetaan ostos heti, jotta tukeminen on mahdollista uudelleen myöhemmin
            // eikä Google Play palauta kuittaamatonta maksua automaattisesti
            val consumeParams = ConsumeParams.newBuilder()
                .setPurchaseToken(purchase.purchaseToken)
                .build()

            billingClient.consumeAsync(consumeParams) { billingResult, _ ->
                if (isDestroyed) return@consumeAsync
                if (billingResult.responseCode == BillingClient.BillingResponseCode.OK) {
                    postStatus("Lämmin kiitos tuestasi! ☕", true)
                }
            }
        } else if (purchase.purchaseState == Purchase.PurchaseState.PENDING) {
            postStatus("Maksu odottaa Google Playn vahvistusta...", false)
        }
    }

    private fun consumeUnfinishedPurchases() {
        val params = QueryPurchasesParams.newBuilder()
            .setProductType(BillingClient.ProductType.INAPP)
            .build()

        billingClient.queryPurchasesAsync(params) { billingResult, purchases ->
            if (billingResult.responseCode == BillingClient.BillingResponseCode.OK) {
                purchases.forEach { handlePurchase(it) }
            }
        }
    }

    private fun postStatus(message: String, isSuccess: Boolean) {
        mainHandler.post {
            if (!isDestroyed) {
                onStatusMessage(message, isSuccess)
            }
        }
    }

    private fun findActivity(ctx: Context): Activity? {
        var current: Context? = ctx
        while (current is ContextWrapper) {
            if (current is Activity) return current
            current = current.baseContext
        }
        return null
    }

    fun destroy() {
        isDestroyed = true
        try {
            if (billingClient.isReady) {
                billingClient.endConnection()
            }
        } catch (_: Exception) {
        }
    }
}
"""

def find_file(candidates):
    for c in candidates:
        p = pathlib.Path(c)
        if p.exists():
            return p
    return None

def main():
    settings_path = find_file([
        "app/src/main/java/fi/numeron/vuorovahti/SettingsDialogHelper.kt",
        "SettingsDialogHelper.kt",
        "SettingsDialogHelper.kt.txt"
    ])
    if not settings_path:
        print("Virhe: SettingsDialogHelper.kt-tiedostoa ei löytynyt.", file=sys.stderr)
        sys.exit(1)

    billing_helper_path = settings_path.parent / "SupportBillingHelper.kt"
    billing_helper_path.write_text(BILLING_HELPER_KT, encoding="utf-8")
    print(f"Luotu/päivitetty: {billing_helper_path}")

    s_content = settings_path.read_text(encoding="utf-8")
    s_original = s_content

    support_card_block = """        // === KORTTI 5: VAPAAEHTOINEN TUKI (GOOGLE PLAY BILLING) ===
        val supportCard = createSectionCard("Tue sovelluksen kehitystä")

        supportCard.addView(TextView(context).apply {
            text = "Vuorovahti on maksuton ja itsenäinen harrastusprojekti. Kaikki ominaisuudet ovat aina kaikkien käytössä. Halutessasi voit tukea kehitystä vapaaehtoisella kertamaksulla:"
            textSize = 12.5f
            setTextColor(Color.parseColor("#CBD5E1"))
            setPadding(0, 0, 0, dp(8))
        })

        val tvSupportStatus = TextView(context).apply {
            text = "Haetaan tukivaihtoehtoja Google Playsta..."
            textSize = 12f
            setTextColor(Color.parseColor("#94A3B8"))
            setPadding(0, dp(2), 0, dp(4))
        }
        supportCard.addView(tvSupportStatus)

        val tipButtonsContainer = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
        }
        supportCard.addView(tipButtonsContainer)

        lateinit var billingHelper: SupportBillingHelper

        val btnFallbackSupport = Button(context).apply {
            text = "☕ Tarjoa kehittäjälle kahvit"
            styleButton(this, "#1E3A5F", "#0284C7", "#E0F2FE")
            setOnClickListener {
                tvSupportStatus.setTextColor(Color.parseColor("#38BDF8"))
                tvSupportStatus.text = "Yhdistetään Google Playhin..."
                billingHelper.startConnection()
            }
        }
        tipButtonsContainer.addView(btnFallbackSupport)

        billingHelper = SupportBillingHelper(
            context = context,
            onProductsLoaded = { products ->
                tvSupportStatus.setTextColor(Color.parseColor("#94A3B8"))
                tvSupportStatus.text = "Valitse sopiva kertatuki (Google Play):"
                tipButtonsContainer.removeAllViews()

                val icons = listOf("☕", "🥐", "🍲")
                products.forEachIndexed { index, product ->
                    val price = product.oneTimePurchaseOfferDetails?.formattedPrice ?: ""
                    val title = product.name.ifBlank { "Tue kehitystä" }
                    val icon = icons.getOrElse(index) { "☕" }
                    val btnTier = Button(context).apply {
                        text = if (price.isNotEmpty()) "$icon $title — $price" else "$icon $title"
                        styleButton(this, "#1E3A5F", "#0284C7", "#E0F2FE")
                        setOnClickListener {
                            billingHelper.launchPurchase(product)
                        }
                    }
                    tipButtonsContainer.addView(btnTier)
                }
            },
            onStatusMessage = { msg, isSuccess ->
                tvSupportStatus.setTextColor(
                    Color.parseColor(if (isSuccess) "#10B981" else "#94A3B8")
                )
                tvSupportStatus.text = msg
            }
        )
        billingHelper.startConnection()
"""

    disclaimer_block = """        // Vastuuvapauslauseke
        layout.addView(TextView(context).apply {
            text = "Tämä on itsenäinen, epävirallinen kolmannen osapuolen asiakassovellus. Ei ole sidoksissa Vismaan tai Numeroniin."
            textSize = 11f
            setTextColor(Color.parseColor("#64748B"))
            gravity = Gravity.CENTER
            setPadding(dp(8), dp(4), dp(8), dp(8))
        })
"""

    anchor = "        actionCard.addView(btnTestNotif)"
    if "SupportBillingHelper" not in s_content and anchor in s_content:
        insertion = anchor + "\n\n" + support_card_block
        if "epävirallinen" not in s_content:
            insertion += "\n" + disclaimer_block
        s_content = s_content.replace(anchor, insertion, 1)

    if "billingHelper.destroy()" not in s_content and "        dialog.show()" in s_content:
        s_content = s_content.replace(
            "        dialog.show()",
            "        dialog.setOnDismissListener { billingHelper.destroy() }\n        dialog.show()",
            1
        )

    if s_content != s_original:
        settings_path.write_text(s_content, encoding="utf-8")
        print(f"Päivitetty onnistuneesti: {settings_path}")
    else:
        print("SettingsDialogHelper.kt oli jo päivitetty tai ankkurikohtaa ei löytynyt.")

    gradle_path = find_file([
        "app/build.gradle.kts",
        "app/build.gradle",
        "build.gradle.kts",
        "build.gradle.kts.txt"
    ])
    if gradle_path:
        g_content = gradle_path.read_text(encoding="utf-8")
        g_original = g_content

        billing_dep = '    implementation("com.android.billingclient:billing-ktx:7.1.1")'
        if "com.android.billingclient:billing" not in g_content:
            g_content = re.sub(
                r'(dependencies\s*\{[\s\S]*?)(\n\})',
                r'\1\n' + billing_dep + r'\2',
                g_content,
                count=1
            )

        match = re.search(r'versionCode\s*=\s*(\d+)', g_content)
        if match:
            old_code = int(match.group(1))
            new_code = old_code + 1
            g_content = g_content.replace(f"versionCode = {old_code}", f"versionCode = {new_code}", 1)
            print(f"Nostettu versionCode: {old_code} -> {new_code} ({gradle_path})")

        if g_content != g_original:
            gradle_path.write_text(g_content, encoding="utf-8")
            print(f"Päivitetty riippuvuudet: {gradle_path}")

if __name__ == "__main__":
    main()
