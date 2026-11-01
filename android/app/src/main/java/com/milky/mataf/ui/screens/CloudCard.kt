package com.milky.mataf.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.milky.mataf.core.AppEvents
import com.milky.mataf.core.Cloud
import com.milky.mataf.core.CloudModel
import com.milky.mataf.data.Repo
import com.milky.mataf.ui.components.AppSheet
import com.milky.mataf.ui.components.Btn
import com.milky.mataf.ui.components.BtnStyle
import com.milky.mataf.ui.components.Card
import com.milky.mataf.ui.components.ConfirmDialog
import com.milky.mataf.ui.components.Divider
import com.milky.mataf.ui.components.Field
import com.milky.mataf.ui.components.Label
import com.milky.mataf.ui.components.SettingRow
import com.milky.mataf.ui.components.SheetButtons
import com.milky.mataf.ui.components.Toasts
import com.milky.mataf.ui.components.ToggleRow
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** 설정 → 마고에듀 통합 클라우드 카드 */
@Composable
fun CloudCard() {
    val ctx = LocalContext.current
    val repo = remember { Repo(ctx) }
    val st by Cloud.status.collectAsState()
    val version by AppEvents.version.collectAsState()
    var ring by remember(version, st.loggedIn) { mutableStateOf(Cloud.ringsHere(repo)) }
    var login by remember { mutableStateOf(false) }
    var askLogout by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    if (login) CloudLoginSheet { login = false }
    if (askLogout) ConfirmDialog("클라우드에서 로그아웃할까요?",
        "이 기기의 시간표와 종소리는 그대로 남아요. 로그아웃하면 이 기기에서 다시 종이 울려요.", "로그아웃", {
            scope.launch {
                Cloud.logout()
                Toasts.show("로그아웃했어요. 이제 이 기기에서 종이 울려요")
            }
        }, { askLogout = false }, danger = false)

    Card {
        Text("마고에듀 통합 클라우드", style = text(17, FontWeight.Bold))
        Spacer(Modifier.height(6.dp))
        if (!st.loggedIn) {
            SettingRow("로그인", "같은 아이디로 연결한 PC·휴대폰과 시간표·종소리·기록을 실시간으로 맞춰요") {
                Btn("로그인", { login = true }, style = BtnStyle.Soft, small = true)
            }
            if (st.message.isNotEmpty()) Text(st.message, style = text(13, FontWeight.Medium, C.warning),
                modifier = Modifier.padding(bottom = 8.dp))
        } else {
            SettingRow(st.name.ifBlank { st.username }, "${st.username} · ${host(st.server)}") {
                Btn("로그아웃", { askLogout = true }, small = true)
            }
            Divider()
            SettingRow("동기화", syncText(st)) {
                Btn(if (st.syncing) "맞추는 중" else "지금 동기화", { Cloud.syncNow() }, small = true, enabled = !st.syncing)
            }
            if (st.message.isNotEmpty()) Text(st.message, style = text(13, FontWeight.Medium, C.warning),
                modifier = Modifier.padding(bottom = 8.dp))
        }
        if (st.loggedIn || !ring) {
            Divider()
            ToggleRow("이 기기에서 종 울리기",
                if (ring) "정해진 시각에 이 기기에서 울려요. 다른 기기에서 울려 달라고 하면 이 기기에서 울려요"
                else "이 기기에서는 울리지 않아요. ‘지금 울리기’를 누르면 종을 울리는 기기에 부탁해요",
                ring, { on ->
                    ring = on
                    Cloud.setRingsHere(ctx, on)
                    Toasts.show(if (on) "이 기기에서 종을 울릴게요" else "이 기기에서는 종을 울리지 않아요")
                })
        }
    }
}

private fun host(server: String): String = server.substringAfter("://").trimEnd('/')

private fun syncText(st: Cloud.Status): String {
    val conn = when (st.conn) {
        Cloud.Conn.ONLINE -> "실시간으로 연결돼 있어요"
        Cloud.Conn.CONNECTING -> "연결하고 있어요"
        Cloud.Conn.POLLING -> "연결돼 있어요 (자주 확인해서 맞춰요)"
        Cloud.Conn.OFFLINE -> "연결되지 않았어요. 다시 연결하고 있어요"
        Cloud.Conn.OFF -> ""
    }
    val last = if (st.lastSync > 0) {
        val t = Instant.ofEpochMilli(st.lastSync).atZone(ZoneId.systemDefault())
        val day = if (t.toLocalDate() == LocalDate.now()) "오늘" else t.format(DateTimeFormatter.ofPattern("M월 d일"))
        "마지막 동기화 $day ${t.format(DateTimeFormatter.ofPattern("HH:mm"))}"
    } else "아직 맞추지 않았어요"
    return listOf(conn, last).filter { it.isNotEmpty() }.joinToString(" · ")
}

