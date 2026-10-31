package com.milky.mataf

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.DarkMode
import androidx.compose.material.icons.rounded.LightMode
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.milky.mataf.core.AppEvents
import com.milky.mataf.core.Scheduler
import com.milky.mataf.core.TodayEvent
import com.milky.mataf.data.Repo
import com.milky.mataf.data.TimeUtil
import com.milky.mataf.ui.screens.CountdownRing
import com.milky.mataf.ui.screens.RollingClock
import com.milky.mataf.ui.screens.STATUS
import com.milky.mataf.ui.screens.rememberNow
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.MatafTheme
import com.milky.mataf.ui.theme.text
import kotlinx.coroutines.delay
import java.time.Duration

/** 교실 화면에 크게 띄우는 시계 (데스크톱 전체화면 시계와 같은 구성) */
class FullscreenActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        WindowCompat.getInsetsController(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
        setContent { MatafTheme { FullscreenClock(onClose = { finish() }) } }
    }
}

private class FsTheme(
    val dark: Boolean, val bg: Color, val fg: Color, val sub: Color, val dim: Color,
    val card: Color, val cardNext: Color, val accent: Color,
)

private val DARK = FsTheme(true, Color(0xFF121316), Color.White, Color.White.copy(alpha = 0.6f), Color.White.copy(alpha = 0.42f),
    Color.White.copy(alpha = 0.05f), Color.White.copy(alpha = 0.10f), Color(0xFFFFB27A))
private val LIGHT = FsTheme(false, Color(0xFFF4F5F7), C.grey900, C.grey600, C.grey500, Color.White, Color.White, C.accentText)

@Composable
private fun FullscreenClock(onClose: () -> Unit) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val repo = remember { Repo(ctx) }
    val version by AppEvents.version.collectAsState()
    var light by remember { mutableStateOf(repo.setting("fs_theme", "dark") == "light") }
    val th = if (light) LIGHT else DARK
    val bg by animateColorAsState(th.bg, tween(400), label = "bg")
    val now = rememberNow()
    val minute = now.withSecond(0).withNano(0)
    val next = remember(version, minute) { Scheduler.next(repo, now) }
    val events = remember(version, minute) { Scheduler.today(repo, now) }
    val paused = remember(version) { Scheduler.isPaused(repo) }
    val pauseDay = remember(version, now.toLocalDate()) { repo.isPauseDay(now.toLocalDate()) }

    // 화면을 건드리면 버튼이 3초 동안 보인다
    var touched by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var showControls by remember { mutableStateOf(true) }
    LaunchedEffect(touched) {
        showControls = true
        delay(3000)
        showControls = false
    }

    BoxWithConstraints(
        Modifier.fillMaxSize().background(bg)
            .clickable(remember { MutableInteractionSource() }, null) { touched = System.currentTimeMillis() }
    ) {
        val landscape = maxWidth > maxHeight
        val fontScale = LocalDensity.current.fontScale
        fun sp(d: Dp): Int = (d.value / fontScale).toInt().coerceAtLeast(10)
        val clockDp = if (landscape) minOf(maxWidth * 0.12f, maxHeight * 0.26f) else minOf(maxWidth * 0.19f, maxHeight * 0.12f)
        val ringDp = if (landscape) minOf(maxHeight * 0.44f, maxWidth * 0.27f) else minOf(maxWidth * 0.62f, maxHeight * 0.32f)
        val pad = if (landscape) 48.dp else 24.dp
        val stripH = if (landscape) (maxHeight * 0.16f).coerceIn(84.dp, 140.dp) else 92.dp

        Column(Modifier.fillMaxSize().padding(horizontal = pad, vertical = if (landscape) 28.dp else 36.dp)) {
            // 위: 날짜 · 버튼
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("${now.year}년 ${now.monthValue}월 ${now.dayOfMonth}일 ${TimeUtil.WEEK_KO[now.dayOfWeek.value - 1]}요일",
                    style = text(sp(if (landscape) 26.dp else 20.dp), FontWeight.SemiBold, th.sub), modifier = Modifier.weight(1f))
                AnimatedVisibility(showControls, enter = fadeIn(tween(150)), exit = fadeOut(tween(300))) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FsButton(if (light) Icons.Rounded.DarkMode else Icons.Rounded.LightMode, th) {
                            light = !light
                            repo.setSetting("fs_theme", if (light) "light" else "dark")
                            touched = System.currentTimeMillis()
                        }
                        FsButton(Icons.Rounded.Close, th, onClose)
                    }
                }
            }
            Spacer(Modifier.weight(1f))

            val clock: @Composable () -> Unit = {
                Column(horizontalAlignment = if (landscape) Alignment.Start else Alignment.CenterHorizontally) {
                    RollingClock("%02d:%02d:%02d".format(now.hour, now.minute, now.second), sp(clockDp), th.fg)
                    val state = if (paused) "잠시 멈춤" else if (pauseDay) "오늘은 쉬는 날" else ""
                    if (state.isNotEmpty()) Text(state, style = text(sp(clockDp * 0.2f), FontWeight.SemiBold, th.accent))
                }
            }
            val ring: @Composable () -> Unit = {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    val remain = if (next != null) Duration.between(now, next.runAt).seconds else 0L
                    var prev = now.toLocalDate().atStartOfDay()
                    events.forEach { if (it.runAt.isAfter(prev) && !it.runAt.isAfter(now)) prev = it.runAt }
                    val total = if (next != null) maxOf(1L, Duration.between(prev, next.runAt).seconds) else 1L
                    CountdownRing(if (next != null) 1f - remain.toFloat() / total else 0f,
                        if (next != null) TimeUtil.remaining(remain) else "--:--", if (next != null) "남음" else "",
                        remain in 0..60, size = ringDp.value.toInt(), dark = th.dark)
                    Spacer(Modifier.height(10.dp))
                    Text(next?.name ?: "예정된 종이 없어요", style = text(sp(ringDp * 0.1f), FontWeight.Bold, th.fg),
                        maxLines = 1, overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center)
                    if (next != null) Text("${TimeUtil.whenText(next.runAt, now)}  ·  ${next.soundName}",
                        style = text(sp(ringDp * 0.06f), FontWeight.Medium, th.sub), maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
            if (landscape) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceEvenly) { clock(); ring() }
            } else {
                Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(36.dp)) { clock(); ring() }
            }
            Spacer(Modifier.weight(1f))

            Upcoming(events.filter { it.status in setOf("next", "upcoming", "will_skip", "paused") }
                .take(if (landscape) 5 else 3), th, stripH)
        }
    }
}

