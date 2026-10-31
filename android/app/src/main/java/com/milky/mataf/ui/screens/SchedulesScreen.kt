package com.milky.mataf.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.milky.mataf.core.Alarms
import com.milky.mataf.core.AppEvents
import com.milky.mataf.core.Sounds
import com.milky.mataf.data.BatchChange
import com.milky.mataf.data.Repo
import com.milky.mataf.data.Schedule
import com.milky.mataf.data.TimeUtil
import com.milky.mataf.ui.components.AppMenu
import com.milky.mataf.ui.components.AppSheet
import com.milky.mataf.ui.components.Btn
import com.milky.mataf.ui.components.BtnStyle
import com.milky.mataf.ui.components.Card
import com.milky.mataf.ui.components.CheckCircle
import com.milky.mataf.ui.components.Chip
import com.milky.mataf.ui.components.ConfirmDialog
import com.milky.mataf.ui.components.DayChips
import com.milky.mataf.ui.components.Empty
import com.milky.mataf.ui.components.Field
import com.milky.mataf.ui.components.IconBtn
import com.milky.mataf.ui.components.Label
import com.milky.mataf.ui.components.MenuItem
import com.milky.mataf.ui.components.Page
import com.milky.mataf.ui.components.PageHeader
import com.milky.mataf.ui.components.Select
import com.milky.mataf.ui.components.SheetButtons
import com.milky.mataf.ui.components.TimePicker
import com.milky.mataf.ui.components.Toasts
import com.milky.mataf.ui.components.Toggle
import com.milky.mataf.ui.components.ToggleRow
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text

private fun changed(ctx: android.content.Context) = Alarms.reschedule(ctx)

