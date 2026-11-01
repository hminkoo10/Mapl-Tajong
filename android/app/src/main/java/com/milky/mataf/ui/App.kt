package com.milky.mataf.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.History
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.MusicNote
import androidx.compose.material.icons.rounded.Schedule
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.milky.mataf.R
import com.milky.mataf.core.Cloud
import com.milky.mataf.core.Sounds
import com.milky.mataf.core.Updater
import com.milky.mataf.core.Updates
import com.milky.mataf.data.Repo
import com.milky.mataf.data.Sound
import com.milky.mataf.ui.screens.SearchScreen
import com.milky.mataf.ui.screens.SoundEditorScreen
import java.io.File
import com.milky.mataf.ui.components.ConfirmDialog
import com.milky.mataf.ui.components.ToastHost
import com.milky.mataf.ui.components.isWide
import com.milky.mataf.ui.screens.Changelog
import com.milky.mataf.ui.screens.ChangelogSheet
import com.milky.mataf.ui.screens.CloudChoiceDialog
import com.milky.mataf.ui.screens.CloudGate
import com.milky.mataf.ui.screens.HomeScreen
import com.milky.mataf.ui.screens.LogsScreen
import com.milky.mataf.ui.screens.SchedulesScreen
import com.milky.mataf.ui.screens.SettingsScreen
import com.milky.mataf.ui.screens.SoundsScreen
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text

enum class Tab(val label: String, val icon: ImageVector) {
    Home("홈", Icons.Rounded.Home),
    Schedules("시간표", Icons.Rounded.Schedule),
    Sounds("종소리", Icons.Rounded.MusicNote),
    Logs("기록", Icons.Rounded.History),
    Settings("설정", Icons.Rounded.Settings),
}

/** 다듬을 소리: 새로 받은 임시 파일(soundId=null) 또는 이미 있는 종소리 */
data class EditTarget(val file: File, val name: String, val soundId: Long?, val volume: Double = 1.0, val temp: Boolean = false)

/** 종소리 화면 위에 덮어 여는 화면 (찾아서 받기 / 자르기·다듬기) */
sealed interface Sub {
    data object Search : Sub
    data class Edit(val target: EditTarget) : Sub
}

@Composable
fun App() {
    // 방금 업데이트됐다면 새로워진 점을 한 번 보여 준다 (로그인 화면 위에도)
    val ctx = androidx.compose.ui.platform.LocalContext.current
    var whatsNew by remember { mutableStateOf(Updates.takeWhatsNew(Repo(ctx))) }
    whatsNew?.let { (v, notes) ->
        if (Changelog.notesFor(ctx, v).isNotEmpty()) {
            ChangelogSheet(onDismiss = { whatsNew = null }, onlyVersion = v, title = "$v 버전으로 업데이트했어요")
        } else {
            ConfirmDialog("$v 버전으로 업데이트했어요", Updater.notesToText(notes).ifEmpty { "더 안정적으로 다듬었어요." }, "확인", {},
                { whatsNew = null }, danger = false, cancelLabel = null)
        }
    }

    // 마고에듀 통합 클라우드에 로그인해야 쓸 수 있다 (로그인한 뒤에는 인터넷이 없어도 그대로)
    val cloud by Cloud.status.collectAsState()
    if (cloud.loggedIn) Main() else CloudGate()
}

