package com.milky.mataf.alarm

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.net.toUri
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import com.milky.mataf.MainActivity
import com.milky.mataf.R
import java.io.File
import java.util.concurrent.TimeUnit

class TajongService : Service() {

    companion object {
        const val ACTION_START = "TAJONG_START"
        const val ACTION_PLAY = "TAJONG_PLAY"
        const val ACTION_STOP_PLAY = "TAJONG_STOP_PLAY"
        const val ACTION_QUIT = "TAJONG_QUIT"

        const val CHANNEL_ID = "tajong_status"
        const val NOTI_ID = 1001
    }

    private var player: ExoPlayer? = null
    private var wakeLock: PowerManager.WakeLock? = null

    private val handler = Handler(Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() {
            updateNotification()
            handler.postDelayed(this, 1000L)
        }
    }

    private var nowPlayingName = ""
    private var isPlaying = false
    private var lastPlayUri: String = ""

    override fun onCreate() {
        super.onCreate()
        ensureChannel()

        val pm = getSystemService(POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "MatafTajong:Main").apply {
            setReferenceCounted(false)
            acquire(TimeUnit.HOURS.toMillis(8))
        }

        player = ExoPlayer.Builder(this).build().also { p ->
            p.addListener(object : Player.Listener {
                override fun onIsPlayingChanged(playing: Boolean) {
                    isPlaying = playing
                    pushNowState()
                    updateNotification()
                }

                override fun onPlaybackStateChanged(state: Int) {
                    if (state == Player.STATE_ENDED) {
                        val currentUri = player
                            ?.currentMediaItem
                            ?.localConfiguration
                            ?.uri
                            ?.toString()
                            ?: ""

                        if (currentUri.isNotBlank() && currentUri == lastPlayUri) {
                            nowPlayingName = ""
                            isPlaying = false
                            lastPlayUri = ""
                            pushNowState()
                            updateNotification()
                        }
                    }
                }
            })
        }

        startForeground(NOTI_ID, buildNotification())
        handler.post(tick)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action ?: ACTION_START

        when (action) {
            ACTION_START -> updateNotification()

            ACTION_PLAY -> {
                val path = intent?.getStringExtra("sound_path") ?: return START_STICKY
                val soundName = intent.getStringExtra("sound_name") ?: "종"
                val vol = intent.getIntExtra("volume_percent", 100).coerceIn(0, 200)
                playFile(path, soundName, vol)
            }

            ACTION_STOP_PLAY -> stopPlay()

            ACTION_QUIT -> {
                stopPlay()
                handler.removeCallbacksAndMessages(null)
                stopForeground(STOP_FOREGROUND_REMOVE)
                val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                nm.cancel(NOTI_ID)
                stopSelf()
            }

            else -> updateNotification()
        }

        return START_STICKY
    }


    private fun playFile(path: String, soundName: String, volumePercent: Int) {
        val file = File(path)
        if (!file.exists()) return

        nowPlayingName = soundName

        val p = player ?: return
        val uri = file.toUri()
        lastPlayUri = uri.toString()

        p.clearMediaItems()
        p.setMediaItem(MediaItem.fromUri(uri))
        p.volume = (volumePercent / 100f).coerceIn(0f, 2f)
        p.prepare()
        p.playWhenReady = true

        pushNowState()
        updateNotification()
    }

    private fun stopPlay() {
        try {
            player?.stop()
            player?.clearMediaItems()
        } catch (_: Exception) {
        }
        nowPlayingName = ""
        isPlaying = false
        lastPlayUri = ""
        pushNowState()
        updateNotification()
    }

    private fun pushNowState() {
        if (nowPlayingName.isBlank()) {
            StatusStore.clearNow(this)
        } else {
            StatusStore.setNow(this, nowPlayingName, isPlaying)
        }
    }

    private fun openAppPendingIntent(): PendingIntent {
        val i = Intent(this, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        }
        return PendingIntent.getActivity(
            this,
            9001,
            i,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }

    private fun buildNotification(): Notification {
        val (nextAt, nextTitle, nextSound) = StatusStore.getNext(this)
        val now = System.currentTimeMillis()

        val line1 = if (nextAt > 0L) {
            val remain = (nextAt - now).coerceAtLeast(0L)
            val h = TimeUnit.MILLISECONDS.toHours(remain)
            val m = TimeUnit.MILLISECONDS.toMinutes(remain) % 60
            val s = TimeUnit.MILLISECONDS.toSeconds(remain) % 60
            "다음까지 ${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}"
        } else {
            "다음 일정 없음"
        }

        val line2 = if (nextAt > 0L) {
            "다음: ${nextTitle.ifBlank { "-" }} / ${nextSound.ifBlank { "-" }}"
        } else {
            "다음: -"
        }

        val line3 = if (nowPlayingName.isNotBlank()) {
            if (isPlaying) "재생 중: $nowPlayingName" else "재생 준비: $nowPlayingName"
        } else {
            "재생 중: -"
        }

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(line1)
            .setContentText(line2)
            .setStyle(NotificationCompat.BigTextStyle().bigText("$line2\n$line3"))
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setShowWhen(false)
            .setContentIntent(openAppPendingIntent())
            .build()
    }

    private fun updateNotification() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(NOTI_ID, buildNotification())
    }

    private fun ensureChannel() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val ch = NotificationChannel(CHANNEL_ID, "타종 상태", NotificationManager.IMPORTANCE_LOW).apply {
            setShowBadge(false)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        }
        nm.createNotificationChannel(ch)
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)

        try { player?.release() } catch (_: Exception) {}
        player = null

        try { wakeLock?.let { if (it.isHeld) it.release() } } catch (_: Exception) {}
        wakeLock = null

        super.onDestroy()
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.cancel(NOTI_ID)
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