@Composable
fun SchedulesScreen() {
    val ctx = LocalContext.current
    val repo = remember { Repo(ctx) }
    val version by AppEvents.version.collectAsState()
    val sets = remember(version) { repo.sets() }
    val activeId = remember(version) { repo.activeSetId() }
    val all = remember(version, activeId) { repo.schedules(activeId) }
    var query by remember { mutableStateOf("") }
    var dayFilter by remember { mutableStateOf(0) }
    val selected = remember { mutableStateListOf<Long>() }
    var editing by remember { mutableStateOf<Schedule?>(null) }
    var adding by remember { mutableStateOf(false) }
    var batch by remember { mutableStateOf(false) }
    var setMenu by remember { mutableStateOf(false) }
    var askName by remember { mutableStateOf<Pair<String, (String) -> Unit>?>(null) }
    var confirmDelete by remember { mutableStateOf<Pair<String, () -> Unit>?>(null) }

    val rows = all.filter { s ->
        (dayFilter == 0 || s.mask and TimeUtil.WEEKDAYS[dayFilter - 1].second != 0) &&
            (query.isBlank() || query.trim() in s.name || query.trim() in s.soundName)
    }

    Box(Modifier.fillMaxSize()) {
        Page(14.dp) {
            PageHeader("시간표", "세트마다 종 치는 시간을 정해요.")
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Select(sets.map { it.id to "${it.name}  (${it.count})" }, activeId, {
                    repo.setActiveSet(it); selected.clear(); changed(ctx)
                }, Modifier.weight(1f), onPage = true)
                Box {
                    IconBtn(Icons.Rounded.MoreVert, { setMenu = true }, bg = Color.White)
                    AppMenu(setMenu, { setMenu = false }, listOf(
                        MenuItem("새 세트 만들기") { askName = "새 세트 이름" to { n: String -> repo.setActiveSet(repo.createSet(n)); changed(ctx) } },
                        MenuItem("이 세트 이름 바꾸기") { askName = "세트 이름" to { n: String -> repo.renameSet(activeId, n); changed(ctx) } },
                        MenuItem("이 세트 복제") {
                            val cur = sets.firstOrNull { it.id == activeId }?.name ?: "세트"
                            repo.setActiveSet(repo.duplicateSet(activeId, "$cur 사본")); changed(ctx)
                            Toasts.show("세트를 복제했어요", "success")
                        },
                        MenuItem("이 세트 삭제", danger = true) {
                            if (sets.size <= 1) Toasts.show("세트가 하나뿐이라 지울 수 없어요", "warning")
                            else confirmDelete = "이 세트와 안의 일정을 모두 지울까요?" to {
                                repo.deleteSet(activeId); changed(ctx); Toasts.show("세트를 지웠어요")
                            }
                        },
                    ))
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Btn("일정 추가", { adding = true }, style = BtnStyle.Primary, icon = Icons.Rounded.Add)
                Field(query, { query = it }, Modifier.weight(1f), placeholder = "이름이나 종소리로 찾기", leading = Icons.Rounded.Search, onPage = true)
            }
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                (listOf("전체") + TimeUtil.WEEKDAYS.map { it.first }).forEachIndexed { i, d ->
                    Chip(d, dayFilter == i, { dayFilter = i })
                }
            }
            Card(padding = 8.dp) {
                if (all.isEmpty()) Empty("아직 일정이 없어요", "‘일정 추가’로 첫 종을 정해 보세요")
                else if (rows.isEmpty()) Empty("찾는 일정이 없어요")
                rows.forEachIndexed { i, s ->
                    if (i > 0) Box(Modifier.fillMaxWidth().padding(horizontal = 12.dp).height(1.dp).background(C.grey100))
                    ScheduleRow(s, s.id in selected,
                        onCheck = { if (s.id in selected) selected.remove(s.id) else selected.add(s.id) },
                        onClick = { if (selected.isNotEmpty()) { if (s.id in selected) selected.remove(s.id) else selected.add(s.id) } else editing = s },
                        onToggle = { on -> repo.setEnabled(listOf(s.id), on); changed(ctx) })
                }
            }
            Text("${rows.size}개 · 사용 중 ${rows.count { it.enabled }}개", style = text(13, color = C.grey500),
                modifier = Modifier.padding(start = 4.dp))
            if (selected.isNotEmpty()) Spacer(Modifier.height(72.dp))
        }

        // 고른 일정에 대한 일괄 작업 막대
        AnimatedVisibility(selected.isNotEmpty(), Modifier.align(Alignment.BottomCenter),
            enter = slideInVertically { it * 2 }, exit = slideOutVertically { it * 2 }) {
            Row(
                Modifier.padding(12.dp).clip(RoundedCornerShape(18.dp)).background(C.grey900).padding(horizontal = 14.dp, vertical = 10.dp)
                    .horizontalScroll(rememberScrollState()),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Text("${selected.size}개", style = text(14, FontWeight.Bold, Color.White))
                Spacer(Modifier.width(4.dp))
                BarBtn("모두") { selected.clear(); selected.addAll(rows.map { it.id }) }
                BarBtn("켜기") { repo.setEnabled(selected.toList(), true); changed(ctx) }
                BarBtn("끄기") { repo.setEnabled(selected.toList(), false); changed(ctx) }
                BarBtn("한 번에 바꾸기") { batch = true }
                BarBtn("복제") {
                    val n = repo.duplicateSchedules(selected.toList()).size; changed(ctx); Toasts.show("${n}개를 복제했어요", "success")
                }
                BarBtn("삭제", danger = true) {
                    confirmDelete = "고른 일정 ${selected.size}개를 지울까요?" to {
                        repo.deleteSchedules(selected.toList()); selected.clear(); changed(ctx); Toasts.show("지웠어요")
                    }
                }
                BarBtn("취소") { selected.clear() }
            }
        }
    }

    if (adding || editing != null) {
        ScheduleEditor(editing, onDismiss = { adding = false; editing = null }) { name, mask, hhmm, soundId, vol, en ->
            val e = editing
            if (e == null) repo.insertSchedule(activeId, name, mask, hhmm, soundId, vol, en)
            else repo.updateSchedule(e.id, name, mask, hhmm, soundId, vol, en)
            adding = false; editing = null
            changed(ctx)
            Toasts.show(if (e == null) "일정을 추가했어요" else "저장했어요", "success")
        }
    }
    if (batch) {
        BatchEditor(selected.size, sets.map { it.id to it.name }, onDismiss = { batch = false }) { ch ->
            repo.batchUpdate(selected.toList(), ch)
            batch = false
            changed(ctx)
            Toasts.show("${selected.size}개를 바꿨어요", "success")
        }
    }
    askName?.let { (title, ok) ->
        NameDialog(title, onDismiss = { askName = null }) { ok(it); askName = null }
    }
    confirmDelete?.let { (msg, ok) ->
        ConfirmDialog("지울까요?", msg, "삭제", ok, { confirmDelete = null })
    }
}

