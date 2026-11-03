package com.milky.mataf.core

import com.milky.mataf.core.CloudModel.Base
import com.milky.mataf.core.CloudModel.Entry
import com.milky.mataf.core.CloudModel.FileOp
import com.milky.mataf.core.CloudModel.Override
import com.milky.mataf.core.CloudModel.Pull
import com.milky.mataf.core.CloudModel.Push
import com.milky.mataf.core.CloudModel.RingRequest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime

class CloudModelTest {
    private val metaA = CloudModel.meta("dev-a", "원장님 폰", Instant.parse("2026-11-01T00:00:00Z"))
    private val metaB = CloudModel.meta("dev-b", "교무실 PC", Instant.parse("2026-11-01T05:00:00Z"))

    private fun tables(volume: Any = 1.0, time: String = "09:00") = mapOf(
        "sounds" to listOf(
            linkedMapOf("id" to 2L, "name" to "학교종", "file_name" to "school.mp3", "volume" to volume, "created_at" to "2026-11-01 00:00:00"),
            linkedMapOf("id" to 1L, "name" to "bell1", "file_name" to "bell1.wav", "volume" to 1.0, "created_at" to "2026-11-01 00:00:00"),
        ),
        "schedule_sets" to listOf(linkedMapOf("id" to 1L, "name" to "기본", "created_at" to "2026-11-01 00:00:00")),
        "schedules" to listOf(linkedMapOf("id" to 1L, "set_id" to 1L, "name" to "1교시", "weekday_mask" to 31L, "time_hhmm" to time,
            "sound_id" to 2L, "volume_override" to null, "enabled" to 1L, "sort_order" to 0L, "created_at" to "x", "updated_at" to "y",
            "extra" to "버림")),
    )

    // ---------------------------------------------------------------- config.json
    @Test
    fun configFileHasHeaderSortedRowsAndKnownColumnsOnly() {
        val cfg = CloudModel.configFile(tables(), "1", metaA)
        assertEquals(listOf("app", "kind", "format", "sounds", "schedule_sets", "schedules", "settings", "meta"), cfg.keys.toList())
        assertEquals("MaplTajong", cfg["app"]); assertEquals("config", cfg["kind"]); assertEquals(1, cfg["format"])
        assertEquals(listOf(1L, 2L), CloudModel.rows(cfg, "sounds").map { it["id"] })
        assertFalse(CloudModel.rows(cfg, "schedules")[0].containsKey("extra"))
        assertEquals(mapOf("active_set_id" to "1"), cfg["settings"])
        assertEquals(setOf("bell1.wav", "school.mp3"), CloudModel.soundFiles(cfg))
        assertEquals(CloudModel.Counts(1, 1, 2), CloudModel.counts(cfg))
        assertTrue(CloudModel.isConfig(cfg))
    }

    @Test
    fun contentIgnoresMetaAndNumberFormSoApplyingDoesNotPingPong() {
        val mine = CloudModel.configFile(tables(volume = 1L), "1", metaA)
        val theirs = CloudModel.configFile(tables(volume = 1.0), "1", metaB)
        assertEquals(CloudModel.contentHash(mine), CloudModel.contentHash(theirs))
        // 파일로 썼다가 다시 읽어도 같은 내용
        val reread = Json.parse(Json.write(theirs)).jObj()!!
        assertEquals(CloudModel.contentHash(theirs), CloudModel.contentHash(reread))
        // 시각이 바뀌면 다른 내용
        assertNotEquals(CloudModel.contentHash(mine), CloudModel.contentHash(CloudModel.configFile(tables(time = "09:10"), "1", metaA)))
    }

    @Test
    fun defaultConfigMeansFreshInstall() {
        val fresh = CloudModel.configFile(mapOf(
            "sounds" to (1..8).map { linkedMapOf<String, Any?>("id" to it.toLong(), "name" to "bell$it", "file_name" to "bell$it.wav") },
            "schedule_sets" to listOf(linkedMapOf<String, Any?>("id" to 1L, "name" to "기본")),
            "schedules" to emptyList(),
        ), "1", metaA)
        assertTrue(CloudModel.isDefaultConfig(fresh))
        assertFalse(CloudModel.isDefaultConfig(CloudModel.configFile(tables(), "1", metaA)))
        val custom = fresh.toMutableMap().apply {
            put("sounds", listOf(linkedMapOf<String, Any?>("id" to 9L, "name" to "학교종", "file_name" to "school.mp3")))
        }
        assertFalse(CloudModel.isDefaultConfig(custom))
    }

