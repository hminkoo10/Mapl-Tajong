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
import com.milky.mataf.core.Sounds
import com.milky.mataf.data.Sound
import com.milky.mataf.ui.screens.SearchScreen
import java.io.File
import com.milky.mataf.ui.components.ToastHost
import com.milky.mataf.ui.components.isWide
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
    var tab by rememberSaveable { mutableStateOf(Tab.Home) }
    var sub by remember { mutableStateOf<Sub?>(null) }
    val wide = isWide()
    val holder = rememberSaveableStateHolder()

    BackHandler(enabled = sub != null || tab != Tab.Home) {
        if (sub != null) sub = null else tab = Tab.Home
    }
    val select: (Tab) -> Unit = { sub = null; tab = it }

    Box(Modifier.fillMaxSize().background(C.bg).statusBarsPadding()
        .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Horizontal))) {
        val content: @Composable (Modifier) -> Unit = { m ->
            Box(m) {
                AnimatedContent(sub ?: tab, transitionSpec = { fadeIn(tween(160)) togetherWith fadeOut(tween(120)) },
                    label = "page") { page ->
                    when (page) {
                        is Tab -> holder.SaveableStateProvider(page.name) { TabPage(page) { sub = it } }
                        is Sub.Search -> SearchScreen(onClose = { sub = null }, onEdit = { sub = Sub.Edit(it) })
                        is Sub.Edit -> Soon { sub = null }
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
private fun Soon(onClose: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally) {
        Text("곧 추가돼요", style = text(18, FontWeight.Bold))
        Spacer(Modifier.height(12.dp))
        Text("돌아가기", style = text(15, FontWeight.SemiBold, C.accentText),
            modifier = Modifier.clip(RoundedCornerShape(10.dp)).clickable(onClick = onClose).padding(12.dp))
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
            Icon(androidx.compose.ui.res.painterResource(R.drawable.ic_bell), null, tint = C.accent, modifier = Modifier.size(26.dp))
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
