package com.milky.mataf.core

import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.os.Build
import android.os.SystemClock
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.milky.mataf.BuildConfig
import com.milky.mataf.core.CloudModel.Base
import com.milky.mataf.core.CloudModel.Entry
import com.milky.mataf.core.CloudModel.Pull
import com.milky.mataf.core.CloudModel.SyncState
import com.milky.mataf.data.DATE
import com.milky.mataf.data.DataChanges
import com.milky.mataf.data.LogEntry
import com.milky.mataf.data.Repo
import com.milky.mataf.ui.components.Toasts
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.io.File
import java.security.KeyStore
import java.security.MessageDigest
import java.time.Instant
import java.time.LocalDate
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * 마고에듀 통합 클라우드 동기화 (docs/cloud-sync.md 의 안드로이드 쪽).
 *
 * - 로그인 정보: 서버 주소·아이디·이름은 설정 표, 세션 토큰은 Android Keystore 키로 암호화해서 설정 표(`cloud_token`)에.
 * - 동기화 상태(seq, 파일마다 rev/sha, 마지막으로 맞춘 내용): `filesDir/cloud/sync.json`, 다른 기기 기록: `filesDir/cloud/logs/`.
 * - 모든 동기화 일은 한 줄로(작업자 코루틴 하나 + Mutex) 한다. 데이터가 바뀌면 잠시 모았다가(시간표 1초, 기록 5초) 올린다.
 */
object Cloud {
    const val DEFAULT_SERVER = "https://mago.milky.kr"
    /** 이 기기에서 종 울리기 ("1"/"0"), 기기마다 따로 (동기화하지 않음) */
    const val K_RING = "ring_device"
    private const val K_SERVER = "cloud_server"
    private const val K_USERNAME = "cloud_username"
    private const val K_NAME = "cloud_name"
    private const val K_TOKEN = "cloud_token"
    private const val K_LAST_SYNC = "cloud_last_sync"
    const val CONFLICT_MSG = "다른 기기에서 먼저 바뀌어서 그 내용으로 맞췄어요"
    private const val RETRY_MS = 30_000L

    enum class Conn { OFF, CONNECTING, ONLINE, POLLING, OFFLINE }

    data class Status(
        val loggedIn: Boolean = false,
        val server: String = DEFAULT_SERVER,
        val username: String = "",
        val name: String = "",
        val conn: Conn = Conn.OFF,
        /** 마지막으로 생긴 문제 (없으면 "") */
        val message: String = "",
        val lastSync: Long = 0,
        val syncing: Boolean = false,
    )

    /** 처음 연결할 때 클라우드와 이 기기 시간표가 둘 다 있고 다를 때 고르게 한다 */
    data class Choice(val cloud: CloudModel.Counts, val local: CloudModel.Counts, val cloudBy: String, val cloudAt: String)

    private enum class Work { PULL, CONFIG, STATE, LOGS, FULL }

    private lateinit var app: Context
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val lock = Mutex()
    private val _status = MutableStateFlow(Status())
    val status: StateFlow<Status> = _status
    private val _choice = MutableStateFlow<Choice?>(null)
    val choice: StateFlow<Choice?> = _choice

    @Volatile private var token: String? = null
    @Volatile private var server: String = DEFAULT_SERVER
    private var sync: SyncState? = null
    private var pendingRemote: Pair<Map<String, Any?>, Entry>? = null
    private val due = HashMap<Work, Long>()
    private val wake = Channel<Unit>(Channel.CONFLATED)
    @Volatile private var started = false

    // ---------------------------------------------------------------- 시작
    fun init(ctx: Context) {
        if (started) return
        started = true
        app = ctx.applicationContext
        val repo = Repo(app)
        server = repo.setting(K_SERVER, DEFAULT_SERVER).ifBlank { DEFAULT_SERVER }
        val saved = repo.setting(K_TOKEN, "")
        token = Secret.decrypt(saved)
        _status.value = Status(
            loggedIn = token != null, server = server, username = repo.setting(K_USERNAME, ""), name = repo.setting(K_NAME, ""),
            lastSync = repo.setting(K_LAST_SYNC, "").toLongOrNull() ?: 0,
            message = if (token == null && saved.isNotEmpty()) "로그인 정보를 읽지 못했어요. 다시 로그인해 주세요." else "",
        )
        DataChanges.listener = { onDataChanged(it) }
        scope.launch { loop() }
        CloudEvents.init(app)
        if (token != null) schedule(Work.FULL, 0)
    }

    fun isLoggedIn(): Boolean = token != null

    fun credentials(): Pair<String, String>? = token?.let { server to it }

    /** 이 기기에서 종을 울리는지: 클라우드에 로그인해 있고 '이 기기에서 종 울리기'가 켜져 있을 때만 */
    fun ringsHere(repo: Repo): Boolean = token != null && repo.setting(K_RING, "1") != "0"

    /** 로그인 화면의 '이 기기에서 종 울리기' 처음 값: 이 기기에서 로그인한 적이 있으면 그때 고른 것, 처음이면 꺼짐 */
    fun ringChoiceForLogin(repo: Repo): Boolean =
        repo.setting(K_USERNAME, "").isNotEmpty() && repo.setting(K_RING, "1") != "0"

    fun setRingsHere(ctx: Context, on: Boolean) {
        Repo(ctx).setSetting(K_RING, if (on) "1" else "0")
        Alarms.reschedule(ctx)
        CloudService.sync(ctx)
        AppEvents.changed()
    }

    @Volatile private var deviceIdCache: String? = null

