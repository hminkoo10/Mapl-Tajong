package com.milky.mataf.ui.screens

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.milky.mataf.BuildConfig
import com.milky.mataf.ui.components.AppSheet
import com.milky.mataf.ui.components.Btn
import com.milky.mataf.ui.components.BtnStyle
import com.milky.mataf.ui.components.Divider
import com.milky.mataf.ui.components.Empty
import com.milky.mataf.ui.components.Pill
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text

/** 업데이트 기록: 앱에 함께 들어 있는 CHANGELOG.md (android/CHANGELOG.md) 를 버전별로 (데스크톱 changelog_dialog.py) */
object Changelog {
    data class Entry(val version: String, val date: String, val items: List<String>)

    private val HEAD = Regex("""^##\s*\[?(\d+(?:\.\d+){1,3})\]?\s*(?:[-–—·(]\s*([^)]*)\)?)?\s*$""")
    private val ITEM = Regex("""^[-*]\s+""")

    private fun clean(t: String) = t.replace(Regex("\\*\\*(.+?)\\*\\*"), "$1").replace(Regex("`([^`]+)`"), "$1")
        .replace(Regex("\\[([^\\]]+)\\]\\([^)]+\\)"), "$1").trim()

    /** 최신 버전이 먼저 */
    fun parse(md: String): List<Entry> {
        val out = mutableListOf<Triple<String, String, MutableList<String>>>()
        for (line in md.lines()) {
            val m = HEAD.matchEntire(line.trim())
            if (m != null) {
                out += Triple(m.groupValues[1], m.groupValues[2].trim(), mutableListOf())
                continue
            }
            val cur = out.lastOrNull() ?: continue
            val s = line.trim()
            if (ITEM.containsMatchIn(s)) cur.third += clean(s.replace(ITEM, ""))
            else if (s.isNotEmpty() && cur.third.isNotEmpty() && (line.startsWith("  ") || line.startsWith("\t"))) {
                cur.third[cur.third.lastIndex] = cur.third.last() + " " + clean(s)
            }
        }
        return out.map { Entry(it.first, it.second, it.third) }
    }

    fun load(ctx: Context): List<Entry> = try {
        parse(ctx.assets.open("CHANGELOG.md").use { String(it.readBytes(), Charsets.UTF_8) })
    } catch (_: Exception) {
        emptyList()
    }

    fun notesFor(ctx: Context, version: String): List<String> = load(ctx).firstOrNull { it.version == version }?.items.orEmpty()
}

@Composable
fun ChangelogSheet(onDismiss: () -> Unit, onlyVersion: String? = null, title: String? = null) {
    val ctx = LocalContext.current
    val entries = remember {
        Changelog.load(ctx).let { all -> if (onlyVersion == null) all else all.filter { it.version == onlyVersion }.ifEmpty { all.take(1) } }
    }
    AppSheet(title ?: "업데이트 기록", onDismiss, subtitle = if (onlyVersion == null) "버전마다 무엇이 바뀌었는지 볼 수 있어요." else "",
        footer = { Btn("확인", onDismiss, Modifier.fillMaxWidth(), style = BtnStyle.Primary, large = true) }) {
        if (entries.isEmpty()) Empty("기록을 찾지 못했어요.")
        entries.forEachIndexed { i, e ->
            if (i > 0) Divider()
            val current = e.version == BuildConfig.VERSION_NAME
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("버전 ${e.version}", style = text(17, FontWeight.Bold))
                    if (current) {
                        Spacer(Modifier.width(8.dp))
                        Pill("지금 쓰는 버전")
                    }
                    Spacer(Modifier.weight(1f))
                    if (e.date.isNotEmpty()) Text(e.date, style = text(13, color = C.grey500))
                }
                e.items.ifEmpty { listOf("더 안정적으로 다듬었어요.") }.forEach { item ->
                    Row {
                        Text("•", style = text(15, color = if (current) C.accent else C.grey400), modifier = Modifier.width(16.dp))
                        Text(item, style = text(15, color = C.grey700), modifier = Modifier.padding(end = 4.dp))
                    }
                }
            }
        }
    }
}
