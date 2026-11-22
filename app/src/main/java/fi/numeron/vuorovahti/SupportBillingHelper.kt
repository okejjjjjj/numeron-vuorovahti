package fi.numeron.vuorovahti

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

    @Volatile
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
        if (billingClient.connectionState == BillingClient.ConnectionState.CONNECTING) {
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

        // Play Billing Library 8.0.0 palauttaa QueryProductDetailsResult-olion
        billingClient.queryProductDetailsAsync(params) { billingResult, queryProductDetailsResult ->
            if (isDestroyed) return@queryProductDetailsAsync
            val productDetailsList = queryProductDetailsResult.productDetailsList
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
            BillingClient.BillingResponseCode.ITEM_ALREADY_OWNED -> {
                consumeUnfinishedPurchases()
                postStatus("Keskeneräinen tuki vahvistetaan – voit tukea uudelleen hetken kuluttua.", true)
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
                } else {
                    postStatus("Tuki rekisteröitiin, mutta kuittaus viivästyi (koodi ${billingResult.responseCode}).", false)
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
            if (billingClient.connectionState != BillingClient.ConnectionState.CLOSED) {
                billingClient.endConnection()
            }
        } catch (_: Exception) {
        }
    }
}
