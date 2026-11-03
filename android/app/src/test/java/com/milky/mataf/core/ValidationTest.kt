package com.milky.mataf.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.PrintStream

class ValidationTest {
    private fun config(): Map<String, Any?> = mapOf(
        "app" to "MaplTajong", "kind" to "config", "format" to 1L,
        "sounds" to listOf(mapOf("id" to 5L, "name" to "bell", "file_name" to "bell.wav", "volume" to 1.0)),
        "schedule_sets" to listOf(mapOf("id" to 3L, "name" to "평일")),
        "schedules" to listOf(mapOf("id" to 7L, "set_id" to 3L, "name" to "1교시", "weekday_mask" to 127L,
            "time_hhmm" to "09:00", "sound_id" to 5L)),
        "settings" to mapOf("active_set_id" to "3"),
    )

    private fun row(table: String) = CloudModel.rows(config(), table).single()

    @Test
    fun validBoundariesAndSharedSoundFilesSurvive() {
        val cfg = config() + mapOf(
            "sounds" to listOf(row("sounds") + ("volume" to 2.0), row("sounds") + mapOf("id" to 6L, "volume" to 0.0)),
            "schedules" to listOf(row("schedules") + mapOf("time_hhmm" to "00:00", "enabled" to 0L, "volume_override" to 2.0),
                row("schedules") + mapOf("id" to 8L, "time_hhmm" to "23:59", "weekday_mask" to 1L)),
        )
        val clean = CloudModel.sanitizeTables(cfg)
        assertEquals(2, CloudModel.rows(clean, "sounds").size)
        assertEquals(listOf("00:00", "23:59"), CloudModel.rows(clean, "schedules").map { it["time_hhmm"] })
        assertEquals(0L, CloudModel.rows(clean, "schedules")[0]["enabled"])
    }

    @Test
    fun unsafePathsAreDroppedNotRebased() {
        for (path in listOf("../a.wav", "..\\a.wav", "/tmp/a.wav", "C:/a.wav", "C:a.wav", "\\\\server\\a.wav",
            "a.wav:stream", "sounds/../a.wav", "a.wav ", "a.", "NUL.wav", "COM1.wav", "CONIN$", "a\u0000.wav", "x".repeat(201),
            "한".repeat(100) + ".wav", "\uD800.wav")) {
            val cfg = config() + ("sounds" to listOf(row("sounds"), row("sounds") + mapOf("id" to 6L, "file_name" to path)))
            assertEquals(path, listOf(5L), CloudModel.rows(CloudModel.sanitizeTables(cfg), "sounds").map { it["id"] })
            assertEquals(setOf("bell.wav"), CloudModel.soundFiles(cfg))
        }
        assertEquals("a.wav", CloudModel.soundName("sounds/a.wav"))
    }

    @Test
    fun badIdsAndWrongShapesKeepGoodRows() {
        for (id in listOf(true, false, 0L, -1L, 1.5, Double.POSITIVE_INFINITY, Double.NaN, Long.MAX_VALUE, "9".repeat(5000), "6", emptyList<Any>(), emptyMap<String, Any>())) {
            val cfg = config() + ("sounds" to listOf(null, 1L, emptyList<Any>(), row("sounds") + ("id" to id), row("sounds")))
            assertEquals(listOf(5L), CloudModel.rows(CloudModel.sanitizeTables(cfg), "sounds").map { it["id"] })
        }
        val cfg = config() + ("sounds" to listOf(row("sounds") + ("id" to "HUGE"), row("sounds")))
        val parsed = Json.parse(Json.write(cfg).replace("\"HUGE\"", "9".repeat(5000))).jObj()!!
        assertEquals(listOf(5L), CloudModel.rows(CloudModel.sanitizeTables(parsed), "sounds").map { it["id"] })
    }

    @Test
    fun optionalValuesAndUnknownColumnsAreSanitized() {
        val cfg = config() + mapOf(
            "sounds" to listOf(row("sounds") + mapOf("volume" to Double.NaN, "created_at" to emptyList<Any>(), "updated_at" to "2026-11-03")),
            "schedules" to listOf(row("schedules") + mapOf("volume_override" to -1, "sort_order" to 1e100, "enabled" to "yes", "updated_at" to "bad")),
        )
        val clean = CloudModel.sanitizeTables(cfg)
        val sound = CloudModel.rows(clean, "sounds").single()
        assertEquals(1.0, sound["volume"])
        assertFalse(sound.containsKey("updated_at"))
        assertFalse(sound.containsKey("created_at"))
        val schedule = CloudModel.rows(clean, "schedules").single()
        assertNull(schedule["volume_override"])
        assertEquals(0L, schedule["sort_order"])
        assertEquals(1L, schedule["enabled"])
        val strings = CloudModel.sanitizeTables(config() + mapOf("sounds" to listOf(row("sounds") + ("volume" to "2")),
            "schedules" to listOf(row("schedules") + mapOf("volume_override" to "2", "enabled" to "0"))))
        assertEquals(1.0, CloudModel.rows(strings, "sounds").single()["volume"])
        assertNull(CloudModel.rows(strings, "schedules").single()["volume_override"])
        assertEquals(1L, CloudModel.rows(strings, "schedules").single()["enabled"])
    }

