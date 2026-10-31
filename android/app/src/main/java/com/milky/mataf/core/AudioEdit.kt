package com.milky.mataf.core

import android.media.AudioFormat
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.roundToInt
import kotlin.math.sqrt

/** 데스크톱 app/core/audio_edit.py 의 EditParams 와 같은 뜻 */
data class EditParams(
    val start: Double,
    val end: Double,
    val fadeIn: Double = 0.0,
    val fadeOut: Double = 0.0,
    val gainDb: Double = 0.0,
    val normalize: Boolean = false,
) {
    val length: Double get() = max(0.01, end - start)
}

/** 파형: PEAK_SEC 마다 가장 큰 소리 크기(0..1) */
class Waveform(val peaks: FloatArray, val duration: Double) {
    fun at(t: Double): Float {
        if (peaks.isEmpty()) return 0f
        val i = (t / AudioEdit.PEAK_SEC).toInt().coerceIn(0, peaks.size - 1)
        return peaks[i]
    }
}

/**
 * 소리 자르기·페이드·음량 (MediaCodec 으로 풀어서 WAV 로 저장).
 * 긴 음원도 메모리를 많이 쓰지 않게 파형은 작게 요약하고, 저장할 때는 고른 구간만 다시 푼다.
 */
object AudioEdit {
    const val PEAK_SEC = 0.01

    private class Pcm(val rate: Int, val channels: Int)

