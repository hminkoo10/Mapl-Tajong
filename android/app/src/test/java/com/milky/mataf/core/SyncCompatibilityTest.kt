package com.milky.mataf.core

import java.io.File
import java.time.Instant
import java.time.LocalDate
import org.junit.Assert.*
import org.junit.Test

/** Cross-platform wire fixtures: PC build_config/build_state, Android configFile/stateFile. */
class SyncCompatibilityTest {
    private val key = "sync-compat-test-key-한글-only"
    private val today = LocalDate.parse("2026-11-03")
    private val meta = CloudModel.meta("fixture-android", "교무실 Android", Instant.parse("2026-11-03T12:37:54Z"))

    private fun bytes(device: String, name: String): ByteArray =
        requireNotNull(javaClass.getResourceAsStream("/sync/$device/$name.json")).use { it.readBytes() }

    private fun doc(device: String, name: String) = Json.parse(String(bytes(device, name), Charsets.UTF_8)).jObj()!!

    private fun assertContent(expected: Map<String, Any?>, actual: Map<String, Any?>) =
        assertEquals(CloudModel.content(expected), CloudModel.content(actual))

    private fun androidDocuments(): Map<String, Map<String, Any?>> {
        // Same rows a SQLite cursor supplies to Cloud.buildConfig; use the actual wire builder.
        val tables = CloudModel.TABLES.mapValues { (table, _) -> CloudModel.rows(doc("pc", "config"), table) }
        val overrides = listOf(
            CloudModel.Override(today.toString(), 7, CloudModel.SKIP, "admin"),
            CloudModel.Override(today.toString(), 0, CloudModel.PAUSE_DAY, "admin"),
            CloudModel.Override(today.toString(), 9, "FIRED_ONCE", "local only"),
        )
        val requests = listOf(
            CloudModel.RingRequest("schedule-request", 7, null, "2026-11-03T12:37:54Z", "fixture-sender", "교무실 폰 🔔", "2026-11-03T12:37:57.257Z"),
            CloudModel.RingRequest("sound-request", null, 8, "2026-11-03T12:37:54Z", "fixture-sender", "교무실 폰 🔔", "2026-11-03T12:37:57.000Z"),
        )
        return linkedMapOf(
            "config" to CloudModel.configFile(tables, "3", meta),
            "paused" to CloudModel.stateFile(true, overrides, requests, today, meta),
            "day" to CloudModel.stateFile(false, overrides, requests, today, meta),
            "resumed" to CloudModel.stateFile(false, emptyList(), emptyList(), today, meta),
        )
    }

    @Test
    fun androidSnapshotsAreActualBuilderAndSignerOutput() {
        // Explicit opt-in regeneration only; normal test runs never rewrite golden fixtures.
        val output = System.getenv("TAJONG_WRITE_SYNC_FIXTURES")?.let { File(it, "android").apply { mkdirs() } }
        for ((name, document) in androidDocuments()) {
            val generated = DataSign.signedJson(document, key)
            if (output != null) File(output, "$name.json").writeBytes(generated)
            else assertArrayEquals(name, bytes("android", name), generated)
            assertContent(doc("pc", name), document)
        }
    }

    @Test
    fun pcConfigSurvivesParserSanitizerAndDatabaseRowProjection() {
        val input = doc("pc", "config")
        assertTrue(CloudModel.isConfig(input))
        val safe = CloudModel.sanitizeConfig(input)
        assertContent(input, safe)
        assertEquals(input["meta"], safe["meta"])
        val tables = CloudModel.TABLES.mapValues { (table, cols) ->
            CloudModel.rows(safe, table).map { row -> row.filterKeys { it in cols } }
        }
        assertContent(input, CloudModel.configFile(tables, safe["settings"].jObj()!!["active_set_id"] as String, meta))
    }

    @Test
    fun pcStatePreservesPauseDayZeroSkipOnceAndMillisecondRequests() {
        val config = CloudModel.sanitizeConfig(doc("pc", "config"))
        val scheduleIds = CloudModel.rows(config, "schedules").map { it["id"].jLong()!! }.toSet()
        val soundIds = CloudModel.rows(config, "sounds").map { it["id"].jLong()!! }.toSet()
        for (name in listOf("paused", "day", "resumed", "paused")) {
            val input = doc("pc", name)
            assertTrue(CloudModel.isState(input))
            assertContent(input, CloudModel.sanitizeState(input))
            val parsed = CloudModel.parseState(input)
            val applied = CloudModel.referencedState(parsed, scheduleIds, soundIds)
            assertEquals(parsed, applied)
            assertContent(input, CloudModel.stateFile(applied.paused, applied.overrides, applied.requests, today, meta))
            if (name != "resumed") {
                assertTrue(applied.overrides.any { it.action == CloudModel.PAUSE_DAY && it.scheduleId == 0L })
                assertEquals(Instant.parse("2026-11-03T12:37:57.257Z"), applied.requests[0].ringInstant)
                assertEquals(applied.requests, CloudModel.dueRequests(applied.requests, emptySet(), Instant.parse("2026-11-03T12:37:54Z")))
            }
        }
    }

