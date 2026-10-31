package com.milky.mataf.core

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.audiofx.LoudnessEnhancer
import android.net.Uri
import android.os.PowerManager
import android.provider.OpenableColumns
import com.milky.mataf.data.Repo
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.io.File
import kotlin.math.log10
import kotlin.math.roundToInt

/** 화면들이 다시 그려야 할 때 알리는 신호 */
object AppEvents {
    private val _version = MutableStateFlow(0L)
    val version: StateFlow<Long> = _version
    fun changed() {
        _version.value = _version.value + 1
    }
}

/** 종소리 파일 관리 */
object Sounds {
    val SUPPORTED = setOf("wav", "mp3", "ogg", "m4a", "aac", "flac", "opus", "webm", "3gp", "mp4")

    fun dir(ctx: Context): File = File(ctx.filesDir, "sounds").apply { mkdirs() }

    fun file(ctx: Context, fileName: String): File = File(dir(ctx), File(fileName).name)

    /** 처음 실행할 때 기본 종소리(bell1~8)를 넣는다 */
    fun seed(ctx: Context) {
        val repo = Repo(ctx)
        if (repo.sounds().isNotEmpty()) return
        val names = ctx.assets.list("sounds")?.filter { it.endsWith(".wav") || it.endsWith(".mp3") }?.sorted() ?: return
        for (n in names) {
            val dst = file(ctx, n)
            if (!dst.exists()) ctx.assets.open("sounds/$n").use { input -> dst.outputStream().use { input.copyTo(it) } }
            repo.insertSound(n.substringBeforeLast('.'), n, 1.0)
        }
    }

    fun safeStem(name: String): String =
        name.replace(Regex("[\\\\/:*?\"<>|\\x00-\\x1f]+"), "_").trim(' ', '.').take(60).ifEmpty { "sound" }

    fun uniqueFile(ctx: Context, stem: String, ext: String): File {
        val e = ext.trimStart('.').lowercase()
        var f = File(dir(ctx), "${safeStem(stem)}.$e")
        var n = 2
        while (f.exists()) {
            f = File(dir(ctx), "${safeStem(stem)}_$n.$e"); n++
        }
        return f
    }

    fun displayName(ctx: Context, uri: Uri): String {
        ctx.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0)?.let { return it }
        }
        return uri.lastPathSegment?.substringAfterLast('/') ?: "sound"
    }

    /** 파일 앱에서 고른 소리를 복사해 등록한다 */
    fun importUri(ctx: Context, uri: Uri, name: String?, volume: Double): Long {
        val display = displayName(ctx, uri)
        val ext = display.substringAfterLast('.', "mp3").lowercase().let { if (it in SUPPORTED) it else "mp3" }
        val dst = uniqueFile(ctx, display.substringBeforeLast('.'), ext)
        ctx.contentResolver.openInputStream(uri).use { input ->
            requireNotNull(input) { "파일을 열 수 없어요." }
            dst.outputStream().use { input.copyTo(it) }
        }
        return Repo(ctx).insertSound(name?.trim()?.ifEmpty { null } ?: display.substringBeforeLast('.'), dst.name, volume)
    }

    fun importFile(ctx: Context, src: File, name: String, volume: Double = 1.0): Long {
        val dst = uniqueFile(ctx, name, src.extension.ifEmpty { "mp3" })
        src.copyTo(dst, overwrite = false)
        return Repo(ctx).insertSound(name, dst.name, volume)
    }

    fun durationMs(ctx: Context, fileName: String): Int? = try {
        val mp = MediaPlayer()
        mp.setDataSource(file(ctx, fileName).absolutePath)
        mp.prepare()
        val d = mp.duration
        mp.release()
        d
    } catch (e: Exception) {
        null
    }

    fun formatDuration(ms: Int?): String {
        if (ms == null || ms <= 0) return "-"
        val s = ms / 1000.0
        if (s < 60) return "%.1f초".format(s)
        val t = s.roundToInt()
        return "${t / 60}:%02d".format(t % 60)
    }
}

/**
 * 소리 재생 (앱 안 미리 듣기와 종 울리기에 함께 쓴다). 100%보다 크게는 LoudnessEnhancer 로 키운다.
 */
class BellPlayer(private val ctx: Context) {
    private var mp: MediaPlayer? = null
    private var boost: LoudnessEnhancer? = null
    var label: String = ""
        private set

    val isPlaying: Boolean get() = try { mp?.isPlaying == true } catch (e: Exception) { false }

    fun play(path: String, volume: Double, label: String, onDone: (() -> Unit)? = null, onError: ((String) -> Unit)? = null) {
        stop()
        this.label = label
        val p = MediaPlayer()
        try {
            p.setAudioAttributes(
                AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build()
            )
            p.setWakeMode(ctx, PowerManager.PARTIAL_WAKE_LOCK)
            p.setDataSource(path)
            p.prepare()
            val v = volume.coerceIn(0.0, 2.0)
            p.setVolume(v.coerceAtMost(1.0).toFloat(), v.coerceAtMost(1.0).toFloat())
            if (v > 1.0) {
                boost = try {
                    LoudnessEnhancer(p.audioSessionId).apply {
                        setTargetGain((2000 * log10(v)).roundToInt())   // mB: 2배 ≈ +6dB
                        enabled = true
                    }
                } catch (e: Exception) {
                    null
                }
            }
            p.setOnCompletionListener { stop(); onDone?.invoke() }
            p.setOnErrorListener { _, what, _ -> stop(); onError?.invoke("재생 오류 ($what)"); true }
            p.start()
            mp = p
        } catch (e: Exception) {
            try { p.release() } catch (_: Exception) {}
            onError?.invoke(e.message ?: "재생하지 못했어요")
        }
    }

    fun stop() {
        try { boost?.release() } catch (_: Exception) {}
        boost = null
        mp?.let {
            try { if (it.isPlaying) it.stop() } catch (_: Exception) {}
            try { it.release() } catch (_: Exception) {}
        }
        mp = null
    }
}

/** 앱 화면에서 쓰는 미리 듣기 (하나만) */
object Preview {
    private var player: BellPlayer? = null
    private val _playing = MutableStateFlow<String?>(null)
    val playing: StateFlow<String?> = _playing

    fun play(ctx: Context, path: String, volume: Double, label: String, onError: ((String) -> Unit)? = null) {
        val p = player ?: BellPlayer(ctx.applicationContext).also { player = it }
        _playing.value = label
        p.play(path, volume, label, onDone = { _playing.value = null }, onError = { _playing.value = null; onError?.invoke(it) })
    }

    fun stop() {
        player?.stop()
        _playing.value = null
    }
}