    /**
     * 파일을 처음부터 풀면서 chunk(짧은 소리 조각)를 넘겨준다.
     * onChunk(시작 시각 초, 소리[-1..1] 인터리브, 채널 수, 샘플레이트) 가 false 를 돌려주면 멈춘다.
     */
    private suspend fun decode(file: File, fromSec: Double = 0.0, onChunk: (Double, FloatArray, Int, Int) -> Boolean) {
        val ex = MediaExtractor()
        var codec: MediaCodec? = null
        try {
            ex.setDataSource(file.absolutePath)
            val track = (0 until ex.trackCount).firstOrNull {
                ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true
            } ?: throw IllegalStateException("소리가 들어 있지 않은 파일이에요.")
            ex.selectTrack(track)
            val fmt = ex.getTrackFormat(track)
            if (fromSec > 0) ex.seekTo((fromSec * 1e6).toLong(), MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
            val c = MediaCodec.createDecoderByType(fmt.getString(MediaFormat.KEY_MIME)!!)
            codec = c
            c.configure(fmt, null, null, 0)
            c.start()
            var rate = fmt.getIntegerOrNull(MediaFormat.KEY_SAMPLE_RATE) ?: 44100
            var ch = fmt.getIntegerOrNull(MediaFormat.KEY_CHANNEL_COUNT) ?: 2
            var floatPcm = false
            val info = MediaCodec.BufferInfo()
            var inDone = false
            var outDone = false
            while (!outDone) {
                currentCoroutineContext().ensureActive()
                if (!inDone) {
                    val ii = c.dequeueInputBuffer(10_000)
                    if (ii >= 0) {
                        val buf = c.getInputBuffer(ii)!!
                        val n = ex.readSampleData(buf, 0)
                        if (n < 0) {
                            c.queueInputBuffer(ii, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM); inDone = true
                        } else {
                            c.queueInputBuffer(ii, 0, n, ex.sampleTime, 0); ex.advance()
                        }
                    }
                }
                val oi = c.dequeueOutputBuffer(info, 10_000)
                when {
                    oi == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                        val of = c.outputFormat
                        rate = of.getIntegerOrNull(MediaFormat.KEY_SAMPLE_RATE) ?: rate
                        ch = of.getIntegerOrNull(MediaFormat.KEY_CHANNEL_COUNT) ?: ch
                        floatPcm = of.getIntegerOrNull(MediaFormat.KEY_PCM_ENCODING) == AudioFormat.ENCODING_PCM_FLOAT
                    }
                    oi >= 0 -> {
                        if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) outDone = true
                        if (info.size > 0) {
                            val ob: ByteBuffer = c.getOutputBuffer(oi)!!
                            ob.position(info.offset); ob.limit(info.offset + info.size)
                            ob.order(ByteOrder.LITTLE_ENDIAN)
                            val samples = if (floatPcm) {
                                FloatArray(info.size / 4).also { ob.asFloatBuffer().get(it) }
                            } else {
                                val sb = ob.asShortBuffer()
                                FloatArray(sb.remaining()) { sb.get(it) / 32768f }
                            }
                            val keep = onChunk(info.presentationTimeUs / 1e6, samples, ch, rate)
                            if (!keep) outDone = true
                        }
                        c.releaseOutputBuffer(oi, false)
                    }
                }
            }
        } finally {
            try { codec?.stop() } catch (_: Exception) {}
            try { codec?.release() } catch (_: Exception) {}
            ex.release()
        }
    }

    private fun MediaFormat.getIntegerOrNull(key: String): Int? = if (containsKey(key)) getInteger(key) else null

    /** 파형 만들기 (화면에 그릴 요약) */
    suspend fun waveform(file: File): Waveform {
        val peaks = ArrayList<Float>(30_000)
        var cur = 0f
        var bucketEnd = PEAK_SEC
        var t = 0.0
        decode(file) { at, s, ch, rate ->
            t = at
            val step = 1.0 / rate
            var i = 0
            while (i < s.size) {
                var m = 0f
                for (k in 0 until ch) if (i + k < s.size) m = max(m, abs(s[i + k]))
                if (t >= bucketEnd) {
                    peaks += cur; cur = 0f; bucketEnd += PEAK_SEC
                }
                cur = max(cur, m)
                t += step
                i += ch
            }
            true
        }
        peaks += cur
        return Waveform(peaks.toFloatArray(), t)
    }

    /** 앞뒤 조용한 부분을 뺀 구간 (데스크톱 suggest_trim 과 같은 기준) */
    fun suggestTrim(w: Waveform, from: Double = 0.0, to: Double = w.duration, threshold: Float = 0.02f): Pair<Double, Double> {
        val p = w.peaks
        if (p.isEmpty()) return 0.0 to w.duration
        val a0 = (from / PEAK_SEC).toInt().coerceIn(0, p.size - 1)
        val b0 = (to / PEAK_SEC).toInt().coerceIn(a0, p.size - 1)
        var first = a0
        while (first <= b0 && p[first] < threshold) first++
        if (first > b0) return from to to
        var last = b0
        while (last > first && p[last] < threshold) last--
        val pad = 0.05
        return max(0.0, first * PEAK_SEC - pad) to min(w.duration, (last + 1) * PEAK_SEC + pad)
    }

    /** 구간만 풀어서 편집을 적용하고 16비트 WAV 로 쓴다 */
    suspend fun render(src: File, dst: File, p: EditParams, onProgress: (Float) -> Unit = {}) {
        // 크기 자동 맞춤: 먼저 고른 구간의 크기를 잰다
        var norm = 1.0
        if (p.normalize) {
            var sum = 0.0
            var n = 0L
            var peak = 0f
            forRange(src, p) { _, s, _ ->
                for (v in s) {
                    sum += v * v; n++; peak = max(peak, abs(v))
                }
            }
            if (n > 0 && peak > 0f) {
                val rms = sqrt(sum / n)
                val target = 10.0.pow(-16.0 / 20)   // 다른 종소리와 비슷한 크기
                norm = min(target / max(rms, 1e-6), 0.98 / peak)
            }
        }
        val gain = norm * 10.0.pow(p.gainDb / 20)
        dst.parentFile?.mkdirs()
        val raf = RandomAccessFile(dst, "rw")
        raf.setLength(0)
        raf.write(ByteArray(44))
        var written = 0L
        var fmt: Pcm? = null
        try {
            val buf = ByteBuffer.allocate(256 * 1024).order(ByteOrder.LITTLE_ENDIAN)
            forRange(src, p) { rel, s, pcm ->
                fmt = pcm
                val ch = pcm.channels
                val frames = s.size / ch
                buf.clear()
                for (f in 0 until frames) {
                    val t = rel + f.toDouble() / pcm.rate
                    var env = gain
                    if (p.fadeIn > 0 && t < p.fadeIn) env *= t / p.fadeIn
                    val left = p.length - t
                    if (p.fadeOut > 0 && left < p.fadeOut) env *= max(0.0, left / p.fadeOut)
                    for (k in 0 until ch) {
                        val v = (s[f * ch + k] * env).coerceIn(-1.0, 1.0)
                        if (buf.remaining() < 2) {
                            raf.write(buf.array(), 0, buf.position()); written += buf.position(); buf.clear()
                        }
                        buf.putShort((v * 32767).roundToInt().toShort())
                    }
                }
                raf.write(buf.array(), 0, buf.position()); written += buf.position()
                onProgress((rel / p.length).toFloat().coerceIn(0f, 1f))
            }
            val f = fmt ?: throw IllegalStateException("소리를 풀지 못했어요.")
            writeHeader(raf, f.rate, f.channels, written)
        } catch (e: Exception) {
            raf.close(); dst.delete(); throw e
        }
        raf.close()
        if (written == 0L) {
            dst.delete(); throw IllegalStateException("고른 구간에 소리가 없어요.")
        }
    }

    /** 고른 구간 [start, end) 의 소리만 차례로 넘겨준다. rel = 구간 시작부터의 시각 */
    private suspend fun forRange(src: File, p: EditParams, onPart: (Double, FloatArray, Pcm) -> Unit) {
        decode(src, p.start) { at, s, ch, rate ->
            val frames = s.size / ch
            val chunkEnd = at + frames.toDouble() / rate
            if (chunkEnd <= p.start) return@decode true
            if (at >= p.end) return@decode false
            val from = max(0, ((p.start - at) * rate).roundToInt())
            val to = min(frames, ((p.end - at) * rate).roundToInt())
            if (to > from) {
                val part = if (from == 0 && to == frames) s else s.copyOfRange(from * ch, to * ch)
                onPart(max(0.0, at + from.toDouble() / rate - p.start), part, Pcm(rate, ch))
            }
            chunkEnd < p.end
        }
    }

    private fun writeHeader(raf: RandomAccessFile, rate: Int, ch: Int, dataLen: Long) {
        val h = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        h.put("RIFF".toByteArray()); h.putInt((36 + dataLen).toInt())
        h.put("WAVE".toByteArray()); h.put("fmt ".toByteArray())
        h.putInt(16); h.putShort(1); h.putShort(ch.toShort()); h.putInt(rate)
        h.putInt(rate * ch * 2); h.putShort((ch * 2).toShort()); h.putShort(16)
        h.put("data".toByteArray()); h.putInt(dataLen.toInt())
        raf.seek(0)
        raf.write(h.array())
    }

    // ---------------- 원본 보관 (덮어쓰기 뒤 되돌리기) ----------------
    fun originalsDir(ctx: android.content.Context) = File(ctx.filesDir, "originals").apply { mkdirs() }

    fun originalOf(ctx: android.content.Context, soundId: Long): File? =
        originalsDir(ctx).listFiles()?.firstOrNull { it.nameWithoutExtension == soundId.toString() }

    fun backupOriginal(ctx: android.content.Context, soundId: Long, current: File) {
        if (originalOf(ctx, soundId) != null || !current.exists()) return
        current.copyTo(File(originalsDir(ctx), "$soundId.${current.extension.ifEmpty { "bin" }}"))
    }
}
