package com.milky.mataf.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.milky.mataf.core.FoundPlace
import com.milky.mataf.core.Weather
import com.milky.mataf.data.Repo
import com.milky.mataf.ui.components.AppSheet
import com.milky.mataf.ui.components.Btn
import com.milky.mataf.ui.components.BtnStyle
import com.milky.mataf.ui.components.Chip
import com.milky.mataf.ui.components.Field
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.Locale

/** 날씨 지역 고르기: 동네·주소로 찾거나 자주 쓰는 도시에서 고른다 (데스크톱 place_dialog.py). 고르면 저장하고 onPicked */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PlaceSheet(onPicked: (String) -> Unit, onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    val repo = remember { Repo(ctx) }
    val scope = rememberCoroutineScope()
    val focus = LocalFocusManager.current
    val current = remember { Weather.place(repo).name }
    var query by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<FoundPlace>>(emptyList()) }
    var searching by remember { mutableStateOf(false) }
    var state by remember { mutableStateOf("") }
    var seq by remember { mutableIntStateOf(0) }

    fun choose(p: FoundPlace) {
        Weather.savePlace(repo, p)
        onDismiss()
        onPicked(p.name)
    }

    fun search() {
        val q = query.trim()
        if (q.isEmpty() || searching) return
        focus.clearFocus()
        val my = ++seq
        searching = true
        state = "찾고 있어요"
        scope.launch {
            try {
                val found = withContext(Dispatchers.IO) { Weather.searchPlaces(ctx, q) }
                if (my != seq) return@launch
                results = found
                val first = found.firstOrNull()
                state = when {
                    first == null -> "찾는 곳이 없어요. 동네(○○동)나 시·구 이름, 또는 도로명 주소로 찾아 보세요."
                    first.exact -> "주소를 건물까지 찾았어요. 눌러서 고르세요."
                    else -> (if (first.approx != null) "건물 번호까지는 못 찾아서 ‘${first.approx}’ 근처로 찾았어요. " else "") +
                        "${found.size}곳을 찾았어요. 눌러서 고르세요."
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (my == seq) state = "지금은 찾을 수 없어요. 인터넷 연결을 확인하거나 아래 도시에서 골라 주세요."
            } finally {
                if (my == seq) searching = false
            }
        }
    }

    AppSheet("날씨 지역 고르기", onDismiss, subtitle = "동네·주소로 찾거나, 아래 도시에서 골라 주세요.",
        footer = { Btn("닫기", onDismiss, Modifier.fillMaxWidth(), large = true) }) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("지금 지역: $current", style = text(14, color = C.grey600))
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Field(query, { query = it }, Modifier.weight(1f), placeholder = "예) 대치동 · 테헤란로 152 · 37.50, 127.06",
                    leading = Icons.Rounded.Search, onDone = ::search)
                Btn("찾기", ::search, style = BtnStyle.Primary, enabled = !searching && query.isNotBlank())
            }
        }
        if (results.isNotEmpty()) {
            Column {
                Text("찾은 곳", style = text(13, FontWeight.SemiBold, C.grey500), modifier = Modifier.padding(bottom = 4.dp))
                results.forEach { PlaceRow(it) { choose(it) } }
            }
        }
        val t = query.trim()
        val cities = Weather.CITIES.filter { t.isEmpty() || t in it.name || it.name in t }
        if (cities.isNotEmpty()) {
            Column {
                Text("자주 쓰는 도시", style = text(13, FontWeight.SemiBold, C.grey500), modifier = Modifier.padding(bottom = 8.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    cities.forEach { c -> Chip(c.name, false, { choose(FoundPlace(c.name, c.name, c.lat, c.lon)) }) }
                }
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (state.isNotEmpty()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (searching) {
                        CircularProgressIndicator(color = C.accent, strokeWidth = 2.dp, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(8.dp))
                    }
                    Text(state, style = text(13, color = C.grey600))
                }
            }
            Text(Weather.GEO_CREDIT, style = text(12, color = C.grey400))
        }
    }
}

@Composable
private fun PlaceRow(p: FoundPlace, onClick: () -> Unit) {
    val rest = p.label.removePrefix(p.name).trim(' ', '(', ')')
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable(onClick = onClick).padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Rounded.Search, null, tint = C.grey400, modifier = Modifier.size(16.dp))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(p.name, style = text(15, FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis)
            if (rest.isNotEmpty()) Text(rest, style = text(13, color = C.grey500), maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Spacer(Modifier.width(8.dp))
        Text("%.4f, %.4f".format(Locale.US, p.lat, p.lon), style = text(12, FontWeight.Medium, C.grey400))
    }
}
