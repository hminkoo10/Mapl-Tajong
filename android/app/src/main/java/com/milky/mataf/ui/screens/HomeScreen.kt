package com.milky.mataf.ui.screens

import android.content.Intent
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
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
import androidx.compose.material.icons.rounded.Fullscreen
import androidx.compose.material.icons.rounded.NotificationsActive
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.SkipNext
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.milky.mataf.FullscreenActivity
import com.milky.mataf.core.Alarms
import com.milky.mataf.core.AppEvents
import com.milky.mataf.core.BellService
import com.milky.mataf.core.Scheduler
import com.milky.mataf.core.TodayEvent
import com.milky.mataf.data.Repo
import com.milky.mataf.data.TimeUtil
import com.milky.mataf.ui.components.Btn
import com.milky.mataf.ui.components.BtnStyle
import com.milky.mataf.ui.components.Card
import com.milky.mataf.ui.components.Page
import com.milky.mataf.ui.components.Empty
import com.milky.mataf.ui.components.Select
import com.milky.mataf.ui.components.Toasts
import com.milky.mataf.ui.components.Toggle
import com.milky.mataf.ui.components.isWide
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text
import kotlinx.coroutines.delay
import java.time.Duration
import java.time.LocalDate
import java.time.LocalDateTime

val STATUS = mapOf(
    "played" to ("울림" to C.success), "skipped" to ("건너뜀" to C.warning), "will_skip" to ("건너뛸 예정" to C.warning),
    "rang_early" to ("미리 울림" to C.success), "failed" to ("실패" to C.danger), "missed" to ("놓침" to C.danger),
    "passed" to ("지남" to C.grey400), "next" to ("다음" to C.accent), "upcoming" to ("예정" to C.grey500),
    "paused" to ("쉼" to C.grey400),
)

@Composable
fun rememberNow(): LocalDateTime {
    var now by remember { mutableStateOf(LocalDateTime.now()) }
    LaunchedEffect(Unit) {
        while (true) {
            val n = LocalDateTime.now()
            now = n
            delay(1000L - n.nano / 1_000_000 + 5)
        }
    }
    return now
}

