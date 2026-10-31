package com.milky.mataf.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.milky.mataf.core.AppEvents
import com.milky.mataf.core.AudioSource
import com.milky.mataf.core.Found
import com.milky.mataf.core.Online
import com.milky.mataf.core.Preview
import com.milky.mataf.core.Sounds
import com.milky.mataf.data.Repo
import com.milky.mataf.ui.EditTarget
import com.milky.mataf.ui.components.Btn
import com.milky.mataf.ui.components.BtnStyle
import com.milky.mataf.ui.components.Chip
import com.milky.mataf.ui.components.Empty
import com.milky.mataf.ui.components.Field
import com.milky.mataf.ui.components.IconBtn
import com.milky.mataf.ui.components.NetImage
import com.milky.mataf.ui.components.Segmented
import com.milky.mataf.ui.components.Toasts
import com.milky.mataf.ui.components.isWide
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

private val SUGGESTIONS = mapOf(
    Online.YOUTUBE to listOf("학교 종소리", "수업 시작종", "차임벨 효과음", "띵동댕동", "쉬는 시간 종", "알림음 효과음"),
    Online.SOUNDCLOUD to listOf("school bell", "chime", "bell ring", "doorbell", "notification sound", "학교 종소리"),
)
private val PLACEHOLDER = mapOf(
    Online.YOUTUBE to "검색어나 YouTube 주소",
    Online.SOUNDCLOUD to "검색어나 SoundCloud 주소 (영어로 찾으면 더 많이 나와요)",
)
const val PREVIEW_SEC = 30

private fun dur(sec: Long): String {
    if (sec <= 0) return "-"
    val h = sec / 3600
    val m = sec % 3600 / 60
    val s = sec % 60
    return if (h > 0) "$h:%02d:%02d".format(m, s) else "$m:%02d".format(s)
}

