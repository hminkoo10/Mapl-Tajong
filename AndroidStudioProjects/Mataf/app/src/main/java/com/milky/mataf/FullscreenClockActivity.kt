package com.milky.mataf

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.milky.mataf.alarm.StatusStore
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

        setContent {
            MaterialTheme {
                Surface(
                    modifier = Modifier.fillMaxSize().background(Color.Black),
                    color = Color.Black
                ) {
                    FullscreenClock(
                        onExit = { finish() }
                    )
                }
            }
        }
    }
}

@androidx.compose.runtime.Composable
private fun FullscreenClock(onExit: () -> Unit) {
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var next by remember { mutableStateOf(Triple(0L, "", "")) }
    var playing by remember { mutableStateOf("" to false) }

    LaunchedEffect(Unit) {
        while (true) {
            now = System.currentTimeMillis()
            delay(1000L)
        }
    }

    val ctx = androidx.compose.ui.platform.LocalContext.current

    LaunchedEffect(now) {
        next = StatusStore.getNext(ctx)
        playing = StatusStore.getNow(ctx)
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
    val nowPlayLine = if (nowName.isBlank()) "-" else if (nowIsPlaying) nowName else "$nowName"

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

        Spacer(Modifier.height(24.dp))

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

        Spacer(Modifier.height(30.dp))

        Button(onClick = onExit) {
            Text("닫기")
        }
    }
}
