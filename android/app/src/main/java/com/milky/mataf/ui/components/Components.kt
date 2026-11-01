package com.milky.mataf.ui.components

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.KeyboardArrowDown
import androidx.compose.material.icons.rounded.KeyboardArrowUp
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.milky.mataf.data.TimeUtil
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text

// ---------------------------------------------------------------- 카드
@Composable
fun Card(modifier: Modifier = Modifier, padding: Dp = 20.dp, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier
            .clip(RoundedCornerShape(20.dp))
            .background(C.surface)
            .padding(padding),
        content = content,
    )
}

@Composable
fun SectionTitle(title: String, modifier: Modifier = Modifier, trailing: @Composable RowScope.() -> Unit = {}) {
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(title, style = text(17, FontWeight.Bold), modifier = Modifier.weight(1f))
        trailing()
    }
}

// ---------------------------------------------------------------- 버튼
enum class BtnStyle { Primary, Secondary, White, Soft, Subtle, Danger, DangerSolid }

@Composable
fun Btn(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    style: BtnStyle = BtnStyle.Secondary,
    icon: ImageVector? = null,
    enabled: Boolean = true,
    small: Boolean = false,
    large: Boolean = false,
) {
    val src = remember { MutableInteractionSource() }
    val pressed by src.collectIsPressedAsState()
    val scale by animateFloatAsState(if (pressed) 0.96f else 1f, spring(stiffness = 900f), label = "press")
    val (bg, fg) = when (style) {
        BtnStyle.Primary -> (if (pressed) C.accentPressed else C.accent) to Color.White
        BtnStyle.Secondary -> (if (pressed) C.grey200 else C.grey100) to C.grey800
        BtnStyle.White -> (if (pressed) C.grey100 else Color.White) to C.grey800
        BtnStyle.Soft -> C.accentSoft to C.accentText
        BtnStyle.Subtle -> (if (pressed) C.grey100 else Color.Transparent) to C.grey700
        BtnStyle.Danger -> C.dangerSoft to C.danger
        BtnStyle.DangerSolid -> C.danger to Color.White
    }
    val h = if (small) 34.dp else if (large) 52.dp else 44.dp
    Row(
        modifier
            .scale(scale)
            .heightIn(min = h)
            .clip(RoundedCornerShape(if (small) 9.dp else 12.dp))
            .background(if (enabled) bg else bg.copy(alpha = 0.45f))
            .clickable(src, null, enabled = enabled, onClick = onClick)
            .padding(horizontal = if (small) 12.dp else 16.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
    ) {
        if (icon != null) {
            Icon(icon, null, tint = if (enabled) fg else fg.copy(alpha = 0.5f), modifier = Modifier.size(if (small) 16.dp else 18.dp))
            if (label.isNotEmpty()) Spacer(Modifier.width(6.dp))
        }
        if (label.isNotEmpty()) {
            Text(label, style = text(if (small) 13 else if (large) 16 else 15, FontWeight.SemiBold,
                if (enabled) fg else fg.copy(alpha = 0.5f)), maxLines = 1)
        }
    }
}

@Composable
fun IconBtn(icon: ImageVector, onClick: () -> Unit, modifier: Modifier = Modifier, tint: Color = C.grey700,
            bg: Color = C.grey100, size: Dp = 40.dp, enabled: Boolean = true) {
    Box(
        modifier.size(size).clip(RoundedCornerShape(12.dp)).background(bg).clickable(enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { Icon(icon, null, tint = if (enabled) tint else tint.copy(alpha = 0.4f), modifier = Modifier.size(size * 0.5f)) }
}

// ---------------------------------------------------------------- 칩 / 배지
@Composable
fun Chip(label: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier, round: Boolean = false) {
    val bg by animateColorAsState(if (selected) C.accent else C.grey100, tween(160), label = "chip")
    val fg by animateColorAsState(if (selected) Color.White else C.grey700, tween(160), label = "chipText")
    Box(
        modifier
            .heightIn(min = 36.dp)
            .clip(if (round) CircleShape else RoundedCornerShape(18.dp))
            .background(bg)
            .clickable(onClick = onClick)
            .padding(horizontal = if (round) 0.dp else 14.dp),
        contentAlignment = Alignment.Center,
    ) { Text(label, style = text(14, FontWeight.SemiBold, fg), maxLines = 1) }
}

@Composable
fun Pill(label: String, fg: Color = C.accentText, bg: Color = C.accentSofter) {
    Text(label, style = text(12, FontWeight.SemiBold, fg),
        modifier = Modifier.clip(RoundedCornerShape(6.dp)).background(bg).padding(horizontal = 8.dp, vertical = 3.dp))
}

// ---------------------------------------------------------------- 세그먼트
@Composable
fun Segmented(options: List<String>, selected: Int, onSelect: (Int) -> Unit, modifier: Modifier = Modifier, onPage: Boolean = false) {
    BoxWithConstraints(
        modifier
            .clip(RoundedCornerShape(12.dp))
            .background(if (onPage) Color.White else C.grey100)
            .padding(4.dp)
    ) {
        val segW = maxWidth / options.size
        val x by animateDpAsState(segW * selected, spring(dampingRatio = 0.85f, stiffness = 500f), label = "seg")
        Box(Modifier.offset(x = x).width(segW).height(36.dp).clip(RoundedCornerShape(9.dp))
            .background(if (onPage) C.grey100 else Color.White))
        Row {
            options.forEachIndexed { i, o ->
                Box(Modifier.width(segW).height(36.dp).clip(RoundedCornerShape(9.dp)).clickable { onSelect(i) },
                    contentAlignment = Alignment.Center) {
                    Text(o, style = text(14, if (i == selected) FontWeight.Bold else FontWeight.Medium,
                        if (i == selected) C.grey900 else C.grey600), maxLines = 1)
                }
            }
        }
    }
}

// ---------------------------------------------------------------- 스위치
@Composable
fun Toggle(checked: Boolean, onChange: (Boolean) -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    val track by animateColorAsState(if (checked) C.accent else C.grey300, tween(180), label = "track")
    val x by animateDpAsState(if (checked) 22.dp else 2.dp, spring(dampingRatio = 0.7f, stiffness = 700f), label = "knob")
    Box(
        modifier.size(50.dp, 30.dp).clip(CircleShape).background(if (enabled) track else track.copy(alpha = 0.4f))
            .clickable(enabled = enabled) { onChange(!checked) }
    ) {
        Box(Modifier.offset(x = x, y = 2.dp).size(26.dp).clip(CircleShape).background(Color.White))
    }
}

@Composable
fun ToggleRow(title: String, desc: String = "", checked: Boolean, onChange: (Boolean) -> Unit, enabled: Boolean = true) {
    Row(Modifier.fillMaxWidth().clickable(enabled = enabled) { onChange(!checked) }.padding(vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, style = text(15, FontWeight.SemiBold))
            if (desc.isNotEmpty()) Text(desc, style = text(13, color = C.grey500))
        }
        Spacer(Modifier.width(12.dp))
        Toggle(checked, onChange, enabled = enabled)
    }
}

@Composable
fun SettingRow(title: String, desc: String = "", trailing: @Composable () -> Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, style = text(15, FontWeight.SemiBold))
            if (desc.isNotEmpty()) Text(desc, style = text(13, color = C.grey500))
        }
        Spacer(Modifier.width(12.dp))
        trailing()
    }
}

