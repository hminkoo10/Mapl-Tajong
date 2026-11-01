package com.milky.mataf.core

import com.milky.mataf.data.TimeUtil
import java.security.MessageDigest
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.temporal.ChronoUnit

/**
 * 클라우드 동기화 파일 형식과 판단 규칙 (docs/cloud-sync.md). 안드로이드에 기대지 않아 JVM 시험으로 확인한다.
 */
object CloudModel {
    const val APP_ID = "tajong"
    const val APP = "MaplTajong"
    const val FORMAT = 1
    const val CONFIG = "config.json"
    const val STATE = "state.json"
    const val SOUNDS = "sounds/"
    const val LOGS = "logs/"
    const val SKIP = "SKIP_ONCE"
    const val PAUSE_DAY = "PAUSE_DAY"

    /** 울려 달라는 요청을 쓸 때 이보다 오래된 것은 지운다 */
    const val REQUEST_KEEP_MIN = 10L
    /** 울리는 기기는 지금 ±이 시간 안의 요청만 울린다 */
    const val REQUEST_WINDOW_SEC = 120L
    const val LOG_DAYS = 60L
    const val LOG_MAX = 5000

    /** config.json 에 넣는 표와 열 (백업 data.json 과 같다) */
    val TABLES: LinkedHashMap<String, List<String>> = linkedMapOf(
        "sounds" to listOf("id", "name", "file_name", "volume", "created_at"),
        "schedule_sets" to listOf("id", "name", "created_at"),
        "schedules" to listOf("id", "set_id", "name", "weekday_mask", "time_hhmm", "sound_id", "volume_override",
            "enabled", "sort_order", "created_at", "updated_at"),
    )

    private val DEFAULT_SOUND = Regex("^bell[1-8]\\.wav$")
    private val SAFE_FILE = Regex("^[^/\\\\:*?\"<>|\\x00-\\x1f]+$")

    // ---------------------------------------------------------------- 공통
    fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    fun sha256(text: String): String = sha256(text.toByteArray(Charsets.UTF_8))

    fun meta(deviceId: String, deviceName: String, at: Instant): Map<String, Any?> =
        linkedMapOf("device_id" to deviceId, "device_name" to deviceName, "at" to iso(at))

    fun iso(at: Instant): String = at.truncatedTo(ChronoUnit.SECONDS).toString()

    /** UTC ISO 8601 ('Z' 또는 +09:00 같은 오프셋, 오프셋이 없으면 UTC 로 본다) */
    fun parseInstant(s: String?): Instant? {
        if (s.isNullOrBlank()) return null
        val t = s.trim()
        return runCatching { Instant.parse(t) }.getOrNull()
            ?: runCatching { OffsetDateTime.parse(t).toInstant() }.getOrNull()
            ?: runCatching { LocalDateTime.parse(t).toInstant(ZoneOffset.UTC) }.getOrNull()
    }

    /** 내용 비교용 값: meta 를 뺀 정규화 JSON */
    fun content(file: Map<String, Any?>): String = Json.canonical(file.filterKeys { it != "meta" })

    fun contentHash(file: Map<String, Any?>): String = sha256(content(file))

    /** 기기 ID 를 파일 이름으로 쓸 수 있게: A-Z a-z 0-9 _ - 만 남긴다 */
    fun safeId(id: String): String = id.filter { it in 'A'..'Z' || it in 'a'..'z' || it in '0'..'9' || it == '_' || it == '-' }

    fun logsPath(deviceId: String): String = "$LOGS${safeId(deviceId)}.json"

    /** 서버 경로로 쓸 수 있는 종소리 파일 이름인지 (폴더 없이, 끝이 점·공백이 아니게) */
    fun validFileName(fn: String): Boolean =
        fn.isNotEmpty() && fn.length <= 200 && fn != "." && fn != ".." && SAFE_FILE.matches(fn) && !fn.endsWith(".") && !fn.endsWith(" ")

    fun soundPath(fn: String): String = SOUNDS + fn

    /** 'sounds/x.wav' → 'x.wav' (하위 폴더나 이상한 이름이면 null) */
    fun soundName(path: String): String? {
        if (!path.startsWith(SOUNDS)) return null
        val fn = path.removePrefix(SOUNDS)
        return fn.takeIf { '/' !in it && validFileName(it) }
    }

