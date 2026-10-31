package com.milky.mataf.core

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.milky.mataf.MainActivity
import com.milky.mataf.R
import com.milky.mataf.data.Repo
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.time.Duration
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId

/** 종을 울리는 동안 앞에서 도는 서비스 (화면이 꺼져 있어도 끝까지 울리게) */
class BellService : Service() {

    companion object {
        const val CHANNEL = "bell"
        private const val NOTIF_ID = 4101
        private const val KIND = "kind"
        private const val K_SCHEDULED = "scheduled"
        private const val K_FORCED = "forced"
        private const val K_SOUND = "sound"
        private const val K_STOP = "stop"
        private const val E_ID = "id"
        private const val E_AT = "at"
        private const val E_VOL = "vol"
        /** 늦게 깨어나도 이 시간 안이면 울린다 (그보다 늦으면 '놓침'으로 기록) */
        private const val LATE_LIMIT_SEC = 120L

        private val _ringing = MutableStateFlow<String?>(null)
        /** 지금 울리는 종 이름 (화면 표시용) */
        val ringing: StateFlow<String?> = _ringing

        fun createChannel(ctx: Context) {
            val nm = ctx.getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "종 울림", NotificationManager.IMPORTANCE_LOW).apply {
                description = "종이 울리는 동안 보여요"
                setShowBadge(false)
            })
        }

        fun ringScheduled(ctx: Context, scheduleId: Long, atMillis: Long) =
            start(ctx, Intent(ctx, BellService::class.java).putExtra(KIND, K_SCHEDULED).putExtra(E_ID, scheduleId).putExtra(E_AT, atMillis))

        fun ring(ctx: Context, scheduleId: Long, forced: Boolean) =
            start(ctx, Intent(ctx, BellService::class.java).putExtra(KIND, if (forced) K_FORCED else K_SCHEDULED)
                .putExtra(E_ID, scheduleId).putExtra(E_AT, System.currentTimeMillis()))

        /** 홈 화면의 '종소리 바로 울리기' */
        fun playSound(ctx: Context, soundId: Long, volume: Double? = null) =
            start(ctx, Intent(ctx, BellService::class.java).putExtra(KIND, K_SOUND).putExtra(E_ID, soundId)
                .putExtra(E_VOL, volume ?: -1.0))

        fun stop(ctx: Context) {
            if (_ringing.value != null) start(ctx, Intent(ctx, BellService::class.java).putExtra(KIND, K_STOP))
        }

        private fun start(ctx: Context, i: Intent) = ContextCompat.startForegroundService(ctx, i)
    }

    private var player: BellPlayer? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startInForeground("종을 울리고 있어요")
        val kind = intent?.getStringExtra(KIND) ?: K_STOP
        val id = intent?.getLongExtra(E_ID, -1) ?: -1
        try {
            when (kind) {
                K_SCHEDULED -> handleScheduled(id, intent?.getLongExtra(E_AT, 0) ?: 0)
                K_FORCED -> handleForced(id)
                K_SOUND -> handleSound(id, intent?.getDoubleExtra(E_VOL, -1.0) ?: -1.0)
                else -> finish()
            }
        } catch (e: Exception) {
            finish()
        }
        return START_NOT_STICKY
    }

    private fun handleScheduled(id: Long, atMillis: Long) {
        val repo = Repo(this)
        val s = repo.schedule(id)
        if (s == null) {
            finish(); Alarms.reschedule(this); return
        }
        val runAt = LocalDateTime.ofInstant(Instant.ofEpochMilli(if (atMillis > 0) atMillis else System.currentTimeMillis()),
            ZoneId.systemDefault())
        val date = runAt.toLocalDate()
        val late = Duration.between(runAt, LocalDateTime.now()).seconds
        when {
            Scheduler.isPaused(repo) || repo.isPauseDay(date) -> finish()
            repo.hasOverride(date, id, Scheduler.SKIP) -> {
                repo.log(id, s.name, s.soundName, "SKIPPED"); finish()
            }
            repo.hasOverride(date, id, Scheduler.FIRED) -> finish()
            late > LATE_LIMIT_SEC -> {
                repo.log(id, s.name, s.soundName, "MISSED", "late=${late}s"); finish()
            }
            else -> {
                repo.addOverride(date, id, Scheduler.FIRED, "auto")
                play(Sounds.file(this, s.soundFile).absolutePath, s.volume, s.name) { err ->
                    repo.log(id, s.name, s.soundName, if (err == null) "PLAYED" else "FAILED", err ?: "")
                }
            }
        }
        Alarms.reschedule(this)
    }

    private fun handleForced(id: Long) {
        val repo = Repo(this)
        val s = repo.schedule(id) ?: return finish()
        play(Sounds.file(this, s.soundFile).absolutePath, s.volume, s.name) { err ->
            repo.log(id, s.name, s.soundName, if (err == null) "PLAYED" else "FAILED", if (err == null) "forced" else err)
        }
    }

    private fun handleSound(soundId: Long, volume: Double) {
        val s = Repo(this).sound(soundId) ?: return finish()
        play(Sounds.file(this, s.fileName).absolutePath, if (volume >= 0) volume else s.volume, s.name) {}
    }

    /** onStarted(null) = 재생 시작, onStarted("오류") = 실패 */
    private fun play(path: String, volume: Double, label: String, onStarted: (String?) -> Unit) {
        Preview.stop()
        val f = java.io.File(path)
        if (!f.exists()) {
            onStarted("종소리 파일이 없어요"); finish(); return
        }
        val p = player ?: BellPlayer(this).also { player = it }
        _ringing.value = label
        startInForeground("$label 종을 울리고 있어요")
        var reported = false
        p.play(path, volume, label,
            onDone = { finish() },
            onError = { msg -> if (!reported) { reported = true; onStarted(msg) }; finish() })
        if (p.isPlaying && !reported) {
            reported = true
            onStarted(null)
        }
        AppEvents.changed()
    }

    private fun finish() {
        player?.stop()
        _ringing.value = null
        AppEvents.changed()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        player?.stop()
        _ringing.value = null
        super.onDestroy()
    }

    private fun startInForeground(text: String) {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val stop = PendingIntent.getService(this, 1, Intent(this, BellService::class.java).putExtra(KIND, K_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n: Notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("마고 타종")
            .setContentText(text)
            .setContentIntent(open)
            .addAction(0, "정지", stop)
            .setOngoing(true)
            .setSilent(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
        } else {
            startForeground(NOTIF_ID, n)
        }
    }
}