    @Test
    fun staleOverridesOnlyForRemovedOrMovedSchedules() {
        val old = mapOf(1L to "09:00", 2L to "10:00", 3L to "11:00")
        val new = mapOf(1L to "09:00", 2L to "10:05", 4L to "12:00")
        assertEquals(setOf(2L, 3L), CloudModel.staleOverrideSchedules(listOf(1L, 2L, 3L), old, new))
        // PAUSE_DAY(0)는 건드리지 않는다
        assertEquals(emptySet<Long>(), CloudModel.staleOverrideSchedules(listOf(0L, 1L), old, new))
    }

    // ---------------------------------------------------------------- state.json
    @Test
    fun stateKeepsOnlyTodayAndLaterSkipAndPauseDay() {
        val today = LocalDate.parse("2026-11-02")
        val ov = listOf(
            Override("2026-11-01", 3, "SKIP_ONCE", "admin"),     // 어제 → 뺌
            Override("2026-11-02", 3, "SKIP_ONCE", "admin"),
            Override("2026-11-02", 3, "SKIP_ONCE", "admin"),     // 같은 것 → 하나로
            Override("2026-11-02", 5, "FIRED_ONCE", "auto"),     // 기기마다 따로 → 뺌
            Override("2026-11-03", 7, "PAUSE_DAY", "admin"),     // 오늘 쉬기는 schedule_id 0
        )
        val shared = CloudModel.sharedOverrides(ov, today)
        assertEquals(listOf(Override("2026-11-02", 3, "SKIP_ONCE", "admin"), Override("2026-11-03", 0, "PAUSE_DAY", "admin")), shared)

        val req = RingRequest("r1", 3, null, "2026-11-02T01:00:00Z", "dev-a", "원장님 폰")
        val file = CloudModel.stateFile(true, ov, listOf(req, req), today, metaA)
        assertEquals("state", file["kind"])
        val parsed = CloudModel.parseState(Json.parse(Json.write(file)).jObj()!!)
        assertTrue(parsed.paused)
        assertEquals(shared, parsed.overrides)
        assertEquals(listOf(req), parsed.requests)
    }

    @Test
    fun oldRingRequestsAreDroppedWhenWriting() {
        val now = Instant.parse("2026-11-02T01:10:00Z")
        val fresh = RingRequest("a", 1, null, "2026-11-02T01:05:00Z", "d", "n")
        val old = RingRequest("b", 1, null, "2026-11-02T00:59:00Z", "d", "n")
        val broken = RingRequest("c", 1, null, "어제", "d", "n")
        assertEquals(listOf(fresh), CloudModel.freshRequests(listOf(fresh, old, broken), now))
    }

    @Test
    fun ringRequestNeedsScheduleOrSound() {
        assertNull(RingRequest.from(mapOf("id" to "x", "at" to "2026-11-02T01:00:00Z")))
        assertEquals(5L, RingRequest.from(mapOf("id" to "x", "sound_id" to 5L, "schedule_id" to null,
            "at" to "2026-11-02T01:00:00Z"))?.soundId)
    }

    @Test
    fun dueRequestsWithinTwoMinutesOnceEach() {
        val now = Instant.parse("2026-11-02T01:00:00Z")
        fun r(id: String, at: String) = RingRequest(id, 1, null, at, "dev-b", "교무실 PC")
        val reqs = listOf(
            r("in-past", "2026-11-02T00:58:00Z"),       // 정확히 2분 전 → 울림
            r("too-old", "2026-11-02T00:57:59Z"),
            r("in-future", "2026-11-02T01:01:30Z"),
            r("too-far", "2026-11-02T01:02:01Z"),
            r("handled", "2026-11-02T01:00:00Z"),
            r("offset", "2026-11-02T10:00:30+09:00"),   // 오프셋도 읽는다
        )
        assertEquals(listOf("in-past", "in-future", "offset"), CloudModel.dueRequests(reqs, setOf("handled"), now).map { it.id })
    }

