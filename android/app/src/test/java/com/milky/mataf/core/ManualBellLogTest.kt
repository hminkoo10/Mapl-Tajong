package com.milky.mataf.core

import com.milky.mataf.ui.screens.detailText
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ManualBellLogTest {
    private val rows = mutableListOf<Map<String, Any?>>()

    private fun report(scheduleId: Long? = null, detail: String? = null): (String?) -> Unit =
        manualRingReport(scheduleId, if (scheduleId == null) "" else "1교시", "학교종", detail) { id, name, sound, result, memo ->
            rows += mapOf("occurred_at" to "2026-11-03 09:00:00", "schedule_id" to id, "schedule_name" to name,
                "sound_name" to sound, "result" to result, "detail" to memo)
        }

    @Test
    fun localSoundRecordsManualPlayback() {
        report()(null)
        assertEquals(1, rows.size)
        assertNull(rows.single()["schedule_id"])
        assertEquals("", rows.single()["schedule_name"])
        assertEquals("학교종", rows.single()["sound_name"])
        assertEquals("PLAYED", rows.single()["result"])
        assertEquals("forced", rows.single()["detail"])
    }

    @Test
    fun localSoundFailureKeepsManualMarker() {
        report()("파일 없음")
        assertEquals(1, rows.size)
        assertEquals("FAILED", rows.single()["result"])
        assertEquals("forced · 파일 없음", rows.single()["detail"])
    }

    @Test
    fun remoteSoundKeepsRequesterOnSuccessAndFailure() {
        report(detail = "forced · 교무실 PC")(null)
        report(detail = "forced · 교무실 PC")("파일 없음")
        assertEquals(listOf("PLAYED", "FAILED"), rows.map { it["result"] })
        assertEquals(listOf("forced · 교무실 PC", "forced · 교무실 PC · 파일 없음"), rows.map { it["detail"] })
    }

    @Test
    fun manualScheduleKeepsScheduleAndSource() {
        report(7)(null)
        report(7, "forced · 교무실 PC")("파일 없음")
        assertEquals(listOf(7L, 7L), rows.map { it["schedule_id"] })
        assertEquals(listOf("1교시", "1교시"), rows.map { it["schedule_name"] })
        assertEquals(listOf("forced", "forced · 교무실 PC · 파일 없음"), rows.map { it["detail"] })
    }

    @Test
    fun preparingWithoutPlaybackDoesNotRecord() {
        report()
        assertTrue(rows.isEmpty())
    }

    @Test
    fun manualLogSurvivesCloudRoundTrip() {
        report()(null)
        val doc = CloudModel.logsFile("phone", "휴대폰", rows)
        val parsed = CloudModel.parseLogs(Json.parse(Json.write(doc)).jObj()!!)!!
        assertEquals(1, parsed.rows.size)
        assertNull(parsed.rows.single().scheduleId)
        assertEquals("학교종", parsed.rows.single().soundName)
        assertEquals("forced", parsed.rows.single().detail)
    }

    @Test
    fun legacyLogsWithoutDetailStillLoad() {
        val doc = mapOf("app" to CloudModel.APP, "kind" to "logs", "logs" to listOf(
            mapOf("occurred_at" to "2026-11-03 09:00:00", "schedule_id" to 7L, "result" to "PLAYED")))
        val parsed = CloudModel.parseLogs(doc)!!
        assertEquals(7L, parsed.rows.single().scheduleId)
        assertEquals("", parsed.rows.single().detail)
    }

    @Test
    fun manualDetailsDisplayAsManualAndOldDetailsStayUnchanged() {
        assertEquals("수동 타종", detailText("forced"))
        assertEquals("수동 타종 · 교무실 PC", detailText("forced · 교무실 PC"))
        assertEquals("수동 타종 · 파일 없음", detailText("forced · 파일 없음"))
        assertEquals("", detailText(""))
        assertEquals("late=121s", detailText("late=121s"))
    }
}
