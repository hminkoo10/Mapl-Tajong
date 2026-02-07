package com.milky.mataf.ui

import android.app.Activity
import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.milky.mataf.alarm.TajongService
import com.milky.mataf.data.SoundRepo
import com.milky.mataf.data.SoundRow

private const val PREFS_NAME = "mataf_prefs"
private const val KEY_SUSPEND_UNTIL_OPEN = "suspend_until_open"

@Composable
fun SoundsScreen(repo: SoundRepo) {
    val ctx = LocalContext.current

    var sounds by remember { mutableStateOf(repo.listSounds()) }
    var volume by remember { mutableStateOf(100f) }
    var name by remember { mutableStateOf("") }
    var selected by remember { mutableStateOf<SoundRow?>(null) }
    var error by remember { mutableStateOf("") }

    var showEdit by remember { mutableStateOf(false) }
    var editName by remember { mutableStateOf("") }
    var editVol by remember { mutableStateOf(100) }

    var showQuitConfirm by remember { mutableStateOf(false) }

    val pick = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        try {
            repo.addUserSoundFromUri(uri, name.trim().ifBlank { null }, volume.toInt())
            sounds = repo.listSounds()
            name = ""
            error = ""
        } catch (e: Exception) {
            error = e.message ?: "추가 실패"
        }
    }

    Column(
        Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {

        if (error.isNotBlank()) {
            Text(error, color = MaterialTheme.colorScheme.error)
        }

        Row(
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            OutlinedTextField(
                value = name,
                onValueChange = { name = it },
                modifier = Modifier.weight(1f),
                label = { Text("이름(선택)") }
            )
            Button(onClick = { pick.launch(arrayOf("audio/*")) }) {
                Text("음원 추가")
            }
        }

        Row(
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("음량 ${volume.toInt()}%", modifier = Modifier.width(100.dp))
            Slider(
                value = volume,
                onValueChange = { volume = it },
                valueRange = 0f..200f,
                steps = 199,
                modifier = Modifier.weight(1f)
            )
        }

        Row(
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            Button(
                enabled = selected != null,
                onClick = {
                    val s = selected ?: return@Button
                    val i = Intent(ctx, TajongService::class.java).apply {
                        action = TajongService.ACTION_PLAY
                        putExtra("sound_path", repo.soundPath(s.fileName))
                        putExtra("sound_name", s.name)
                        putExtra("volume_percent", s.volumePercent)
                    }
                    ContextCompat.startForegroundService(ctx, i)
                }
            ) { Text("재생") }

            OutlinedButton(
                onClick = {
                    val i = Intent(ctx, TajongService::class.java).apply {
                        action = TajongService.ACTION_STOP_PLAY
                    }
                    ctx.startService(i)
                }
            ) { Text("중지") }

            OutlinedButton(
                enabled = selected != null,
                onClick = {
                    val s = selected ?: return@OutlinedButton
                    editName = s.name
                    editVol = s.volumePercent
                    showEdit = true
                }
            ) { Text("수정") }

            OutlinedButton(
                enabled = selected != null && selected?.builtIn != 1,
                onClick = {
                    val s = selected ?: return@OutlinedButton
                    repo.removeUserSoundAndFile(s)
                    sounds = repo.listSounds()
                    selected = null
                }
            ) { Text("삭제") }
        }

        LazyColumn(Modifier.fillMaxSize()) {
            items(sounds) { s ->
                val picked = selected?.id == s.id
                val tag = if (s.builtIn == 1) "내장" else "사용자"

                ListItem(
                    headlineContent = { Text("${s.name}  ($tag)") },
                    supportingContent = { Text("${s.fileName} / ${s.volumePercent}%") },
                    colors = ListItemDefaults.colors(
                        containerColor = if (picked)
                            MaterialTheme.colorScheme.surfaceVariant
                        else
                            MaterialTheme.colorScheme.surface
                    ),
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable {
                            selected = s
                            editName = s.name
                            editVol = s.volumePercent
                        }
                )
                HorizontalDivider()
            }
        }
    }

    if (showEdit) {
        AlertDialog(
            onDismissRequest = { showEdit = false },
            title = { Text("종소리 수정") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedTextField(
                        value = editName,
                        onValueChange = { editName = it },
                        label = { Text("이름") },
                        singleLine = true
                    )

                    Row(
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("음량 ${editVol}%", modifier = Modifier.width(110.dp))
                        Slider(
                            value = editVol.toFloat(),
                            onValueChange = { editVol = it.toInt() },
                            valueRange = 0f..200f,
                            steps = 199,
                            modifier = Modifier.weight(1f)
                        )
                    }
                }
            },
            confirmButton = {
                Button(onClick = {
                    val s = selected ?: return@Button
                    val nm = editName.trim()
                    if (nm.isBlank()) return@Button
                    repo.updateSound(s.id, nm, editVol)
                    sounds = repo.listSounds()
                    selected = sounds.firstOrNull { it.id == s.id }
                    showEdit = false
                }) { Text("저장") }
            },
            dismissButton = {
                OutlinedButton(onClick = { showEdit = false }) { Text("취소") }
            }
        )
    }

}