    /** 로그인할 때 보내고, 기록 파일 이름에도 쓰는 기기 ID (백업되지 않는 곳에 둔다) */
    fun deviceId(ctx: Context = app): String {
        deviceIdCache?.let { return it }
        val f = File(ctx.noBackupFilesDir, "cloud_device_id")
        val cur = runCatching { f.readText().trim() }.getOrNull()
        val id = if (!cur.isNullOrEmpty() && CloudModel.safeId(cur) == cur) cur else UUID.randomUUID().toString().also { runCatching { f.writeText(it) } }
        deviceIdCache = id
        return id
    }

    fun deviceName(): String {
        val maker = Build.MANUFACTURER.orEmpty().trim().replaceFirstChar { it.uppercase() }
        val model = Build.MODEL.orEmpty().trim()
        return when {
            model.isEmpty() -> maker.ifEmpty { "안드로이드" }
            maker.isEmpty() || model.startsWith(maker, ignoreCase = true) -> model
            else -> "$maker $model"
        }
    }

    /** 앱 화면이 보이기 시작하거나 사라질 때 */
    fun onVisible(visible: Boolean) {
        CloudEvents.setVisible(visible)
        if (visible && token != null) {
            schedule(Work.FULL, 0)
            CloudService.sync(app)
        }
    }

    fun syncNow() = schedule(Work.FULL, 0)

    fun requestPull(delayMs: Long = 0) = schedule(Work.PULL, delayMs)

    fun networkBack() {
        if (token != null) schedule(Work.FULL, 1000)
    }

    fun setConn(c: Conn) {
        _status.value = _status.value.copy(conn = c)
    }

    /** 이번 동기화에서 생긴 문제 (작업자 안에서만 쓴다) */
    private var problem: String? = null

    private fun setMessage(m: String) {
        problem = m
        _status.value = _status.value.copy(message = m)
    }

    private fun onDataChanged(kind: DataChanges.Kind) {
        if (token == null) return
        when (kind) {
            DataChanges.Kind.CONFIG -> schedule(Work.CONFIG, 1000)
            DataChanges.Kind.STATE -> schedule(Work.STATE, 1000)
            DataChanges.Kind.LOGS -> schedule(Work.LOGS, 5000)
        }
    }

    // ---------------------------------------------------------------- 작업자 (한 번에 하나씩)
    private fun schedule(w: Work, delayMs: Long) {
        if (token == null) return
        val at = SystemClock.elapsedRealtime() + delayMs
        synchronized(due) {
            val cur = due[w]
            // 받기는 가장 이른 때에, 올리기는 마지막 변경에서 delay 뒤에 (그동안 바뀐 것을 모아서)
            due[w] = if (w == Work.PULL || w == Work.FULL) minOf(cur ?: at, at) else at
        }
        wake.trySend(Unit)
    }

    private suspend fun loop() {
        while (true) {
            val now = SystemClock.elapsedRealtime()
            val ready: Set<Work>
            val next: Long?
            synchronized(due) {
                ready = due.filterValues { it <= now }.keys.toSet()
                ready.forEach { due.remove(it) }
                next = due.values.minOrNull()
            }
            if (ready.isEmpty()) {
                if (next == null) wake.receive() else withTimeoutOrNull(maxOf(1L, next - now)) { wake.receive() }
                continue
            }
            try {
                run(ready)
            } catch (_: Throwable) {
            }
        }
    }

    private suspend fun run(ready: Set<Work>) = lock.withLock {
        val t = token ?: return@withLock
        val api = CloudApi(server, t)
        val st = state()
        _status.value = _status.value.copy(syncing = true)
        problem = null
        try {
            val full = Work.FULL in ready
            if (full || Work.PULL in ready) pull(api, st)
            if (full || Work.CONFIG in ready) step { exportConfig(api, st) }
            if (full || Work.STATE in ready) step { exportState(api, st) }
            if (full || Work.LOGS in ready) step { exportLogs(api, st) }
            val at = System.currentTimeMillis()
            Repo(app).setSetting(K_LAST_SYNC, at.toString())
            _status.value = _status.value.copy(lastSync = at, message = problem ?: "")
        } catch (e: CloudError) {
            when {
                e.status == 401 -> unauthorized(e.message ?: "")
                else -> {
                    setMessage(e.message ?: "동기화하지 못했어요.")
                    // 잠시 뒤 다시 (네트워크가 돌아오면 그때 바로). 권한·주소 문제는 '지금 동기화'나 다음에 열 때
                    if (e.offline || e.status >= 500 || e.status == 429) for (w in ready + Work.PULL) schedule(w, RETRY_MS)
                }
            }
        } catch (e: Exception) {
            setMessage("동기화하지 못했어요: ${e.message ?: e}")
        } finally {
            save(st)
            _status.value = _status.value.copy(syncing = false)
        }
    }

    /** 401·연결 끊김은 위로 올리고, 그 밖의 문제는 알리고 다음 단계로 */
    private inline fun step(block: () -> Unit) {
        try {
            block()
        } catch (e: CloudError) {
            if (e.status == 401 || e.offline) throw e
            setMessage(e.message ?: "동기화하지 못했어요.")
        }
    }