@Composable
private fun Main() {
    var tab by rememberSaveable { mutableStateOf(Tab.Home) }
    var sub by remember { mutableStateOf<Sub?>(null) }
    val wide = isWide()
    val holder = rememberSaveableStateHolder()

    BackHandler(enabled = sub != null || tab != Tab.Home) {
        if (sub != null) sub = null else tab = Tab.Home
    }
    val select: (Tab) -> Unit = { sub = null; tab = it }

    // 처음 클라우드에 연결할 때 어느 시간표로 맞출지
    CloudChoiceDialog()

    Box(Modifier.fillMaxSize().background(C.bg).statusBarsPadding()
        .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Horizontal))) {
        val content: @Composable (Modifier) -> Unit = { m ->
            Box(m) {
                AnimatedContent(sub ?: tab, transitionSpec = { fadeIn(tween(160)) togetherWith fadeOut(tween(120)) },
                    label = "page") { page ->
                    when (page) {
                        is Tab -> holder.SaveableStateProvider(page.name) { TabPage(page) { sub = it } }
                        is Sub.Search -> SearchScreen(onClose = { sub = null }, onEdit = { sub = Sub.Edit(it) })
                        is Sub.Edit -> SoundEditorScreen(page.target) { sub = null }
                        else -> {}
                    }
                }
            }
        }
        if (wide) {
            Row(Modifier.fillMaxSize()) {
                Sidebar(tab, select)
                content(Modifier.weight(1f).fillMaxHeight().navigationBarsPadding())
            }
        } else {
            Column(Modifier.fillMaxSize()) {
                content(Modifier.weight(1f).fillMaxWidth())
                BottomBar(tab, select)
            }
        }
        ToastHost(Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(bottom = if (wide) 8.dp else 68.dp))
    }
}

@Composable
private fun TabPage(tab: Tab, open: (Sub) -> Unit) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    when (tab) {
        Tab.Home -> HomeScreen()
        Tab.Schedules -> SchedulesScreen()
        Tab.Sounds -> SoundsScreen(onSearch = { open(Sub.Search) }, onEdit = { open(Sub.Edit(it.toTarget(ctx))) })
        Tab.Logs -> LogsScreen()
        Tab.Settings -> SettingsScreen()
    }
}

@Composable
private fun BottomBar(tab: Tab, onSelect: (Tab) -> Unit) {
    Column(Modifier.fillMaxWidth().background(Color.White).navigationBarsPadding()) {
        Box(Modifier.fillMaxWidth().height(1.dp).background(C.grey100))
        Row(Modifier.fillMaxWidth().height(60.dp), verticalAlignment = Alignment.CenterVertically) {
            Tab.entries.forEach { t ->
                val on = t == tab
                Column(
                    Modifier.weight(1f).fillMaxHeight().clickable(remember { MutableInteractionSource() }, null) { onSelect(t) },
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
                ) {
                    Icon(t.icon, null, tint = if (on) C.accent else C.grey400, modifier = Modifier.size(24.dp))
                    Text(t.label, style = text(11, if (on) FontWeight.Bold else FontWeight.Medium, if (on) C.grey900 else C.grey500))
                }
            }
        }
    }
}

@Composable
private fun Sidebar(tab: Tab, onSelect: (Tab) -> Unit) {
    Column(Modifier.width(232.dp).fillMaxHeight().background(Color.White).navigationBarsPadding().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(Modifier.padding(start = 8.dp, top = 8.dp, bottom = 20.dp), verticalAlignment = Alignment.CenterVertically) {
            androidx.compose.foundation.Image(androidx.compose.ui.res.painterResource(R.drawable.app_icon), null,
                modifier = Modifier.size(32.dp).clip(RoundedCornerShape(8.dp)))
            Spacer(Modifier.width(10.dp))
            Text("마고 타종", style = text(19, FontWeight.ExtraBold))
        }
        Tab.entries.forEach { t ->
            val on = t == tab
            Row(
                Modifier.fillMaxWidth().height(48.dp).clip(RoundedCornerShape(12.dp))
                    .background(if (on) C.accentSofter else Color.Transparent).clickable { onSelect(t) }.padding(horizontal = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(t.icon, null, tint = if (on) C.accent else C.grey500, modifier = Modifier.size(22.dp))
                Spacer(Modifier.width(12.dp))
                Text(t.label, style = text(15, if (on) FontWeight.Bold else FontWeight.Medium, if (on) C.accentText else C.grey700))
            }
        }
    }
}

private fun Sound.toTarget(ctx: android.content.Context) = EditTarget(Sounds.file(ctx, fileName), name, id, volume)
