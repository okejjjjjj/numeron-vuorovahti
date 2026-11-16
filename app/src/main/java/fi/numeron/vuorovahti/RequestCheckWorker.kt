package fi.numeron.vuorovahti

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.webkit.CookieManager
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class RequestCheckWorker(
    private val context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        const val CHANNEL_ID = "numeron_requests_channel"
        private const val PREFS_NAME = "numeron_request_statuses"
    }

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        if (DemoModeHelper.isDemoEnabled(context)) {
            return@withContext Result.success()
        }

        val baseUrl = UrlNormalizer.getSavedBaseUrl(context)
        if (baseUrl.isBlank()) {
            return@withContext Result.success()
        }

        try {
            var jsonText = fetchRequestsJson(baseUrl)

            // Jos eväste puuttuu tai 12 h istunto on katkennut, kirjaudu taustalla ja yritä uudelleen
            if (jsonText == null) {
                val loggedIn = BackgroundAuthHelper.ensureAuthenticatedSession(context)
                if (loggedIn) {
                    jsonText = fetchRequestsJson(baseUrl)
                }
            }

            if (jsonText == null) {
                return@withContext Result.success()
            }

            val json = JSONObject(jsonText)
            val dataArray = json.optJSONArray("data") ?: return@withContext Result.success()

            val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            val isFirstRun = prefs.all.isEmpty()
            val editor = prefs.edit()

            val resolvedStatuses = setOf("Hyväksytty", "Osittain hyväksytty", "Hylätty")

            for (i in 0 until dataArray.length()) {
                val item = dataArray.getJSONObject(i)
                val id = item.optString("Id")
                if (id.isBlank()) continue

                val newStatus = item.optString("StatusDescription", "")
                val oldStatus = prefs.getString(id, null)

                if (!isFirstRun && oldStatus != null && oldStatus != newStatus && newStatus in resolvedStatuses) {
                    val typeName = item.optString("Type", "Toive")
                    val dateFrom = parseAspNetDate(item.optString("DateFrom", ""))
                    val approver = item.optString("ApprovedBy", "")

                    val title = "Toive käsitelty: $newStatus"
                    val body = buildString {
                        append(typeName)
                        if (dateFrom.isNotBlank()) append(" ($dateFrom)")
                        if (approver.isNotBlank()) append(" – Käsittelijä: $approver")
                    }

                    sendNotification(id.hashCode(), title, body)
                }

                editor.putString(id, newStatus)
            }

            editor.apply()
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }

    private fun fetchRequestsJson(baseUrl: String): String? {
        val cookies = CookieManager.getInstance().getCookie(baseUrl)
        if (cookies.isNullOrBlank()) return null

        val conn = (URL("$baseUrl/PersonRequests/Read").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            setRequestProperty("Cookie", cookies)
            setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
            setRequestProperty("X-Requested-With", "XMLHttpRequest")
            doOutput = true
            connectTimeout = 15000
            readTimeout = 15000
        }

        OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { writer ->
            writer.write("selectedFilter=active&page=1&pageSize=50")
            writer.flush()
        }

        if (conn.responseCode != 200) {
            conn.disconnect()
            return null
        }

        val responseText = conn.inputStream.bufferedReader().use { it.readText() }
        conn.disconnect()

        return if (responseText.trim().startsWith("{")) responseText else null
    }

    private fun parseAspNetDate(raw: String): String {
        val match = Regex("""/Date\((\d+)\)/""").find(raw)
        return if (match != null) {
            val millis = match.groupValues[1].toLongOrNull() ?: return ""
            SimpleDateFormat("dd.MM.yyyy", Locale("fi", "FI")).format(Date(millis))
        } else {
            raw.take(10)
        }
    }

    private fun sendNotification(notificationId: Int, title: String, message: String) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Toiveiden tilamuutokset",
                NotificationManager.IMPORTANCE_DEFAULT
            )
            val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(channel)
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ActivityCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            return
        }

        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("OPEN_REQUESTS", true)
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            notificationId,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message))
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()

        NotificationManagerCompat.from(context).notify(notificationId, notification)
    }
}