    @Test
    fun ringAtIsWrittenOnlyWhenPresentAndSurvivesRoundTrips() {
        val now = RingRequest("r1", 3, null, "2026-11-01T01:23:45Z", "dev-a", "원장님 폰", "2026-11-01T01:23:48.250Z")
        val old = RingRequest("r2", null, 4, "2026-11-01T01:23:45Z", "dev-b", "교무실 PC")     // PC 2.2.3·안드로이드 2.2.4 까지가 넣은 것
        assertEquals(listOf("id", "schedule_id", "sound_id", "at", "ring_at", "by", "by_name"), now.toMap().keys.toList())
        assertEquals(listOf("id", "schedule_id", "sound_id", "at", "by", "by_name"), old.toMap().keys.toList())
        assertEquals(now, RingRequest.from(Json.parse(Json.write(now.toMap())).jObj()))
        assertNull(RingRequest.from(Json.parse(Json.write(old.toMap())).jObj())!!.ringAt)
        assertNull(RingRequest.from(old.toMap() + ("ring_at" to ""))!!.ringAt)
        // 울릴 때: ring_at, 없으면 at
        assertEquals(Instant.parse("2026-11-01T01:23:48.250Z"), now.ringInstant)
        assertEquals(Instant.parse("2026-11-01T01:23:45Z"), old.ringInstant)
        // state.json 과 이 기기 동기화 상태(sync.json)를 거쳐도 그대로
        val file = CloudModel.stateFile(false, emptyList(), listOf(now, old), LocalDate.parse("2026-11-01"), metaA)
        assertEquals(listOf(now, old), CloudModel.parseState(Json.parse(Json.write(file)).jObj()!!).requests)
        val st = CloudModel.SyncState().apply { requests = listOf(now, old) }
        assertEquals(listOf(now, old), CloudModel.SyncState.from(Json.parse(Json.write(st.toMap(), 0)).jObj()).requests)
    }

    @Test
    fun isoMsAlwaysHasThreeDigits() {
        assertEquals("2026-11-01T01:23:48.250Z", CloudModel.isoMs(Instant.parse("2026-11-01T01:23:48.25Z")))
        assertEquals("2026-11-01T01:23:48.000Z", CloudModel.isoMs(Instant.parse("2026-11-01T01:23:48Z")))
        assertEquals("2026-11-01T01:23:48.007Z", CloudModel.isoMs(Instant.parse("2026-11-01T01:23:48.007999Z")))   // 밀리초 아래는 버림
        assertEquals(Instant.parse("2026-11-01T01:23:48.250Z"), CloudModel.parseInstant(CloudModel.isoMs(Instant.parse("2026-11-01T01:23:48.250Z"))))
        assertEquals(3000L, CloudModel.RING_DELAY_MS)
    }

    @Test
    fun dueRequestsUseRingAtThenAt() {
        val now = Instant.parse("2026-11-02T01:00:00Z")
        fun r(id: String, at: String, ringAt: String?) = RingRequest(id, 1, null, at, "dev-b", "교무실 PC", ringAt)
        val reqs = listOf(
            r("soon", "2026-11-02T00:59:57Z", "2026-11-02T01:00:00.250Z"),
            r("ring-in", "2026-11-02T00:57:00Z", "2026-11-02T00:58:00.000Z"),       // at 은 2분 넘게 지났지만 ring_at 은 정확히 2분 전
            r("ring-too-far", "2026-11-02T01:00:00Z", "2026-11-02T01:02:00.001Z"),  // at 은 지금이지만 ring_at 이 2분 넘게 뒤
            r("ring-too-old", "2026-11-02T00:59:00Z", "2026-11-02T00:57:59.999Z"),
            r("old-version", "2026-11-02T00:58:10Z", null),                         // ring_at 없음 → at
            r("old-version-too-old", "2026-11-02T00:57:00Z", null),
        )
        assertEquals(listOf("soon", "ring-in", "old-version"), CloudModel.dueRequests(reqs, emptySet(), now).map { it.id })
    }