@Composable
private fun FsButton(icon: ImageVector, th: FsTheme, onClick: () -> Unit) {
    Box(Modifier.size(48.dp).clip(RoundedCornerShape(14.dp))
        .background(if (th.dark) Color.White.copy(alpha = 0.12f) else Color.White).clickable(onClick = onClick),
        contentAlignment = Alignment.Center) {
        Icon(icon, null, tint = th.fg, modifier = Modifier.size(24.dp))
    }
}

@Composable
private fun Upcoming(items: List<TodayEvent>, th: FsTheme, h: Dp) {
    val fontScale = LocalDensity.current.fontScale
    fun sp(d: Dp): Int = (d.value / fontScale).toInt().coerceAtLeast(10)
    if (items.isEmpty()) {
        Box(Modifier.fillMaxWidth().height(h), contentAlignment = Alignment.Center) {
            Text("오늘 남은 종이 없어요", style = text(sp(h * 0.2f), FontWeight.SemiBold, th.dim))
        }
        return
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp, Alignment.CenterHorizontally)) {
        items.forEach { ev ->
            val nxt = ev.status == "next"
            Column(
                Modifier.weight(1f, fill = false).width(300.dp).height(h).clip(RoundedCornerShape(20.dp))
                    .background(if (nxt) th.cardNext else th.card).padding(horizontal = 18.dp, vertical = 10.dp),
                verticalArrangement = Arrangement.Center,
            ) {
                val (part, hm) = TimeUtil.ampmParts(ev.hhmm)
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(hm, style = text(sp(h * 0.28f), FontWeight.Bold, th.fg))
                    Spacer(Modifier.width(4.dp))
                    Text(part, style = text(sp(h * 0.14f), FontWeight.SemiBold, th.sub), modifier = Modifier.padding(bottom = 3.dp))
                }
                Text(ev.name, style = text(sp(h * 0.16f), FontWeight.SemiBold, th.fg.copy(alpha = 0.88f)),
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("${STATUS[ev.status]?.first ?: "예정"}  ·  ${ev.sound}", style = text(sp(h * 0.13f), FontWeight.Medium,
                    if (nxt) th.accent else th.dim), maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}