@Composable
fun HomeScreen() {
    val ctx = LocalContext.current
    val version by AppEvents.version.collectAsState()
    val ringing by BellService.ringing.collectAsState()
    val now = rememberNow()
    val repo = remember { Repo(ctx) }
    val minute = now.withSecond(0).withNano(0)
    val next = remember(version, minute) { Scheduler.next(repo, now) }
    val today = remember(version, minute) { Scheduler.today(repo, now) }
    val paused = remember(version) { Scheduler.isPaused(repo) }
    val pauseDay = remember(version, now.toLocalDate()) { repo.isPauseDay(now.toLocalDate()) }
    val played = remember(version, minute) { repo.countPlayed(now.toLocalDate()) }
    val setName = remember(version) { repo.sets().firstOrNull { it.id == repo.activeSetId() }?.name ?: "" }
    val wide = isWide()

    Page(16.dp) {
        // 시계
        Row(verticalAlignment = Alignment.Bottom) {
            Column(Modifier.weight(1f)) {
                Text("${now.monthValue}월 ${now.dayOfMonth}일 ${TimeUtil.WEEK_KO[now.dayOfWeek.value - 1]}요일",
                    style = text(15, FontWeight.SemiBold, C.grey600))
                RollingClock("%02d:%02d:%02d".format(now.hour, now.minute, now.second), if (wide) 52 else 44)
            }
            StatusDot(if (paused) "잠시 멈춤" else if (pauseDay) "오늘은 쉬는 날" else if (next != null) "자동 타종 중" else "대기 중",
                if (paused || pauseDay) C.warning else if (next != null) C.success else C.grey400)
        }

        if (!Alarms.canExact(ctx)) {
            Card(padding = 16.dp) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Rounded.Warning, null, tint = C.warning)
                    Spacer(Modifier.width(10.dp))
                    Text("정확한 시각에 울리려면 ‘알람 및 리마인더’ 권한이 필요해요.", style = text(14, FontWeight.Medium),
                        modifier = Modifier.weight(1f))
                    Btn("허용하기", { Alarms.openExactSettings(ctx) }, small = true, style = BtnStyle.Soft)
                }
            }
        }

        val left: @Composable () -> Unit = {
            Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                NextCard(next, now, setName, today)
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    ActionTile(Icons.Rounded.NotificationsActive, "다음 종 지금 울리기", "기다리지 않고 바로 울려요",
                        Modifier.weight(1f), enabled = next != null) {
                        val ev = Scheduler.ringNextNow(ctx)
                        if (ev != null) Toasts.show("${TimeUtil.ampm(ev.runAt.toLocalTime())} ${ev.name} 종을 지금 울렸어요", "success",
                            "되돌리기") { BellService.stop(ctx); Scheduler.undo(ctx, ev.scheduleId, ev.runAt.toLocalDate(), Scheduler.FIRED) }
                    }
                    ActionTile(Icons.Rounded.SkipNext, "다음 종 건너뛰기", "이번 한 번만 울리지 않아요", Modifier.weight(1f),
                        enabled = next != null) {
                        val ev = Scheduler.skipNext(ctx)
                        if (ev != null) Toasts.show("${TimeUtil.ampm(ev.runAt.toLocalTime())} ${ev.name} 종은 이번에 건너뛸게요", "info",
                            "되돌리기") { Scheduler.undo(ctx, ev.scheduleId, ev.runAt.toLocalDate(), Scheduler.SKIP) }
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    ActionTile(if (paused) Icons.Rounded.PlayArrow else Icons.Rounded.Pause,
                        if (paused) "자동 타종 다시 켜기" else "잠시 멈추기",
                        if (paused) "멈춘 동안 울리지 않았어요" else "자동 타종을 멈춰요", Modifier.weight(1f)) {
                        Scheduler.setPaused(ctx, !paused)
                        Toasts.show(if (paused) "자동 타종을 다시 켰어요" else "자동 타종을 잠시 멈췄어요")
                    }
                    ActionTile(Icons.Rounded.Fullscreen, "전체화면 시계", "교실 화면에 크게 띄워요", Modifier.weight(1f)) {
                        ctx.startActivity(Intent(ctx, FullscreenActivity::class.java))
                    }
                }
                ManualPlayCard(ringing)
            }
        }
        val right: @Composable () -> Unit = {
            TodayCard(today, played, pauseDay, now) { on ->
                repo.setPauseDay(LocalDate.now(), on)
                Alarms.reschedule(ctx)
                Toasts.show(if (on) "오늘은 자동 타종을 하지 않아요" else "오늘 자동 타종을 다시 켰어요")
            }
        }
        if (wide) {
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                Box(Modifier.weight(3f)) { left() }
                Box(Modifier.weight(2f)) { right() }
            }
        } else {
            left(); right()
        }
        Text("구현민 개발", style = text(12, color = C.grey400), modifier = Modifier.padding(start = 4.dp, top = 4.dp))
    }
}

@Composable
fun RollingClock(t: String, size: Int, color: Color = C.grey900) {
    Row {
        t.forEach { ch ->
            AnimatedContent(ch, transitionSpec = {
                (slideInVertically(tween(320)) { it / 2 } + fadeIn(tween(320))) togetherWith
                    (slideOutVertically(tween(320)) { -it / 2 } + fadeOut(tween(240)))
            }, label = "digit") { c ->
                Text(c.toString(), style = text(size, FontWeight.Bold, color).copy(fontFeatureSettings = "tnum"))
            }
        }
    }
}

@Composable
fun StatusDot(label: String, color: Color) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(color))
        Spacer(Modifier.width(6.dp))
        Text(label, style = text(14, FontWeight.SemiBold, C.grey700))
    }
}

