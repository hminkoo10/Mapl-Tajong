package com.milky.mataf.alarm

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import androidx.core.app.NotificationCompat
import com.milky.mataf.R

object NotificationHelper {
    const val CHANNEL_ID = "tajong_playback"

    fun ensureChannel(context: Context) {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val ch = NotificationChannel(CHANNEL_ID, "타종 재생", NotificationManager.IMPORTANCE_LOW)
        nm.createNotificationChannel(ch)
    }

    fun build(context: Context, title: String, text: String): Notification {
        return NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(text)
            .setOngoing(true)
            .build()
    }
}
