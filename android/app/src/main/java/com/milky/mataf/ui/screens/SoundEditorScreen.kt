package com.milky.mataf.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Remove
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.milky.mataf.core.Alarms
import com.milky.mataf.core.AppEvents
import com.milky.mataf.core.AudioEdit
import com.milky.mataf.core.EditParams
import com.milky.mataf.core.Preview
import com.milky.mataf.core.Sounds
import com.milky.mataf.core.Waveform
import com.milky.mataf.data.Repo
import com.milky.mataf.ui.EditTarget
import com.milky.mataf.ui.components.Btn
import com.milky.mataf.ui.components.BtnStyle
import com.milky.mataf.ui.components.Card
import com.milky.mataf.ui.components.ConfirmDialog
import com.milky.mataf.ui.components.Field
import com.milky.mataf.ui.components.IconBtn
import com.milky.mataf.ui.components.Label
import com.milky.mataf.ui.components.Segmented
import com.milky.mataf.ui.components.Toasts
import com.milky.mataf.ui.components.ToggleRow
import com.milky.mataf.ui.components.isWide
import com.milky.mataf.ui.components.maxContentWidth
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

private fun fmt(t: Double): String {
    val m = (t / 60).toInt()
    val s = t - m * 60
    return if (m > 0) "%d:%05.2f".format(m, s) else "%.2f초".format(s)
}

