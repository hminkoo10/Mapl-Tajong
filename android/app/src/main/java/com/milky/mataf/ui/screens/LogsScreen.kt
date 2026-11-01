package com.milky.mataf.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.FileDownload
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.milky.mataf.core.AppEvents
import com.milky.mataf.data.Repo
import com.milky.mataf.data.TimeUtil
import com.milky.mataf.ui.components.Btn
import com.milky.mataf.ui.components.BtnStyle
import com.milky.mataf.ui.components.Card
import com.milky.mataf.ui.components.Empty
import com.milky.mataf.ui.components.Page
import com.milky.mataf.ui.components.PageHeader
import com.milky.mataf.ui.components.Pill
import com.milky.mataf.ui.components.Segmented
import com.milky.mataf.ui.components.Select
import com.milky.mataf.ui.components.Toasts
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text
import java.time.LocalDate

val RESULT_LABELS = mapOf("PLAYED" to "울림", "SKIPPED" to "건너뜀", "FAILED" to "실패", "MISSED" to "놓침")

/** 기록 설명: 'forced' = 미리 울림, 'forced · 원장님 폰' = 다른 기기의 요청으로 울림 */
fun detailText(d: String): String = when {
    d == "forced" -> "미리 울림"
    d.startsWith("forced · ") -> "${d.removePrefix("forced · ")} 요청"
    else -> d
}

@Composable
fun LogsScreen() {
    val ctx = LocalContext.current
    val repo = remember { Repo(ctx) }
    val version by AppEvents.version.collectAsState()
    var range by remember { mutableStateOf(0) }
    var result by remember { mutableStateOf<String?>(null) }
    val today = LocalDate.now()
    val from = when (range) { 0 -> today; 1 -> today.minusDays(6); else -> today.minusDays(29) }
    val rows = remember(version, range, result) { repo.logs(from, today, result) }
    val exporter = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("text/csv")) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        try {
            ctx.contentResolver.openOutputStream(uri)?.bufferedWriter(Charsets.UTF_8)?.use { w ->
                w.write("﻿날짜,시각,일정,종소리,결과,메모,기기\n")
                rows.forEach { r ->
                    val (d, t) = r.at.split(" ").let { it[0] to it.getOrElse(1) { "" } }
                    w.write(listOf(d, t, r.scheduleName, r.soundName, RESULT_LABELS[r.result] ?: r.result, r.detail, r.device.ifEmpty { "이 기기" })
                        .joinToString(",") { "\"" + it.replace("\"", "\"\"") + "\"" } + "\n")
                }
            }
            Toasts.show("${rows.size}개를 저장했어요", "success")
        } catch (e: Exception) {
            Toasts.show("저장하지 못했어요", "error")
        }
    }

    Page(14.dp) {
        PageHeader("기록", "종이 언제 울렸는지 볼 수 있어요.")
        Segmented(listOf("오늘", "7일", "30일"), range, { range = it }, Modifier.fillMaxWidth(), onPage = true)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Select(listOf<Pair<String?, String>>(null to "모든 결과") + RESULT_LABELS.map { it.key to it.value }, result,
                { result = it }, Modifier.weight(1f), onPage = true)
            Btn("엑셀로", { exporter.launch("타종기록_${today.format(java.time.format.DateTimeFormatter.BASIC_ISO_DATE)}.csv") },
                style = BtnStyle.White, icon = Icons.Rounded.FileDownload, enabled = rows.isNotEmpty())
        }
        val merged = rows.any { it.device.isNotEmpty() }
        Card(padding = 8.dp) {
            if (rows.isEmpty()) Empty("기록이 없어요")
            var lastDate = ""
            rows.forEach { r ->
                val d = r.at.substringBefore(" ")
                if (d != lastDate) {
                    lastDate = d
                    Text(if (d == today.toString()) "오늘" else d, style = text(13, FontWeight.SemiBold, C.grey500),
                        modifier = Modifier.padding(start = 10.dp, top = 12.dp, bottom = 4.dp))
                }
                Row(Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(TimeUtil.ampm(r.at.substringAfter(" ").take(5)), style = text(14, FontWeight.SemiBold, C.grey700),
                        modifier = Modifier.width(84.dp))
                    Column(Modifier.weight(1f)) {
                        Text(r.scheduleName.ifEmpty { "직접 울림" }, style = text(15, FontWeight.Medium), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        val sub = listOf(r.soundName, detailText(r.detail), if (merged) r.device.ifEmpty { "이 기기" } else "")
                            .filter { it.isNotEmpty() }.joinToString(" · ")
                        Text(sub, style = text(12, color = C.grey500), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                    val (fg, bg) = when (r.result) {
                        "PLAYED" -> C.success to C.successSoft
                        "SKIPPED" -> C.warning to C.warningSoft
                        else -> C.danger to C.dangerSoft
                    }
                    Pill(RESULT_LABELS[r.result] ?: r.result, fg, bg)
                }
                Box(Modifier.fillMaxWidth().padding(horizontal = 10.dp).height(1.dp).background(C.grey50))
            }
        }
    }
}
