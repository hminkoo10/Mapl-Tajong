package com.milky.mataf.core

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.Network
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.milky.mataf.BuildConfig
import com.milky.mataf.MainActivity
import com.milky.mataf.R
import com.milky.mataf.data.Repo
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.Call
import okhttp3.Request
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * 서버 실시간 알림 (GET /api/sync/events?apps=tajong, text/event-stream).
 * 앱이 보일 때, 또는 클라우드 연결 서비스(CloudService)가 돌 때만 붙어 있는다. 끊기면 1초부터 두 배씩, 많아야 30초 뒤 다시.
 * 붙을 때마다 바뀐 것을 한 번 받는다. 이 주소가 없는 서버면 다시 붙으려 할 때마다 받아서 그만큼 자주 확인한다.
 */
object CloudEvents {
    private const val STOP_AFTER_MS = 10_000L
    private const val MAX_BACKOFF_MS = 30_000L

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    // 서버가 25초마다 ping 을 보내므로, 그 두 배 넘게 아무것도 안 오면 끊긴 것으로 보고 다시 붙는다
    private val http by lazy {
        Online.http.newBuilder().readTimeout(70, TimeUnit.SECONDS).callTimeout(0, TimeUnit.MILLISECONDS)
            .retryOnConnectionFailure(true).build()
    }
    private val kick = Channel<Unit>(Channel.CONFLATED)
    private val ua = "MaplTajong-Android/${BuildConfig.VERSION_NAME}"

    private var visible = false
    private var serviceRunning = false
    private var job: Job? = null
    private var stopJob: Job? = null
    @Volatile private var call: Call? = null
    private var registered = false

    fun init(ctx: Context) {
        if (registered) return
        registered = true
        try {
            val cm = ctx.getSystemService(ConnectivityManager::class.java)
            cm.registerDefaultNetworkCallback(object : ConnectivityManager.NetworkCallback() {
                private var first = true
                override fun onAvailable(network: Network) {
                    if (first) { first = false; return }
                    kick.trySend(Unit)
                    Cloud.networkBack()
                }
            })
        } catch (_: Exception) {
        }
    }

    fun setVisible(v: Boolean) {
        synchronized(this) { visible = v }
        update()
    }

    fun setService(running: Boolean) {
        synchronized(this) { serviceRunning = running }
        update()
    }

    private fun wanted() = Cloud.isLoggedIn() && (visible || serviceRunning)

    @Synchronized
    fun update() {
        if (wanted()) {
            stopJob?.cancel(); stopJob = null
            if (job?.isActive != true) job = scope.launch { run() }
        } else if (job?.isActive == true && stopJob == null) {
            // 화면을 잠깐 벗어난 것일 수 있으니 조금 기다렸다가 끊는다 (로그아웃이면 바로)
            val wait = if (Cloud.isLoggedIn()) STOP_AFTER_MS else 0L
            stopJob = scope.launch {
                delay(wait)
                synchronized(this@CloudEvents) {
                    if (!wanted()) {
                        job?.cancel(); job = null
                        call?.cancel()
                        Cloud.setConn(Cloud.Conn.OFF)
                    }
                    stopJob = null
                }
            }
        }
    }

    private suspend fun run() {
        var backoff = 1000L
        while (currentCoroutineContext().isActive) {
            val (server, token) = Cloud.credentials() ?: break
            var reached = false
            var opened = false
            Cloud.setConn(Cloud.Conn.CONNECTING)
            try {
                val req = Request.Builder().url("$server/api/sync/events?apps=${CloudModel.APP_ID}")
                    .header("Authorization", "Bearer $token").header("Accept", "text/event-stream").header("User-Agent", ua).build()
                val c = http.newCall(req)
                call = c
                c.execute().use { resp ->
                    reached = true
                    if (resp.code == 401) {
                        Cloud.unauthorized("로그인이 끝났어요. 다시 로그인해 주세요.")
                        return
                    }
                    if (!resp.isSuccessful) throw IOException("HTTP ${resp.code}")
                    val src = resp.body?.source() ?: throw IOException("빈 응답")
                    opened = true
                    backoff = 1000L
                    Cloud.setConn(Cloud.Conn.ONLINE)
                    Cloud.requestPull()
                    var event = "message"
                    val data = StringBuilder()
                    while (true) {
                        val line = src.readUtf8Line() ?: break
                        if (line.isEmpty()) {
                            if (data.isNotEmpty() || event != "message") dispatch(event, data.toString())
                            event = "message"; data.setLength(0)
                            continue
                        }
                        if (line.startsWith(":")) continue            // ping
                        val i = line.indexOf(':')
                        val field = if (i < 0) line else line.substring(0, i)
                        val value = if (i < 0) "" else line.substring(i + 1).removePrefix(" ")
                        when (field) {
                            "event" -> event = value
                            "data" -> { if (data.isNotEmpty()) data.append('\n'); data.append(value) }
                        }
                    }
                }
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
            } finally {
                call = null
            }
            if (!currentCoroutineContext().isActive || !Cloud.isLoggedIn()) break
            Cloud.setConn(if (opened) Cloud.Conn.CONNECTING else if (reached) Cloud.Conn.POLLING else Cloud.Conn.OFFLINE)
            if (reached && !opened) Cloud.requestPull()     // 실시간 알림이 없는 서버: 다시 붙으려 할 때마다 확인
            val wait = backoff
            backoff = minOf(backoff * 2, MAX_BACKOFF_MS)
            withTimeoutOrNull(wait) { kick.receive() }
        }
    }