/** 종소리 다듬기: 필요한 부분만 남기고 시작과 끝을 부드럽게 (데스크톱 '종소리 다듬기'와 같은 기능) */
@Composable
fun SoundEditorScreen(target: EditTarget, onClose: () -> Unit) {
    val ctx = LocalContext.current
    val repo = remember { Repo(ctx) }
    val scope = rememberCoroutineScope()
    val wide = isWide()
    var name by remember { mutableStateOf(target.name) }
    var saveMode by remember { mutableStateOf(0) }
    var wave by remember { mutableStateOf<Waveform?>(null) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var a by remember { mutableStateOf(0.0) }
    var b by remember { mutableStateOf(0.0) }
    var v0 by remember { mutableStateOf(0.0) }
    var v1 by remember { mutableStateOf(1.0) }
    var fadeIn by remember { mutableStateOf(0.0) }
    var fadeOut by remember { mutableStateOf(0.0) }
    var gainDb by remember { mutableStateOf(0.0) }
    var normalize by remember { mutableStateOf(false) }
    var notice by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf<String?>(null) }
    var playhead by remember { mutableStateOf<Double?>(null) }
    var playOffset by remember { mutableStateOf(0.0) }
    var saved by remember { mutableStateOf(false) }
    var askOverwrite by remember { mutableStateOf(false) }
    var askRestore by remember { mutableStateOf(false) }
    val playing by Preview.playing.collectAsState()
    val hasOriginal = remember { target.soundId?.let { AudioEdit.originalOf(ctx, it) } != null }
    val dur = wave?.duration ?: 0.0

    DisposableEffect(Unit) {
        onDispose {
            Preview.stop()
            if (target.temp && !saved) target.file.delete()
        }
    }

    LaunchedEffect(target.file) {
        try {
            val w = withContext(Dispatchers.IO) { AudioEdit.waveform(target.file) }
            wave = w
            a = 0.0; b = w.duration; v0 = 0.0; v1 = max(0.1, w.duration)
            if (w.duration > 30 && target.soundId == null) {
                // 긴 음원(YouTube 등)은 소리가 시작되는 앞부분 10초를 먼저 골라 둔다
                val (s, _) = AudioEdit.suggestTrim(w, 0.0, min(w.duration, 120.0))
                a = s; b = min(w.duration, s + 10.0); fadeOut = 1.0
                v0 = max(0.0, s - 5.0); v1 = min(w.duration, b + 20.0)
                notice = "긴 음원이라 소리가 시작되는 앞부분 10초를 먼저 골라 두었어요. 양 끝을 끌어 바꿀 수 있어요."
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            loadError = e.message ?: "음원을 불러오지 못했어요."
        }
    }

    // 재생 위치 표시
    LaunchedEffect(playing) {
        if (playing != "edit") {
            playhead = null; return@LaunchedEffect
        }
        while (Preview.playing.value == "edit") {
            withFrameNanos { }
            playhead = playOffset + Preview.positionMs() / 1000.0
        }
        playhead = null
    }

    fun params() = EditParams(a, b, fadeIn, fadeOut, gainDb, normalize)

    fun play(from: Double? = null) {
        if (wave == null || busy != null) return
        Preview.stop()
        val p = if (from == null) params() else params().copy(start = from, end = if (b > from) b else dur, fadeIn = 0.0)
        busy = "들어볼 소리를 만드는 중"
        scope.launch {
            try {
                val out = File(ctx.cacheDir, "edit_preview.wav")
                withContext(Dispatchers.IO) { AudioEdit.render(target.file, out, p) }
                playOffset = p.start
                Preview.play(ctx, out.absolutePath, 1.0, "edit") { Toasts.show("들어보지 못했어요: $it", "error") }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Toasts.show("들어볼 소리를 만들지 못했어요: ${e.message}", "error")
            } finally {
                busy = null
            }
        }
    }

    fun zoom(f: Double) {
        if (dur <= 0) return
        val center = if (b > v0 && a < v1) (max(a, v0) + min(b, v1)) / 2 else (v0 + v1) / 2
        val span = ((v1 - v0) * f).coerceIn(min(0.2, dur), dur)
        v0 = (center - span / 2).coerceIn(0.0, dur - span); v1 = v0 + span
    }

    fun save() {
        val n = name.trim()
        when {
            wave == null -> return
            n.isEmpty() -> { Toasts.show("이름을 입력해 주세요", "warning"); return }
            b - a < 0.1 -> { Toasts.show("구간이 너무 짧아요", "warning"); return }
        }
        Preview.stop()
        busy = "저장하는 중"
        val p = params()
        scope.launch {
            try {
                withContext(Dispatchers.IO) {
                    val id = target.soundId
                    if (id == null || saveMode == 0) {
                        val dst = Sounds.uniqueFile(ctx, n, "wav")
                        AudioEdit.render(target.file, dst, p)
                        repo.insertSound(n, dst.name, if (id == null) 1.0 else target.volume)
                    } else {
                        AudioEdit.backupOriginal(ctx, id, target.file)
                        val tmp = File(ctx.cacheDir, "edit_render.wav")
                        AudioEdit.render(target.file, tmp, p)
                        val dst = Sounds.uniqueFile(ctx, n, "wav")
                        tmp.copyTo(dst); tmp.delete()
                        repo.updateSoundFile(id, dst.name)
                        repo.updateSound(id, n, target.volume)
                        if (target.file.absolutePath != dst.absolutePath) target.file.delete()
                    }
                }
                saved = true
                if (target.temp) target.file.delete()
                AppEvents.changed()
                Alarms.reschedule(ctx)
                Toasts.show(if (target.soundId != null && saveMode == 1) "덮어썼어요. 원본은 따로 보관해 두었어요" else "$n 종소리를 저장했어요", "success")
                onClose()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Toasts.show("저장하지 못했어요: ${e.message}", "error")
            } finally {
                busy = null
            }
        }
    }

    fun restore() {
        val id = target.soundId ?: return
        val orig = AudioEdit.originalOf(ctx, id) ?: return
        Preview.stop()
        val dst = Sounds.uniqueFile(ctx, name.trim().ifEmpty { target.name }, orig.extension)
        orig.copyTo(dst)
        repo.updateSoundFile(id, dst.name)
        if (target.file.absolutePath != dst.absolutePath) target.file.delete()
        orig.delete()
        saved = true
        AppEvents.changed()
        Toasts.show("원본으로 되돌렸어요", "success")
        onClose()
    }

    Column(Modifier.fillMaxSize().imePadding()) {
        Box(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()), contentAlignment = Alignment.TopCenter) {
            Column(Modifier.maxContentWidth().fillMaxWidth().padding(horizontal = if (wide) 32.dp else 16.dp, vertical = 16.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconBtn(Icons.AutoMirrored.Rounded.ArrowBack, onClose, bg = Color.White)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text("종소리 다듬기", style = text(24, FontWeight.Bold))
                        Text("필요한 부분만 남기고, 시작과 끝을 부드럽게 만들어요.", style = text(13, color = C.grey600))
                    }
                }
                Card(padding = 16.dp) {
                    Label("이름")
                    Field(name, { name = it }, Modifier.fillMaxWidth(), placeholder = "종소리 이름")
                    if (target.soundId != null) {
                        Spacer(Modifier.height(12.dp))
                        Label("저장")
                        Segmented(listOf("새로 저장", "원래 파일에 덮어쓰기"), saveMode, { saveMode = it }, Modifier.fillMaxWidth())
                    }
                }
                Card(padding = 12.dp) {
                    val w = wave
                    Box(Modifier.fillMaxWidth().height(200.dp), contentAlignment = Alignment.Center) {
                        when {
                            loadError != null -> Text("음원을 불러오지 못했어요.\n$loadError", style = text(14, color = C.danger))
                            w == null -> Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                CircularProgressIndicator(color = C.accent, strokeWidth = 3.dp, modifier = Modifier.size(30.dp))
                                Spacer(Modifier.height(10.dp))
                                Text("파형을 불러오는 중…", style = text(14, color = C.grey500))
                            }
                            else -> WaveView(w, a, b, v0, v1, fadeIn, fadeOut, 10.0.pow(gainDb / 20).toFloat(), playhead,
                                onSel = { x, y -> a = x; b = y }, onPlayFrom = { play(it) }, modifier = Modifier.fillMaxSize())
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                    Text("끌어서 구간을 고르고, 양 끝을 잡아 조절해요. 길게 누르면 그 자리부터 들려줘요.", style = text(12, color = C.grey400))
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Btn("확대", { zoom(0.6) }, small = true, style = BtnStyle.Subtle)
                        Btn("축소", { zoom(1.6) }, small = true, style = BtnStyle.Subtle)
                        Btn("고른 부분만", {
                            val pad = max(0.05, (b - a) * 0.05)
                            v0 = max(0.0, a - pad); v1 = min(dur, b + pad)
                        }, small = true, style = BtnStyle.Subtle)
                        Btn("전체", { v0 = 0.0; v1 = max(0.1, dur) }, small = true, style = BtnStyle.Subtle)
                    }
                }
                if (notice.isNotEmpty()) {
                    Text(notice, style = text(13, FontWeight.SemiBold, C.grey700),
                        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(C.grey50).padding(12.dp))
                }
                Card(padding = 16.dp) {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Stepper("시작", fmt(a), Modifier.weight(1f),
                            { a = max(0.0, a - 0.05) }, { a = min(b - 0.05, a + 0.05) })
                        Stepper("끝", fmt(b), Modifier.weight(1f),
                            { b = max(a + 0.05, b - 0.05) }, { b = min(dur, b + 0.05) })
                    }
                    Spacer(Modifier.height(10.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("남길 길이", style = text(13, FontWeight.SemiBold, C.grey600), modifier = Modifier.weight(1f))
                        Text(fmt(b - a), style = text(17, FontWeight.Bold))
                    }
                    Spacer(Modifier.height(10.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Stepper("페이드 인", "%.1f초".format(fadeIn), Modifier.weight(1f),
                            { fadeIn = max(0.0, fadeIn - 0.1) }, { fadeIn = min(30.0, fadeIn + 0.1) })
                        Stepper("페이드 아웃", "%.1f초".format(fadeOut), Modifier.weight(1f),
                            { fadeOut = max(0.0, fadeOut - 0.1) }, { fadeOut = min(30.0, fadeOut + 0.1) })
                    }
                    Spacer(Modifier.height(12.dp))
                    Label("음량 조절")
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Slider(gainDb.toFloat(), { gainDb = (it * 2).toInt() / 2.0 }, Modifier.weight(1f), valueRange = -12f..12f,
                            colors = SliderDefaults.colors(thumbColor = C.accent, activeTrackColor = C.accent, inactiveTrackColor = C.grey200))
                        Text("%+.1f dB".format(gainDb), style = text(14, FontWeight.SemiBold, C.grey800),
                            modifier = Modifier.widthIn(min = 64.dp).padding(start = 8.dp))
                    }
                    ToggleRow("크기 자동 맞춤", "다른 종소리와 비슷한 크기가 되도록 음량을 맞춰요", normalize, { normalize = it })
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Btn("앞뒤 조용한 부분 자르기", {
                            wave?.let { w ->
                                val (s, e) = AudioEdit.suggestTrim(w)
                                a = s; b = e
                                notice = "앞뒤 조용한 부분을 잘라 ${fmt(e - s)}만 남겼어요."
                            }
                        }, small = true, enabled = wave != null)
                        Btn("처음으로", {
                            a = 0.0; b = dur; fadeIn = 0.0; fadeOut = 0.0; gainDb = 0.0; normalize = false
                            v0 = 0.0; v1 = max(0.1, dur); notice = ""
                        }, small = true, style = BtnStyle.Subtle, enabled = wave != null)
                    }
                }
            }
        }
        Column(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = if (wide) 32.dp else 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            busy?.let {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(color = C.accent, strokeWidth = 2.dp, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(it, style = text(13, FontWeight.Medium, C.grey700))
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                val on = playing == "edit"
                Btn(if (on) "정지" else "들어보기", { if (on) Preview.stop() else play() }, Modifier.weight(1f),
                    icon = if (on) Icons.Rounded.Stop else Icons.Rounded.PlayArrow, enabled = wave != null && busy == null, large = true)
                if (hasOriginal) Btn("원본으로", { askRestore = true }, Modifier.weight(1f), style = BtnStyle.Subtle, large = true,
                    enabled = busy == null)
                Btn("저장", { if (target.soundId != null && saveMode == 1) askOverwrite = true else save() }, Modifier.weight(1.3f),
                    style = BtnStyle.Primary, enabled = wave != null && busy == null, large = true)
            }
        }
    }

    if (askOverwrite) ConfirmDialog("원래 파일에 덮어쓸까요?", "원본은 따로 보관해 두니까 나중에 되돌릴 수 있어요.", "덮어쓰기",
        { save() }, { askOverwrite = false }, danger = false)
    if (askRestore) ConfirmDialog("원본으로 되돌릴까요?", "다듬기 전의 소리로 돌아가요.", "되돌리기",
        { restore() }, { askRestore = false }, danger = false)
}

