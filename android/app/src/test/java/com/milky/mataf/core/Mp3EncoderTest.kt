package com.milky.mataf.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.File
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.min
import kotlin.math.sin

class Mp3EncoderTest {
    private data class Info(val rate: Int, val kbps: Set<Int>, val mono: Boolean, val seconds: Double)

    /** 440Hz 소리를 chunk 프레임씩 나눠 넣어 MP3 로 바꾼다 */
    private fun encode(name: String, rate: Int, ch: Int, seconds: Double, chunk: Int = 4096): ByteArray {
        val out = ByteArrayOutputStream()
        Mp3Encoder(rate, ch).use { enc ->
            val total = (rate * seconds).toInt()
            var i = 0
            while (i < total) {
                val n = min(chunk, total - i)
                val s = FloatArray(n * ch) { k -> (0.4 * sin(2 * PI * 440 * (i + k / ch) / rate)).toFloat() }
                enc.encode(s, ch, out)
                i += n
            }
            enc.finish(out)
        }
        // 다른 프로그램(ffmpeg 등)으로 들어 볼 수 있게 남겨 둔다 (build 폴더라 저장소에는 안 들어감)
        File("build/test-mp3").apply { mkdirs() }.resolve("$name.mp3").writeBytes(out.toByteArray())
        return out.toByteArray()
    }

    /** MP3 프레임 머리말을 처음부터 끝까지 따라가며 읽는다 (MPEG-1/2/2.5 Layer III) */
    private fun parse(b: ByteArray): Info {
        val rates = mapOf(3 to intArrayOf(44100, 48000, 32000), 2 to intArrayOf(22050, 24000, 16000), 0 to intArrayOf(11025, 12000, 8000))
        val mpeg1 = intArrayOf(0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
        val mpeg2 = intArrayOf(0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
        var p = 0
        var rate = 0
        var mono = false
        var samples = 0L
        val kbps = mutableSetOf<Int>()
        while (p + 4 <= b.size) {
            val h = (0 until 4).fold(0) { acc, k -> (acc shl 8) or (b[p + k].toInt() and 0xff) }
            assertEquals("프레임 머리말이 아니에요 (위치 $p)", 0x7ff, h ushr 21)
            val ver = (h ushr 19) and 3
            assertEquals("Layer III", 1, (h ushr 17) and 3)
            rate = rates.getValue(ver)[(h ushr 10) and 3]
            val k = (if (ver == 3) mpeg1 else mpeg2)[(h ushr 12) and 15]
            kbps += k
            mono = ((h ushr 6) and 3) == 3
            samples += if (ver == 3) 1152 else 576
            p += (if (ver == 3) 144 else 72) * k * 1000 / rate + ((h ushr 9) and 1)
        }
        assertEquals("마지막 프레임이 잘렸어요", b.size, p)
        return Info(rate, kbps, mono, samples.toDouble() / rate)
    }

    private fun assertLength(expected: Double, info: Info) =
        assertTrue("길이 ${info.seconds}초 (기대 ${expected}초)", abs(info.seconds - expected) < 0.1)

    @Test
    fun stereoBellBecomes192kMp3OfSameLength() {
        val info = parse(encode("stereo44100", 44100, 2, 2.0))
        assertEquals(44100, info.rate)
        assertEquals(setOf(192), info.kbps)
        assertEquals(false, info.mono)
        assertLength(2.0, info)
    }

    @Test
    fun monoLowRateStaysMono() {
        val info = parse(encode("mono22050", 22050, 1, 1.5, chunk = 1000))
        assertEquals(22050, info.rate)
        assertEquals(1, info.kbps.size)               // 고정 비트레이트
        assertEquals(true, info.mono)
        assertLength(1.5, info)
    }

    @Test
    fun highSampleRateIsResampled() {
        val info = parse(encode("hi96000", 96000, 2, 1.0))
        assertEquals(48000, info.rate)                // MP3 가 받는 가장 높은 값으로
        assertLength(1.0, info)
    }

    @Test
    fun moreThanTwoChannelsUsesFrontPair() {
        val enc = Mp3Encoder(48000, 6)
        enc.close()
        assertEquals(2, enc.channels)
        val info = parse(encode("six48000", 48000, 6, 1.0))
        assertEquals(false, info.mono)
        assertLength(1.0, info)
    }
}
