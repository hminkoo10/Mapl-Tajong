package com.milky.mataf.core

import android.app.AlarmManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
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
import java.util.Collections

/** 수동 타종의 재생 결과를 기록에 넘긴다. */
internal fun manualRingReport(scheduleId: Long?, scheduleName: String, soundName: String, detail: String?,
                              log: (Long?, String, String, String, String) -> Unit): (String?) -> Unit = { err ->
    val source = detail ?: "forced"
    log(scheduleId, scheduleName, soundName, if (err == null) "PLAYED" else "FAILED", if (err == null) source else "$source · $err")
}

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
        /** 기다리는 '지금 울리기' 하나를 거둔다 (되돌리기) */
        private const val K_CANCEL = "cancel"
        private const val E_ID = "id"
        private const val E_AT = "at"
        private const val E_VOL = "vol"
        private const val E_DETAIL = "detail"
        /** '지금 울리기' 요청 id 와 울릴 때(ring_at, epoch ms) */
        private const val E_REQ = "req"
        private const val E_RING_AT = "ring_at"
        /** '지금 울리기' 요청으로 울리는 것: 울릴 때 이 기기가 아직 종을 울리는지 다시 본다 */
        private const val E_HERE = "here"
        /** 울림 서비스를 바로 켜지 못했을 때 알람으로 깨운다 (RingReceiver) */
        const val ACTION_REMOTE = "com.milky.mataf.RING_REMOTE"
        private const val REQ_REMOTE = 7003
        /** 울릴 때를 기다리는 동안 CPU 를 붙잡아 두는 가장 긴 시간 (요청은 ±2분 안의 것만 받으므로 놓쳐도 이 뒤에는 풀린다) */
        private const val WAKE_MAX_MS = 3 * 60_000L
        /** 늦게 깨어나도 이 시간 안이면 울린다 (그보다 늦으면 '놓침'으로 기록) */
        private const val LATE_LIMIT_SEC = 120L

        private val _ringing = MutableStateFlow<String?>(null)
        /** 지금 울리는 종 이름 (화면 표시용) */
        val ringing: StateFlow<String?> = _ringing

        /** 서비스에 맡겨서 울릴 때를 기다리는 요청 id (울리거나 거두면 빠진다). 되돌리기가 서비스에 알릴지 볼 때 쓴다 */
        private val waiting: MutableSet<String> = Collections.synchronizedSet(HashSet())

        fun createChannel(ctx: Context) {
            val nm = ctx.getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "종 울림", NotificationManager.IMPORTANCE_LOW).apply {
                description = "종이 울리는 동안 보여요"
                setShowBadge(false)
            })
        }

        fun ringScheduled(ctx: Context, scheduleId: Long, atMillis: Long) =
            start(ctx, Intent(ctx, BellService::class.java).putExtra(KIND, K_SCHEDULED).putExtra(E_ID, scheduleId).putExtra(E_AT, atMillis))

        /**
         * '지금 울리기' 요청(state.json 의 ring_requests)의 종을 울릴 때(atMillis, ring_at)에 울린다. 시간표 종이면 scheduleId, 아니면 soundId.
         * detail: 기록 설명. 다른 기기의 요청이면 "forced · <요청한 기기>", 이 기기가 누른 것이면 null ("forced"로 기록).
         * 울림 서비스를 바로 켜서, 서비스 안에서 소리를 미리 열어 두고 울릴 때까지 기다린다 (알람은 5초 안으로는 정확히 걸리지 않음).
         * 울릴 때가 이미 지났으면 바로. 울릴 때 이 기기가 종을 울리지 않게 됐으면 울리지 않는다. 요청마다 따로 기다린다.
         */
        fun ringAt(ctx: Context, atMillis: Long, requestId: String, scheduleId: Long?, soundId: Long?, detail: String?) {
            waiting.add(requestId)
            ringRemote(ctx, remoteIntent(ctx, scheduleId, soundId, detail).putExtra(E_REQ, requestId).putExtra(E_RING_AT, atMillis),
                requestId, atMillis)
        }

        /** 되돌리기: 울릴 때를 기다리는 이 요청을 거둔다 (다른 요청은 그대로, 이미 울리고 있으면 stop 으로 끈다) */
        fun cancelAt(ctx: Context, requestId: String) {
            if (requestId !in waiting) return
            PendingIntent.getBroadcast(ctx, REQ_REMOTE, alarmIntent(ctx, requestId), PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE)
                ?.let { pi ->
                    ctx.getSystemService(AlarmManager::class.java).cancel(pi)
                    pi.cancel()
                }
            start(ctx, Intent(ctx, BellService::class.java).putExtra(KIND, K_CANCEL).putExtra(E_REQ, requestId))
        }

        /** 요청마다 다른 알람이 되게 data 에 요청 id 를 넣는다 (같은 알람인지 볼 때 extras 는 보지 않으므로) */
        private fun alarmIntent(ctx: Context, requestId: String): Intent =
            Intent(ctx, RingReceiver::class.java).setAction(ACTION_REMOTE).setData(Uri.fromParts("ring", requestId, null))

        /** 울림 서비스를 켠다. 뒤에서는 바로 켜지 못할 수 있다 → 울릴 때(이미 지났으면 0.3초 뒤)에 정확한 알람으로 깨운다 */
        private fun ringRemote(ctx: Context, i: Intent, requestId: String, atMillis: Long) {
            try {
                ContextCompat.startForegroundService(ctx, i)
            } catch (e: Exception) {
                // 시스템이 5초 안의 알람은 5초 뒤로 미루므로 이 길로 가면 다른 기기보다 조금 늦게 울린다 (대신하는 길이라 그대로 둔다)
                val pi = PendingIntent.getBroadcast(ctx, REQ_REMOTE, alarmIntent(ctx, requestId).putExtras(i),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                val am = ctx.getSystemService(AlarmManager::class.java)
                val at = maxOf(atMillis, System.currentTimeMillis() + 300)
                try {
                    if (Alarms.canExact(ctx)) am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi)
                    else am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi)
                } catch (_: Exception) {
                    am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi)
                }
            }
        }

        private fun remoteIntent(ctx: Context, scheduleId: Long?, soundId: Long?, detail: String?): Intent =
            if (scheduleId != null) Intent(ctx, BellService::class.java).putExtra(KIND, K_FORCED).putExtra(E_ID, scheduleId)
                .putExtra(E_AT, System.currentTimeMillis()).putExtra(E_DETAIL, detail).putExtra(E_HERE, true)
            else Intent(ctx, BellService::class.java).putExtra(KIND, K_SOUND).putExtra(E_ID, soundId ?: -1L)
                .putExtra(E_VOL, -1.0).putExtra(E_DETAIL, detail).putExtra(E_HERE, true)

        /** 알람으로 깨어난 뒤 (RingReceiver) */
        fun startFrom(ctx: Context, extras: Intent) = start(ctx, Intent(ctx, BellService::class.java).putExtras(extras))

        fun stop(ctx: Context) {
            if (_ringing.value != null) start(ctx, Intent(ctx, BellService::class.java).putExtra(KIND, K_STOP))
        }

        private fun start(ctx: Context, i: Intent) = ContextCompat.startForegroundService(ctx, i)
    }

    /** 지금 울리는 소리 */
    private var player: BellPlayer? = null
    private val main = Handler(Looper.getMainLooper())
    /** 울릴 때를 기다리는 '지금 울리기' (요청 id → 할 일과 미리 열어 둔 소리) */
    private val pending = HashMap<String, Pending>()
    private var wake: PowerManager.WakeLock? = null
    private var lastStart = 0

    /** 울릴 준비가 된 종: player 가 null 이면 열지 못한 것(error 가 그 까닭). report 는 한 번만 (울림·실패 기록) */
    private class Ready(val label: String, private val onStarted: (String?) -> Unit) {
        var player: BellPlayer? = null
        var error: String? = null
        private var reported = false

        fun report(err: String?) {
            if (!reported) { reported = true; onStarted(err) }
        }
    }

    private class Pending(val task: Runnable, val ready: Ready)

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        lastStart = startId
        startInForeground(_ringing.value?.let { "$it 종을 울리고 있어요" } ?: "종을 울리고 있어요")
        val kind = intent?.getStringExtra(KIND) ?: K_STOP
        val id = intent?.getLongExtra(E_ID, -1) ?: -1
        try {
            when (kind) {
                K_SCHEDULED -> handleScheduled(id, intent?.getLongExtra(E_AT, 0) ?: 0)
                K_FORCED, K_SOUND -> await(intent!!.getStringExtra(E_REQ) ?: "start-$startId", intent)
                K_CANCEL -> {
                    intent?.getStringExtra(E_REQ)?.let { drop(it); waiting.remove(it) }
                    idle()
                }
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
        // 이 기기에서 종을 울리지 않게 해 두었으면 (클라우드의 다른 기기가 울림) 울리지도 기록하지도 않는다
        if (s == null || !Cloud.ringsHere(repo)) {
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

    /**
     * '지금 울리기': 일정·종소리를 찾아 소리를 미리 열어 두고, 울릴 때(ring_at)까지 기다렸다가 시작만 한다 (여러 기기가 같은 순간에 울리게).
     * 기다리는 동안은 CPU 가 잠들지 않게 붙잡아 둔다. 울릴 때가 이미 지났으면 바로. 요청마다 따로 기다린다.
     */
    private fun await(req: String, i: Intent) {
        drop(req)   // 같은 요청이 또 오면 하나만
        val r = openRequest(i) ?: run { waiting.remove(req); idle(); return }
        val here = i.getBooleanExtra(E_HERE, false)
        val task = Runnable {
            pending.remove(req)
            waiting.remove(req)
            if (pending.isEmpty()) releaseWake()
            try {
                // 울릴 때 이 기기가 아직 종을 울리는지 다시 본다 (그사이 로그아웃했거나 '이 기기에서 종 울리기'를 끔)
                if (here && !Cloud.ringsHere(Repo(this))) {
                    r.player?.stop(); idle()
                } else sound(r)
            } catch (e: Exception) {
                finish()
            }
        }
        pending[req] = Pending(task, r)
        holdWake()
        main.postDelayed(task, maxOf(0L, i.getLongExtra(E_RING_AT, 0) - System.currentTimeMillis()))
        if (_ringing.value == null) startInForeground("곧 종을 울려요", stoppable = false)
    }

    /** 기다리던 이 요청을 거둔다 (울리지 않음) */
    private fun drop(req: String) {
        val p = pending.remove(req) ?: return
        main.removeCallbacks(p.task)
        p.ready.player?.stop()
        if (pending.isEmpty()) releaseWake()
    }

    /** '지금 울리기'의 종을 찾아 소리를 열어 둔다 (일정·종소리가 없어졌으면 null). 재생 결과는 수동 타종으로 기록한다 */
    private fun openRequest(i: Intent): Ready? {
        val repo = Repo(this)
        val id = i.getLongExtra(E_ID, -1)
        val detail = i.getStringExtra(E_DETAIL)
        if (i.getStringExtra(KIND) == K_FORCED) {
            val s = repo.schedule(id) ?: return null
            return open(Sounds.file(this, s.soundFile).absolutePath, s.volume, s.name,
                manualRingReport(id, s.name, s.soundName, detail, repo::log))
        }
        val s = repo.sound(id) ?: return null
        val volume = i.getDoubleExtra(E_VOL, -1.0)
        return open(Sounds.file(this, s.fileName).absolutePath, if (volume >= 0) volume else s.volume, s.name,
            manualRingReport(null, "", s.name, detail, repo::log))
    }

    /** onStarted(null) = 재생 시작, onStarted("오류") = 실패 */
    private fun play(path: String, volume: Double, label: String, onStarted: (String?) -> Unit) = sound(open(path, volume, label, onStarted))

    /** 소리 파일을 열어 둔다 (울릴 때 sound() 로 시작만 하게) */
    private fun open(path: String, volume: Double, label: String, onStarted: (String?) -> Unit): Ready {
        val r = Ready(label, onStarted)
        if (!java.io.File(path).exists()) {
            r.error = "종소리 파일이 없어요"; return r
        }
        val p = BellPlayer(this)
        val ok = p.prepare(path, volume, label,
            onDone = { if (player === p) finish() },
            onError = { msg ->
                if (r.player == null) r.error = msg      // 여는 중
                else { r.report(msg); if (player === p) finish() }
            })
        if (ok) r.player = p
        return r
    }

    /** 열어 둔 종을 지금 낸다 (울리던 종은 멈춘다). 제때 소리가 나게 시작부터 하고 알림·기록은 그 뒤에 */
    private fun sound(r: Ready) {
        Preview.stop()
        val p = r.player
        if (p == null) {
            r.report(r.error ?: "재생하지 못했어요"); idle(); return
        }
        if (player !== p) player?.stop()
        player = p
        _ringing.value = r.label
        p.start()
        if (player === p) startInForeground("${r.label} 종을 울리고 있어요")   // 시작하지 못했으면 finish() 가 이미 정리함
        if (p.isPlaying) r.report(null)
        AppEvents.changed()
    }

    /** 울리던 종을 멈춘다. 기다리는 '지금 울리기'는 그대로 둔다 */
    private fun finish() {
        player?.stop()
        player = null
        _ringing.value = null
        AppEvents.changed()
        idle()
    }

    /** 울리는 종도 기다리는 것도 없으면 서비스를 끝낸다. 기다리는 것만 남았으면 알림을 "곧 종을 울려요"로 */
    private fun idle() {
        if (_ringing.value != null) return
        if (pending.isNotEmpty()) {
            startInForeground("곧 종을 울려요", stoppable = false); return
        }
        releaseWake()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf(lastStart)   // 그사이 새로 맡긴 일이 있으면 끝내지 않는다
    }

    /** 울릴 때를 기다리는 동안 CPU 가 잠들지 않게 (화면이 꺼져도 늦게 울리지 않게) */
    private fun holdWake() {
        val w = wake ?: getSystemService(PowerManager::class.java).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "mataf:ring_at")
            .apply { setReferenceCounted(false) }.also { wake = it }
        w.acquire(WAKE_MAX_MS)
    }

    private fun releaseWake() {
        wake?.let { if (it.isHeld) it.release() }
    }

    override fun onDestroy() {
        for ((req, p) in pending) {
            main.removeCallbacks(p.task)
            p.ready.player?.stop()
            waiting.remove(req)
        }
        pending.clear()
        releaseWake()
        player?.stop()
        _ringing.value = null
        super.onDestroy()
    }

    /** stoppable: 알림에 '정지' (울리는 중일 때만, 기다리는 동안에는 멈출 소리가 없다) */
    private fun startInForeground(text: String, stoppable: Boolean = true) {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val stop = PendingIntent.getService(this, 1, Intent(this, BellService::class.java).putExtra(KIND, K_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n: Notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_bell)
            .setContentTitle("마고 타종")
            .setContentText(text)
            .setContentIntent(open)
            .apply { if (stoppable) addAction(0, "정지", stop) }
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
