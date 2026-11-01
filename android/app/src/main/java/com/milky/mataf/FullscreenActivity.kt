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
import androidx.compose.foundation.layout.fillMaxHeight
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
import androidx.compose.ui.unit.min
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.milky.mataf.core.AppEvents
import com.milky.mataf.core.Scheduler
import com.milky.mataf.core.TodayEvent
import com.milky.mataf.core.Weather
import com.milky.mataf.core.WxData
import com.milky.mataf.core.WxHour
import com.milky.mataf.data.Repo
import com.milky.mataf.data.TimeUtil
import com.milky.mataf.ui.components.WeatherIcon
import com.milky.mataf.ui.screens.CountdownRing
import com.milky.mataf.ui.screens.PlaceSheet
import com.milky.mataf.ui.screens.RollingClock
import com.milky.mataf.ui.screens.STATUS
import com.milky.mataf.ui.screens.rememberNow
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.MatafTheme
import com.milky.mataf.ui.theme.text
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import java.time.Duration

/** 교실 화면에 크게 띄우는 시계 (데스크톱 전체화면 시계와 같은 구성) */
class FullscreenActivity : ComponentActivity() {
    companion object {
        /** 교실 화면에 시계를 띄워 둔 동안은 자동 업데이트를 미룬다 */
        @Volatile var showing = false
    }

    override fun onStart() {
        super.onStart()
        showing = true
    }

    override fun onStop() {
        showing = false
        super.onStop()
    }

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

    // 날씨: 열 때와 10분마다 (받는 간격은 Weather.get 이 서버 규칙대로 지킨다)
    val weatherOn = remember { repo.setting("weather_on", "1") != "0" }
    var placeVer by remember { mutableStateOf(0) }
    var wx by remember { mutableStateOf<WxData?>(null) }
    var wxFailed by remember { mutableStateOf(false) }
    var picking by remember { mutableStateOf(false) }
    LaunchedEffect(placeVer) {
        if (!weatherOn) return@LaunchedEffect
        while (true) {
            val d = withContext(Dispatchers.IO) { Weather.get(ctx, Weather.place(repo)) }
            wx = d
            wxFailed = d == null
            delay(10 * 60 * 1000L)
        }
    }
    if (picking) PlaceSheet(onPicked = { placeVer++ }, onDismiss = { picking = false })

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
        val hourly = wx?.hours.orEmpty()
        val ringDp = if (landscape) minOf(maxHeight * 0.44f, maxWidth * 0.27f)
        else if (hourly.isNotEmpty()) minOf(maxWidth * 0.55f, maxHeight * 0.26f) else minOf(maxWidth * 0.62f, maxHeight * 0.32f)
        val pad = if (landscape) 48.dp else 24.dp
        val stripH = if (landscape) (maxHeight * 0.16f).coerceIn(84.dp, 140.dp) else 92.dp
        val hourlyW = min(maxWidth * 0.42f, maxHeight * 0.75f)
        val hourlyH = (maxHeight * 0.15f).coerceIn(72.dp, 130.dp)
        val wxPx = if (landscape) (maxHeight * 0.03f).coerceIn(16.dp, 30.dp) else (maxHeight * 0.025f).coerceIn(16.dp, 24.dp)
        val weatherNow: @Composable () -> Unit = {
            if (weatherOn) WeatherNow(wx, wxFailed, th, wxPx) { picking = true }
        }

        Column(Modifier.fillMaxSize().padding(horizontal = pad, vertical = if (landscape) 28.dp else 36.dp)) {
            // 위: 날짜 · 버튼
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("${now.year}년 ${now.monthValue}월 ${now.dayOfMonth}일 ${TimeUtil.WEEK_KO[now.dayOfWeek.value - 1]}요일",
                    style = text(sp(if (landscape) 26.dp else 20.dp), FontWeight.SemiBold, th.sub), modifier = Modifier.weight(1f))
                if (landscape) {
                    weatherNow()
                    Spacer(Modifier.width(8.dp))
                }
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
            if (!landscape) {
                Spacer(Modifier.height(10.dp))
                weatherNow()
            }
            Spacer(Modifier.weight(1f))

            val clock: @Composable () -> Unit = {
                Column(horizontalAlignment = if (landscape) Alignment.Start else Alignment.CenterHorizontally) {
                    RollingClock("%02d:%02d:%02d".format(now.hour, now.minute, now.second), sp(clockDp), th.fg)
                    val state = if (paused) "잠시 멈춤" else if (pauseDay) "오늘은 쉬는 날" else ""
                    if (state.isNotEmpty()) Text(state, style = text(sp(clockDp * 0.2f), FontWeight.SemiBold, th.accent))
                    if (hourly.isNotEmpty()) {
                        Spacer(Modifier.height(18.dp))
                        HourlyStrip(hourly, th, if (landscape) 6 else 4,
                            if (landscape) Modifier.width(hourlyW).height(hourlyH) else Modifier.fillMaxWidth().height(92.dp))
                    }
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
                        remain in 0..60, size = ringDp.value.toInt(), dark = th.dark, track = if (th.dark) null else C.grey200)
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
                    verticalArrangement = Arrangement.spacedBy(if (hourly.isNotEmpty()) 24.dp else 36.dp)) { clock(); ring() }
            }
            Spacer(Modifier.weight(1f))

