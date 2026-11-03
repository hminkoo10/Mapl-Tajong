package com.milky.mataf.core

import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * 설정 파일 서명 (앱 밖에서 손으로 바꾼 설정은 적용하지 않으려고). 데스크톱 app/core/data_sign.py 와 같다.
 * 키는 서버가 준다 (GET /api/me/data-key). 키가 없으면(예전 서버) 서명하지 않고 확인하지도 않는다.
 *
 * PC 와 바이트까지 같아야 해서 정규화 JSON 이 아니라 쓴 글자 그대로 다룬다.
 * - 서명: 맨 위에 "sig": "000…0"(0 64개)을 넣어 평소처럼 직렬화 → UTF-8 바이트 B,
 *   sig = HMAC-SHA256(키 글자의 UTF-8 바이트, B) 의 소문자 16진수. B 의 그 0 자리만 sig 로 바꿔 쓴다 (길이 같음)
 * - 확인: 받은 바이트 그대로(BOM·공백도 그대로) UTF-8 로 읽어 "sig"\s*:\s*"([0-9a-f]{64})" 가 꼭 하나 있어야 하고,
 *   그 64자를 0 으로 바꾼 바이트의 HMAC 과 같아야 한다 (상수 시간 비교)
 * 안드로이드에 기대지 않아 JVM 시험으로 확인한다.
 */
object DataSign {
    val ZERO = "0".repeat(64)
    private val SIG = Regex("\"sig\"\\s*:\\s*\"([0-9a-f]{64})\"")

    /** 받은 파일을 어떻게 볼지: 서명이 맞음 / 서명하기 전 버전이 쓴 것(처음 한 번만 받음) / 받지 않음(앱 밖에서 바꿈) */
    enum class Trust { OK, UNSIGNED, REJECTED }

    private fun mac(key: String, data: ByteArray): String {
        val m = Mac.getInstance("HmacSHA256")
        m.init(SecretKeySpec(key.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        return m.doFinal(data).joinToString("") { "%02x".format(it) }
    }

    /** bytes 에 "sig": "000…0" 이 하나만 있어야 한다. 그 자리에 서명을 넣은 바이트를 돌려준다 */
    fun sign(bytes: ByteArray, key: String): ByteArray {
        val text = String(bytes, Charsets.UTF_8)
        val found = SIG.findAll(text).toList()
        require(found.size == 1 && found[0].groupValues[1] == ZERO) { "서명 자리가 없어요" }
        val r = found[0].groups[1]!!.range
        return text.replaceRange(r, mac(key, bytes)).toByteArray(Charsets.UTF_8)
    }

    /** Json.write(m, indent) 와 같게 쓰되 "sig" 를 넣어 서명한 UTF-8 바이트 */
    fun signedJson(m: Map<String, Any?>, key: String, indent: Int = 2): ByteArray =
        sign(Json.write(LinkedHashMap(m).apply { put("sig", ZERO) }, indent).toByteArray(Charsets.UTF_8), key)

    /** 서명이 맞으면 true. 없거나, 둘 이상이거나, 틀리면 false */
    fun verify(bytes: ByteArray, key: String): Boolean {
        val text = String(bytes, Charsets.UTF_8)
        val found = SIG.findAll(text).toList()
        if (found.size != 1) return false
        val blank = text.replaceRange(found[0].groups[1]!!.range, ZERO).toByteArray(Charsets.UTF_8)
        return MessageDigest.isEqual(mac(key, blank).toByteArray(Charsets.US_ASCII), found[0].groupValues[1].toByteArray(Charsets.US_ASCII))
    }

    /**
     * key: 서버가 준 키 (null 이면 서명을 쓰지 않음 → 늘 OK)
     * signedBefore: 이 기기에서 이 계정의 그 파일에 이미 서명했는지 (그 뒤로는 서명 없는 파일을 받지 않는다)
     */
    fun trust(bytes: ByteArray, doc: Map<String, Any?>, key: String?, signedBefore: Boolean): Trust = when {
        key.isNullOrEmpty() -> Trust.OK
        verify(bytes, key) -> Trust.OK
        !doc.containsKey("sig") && !signedBefore -> Trust.UNSIGNED
        else -> Trust.REJECTED
    }
}