    @Test
    fun duplicatesDoNotHideLaterValidRows() {
        val cfg = config() + mapOf(
            "sounds" to listOf(row("sounds") + ("name" to emptyList<Any>()), row("sounds"), row("sounds")),
            "schedule_sets" to listOf(row("schedule_sets"), row("schedule_sets") + ("id" to 4L)),
        )
        val clean = CloudModel.sanitizeTables(cfg)
        assertEquals(1, CloudModel.rows(clean, "sounds").size)
        assertEquals(1, CloudModel.rows(clean, "schedule_sets").size)
        assertEquals(1, CloudModel.rows(clean, "schedules").size)
    }

    @Test
    fun requiredValuesReferencesAndLimitsAreChecked() {
        val bad = listOf(mapOf("time_hhmm" to "24:00"), mapOf("time_hhmm" to "9:00"), mapOf("weekday_mask" to 128L),
            mapOf("weekday_mask" to -1L), mapOf("name" to "x".repeat(201)), mapOf("name" to "x\u0000"), mapOf("name" to "\uD800"),
            mapOf("sound_id" to 999L), mapOf("set_id" to 999L))
        val cfg = config() + ("schedules" to (listOf(row("schedules")) + bad.mapIndexed { i, fields -> row("schedules") + fields + ("id" to i + 20L) }))
        assertEquals(listOf(7L), CloudModel.rows(CloudModel.sanitizeTables(cfg), "schedules").map { it["id"] })
        for ((table, limit) in mapOf("sounds" to 256, "schedule_sets" to 128, "schedules" to 2000)) {
            val rows = (1..limit+1).map { row(table) + mapOf("id" to it.toLong(), "name" to "row$it") }
            assertEquals(limit, CloudModel.rows(CloudModel.sanitizeTables(config() + (table to rows)), table).size)
            assertTrue(CloudModel.rows(CloudModel.sanitizeTables(config() + (table to emptyMap<String, Any>())), table).isEmpty())
        }
    }

    @Test
    fun normalizationCannotTurnWrongHeaderIntoValidFile() {
        for (fmt in listOf(true, 0L, -1L, 1.5, Double.POSITIVE_INFINITY, emptyMap<String, Any>(), "9".repeat(5000), "1", 2L)) {
            assertFalse(CloudModel.isConfig(CloudModel.sanitizeConfig(config() + ("format" to fmt))))
            assertFalse(CloudModel.isState(CloudModel.sanitizeState(config() + mapOf("kind" to "state", "format" to fmt))))
        }
        assertFalse(CloudModel.isConfig(CloudModel.sanitizeConfig(config() + ("app" to "evil"))))
        assertFalse(CloudModel.isState(CloudModel.sanitizeState(config())))
        val meta = mapOf("device_id" to emptyList<Any>(), "device_name" to "x".repeat(201), "at" to "bad")
        val safe = CloudModel.sanitizeConfig(config() + ("meta" to meta))
        assertEquals(mapOf("device_id" to "", "device_name" to "", "at" to ""), safe["meta"])
    }

    @Test
    fun stateDatesReferencesAndDuplicatesAreChecked() {
        val valid = mapOf("date" to "2026-11-04", "schedule_id" to 7L, "action" to CloudModel.SKIP)
        val req = mapOf("id" to "ok", "schedule_id" to 7L, "at" to "2026-11-03T00:00:00Z")
        val state = CloudModel.parseState(mapOf("paused" to "yes",
            "overrides" to listOf(valid, valid, null, valid + ("date" to "2026-02-30"), valid + ("date" to "2026-11-4"),
                valid + ("schedule_id" to 0L), valid + ("action" to "BAD"),
                valid + mapOf("action" to CloudModel.PAUSE_DAY, "schedule_id" to 1L),
                valid + mapOf("action" to CloudModel.PAUSE_DAY, "schedule_id" to 2L)),
            "ring_requests" to listOf(req, req, emptyList<Any>(), req + mapOf("id" to "bad", "sound_id" to emptyMap<String, Any>()),
                req + mapOf("id" to "date", "at" to "2026-11-03")),
        ))
        assertFalse(state.paused)
        assertEquals(2, state.overrides.size)
        assertEquals(listOf("ok"), state.requests.map { it.id })
    }

