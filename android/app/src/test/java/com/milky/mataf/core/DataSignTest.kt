package com.milky.mataf.core

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DataSignTest {
    // 데스크톱 tests/test_data_sign.py 와 같은 값 (PC 와 안드로이드가 같은 서명을 만드는지)
    private val vectorKey = "test-key"
    private val vectorDoc = "{\"app\":\"tajong\",\"sig\":\"" + "0".repeat(64) + "\",\"v\":1}"
    private val vectorSig = "04ea5198af2926906353ebd72e8967c86760cb18b8bebba19f1f7998ead70484"
    private val key = "Zm9vYmFyLWtleS1mb3ItdGVzdHMtb25seS0xMjM0NTY3OA"

    @Test
    fun fixedVectorMatchesDesktop() {
        val signed = DataSign.sign(vectorDoc.toByteArray(Charsets.UTF_8), vectorKey)
        assertEquals(vectorDoc.replace("0".repeat(64), vectorSig), String(signed, Charsets.UTF_8))
        assertTrue(DataSign.verify(signed, vectorKey))
        assertFalse(DataSign.verify(signed, "other-key"))
        assertFalse(DataSign.verify(vectorDoc.toByteArray(Charsets.UTF_8), vectorKey))
    }

    @Test
    fun signedJsonRoundTrips() {
        val doc = linkedMapOf<String, Any?>("app" to "MaplTajong", "kind" to "config", "name" to "1교시 \"종\" \\", "list" to listOf(1L, 2.5, null))
        val bytes = DataSign.signedJson(doc, key)
        assertTrue(DataSign.verify(bytes, key))
        val back = Json.parse(String(bytes, Charsets.UTF_8)).jObj()!!
        assertTrue(Regex("^[0-9a-f]{64}$").matches(back["sig"] as String))
        assertEquals(doc, back.filterKeys { it != "sig" })
        assertFalse(doc.containsKey("sig"))   // 넘긴 것은 그대로
        assertTrue(DataSign.verify(DataSign.signedJson(doc, key, 0), key))
        // 서명은 내용 비교에 넣지 않는다
        assertEquals(CloudModel.contentHash(doc), CloudModel.contentHash(back))
    }

    @Test
    fun anyChangeBreaksSignature() {
        val bytes = DataSign.signedJson(linkedMapOf("app" to "MaplTajong", "name" to "1교시", "paused" to false), key)
        val text = String(bytes, Charsets.UTF_8)
        val sig = Json.parse(text).jObj()!!["sig"] as String
        val bad = listOf(
            text.replace("1교시", "2교시").toByteArray(Charsets.UTF_8),
            text.replace("false", "true").toByteArray(Charsets.UTF_8),
            byteArrayOf(0xEF.toByte(), 0xBB.toByte(), 0xBF.toByte()) + bytes,   // BOM 도 그대로 본다
            bytes + "\n".toByteArray(),
            text.replace(sig, "0".repeat(64)).toByteArray(Charsets.UTF_8),
            text.replaceFirst("{", "{\n  \"sig\": \"$sig\",").toByteArray(Charsets.UTF_8),   // 서명이 둘
            text.replace("\"sig\"", "\"Sig\"").toByteArray(Charsets.UTF_8),               // 서명 없음
            text.replace(sig, sig.uppercase()).toByteArray(Charsets.UTF_8),
            byteArrayOf(0xFF.toByte()) + bytes,                                           // UTF-8 이 아님
        )
        for (b in bad) assertFalse(String(b, Charsets.UTF_8), DataSign.verify(b, key))
        val spaced = DataSign.sign(vectorDoc.replace("\"sig\":", "\"sig\" :\n\t").toByteArray(Charsets.UTF_8), vectorKey)
        assertTrue(DataSign.verify(spaced, vectorKey))
    }

    @Test
    fun signNeedsOnePlaceholder() {
        assertTrue(runCatching { DataSign.sign("{\"app\":\"tajong\"}".toByteArray(), key) }.isFailure)
        assertTrue(runCatching { DataSign.sign(vectorDoc.replace("0".repeat(64), vectorSig).toByteArray(), key) }.isFailure)
    }

    @Test
    fun trustRules() {
        val signed = DataSign.signedJson(linkedMapOf("app" to "MaplTajong"), key)
        val signedDoc = Json.parse(String(signed, Charsets.UTF_8)).jObj()!!
        val plain = Json.write(linkedMapOf("app" to "MaplTajong")).toByteArray(Charsets.UTF_8)
        val plainDoc = Json.parse(String(plain, Charsets.UTF_8)).jObj()!!
        val forged = String(signed, Charsets.UTF_8).replace("MaplTajong", "Forged").toByteArray(Charsets.UTF_8)
        val forgedDoc = Json.parse(String(forged, Charsets.UTF_8)).jObj()!!
        // 키가 없으면(예전 서버) 예전처럼 다 받는다
        assertEquals(DataSign.Trust.OK, DataSign.trust(forged, forgedDoc, null, signedBefore = true))
        assertEquals(DataSign.Trust.OK, DataSign.trust(plain, plainDoc, null, signedBefore = true))
        assertEquals(DataSign.Trust.OK, DataSign.trust(signed, signedDoc, key, signedBefore = false))
        assertEquals(DataSign.Trust.OK, DataSign.trust(signed, signedDoc, key, signedBefore = true))
        // 서명 없는 예전 파일은 처음 서명하기 전까지만
        assertEquals(DataSign.Trust.UNSIGNED, DataSign.trust(plain, plainDoc, key, signedBefore = false))
        assertEquals(DataSign.Trust.REJECTED, DataSign.trust(plain, plainDoc, key, signedBefore = true))
        // 서명이 틀리면 언제나 받지 않는다
        assertEquals(DataSign.Trust.REJECTED, DataSign.trust(forged, forgedDoc, key, signedBefore = false))
        assertEquals(DataSign.Trust.REJECTED, DataSign.trust(signed, signedDoc, "other-key", signedBefore = false))
    }

    @Test
    fun signsSameBytesAsDesktopWouldVerify() {
        // 사람이 읽기 좋게 쓴 config.json (Json.write) 도 서명 자리만 바뀌고 나머지 바이트는 그대로
        val cfg = CloudModel.configFile(mapOf("sounds" to listOf(linkedMapOf<String, Any?>("id" to 1L, "name" to "종", "file_name" to "bell1.wav",
            "volume" to 1.0))), "1", CloudModel.meta("dev", "폰", java.time.Instant.EPOCH))
        val zero = Json.write(LinkedHashMap(cfg).apply { put("sig", DataSign.ZERO) }).toByteArray(Charsets.UTF_8)
        val signed = DataSign.signedJson(cfg, key)
        assertEquals(zero.size, signed.size)
        val sig = Json.parse(String(signed, Charsets.UTF_8)).jObj()!!["sig"] as String
        assertArrayEquals(zero, String(signed, Charsets.UTF_8).replace(sig, DataSign.ZERO).toByteArray(Charsets.UTF_8))
    }
}