@Composable
fun Divider() {
    Box(Modifier.fillMaxWidth().height(1.dp).background(C.grey100))
}

// ---------------------------------------------------------------- 입력
@Composable
fun Field(
    value: String,
    onChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    placeholder: String = "",
    leading: ImageVector? = null,
    onPage: Boolean = false,
    numeric: Boolean = false,
    onDone: (() -> Unit)? = null,
    password: Boolean = false,
) {
    Row(
        modifier
            .heightIn(min = 48.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(if (onPage) Color.White else C.grey100)
            .padding(horizontal = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (leading != null) {
            Icon(leading, null, tint = C.grey500, modifier = Modifier.size(18.dp)); Spacer(Modifier.width(8.dp))
        }
        Box(Modifier.weight(1f)) {
            if (value.isEmpty()) Text(placeholder, style = text(15, color = C.grey400), maxLines = 1, overflow = TextOverflow.Ellipsis)
            // 물리 키보드의 Enter 도 줄바꿈이 아니라 검색/완료로 (데스크톱 2.1.5 와 같게)
            BasicTextField(
                value, { onChange(it.replace("\n", "")) }, singleLine = true, textStyle = text(15),
                cursorBrush = SolidColor(C.accent),
                visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
                modifier = Modifier.fillMaxWidth().onPreviewKeyEvent { e ->
                    val enter = e.key == Key.Enter || e.key == Key.NumPadEnter
                    if (enter && e.type == KeyEventType.KeyDown) onDone?.invoke()
                    enter && onDone != null
                },
                keyboardOptions = KeyboardOptions(
                    keyboardType = if (password) KeyboardType.Password else if (numeric) KeyboardType.Number else KeyboardType.Text,
                    imeAction = if (onDone != null && !password) ImeAction.Search else ImeAction.Done,
                    autoCorrectEnabled = !password,
                ),
                keyboardActions = KeyboardActions(onSearch = { onDone?.invoke() }, onDone = { onDone?.invoke() }),
            )
        }
    }
}

@Composable
fun Label(t: String) {
    Text(t, style = text(13, FontWeight.SemiBold, C.grey600), modifier = Modifier.padding(bottom = 8.dp))
}

// ---------------------------------------------------------------- 요일
@Composable
fun DayChips(mask: Int, onChange: (Int) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            TimeUtil.WEEKDAYS.forEach { (d, bit) ->
                Chip(d, mask and bit != 0, { onChange(mask xor bit) }, Modifier.size(40.dp), round = true)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Chip("평일", mask == TimeUtil.WEEKDAYS_MASK, { onChange(TimeUtil.WEEKDAYS_MASK) })
            Chip("주말", mask == TimeUtil.WEEKEND_MASK, { onChange(TimeUtil.WEEKEND_MASK) })
            Chip("매일", mask == TimeUtil.ALL, { onChange(TimeUtil.ALL) })
        }
    }
}

// ---------------------------------------------------------------- 시각 고르기: [오전|오후] [ 2 ▴▾ ] : [ 40 ▴▾ ]
@Composable
fun TimePicker(hour: Int, minute: Int, onChange: (Int, Int) -> Unit) {
    val pm = hour >= 12
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Segmented(listOf("오전", "오후"), if (pm) 1 else 0, { i ->
                val h = hour % 12 + if (i == 1) 12 else 0
                onChange(h, minute)
            }, Modifier.width(150.dp))
            Stepper((hour % 12).let { if (it == 0) 12 else it }.toString(),
                onUp = { onChange((hour + 1) % 24, minute) }, onDown = { onChange((hour + 23) % 24, minute) })
            Text(":", style = text(22, FontWeight.Bold, C.grey500))
            Stepper("%02d".format(minute),
                onUp = { onChange(hour, (minute + 1) % 60) }, onDown = { onChange(hour, (minute + 59) % 60) })
        }
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf(-5, 5, 10, 60).forEach { d ->
                Btn(if (d == 60) "+1시간" else if (d > 0) "+${d}분" else "${d}분", {
                    val t = Math.floorMod(hour * 60 + minute + d, 1440)
                    onChange(t / 60, t % 60)
                }, small = true)
            }
        }
    }
}