    @Test
    fun freshRequestsStillUseAt() {
        val now = Instant.parse("2026-11-02T01:10:00Z")
        val stale = RingRequest("a", 1, null, "2026-11-02T00:59:59Z", "d", "n", "2026-11-02T01:05:00.000Z")   // ring_at 은 10분 안이어도 at 이 지남
        val fresh = RingRequest("b", 1, null, "2026-11-02T01:00:00Z", "d", "n", "2026-11-02T00:50:00.000Z")
        assertEquals(listOf(fresh), CloudModel.freshRequests(listOf(stale, fresh), now))
    }

    @Test
    fun parseInstantFormats() {
        assertEquals(Instant.parse("2026-11-01T01:23:45Z"), CloudModel.parseInstant("2026-11-01T01:23:45Z"))
        assertEquals(Instant.parse("2026-11-01T01:23:45Z"), CloudModel.parseInstant("2026-11-01T10:23:45+09:00"))
        assertEquals(Instant.parse("2026-11-01T01:23:45Z"), CloudModel.parseInstant("2026-11-01T01:23:45"))
        assertEquals(Instant.parse("2026-11-01T01:23:45.500Z"), CloudModel.parseInstant("2026-11-01T01:23:45.5Z"))
        assertNull(CloudModel.parseInstant("x"))
        assertEquals("2026-11-01T01:23:45Z", CloudModel.iso(Instant.parse("2026-11-01T01:23:45.789Z")))
    }

    // ---------------------------------------------------------------- logs
    @Test
    fun logsFileKeepsNewestFiveThousand() {
        val rows = (1..5003).map { i ->
            linkedMapOf<String, Any?>("occurred_at" to "2026-11-01 09:%02d:%02d".format(i / 60 % 60, i % 60), "schedule_id" to i.toLong(),
                "schedule_name" to "s$i", "sound_name" to "bell1", "result" to "PLAYED", "detail" to "")
        }
        val f = CloudModel.logsFile("dev-a", "원장님 폰", rows)
        val d = CloudModel.parseLogs(Json.parse(Json.write(f)).jObj()!!)!!
        assertEquals(5000, d.rows.size)
        assertEquals(4L, d.rows.first().scheduleId)
        assertEquals("원장님 폰", d.deviceName)
        assertNull(CloudModel.parseLogs(mapOf("app" to "MaplTajong", "kind" to "config")))
    }

    @Test
    fun deviceIdIsSafeForFileNames() {
        assertEquals("ab-c_1", CloudModel.safeId("a/b-c_1.\\"))
        assertEquals("logs/8c0f-11.json", CloudModel.logsPath("8c0f-11"))
    }

    @Test
    fun soundPathsMatchServerRules() {
        assertEquals("x.wav", CloudModel.soundName("sounds/x.wav"))
        assertNull(CloudModel.soundName("sounds/a/b.wav"))
        assertNull(CloudModel.soundName("config.json"))
        assertFalse(CloudModel.validFileName("a:b.wav"))
        assertFalse(CloudModel.validFileName("끝에 점."))
        assertTrue(CloudModel.validFileName("종소리 1.wav"))
    }

    // ---------------------------------------------------------------- 판단
    private fun e(rev: Long, sha: String? = "s$rev", deleted: Boolean = false) = Entry("config.json", rev, rev, sha, 1, deleted, false, "x")

    @Test
    fun decideConfigFirstConnect() {
        assertEquals(Pull.UPLOAD, CloudModel.decideConfig(null, null, "L", null, null, false))
        assertEquals(Pull.UPLOAD, CloudModel.decideConfig(null, e(3, deleted = true), "L", null, null, false))
        assertEquals(Pull.RECORD, CloudModel.decideConfig(null, e(3), "L", null, "L", false))
        assertEquals(Pull.APPLY, CloudModel.decideConfig(null, e(3), "L", null, "R", localDefault = true))
        assertEquals(Pull.ASK, CloudModel.decideConfig(null, e(3), "L", null, "R", localDefault = false))
    }