@Composable
private fun BarBtn(label: String, danger: Boolean = false, onClick: () -> Unit) {
    Text(label, style = text(14, FontWeight.SemiBold, if (danger) Color(0xFFFF8A93) else Color.White),
        modifier = Modifier.clip(RoundedCornerShape(10.dp)).background(Color.White.copy(alpha = 0.08f)).clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 8.dp))
}

@Composable
private fun ScheduleRow(s: Schedule, checked: Boolean, onCheck: () -> Unit, onClick: () -> Unit, onToggle: (Boolean) -> Unit) {
    val dim = !s.enabled
    val (part, hm) = TimeUtil.ampmParts(s.hhmm)
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (checked) C.accentSofter else Color.Transparent)
            .clickable(onClick = onClick).padding(horizontal = 10.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        CheckCircle(checked, onCheck)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.width(64.dp)) {
            Text(part, style = text(12, FontWeight.Medium, C.grey500))
            Text(hm, style = text(18, FontWeight.Bold, if (dim) C.grey400 else C.grey900))
        }
        Column(Modifier.weight(1f)) {
            Text(s.name, style = text(15, FontWeight.SemiBold, if (dim) C.grey400 else C.grey900), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text("${TimeUtil.maskText(s.mask)} · ${s.soundName}" + (s.volumeOverride?.let { " · ${(it * 100).toInt()}%" } ?: ""),
                style = text(13, color = if (dim) C.grey400 else C.grey500), maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Toggle(s.enabled, onToggle)
    }
}

@Composable
fun ScheduleEditor(
    data: Schedule?,
    onDismiss: () -> Unit,
    onSave: (name: String, mask: Int, hhmm: String, soundId: Long, volume: Double?, enabled: Boolean) -> Unit,
) {
    val ctx = LocalContext.current
    val sounds = remember { Repo(ctx).sounds() }
    var name by remember { mutableStateOf(data?.name ?: "") }
    var mask by remember { mutableStateOf(data?.mask ?: TimeUtil.WEEKDAYS_MASK) }
    var hour by remember { mutableStateOf(data?.hour ?: 9) }
    var minute by remember { mutableStateOf(data?.minute ?: 0) }
    var soundId by remember { mutableStateOf(data?.soundId ?: sounds.firstOrNull()?.id) }
    var useDefault by remember { mutableStateOf(data?.volumeOverride == null) }
    var volume by remember { mutableStateOf(((data?.volumeOverride ?: 1.0) * 100).toInt()) }
    var enabled by remember { mutableStateOf(data?.enabled ?: true) }
    val error = when {
        name.isBlank() -> "이름을 입력해 주세요."
        mask == 0 -> "요일을 하나 이상 골라 주세요."
        soundId == null -> "종소리를 골라 주세요."
        else -> null
    }
    AppSheet(if (data == null) "일정 추가" else "일정 수정", onDismiss, footer = {
        SheetButtons("저장", {
            onSave(name.trim(), mask, TimeUtil.hhmm(hour, minute), soundId!!, if (useDefault) null else volume / 100.0, enabled)
        }, onDismiss, okEnabled = error == null)
    }) {
        Column { Label("이름"); Field(name, { name = it }, Modifier.fillMaxWidth(), placeholder = "예) 1교시 시작") }
        Column { Label("요일"); DayChips(mask) { mask = it } }
        Column { Label("시간"); TimePicker(hour, minute) { h, m -> hour = h; minute = m } }
        Column {
            Label("종소리")
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Select(sounds.map { it.id to it.name }, soundId, { soundId = it }, Modifier.weight(1f))
                Btn("들어보기", {
                    val s = sounds.firstOrNull { it.id == soundId } ?: return@Btn
                    com.milky.mataf.core.Preview.play(ctx, Sounds.file(ctx, s.fileName).absolutePath,
                        if (useDefault) s.volume else volume / 100.0, s.name) { Toasts.show(it, "error") }
                })
            }
        }
        Column {
            Label("음량")
            ToggleRow("종소리 기본 음량 사용", checked = useDefault, onChange = { useDefault = it })
            if (!useDefault) VolumeSlider(volume) { volume = it }
        }
        ToggleRow("이 일정 사용", checked = enabled, onChange = { enabled = it })
        if (error != null && name.isNotEmpty()) Text(error, style = text(13, FontWeight.SemiBold, C.danger))
    }
}