@Composable
private fun CloudLoginSheet(onDismiss: () -> Unit) {
    val st = Cloud.status.value
    var server by remember { mutableStateOf(st.server.ifBlank { Cloud.DEFAULT_SERVER }) }
    var user by remember { mutableStateOf(st.username) }
    var pw by remember { mutableStateOf("") }
    var ring by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    val ok = server.isNotBlank() && user.isNotBlank() && pw.isNotEmpty() && !busy
    val go = {
        if (ok) {
            busy = true
            error = ""
            scope.launch {
                val err = Cloud.login(server, user, pw, ring)
                busy = false
                if (err == null) {
                    onDismiss()
                    Toasts.show(if (ring) "클라우드에 연결했어요" else "클라우드에 연결했어요. 이 기기에서는 종을 울리지 않아요", "success")
                } else {
                    error = err
                }
            }
        }
    }
    AppSheet("마고에듀 통합 클라우드", onDismiss, subtitle = "같은 아이디로 로그인한 PC·휴대폰과 시간표·종소리·기록을 맞춰요",
        footer = { SheetButtons(if (busy) "로그인하는 중" else "로그인", { go() }, onDismiss, okEnabled = ok) }) {
        Column { Label("서버 주소"); Field(server, { server = it }, Modifier.fillMaxWidth()) }
        Column { Label("아이디"); Field(user, { user = it }, Modifier.fillMaxWidth()) }
        Column { Label("비밀번호"); Field(pw, { pw = it }, Modifier.fillMaxWidth(), password = true, onDone = { go() }) }
        ToggleRow("이 기기에서 종 울리기",
            "교무실 PC처럼 종을 울리는 기기가 따로 있으면 꺼 두세요. 끄면 이 기기에서는 시간표를 보고 바꾸고, ‘지금 울리기’는 그 기기에 부탁해요",
            ring, { ring = it })
        if (error.isNotEmpty()) Text(error, style = text(14, FontWeight.Medium, C.danger))
    }
}

/** 처음 연결할 때 클라우드와 이 기기 시간표가 다르면 어느 쪽으로 맞출지 묻는다 (닫을 수 없음) */
@Composable
fun CloudChoiceDialog() {
    val choice by Cloud.choice.collectAsState()
    val c = choice ?: return
    var busy by remember(c) { mutableStateOf(false) }
    Dialog(onDismissRequest = {}, properties = DialogProperties(dismissOnBackPress = false, dismissOnClickOutside = false)) {
        Column(Modifier.widthIn(max = 440.dp).clip(RoundedCornerShape(24.dp)).background(Color.White).padding(24.dp)) {
            Text("클라우드 시간표와 이 기기 시간표가 달라요", style = text(19, FontWeight.Bold))
            Spacer(Modifier.height(10.dp))
            Text("어느 쪽으로 맞출까요?", style = text(15, color = C.grey700))
            Spacer(Modifier.height(14.dp))
            val by = listOf(c.cloudBy, CloudModel.parseInstant(c.cloudAt)?.atZone(ZoneId.systemDefault())
                ?.format(DateTimeFormatter.ofPattern("M월 d일 HH:mm")) ?: "").filter { it.isNotBlank() }.joinToString(" · ")
            Summary("클라우드", c.cloud, by)
            Spacer(Modifier.height(8.dp))
            Summary("이 기기", c.local, "")
            Spacer(Modifier.height(20.dp))
            Btn("클라우드 시간표 쓰기", { busy = true; Cloud.chooseCloud() }, Modifier.fillMaxWidth(), style = BtnStyle.Primary,
                large = true, enabled = !busy)
            Text("이 기기 시간표는 백업 파일로 남겨 둬요", style = text(12, color = C.grey500),
                modifier = Modifier.padding(top = 4.dp, bottom = 12.dp))
            Btn("이 기기 시간표로 바꾸기", { busy = true; Cloud.chooseLocal() }, Modifier.fillMaxWidth(), large = true, enabled = !busy)
            Text("클라우드와 연결된 다른 기기의 시간표도 이 기기 것으로 바뀌어요", style = text(12, color = C.grey500),
                modifier = Modifier.padding(top = 4.dp))
        }
    }
}

@Composable
private fun Summary(title: String, n: CloudModel.Counts, sub: String) {
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(C.grey50).padding(12.dp)) {
        Text(title, style = text(14, FontWeight.Bold))
        Text("일정 ${n.schedules}개 · 세트 ${n.sets}개 · 종소리 ${n.sounds}개", style = text(13, color = C.grey700))
        if (sub.isNotEmpty()) Text(sub, style = text(12, color = C.grey500))
    }
}