            Upcoming(events.filter { it.status in setOf("next", "upcoming", "will_skip", "paused") }
                .take(if (landscape) 5 else 3), th, stripH)
        }
        // 날씨 출처는 아래 여백 위에 (휴대폰 가로 화면에서 남은 종 카드를 밀어내지 않게)
        if (wx != null) {
            Text(Weather.CREDIT, style = text(11, color = th.dim),
                modifier = Modifier.align(Alignment.BottomEnd).padding(end = pad, bottom = if (landscape) 8.dp else 12.dp))
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

private fun temp(v: Double?): String = if (v == null) "-" else "${Math.rint(v).toInt()}°"

/** 지금 날씨와 오늘 최고/최저. 누르면 지역을 바꾼다 */
@Composable
private fun WeatherNow(d: WxData?, failed: Boolean, th: FsTheme, px: Dp, onClick: () -> Unit) {
    val fontScale = LocalDensity.current.fontScale
    fun sp(x: Dp): Int = (x.value / fontScale).toInt().coerceAtLeast(10)
    if (d == null) {
        if (failed) Text("날씨를 불러오지 못했어요 · 눌러서 지역 확인", style = text(sp(px * 0.5f), FontWeight.Medium, th.dim),
            modifier = Modifier.clip(RoundedCornerShape(10.dp)).clickable(onClick = onClick).padding(6.dp))
        return
    }
    val h = px * 1.9f
    Row(Modifier.height(h).clip(RoundedCornerShape(12.dp)).clickable(onClick = onClick).padding(horizontal = 6.dp),
        verticalAlignment = Alignment.CenterVertically) {
        WeatherIcon(d.now.kind, d.now.night, th.dark, Modifier.size(h * 0.92f))
        Spacer(Modifier.width(10.dp))
        Text(temp(d.now.temp), style = text(sp(px * 1.15f), FontWeight.Bold, th.fg))
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f, fill = false)) {
            Text("${d.city} · ${d.now.text}", style = text(sp(px * 0.6f), FontWeight.SemiBold, th.fg.copy(alpha = 0.9f)),
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text("최고 ${temp(d.todayMax)}  최저 ${temp(d.todayMin)}", style = text(sp(px * 0.5f), FontWeight.Medium, th.sub), maxLines = 1)
        }
    }
}

/** 시계 아래: 앞으로 몇 시간의 날씨 */
@Composable
private fun HourlyStrip(hours: List<WxHour>, th: FsTheme, slots: Int, modifier: Modifier) {
    val fontScale = LocalDensity.current.fontScale
    fun sp(x: Dp): Int = (x.value / fontScale).toInt().coerceAtLeast(10)
    val step = if (hours.size >= slots * 2) 2 else 1
    val picks = hours.filterIndexed { i, _ -> i % step == 0 }.take(slots)
    BoxWithConstraints(modifier.clip(RoundedCornerShape(22.dp)).background(th.card)) {
        val h = maxHeight
        Row(Modifier.fillMaxSize().padding(vertical = h * 0.06f)) {
            picks.forEach { it ->
                Column(Modifier.weight(1f).fillMaxHeight(), horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.SpaceBetween) {
                    val hr = it.time.hour
                    Text("${if (hr < 12) "오전" else "오후"} ${if (hr % 12 == 0) 12 else hr % 12}시",
                        style = text(sp(h * 0.14f), FontWeight.SemiBold, th.sub), maxLines = 1)
                    WeatherIcon(it.kind, it.night, th.dark, Modifier.size(h * 0.40f))
                    Text(temp(it.temp), style = text(sp(h * 0.17f), FontWeight.Bold, th.fg), maxLines = 1)
                }
            }
        }
    }
}