@Composable
private fun Stepper(label: String, value: String, modifier: Modifier, onMinus: () -> Unit, onPlus: () -> Unit) {
    Column(modifier) {
        Label(label)
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(C.grey100), verticalAlignment = Alignment.CenterVertically) {
            IconBtn(Icons.Rounded.Remove, onMinus, bg = Color.Transparent, size = 44.dp)
            Text(value, style = text(15, FontWeight.Bold), modifier = Modifier.weight(1f),
                textAlign = androidx.compose.ui.text.style.TextAlign.Center)
            IconBtn(Icons.Rounded.Add, onPlus, bg = Color.Transparent, size = 44.dp)
        }
    }
}

/** 파형 + 고른 구간 + 페이드 모양 + 재생 위치 */
@Composable
private fun WaveView(
    w: Waveform, a: Double, b: Double, v0: Double, v1: Double, fadeIn: Double, fadeOut: Double, gain: Float, playhead: Double?,
    onSel: (Double, Double) -> Unit, onPlayFrom: (Double) -> Unit, modifier: Modifier,
) {
    val cur = rememberUpdatedState(Triple(a, b, v0 to v1))
    val sel = rememberUpdatedState(onSel)
    val playFrom = rememberUpdatedState(onPlayFrom)
    val hitPx = with(LocalDensity.current) { 28.dp.toPx() }
    val minLen = 0.05
    Canvas(
        modifier
            .clip(RoundedCornerShape(12.dp))
            .background(C.grey50)
            .pointerInput(w) {
                var mode = 0
                var anchor = 0.0
                fun tOf(x: Float): Double {
                    val (vs, ve) = cur.value.third
                    return (vs + (x / size.width) * (ve - vs)).coerceIn(0.0, w.duration)
                }
                fun xOf(t: Double): Float {
                    val (vs, ve) = cur.value.third
                    return ((t - vs) / (ve - vs) * size.width).toFloat()
                }
                detectHorizontalDragGestures(
                    onDragStart = { o ->
                        val (sa, sb, _) = cur.value
                        mode = when {
                            abs(xOf(sa) - o.x) < hitPx && abs(xOf(sa) - o.x) <= abs(xOf(sb) - o.x) -> 1
                            abs(xOf(sb) - o.x) < hitPx -> 2
                            else -> { anchor = tOf(o.x); 3 }
                        }
                    },
                    onHorizontalDrag = { ch, _ ->
                        ch.consume()
                        val t = tOf(ch.position.x)
                        val (sa, sb, _) = cur.value
                        when (mode) {
                            1 -> sel.value(min(t, sb - minLen), sb)
                            2 -> sel.value(sa, max(t, sa + minLen))
                            3 -> if (abs(t - anchor) >= minLen) sel.value(min(anchor, t), max(anchor, t))
                        }
                    },
                )
            }
            .pointerInput(w) {
                detectTapGestures(onLongPress = { o ->
                    val (vs, ve) = cur.value.third
                    playFrom.value((vs + (o.x / size.width) * (ve - vs)).coerceIn(0.0, w.duration))
                })
            }
    ) {
        val W = size.width
        val H = size.height
        val mid = H / 2
        val span = max(1e-6, v1 - v0)
        fun x(t: Double) = ((t - v0) / span * W).toFloat()
        val len = max(0.01, b - a)
        val step = 2f
        var px = 0f
        val peaks = w.peaks
        while (px < W) {
            val t0 = v0 + px / W * span
            val t1 = v0 + (px + step) / W * span
            val i0 = (t0 / AudioEdit.PEAK_SEC).toInt().coerceIn(0, max(0, peaks.size - 1))
            val i1 = max(i0 + 1, (t1 / AudioEdit.PEAK_SEC).toInt()).coerceAtMost(peaks.size)
            var m = 0f
            for (i in i0 until i1) if (peaks[i] > m) m = peaks[i]
            val inside = t0 >= a && t0 <= b
            var amp = m
            if (inside) {
                val rel = t0 - a
                var env = gain.toDouble()
                if (fadeIn > 0 && rel < fadeIn) env *= rel / fadeIn
                if (fadeOut > 0 && len - rel < fadeOut) env *= max(0.0, (len - rel) / fadeOut)
                amp = (m * env).toFloat().coerceAtMost(1f)
            }
            val h = max(1f, amp * (H * 0.46f))
            drawRect(if (inside) C.accent else C.grey300, Offset(px, mid - h), Size(step * 0.7f, h * 2))
            px += step
        }
        // 고르지 않은 부분은 흐리게
        val xa = x(a).coerceIn(0f, W)
        val xb = x(b).coerceIn(0f, W)
        if (xa > 0) drawRect(Color.White.copy(alpha = 0.55f), Offset.Zero, Size(xa, H))
        if (xb < W) drawRect(Color.White.copy(alpha = 0.55f), Offset(xb, 0f), Size(W - xb, H))
        // 손잡이
        for (hx in listOf(x(a), x(b))) {
            if (hx < -2 || hx > W + 2) continue
            drawRect(C.accentPressed, Offset(hx - 1.5f, 0f), Size(3f, H))
            drawRoundRect(C.accentPressed, Offset(hx - 8f, H / 2 - 22f), Size(16f, 44f), CornerRadius(8f, 8f))
        }
        playhead?.let { t ->
            val hx = x(t)
            if (hx in 0f..W) drawRect(C.grey900, Offset(hx - 1f, 0f), Size(2f, H))
        }
    }
}