    // ---------------------------------------------------------------- 받기
    private fun pull(api: CloudApi, st: SyncState) {
        val res = api.list(st.seq)
        if (res["full"] == true) st.remote.clear()
        res["entries"].jList().forEach { e -> Entry.from(e.jObj())?.let { st.remote[it.path] = it } }
        st.seq = res["seq"].jLong() ?: st.seq
        val repo = Repo(app)

        // ---- config.json (종소리 파일을 먼저 받고 나서 적용)
        val rc = st.remote[CloudModel.CONFIG]
        val bc = st.base[CloudModel.CONFIG]
        val localCfg = buildConfig(repo)
        val localHash = CloudModel.contentHash(localCfg)
        val need = rc != null && rc.live && (bc == null || bc.rev != rc.rev)
        val remoteCfg = if (need) fetchJson(api, CloudModel.CONFIG, rc!!)?.takeIf { CloudModel.isConfig(it) } else null
        val decision = if (need && remoteCfg == null) {
            setMessage("클라우드의 시간표 파일을 읽지 못했어요.")
            Pull.NONE
        } else {
            CloudModel.decideConfig(bc, rc, localHash, st.lastConfig, remoteCfg?.let { CloudModel.contentHash(it) },
                CloudModel.isDefaultConfig(localCfg))
        }
        if (decision != Pull.ASK && _choice.value != null && st.base[CloudModel.CONFIG] == null && decision != Pull.NONE) {
            _choice.value = null; pendingRemote = null
        }
        val undecided = decision == Pull.ASK || _choice.value != null
        // 처음 연결이면 클라우드 것을 쓰기로 했을 때만 받는다 (이 기기의 같은 이름 파일을 덮지 않게)
        val allowDownload = bc != null || decision == Pull.APPLY || decision == Pull.RECORD
        if (!undecided) pullSounds(api, st, allowDownload)
        when (decision) {
            Pull.RECORD -> {
                st.base[CloudModel.CONFIG] = Base(rc!!.rev, rc.sha)
                st.lastConfig = localHash
                st.lastConfigFiles = CloudModel.soundFiles(localCfg)
            }
            Pull.APPLY -> applyConfig(api, st, remoteCfg!!, rc!!)
            Pull.CONFLICT -> if (applyConfig(api, st, remoteCfg!!, rc!!)) Toasts.show(CONFLICT_MSG, "info")
            Pull.ASK -> {
                pendingRemote = remoteCfg!! to rc!!
                val meta = remoteCfg["meta"].jObj()
                _choice.value = Choice(CloudModel.counts(remoteCfg), CloudModel.counts(localCfg), meta?.get("device_name").jStr() ?: "",
                    meta?.get("at").jStr() ?: "")
            }
            Pull.UPLOAD -> schedule(Work.CONFIG, 0)
            Pull.NONE -> {}
        }
        if (!undecided) pullSoundDeletes(st)

        pullState(api, st)
        pullLogs(api, st)
    }

    /** 내용을 받아 JSON 으로 (없어졌거나 깨졌으면 null) */
    private fun fetchJson(api: CloudApi, path: String, e: Entry): Map<String, Any?>? = try {
        Json.parse(String(api.downloadBytes(path, e.sha), Charsets.UTF_8)).jObj()
    } catch (err: CloudError) {
        if (err.status == 404 || err.status == 410) null else throw err
    } catch (err: Json.ParseError) {
        null
    }

    private fun pullSounds(api: CloudApi, st: SyncState, allowDownload: Boolean) {
        for ((p, r) in st.remote.toList()) {
            val fn = CloudModel.soundName(p) ?: continue
            if (!r.live) continue
            val sha = localSha(st, fn)
            when (CloudModel.planSoundPull(sha, st.base[p], r, referenced = true)) {
                CloudModel.FileOp.RECORD -> st.base[p] = Base(r.rev, sha)
                CloudModel.FileOp.DOWNLOAD -> if (allowDownload) downloadSound(api, st, fn, r)
                else -> {}
            }
        }
    }

    private fun pullSoundDeletes(st: SyncState) {
        val referenced = CloudModel.soundFiles(buildConfig(Repo(app)))
        for ((p, r) in st.remote.toList()) {
            val fn = CloudModel.soundName(p) ?: continue
            if (!r.deleted) continue
            when (CloudModel.planSoundPull(localSha(st, fn), st.base[p], r, fn in referenced)) {
                CloudModel.FileOp.DELETE_LOCAL -> {
                    Sounds.file(app, fn).delete()
                    st.base.remove(p); st.cache.remove(fn)
                }
                CloudModel.FileOp.FORGET -> st.base.remove(p)
                else -> {}
            }
        }
    }

    private fun downloadSound(api: CloudApi, st: SyncState, fn: String, r: Entry) {
        val p = CloudModel.soundPath(fn)
        try {
            val f = Sounds.file(app, fn)
            val sha = api.downloadFile(p, f, r.sha)
            st.base[p] = Base(r.rev, sha)
            st.cache[fn] = CloudModel.FileSig(f.length(), f.lastModified(), sha)
        } catch (e: CloudError) {
            if (e.status == 401 || e.offline) throw e   // 그 밖(서버에 파일 없음 등)은 건너뛴다. 울릴 때 파일이 없으면 '실패'로 남는다
        }
    }

    /** 받은 config.json 을 적용한다. 이 기기에 넣지 못했으면 false */
    private fun applyConfig(api: CloudApi, st: SyncState, cfg: Map<String, Any?>, rc: Entry): Boolean {
        for (fn in CloudModel.soundFiles(cfg)) {
            val p = CloudModel.soundPath(fn)
            val r = st.remote[p] ?: continue
            if (!r.live) continue
            val sha = localSha(st, fn)
            if (sha != r.sha) downloadSound(api, st, fn, r) else st.base[p] = Base(r.rev, sha)
        }
        val stale = try {
            writeConfig(cfg)
        } catch (e: Exception) {
            setMessage("클라우드 시간표를 이 기기에 넣지 못했어요: ${e.message ?: e}")
            return false
        }
        st.base[CloudModel.CONFIG] = Base(rc.rev, rc.sha)
        val after = buildConfig(Repo(app))
        st.lastConfig = CloudModel.contentHash(after)
        st.lastConfigFiles = CloudModel.soundFiles(after)
        if (stale) schedule(Work.STATE, 1000)
        Alarms.reschedule(app)
        AppEvents.changed()
        return true
    }

