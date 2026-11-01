package com.milky.mataf.ui.screens

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.milky.mataf.R
import com.milky.mataf.core.AppEvents
import com.milky.mataf.core.Cloud
import com.milky.mataf.core.CloudModel
import com.milky.mataf.data.Repo
import com.milky.mataf.ui.components.Btn
import com.milky.mataf.ui.components.BtnStyle
import com.milky.mataf.ui.components.Card
import com.milky.mataf.ui.components.ConfirmDialog
import com.milky.mataf.ui.components.Divider
import com.milky.mataf.ui.components.Field
import com.milky.mataf.ui.components.Label
import com.milky.mataf.ui.components.SettingRow
import com.milky.mataf.ui.components.ToastHost
import com.milky.mataf.ui.components.Toasts
import com.milky.mataf.ui.components.ToggleRow
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** 설정 → 마고에듀 통합 클라우드 카드 (앱은 로그인해야 쓸 수 있으므로 늘 로그인한 상태) */
@Composable
fun CloudCard() {
    val ctx = LocalContext.current
    val repo = remember { Repo(ctx) }
    val st by Cloud.status.collectAsState()
    val version by AppEvents.version.collectAsState()
    var ring by remember(version, st.loggedIn) { mutableStateOf(Cloud.ringsHere(repo)) }
    var askLogout by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    if (askLogout) ConfirmDialog("클라우드에서 로그아웃할까요?",
        "다시 로그인할 때까지 이 기기에서 종이 울리지 않고 앱도 쓸 수 없어요. 이 기기의 시간표와 종소리는 그대로 남아요.", "로그아웃", {
            scope.launch(NonCancellable) { Cloud.logout() }
        }, { askLogout = false }, danger = true)

    Card {
        Text("마고에듀 통합 클라우드", style = text(17, FontWeight.Bold))
        Spacer(Modifier.height(6.dp))
        SettingRow(st.name.ifBlank { st.username }, "${st.username} · ${host(st.server)}") {
            Btn("로그아웃", { askLogout = true }, small = true)
        }
        Divider()
        SettingRow("동기화", syncText(st)) {
            Btn(if (st.syncing) "맞추는 중" else "지금 동기화", { Cloud.syncNow() }, small = true, enabled = !st.syncing)
        }
        if (st.message.isNotEmpty()) Text(st.message, style = text(13, FontWeight.Medium, C.warning),
            modifier = Modifier.padding(bottom = 8.dp))
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

/**
 * 로그인하지 않았을 때 앱 대신 보여 주는 화면. 마고에듀 통합 클라우드 계정으로 로그인해야 앱을 쓸 수 있다.
 * 로그인한 뒤에는 인터넷이 없어도 그대로 쓰고 종도 울린다.
 */
@Composable
fun CloudGate() {
    val ctx = LocalContext.current
    val repo = remember { Repo(ctx) }
    val st by Cloud.status.collectAsState()
    var server by remember { mutableStateOf(st.server.ifBlank { Cloud.DEFAULT_SERVER }) }
    var user by remember { mutableStateOf(st.username) }
    var pw by remember { mutableStateOf("") }
    var ring by remember { mutableStateOf(Cloud.ringChoiceForLogin(repo)) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    // 로그인한 적 없이 이 기기에서 쓰던 시간표가 있는지 (처음 설치한 그대로가 아니면)
    val hasLocal = remember {
        st.username.isBlank() && runCatching { !CloudModel.isDefaultConfig(Cloud.buildConfig(repo)) }.getOrDefault(false)
    }
    val scope = rememberCoroutineScope()
    val ok = server.isNotBlank() && user.isNotBlank() && pw.isNotEmpty() && !busy
    val go = {
        if (ok) {
            busy = true
            error = ""
            // 로그인되면 이 화면이 바로 사라지므로 끝까지 마치게 한다
            scope.launch(NonCancellable) {
                val err = Cloud.login(server, user, pw, ring)
                if (err == null) {
                    Toasts.show(if (ring) "로그인했어요. 이 기기에서 종을 울려요" else "로그인했어요. 이 기기에서는 종을 울리지 않아요", "success")
                } else {
                    busy = false
                    error = err
                }
            }
        }
    }

    Box(Modifier.fillMaxSize().background(C.bg).statusBarsPadding().navigationBarsPadding().imePadding()) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally) {
            Column(Modifier.widthIn(max = 440.dp).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Box(Modifier.size(64.dp).clip(RoundedCornerShape(18.dp)).background(Color.White), contentAlignment = Alignment.Center) {
                    Image(painterResource(R.mipmap.ic_launcher_foreground), null, Modifier.requiredSize(96.dp))
                }
                Column {
                    Text("마고 타종", style = text(26, FontWeight.ExtraBold))
                    Spacer(Modifier.height(6.dp))
                    Text("마고에듀 통합 클라우드 아이디로 로그인해 주세요", style = text(16, FontWeight.SemiBold, C.grey700))
                }
                Text("마고 타종은 마고에듀 통합 클라우드 계정으로 써요. 같은 아이디로 로그인한 PC·휴대폰과 시간표·종소리·기록이 저절로 맞춰져요. " +
                    "한 번 로그인하면 인터넷이 끊겨도 이 기기에서 종은 그대로 울려요.", style = text(14, color = C.grey600))
                if (hasLocal) Text("이 기기에서 쓰던 시간표와 종소리는 그대로 있어요. 로그인한 뒤 클라우드 것과 다르면 어느 쪽을 쓸지 골라요.",
                    style = text(14, color = C.grey600))
                if (st.message.isNotEmpty()) Text(st.message, style = text(14, FontWeight.Medium, C.warning))
                Card {
                    Label("아이디")
                    Field(user, { user = it }, Modifier.fillMaxWidth())
                    Spacer(Modifier.height(14.dp))
                    Label("비밀번호")
                    Field(pw, { pw = it }, Modifier.fillMaxWidth(), password = true, onDone = { go() })
                    Spacer(Modifier.height(14.dp))
                    Label("서버 주소")
                    Field(server, { server = it }, Modifier.fillMaxWidth())
                    Spacer(Modifier.height(4.dp))
                    ToggleRow("이 기기에서 종 울리기",
                        "교무실 PC처럼 종을 울리는 기기가 따로 있으면 꺼 두세요. 끄면 이 기기에서는 시간표를 보고 바꾸고, ‘지금 울리기’는 그 기기에 부탁해요",
                        ring, { ring = it })
                    if (error.isNotEmpty()) Text(error, style = text(14, FontWeight.Medium, C.danger), modifier = Modifier.padding(bottom = 8.dp))
                    Spacer(Modifier.height(8.dp))
                    Btn(if (busy) "로그인하는 중" else "로그인", { go() }, Modifier.fillMaxWidth(), style = BtnStyle.Primary, large = true, enabled = ok)
                }
                Text("아이디가 없으면 원장님이나 운영자에게 받아 주세요.", style = text(13, color = C.grey500))
            }
        }
        ToastHost(Modifier.align(Alignment.BottomCenter).padding(bottom = 8.dp))
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
