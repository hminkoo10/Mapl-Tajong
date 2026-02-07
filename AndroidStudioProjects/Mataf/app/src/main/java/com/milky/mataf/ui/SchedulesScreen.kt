package com.milky.mataf.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.milky.mataf.alarm.AlarmScheduler
import com.milky.mataf.data.ScheduleRepo
import com.milky.mataf.data.ScheduleRow
import com.milky.mataf.data.SoundRepo
import com.milky.mataf.data.SoundRow

@Composable
fun SchedulesScreen(soundRepo: SoundRepo) {
    val ctx = LocalContext.current
    val repo = remember { ScheduleRepo(ctx) }

    var sounds by remember { mutableStateOf(soundRepo.listSounds()) }
    var schedules by remember { mutableStateOf(repo.listSchedules()) }
    var selected by remember { mutableStateOf<ScheduleRow?>(null) }

    var showEdit by remember { mutableStateOf(false) }
    var showDeleteConfirm by remember { mutableStateOf(false) }

    var showExactDialog by remember { mutableStateOf(false) }

    var editId by remember { mutableStateOf<Long?>(null) }
    var editName by remember { mutableStateOf("") }
    var editMask by remember { mutableIntStateOf(0) }
    var editHour12 by remember { mutableIntStateOf(9) }
    var editMin by remember { mutableIntStateOf(0) }
    var editIsPm by remember { mutableStateOf(false) }
    var editSoundId by remember { mutableLongStateOf(-1L) }
    var editEnabled by remember { mutableStateOf(true) }

    fun refreshAll() {
        sounds = soundRepo.listSounds()
        schedules = repo.listSchedules()
        AlarmScheduler.rescheduleNext(ctx)
    }

    Column(
        Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            Button(onClick = {
                sounds = soundRepo.listSounds()
                editId = null
                editName = ""
                editMask = 0
                editHour12 = 9
                editMin = 0
                editIsPm = false
                editSoundId = sounds.firstOrNull()?.id ?: -1L
                editEnabled = true
                showEdit = true
            }) { Text("추가") }

            OutlinedButton(
                enabled = selected != null,
                onClick = {
                    sounds = soundRepo.listSounds()
                    val s = selected ?: return@OutlinedButton

                    editId = s.id
                    editName = s.name
                    editMask = s.weekdayMask

                    val h24 = s.hour.coerceIn(0, 23)
                    editIsPm = h24 >= 12
                    editHour12 = when {
                        h24 == 0 -> 12
                        h24 in 1..12 -> h24
                        else -> h24 - 12
                    }

                    editMin = s.minute.coerceIn(0, 59)
                    editSoundId = s.soundId
                    editEnabled = s.enabled == 1
                    showEdit = true
                }
            ) { Text("수정") }

            OutlinedButton(
                enabled = selected != null,
                onClick = { showDeleteConfirm = true }
            ) { Text("삭제") }
        }

        LazyColumn(Modifier.fillMaxSize()) {
            items(schedules) { sc ->
                val picked = selected?.id == sc.id
                val soundName = sounds.firstOrNull { it.id == sc.soundId }?.name ?: "-"

                ListItem(
                    headlineContent = {
                        Text(
                            "${formatDays(sc.weekdayMask)}  " +
                                    "${sc.hour.toString().padStart(2, '0')}:${sc.minute.toString().padStart(2, '0')}  " +
                                    sc.name
                        )
                    },
                    supportingContent = {
                        Text("종: $soundName / 상태: ${if (sc.enabled == 1) "ON" else "OFF"}")
                    },
                    colors = ListItemDefaults.colors(
                        containerColor = if (picked) MaterialTheme.colorScheme.surfaceVariant else MaterialTheme.colorScheme.surface
                    ),
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { selected = sc }
                )
                HorizontalDivider()
            }
        }
    }

    if (showDeleteConfirm) {
        AlertDialog(
            onDismissRequest = { showDeleteConfirm = false },
            title = { Text("삭제") },
            text = { Text("삭제할까요?") },
            confirmButton = {
                Button(onClick = {
                    val s = selected ?: return@Button
                    repo.deleteSchedule(s.id)
                    selected = null
                    showDeleteConfirm = false
                    refreshAll()
                }) { Text("삭제") }
            },
            dismissButton = {
                OutlinedButton(onClick = { showDeleteConfirm = false }) { Text("취소") }
            }
        )
    }

    if (showExactDialog) {
        AlertDialog(
            onDismissRequest = { showExactDialog = false },
            title = { Text("정확한 알람 권한 필요") },
            text = {
                Text(
                    "정해진 시간에 종을 정확히 울리려면 “정확한 알람” 권한이 필요합니다.\n" +
                            "설정에서 허용한 뒤 다시 저장해 주세요."
                )
            },
            confirmButton = {
                Button(onClick = {
                    showExactDialog = false
                    AlarmScheduler.openExactAlarmSettings(ctx)
                }) { Text("설정으로 이동") }
            },
            dismissButton = {
                OutlinedButton(onClick = { showExactDialog = false }) { Text("취소") }
            }
        )
    }

    if (showEdit) {
        val soundList: List<SoundRow> = sounds

        if (editSoundId <= 0L || soundList.none { it.id == editSoundId }) {
            editSoundId = soundList.firstOrNull()?.id ?: -1L
        }

        var hourText by remember(showEdit) { mutableStateOf(editHour12.toString()) }
        var minText by remember(showEdit) { mutableStateOf(editMin.toString().padStart(2, '0')) }

        fun syncHourFromText() {
            val v = hourText.trim().toIntOrNull()
            if (v != null) editHour12 = v.coerceIn(1, 12)
        }

        fun syncMinFromText() {
            val v = minText.trim().toIntOrNull()
            if (v != null) editMin = v.coerceIn(0, 59)
        }

        var soundExpanded by remember(showEdit) { mutableStateOf(false) }
        val currentSound = soundList.firstOrNull { it.id == editSoundId }
        val currentSoundLabel = currentSound?.name ?: "종소리 선택"

        var warn by remember(showEdit) { mutableStateOf<String?>(null) }

        AlertDialog(
            onDismissRequest = { showEdit = false },
            title = { Text(if (editId == null) "시간표 추가" else "시간표 수정") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {

                    OutlinedTextField(
                        value = editName,
                        onValueChange = { editName = it },
                        label = { Text("이벤트명") },
                        singleLine = true,
                        isError = warn != null && editName.trim().isBlank()
                    )

                    if (warn != null) {
                        Text(warn!!, color = MaterialTheme.colorScheme.error)
                    }

                    Text("요일")
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        DayChip("월", editMask, 1) { editMask = it }
                        DayChip("화", editMask, 2) { editMask = it }
                        DayChip("수", editMask, 4) { editMask = it }
                        DayChip("목", editMask, 8) { editMask = it }
                        DayChip("금", editMask, 16) { editMask = it }
                        DayChip("토", editMask, 32) { editMask = it }
                        DayChip("일", editMask, 64) { editMask = it }
                    }

                    Text("오전/오후")
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(
                            selected = !editIsPm,
                            onClick = { editIsPm = false },
                            label = { Text("오전") }
                        )
                        FilterChip(
                            selected = editIsPm,
                            onClick = { editIsPm = true },
                            label = { Text("오후") }
                        )
                    }

                    Text("시간")
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {

                        Column {
                            Text("시")
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                                OutlinedButton(onClick = {
                                    syncHourFromText()
                                    editHour12 = (editHour12 - 1).let { if (it < 1) 12 else it }
                                    hourText = editHour12.toString()
                                }) { Text("-") }

                                OutlinedTextField(
                                    value = hourText,
                                    onValueChange = {
                                        hourText = it.filter { ch -> ch.isDigit() }.take(2)
                                        val v = hourText.toIntOrNull()
                                        if (v != null) {
                                            editHour12 = v.coerceIn(1, 12)
                                            hourText = editHour12.toString()
                                        }
                                    },
                                    singleLine = true,
                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                    modifier = Modifier.width(84.dp),
                                    label = { Text("1-12") }
                                )

                                OutlinedButton(onClick = {
                                    syncHourFromText()
                                    editHour12 = (editHour12 + 1).let { if (it > 12) 1 else it }
                                    hourText = editHour12.toString()
                                }) { Text("+") }
                            }
                        }

                        Column {
                            Text("분")
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                                OutlinedButton(onClick = {
                                    syncMinFromText()
                                    editMin = (editMin - 5).coerceAtLeast(0)
                                    minText = editMin.toString().padStart(2, '0')
                                }) { Text("-") }

                                OutlinedTextField(
                                    value = minText,
                                    onValueChange = {
                                        minText = it.filter { ch -> ch.isDigit() }.take(2)
                                        val v = minText.toIntOrNull()
                                        if (v != null) {
                                            editMin = v.coerceIn(0, 59)
                                            minText = editMin.toString().padStart(2, '0')
                                        }
                                    },
                                    singleLine = true,
                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                    modifier = Modifier.width(84.dp),
                                    label = { Text("00-59") }
                                )

                                OutlinedButton(onClick = {
                                    syncMinFromText()
                                    editMin = (editMin + 5).coerceAtMost(59)
                                    minText = editMin.toString().padStart(2, '0')
                                }) { Text("+") }
                            }
                        }
                    }

                    Text("종소리")
                    Box(Modifier.fillMaxWidth()) {
                        OutlinedTextField(
                            value = currentSoundLabel,
                            onValueChange = {},
                            readOnly = true,
                            singleLine = true,
                            label = { Text("선택") },
                            modifier = Modifier.fillMaxWidth()
                        )

                        Box(
                            modifier = Modifier
                                .matchParentSize()
                                .clickable {
                                    if (soundList.isNotEmpty()) soundExpanded = true
                                }
                        )

                        DropdownMenu(
                            expanded = soundExpanded,
                            onDismissRequest = { soundExpanded = false },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            soundList.forEach { s ->
                                DropdownMenuItem(
                                    text = { Text(s.name) },
                                    onClick = {
                                        editSoundId = s.id
                                        soundExpanded = false
                                    }
                                )
                            }
                        }
                    }

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = editEnabled, onCheckedChange = { editEnabled = it })
                        Text("활성")
                    }
                }
            },
            confirmButton = {
                Button(onClick = {
                    warn = null

                    val nm = editName.trim()
                    if (nm.isBlank()) {
                        warn = "이벤트명을 입력하세요"
                        return@Button
                    }
                    if (editMask == 0) {
                        warn = "요일을 선택하세요"
                        return@Button
                    }
                    if (soundList.isEmpty()) {
                        warn = "종소리가 없습니다"
                        return@Button
                    }
                    if (editSoundId <= 0L || soundList.none { it.id == editSoundId }) {
                        warn = "종소리를 선택하세요"
                        return@Button
                    }

                    if (!AlarmScheduler.canScheduleExact(ctx)) {
                        showExactDialog = true
                        return@Button
                    }

                    syncHourFromText()
                    syncMinFromText()

                    val h12 = editHour12.coerceIn(1, 12)
                    val hour24 = if (editIsPm) {
                        if (h12 == 12) 12 else h12 + 12
                    } else {
                        if (h12 == 12) 0 else h12
                    }
                    val minute = editMin.coerceIn(0, 59)

                    if (editId == null) {
                        repo.insertSchedule(nm, editMask, hour24, minute, editSoundId, if (editEnabled) 1 else 0)
                    } else {
                        repo.updateSchedule(editId!!, nm, editMask, hour24, minute, editSoundId, if (editEnabled) 1 else 0)
                    }

                    showEdit = false
                    refreshAll()
                }) { Text("저장") }
            },
            dismissButton = {
                OutlinedButton(onClick = { showEdit = false }) { Text("취소") }
            }
        )
    }
}

@Composable
private fun DayChip(label: String, mask: Int, bit: Int, onChange: (Int) -> Unit) {
    val checked = (mask and bit) != 0
    FilterChip(
        selected = checked,
        onClick = { onChange(if (checked) mask and bit.inv() else mask or bit) },
        label = { Text(label) }
    )
}

private fun formatDays(mask: Int): String {
    val parts = ArrayList<String>()
    if ((mask and 1) != 0) parts.add("월")
    if ((mask and 2) != 0) parts.add("화")
    if ((mask and 4) != 0) parts.add("수")
    if ((mask and 8) != 0) parts.add("목")
    if ((mask and 16) != 0) parts.add("금")
    if ((mask and 32) != 0) parts.add("토")
    if ((mask and 64) != 0) parts.add("일")
    return if (parts.isEmpty()) "-" else parts.joinToString("")
}