    // ---------------------------------------------------------------- config.json
    fun configFile(tables: Map<String, List<Map<String, Any?>>>, activeSetId: String?, meta: Map<String, Any?>): Map<String, Any?> {
        val m = linkedMapOf<String, Any?>("app" to APP, "kind" to "config", "format" to FORMAT)
        for ((t, cols) in TABLES) {
            m[t] = (tables[t] ?: emptyList()).sortedBy { it["id"].jLong() ?: Long.MAX_VALUE }
                .map { row -> LinkedHashMap<String, Any?>().apply { cols.forEach { c -> if (row.containsKey(c)) put(c, row[c]) } } }
        }
        m["settings"] = if (activeSetId != null) linkedMapOf("active_set_id" to activeSetId) else linkedMapOf<String, Any?>()
        m["meta"] = meta
        return m
    }

    fun isConfig(m: Map<String, Any?>?): Boolean = m != null && m["app"] == APP && (m["kind"] == null || m["kind"] == "config") &&
        ((m["format"].jLong() ?: 1L) <= FORMAT)

    fun rows(cfg: Map<String, Any?>, table: String): List<Map<String, Any?>> = cfg[table].jList().mapNotNull { it.jObj() }

    /** 종소리 파일 이름들 */
    fun soundFiles(cfg: Map<String, Any?>?): Set<String> =
        if (cfg == null) emptySet() else rows(cfg, "sounds").mapNotNull { it["file_name"].jStr()?.substringAfterLast('/')?.substringAfterLast('\\') }
            .filter { validFileName(it) }.toSet()

    /** 처음 설치한 그대로인지: 일정 없음, 세트 하나 이하, 기본 종소리(bell1~8)만 */
    fun isDefaultConfig(cfg: Map<String, Any?>): Boolean =
        rows(cfg, "schedules").isEmpty() && rows(cfg, "schedule_sets").size <= 1 &&
            rows(cfg, "sounds").all { DEFAULT_SOUND.matches(it["file_name"].jStr() ?: "") }

    data class Counts(val schedules: Int, val sets: Int, val sounds: Int)

    fun counts(cfg: Map<String, Any?>): Counts =
        Counts(rows(cfg, "schedules").size, rows(cfg, "schedule_sets").size, rows(cfg, "sounds").size)

    /**
     * 받은 config.json 을 적용할 때 지울 이 기기의 FIRED_ONCE·SKIP_ONCE 의 일정 ID:
     * 시간표가 없어졌거나 시각이 바뀐 것만.
     */
    fun staleOverrideSchedules(overrideIds: Collection<Long>, oldTimes: Map<Long, String>, newTimes: Map<Long, String>): Set<Long> =
        overrideIds.filter { id -> id != 0L && (id !in newTimes || (oldTimes[id] != null && oldTimes[id] != newTimes[id])) }.toSet()

    // ---------------------------------------------------------------- state.json
    data class Override(val date: String, val scheduleId: Long, val action: String, val note: String) {
        fun toMap(): Map<String, Any?> = linkedMapOf("date" to date, "schedule_id" to scheduleId, "action" to action, "note" to note)
    }

    data class RingRequest(val id: String, val scheduleId: Long?, val soundId: Long?, val at: String, val by: String, val byName: String) {
        val instant: Instant? get() = parseInstant(at)
        fun toMap(): Map<String, Any?> = linkedMapOf("id" to id, "schedule_id" to scheduleId, "sound_id" to soundId, "at" to at,
            "by" to by, "by_name" to byName)

        companion object {
            fun from(m: Map<String, Any?>?): RingRequest? {
                if (m == null) return null
                val id = m["id"].jStr()?.takeIf { it.isNotBlank() } ?: return null
                val sched = m["schedule_id"].jLong()?.takeIf { it > 0 }
                val sound = m["sound_id"].jLong()?.takeIf { it > 0 }
                if (sched == null && sound == null) return null
                return RingRequest(id, sched, sound, m["at"].jStr() ?: "", m["by"].jStr() ?: "", m["by_name"].jStr() ?: "")
            }
        }
    }

    data class State(val paused: Boolean, val overrides: List<Override>, val requests: List<RingRequest>)

    /** 오늘과 그 뒤 날짜의 SKIP_ONCE·PAUSE_DAY 만, 같은 것은 하나로, 날짜·일정 순 */
    fun sharedOverrides(all: List<Override>, today: LocalDate): List<Override> {
        val t = today.toString()
        return all.filter { (it.action == SKIP || it.action == PAUSE_DAY) && it.date >= t }
            .map { if (it.action == PAUSE_DAY) it.copy(scheduleId = 0) else it }
            .distinctBy { Triple(it.date, it.scheduleId, it.action) }
            .sortedWith(compareBy({ it.date }, { it.scheduleId }, { it.action }))
    }