@Composable
fun VolumeSlider(percent: Int, onChange: (Int) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        androidx.compose.material3.Slider(
            value = percent.toFloat(), onValueChange = { onChange(((it / 5).toInt() * 5)) }, valueRange = 0f..200f,
            modifier = Modifier.weight(1f),
            colors = androidx.compose.material3.SliderDefaults.colors(thumbColor = C.accent, activeTrackColor = C.accent,
                inactiveTrackColor = C.grey200),
        )
        Text("$percent%", style = text(15, FontWeight.SemiBold, C.grey700), modifier = Modifier.width(56.dp).padding(start = 8.dp))
    }
}

@Composable
private fun BatchEditor(count: Int, sets: List<Pair<Long, String>>, onDismiss: () -> Unit, onApply: (BatchChange) -> Unit) {
    val ctx = LocalContext.current
    val sounds = remember { Repo(ctx).sounds() }
    var useDays by remember { mutableStateOf(false) }
    var mask by remember { mutableStateOf(TimeUtil.WEEKDAYS_MASK) }
    var useShift by remember { mutableStateOf(false) }
    var shift by remember { mutableStateOf(5) }
    var useSound by remember { mutableStateOf(false) }
    var soundId by remember { mutableStateOf(sounds.firstOrNull()?.id) }
    var useVolume by remember { mutableStateOf(false) }
    var volume by remember { mutableStateOf(100) }
    var useName by remember { mutableStateOf(false) }
    var find by remember { mutableStateOf("") }
    var replace by remember { mutableStateOf("") }
    var useSet by remember { mutableStateOf(false) }
    var setId by remember { mutableStateOf(sets.firstOrNull()?.first) }
    AppSheet("${count}개 한 번에 바꾸기", onDismiss, subtitle = "켠 항목만 바꿔요.", footer = {
        SheetButtons("바꾸기", {
            onApply(BatchChange(
                mask = if (useDays) mask else null,
                shiftMinutes = if (useShift) shift else null,
                soundId = if (useSound) soundId else null,
                volume = if (useVolume) volume / 100.0 else null,
                nameFind = if (useName) find else null, nameReplace = if (useName) replace else null,
                setId = if (useSet) setId else null,
            ))
        }, onDismiss, okEnabled = useDays || useShift || useSound || useVolume || (useName && find.isNotEmpty()) || useSet)
    }) {
        Column {
            ToggleRow("요일 바꾸기", checked = useDays, onChange = { useDays = it })
            if (useDays) DayChips(mask) { mask = it }
        }
        Column {
            ToggleRow("시간 옮기기", "자정을 넘으면 요일도 함께 옮겨요", checked = useShift, onChange = { useShift = it })
            if (useShift) Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.horizontalScroll(rememberScrollState())) {
                listOf(-30, -10, -5, -1, 1, 5, 10, 30).forEach { d -> Chip(if (d > 0) "+${d}분" else "${d}분", shift == d, { shift = d }) }
            }
        }
        Column {
            ToggleRow("종소리 바꾸기", checked = useSound, onChange = { useSound = it })
            if (useSound) Select(sounds.map { it.id to it.name }, soundId, { soundId = it }, Modifier.fillMaxWidth())
        }
        Column {
            ToggleRow("음량 바꾸기", checked = useVolume, onChange = { useVolume = it })
            if (useVolume) VolumeSlider(volume) { volume = it }
        }
        Column {
            ToggleRow("이름 바꾸기", "찾을 글자를 바꿀 글자로", checked = useName, onChange = { useName = it })
            if (useName) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Field(find, { find = it }, Modifier.weight(1f), placeholder = "찾을 글자")
                Field(replace, { replace = it }, Modifier.weight(1f), placeholder = "바꿀 글자")
            }
        }
        if (sets.size > 1) Column {
            ToggleRow("다른 세트로 옮기기", checked = useSet, onChange = { useSet = it })
            if (useSet) Select(sets, setId, { setId = it }, Modifier.fillMaxWidth())
        }
    }
}

@Composable
fun NameDialog(title: String, initial: String = "", onDismiss: () -> Unit, onOk: (String) -> Unit) {
    var v by remember { mutableStateOf(initial) }
    AppSheet(title, onDismiss, footer = {
        SheetButtons("확인", { onOk(v.trim()) }, onDismiss, okEnabled = v.isNotBlank())
    }) {
        Field(v, { v = it }, Modifier.fillMaxWidth(), placeholder = "이름")
    }
}
