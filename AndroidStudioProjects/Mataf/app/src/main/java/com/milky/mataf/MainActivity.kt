package com.milky.mataf

import android.app.Activity
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Process
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.milky.mataf.alarm.AlarmScheduler
import com.milky.mataf.alarm.StatusStore
import com.milky.mataf.alarm.TajongService
import com.milky.mataf.data.SoundRepo
import com.milky.mataf.ui.SchedulesScreen
import com.milky.mataf.ui.SoundsScreen
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit
import kotlin.system.exitProcess

class MainActivity : ComponentActivity() {

    companion object {
        private const val PREFS_NAME = "mataf_prefs"
        private const val KEY_SUSPEND_UNTIL_OPEN = "suspend_until_open"
        private const val REQ_NOTI = 1001
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (Build.VERSION.SDK_INT >= 33) {
            requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), REQ_NOTI)
        }

        val repo = SoundRepo(this)
        repo.seedBuiltInFromAssets()

        val prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
        val suspended = prefs.getBoolean(KEY_SUSPEND_UNTIL_OPEN, false)
        if (suspended) {
            prefs.edit().putBoolean(KEY_SUSPEND_UNTIL_OPEN, false).apply()
        }

        startStatusService()
        AlarmScheduler.rescheduleNext(this)

        setContent {
            MaterialTheme {
                Surface(Modifier.fillMaxSize()) {
                    TajongTabs(repo)
                }
            }
        }
    }

    private fun startStatusService() {
        val i = Intent(this, TajongService::class.java).apply {
            action = TajongService.ACTION_START
        }
        ContextCompat.startForegroundService(this, i)
    }
}

@Composable
private fun TajongTabs(soundRepo: SoundRepo) {
    var tab by remember { mutableStateOf(0) }
    val titles = listOf("종소리", "시간표")
    val ctx = LocalContext.current

    Column {
        StatusCard(
            onFullscreen = {
                ctx.startActivity(Intent(ctx, FullscreenClockActivity::class.java))
            }
        )

        TabRow(selectedTabIndex = tab) {
            titles.forEachIndexed { idx, t ->
                Tab(
                    selected = tab == idx,
                    onClick = { tab = idx },
                    text = { Text(t) }
                )
            }
        }

        when (tab) {
            0 -> SoundsScreen(soundRepo)
            1 -> SchedulesScreen(soundRepo)
        }
    }
}

@Composable
private fun StatusCard(onFullscreen: () -> Unit) {
    val ctx = LocalContext.current
    val act = ctx as? Activity

    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) {
        while (true) {
            now = System.currentTimeMillis()
            delay(1000L)
        }
    }

    var next by remember { mutableStateOf(StatusStore.getNext(ctx)) }
    var playing by remember { mutableStateOf(StatusStore.getNow(ctx)) }

    DisposableEffect(ctx) {
        val prefs = ctx.getSharedPreferences("tajong_status", android.content.Context.MODE_PRIVATE)
        val listener = android.content.SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
            if (key == "next_at" || key == "next_title" || key == "next_sound") {
                next = StatusStore.getNext(ctx)
            }
            if (key == "now_name" || key == "now_playing") {
                playing = StatusStore.getNow(ctx)
            }
        }
        prefs.registerOnSharedPreferenceChangeListener(listener)
        next = StatusStore.getNext(ctx)
        playing = StatusStore.getNow(ctx)
        onDispose { prefs.unregisterOnSharedPreferenceChangeListener(listener) }
    }

    var showQuitConfirm by remember { mutableStateOf(false) }

    val (nextAt, nextTitle, nextSound) = next
    val (nowName, nowIsPlaying) = playing

    val timeFmt = remember { SimpleDateFormat("a hh:mm:ss", Locale.KOREA) }

    val remain = if (nextAt > 0L) (nextAt - now).coerceAtLeast(0L) else -1L
    val remainText = if (remain >= 0L) {
        val h = TimeUnit.MILLISECONDS.toHours(remain)
        val m = TimeUnit.MILLISECONDS.toMinutes(remain) % 60
        val s = TimeUnit.MILLISECONDS.toSeconds(remain) % 60
        "${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}"
    } else {
        "-"
    }

    Card(Modifier.fillMaxWidth().padding(12.dp)) {
        Column(
            Modifier.fillMaxWidth().padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Text("현재 시각: ${timeFmt.format(Date(now))}", style = MaterialTheme.typography.titleMedium)

            Text(
                "다음 종: ${
                    if (nextAt > 0L) "${nextTitle.ifBlank { "-" }} / ${nextSound.ifBlank { "-" }}"
                    else "-"
                }",
                style = MaterialTheme.typography.bodyLarge
            )

            Text("남은 시간: $remainText", style = MaterialTheme.typography.bodyLarge)

            Text(
                "현재 재생: ${
                    if (nowName.isBlank()) "-"
                    else if (nowIsPlaying) nowName
                    else nowName
                }",
                style = MaterialTheme.typography.bodyLarge
            )

            Spacer(Modifier.height(6.dp))

            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(onClick = onFullscreen) { Text("전체화면") }
                OutlinedButton(onClick = { showQuitConfirm = true }) { Text("앱 종료") }
            }
        }
    }

    if (showQuitConfirm) {
        AlertDialog(
            onDismissRequest = { showQuitConfirm = false },
            title = { Text("앱 종료") },
            text = { Text("종소리 알림이 중지되고 앱이 종료됩니다. 계속할까요?") },
            confirmButton = {
                Button(onClick = {
                    showQuitConfirm = false

                    AlarmScheduler.cancelNext(ctx)
                    StatusStore.clear(ctx)

                    ContextCompat.startForegroundService(
                        ctx,
                        Intent(ctx, TajongService::class.java).apply { action = TajongService.ACTION_QUIT }
                    )

                    act?.finishAffinity()
                    Process.killProcess(Process.myPid())
                    exitProcess(0)
                }) { Text("확인") }
            },
            dismissButton = {
                OutlinedButton(onClick = { showQuitConfirm = false }) { Text("취소") }
            }
        )
    }
}