    @Test
    fun decideConfigAfterwards() {
        val base = Base(3, "s3")
        assertEquals(Pull.NONE, CloudModel.decideConfig(base, e(3), "L2", "L", null, false))          // 바뀐 건 이 기기 → 올릴 때
        assertEquals(Pull.APPLY, CloudModel.decideConfig(base, e(4), "L", "L", "R", false))          // 서버만 바뀜
        assertEquals(Pull.CONFLICT, CloudModel.decideConfig(base, e(4), "L2", "L", "R", false))      // 둘 다 → 서버 것
        assertEquals(Pull.RECORD, CloudModel.decideConfig(base, e(4), "R", "L", "R", false))         // 둘 다 같게 바뀜
        assertEquals(Pull.UPLOAD, CloudModel.decideConfig(base, e(5, deleted = true), "L", "L", null, false))
    }

    @Test
    fun decideStateServerWinsOnFirstConnect() {
        assertEquals(Pull.APPLY, CloudModel.decideState(null, e(2), "L", null, "R"))
        assertEquals(Pull.RECORD, CloudModel.decideState(null, e(2), "L", null, "L"))
        assertEquals(Pull.UPLOAD, CloudModel.decideState(null, null, "L", null, null))
        assertEquals(Pull.CONFLICT, CloudModel.decideState(Base(2, "s2"), e(3), "L2", "L", "R"))
    }

    private fun s(rev: Long, sha: String?, deleted: Boolean = false) = Entry("sounds/a.wav", rev, rev, sha, 1, deleted, false, "x")

    @Test
    fun planSoundPull() {
        assertEquals(FileOp.DOWNLOAD, CloudModel.planSoundPull(null, null, s(1, "R"), true))
        assertEquals(FileOp.RECORD, CloudModel.planSoundPull("R", null, s(1, "R"), true))
        assertEquals(FileOp.NONE, CloudModel.planSoundPull("R", Base(1, "R"), s(1, "R"), true))
        assertEquals(FileOp.DOWNLOAD, CloudModel.planSoundPull("L", Base(1, "L"), s(2, "R"), true))
        assertEquals(FileOp.NONE, CloudModel.planSoundPull("L2", Base(1, "L"), s(1, "L"), true))         // 이 기기만 바뀜
        assertEquals(FileOp.DELETE_LOCAL, CloudModel.planSoundPull("L", Base(1, "L"), s(2, null, deleted = true), false))
        assertEquals(FileOp.FORGET, CloudModel.planSoundPull("L", Base(1, "L"), s(2, null, deleted = true), true))   // 아직 씀
        assertEquals(FileOp.FORGET, CloudModel.planSoundPull("L2", Base(1, "L"), s(2, null, deleted = true), false)) // 그 뒤 고침
        assertEquals(FileOp.NONE, CloudModel.planSoundPull("L", null, s(2, null, deleted = true), false))
    }

    @Test
    fun planSoundPush() {
        assertEquals(Push.Upload(0), CloudModel.planSoundPush("L", null, null))
        assertEquals(Push.Record, CloudModel.planSoundPush("L", null, s(1, "L")))
        assertEquals(Push.None, CloudModel.planSoundPush("L", Base(1, "L"), s(1, "L")))
        assertEquals(Push.Upload(1), CloudModel.planSoundPush("L2", Base(1, "L"), s(1, "L")))
        assertEquals(Push.Upload(4), CloudModel.planSoundPush("L", Base(3, "L"), s(4, null, deleted = true)))   // 지워졌지만 아직 씀
        assertEquals(Push.None, CloudModel.planSoundPush("L", Base(1, "L"), s(2, "R")))                        // 서버만 바뀜 → 받기
        assertEquals(Push.Upload(5), CloudModel.planSoundPush("L", null, s(5, "R")))                           // 이 기기 것으로 바꾸기
        assertEquals(setOf("old.wav"), CloudModel.removedSoundFiles(setOf("old.wav", "keep.wav"), setOf("keep.wav", "new.wav")))
    }

    // ---------------------------------------------------------------- 시각 · 주소 · 저장
    @Test
    fun nextOccurrenceSkipsPassedAndBlockedDays() {
        val mon = LocalDateTime.parse("2026-11-02T08:00:00")    // 월요일
        assertEquals(LocalDate.parse("2026-11-02"), CloudModel.nextOccurrence(31, "09:00", mon))
        assertEquals(LocalDate.parse("2026-11-03"), CloudModel.nextOccurrence(31, "07:00", mon))
        assertEquals(LocalDate.parse("2026-11-09"), CloudModel.nextOccurrence(1, "07:00", mon))           // 월요일만
        assertEquals(LocalDate.parse("2026-11-03"), CloudModel.nextOccurrence(31, "09:00", mon) { it == LocalDate.parse("2026-11-02") })
        assertNull(CloudModel.nextOccurrence(0, "09:00", mon))
    }