@Composable
private fun Stepper(value: String, onUp: () -> Unit, onDown: () -> Unit) {
    Column(Modifier.clip(RoundedCornerShape(12.dp)).background(C.grey100).width(64.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        Box(Modifier.fillMaxWidth().height(26.dp).clickable(onClick = onUp), contentAlignment = Alignment.Center) {
            Icon(Icons.Rounded.KeyboardArrowUp, null, tint = C.grey500, modifier = Modifier.size(18.dp))
        }
        Text(value, style = text(22, FontWeight.Bold))
        Box(Modifier.fillMaxWidth().height(26.dp).clickable(onClick = onDown), contentAlignment = Alignment.Center) {
            Icon(Icons.Rounded.KeyboardArrowDown, null, tint = C.grey500, modifier = Modifier.size(18.dp))
        }
    }
}

// ---------------------------------------------------------------- 빈 화면 / 체크
@Composable
fun Empty(title: String, desc: String = "", modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().padding(vertical = 48.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(title, style = text(15, FontWeight.SemiBold, C.grey500))
        if (desc.isNotEmpty()) Text(desc, style = text(13, color = C.grey400), modifier = Modifier.padding(top = 4.dp))
    }
}

@Composable
fun CheckCircle(checked: Boolean, onClick: () -> Unit) {
    val bg by animateColorAsState(if (checked) C.accent else Color.Transparent, tween(150), label = "check")
    Box(
        Modifier.size(24.dp).clip(CircleShape).background(bg)
            .border(2.dp, if (checked) C.accent else C.grey300, CircleShape).clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        if (checked) Icon(Icons.Rounded.Check, null, tint = Color.White, modifier = Modifier.size(16.dp))
    }
}

@Composable
fun PageHeader(title: String, subtitle: String = "", trailing: @Composable RowScope.() -> Unit = {}) {
    Row(Modifier.fillMaxWidth().padding(bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, style = text(26, FontWeight.Bold))
            if (subtitle.isNotEmpty()) Text(subtitle, style = text(14, color = C.grey600))
        }
        trailing()
    }
}

@Composable
fun Bar(modifier: Modifier = Modifier, content: @Composable RowScope.() -> Unit) {
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
        content = content)
}

fun Modifier.maxContentWidth(): Modifier = this.widthIn(max = 1200.dp)

/** 한 화면: 세로로 스크롤되고, 넓은 화면에서는 가운데로 모인다. */
@Composable
fun Page(spacing: Dp = 16.dp, content: @Composable ColumnScope.() -> Unit) {
    val wide = isWide()
    Box(Modifier.fillMaxSize().imePadding().verticalScroll(rememberScrollState()), contentAlignment = Alignment.TopCenter) {
        Column(
            Modifier.maxContentWidth().fillMaxWidth()
                .padding(horizontal = if (wide) 32.dp else 16.dp)
                .padding(top = if (wide) 28.dp else 16.dp, bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(spacing),
            content = content,
        )
    }
}
