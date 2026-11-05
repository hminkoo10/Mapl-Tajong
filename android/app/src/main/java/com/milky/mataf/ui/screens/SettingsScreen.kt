package com.milky.mataf.ui.screens

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.DocumentsContract
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.milky.mataf.BuildConfig
import com.milky.mataf.core.Alarms
import com.milky.mataf.core.AppEvents
import com.milky.mataf.core.Backup
import com.milky.mataf.core.BellService
import com.milky.mataf.core.Cloud
import com.milky.mataf.core.GoogleLogin
import com.milky.mataf.core.Preview
import com.milky.mataf.core.Updater
import com.milky.mataf.core.Updates
import com.milky.mataf.core.Weather
import com.milky.mataf.core.helpUrl
import com.milky.mataf.data.Repo
import com.milky.mataf.ui.components.Btn
import com.milky.mataf.ui.components.BtnStyle
import com.milky.mataf.ui.components.Card
import com.milky.mataf.ui.components.ConfirmDialog
import com.milky.mataf.ui.components.Divider
import com.milky.mataf.ui.components.Page
import com.milky.mataf.ui.components.PageHeader
import com.milky.mataf.ui.components.Segmented
import com.milky.mataf.ui.components.SettingRow
import com.milky.mataf.ui.components.Toasts
import com.milky.mataf.ui.components.ToggleRow
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.LocalDate
import java.time.format.DateTimeFormatter