    @Test
    fun normalizeServer() {
        assertEquals("https://mago.milky.kr", CloudModel.normalizeServer(" mago.milky.kr/ "))
        assertEquals("http://10.0.2.2:8472", CloudModel.normalizeServer("http://10.0.2.2:8472"))
        assertEquals("", CloudModel.normalizeServer("  "))
    }

    @Test
    fun syncStateRoundTrips() {
        val st = CloudModel.SyncState().apply {
            seq = 42
            remote["config.json"] = Entry("config.json", 3, 40, "a".repeat(64), 10, false, false, "dev-b")
            base["config.json"] = Base(3, "a".repeat(64))
            lastConfig = "b".repeat(64); lastConfigFiles = setOf("b.wav", "a.wav"); lastState = "c".repeat(64); lastLogs = null
            requests = listOf(RingRequest("r1", null, 4, "2026-11-02T01:00:00Z", "dev-a", "폰"))
            handled["r0"] = 123L
            cache["a.wav"] = CloudModel.FileSig(5, 6, "d".repeat(64))
        }
        val back = CloudModel.SyncState.from(Json.parse(Json.write(st.toMap(), 0)).jObj())
        assertEquals(st.toMap(), back.toMap())
        assertEquals(0L, CloudModel.SyncState.from(mapOf("v" to 99L)).seq)
    }

    @Test
    fun sanitizeConfigDropsGarbageAndKeepsValidRows() {
        val cfg = mapOf<String, Any?>(
            "app" to "MaplTajong", "kind" to "config", "format" to 1L,
            "sounds" to listOf(
                mapOf<String, Any?>("id" to 5L, "name" to "bell", "file_name" to "bell.wav", "volume" to Double.NaN),
                mapOf<String, Any?>("id" to 6L, "name" to "bad", "file_name" to "../outside.wav", "volume" to 1.0),
            ),
            "schedule_sets" to listOf(mapOf<String, Any?>("id" to 3L, "name" to "평일")),
            "schedules" to listOf(
                mapOf<String, Any?>("id" to 7L, "set_id" to 3L, "name" to "1교시", "weekday_mask" to 127L,
                    "time_hhmm" to "09:00", "sound_id" to 5L),
                mapOf<String, Any?>("id" to 8L, "set_id" to 3L, "name" to "bad", "weekday_mask" to 127L,
                    "time_hhmm" to "25:99", "sound_id" to 5L),
            ),
            "settings" to mapOf("active_set_id" to "3"),
        )
        val clean = CloudModel.sanitizeConfig(cfg)
        assertEquals(listOf("bell.wav"), CloudModel.rows(clean, "sounds").map { it["file_name"] })
        assertEquals(1.0, CloudModel.rows(clean, "sounds")[0]["volume"])
        assertEquals(listOf(7L), CloudModel.rows(clean, "schedules").map { it["id"] })
    }

    @Test
    fun sanitizeStateDropsWrongShapesAndInvalidRequests() {
        val clean = CloudModel.sanitizeState(mapOf(
            "app" to "MaplTajong", "kind" to "state", "format" to 1L, "paused" to "yes",
            "overrides" to listOf(
                mapOf<String, Any?>("date" to "2026-11-04", "schedule_id" to 7L, "action" to CloudModel.SKIP),
                mapOf<String, Any?>("date" to "bad", "schedule_id" to 7L, "action" to CloudModel.SKIP),
            ),
            "ring_requests" to listOf(
                mapOf<String, Any?>("id" to "ok", "schedule_id" to 7L, "at" to "2026-11-03T00:00:00Z"),
                mapOf<String, Any?>("id" to "bad", "sound_id" to -1L, "at" to "bad"),
            ),
        ))
        val parsed = CloudModel.parseState(clean)
        assertFalse(parsed.paused)
        assertEquals(1, parsed.overrides.size)
        assertEquals(listOf("ok"), parsed.requests.map { it.id })
    }
}