@Composable
private fun NextCard(next: com.milky.mataf.core.NextEvent?, now: LocalDateTime, setName: String, today: List<TodayEvent>) {
    Card {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("다음 종", style = text(14, FontWeight.SemiBold, C.grey600))
                Spacer(Modifier.height(6.dp))
                Text(next?.name ?: "예정된 종이 없어요", style = text(24, FontWeight.Bold), maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text(if (next != null) "${TimeUtil.whenText(next.runAt, now)}  ·  ${next.soundName}" else "시간표에서 일정을 추가해 보세요",
                    style = text(14, color = C.grey600), modifier = Modifier.padding(top = 4.dp))
                Spacer(Modifier.height(18.dp))
                Text(setName, style = text(13, color = C.grey500))
            }
            val remain = if (next != null) Duration.between(now, next.runAt).seconds else 0L
            var prev = now.toLocalDate().atStartOfDay()
            today.forEach { if (it.runAt.isAfter(prev) && !it.runAt.isAfter(now)) prev = it.runAt }
            val total = if (next != null) maxOf(1L, Duration.between(prev, next.runAt).seconds) else 1L
            CountdownRing(if (next != null) 1f - remain.toFloat() / total else 0f,
                if (next != null) TimeUtil.remaining(remain) else "--:--", if (next != null) "남음" else "", remain in 0..60)
        }
    }
}

@Composable
fun CountdownRing(progress: Float, center: String, sub: String, urgent: Boolean, size: Int = 132, dark: Boolean = false) {
    val p by animateFloatAsState(progress.coerceIn(0f, 1f), tween(700), label = "ring")
    Box(Modifier.size(size.dp), contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(size.dp)) {
            val th = this.size.minDimension * 0.075f
            val inset = th / 2 + 4
            val sz = Size(this.size.width - inset * 2, this.size.height - inset * 2)
            drawArc(if (dark) Color.White.copy(alpha = 0.12f) else C.grey100, 0f, 360f, false, Offset(inset, inset), sz,
                style = Stroke(th, cap = StrokeCap.Round))
            if (p > 0.003f) {
                drawArc(Brush.sweepGradient(listOf(C.g0, C.g2, C.g0)), -90f, 360f * p, false, Offset(inset, inset), sz,
                    style = Stroke(th, cap = StrokeCap.Round))
            }
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(center, style = text(if (center.length <= 5) (size * 0.17).toInt() else (size * 0.13).toInt(), FontWeight.Bold,
                if (urgent) (if (dark) Color(0xFFFFB27A) else C.accent) else if (dark) Color.White else C.grey900))
            if (sub.isNotEmpty()) Text(sub, style = text((size * 0.085).toInt(), FontWeight.Medium,
                if (dark) Color.White.copy(alpha = 0.6f) else C.grey500))
        }
    }
}