    /** 10분 넘게 지난 요청은 뺀다 (시각을 읽을 수 없는 것도) */
    fun freshRequests(requests: List<RingRequest>, now: Instant): List<RingRequest> {
        val limit = now.minus(Duration.ofMinutes(REQUEST_KEEP_MIN))
        return requests.filter { r -> r.instant?.let { !it.isBefore(limit) } == true }.distinctBy { it.id }
    }

    fun stateFile(paused: Boolean, overrides: List<Override>, requests: List<RingRequest>, today: LocalDate,
                  meta: Map<String, Any?>): Map<String, Any?> = linkedMapOf(
        "app" to APP, "kind" to "state", "format" to FORMAT,
        "paused" to paused,
        "overrides" to sharedOverrides(overrides, today).map { it.toMap() },
        "ring_requests" to requests.distinctBy { it.id }.map { it.toMap() },
        "meta" to meta,
    )

    fun isState(m: Map<String, Any?>?): Boolean = m != null && m["app"] == APP && m["kind"] == "state" &&
        ((m["format"].jLong() ?: 1L) <= FORMAT)

    fun parseState(m: Map<String, Any?>): State {
        val paused = when (val p = m["paused"]) {
            is Boolean -> p
            else -> p.jLong() == 1L
        }
        val ov = m["overrides"].jList().mapNotNull { it.jObj() }.mapNotNull { o ->
            val date = o["date"].jStr()?.trim()?.takeIf { runCatching { LocalDate.parse(it) }.isSuccess } ?: return@mapNotNull null
            val action = o["action"].jStr() ?: return@mapNotNull null
            if (action != SKIP && action != PAUSE_DAY) return@mapNotNull null
            Override(date, if (action == PAUSE_DAY) 0 else o["schedule_id"].jLong() ?: return@mapNotNull null, action, o["note"].jStr() ?: "")
        }
        val req = m["ring_requests"].jList().mapNotNull { RingRequest.from(it.jObj()) }
        return State(paused, ov, req)
    }

    /** 처음 보는 요청 중 시각이 지금 ±2분 안인 것 */
    fun dueRequests(requests: List<RingRequest>, handled: Set<String>, now: Instant): List<RingRequest> =
        requests.filter { r ->
            if (r.id in handled) return@filter false
            val at = r.instant ?: return@filter false
            Math.abs(Duration.between(at, now).seconds) <= REQUEST_WINDOW_SEC
        }.distinctBy { it.id }

    // ---------------------------------------------------------------- logs/<기기>.json
    fun logsFile(deviceId: String, deviceName: String, rows: List<Map<String, Any?>>): Map<String, Any?> = linkedMapOf(
        "app" to APP, "kind" to "logs", "format" to FORMAT,
        "device_id" to deviceId, "device_name" to deviceName,
        "logs" to rows.takeLast(LOG_MAX).map { r ->
            linkedMapOf("occurred_at" to r["occurred_at"], "schedule_id" to r["schedule_id"], "schedule_name" to (r["schedule_name"] ?: ""),
                "sound_name" to (r["sound_name"] ?: ""), "result" to r["result"], "detail" to (r["detail"] ?: ""))
        },
    )

    data class LogRow(val at: String, val scheduleId: Long?, val scheduleName: String, val soundName: String, val result: String,
                      val detail: String)

    data class DeviceLogs(val deviceId: String, val deviceName: String, val rows: List<LogRow>)

    fun parseLogs(m: Map<String, Any?>): DeviceLogs? {
        if (m["app"] != APP || m["kind"] != "logs") return null
        val rows = m["logs"].jList().mapNotNull { it.jObj() }.mapNotNull { r ->
            val at = r["occurred_at"].jStr() ?: return@mapNotNull null
            val result = r["result"].jStr() ?: return@mapNotNull null
            LogRow(at, r["schedule_id"].jLong(), r["schedule_name"].jStr() ?: "", r["sound_name"].jStr() ?: "", result, r["detail"].jStr() ?: "")
        }
        return DeviceLogs(m["device_id"].jStr() ?: "", m["device_name"].jStr() ?: "", rows)
    }