    private fun pullState(api: CloudApi, st: SyncState) {
        val rs = st.remote[CloudModel.STATE]
        val bs = st.base[CloudModel.STATE]
        val repo = Repo(app)
        val local = buildState(repo, st.requests)
        val localHash = CloudModel.contentHash(local)
        val need = rs != null && rs.live && (bs == null || bs.rev != rs.rev)
        val remote = if (need) fetchJson(api, CloudModel.STATE, rs!!)?.takeIf { CloudModel.isState(it) } else null
        if (need && remote == null) return
        when (CloudModel.decideState(bs, rs, localHash, st.lastState, remote?.let { CloudModel.contentHash(it) })) {
            Pull.RECORD -> {
                st.base[CloudModel.STATE] = Base(rs!!.rev, rs.sha)
                st.lastState = localHash
            }
            Pull.APPLY -> applyState(st, CloudModel.parseState(remote!!), rs!!)
            Pull.CONFLICT -> stateConflict(st, local, remote!!, rs!!)
            Pull.UPLOAD -> schedule(Work.STATE, 0)
            else -> {}
        }
    }

    /** 둘 다 바뀜: 서버 것을 쓰고, 이 기기가 넣은 울림 요청만 다시 얹는다 */
    private fun stateConflict(st: SyncState, local: Map<String, Any?>, remote: Map<String, Any?>, rs: Entry) {
        val parsed = CloudModel.parseState(remote)
        val ids = parsed.requests.map { it.id }.toSet()
        val me = deviceId()
        val mine = CloudModel.freshRequests(st.requests.filter { it.by == me && it.id !in ids }, Instant.now())
        fun core(m: Map<String, Any?>) = Json.canonical(m.filterKeys { it != "meta" && it != "ring_requests" })
        if (core(local) != core(remote)) Toasts.show(CONFLICT_MSG, "info")
        applyState(st, parsed, rs)
        if (mine.isNotEmpty()) {
            st.requests = st.requests + mine
            schedule(Work.STATE, 0)
        }
    }