@Composable
private fun ActionTile(icon: ImageVector, title: String, desc: String, modifier: Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    Row(
        modifier.clip(RoundedCornerShape(20.dp)).background(Color.White).clickable(enabled = enabled, onClick = onClick).padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(40.dp).clip(CircleShape).background(if (enabled) C.accentSofter else C.grey100), contentAlignment = Alignment.Center) {
            Icon(icon, null, tint = if (enabled) C.accent else C.grey400, modifier = Modifier.size(22.dp))
        }
        Spacer(Modifier.width(12.dp))
        Column {
            Text(title, style = text(15, FontWeight.Bold, if (enabled) C.grey900 else C.grey400), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(desc, style = text(12, color = if (enabled) C.grey500 else C.grey300), maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun ManualPlayCard(ringing: String?) {
    val ctx = LocalContext.current
    val version by AppEvents.version.collectAsState()
    val sounds = remember(version) { Repo(ctx).sounds() }
    var sel by remember { mutableStateOf<Long?>(null) }
    val chosen = sel ?: sounds.firstOrNull()?.id
    Card {
        Text("종소리 바로 울리기", style = text(16, FontWeight.Bold))
        Spacer(Modifier.height(12.dp))
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Select(sounds.map { it.id to it.name }, chosen, { sel = it }, Modifier.weight(1f))
            Btn("울리기", { chosen?.let { BellService.playSound(ctx, it) } }, style = BtnStyle.Primary, enabled = chosen != null)
            Btn("정지", { BellService.stop(ctx) }, icon = Icons.Rounded.Stop, enabled = ringing != null)
        }
        if (ringing != null) {
            Text("‘$ringing’ 울리는 중", style = text(13, FontWeight.Medium, C.accentText), modifier = Modifier.padding(top = 8.dp))
        }
    }
}

@Composable
private fun TodayCard(events: List<TodayEvent>, played: Int, pauseDay: Boolean, now: LocalDateTime, onPauseDay: (Boolean) -> Unit) {
    val ctx = LocalContext.current
    Card {
        Text("오늘", style = text(17, FontWeight.Bold))
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Stat("울린 종", "${played}번", Modifier.weight(1f))
            Stat("남은 종", "${events.count { it.status in setOf("next", "upcoming") }}번", Modifier.weight(1f))
        }
        Spacer(Modifier.height(8.dp))
        if (events.isEmpty()) Empty("오늘은 울릴 종이 없어요")
        events.forEach { ev -> TodayRow(ev, now) { action ->
            if (Scheduler.undo(ctx, ev.scheduleId, ev.date, action)) Toasts.show(
                if (action == Scheduler.SKIP) "건너뛰기를 취소했어요. 정해진 시간에 울려요" else "정해진 시간에 다시 울려요", "success")
        } }
        Spacer(Modifier.height(10.dp))
        Box(Modifier.fillMaxWidth().height(1.dp).background(C.grey100))
        Row(Modifier.fillMaxWidth().padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("오늘 하루 자동 타종 끄기", style = text(15, FontWeight.Medium), modifier = Modifier.weight(1f))
            Toggle(pauseDay, onPauseDay)
        }
    }
}

@Composable
private fun Stat(label: String, value: String, modifier: Modifier) {
    Column(modifier.clip(RoundedCornerShape(14.dp)).background(C.grey50).padding(14.dp)) {
        Text(label, style = text(13, color = C.grey600))
        Text(value, style = text(22, FontWeight.Bold))
    }
}

@Composable
private fun TodayRow(ev: TodayEvent, now: LocalDateTime, onUndo: (String) -> Unit) {
    val nxt = ev.status == "next"
    val past = ev.status in setOf("played", "skipped", "failed", "missed", "passed")
    val undo = when (ev.status) {
        "will_skip" -> Scheduler.SKIP to "울리기"
        "rang_early" -> Scheduler.FIRED to "제때 울리기"
        else -> null
    }
    val (label, col) = STATUS[ev.status] ?: ("예정" to C.grey500)
    val (part, hm) = TimeUtil.ampmParts(ev.hhmm)
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (nxt) C.accentSofter else Color.Transparent)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.width(56.dp)) {
            Text(part, style = text(11, FontWeight.SemiBold, if (past) C.grey400 else if (nxt) C.accent else C.grey500))
            Text(hm, style = text(16, FontWeight.Bold, if (past) C.grey400 else if (nxt) C.accent else C.grey900))
        }
        Column(Modifier.weight(1f)) {
            Text(ev.name, style = text(15, FontWeight.Medium, if (past || undo != null) C.grey400 else C.grey900), maxLines = 1,
                overflow = TextOverflow.Ellipsis)
            Row {
                if (undo != null) Text("$label · ", style = text(12, FontWeight.SemiBold, col))
                Text(ev.sound, style = text(12, color = C.grey500), maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        if (undo != null) {
            Btn(undo.second, { onUndo(undo.first) }, small = true, style = BtnStyle.Soft)
        } else {
            Text(if (nxt) TimeUtil.remainWords(Duration.between(now, ev.runAt).seconds) else label,
                style = text(13, FontWeight.SemiBold, col))
        }
    }
}