    // ---------------------------------------------------------------- 서버 목록
    data class Entry(val path: String, val rev: Long, val seq: Long, val sha: String?, val size: Long, val deleted: Boolean,
                     val evicted: Boolean, val deviceId: String?) {
        val live: Boolean get() = !deleted && !evicted

        fun toMap(): Map<String, Any?> = linkedMapOf("path" to path, "rev" to rev, "seq" to seq, "sha256" to sha, "size" to size,
            "deleted" to deleted, "evicted" to evicted, "deviceId" to deviceId)

        companion object {
            fun from(m: Map<String, Any?>?): Entry? {
                if (m == null) return null
                val path = m["path"].jStr() ?: return null
                return Entry(path, m["rev"].jLong() ?: 0, m["seq"].jLong() ?: 0, m["sha256"].jStr()?.lowercase(), m["size"].jLong() ?: 0,
                    m["deleted"] == true, m["evicted"] == true, m["deviceId"].jStr())
            }
        }
    }

    /** 마지막으로 맞춘 파일 상태 */
    data class Base(val rev: Long, val sha: String?)

    // ---------------------------------------------------------------- 판단
    enum class Pull { NONE, RECORD, APPLY, CONFLICT, ASK, UPLOAD }

    /**
     * 서버 목록을 보고 config.json 을 어떻게 할지.
     * localHash: 지금 이 기기 내용, lastHash: 마지막으로 맞춘 내용, remoteHash: 서버 내용(받아야 알 때만)
     */
    fun decideConfig(base: Base?, remote: Entry?, localHash: String, lastHash: String?, remoteHash: String?, localDefault: Boolean): Pull {
        if (remote == null || remote.deleted) return Pull.UPLOAD     // 클라우드가 비었음 → 이 기기 것을 올림
        if (remote.evicted) return Pull.NONE
        if (base == null) {
            return when {
                remoteHash == localHash -> Pull.RECORD
                localDefault -> Pull.APPLY
                else -> Pull.ASK
            }
        }
        if (remote.rev == base.rev) return Pull.NONE
        return changed(localHash, lastHash, remoteHash)
    }

    /** state.json: 처음 연결하면 서버 것을 쓰고, 그 뒤로는 config 와 같다 */
    fun decideState(base: Base?, remote: Entry?, localHash: String, lastHash: String?, remoteHash: String?): Pull {
        if (remote == null || remote.deleted) return Pull.UPLOAD
        if (remote.evicted) return Pull.NONE
        if (base == null) return if (remoteHash == localHash) Pull.RECORD else Pull.APPLY
        if (remote.rev == base.rev) return Pull.NONE
        return changed(localHash, lastHash, remoteHash)
    }

    private fun changed(localHash: String, lastHash: String?, remoteHash: String?): Pull = when {
        remoteHash == localHash -> Pull.RECORD
        localHash == lastHash -> Pull.APPLY
        else -> Pull.CONFLICT      // 둘 다 바뀜 → 서버에 먼저 올라간 것을 쓴다
    }

    enum class FileOp { NONE, RECORD, DOWNLOAD, DELETE_LOCAL, FORGET }

    /** 받을 때 종소리 파일 하나 (referenced: 이 기기 시간표가 이 파일을 쓰는지) */
    fun planSoundPull(localSha: String?, base: Base?, remote: Entry?, referenced: Boolean): FileOp {
        if (remote == null || remote.evicted) return FileOp.NONE
        if (remote.deleted) {
            if (base == null) return FileOp.NONE
            return if (!referenced && localSha != null && localSha == base.sha) FileOp.DELETE_LOCAL else FileOp.FORGET
        }
        if (localSha != null && localSha == remote.sha) {
            return if (base == null || base.rev != remote.rev || base.sha != localSha) FileOp.RECORD else FileOp.NONE
        }
        if (base != null && base.rev == remote.rev) return FileOp.NONE   // 서버는 그대로, 바뀐 건 이 기기 → 올릴 때 처리
        return FileOp.DOWNLOAD
    }

    sealed interface Push {
        data object None : Push
        data object Record : Push
        data class Upload(val baseRev: Long) : Push
    }

    /** 올릴 때 이 기기 시간표가 쓰는 종소리 파일 하나 */
    fun planSoundPush(localSha: String, base: Base?, remote: Entry?): Push {
        if (remote != null && remote.live && remote.sha == localSha) {
            return if (base == null || base.rev != remote.rev || base.sha != localSha) Push.Record else Push.None
        }
        // 이 기기 파일은 그대로인데 다른 기기가 서버 파일을 바꿈 → 받을 때 처리
        if (base != null && base.sha == localSha && remote != null && remote.live && remote.rev != base.rev) return Push.None
        return Push.Upload(remote?.rev ?: 0)
    }