    private fun applyState(st: SyncState, s: CloudModel.State, rs: Entry) {
        val repo = Repo(app)
        val db = repo.raw()
        val today = LocalDate.now()
        db.beginTransaction()
        try {
            db.execSQL("INSERT OR REPLACE INTO settings(key, value) VALUES('paused', ?)", arrayOf(if (s.paused) "1" else "0"))
            db.execSQL("DELETE FROM overrides WHERE action IN ('SKIP_ONCE','PAUSE_DAY') AND date_yyyymmdd >= ?", arrayOf(today.format(DATE)))
            for (o in CloudModel.sharedOverrides(s.overrides, today)) {
                db.execSQL("INSERT INTO overrides(date_yyyymmdd, schedule_id, action, note) VALUES(?, ?, ?, ?)",
                    arrayOf<Any?>(o.date, o.scheduleId, o.action, o.note))
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        st.requests = s.requests
        st.base[CloudModel.STATE] = Base(rs.rev, rs.sha)
        st.lastState = CloudModel.contentHash(buildState(repo, st.requests))
        handleRequests(st)
        Alarms.reschedule(app)
        AppEvents.changed()
    }

    private fun pullLogs(api: CloudApi, st: SyncState) {
        val mine = CloudModel.logsPath(deviceId())
        val dir = CloudLogs.dir(app).apply { mkdirs() }
        var changed = false
        for ((p, r) in st.remote.toList()) {
            if (!p.startsWith(CloudModel.LOGS) || !p.endsWith(".json")) continue
            val name = p.removePrefix(CloudModel.LOGS).removeSuffix(".json")
            if ('/' in name) continue
            if (p == mine) {
                // 다른 곳에서 내 기록 파일이 바뀜 → 그 위에 다시 올린다
                if (r.live && st.base[p]?.rev != r.rev) { st.lastLogs = null; schedule(Work.LOGS, 0) }
                continue
            }
            val f = File(dir, CloudModel.safeId(name).ifEmpty { "device" } + ".json")
            if (r.live) {
                if (st.base[p]?.rev == r.rev && f.exists()) continue
                try {
                    val bytes = api.downloadBytes(p, r.sha)
                    val tmp = File(dir, ".${f.name}.tmp")
                    tmp.writeBytes(bytes)
                    if (!tmp.renameTo(f)) { f.delete(); tmp.renameTo(f) }
                    st.base[p] = Base(r.rev, r.sha)
                    changed = true
                } catch (e: CloudError) {
                    if (e.status == 401 || e.offline) throw e
                }
            } else if (r.deleted) {
                if (f.delete()) changed = true
                st.base.remove(p)
            }
        }
        if (changed) AppEvents.changed()
    }

    // ---------------------------------------------------------------- 울려 달라는 요청
    private fun handleRequests(st: SyncState) {
        val repo = Repo(app)
        val now = Instant.now()
        st.handled.entries.removeIf { now.toEpochMilli() - it.value > 24 * 3600_000L }
        if (!ringsHere(repo)) return
        val me = deviceId()
        for (r in CloudModel.dueRequests(st.requests.filter { it.by != me }, st.handled.keys, now)) {
            st.handled[r.id] = now.toEpochMilli()
            val detail = "forced · ${r.byName.ifBlank { "다른 기기" }}"
            val sid = r.scheduleId
            if (sid != null) {
                val s = repo.schedule(sid) ?: continue
                Scheduler.nextDateOf(repo, s)?.let { repo.addOverride(it, s.id, Scheduler.FIRED, "forced") }
                BellService.ringRemote(app, s.id, null, detail)
                Alarms.reschedule(app)
            } else {
                val soundId = r.soundId ?: continue
                if (repo.sound(soundId) == null) continue
                BellService.ringRemote(app, null, soundId, detail)
            }
        }
    }

    /** 종을 울리지 않는 기기의 '지금 울리기': state.json 에 요청을 넣는다. 로그인하지 않았으면 false */
    fun requestRing(scheduleId: Long?, soundId: Long?): Boolean {
        if (token == null) return false
        val req = CloudModel.RingRequest(UUID.randomUUID().toString(), scheduleId, soundId, CloudModel.iso(Instant.now()), deviceId(), deviceName())
        scope.launch {
            lock.withLock {
                val st = state()
                st.requests = st.requests + req
                save(st)
            }
            schedule(Work.STATE, 0)
        }
        return true
    }

    // ---------------------------------------------------------------- 올리기
    private fun exportConfig(api: CloudApi, st: SyncState) {
        if (_choice.value != null) return
        val rc = st.remote[CloudModel.CONFIG]
        if (st.base[CloudModel.CONFIG] == null && rc != null && rc.live) {
            schedule(Work.PULL, 0)   // 처음 연결: 받아서 정한 뒤에
            return
        }
        val repo = Repo(app)
        val cfg = buildConfig(repo)
        val hash = CloudModel.contentHash(cfg)
        val missing = rc == null || !rc.live
        if (hash == st.lastConfig && !missing) return
        val files = CloudModel.soundFiles(cfg)
        for (fn in files) uploadSound(api, st, fn)     // 종소리 파일 먼저
        val entry = try {
            api.upload(CloudModel.CONFIG, Json.write(cfg).toByteArray(Charsets.UTF_8), rc?.rev ?: 0)
        } catch (e: CloudError) {
            if (e.status != 409) throw e
            e.entry?.let { st.remote[CloudModel.CONFIG] = it }
            configConflict(api, st, cfg)
            return
        }
        st.remote[CloudModel.CONFIG] = entry
        st.base[CloudModel.CONFIG] = Base(entry.rev, entry.sha)
        val removed = CloudModel.removedSoundFiles(st.lastConfigFiles, files)
        st.lastConfig = hash
        st.lastConfigFiles = files
        // 지운 종소리 파일은 서버에서도 지운다 (config.json 을 올린 뒤에)
        for (fn in removed) {
            val p = CloudModel.soundPath(fn)
            val r = st.remote[p] ?: continue
            if (!r.live) continue
            try {
                api.delete(p, r.rev)?.let { st.remote[p] = it }
                st.base.remove(p)
            } catch (e: CloudError) {
                if (e.status == 401 || e.offline) throw e
                e.entry?.let { st.remote[p] = it }
            }
        }
    }

    /** 올리려는데 다른 기기가 먼저 바꿈 → 서버 것을 쓴다 */
    private fun configConflict(api: CloudApi, st: SyncState, local: Map<String, Any?>) {
        val rc = st.remote[CloudModel.CONFIG]
        if (rc == null || !rc.live) {
            schedule(Work.FULL, 0); return
        }
        val remote = fetchJson(api, CloudModel.CONFIG, rc)?.takeIf { CloudModel.isConfig(it) } ?: return
        if (CloudModel.contentHash(remote) == CloudModel.contentHash(local)) {
            st.base[CloudModel.CONFIG] = Base(rc.rev, rc.sha)
            st.lastConfig = CloudModel.contentHash(local)
            st.lastConfigFiles = CloudModel.soundFiles(local)
            return
        }
        if (applyConfig(api, st, remote, rc)) Toasts.show(CONFLICT_MSG, "info")
    }

    private fun uploadSound(api: CloudApi, st: SyncState, fn: String) {
        val p = CloudModel.soundPath(fn)
        val f = Sounds.file(app, fn)
        if (!f.isFile) return
        val sha = localSha(st, fn) ?: return
        when (val op = CloudModel.planSoundPush(sha, st.base[p], st.remote[p])) {
            CloudModel.Push.None -> {}
            CloudModel.Push.Record -> st.base[p] = Base(st.remote[p]!!.rev, sha)
            is CloudModel.Push.Upload -> {
                val e = try {
                    api.uploadFile(p, f, sha, op.baseRev)
                } catch (err: CloudError) {
                    if (err.status != 409) throw err
                    // 시간표가 이 파일을 쓰니 서버 것 위에 다시 올린다
                    api.uploadFile(p, f, sha, err.entry?.rev ?: 0)
                }
                st.remote[p] = e
                st.base[p] = Base(e.rev, sha)
            }
        }
    }

    private fun exportState(api: CloudApi, st: SyncState) {
        val rs = st.remote[CloudModel.STATE]
        if (st.base[CloudModel.STATE] == null && rs != null && rs.live) {
            schedule(Work.PULL, 0); return
        }
        val repo = Repo(app)
        val missing = rs == null || !rs.live
        if (CloudModel.contentHash(buildState(repo, st.requests)) == st.lastState && !missing) return
        st.requests = CloudModel.freshRequests(st.requests, Instant.now())   // 쓸 때 10분 지난 요청은 뺀다
        val file = buildState(repo, st.requests)
        val entry = try {
            api.upload(CloudModel.STATE, Json.write(file).toByteArray(Charsets.UTF_8), rs?.rev ?: 0)
        } catch (e: CloudError) {
            if (e.status != 409) throw e
            val r = e.entry ?: run { schedule(Work.FULL, 0); return }
            st.remote[CloudModel.STATE] = r
            if (!r.live) { schedule(Work.STATE, 0); return }
            val remote = fetchJson(api, CloudModel.STATE, r)?.takeIf { CloudModel.isState(it) } ?: return
            if (CloudModel.contentHash(remote) == CloudModel.contentHash(file)) {
                st.base[CloudModel.STATE] = Base(r.rev, r.sha)
                st.lastState = CloudModel.contentHash(file)
            } else {
                stateConflict(st, file, remote, r)
            }
            return
        }
        st.remote[CloudModel.STATE] = entry
        st.base[CloudModel.STATE] = Base(entry.rev, entry.sha)
        st.lastState = CloudModel.contentHash(file)
    }

    private fun exportLogs(api: CloudApi, st: SyncState) {
        val id = deviceId()
        val p = CloudModel.logsPath(id)
        val rows = Repo(app).logRowsSince(LocalDate.now().minusDays(CloudModel.LOG_DAYS), CloudModel.LOG_MAX)
        val file = CloudModel.logsFile(id, deviceName(), rows)
        val hash = CloudModel.contentHash(file)
        val r = st.remote[p]
        if (hash == st.lastLogs && r != null && r.live) return
        val bytes = Json.write(file).toByteArray(Charsets.UTF_8)
        val entry = try {
            api.upload(p, bytes, r?.rev ?: 0)
        } catch (e: CloudError) {
            if (e.status != 409) throw e
            api.upload(p, bytes, e.entry?.rev ?: 0)      // 내 기록 파일은 내 것이 맞다 → 그 위에 다시
        }
        st.remote[p] = entry
        st.base[p] = Base(entry.rev, entry.sha)
        st.lastLogs = hash
    }

    // ---------------------------------------------------------------- 이 기기 데이터 ↔ 파일 내용
    private fun meta() = CloudModel.meta(deviceId(), deviceName(), Instant.now())

    private fun cell(c: Cursor, i: Int): Any? = when (c.getType(i)) {
        Cursor.FIELD_TYPE_NULL -> null
        Cursor.FIELD_TYPE_INTEGER -> c.getLong(i)
        Cursor.FIELD_TYPE_FLOAT -> c.getDouble(i)
        else -> c.getString(i)
    }

    fun buildConfig(repo: Repo): Map<String, Any?> {
        val db = repo.raw()
        val tables = CloudModel.TABLES.mapValues { (t, cols) ->
            db.rawQuery("SELECT ${cols.joinToString(", ")} FROM $t ORDER BY id", null).use { c ->
                buildList { while (c.moveToNext()) add(LinkedHashMap<String, Any?>().apply { cols.forEachIndexed { i, col -> put(col, cell(c, i)) } }) }
            }
        }
        val active = db.rawQuery("SELECT value FROM settings WHERE key='active_set_id'", null).use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        }
        return CloudModel.configFile(tables, active, meta())
    }

    private fun buildState(repo: Repo, requests: List<CloudModel.RingRequest>): Map<String, Any?> {
        val today = LocalDate.now()
        val ov = repo.raw().rawQuery(
            "SELECT date_yyyymmdd, schedule_id, action, note FROM overrides WHERE action IN ('SKIP_ONCE','PAUSE_DAY') AND date_yyyymmdd >= ?",
            arrayOf(today.format(DATE))
        ).use { c -> buildList { while (c.moveToNext()) add(CloudModel.Override(c.getString(0), c.getLong(1), c.getString(2), c.getString(3) ?: "")) } }
        return CloudModel.stateFile(Scheduler.isPaused(repo), ov, requests, today, meta())
    }

    private fun scheduleTimes(db: SQLiteDatabase): Map<Long, String> =
        db.rawQuery("SELECT id, time_hhmm FROM schedules", null).use { c -> buildMap { while (c.moveToNext()) put(c.getLong(0), c.getString(1)) } }

    /**
     * 받은 config.json 으로 시간표·세트·종소리 줄을 바꾼다 (ID 그대로). 기록과 이 기기 설정은 그대로.
     * 시간표가 없어졌거나 시각이 바뀐 일정의 FIRED_ONCE·SKIP_ONCE 만 지운다. 지운 게 있으면 true.
     */
    private fun writeConfig(cfg: Map<String, Any?>): Boolean {
        val db = Repo(app).raw()
        var removedSkip = false
        db.beginTransaction()
        try {
            val oldTimes = scheduleTimes(db)
            db.execSQL("DELETE FROM schedules")
            db.execSQL("DELETE FROM schedule_sets")
            db.execSQL("DELETE FROM sounds")
            for ((table, cols) in CloudModel.TABLES) {
                for (row0 in CloudModel.rows(cfg, table)) {
                    val row = if (table == "sounds") row0 + ("file_name" to (row0["file_name"].jStr() ?: "").substringAfterLast('/').substringAfterLast('\\')) else row0
                    if (row["id"].jLong() == null) continue
                    val present = cols.filter { row.containsKey(it) }
                    db.execSQL("INSERT INTO $table (${present.joinToString(", ")}) VALUES (${present.joinToString(", ") { "?" }})",
                        present.map { row[it] }.toTypedArray())
                }
            }
            if (CloudModel.rows(cfg, "schedule_sets").isEmpty()) db.execSQL("INSERT INTO schedule_sets(name) VALUES('기본')")
            cfg["settings"].jObj()?.get("active_set_id")?.let {
                db.execSQL("INSERT OR REPLACE INTO settings(key, value) VALUES('active_set_id', ?)", arrayOf(it.jStr()))
            }
            val valid = db.rawQuery(
                "SELECT 1 FROM schedule_sets WHERE id=(SELECT CAST(value AS INTEGER) FROM settings WHERE key='active_set_id')", null
            ).use { it.moveToFirst() }
            if (!valid) {
                val first = db.rawQuery("SELECT id FROM schedule_sets ORDER BY id LIMIT 1", null).use { it.moveToFirst(); it.getLong(0) }
                db.execSQL("INSERT OR REPLACE INTO settings(key, value) VALUES('active_set_id', ?)", arrayOf(first.toString()))
            }
            val newTimes = scheduleTimes(db)
            val ids = db.rawQuery("SELECT DISTINCT schedule_id FROM overrides WHERE action IN ('SKIP_ONCE','FIRED_ONCE')", null)
                .use { c -> buildList { while (c.moveToNext()) add(c.getLong(0)) } }
            val stale = CloudModel.staleOverrideSchedules(ids, oldTimes, newTimes)
            if (stale.isNotEmpty()) {
                val q = stale.joinToString(",") { "?" }
                removedSkip = db.rawQuery("SELECT 1 FROM overrides WHERE action='SKIP_ONCE' AND schedule_id IN ($q) LIMIT 1",
                    stale.map { it.toString() }.toTypedArray()).use { it.moveToFirst() }
                db.execSQL("DELETE FROM overrides WHERE action IN ('SKIP_ONCE','FIRED_ONCE') AND schedule_id IN ($q)", stale.toTypedArray<Any>())
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        return removedSkip
    }

    private fun localSha(st: SyncState, fn: String): String? {
        val f = Sounds.file(app, fn)
        if (!f.isFile) return null
        val sig = st.cache[fn]
        if (sig != null && sig.size == f.length() && sig.mtime == f.lastModified()) return sig.sha
        val md = MessageDigest.getInstance("SHA-256")
        f.inputStream().use { input ->
            val buf = ByteArray(64 * 1024)
            while (true) {
                val n = input.read(buf)
                if (n < 0) break
                md.update(buf, 0, n)
            }
        }
        val sha = md.digest().joinToString("") { "%02x".format(it) }
        st.cache[fn] = CloudModel.FileSig(f.length(), f.lastModified(), sha)
        return sha
    }

    // ---------------------------------------------------------------- 동기화 상태 파일
    private fun stateFile() = File(app.filesDir, "cloud/sync.json")

    private fun state(): SyncState = sync ?: runCatching {
        SyncState.from(Json.parse(stateFile().readText()).jObj())
    }.getOrElse { SyncState() }.also { sync = it }

    private fun save(st: SyncState) {
        try {
            val f = stateFile()
            f.parentFile?.mkdirs()
            val tmp = File(f.parentFile, "sync.json.tmp")
            tmp.writeText(Json.write(st.toMap(), 0))
            if (!tmp.renameTo(f)) { f.delete(); tmp.renameTo(f) }
        } catch (_: Exception) {
        }
    }

    /** 다른 계정으로 로그인할 때: 맞춘 기록과 다른 기기 기록을 지운다 (이 기기 시간표는 그대로) */
    private fun resetLocal() {
        sync = SyncState()
        stateFile().delete()
        CloudLogs.clear(app)
        synchronized(due) { due.clear() }
        _choice.value = null
        pendingRemote = null
    }

    // ---------------------------------------------------------------- 로그인 · 로그아웃
    /** 로그인. 실패하면 사용자에게 보여 줄 문구, 성공하면 null */
    suspend fun login(serverInput: String, username: String, password: String, ringHere: Boolean): String? = withContext(Dispatchers.IO) {
        val srv = CloudModel.normalizeServer(serverInput)
        if (srv.isEmpty()) return@withContext "서버 주소를 입력해 주세요."
        val device = linkedMapOf("id" to deviceId(), "name" to deviceName(), "platform" to "android", "version" to BuildConfig.VERSION_NAME)
        val res = try {
            CloudApi(srv, null).login(username.trim(), password, device)
        } catch (e: CloudError) {
            return@withContext if (e.status == 404) "이 주소에서 통합 클라우드 서버를 찾지 못했어요. 주소를 확인해 주세요." else e.message
        }
        val tok = res["token"].jStr() ?: return@withContext "서버 응답을 읽지 못했어요."
        val user = res["user"].jObj() ?: emptyMap()
        val allowed = user["allowedApps"]
        if (allowed is List<*> && allowed.none { it == CloudModel.APP_ID }) {
            runCatching { CloudApi(srv, tok).logout() }
            return@withContext "이 계정은 마고 타종을 쓸 수 없어요. 원장님이나 운영자에게 문의해 주세요."
        }
        val uname = user["username"].jStr() ?: username.trim().lowercase()
        val name = user["name"].jStr() ?: ""
        lock.withLock {
            val repo = Repo(app)
            val same = repo.setting(K_SERVER, "") == srv && repo.setting(K_USERNAME, "") == uname
            if (!same) resetLocal()
            repo.setSetting(K_SERVER, srv)
            repo.setSetting(K_USERNAME, uname)
            repo.setSetting(K_NAME, name)
            repo.setSetting(K_TOKEN, Secret.encrypt(tok))
            repo.setSetting(K_RING, if (ringHere) "1" else "0")
            server = srv
            token = tok
            _status.value = Status(loggedIn = true, server = srv, username = uname, name = name,
                lastSync = repo.setting(K_LAST_SYNC, "").toLongOrNull() ?: 0)
        }
        accountChanged()
        CloudService.cancelLoginNotice(app)
        schedule(Work.FULL, 0)
        null
    }

    /**
     * 로그아웃: 로그인 화면으로 돌아가고, 다시 로그인할 때까지 이 기기에서 종을 울리지 않는다.
     * 이 기기 시간표·종소리와 맞춘 기록은 그대로 둬서 같은 계정으로 다시 로그인하면 이어서 맞춘다.
     */
    suspend fun logout() = withContext(Dispatchers.IO) {
        val t = token
        val srv = server
        token = null
        lock.withLock {
            Repo(app).setSetting(K_TOKEN, "")
            synchronized(due) { due.clear() }
            _choice.value = null
            pendingRemote = null
            _status.value = _status.value.copy(loggedIn = false, conn = Conn.OFF, syncing = false, message = "")
        }
        accountChanged()
        if (t != null) runCatching { CloudApi(srv, t).logout() }
    }

    /** 세션이 끝났을 때(401): 로그아웃과 같이 로그인 화면으로 돌아가고, 종을 울리지 않게 된 것을 알림으로 알린다 */
    fun unauthorized(message: String) {
        if (token == null) return
        val rang = ringsHere(Repo(app))
        token = null
        Repo(app).setSetting(K_TOKEN, "")
        synchronized(due) { due.clear() }
        _choice.value = null
        pendingRemote = null
        _status.value = _status.value.copy(loggedIn = false, conn = Conn.OFF, syncing = false,
            message = message.ifBlank { "로그인이 끝났어요. 다시 로그인해 주세요." })
        accountChanged()
        CloudService.notifyLogin(app, if (rang) "로그인이 끝나서 이 기기에서 종을 울리지 않아요. 다시 로그인해 주세요."
            else "클라우드 로그인이 끝났어요. 다시 로그인해 주세요.")
    }

    private fun accountChanged() {
        Alarms.reschedule(app)
        CloudEvents.update()
        CloudService.sync(app)
        AppEvents.changed()
    }

    // ---------------------------------------------------------------- 처음 연결할 때 고르기
    /** 클라우드 시간표 쓰기: 이 기기 것은 먼저 filesDir/backups 에 백업해 둔다 */
    fun chooseCloud() {
        scope.launch {
            lock.withLock {
                val (cfg, rc) = pendingRemote ?: return@withLock
                val t = token ?: return@withLock
                val st = state()
                try {
                    val dir = File(app.filesDir, "backups").apply { mkdirs() }
                    val f = File(dir, "클라우드_연결_전_" + Backup.defaultBackupName())
                    f.outputStream().use { Backup.export(app, it) }
                    if (applyConfig(CloudApi(server, t), st, cfg, rc)) {
                        pullSoundDeletes(st)
                        pendingRemote = null
                        _choice.value = null
                        Toasts.show("클라우드 시간표로 맞췄어요. 이 기기 시간표는 백업해 두었어요", "success")
                    } else {
                        Toasts.show(problem ?: "클라우드 시간표를 넣지 못했어요", "error")
                    }
                } catch (e: CloudError) {
                    if (e.status == 401) unauthorized(e.message ?: "") else Toasts.show(e.message ?: "맞추지 못했어요", "error")
                } catch (e: Exception) {
                    Toasts.show("맞추지 못했어요: ${e.message ?: e}", "error")
                } finally {
                    save(st)
                }
            }
            schedule(Work.FULL, 0)
        }
    }

    /** 이 기기 시간표로 바꾸기: 서버 것을 '마지막으로 맞춘 것'으로 두고 이 기기 것을 그 위에 올린다 */
    fun chooseLocal() {
        scope.launch {
            lock.withLock {
                val (cfg, rc) = pendingRemote ?: return@withLock
                val st = state()
                st.base[CloudModel.CONFIG] = Base(rc.rev, rc.sha)
                st.lastConfig = CloudModel.contentHash(cfg)
                st.lastConfigFiles = CloudModel.soundFiles(cfg)
                pendingRemote = null
                _choice.value = null
                save(st)
            }
            schedule(Work.FULL, 0)
            Toasts.show("이 기기 시간표를 클라우드에 올릴게요", "success")
        }
    }

    // ---------------------------------------------------------------- 토큰 암호화
    private object Secret {
        private const val ALIAS = "magoedu_cloud_token"

        private fun key(): SecretKey {
            val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
            val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
            gen.init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build())
            return gen.generateKey()
        }

        /** "k1:iv:암호문" (Keystore 를 못 쓰는 기기에서만 "p1:토큰") */
        fun encrypt(plain: String): String = try {
            val c = Cipher.getInstance("AES/GCM/NoPadding")
            c.init(Cipher.ENCRYPT_MODE, key())
            val ct = c.doFinal(plain.toByteArray(Charsets.UTF_8))
            "k1:" + Base64.encodeToString(c.iv, Base64.NO_WRAP) + ":" + Base64.encodeToString(ct, Base64.NO_WRAP)
        } catch (e: Exception) {
            "p1:$plain"
        }

        fun decrypt(s: String): String? {
            if (s.isBlank()) return null
            if (s.startsWith("p1:")) return s.removePrefix("p1:").ifEmpty { null }
            val parts = s.split(':')
            if (parts.size != 3 || parts[0] != "k1") return null
            return try {
                val c = Cipher.getInstance("AES/GCM/NoPadding")
                c.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(parts[1], Base64.NO_WRAP)))
                String(c.doFinal(Base64.decode(parts[2], Base64.NO_WRAP)), Charsets.UTF_8)
            } catch (e: Exception) {
                null   // 다른 기기로 옮긴 백업 등 → 다시 로그인
            }
        }
    }
}

