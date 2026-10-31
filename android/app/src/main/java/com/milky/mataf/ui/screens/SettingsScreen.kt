package com.milky.mataf.ui.screens

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.milky.mataf.BuildConfig
import com.milky.mataf.core.Alarms
import com.milky.mataf.core.AppEvents
import com.milky.mataf.data.Repo
import com.milky.mataf.ui.components.Btn
import com.milky.mataf.ui.components.BtnStyle
import com.milky.mataf.ui.components.Card
import com.milky.mataf.ui.components.Divider
import com.milky.mataf.ui.components.Page
import com.milky.mataf.ui.components.PageHeader
import com.milky.mataf.ui.components.Segmented
import com.milky.mataf.ui.components.SettingRow
import com.milky.mataf.ui.components.ToggleRow
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text

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

    Page(16.dp) {
        PageHeader("설정")
        Card {
            Text("정확히 울리게 하기", style = text(17, FontWeight.Bold))
            Spacer(Modifier.height(6.dp))
            SettingRow("알람 및 리마인더", if (exactOk) "허용됨 · 정해진 시각에 정확히 울려요" else "허용해야 정확한 시각에 울려요") {
                if (!exactOk) Btn("허용하기", { Alarms.openExactSettings(ctx); refresh() }, style = BtnStyle.Soft, small = true)
                else Text("허용됨", style = text(14, FontWeight.SemiBold, C.success))
            }
            Divider()
            SettingRow("배터리 사용량 최적화 제외", if (batteryOk) "제외됨 · 절전 중에도 울려요" else "제외해야 절전 모드에서도 놓치지 않아요") {
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
            SettingRow("알림", if (notifOk) "종이 울리는 동안 알림에 ‘정지’ 버튼이 보여요" else "허용하면 알림에서 바로 멈출 수 있어요") {
                if (!notifOk && Build.VERSION.SDK_INT >= 33) Btn("허용하기", { notifLauncher.launch(Manifest.permission.POST_NOTIFICATIONS) },
                    style = BtnStyle.Soft, small = true)
                else Text("허용됨", style = text(14, FontWeight.SemiBold, C.success))
            }
        }
        Card {
            Text("전체화면 시계", style = text(17, FontWeight.Bold))
            Spacer(Modifier.height(6.dp))
            ToggleRow("날씨 예보 보이기", "지금 날씨와 앞으로 몇 시간의 예보를 함께 보여 줘요", weatherOn, {
                weatherOn = it; repo.setSetting("weather_on", if (it) "1" else "0")
            })
            Divider()
            SettingRow("화면 밝기", "시계 화면에서도 바꿀 수 있어요") {
                Segmented(listOf("어둡게", "밝게"), theme, { theme = it; repo.setSetting("fs_theme", if (it == 1) "light" else "dark") },
                    Modifier.width(150.dp))
            }
        }
        extra()
        Card {
            Text("정보", style = text(17, FontWeight.Bold))
            Spacer(Modifier.height(6.dp))
            SettingRow("버전") { Text(BuildConfig.VERSION_NAME, style = text(14, color = C.grey700)) }
            Divider()
            SettingRow("만든 사람") { Text("구현민", style = text(14, color = C.grey700)) }
        }
    }
}
