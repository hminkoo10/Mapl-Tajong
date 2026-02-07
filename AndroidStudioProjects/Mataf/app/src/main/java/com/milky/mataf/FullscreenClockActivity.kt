package com.milky.mataf

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.milky.mataf.alarm.StatusStore
import com.milky.mataf.data.ScheduleRepo
import com.milky.mataf.data.SoundRepo
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

class FullscreenClockActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        requestedOrientation = android.content.pm.ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
        super.onCreate(savedInstanceState)

        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        WindowCompat.setDecorFitsSystemWindows(window, false)

        hideSystemBars()

        setContent {
            MaterialTheme {
                Surface(
                    modifier = Modifier.fillMaxSize().background(Color.Black),
                    color = Color.Black
                ) {
                    FullscreenClock(onExit = { finish() })
                }
            }
        }
    }

    private fun hideSystemBars() {
        val controller = WindowInsetsControllerCompat(window, window.decorView)
        controller.hide(WindowInsetsCompat.Type.systemBars())
        controller.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemBars()
    }
}

@Composable
private fun FullscreenClock(onExit: () -> Unit) {
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var next by remember { mutableStateOf(Triple(0L, "", "")) }
    var playing by remember { mutableStateOf("" to false) }

    val ctx = LocalContext.current
    val scheduleRepo = remember { ScheduleRepo(ctx) }
    val soundRepo = remember { SoundRepo(ctx) }

    var soundMap by remember { mutableStateOf(emptyMap<Long, String>()) }
    var upcoming by remember { mutableStateOf(emptyList<ScheduleRepo.UpcomingSchedule>()) }

    LaunchedEffect(Unit) {
        while (true) {
            now = System.currentTimeMillis()
            delay(1000L)
        }
    }

    LaunchedEffect(Unit) {
        soundMap = soundRepo.listSounds().associate { it.id to it.name }
    }

    LaunchedEffect(now) {
        next = StatusStore.getNext(ctx)
        playing = StatusStore.getNow(ctx)
        upcoming = scheduleRepo.listUpcomingWithin(
            nowMillis = now,
            horizonMillis = now + 3L * 60L * 60L * 1000L,
            limit = 10
        )
    }

    val timeFmt = remember { SimpleDateFormat("a hh:mm:ss", Locale.KOREA) }
    val (nextAt, nextTitle, nextSound) = next

    val remainText = if (nextAt > 0L) {
        val remain = (nextAt - now).coerceAtLeast(0L)
        val h = TimeUnit.MILLISECONDS.toHours(remain)
        val m = TimeUnit.MILLISECONDS.toMinutes(remain) % 60
        val s = TimeUnit.MILLISECONDS.toSeconds(remain) % 60
        "${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}"
    } else {
        "-"
    }

    val (nowName, nowIsPlaying) = playing
    val nowPlayLine = if (nowName.isBlank()) "-" else if (nowIsPlaying) nowName else nowName

    Box(Modifier.fillMaxSize().background(Color.Black)) {

        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = timeFmt.format(Date(now)),
                color = Color.White,
                style = MaterialTheme.typography.displayLarge
            )

            Spacer(Modifier.height(22.dp))

            Text(
                text = "다음 종: ${if (nextAt > 0L) (nextTitle.ifBlank { "-" } + " / " + nextSound.ifBlank { "-" }) else "-"}",
                color = Color.White,
                style = MaterialTheme.typography.titleLarge
            )

            Spacer(Modifier.height(10.dp))

            Text(
                text = "남은 시간: $remainText",
                color = Color.White,
                style = MaterialTheme.typography.headlineMedium
            )

            Spacer(Modifier.height(10.dp))

            Text(
                text = "현재 재생: $nowPlayLine",
                color = Color.White,
                style = MaterialTheme.typography.titleLarge
            )

            Spacer(Modifier.height(26.dp))

            Text(
                text = "3시간 이내 예정 (${upcoming.size})",
                color = Color(0xFFB0B0B0),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.fillMaxWidth().widthIn(max = 800.dp)
            )

            Spacer(Modifier.height(10.dp))

            LazyColumn(
                modifier = Modifier.fillMaxWidth().widthIn(max = 800.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                items(upcoming) { u ->
                    val remain = (u.runAtMillis - now).coerceAtLeast(0L)
                    val h = TimeUnit.MILLISECONDS.toHours(remain)
                    val m = TimeUnit.MILLISECONDS.toMinutes(remain) % 60
                    val s = TimeUnit.MILLISECONDS.toSeconds(remain) % 60
                    val t = "${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}"
                    val bell = soundMap[u.soundId] ?: "-"

                    Column(Modifier.fillMaxWidth()) {
                        Text(
                            text = "• $t  ${u.title}",
                            color = Color.White,
                            style = MaterialTheme.typography.bodyLarge
                        )
                        Text(
                            text = "   벨소리: $bell",
                            color = Color(0xFF9A9A9A),
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                }
            }

            Spacer(Modifier.height(18.dp))
        }

        OutlinedButton(
            onClick = onExit,
            modifier = Modifier.align(Alignment.TopEnd).padding(12.dp),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = Color(0xFFB0B0B0))
        ) {
            Text("닫기")
        }
    }
}