    @Test
    fun stateLimitsAndCorrectionLogs() {
        val output = ByteArrayOutputStream()
        val previous = System.err
        try {
            System.setErr(PrintStream(output))
            val state = CloudModel.parseState(mapOf("paused" to "bad",
                "overrides" to (1..501).map { mapOf("date" to "2026-11-04", "schedule_id" to it, "action" to CloudModel.SKIP) },
                "ring_requests" to (1..2001).map { mapOf("id" to "$it", "sound_id" to 5L, "at" to "2026-11-03T00:00:00Z") }))
            assertEquals(500, state.overrides.size)
            assertEquals(2000, state.requests.size)
            assertTrue(output.toString().contains("paused"))
            assertTrue(output.toString().contains("overrides"))
            assertTrue(output.toString().contains("ring_requests"))
        } finally {
            System.setErr(previous)
        }
    }

    @Test
    fun stateDropsMissingReferencesWithoutLosingValidRequests() {
        val request = CloudModel.RingRequest("ok", 7L, 5L, "2026-11-03T00:00:00Z", "dev", "phone")
        val override = CloudModel.Override("2026-11-04", 7L, CloudModel.SKIP, "")
        val state = CloudModel.State(false, listOf(override, override.copy(scheduleId = 999L),
            override.copy(scheduleId = 0L, action = CloudModel.PAUSE_DAY)),
            listOf(request, request.copy(id = "bad", scheduleId = 999L), request.copy(id = "bad-sound", soundId = 999L)))
        val safe = CloudModel.referencedState(state, setOf(7L), setOf(5L))
        assertEquals(listOf(request), safe.requests)
        assertEquals(listOf(7L, 0L), safe.overrides.map { it.scheduleId })
    }

    @Test
    fun backupManifestRejectsBadVersionsAndRepairsCounts() {
        for (value in listOf("true", "-1", "1e999", "{}", "2", "1.5")) {
            assertThrows(BackupError::class.java) { Backup.parseManifest("{\"app\":\"MaplTajong\",\"format\":$value}") }
        }
        for (value in listOf("[]", "null", "\"text\"")) {
            assertThrows(BackupError::class.java) { Backup.parseManifest(value) }
        }
        val manifest = Backup.parseManifest("""{"app":"MaplTajong","format":1,"counts":{"sounds":-1},"app_version":[]}""")
        assertEquals(mapOf("sounds" to 0, "schedule_sets" to 0, "schedules" to 0), manifest.counts)
        assertEquals("", manifest.appVersion)
    }

    @Test
    fun internalSyncStateRejectsPathsShapesAndNonFiniteCounters() {
        val sha = "a".repeat(64)
        val entry = CloudModel.Entry("config.json", 3, 40, sha, 10, false, false, "dev").toMap()
        val good = mapOf("size" to 5L, "mtime" to 6L, "sha" to sha)
        val state = CloudModel.SyncState.from(mapOf("v" to 1L, "seq" to -1L,
            "remote" to mapOf("config.json" to entry, "../outside" to entry, "state.json" to (entry + ("rev" to Double.POSITIVE_INFINITY))),
            "base" to mapOf("config.json" to mapOf("rev" to 3L, "sha" to sha), "../outside" to mapOf("rev" to 3L)),
            "lastConfig" to emptyMap<String, Any>(), "lastConfigFiles" to listOf("ok.wav", "../evil.wav", "C:evil.wav"),
            "cache" to mapOf("ok.wav" to good, "../evil.wav" to good, "bad.wav" to (good + ("size" to -1))),
            "handled" to mapOf("ok" to 123L, "bad" to Double.NaN, "negative" to -1L), "requests" to emptyMap<String, Any>(),
        ))
        assertEquals(0L, state.seq)
        assertEquals(setOf("config.json"), state.remote.keys)
        assertEquals(setOf("config.json"), state.base.keys)
        assertEquals(setOf("ok.wav"), state.lastConfigFiles)
        assertEquals(setOf("ok.wav"), state.cache.keys)
        assertEquals(mapOf("ok" to 123L), state.handled)
        assertNull(state.lastConfig)
        assertTrue(state.requests.isEmpty())
    }
}