/** 설정 화면. 추가 카드(날씨 지역·백업·업데이트 등)는 extra 로 넣는다. */
@Composable
fun SettingsScreen(extra: @Composable () -> Unit = {}) {
    val ctx = LocalContext.current
    val repo = remember { Repo(ctx) }
    val version by AppEvents.version.collectAsState()
    var tick by remember { mutableStateOf(0) }
    val refresh = { tick++ }
    val notifLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { refresh() }

    val exactOk = remember(version, tick) { Alarms.canExact(ctx) }
    val notifOk = remember(tick) {
        Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
    }
    val batteryOk = remember(tick) {
        ctx.getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(ctx.packageName)
    }
    var weatherOn by remember { mutableStateOf(repo.setting("weather_on", "1") != "0") }
    var theme by remember { mutableStateOf(if (repo.setting("fs_theme", "dark") == "light") 1 else 0) }
    var placeName by remember { mutableStateOf(Weather.place(repo).name) }
    var picking by remember { mutableStateOf(false) }
    if (picking) PlaceSheet(onPicked = {
        placeName = it
        Toasts.show("$it 날씨를 보여 줄게요", "success")
    }, onDismiss = { picking = false })

    // ---------- 백업 ----------
    val scope = rememberCoroutineScope()
    var notice by remember { mutableStateOf<Pair<String, String>?>(null) }
    var restore by remember { mutableStateOf<Pair<Uri, Backup.Manifest>?>(null) }
    var history by remember { mutableStateOf(false) }
    notice?.let { (t, m) -> ConfirmDialog(t, m, "확인", {}, { notice = null }, danger = false, cancelLabel = null) }
    if (history) ChangelogSheet(onDismiss = { history = false })

    val backupLauncher = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            try {
                val m = withContext(Dispatchers.IO) {
                    ctx.contentResolver.openOutputStream(uri)!!.use { Backup.export(ctx, it) }
                }
                Toasts.show("백업했어요 · 일정 ${m.counts["schedules"] ?: 0}개, 종소리 ${m.counts["sounds"] ?: 0}개", "success")
            } catch (e: Exception) {
                withContext(Dispatchers.IO) { runCatching { DocumentsContract.deleteDocument(ctx.contentResolver, uri) } }
                notice = "백업하지 못했어요" to (e.message ?: e.toString())
            }
        }
    }
    val restoreLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            try {
                val m = withContext(Dispatchers.IO) { ctx.contentResolver.openInputStream(uri)!!.use { Backup.readManifest(it) } }
                restore = uri to m
            } catch (e: Exception) {
                notice = "불러올 수 없어요" to (e.message ?: e.toString())
            }
        }
    }
    val csvLauncher = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("text/csv")) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            try {
                val n = withContext(Dispatchers.IO) {
                    ctx.contentResolver.openOutputStream(uri)!!.use { Backup.exportSchedulesCsv(ctx, it) }
                }
                Toasts.show("일정 ${n}개를 저장했어요", "success")
            } catch (e: Exception) {
                withContext(Dispatchers.IO) { runCatching { DocumentsContract.deleteDocument(ctx.contentResolver, uri) } }
                notice = "내보내지 못했어요" to (e.message ?: e.toString())
            }
        }
    }
    restore?.let { (uri, m) ->
        val c = m.counts
        ConfirmDialog("백업을 불러올까요?",
            "${m.createdAt.take(16)}에 만든 백업이에요.\n" +
                "일정 ${c["schedules"] ?: 0}개 · 세트 ${c["schedule_sets"] ?: 0}개 · 종소리 ${c["sounds"] ?: 0}개\n\n" +
                "지금 시간표와 종소리는 백업 내용으로 바뀌어요. 기록은 그대로예요.",
            "불러오기", {
                BellService.stop(ctx)
                Preview.stop()
                scope.launch {
                    try {
                        withContext(Dispatchers.IO) { ctx.contentResolver.openInputStream(uri)!!.use { Backup.import(ctx, it) } }
                        Toasts.show("백업을 불러왔어요", "success")
                    } catch (e: Exception) {
                        notice = "불러오지 못했어요" to (e.message ?: e.toString())
                    }
                }
            }, { restore = null }, danger = false)
    }

    // ---------- 업데이트 ----------
    val upd by Updates.state.collectAsState()
    var autoUpdate by remember { mutableStateOf(Updates.auto(repo)) }
    val updBusy = upd.state in setOf("checking", "downloading", "installing")
    val hasUpdate = upd.state in setOf("available", "ready") && upd.info != null

    // ---------- 구글 로그인 ----------
    var googleAt by remember { mutableStateOf(GoogleLogin.loggedInAt(ctx).takeIf { GoogleLogin.isLoggedIn(ctx) }) }
    var loggingIn by remember { mutableStateOf(false) }
    var askLogout by remember { mutableStateOf(false) }
    if (loggingIn) GoogleLoginScreen { ok ->
        loggingIn = false
        if (ok) {
            googleAt = GoogleLogin.loggedInAt(ctx)
            Toasts.show("구글 로그인했어요", "success")
        }
    }
    if (askLogout) ConfirmDialog("구글 로그아웃할까요?", "이 기기에 저장한 로그인 정보를 지워요.", "로그아웃", {
        GoogleLogin.logout(ctx)
        googleAt = null
        Toasts.show("로그아웃했어요")
    }, { askLogout = false }, danger = false)

    Page(16.dp) {
        PageHeader("설정")
        Card {
            Text("정확히 울리게 하기", style = text(17, FontWeight.Bold))
            Spacer(Modifier.height(6.dp))
            SettingRow("알람 및 리마인더", if (exactOk) " " else "정시에 울리려면 허용하세요.") {
                if (!exactOk) Btn("허용하기", { Alarms.openExactSettings(ctx); refresh() }, style = BtnStyle.Soft, small = true)
                else Text("허용됨", style = text(14, FontWeight.SemiBold, C.success))
            }
            Divider()
            SettingRow("배터리 사용량 최적화 제외", if (batteryOk) "절전 중에도 울려요." else "절전 중 타종에 필요한 설정이에요.") {
                if (!batteryOk) Btn("제외하기", {
                    try {
                        ctx.startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${ctx.packageName}")))
                    } catch (e: Exception) {
                        ctx.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                    }
                    refresh()
                }, style = BtnStyle.Soft, small = true)
                else Text("제외됨", style = text(14, FontWeight.SemiBold, C.success))
            }
            Divider()
            SettingRow("알림", if (notifOk) "알림에서 울리는 종을 멈추세요." else "알림에서 종을 멈추려면 허용하세요.") {
                if (!notifOk && Build.VERSION.SDK_INT >= 33) Btn("허용하기", { notifLauncher.launch(Manifest.permission.POST_NOTIFICATIONS) },
                    style = BtnStyle.Soft, small = true)
                else Text("허용됨", style = text(14, FontWeight.SemiBold, C.success))
            }
        }
        CloudCard()
        Card {
            Text("전체화면 시계", style = text(17, FontWeight.Bold))
            Spacer(Modifier.height(6.dp))
            ToggleRow("날씨 예보 보이기", " ", weatherOn, {
                weatherOn = it; repo.setSetting("weather_on", if (it) "1" else "0")
            })
            Divider()
            SettingRow("날씨 지역", "$placeName") {
                Btn("바꾸기", { picking = true }, small = true, enabled = weatherOn)
            }
            Divider()
            SettingRow("화면 밝기", " ") {
                Segmented(listOf("어둡게", "밝게"), theme, { theme = it; repo.setSetting("fs_theme", if (it == 1) "light" else "dark") },
                    Modifier.width(150.dp))
            }
        }
        Card {
            Text("백업", style = text(17, FontWeight.Bold))
            Spacer(Modifier.height(6.dp))
            SettingRow("백업 파일 만들기", "시간표·세트·종소리를 함께 저장해요.") {
                Btn("백업하기", { backupLauncher.launch(Backup.defaultBackupName()) }, small = true)
            }
            Divider()
            SettingRow("백업 불러오기", " ") {
                Btn("불러오기", {
                    restoreLauncher.launch(arrayOf("application/zip", "application/x-zip-compressed", "application/octet-stream"))
                }, small = true)
            }
            Divider()
            SettingRow("시간표를 엑셀로", " ") {
                Btn("내보내기", { csvLauncher.launch("시간표_${LocalDate.now().format(DateTimeFormatter.ofPattern("yyyyMMdd"))}.csv") },
                    small = true)
            }
        }
        Card {
            Text("업데이트", style = text(17, FontWeight.Bold))
            Spacer(Modifier.height(6.dp))
            SettingRow("버전 ${BuildConfig.VERSION_NAME}", Updates.statusText(upd, autoUpdate)) {
                Btn(if (hasUpdate) "업데이트" else "새 버전 확인", {
                    if (hasUpdate) Updates.installNow(ctx) else Updates.check(ctx, manual = true)
                }, style = if (hasUpdate) BtnStyle.Primary else BtnStyle.Secondary, small = true, enabled = !updBusy)
            }
            if (upd.state == "downloading") {
                LinearProgressIndicator({ upd.progress }, Modifier.fillMaxWidth().padding(bottom = 8.dp), color = C.accent,
                    trackColor = C.grey100)
            }
            Divider()
            ToggleRow("자동으로 업데이트", "다음 종까지 ${Updates.SAFE_GAP_MIN}분 넘게 남으면 설치해요.",
                autoUpdate, { autoUpdate = it; Updates.setAuto(ctx, it) })
            Divider()
            SettingRow("업데이트 기록", " ") {
                Btn("보기", { history = true }, small = true)
            }
            val notes = upd.info?.notes.orEmpty()
            if (notes.isNotBlank()) {
                Divider()
                SettingRow("새 버전에서 바뀌는 점") {
                    Btn("보기", { notice = "${upd.info?.version}에서 새로워진 점" to Updater.notesToText(notes).ifEmpty { "-" } }, small = true)
                }
            }
        }
        extra()
        Card {
            Text("정보", style = text(17, FontWeight.Bold))
            Spacer(Modifier.height(6.dp))
            SettingRow("사용 설명서") {
                Btn("열기", {
                    try {
                        ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(helpUrl(Cloud.status.value.server))))
                    } catch (e: Exception) {
                        Toasts.show("브라우저를 열 수 없어요", "warning")
                    }
                }, small = true)
            }
            Divider()
            val at = googleAt
            SettingRow("YouTube 구글 로그인",
                if (at != null) "로그인됨 · ${java.time.Instant.ofEpochMilli(at).atZone(java.time.ZoneId.systemDefault())
                    .format(DateTimeFormatter.ofPattern("yyyy년 MM월 dd일"))}"
                else "YouTube에서 로그인을 요구할 때 써요.") {
                Btn(if (at != null) "로그아웃" else "로그인", { if (at != null) askLogout = true else loggingIn = true }, small = true)
            }
            Divider()
            SettingRow("만든 사람") { Text("구현민", style = text(14, color = C.grey700)) }
        }
    }
}
