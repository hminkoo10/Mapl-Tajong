package com.milky.mataf.core

import com.milky.mataf.data.TimeUtil
import java.security.MessageDigest
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
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
    /** '지금 울리기'는 누른 때에서 이만큼 뒤(ring_at)에 모든 기기가 함께 울린다 (요청이 다른 기기에 닿을 시간) */
    const val RING_DELAY_MS = 3000L
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
    private val ISO_MS: DateTimeFormatter = DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSS'Z'").withZone(ZoneOffset.UTC)

    // ---------------------------------------------------------------- 공통
    fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    fun sha256(text: String): String = sha256(text.toByteArray(Charsets.UTF_8))

    fun meta(deviceId: String, deviceName: String, at: Instant): Map<String, Any?> =
        linkedMapOf("device_id" to deviceId, "device_name" to deviceName, "at" to iso(at))

    fun iso(at: Instant): String = at.truncatedTo(ChronoUnit.SECONDS).toString()

    /** 밀리초까지, 늘 세 자리 ('2026-11-01T01:23:48.250Z'). Instant.toString() 은 0 인 자리를 빼서 따로 만든다 */
    fun isoMs(at: Instant): String = ISO_MS.format(at)

    /** UTC ISO 8601 ('Z' 또는 +09:00 같은 오프셋, 오프셋이 없으면 UTC 로 본다) */
    fun parseInstant(s: String?): Instant? {
        if (s.isNullOrBlank() || s.length > 40 || !Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}[T ].*").matches(s)) return null
        val t = s.trim()
        return runCatching { Instant.parse(t) }.getOrNull()
            ?: runCatching { OffsetDateTime.parse(t).toInstant() }.getOrNull()
            ?: runCatching { LocalDateTime.parse(t).toInstant(ZoneOffset.UTC) }.getOrNull()
    }

    /** 내용 비교용 값: meta·sig 를 뺀 정규화 JSON */
    fun content(file: Map<String, Any?>): String = Json.canonical(file.filterKeys { it != "meta" && it != "sig" })

    fun contentHash(file: Map<String, Any?>): String = sha256(content(file))

    /** 기기 ID 를 파일 이름으로 쓸 수 있게: A-Z a-z 0-9 _ - 만 남긴다 */
    fun safeId(id: String): String = id.filter { it in 'A'..'Z' || it in 'a'..'z' || it in '0'..'9' || it == '_' || it == '-' }

    fun logsPath(deviceId: String): String = "$LOGS${safeId(deviceId)}.json"

    /** 서버 경로로 쓸 수 있는 종소리 파일 이름인지 (폴더 없이, 끝이 점·공백이 아니게) */
    fun validFileName(fn: String): Boolean =
        fn.isNotEmpty() && fn.length <= 200 && fn != "." && fn != ".." && SAFE_FILE.matches(fn) && !fn.endsWith(".") && !fn.endsWith(" ") &&
            fn.toByteArray(Charsets.UTF_8).size <= 255 && String(fn.toByteArray(Charsets.UTF_8), Charsets.UTF_8) == fn &&
            !Regex("(?i:CON|CONIN\\$|CONOUT\\$|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])").matches(fn.substringBefore('.'))

    fun soundPath(fn: String): String = SOUNDS + fn

    /** 'sounds/x.wav' → 'x.wav' (하위 폴더나 이상한 이름이면 null) */
    fun soundName(path: String): String? {
        if (!path.startsWith(SOUNDS)) return null
        val fn = path.removePrefix(SOUNDS)
        return fn.takeIf { '/' !in it && validFileName(it) }
    }

    private const val MAX_ID = 2147483647L
    private const val MAX_NAME = 200
    private val MAX_ROWS = mapOf("sounds" to 256, "schedule_sets" to 128, "schedules" to 2000)

    private fun cleanLong(v: Any?): Long? = when (v) {
        is Boolean -> null
        is Byte, is Short, is Int, is Long -> v.toString().toLongOrNull()?.takeIf { it in -MAX_ID..MAX_ID }
        is Float, is Double -> (v as Number).toDouble().takeIf { it.isFinite() && it == kotlin.math.floor(it) && it in -MAX_ID.toDouble()..MAX_ID.toDouble() }?.toLong()
        else -> null
    }

    private fun settingId(v: Any?): Long? = if (v is String)
        v.takeIf { it.length <= 10 && Regex("[0-9]+").matches(it) }?.toLongOrNull()?.takeIf { it <= MAX_ID }
        else cleanLong(v)

    private fun cleanDouble(v: Any?): Double? = when (v) {
        is Boolean, null -> null
        is Number -> v.toDouble().takeIf { it.isFinite() }
        else -> null
    }

    private fun cleanText(v: Any?, limit: Int = MAX_NAME, required: Boolean = true): String? =
        (v as? String)?.trim()?.takeIf { (!required || it.isNotEmpty()) && it.length <= limit && it.none { c -> c.code < 32 } &&
            String(it.toByteArray(Charsets.UTF_8), Charsets.UTF_8) == it }

    private fun cleanFileName(v: Any?): String? {
        var fn = (v as? String) ?: return null
        if (fn.startsWith(SOUNDS)) fn = fn.removePrefix(SOUNDS)
        return fn.takeIf { validFileName(it) && '/' !in it && '\\' !in it }
    }

    private fun validation(detail: String) =
        System.err.println("TajongValidation: 값 검증 보정: $detail")

    private fun cleanMeta(v: Any?): Map<String, Any?> {
        val m = v.jObj() ?: emptyMap()
        val clean = mapOf("device_id" to (cleanText(m["device_id"], 80, false) ?: ""),
            "device_name" to (cleanText(m["device_name"], MAX_NAME, false) ?: ""),
            "at" to ((m["at"] as? String)?.takeIf { parseInstant(it) != null } ?: ""))
        if (v != clean) validation("meta: 잘못된 값 보정")
        return clean
    }

    /** config/backup 입력을 SQLite에 넣기 전, 만들어질 수 없는 값과 참조를 제거한다. */
    fun sanitizeTables(data: Map<String, Any?>): Map<String, Any?> {
        val out = linkedMapOf<String, Any?>()
        val fixed = LinkedHashSet<String>()
        val ids = HashMap<String, MutableSet<Long>>()
        val setNames = HashSet<String>()
        for ((table, cols) in TABLES) {
            val raw = data[table].jList()
            if (data[table] != null && data[table] !is List<*>) fixed += "$table: 목록 아님"
            val limit = MAX_ROWS.getValue(table)
            if (raw.size > limit) fixed += "$table: 최대 개수 초과"
            val clean = ArrayList<Map<String, Any?>>()
            for (rawRow in raw.take(limit)) {
                val row = rawRow.jObj()
                if (row == null) { fixed += "$table: 객체 아님"; continue }
                val id = cleanLong(row["id"])
                if (id == null || id !in 1..MAX_ID || id in ids.getOrPut(table) { HashSet() }) {
                    fixed += "$table: id 오류/중복"; continue
                }
                val item = linkedMapOf<String, Any?>("id" to id)
                when (table) {
                    "sounds" -> {
                        val name = cleanText(row["name"])
                        val fn = cleanFileName(row["file_name"])
                        if (name == null || fn == null) {
                            fixed += "sounds: 이름/파일명 오류"; continue
                        }
                        val volume = cleanDouble(row["volume"] ?: 1.0)
                        item["name"] = name; item["file_name"] = fn
                        item["volume"] = if (volume != null && volume in 0.0..2.0) volume else 1.0
                        if (volume == null || volume !in 0.0..2.0) fixed += "sounds.volume: 기본값"
                    }
                    "schedule_sets" -> {
                        val name = cleanText(row["name"])
                        if (name == null || !setNames.add(name)) { fixed += "schedule_sets: 이름 오류/중복"; continue }
                        item["name"] = name
                    }
                    "schedules" -> {
                        val setId = cleanLong(row["set_id"])
                        val name = cleanText(row["name"])
                        val mask = cleanLong(row["weekday_mask"])
                        val time = (row["time_hhmm"] as? String)?.let {
                            Regex("([0-9]{2}):([0-9]{2})").matchEntire(it)?.let { m ->
                                val h = m.groupValues[1].toInt(); val min = m.groupValues[2].toInt()
                                if (h <= 23 && min <= 59) it else null
                            }
                        }
                        val soundId = cleanLong(row["sound_id"])
                        if (setId == null || setId !in 1..MAX_ID || name == null || mask == null || mask !in 1..127 ||
                            time == null || soundId == null || soundId !in 1..MAX_ID) {
                            fixed += "schedules: 필수 값 오류"; continue
                        }
                        item["set_id"] = setId; item["name"] = name; item["weekday_mask"] = mask
                        item["time_hhmm"] = time; item["sound_id"] = soundId
                        val volume = if (row.containsKey("volume_override") && row["volume_override"] != null) cleanDouble(row["volume_override"]) else null
                        item["volume_override"] = if (volume != null && volume in 0.0..2.0) volume else null
                        if (row["volume_override"] != null && (volume == null || volume !in 0.0..2.0)) fixed += "schedules.volume_override: 기본값"
                        val enabled = when (val e = row["enabled"]) {
                            is Boolean -> if (e) 1L else 0L
                            else -> cleanLong(e)?.takeIf { it == 0L || it == 1L } ?: 1L
                        }
                        item["enabled"] = enabled
                        item["sort_order"] = cleanLong(row["sort_order"])?.takeIf { it >= 0 } ?: 0L
                        if (row.containsKey("enabled") && row["enabled"] !is Boolean && cleanLong(row["enabled"]) !in listOf(0L, 1L)) fixed += "schedules.enabled: 기본값"
                        if (row.containsKey("sort_order") && cleanLong(row["sort_order"])?.let { it >= 0 } != true) fixed += "schedules.sort_order: 기본값"
                    }
                }
                for (col in cols.filter { it.endsWith("_at") }) {
                    if (row[col] == null) continue
                    val text = cleanText(row[col], 40)?.takeIf { parseInstant(it.replace(' ', 'T')) != null }
                    if (text != null) item[col] = text else fixed += "$table.$col: 기본값"
                }
                ids.getValue(table).add(id)
                clean += item
            }
            out[table] = clean
        }
        val soundIds = out["sounds"].jList().mapNotNull { it.jObj()?.get("id")?.let(::cleanLong) }.toSet()
        val setIds = out["schedule_sets"].jList().mapNotNull { it.jObj()?.get("id")?.let(::cleanLong) }.toSet()
        val schedules = out["schedules"].jList().mapNotNull { it.jObj() }.filter {
            val ok = cleanLong(it["sound_id"]) in soundIds && cleanLong(it["set_id"]) in setIds
            if (!ok) fixed += "schedules: 참조 오류"
            ok
        }
        out["schedules"] = schedules
        val active = settingId(data["settings"].jObj()?.get("active_set_id"))
        out["settings"] = if (active != null && active in setIds) mapOf("active_set_id" to active.toString()) else emptyMap<String, Any?>()
        if (data["settings"].jObj()?.containsKey("active_set_id") == true && active !in setIds) fixed += "settings.active_set_id: 기본값"
        if (data["settings"] != null && data["settings"] !is Map<*, *>) fixed += "settings: 객체 아님"
        if (fixed.isNotEmpty()) validation(fixed.take(20).joinToString(", ") + if (fixed.size > 20) " 외" else "")
        return out
    }

    fun sanitizeConfig(m: Map<String, Any?>): Map<String, Any?> = linkedMapOf<String, Any?>(
        "app" to m["app"], "kind" to m["kind"], "format" to (if (m.containsKey("format")) m["format"] else FORMAT),
    ).apply {
        putAll(sanitizeTables(m)); if (m.containsKey("meta")) put("meta", cleanMeta(m["meta"]))
    }

    fun sanitizeManifest(m: Map<String, Any?>): Map<String, Any?> {
        val format = if (m.containsKey("format")) cleanLong(m["format"]) else FORMAT.toLong()
        require(m["app"] == APP && format != null && format >= 1) { "타종 프로그램 백업 파일이 아닙니다." }
        require(format <= FORMAT) { "더 최신 버전에서 만든 백업입니다. 프로그램을 업데이트하세요." }
        val counts = MAX_ROWS.mapValues { (table, limit) -> cleanLong(m["counts"].jObj()?.get(table))?.takeIf { it in 0..limit.toLong() } ?: 0L }
        val version = cleanText(m["app_version"] ?: "", 64, false) ?: ""
        val created = cleanText(m["created_at"] ?: "", 64, false) ?: ""
        for ((field, value) in mapOf("counts" to counts, "app_version" to version, "created_at" to created)) {
            if (m.containsKey(field) && m[field] != value) validation("manifest.$field: 기본값으로 보정")
        }
        return mapOf("counts" to counts, "app_version" to version, "created_at" to created)
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
        validFormat(m)

    private fun validFormat(m: Map<String, Any?>): Boolean =
        (if (m.containsKey("format")) cleanLong(m["format"]) else FORMAT.toLong())?.let { it in 1..FORMAT.toLong() } == true

    fun rows(cfg: Map<String, Any?>, table: String): List<Map<String, Any?>> = cfg[table].jList().mapNotNull { it.jObj() }

    /** 종소리 파일 이름들 */
    fun soundFiles(cfg: Map<String, Any?>?): Set<String> =
        if (cfg == null) emptySet() else rows(cfg, "sounds").mapNotNull { cleanFileName(it["file_name"]) }.toSet()

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

    /** at: 요청한 때(초까지), ringAt: 울릴 때(밀리초까지). 예전 버전(PC 2.2.3·안드로이드 2.2.4 까지)이 넣은 요청에는 ringAt 이 없다 */
    data class RingRequest(val id: String, val scheduleId: Long?, val soundId: Long?, val at: String, val by: String, val byName: String,
                           val ringAt: String? = null) {
        val instant: Instant? get() = parseInstant(at)
        /** 울릴 때: ring_at, 없으면 at */
        val ringInstant: Instant? get() = parseInstant(ringAt) ?: instant
        /** ring_at 은 있을 때만 쓴다 (예전 버전이 쓴 요청의 내용이 바뀌지 않게) */
        fun toMap(): Map<String, Any?> = linkedMapOf<String, Any?>("id" to id, "schedule_id" to scheduleId, "sound_id" to soundId, "at" to at)
            .apply { if (ringAt != null) put("ring_at", ringAt); put("by", by); put("by_name", byName) }

        companion object {
            fun from(m: Map<String, Any?>?): RingRequest? {
                if (m == null) return null
                val id = cleanText(m["id"], 128)?.takeIf { it.isNotBlank() } ?: return null
                if (parseInstant(m["at"] as? String) == null) return null
                val sched = cleanLong(m["schedule_id"]).takeIf { it != null && it in 1..MAX_ID }
                val sound = cleanLong(m["sound_id"]).takeIf { it != null && it in 1..MAX_ID }
                if ((m["schedule_id"] != null && sched == null) || (m["sound_id"] != null && sound == null)) return null
                if (sched == null && sound == null) return null
                return RingRequest(id, sched, sound, m["at"] as String,
                    cleanText(m["by"], 80, false) ?: "", cleanText(m["by_name"], MAX_NAME, false) ?: "",
                    (m["ring_at"] as? String)?.takeIf { it.isNotBlank() && parseInstant(it) != null })
            }
        }
    }

    data class State(val paused: Boolean, val overrides: List<Override>, val requests: List<RingRequest>)

    fun sanitizeState(m: Map<String, Any?>): Map<String, Any?> {
        val fixed = ArrayList<String>()
        val overrides = ArrayList<Map<String, Any?>>()
        val seen = HashSet<String>()
        for (raw in m["overrides"].jList().take(500)) {
            val o = raw.jObj()
            if (o == null) { fixed += "overrides: 객체 아님"; continue }
            val date = cleanText(o["date"], 10) ?: continue
            if (runCatching { LocalDate.parse(date) }.isFailure) continue
            val action = o["action"] as? String ?: continue
            val rawId = cleanLong(o["schedule_id"] ?: 0L) ?: continue
            val id = if (action == PAUSE_DAY) 0L else rawId
            if (rawId !in 0..MAX_ID || (action == SKIP && id == 0L) || action !in setOf(SKIP, PAUSE_DAY) || !seen.add("$date/$id/$action")) continue
            overrides += linkedMapOf("date" to date, "schedule_id" to id,
                "action" to action, "note" to (cleanText(o["note"], MAX_NAME, false) ?: ""))
        }
        val requests = ArrayList<Map<String, Any?>>()
        val requestIds = HashSet<String>()
        for (raw in m["ring_requests"].jList().take(2000)) {
            val r = RingRequest.from(raw.jObj())
            if (r != null && requestIds.add(r.id)) requests += r.toMap()
        }
        val paused = when (val p = m["paused"]) {
            is Boolean -> p
            is Number -> cleanLong(p) == 1L
            else -> false
        }
        for ((field, value) in mapOf("paused" to paused, "overrides" to overrides, "ring_requests" to requests)) {
            if (m.containsKey(field) && m[field] != value) fixed += "$field: 잘못된 값/중복/초과 항목 보정"
        }
        if (m["overrides"] != null && m["overrides"] !is List<*>) fixed += "overrides: 목록 아님"
        if (m["ring_requests"] != null && m["ring_requests"] !is List<*>) fixed += "ring_requests: 목록 아님"
        if (fixed.isNotEmpty()) validation(fixed.take(20).joinToString(", ") + if (fixed.size > 20) " 외" else "")
        return linkedMapOf<String, Any?>("app" to m["app"], "kind" to m["kind"], "format" to (if (m.containsKey("format")) m["format"] else FORMAT),
            "paused" to paused, "overrides" to overrides, "ring_requests" to requests).apply {
                if (m.containsKey("meta")) put("meta", cleanMeta(m["meta"]))
            }
    }

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
        validFormat(m)

    fun parseState(m: Map<String, Any?>): State {
        val safe = sanitizeState(m)
        val paused = when (val p = safe["paused"]) {
            is Boolean -> p
            else -> p.jLong() == 1L
        }
        val ov = safe["overrides"].jList().mapNotNull { it.jObj() }.mapNotNull { o ->
            val date = o["date"].jStr()?.trim()?.takeIf { runCatching { LocalDate.parse(it) }.isSuccess } ?: return@mapNotNull null
            val action = o["action"].jStr() ?: return@mapNotNull null
            if (action != SKIP && action != PAUSE_DAY) return@mapNotNull null
            Override(date, if (action == PAUSE_DAY) 0 else o["schedule_id"].jLong() ?: return@mapNotNull null, action, o["note"].jStr() ?: "")
        }
        val req = safe["ring_requests"].jList().mapNotNull { RingRequest.from(it.jObj()) }
        return State(paused, ov, req)
    }

    fun referencedState(state: State, scheduleIds: Set<Long>, soundIds: Set<Long>): State {
        val clean = state.copy(
            overrides = state.overrides.filter { it.scheduleId == 0L || it.scheduleId in scheduleIds },
            requests = state.requests.filter { (it.scheduleId == null || it.scheduleId in scheduleIds) &&
                (it.soundId == null || it.soundId in soundIds) },
        )
        if (clean != state) validation("state: 존재하지 않는 일정/소리 참조 삭제")
        return clean
    }

    /** 처음 보는 요청 중 울릴 때(ring_at, 없으면 at)가 지금 ±2분 안인 것 */
    fun dueRequests(requests: List<RingRequest>, handled: Set<String>, now: Instant): List<RingRequest> =
        requests.filter { r ->
            if (r.id in handled) return@filter false
            val at = r.ringInstant ?: return@filter false
            Math.abs(Duration.between(at, now).toMillis()) <= REQUEST_WINDOW_SEC * 1000
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

    private fun counter(v: Any?): Long? = when (v) {
        is Long -> v.takeIf { it >= 0 }
        is Int -> v.toLong().takeIf { it >= 0 }
        is Double -> v.takeIf { it.isFinite() && it >= 0 && it < Long.MAX_VALUE.toDouble() && it == Math.floor(it) }?.toLong()
        else -> null
    }

    private fun hash(v: Any?): String? = (v as? String)?.takeIf { Regex("[0-9a-f]{64}").matches(it) }

    private fun syncPath(path: String): Boolean = path in listOf(CONFIG, STATE) || soundName(path) != null ||
        Regex("logs/[A-Za-z0-9_-]{1,80}\\.json").matches(path)

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
                if (m == null) return s
                if (cleanLong(m["v"]) != 1L) { validation("sync.v: 기본값"); return s }
                s.seq = counter(m["seq"]) ?: 0
                m["remote"].jObj()?.entries?.take(5000)?.forEach { (k, v) ->
                    val e = v.jObj() ?: return@forEach
                    if (!syncPath(k) || e["path"] != k || e["deleted"] !is Boolean || e["evicted"] !is Boolean) return@forEach
                    val rev = counter(e["rev"]) ?: return@forEach
                    val seq = counter(e["seq"]) ?: return@forEach
                    val size = counter(e["size"]) ?: return@forEach
                    val sha = hash(e["sha256"])
                    if (e["sha256"] != null && sha == null) return@forEach
                    s.remote[k] = Entry(k, rev, seq, sha, size, e["deleted"] == true, e["evicted"] == true, cleanText(e["deviceId"], 80))
                }
                m["base"].jObj()?.entries?.take(5000)?.forEach { (k, v) ->
                    val b = v.jObj() ?: return@forEach
                    if (!syncPath(k)) return@forEach
                    val rev = counter(b["rev"]) ?: return@forEach
                    val sha = hash(b["sha"])
                    if (b["sha"] != null && sha == null) return@forEach
                    s.base[k] = Base(rev, sha)
                }
                s.lastConfig = hash(m["lastConfig"])
                s.lastConfigFiles = m["lastConfigFiles"].jList().take(256).mapNotNull { (it as? String)?.takeIf(::validFileName) }.toSet()
                s.lastState = hash(m["lastState"])
                s.lastLogs = hash(m["lastLogs"])
                s.requests = sanitizeState(mapOf("ring_requests" to m["requests"]))["ring_requests"].jList().mapNotNull { RingRequest.from(it.jObj()) }
                m["handled"].jObj()?.entries?.take(2000)?.forEach { (k, v) ->
                    val id = cleanText(k, 128) ?: return@forEach
                    counter(v)?.takeIf { it <= 253402300799999L }?.let { s.handled[id] = it }
                }
                m["cache"].jObj()?.entries?.take(256)?.forEach { (k, v) ->
                    if (!validFileName(k)) return@forEach
                    v.jObj()?.let { c ->
                        val sha = hash(c["sha"]) ?: return@let
                        val size = counter(c["size"]) ?: return@let
                        val mtime = counter(c["mtime"]) ?: return@let
                        s.cache[k] = FileSig(size, mtime, sha)
                    }
                }
                for ((field, value) in s.toMap()) if (field != "v" && m.containsKey(field) && m[field] != value) validation("sync.$field: 잘못된 값/초과 항목 보정")
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