    /** 이 기기에서 지운 종소리 → 서버에서도 지울 파일 (다른 곳에서 아직 쓰면 남긴다) */
    fun removedSoundFiles(lastFiles: Set<String>, nowFiles: Set<String>): Set<String> = lastFiles - nowFiles

    // ---------------------------------------------------------------- 이 기기에 저장하는 동기화 상태
    data class FileSig(val size: Long, val mtime: Long, val sha: String)

    class SyncState {
        var seq = 0L
        val remote = LinkedHashMap<String, Entry>()
        val base = LinkedHashMap<String, Base>()
        /** 마지막으로 맞춘 내용(meta 뺀 것)의 SHA-256 */
        var lastConfig: String? = null
        var lastConfigFiles: Set<String> = emptySet()
        var lastState: String? = null
        var lastLogs: String? = null
        /** state.json 의 울려 달라는 요청 (쓸 때 10분 지난 것은 뺀다) */
        var requests: List<RingRequest> = emptyList()
        /** 이 기기에서 처리한 요청 id → 처리한 시각(ms) */
        val handled = LinkedHashMap<String, Long>()
        /** 종소리 파일 이름 → 크기·고친 시각·SHA-256 (다시 계산하지 않게) */
        val cache = LinkedHashMap<String, FileSig>()

        fun toMap(): Map<String, Any?> = linkedMapOf(
            "v" to 1, "seq" to seq,
            "remote" to remote.mapValues { it.value.toMap() },
            "base" to base.mapValues { linkedMapOf("rev" to it.value.rev, "sha" to it.value.sha) },
            "lastConfig" to lastConfig, "lastConfigFiles" to lastConfigFiles.sorted(), "lastState" to lastState, "lastLogs" to lastLogs,
            "requests" to requests.map { it.toMap() },
            "handled" to LinkedHashMap<String, Any?>(handled),
            "cache" to cache.mapValues { linkedMapOf("size" to it.value.size, "mtime" to it.value.mtime, "sha" to it.value.sha) },
        )

        companion object {
            fun from(m: Map<String, Any?>?): SyncState {
                val s = SyncState()
                if (m == null || m["v"].jLong() != 1L) return s
                s.seq = m["seq"].jLong() ?: 0
                m["remote"].jObj()?.forEach { (k, v) -> Entry.from(v.jObj())?.let { s.remote[k] = it } }
                m["base"].jObj()?.forEach { (k, v) -> v.jObj()?.let { b -> s.base[k] = Base(b["rev"].jLong() ?: 0, b["sha"].jStr()) } }
                s.lastConfig = m["lastConfig"].jStr()
                s.lastConfigFiles = m["lastConfigFiles"].jList().mapNotNull { it.jStr() }.toSet()
                s.lastState = m["lastState"].jStr()
                s.lastLogs = m["lastLogs"].jStr()
                s.requests = m["requests"].jList().mapNotNull { RingRequest.from(it.jObj()) }
                m["handled"].jObj()?.forEach { (k, v) -> v.jLong()?.let { s.handled[k] = it } }
                m["cache"].jObj()?.forEach { (k, v) ->
                    v.jObj()?.let { c ->
                        val sha = c["sha"].jStr() ?: return@let
                        s.cache[k] = FileSig(c["size"].jLong() ?: -1, c["mtime"].jLong() ?: -1, sha)
                    }
                }
                return s
            }
        }
    }

    // ---------------------------------------------------------------- 시각
    /**
     * 일정의 다음 울릴 날짜 (오늘은 아직 안 지난 경우만). blocked(날짜) 가 true 면 그날은 건너뛴다 (쉬는 날·건너뛰기·이미 울림).
     */
    fun nextOccurrence(mask: Int, hhmm: String, now: LocalDateTime, blocked: (LocalDate) -> Boolean = { false }): LocalDate? {
        for (offset in 0L..7L) {
            val day = now.toLocalDate().plusDays(offset)
            if (mask and TimeUtil.bit(day) == 0) continue
            if (offset == 0L && !TimeUtil.at(day, hhmm).isAfter(now)) continue
            if (blocked(day)) continue
            return day
        }
        return null
    }

    // ---------------------------------------------------------------- 주소
    /** 'mago.milky.kr/' → 'https://mago.milky.kr' */
    fun normalizeServer(input: String): String {
        var s = input.trim().trimEnd('/')
        if (s.isEmpty()) return s
        if (!s.startsWith("http://", ignoreCase = true) && !s.startsWith("https://", ignoreCase = true)) s = "https://$s"
        return s
    }
}