/** 클라우드로 받은 다른 기기의 기록 (filesDir/cloud/logs/<기기>.json) */
object CloudLogs {
    private data class Cached(val mtime: Long, val size: Long, val entries: List<LogEntry>)

    private val cache = HashMap<String, Cached>()

    fun dir(ctx: Context): File = File(ctx.filesDir, "cloud/logs")

    fun others(ctx: Context): List<LogEntry> {
        val files = dir(ctx).listFiles { f -> f.isFile && f.name.endsWith(".json") && !f.name.startsWith(".") } ?: return emptyList()
        synchronized(cache) {
            val out = ArrayList<LogEntry>()
            for (f in files) {
                val hit = cache[f.name]?.takeIf { it.mtime == f.lastModified() && it.size == f.length() }
                val c = hit ?: Cached(f.lastModified(), f.length(), read(f)).also { cache[f.name] = it }
                out.addAll(c.entries)
            }
            cache.keys.retainAll(files.map { it.name }.toSet())
            return out
        }
    }

    private fun read(f: File): List<LogEntry> = try {
        val d = CloudModel.parseLogs(Json.parse(f.readText()).jObj() ?: emptyMap())
        val name = d?.deviceName?.ifBlank { null } ?: "다른 기기"
        d?.rows?.map { LogEntry(-1, it.at, it.scheduleId, it.scheduleName, it.soundName, it.result, it.detail, name) } ?: emptyList()
    } catch (e: Exception) {
        emptyList()
    }

    fun clear(ctx: Context) {
        dir(ctx).deleteRecursively()
        synchronized(cache) { cache.clear() }
    }
}