/** YouTube·SoundCloud 에서 찾아 종소리로 받기 (데스크톱 '종소리 찾기'와 같은 흐름) */
@Composable
fun SearchScreen(onClose: () -> Unit, onEdit: (EditTarget) -> Unit) {
    val ctx = LocalContext.current
    val repo = remember { Repo(ctx) }
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    var source by remember { mutableStateOf(repo.setting("search_source", Online.YOUTUBE).let { if (it in Online.SOURCES) it else Online.YOUTUBE }) }
    var query by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<Found>>(emptyList()) }
    var emptyText by remember { mutableStateOf("무엇을 찾을까요?" to "위의 추천 검색어를 눌러도 돼요.") }
    var searching by remember { mutableStateOf(false) }
    var selected by remember { mutableStateOf<Found?>(null) }
    var state by remember { mutableStateOf("") }
    var stateError by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var progress by remember { mutableFloatStateOf(-1f) }
    var pvLoading by remember { mutableStateOf<String?>(null) }
    val playing by Preview.playing.collectAsState()
    val resolved = remember { mutableMapOf<String, AudioSource>() }
    var searchJob by remember { mutableStateOf<Job?>(null) }
    var pvJob by remember { mutableStateOf<Job?>(null) }
    var dlJob by remember { mutableStateOf<Job?>(null) }
    val wide = isWide()

    DisposableEffect(Unit) {
        onDispose { Preview.stop() }
    }

    fun setState(t: String, error: Boolean = false, isBusy: Boolean = false) {
        state = t; stateError = error; busy = isBusy
    }

    suspend fun resolve(f: Found): AudioSource =
        resolved[f.url] ?: withContext(Dispatchers.IO) { Online.resolve(f.url) }.also { resolved[f.url] = it }

    fun search(q0: String = query) {
        val q = q0.trim()
        if (q.isEmpty()) return
        focus.clearFocus()
        searchJob?.cancel()
        Preview.stop(); pvJob?.cancel(); pvLoading = null
        selected = null
        results = emptyList()
        searching = true
        setState("")
        searchJob = scope.launch {
            try {
                val r = withContext(Dispatchers.IO) { Online.search(q, source) }
                results = r
                if (r.isEmpty()) emptyText = "찾는 결과가 없어요" to "다른 검색어로 찾아 보세요."
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                emptyText = "찾지 못했어요" to Online.explain(e)
            } finally {
                searching = false
            }
        }
    }

    fun togglePreview(f: Found) {
        val label = "pv:" + f.url
        if (playing == label || pvLoading == f.url) {
            Preview.stop(); pvJob?.cancel(); pvLoading = null; return
        }
        Preview.stop(); pvJob?.cancel()
        selected = f
        pvLoading = f.url
        pvJob = scope.launch {
            try {
                val src = resolve(f)
                val out = File(ctx.cacheDir, "preview/clip.${src.ext}")
                File(ctx.cacheDir, "preview").listFiles()?.forEach { it.delete() }
                withContext(Dispatchers.IO) { Online.download(src, out, PREVIEW_SEC) }
                if (pvLoading == f.url) Preview.play(ctx, out.absolutePath, 1.0, label) { setState("미리 듣지 못했어요: $it", error = true) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                setState(Online.explain(e), error = true)
            } finally {
                if (pvLoading == f.url) pvLoading = null
            }
        }
    }

    fun download(edit: Boolean) {
        val f = selected ?: return
        if (dlJob?.isActive == true) return
        Preview.stop(); pvJob?.cancel(); pvLoading = null
        progress = 0f
        setState("받을 준비를 하고 있어요", isBusy = true)
        dlJob = scope.launch {
            val dir = File(ctx.cacheDir, "download").apply { mkdirs() }
            var file: File? = null
            try {
                val src = resolve(f)
                val name = f.title.trim().take(40).ifEmpty { if (Online.sourceOf(f.url) == Online.SOUNDCLOUD) "SoundCloud 종소리" else "YouTube 종소리" }
                val out = File(dir, "${Sounds.safeStem(name)}.${src.ext}")
                file = withContext(Dispatchers.IO) {
                    Online.download(src, out) { p -> progress = p; state = "받는 중 ${(p * 100).toInt()}%" }
                }
                progress = -1f
                if (edit) {
                    setState("다 받았어요")
                    onEdit(EditTarget(file, name, null, 1.0, temp = true))
                } else {
                    withContext(Dispatchers.IO) { Sounds.importFile(ctx, file, name) }
                    file.delete()
                    AppEvents.changed()
                    Toasts.show("$name 종소리를 추가했어요", "success")
                    onClose()
                }
            } catch (e: CancellationException) {
                file?.delete()
                progress = -1f
                setState("받기를 취소했어요")
                throw e
            } catch (e: Exception) {
                file?.delete()
                progress = -1f
                setState(Online.explain(e), error = true)
            }
        }
    }

    Column(Modifier.fillMaxSize().imePadding()) {
        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(horizontal = if (wide) 32.dp else 16.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconBtn(Icons.AutoMirrored.Rounded.ArrowBack, onClose, bg = Color.White)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text("종소리 찾기", style = text(24, FontWeight.Bold))
                        Text("YouTube나 SoundCloud에서 소리만 받아 종소리로 만들어요.", style = text(13, color = C.grey600))
                    }
                }
                Spacer(Modifier.height(14.dp))
                Segmented(listOf("YouTube", "SoundCloud"), Online.SOURCES.indexOf(source), { i ->
                    source = Online.SOURCES[i]; repo.setSetting("search_source", source)
                    if (query.isNotBlank()) search()
                }, Modifier.fillMaxWidth(), onPage = true)
                Spacer(Modifier.height(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Field(query, { query = it }, Modifier.weight(1f), placeholder = PLACEHOLDER[source] ?: "",
                        leading = Icons.Rounded.Search, onPage = true, onDone = { search() })
                    Btn("검색", { search() }, style = BtnStyle.Primary, enabled = query.isNotBlank() && !searching)
                }
                Spacer(Modifier.height(10.dp))
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    (SUGGESTIONS[source] ?: emptyList()).forEach { s ->
                        Chip(s, false, { query = s; search(s) })
                    }
                }
                Spacer(Modifier.height(10.dp))
            }
            if (searching) {
                item {
                    Box(Modifier.fillMaxWidth().padding(vertical = 48.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(color = C.accent, strokeWidth = 3.dp, modifier = Modifier.size(32.dp))
                    }
                }
            } else if (results.isEmpty()) {
                item { Empty(emptyText.first, emptyText.second) }
            }
            items(results, key = { it.url }) { f ->
                ResultRow(f, f == selected,
                    previewState = when {
                        pvLoading == f.url -> "loading"
                        playing == "pv:" + f.url -> "playing"
                        else -> "idle"
                    },
                    onClick = { selected = if (selected == f) null else f },
                    onPreview = { togglePreview(f) })
            }
        }

        // 아래: 상태 · 버튼
        Column(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = if (wide) 32.dp else 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (state.isNotEmpty() || progress >= 0f) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    if (busy) CircularProgressIndicator(color = C.accent, strokeWidth = 2.dp, modifier = Modifier.size(18.dp))
                    Text(state, style = text(14, FontWeight.Medium, if (stateError) C.danger else C.grey700), modifier = Modifier.weight(1f),
                        maxLines = 2, overflow = TextOverflow.Ellipsis)
                    if (dlJob?.isActive == true) Btn("취소", { dlJob?.cancel(); setState("취소하고 있어요", isBusy = true) },
                        style = BtnStyle.Subtle, small = true)
                }
                if (progress >= 0f) LinearProgressIndicator({ progress }, Modifier.fillMaxWidth().height(6.dp).clip(CircleShape),
                    color = C.accent, trackColor = C.grey100)
            }
            val canAct = selected != null && dlJob?.isActive != true
            val pvOn = selected?.let { playing == "pv:" + it.url || pvLoading == it.url } == true
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Btn(if (pvOn) "그만 듣기" else "미리 듣기", { selected?.let { togglePreview(it) } }, Modifier.weight(1f),
                    icon = if (pvOn) Icons.Rounded.Stop else Icons.Rounded.PlayArrow, enabled = canAct, large = true)
                Btn("바로 추가", { download(false) }, Modifier.weight(1f), enabled = canAct, large = true)
                Btn("받아서 다듬기", { download(true) }, Modifier.weight(1.3f), style = BtnStyle.Primary, enabled = canAct, large = true)
            }
            Text("저작권이 있는 소리는 허락된 범위에서만 써 주세요. 받은 소리는 이 기기에만 저장돼요.",
                style = text(12, color = C.grey400))
        }
    }
}

