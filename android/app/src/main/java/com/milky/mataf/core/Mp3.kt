package com.milky.mataf.core

import de.sciss.jump3r.mp3.BitStream
import de.sciss.jump3r.mp3.GainAnalysis
import de.sciss.jump3r.mp3.GetAudio
import de.sciss.jump3r.mp3.ID3Tag
import de.sciss.jump3r.mp3.Lame
import de.sciss.jump3r.mp3.LameGlobalFlags
import de.sciss.jump3r.mp3.MPEGMode
import de.sciss.jump3r.mp3.Parse
import de.sciss.jump3r.mp3.Presets
import de.sciss.jump3r.mp3.Quantize
import de.sciss.jump3r.mp3.QuantizePVT
import de.sciss.jump3r.mp3.Reservoir
import de.sciss.jump3r.mp3.Takehiro
import de.sciss.jump3r.mp3.VBRTag
import de.sciss.jump3r.mp3.VbrMode
import de.sciss.jump3r.mp3.Version
import de.sciss.jump3r.mpg.Common
import de.sciss.jump3r.mpg.Interface
import de.sciss.jump3r.mpg.MPGLib
import java.io.OutputStream
import kotlin.math.roundToInt

/**
 * 소리를 MP3 로 바꾼다 (LAME 을 자바로 옮긴 jump3r, LGPL-2.1+). 안드로이드에는 MP3 로 바꾸는 기능이 없다.
 * jump3r 의 LameEncoder 는 안드로이드에 없는 javax.sound 를 써서, 그 안의 부품 연결을 여기서 똑같이 한다.
 */
class Mp3Encoder(sampleRate: Int, channels: Int, kbps: Int = 192) : AutoCloseable {
    /** MP3 는 1~2채널만 된다. 그보다 많으면 앞의 두 채널(왼쪽·오른쪽)을 쓴다 */
    val channels = channels.coerceIn(1, 2)
    private val lame = Lame()
    private val gfp: LameGlobalFlags
    private var buf = ByteArray(16 * 1024)

    init {
        val ga = GainAnalysis(); val bs = BitStream(); val presets = Presets(); val qupvt = QuantizePVT()
        val qu = Quantize(); val vbr = VBRTag(); val ver = Version(); val id3 = ID3Tag(); val rv = Reservoir()
        val tak = Takehiro(); val parse = Parse(); val mpg = MPGLib(); val intf = Interface(); val common = Common()
        lame.setModules(ga, bs, presets, qupvt, qu, vbr, ver, id3, mpg)
        bs.setModules(ga, mpg, ver, vbr)
        id3.setModules(bs, ver)
        presets.setModules(lame)
        qu.setModules(bs, rv, qupvt, tak)
        qupvt.setModules(tak, rv, lame.enc.psy)
        rv.setModules(bs)
        tak.setModules(qupvt)
        vbr.setModules(lame, bs, ver)
        GetAudio().setModules(parse, mpg)
        parse.setModules(ver, id3, presets)
        mpg.setModules(intf, common)
        intf.setModules(vbr, common)

        gfp = lame.lame_init()
        gfp.num_channels = this.channels
        gfp.in_samplerate = sampleRate
        gfp.mode = if (this.channels == 1) MPEGMode.MONO else MPEGMode.JOINT_STEREO
        gfp.VBR = VbrMode.vbr_off
        gfp.brate = kbps
        gfp.quality = 5
        gfp.bWriteVbrTag = false          // 고정 비트레이트라 앞쪽 정보 프레임이 없어도 길이를 안다
        id3.id3tag_init(gfp)
        gfp.write_id3tag_automatic = false
        val r = lame.lame_init_params(gfp)
        if (r < 0) throw IllegalArgumentException("MP3로 바꿀 수 없는 소리예요. (${sampleRate}Hz, ${channels}채널)")
    }

    /** 인터리브된 소리[-1..1](srcChannels 채널)를 넣고, 나온 MP3 조각을 out 에 쓴다 */
    fun encode(samples: FloatArray, srcChannels: Int, out: OutputStream) {
        val frames = samples.size / srcChannels
        if (frames == 0) return
        val left = IntArray(frames)
        val right = IntArray(frames)
        for (f in 0 until frames) {
            left[f] = pcm(samples[f * srcChannels])
            right[f] = if (srcChannels > 1) pcm(samples[f * srcChannels + 1]) else left[f]
        }
        val need = frames + frames / 4 + 7200      // LAME 이 말하는 최대 크기
        if (buf.size < need) buf = ByteArray(need)
        val n = lame.lame_encode_buffer_int(gfp, left, right, frames, buf, 0, buf.size)
        if (n < 0) throw IllegalStateException("MP3로 바꾸지 못했어요. ($n)")
        out.write(buf, 0, n)
    }

    /** 남은 소리를 마저 쓴다 */
    fun finish(out: OutputStream) {
        if (buf.size < 7200) buf = ByteArray(7200)
        val n = lame.lame_encode_flush(gfp, buf, 0, buf.size)
        if (n < 0) throw IllegalStateException("MP3로 바꾸지 못했어요. ($n)")
        out.write(buf, 0, n)
    }

    override fun close() {
        lame.lame_close(gfp)
    }

    /** 16비트로 맞춘 뒤 LAME 이 받는 32비트 범위로 */
    private fun pcm(v: Float): Int = (v.coerceIn(-1f, 1f) * 32767f).roundToInt() shl 16
}