    @Test
    fun phone227RealFilesSurviveSanitizers() {
        // Account key unknown: this checks real payloads, not the original signatures.
        val config = doc("phone-2.2.7", "config")
        val state = doc("phone-2.2.7", "state")
        assertContent(config, CloudModel.sanitizeConfig(config))
        assertContent(state, CloudModel.sanitizeState(state))
        val parsed = CloudModel.parseState(state)
        val safe = CloudModel.referencedState(parsed, emptySet(), CloudModel.rows(config, "sounds").map { it["id"].jLong()!! }.toSet())
        assertEquals(parsed, safe)
        assertTrue(safe.paused)
        assertEquals("2026-11-03T12:37:57.257Z", safe.requests.single().ringAt)
    }

    @Test
    fun pcSignaturesVerifyOnOriginalBytes() {
        for (name in listOf("config", "paused", "day", "resumed")) {
            val raw = bytes("pc", name)
            assertTrue(name, DataSign.verify(raw, key))
            assertFalse(DataSign.verify(raw, "wrong-key"))
            assertFalse(DataSign.verify(raw + byteArrayOf(10), key))
            assertEquals(DataSign.Trust.OK, DataSign.trust(raw, doc("pc", name), key, true))
        }
    }

    @Test
    fun unsignedPcFilesAcceptedOnlyBeforeFirstSignature() {
        for (name in listOf("config", "paused")) {
            val old = doc("pc", name).filterKeys { it != "sig" }
            val raw = Json.write(old).toByteArray(Charsets.UTF_8)
            assertEquals(DataSign.Trust.UNSIGNED, DataSign.trust(raw, old, key, false))
            val resigned = DataSign.signedJson(old, key)
            assertTrue(DataSign.verify(resigned, key))
            assertEquals(DataSign.Trust.REJECTED, DataSign.trust(raw, old, key, true))
            assertEquals(DataSign.Trust.OK, DataSign.trust(raw, old, null, true))
        }
    }

    @Test
    fun oldPcRequestWithoutRingAtUsesAt() {
        val input = doc("pc", "paused").toMutableMap()
        input["ring_requests"] = input["ring_requests"].jList().map { it.jObj()!!.filterKeys { k -> k != "ring_at" } }
        val state = CloudModel.parseState(input)
        assertContent(input, CloudModel.stateFile(state.paused, state.overrides, state.requests, today, meta))
        assertEquals(state.requests[0].instant, state.requests[0].ringInstant)
    }

    @Test
    fun manualRingUsesNextUnblockedOccurrence() {
        // Scheduler.nextDateOf passes PAUSE_DAY / SKIP_ONCE / FIRED_ONCE as this predicate.
        val blocked = (0L..2L).map { today.plusDays(it) }.toMutableSet()
        assertEquals(today.plusDays(3), CloudModel.nextOccurrence(127, "09:00", today.atTime(8, 0)) { it in blocked })
        blocked += (3L..7L).map { today.plusDays(it) }
        assertNull(CloudModel.nextOccurrence(127, "09:00", today.atTime(8, 0)) { it in blocked })
    }

    @Test
    fun newServerRevisionAppliesBothPauseTransitionsWithoutEcho() {
        var local = doc("pc", "resumed")
        var lastHash = CloudModel.contentHash(local)
        var base = CloudModel.Base(1, "old-sha")
        for (name in listOf("paused", "day", "resumed")) {
            val remote = doc("pc", name)
            val entry = CloudModel.Entry(CloudModel.STATE, base.rev + 1, base.rev + 1, CloudModel.sha256(bytes("pc", name)), 1, false, false, "pc")
            assertEquals(CloudModel.Pull.APPLY, CloudModel.decideState(base, entry, CloudModel.contentHash(local), lastHash, CloudModel.contentHash(remote)))
            val state = CloudModel.parseState(remote)
            local = CloudModel.stateFile(state.paused, state.overrides, state.requests, today, meta)
            lastHash = CloudModel.contentHash(local)
            base = CloudModel.Base(entry.rev, entry.sha)
            assertEquals(CloudModel.Pull.NONE, CloudModel.decideState(base, entry, lastHash, lastHash, null))
            assertContent(remote, local)
            val next = CloudModel.nextOccurrence(127, "09:00", today.atTime(8, 0)) { day ->
                state.overrides.any { it.date == day.toString() && it.action == CloudModel.PAUSE_DAY }
            }
            assertEquals(if (name == "resumed") today else today.plusDays(1), next)
        }
    }
}