@Composable
private fun ResultRow(f: Found, selected: Boolean, previewState: String, onClick: () -> Unit, onPreview: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp))
            .background(if (selected) C.accentSofter else Color.Transparent)
            .clickable(onClick = onClick).padding(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(128.dp, 72.dp).clip(RoundedCornerShape(10.dp)).clickable(onClick = onPreview)) {
            NetImage(f.thumb, Modifier.matchParentSize())
            Box(Modifier.matchParentSize().background(Color.Black.copy(alpha = if (previewState == "idle") 0.12f else 0.35f)))
            Box(Modifier.align(Alignment.Center).size(34.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.95f)),
                contentAlignment = Alignment.Center) {
                when (previewState) {
                    "loading" -> CircularProgressIndicator(color = C.accent, strokeWidth = 2.5.dp, modifier = Modifier.size(18.dp))
                    "playing" -> Icon(Icons.Rounded.Stop, null, tint = C.grey900, modifier = Modifier.size(18.dp))
                    else -> Icon(Icons.Rounded.PlayArrow, null, tint = C.grey900, modifier = Modifier.size(20.dp))
                }
            }
            Text(dur(f.durationSec), style = text(11, FontWeight.Bold, Color.White),
                modifier = Modifier.align(Alignment.BottomEnd).padding(4.dp).clip(RoundedCornerShape(5.dp))
                    .background(Color.Black.copy(alpha = 0.7f)).padding(horizontal = 5.dp, vertical = 1.dp))
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(f.title, style = text(14, FontWeight.Bold), maxLines = 2, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.height(4.dp))
            Text(f.channel + if (f.durationSec > 20 * 60) "  ·  긴 영상" else "", style = text(12, color = C.grey500),
                maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        if (selected) {
            Spacer(Modifier.width(8.dp))
            Box(Modifier.size(22.dp).clip(CircleShape).background(C.accent), contentAlignment = Alignment.Center) {
                Icon(Icons.Rounded.Check, null, tint = Color.White, modifier = Modifier.size(14.dp))
            }
        }
    }
}
