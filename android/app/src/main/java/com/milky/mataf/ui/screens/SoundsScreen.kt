package com.milky.mataf.ui.screens

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.milky.mataf.core.Alarms
import com.milky.mataf.core.AppEvents
import com.milky.mataf.core.Preview
import com.milky.mataf.core.Sounds
import com.milky.mataf.data.Repo
import com.milky.mataf.data.Sound
import com.milky.mataf.ui.components.AppMenu
import com.milky.mataf.ui.components.AppSheet
import com.milky.mataf.ui.components.Btn
import com.milky.mataf.ui.components.BtnStyle
import com.milky.mataf.ui.components.Card
import com.milky.mataf.ui.components.ConfirmDialog
import com.milky.mataf.ui.components.Empty
import com.milky.mataf.ui.components.Field
import com.milky.mataf.ui.components.Label
import com.milky.mataf.ui.components.MenuItem
import com.milky.mataf.ui.components.Page
import com.milky.mataf.ui.components.PageHeader
import com.milky.mataf.ui.components.Pill
import com.milky.mataf.ui.components.SheetButtons
import com.milky.mataf.ui.components.Toasts
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun SoundsScreen(onSearch: () -> Unit, onEdit: (Sound) -> Unit) {
    val ctx = LocalContext.current
    val repo = remember { Repo(ctx) }
    val version by AppEvents.version.collectAsState()
    val sounds = remember(version) { repo.sounds() }
    val usage = remember(version) { repo.soundUsage() }
    val playing by Preview.playing.collectAsState()
    val scope = rememberCoroutineScope()
    var durations by remember { mutableStateOf<Map<Long, Int?>>(emptyMap()) }
    var info by remember { mutableStateOf<Sound?>(null) }
    var pendingUri by remember { mutableStateOf<Uri?>(null) }
    var confirm by remember { mutableStateOf<Sound?>(null) }

    // 길이는 파일을 열어 봐야 알 수 있어 뒤에서 계산한다
    androidx.compose.runtime.LaunchedEffect(version) {
        durations = withContext(Dispatchers.IO) { sounds.associate { it.id to Sounds.durationMs(ctx, it.fileName) } }
    }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> if (uri != null) pendingUri = uri }

    Page(14.dp) {
        PageHeader("종소리", "파일을 넣거나 YouTube·SoundCloud에서 찾아 받고, 필요한 부분만 잘라 쓸 수 있어요.")
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Btn("찾아서 받기", onSearch, style = BtnStyle.Primary, icon = Icons.Rounded.Search)
            Btn("파일 추가", { picker.launch(arrayOf("audio/*")) }, style = BtnStyle.White, icon = Icons.Rounded.Add)
        }
        Card(padding = 8.dp) {
            if (sounds.isEmpty()) Empty("종소리가 없어요")
            sounds.forEachIndexed { i, s ->
                if (i > 0) Box(Modifier.fillMaxWidth().padding(horizontal = 12.dp).height(1.dp).background(C.grey100))
                SoundRow(s, usage[s.id] ?: 0, Sounds.formatDuration(durations[s.id]), playing == s.name,
                    onPlay = {
                        if (playing == s.name) Preview.stop()
                        else Preview.play(ctx, Sounds.file(ctx, s.fileName).absolutePath, s.volume, s.name) { Toasts.show(it, "error") }
                    },
                    onEdit = { onEdit(s) }, onInfo = { info = s },
                    onDelete = {
                        val n = usage[s.id] ?: 0
                        if (n > 0) Toasts.show("일정 ${n}개에서 쓰고 있어요. 시간표에서 다른 종소리로 바꾼 뒤 지워 주세요.", "warning")
                        else confirm = s
                    })
            }
        }
        Text("${sounds.size}개 · 눌러서 들어볼 수 있어요", style = text(13, color = C.grey500), modifier = Modifier.padding(start = 4.dp))
    }

    pendingUri?.let { uri ->
        SoundInfoSheet("파일 추가", Sounds.displayName(ctx, uri).substringBeforeLast('.'), 100, onDismiss = { pendingUri = null }) { name, vol ->
            pendingUri = null
            scope.launch {
                try {
                    withContext(Dispatchers.IO) { Sounds.importUri(ctx, uri, name, vol / 100.0) }
                    AppEvents.changed()
                    Toasts.show("$name 종소리를 추가했어요", "success")
                } catch (e: Exception) {
                    Toasts.show("추가하지 못했어요: ${e.message}", "error")
                }
            }
        }
    }
    info?.let { s ->
        SoundInfoSheet("이름·음량", s.name, (s.volume * 100).toInt(), onDismiss = { info = null }) { name, vol ->
            repo.updateSound(s.id, name, vol / 100.0); info = null; Alarms.reschedule(ctx); Toasts.show("저장했어요", "success")
        }
    }
    confirm?.let { s ->
        ConfirmDialog("${s.name}을(를) 지울까요?", "종소리 파일도 함께 지워져요.", "삭제", {
            Preview.stop()
            repo.deleteSound(s.id)
            Sounds.file(ctx, s.fileName).delete()
            AppEvents.changed()
            Toasts.show("지웠어요")
        }, { confirm = null })
    }
}

@Composable
private fun SoundRow(s: Sound, used: Int, duration: String, playing: Boolean, onPlay: () -> Unit, onEdit: () -> Unit,
                     onInfo: () -> Unit, onDelete: () -> Unit) {
    var menu by remember { mutableStateOf(false) }
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(onClick = onPlay).padding(horizontal = 10.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(40.dp).clip(CircleShape).background(if (playing) C.accent else C.accentSofter), contentAlignment = Alignment.Center) {
            Icon(if (playing) Icons.Rounded.Stop else Icons.Rounded.PlayArrow, null, tint = if (playing) Color.White else C.accent)
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(s.name, style = text(15, FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text("$duration · 기본 음량 ${(s.volume * 100).toInt()}%", style = text(13, color = C.grey500))
        }
        if (used > 0) Pill("일정 ${used}개") else Pill("안 씀", C.grey500, C.grey100)
        Box {
            androidx.compose.material3.IconButton({ menu = true }) { Icon(Icons.Rounded.MoreVert, null, tint = C.grey500) }
            AppMenu(menu, { menu = false }, listOf(
                MenuItem("자르기·다듬기", onClick = onEdit),
                MenuItem("이름·음량", onClick = onInfo),
                MenuItem("삭제", danger = true, onClick = onDelete),
            ))
        }
    }
}

@Composable
fun SoundInfoSheet(title: String, name0: String, volume0: Int, onDismiss: () -> Unit, onOk: (String, Int) -> Unit) {
    var name by remember { mutableStateOf(name0) }
    var vol by remember { mutableStateOf(volume0) }
    AppSheet(title, onDismiss, footer = { SheetButtons("저장", { onOk(name.trim(), vol) }, onDismiss, okEnabled = name.isNotBlank()) }) {
        Column { Label("이름"); Field(name, { name = it }, Modifier.fillMaxWidth()) }
        Column { Label("기본 음량"); VolumeSlider(vol) { vol = it } }
    }
}