    private fun dispatch(event: String, data: String) {
        when (event) {
            "hello" -> Cloud.requestPull()
            "change" -> {
                val m = runCatching { Json.parse(data).jObj() }.getOrNull()
                val app = m?.get("appId").jStr()
                if (app != null && app != CloudModel.APP_ID) return
                if (m?.get("deviceId").jStr() == Cloud.deviceId()) return     // 내가 올린 것
                Cloud.requestPull(300)    // 여러 파일이 잇달아 바뀌면 한 번에 받게
            }
        }
    }
}

/**
 * 앱을 닫아도 다른 기기의 '울려 달라' 요청을 바로 받도록 클라우드 연결을 유지하는 서비스.
 * 로그인했고 이 기기가 종을 울릴 때만 돈다. 알림: "클라우드와 연결돼 있어요".
 */
class CloudService : Service() {
    companion object {
        const val CHANNEL = "cloud"
        private const val CHANNEL_LOGIN = "cloud_login"
        private const val NOTIF_ID = 4102
        private const val NOTIF_LOGIN = 4103

        fun createChannel(ctx: Context) {
            val nm = ctx.getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "클라우드 연결", NotificationManager.IMPORTANCE_LOW).apply {
                description = "다른 기기에서 울려 달라고 하면 바로 울리려고 연결해 둘 때 보여요"
                setShowBadge(false)
            })
            nm.createNotificationChannel(NotificationChannel(CHANNEL_LOGIN, "클라우드 로그인", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "로그인이 끝나서 이 기기에서 종을 울리지 못할 때 알려요"
            })
        }

        /** 로그인하지 않아서 종을 울리지 못한다고 알린다 (누르면 앱의 로그인 화면) */
        fun notifyLogin(ctx: Context, text: String) {
            val open = PendingIntent.getActivity(ctx, 1, Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            val n = NotificationCompat.Builder(ctx, CHANNEL_LOGIN)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle("마고 타종")
                .setContentText(text)
                .setStyle(NotificationCompat.BigTextStyle().bigText(text))
                .setContentIntent(open)
                .setAutoCancel(true)
                .build()
            try {
                ctx.getSystemService(NotificationManager::class.java).notify(NOTIF_LOGIN, n)
            } catch (_: Exception) {
                // 알림 권한이 없으면 앱을 열 때 로그인 화면이 보인다
            }
        }

        fun cancelLoginNotice(ctx: Context) {
            ctx.getSystemService(NotificationManager::class.java).cancel(NOTIF_LOGIN)
        }

        private fun wanted(ctx: Context) = Cloud.isLoggedIn() && Cloud.ringsHere(Repo(ctx))

        /** 조건에 맞게 켜거나 끈다 (앱 시작·부팅·로그인·로그아웃·설정 바꿈) */
        fun sync(ctx: Context) {
            val i = Intent(ctx, CloudService::class.java)
            if (wanted(ctx)) {
                try {
                    ContextCompat.startForegroundService(ctx, i)
                } catch (_: Exception) {
                    // 뒤에서 앞 서비스를 시작할 수 없는 때 (앱을 다시 열면 그때 켜진다)
                }
            } else {
                ctx.stopService(i)
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        try {
            startInForeground()
        } catch (_: Exception) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (!wanted(this)) {
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return START_NOT_STICKY
        }
        CloudEvents.setService(true)
        return START_STICKY
    }

    override fun onDestroy() {
        CloudEvents.setService(false)
        super.onDestroy()
    }

    private fun startInForeground() {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n: Notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("마고 타종")
            .setContentText("클라우드와 연결돼 있어요")
            .setContentIntent(open)
            .setOngoing(true)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIF_ID, n)
        }
    }
}
