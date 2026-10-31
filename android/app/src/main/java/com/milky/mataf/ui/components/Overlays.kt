package com.milky.mataf.ui.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.KeyboardArrowDown
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.DpOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.milky.mataf.ui.theme.C
import com.milky.mataf.ui.theme.text
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

// ---------------------------------------------------------------- 알림(토스트)
data class ToastMsg(val text: String, val kind: String = "info", val action: String? = null, val onAction: (() -> Unit)? = null,
                    val id: Long = System.nanoTime())

object Toasts {
    private val _cur = MutableStateFlow<ToastMsg?>(null)
    val current: StateFlow<ToastMsg?> = _cur
    fun show(text: String, kind: String = "info", action: String? = null, onAction: (() -> Unit)? = null) {
        _cur.value = ToastMsg(text, kind, action, onAction)
    }
    fun dismiss() {
        _cur.value = null
    }
}

@Composable
fun ToastHost(modifier: Modifier = Modifier) {
    val msg by Toasts.current.collectAsState()
    LaunchedEffect(msg?.id) {
        val m = msg ?: return@LaunchedEffect
        delay(if (m.action != null) 6000 else 2600)
        if (Toasts.current.value?.id == m.id) Toasts.dismiss()
    }
    Box(modifier.fillMaxWidth().padding(16.dp), contentAlignment = Alignment.BottomCenter) {
        AnimatedVisibility(
            visible = msg != null,
            enter = fadeIn(tween(180)) + slideInVertically(tween(260)) { it / 2 },
            exit = fadeOut(tween(160)) + slideOutVertically(tween(200)) { it / 2 },
        ) {
            val m = msg
            if (m != null) {
                Row(
                    Modifier.widthIn(max = 520.dp).clip(RoundedCornerShape(16.dp)).background(Color(0xF0222831))
                        .padding(horizontal = 16.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    val (icon, tint) = when (m.kind) {
                        "success" -> Icons.Rounded.CheckCircle to Color(0xFF34D399)
                        "error", "warning" -> Icons.Rounded.Warning to Color(0xFFFFB27A)
                        else -> Icons.Rounded.Info to Color(0xFFB0B8C1)
                    }
                    Icon(icon, null, tint = tint, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(10.dp))
                    Text(m.text, style = text(14, FontWeight.Medium, Color.White), modifier = Modifier.weight(1f, fill = false))
                    if (m.action != null) {
                        Spacer(Modifier.width(12.dp))
                        Text(m.action, style = text(14, FontWeight.Bold, Color(0xFFFFB27A)),
                            modifier = Modifier.clip(RoundedCornerShape(8.dp)).clickable {
                                Toasts.dismiss(); m.onAction?.invoke()
                            }.padding(horizontal = 6.dp, vertical = 4.dp))
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------- 시트 (휴대폰: 아래에서, 태블릿: 가운데 창)
@Composable
fun isWide(): Boolean = LocalConfiguration.current.screenWidthDp >= 840

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppSheet(
    title: String,
    onDismiss: () -> Unit,
    subtitle: String = "",
    footer: (@Composable () -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val body: @Composable () -> Unit = {
        Column(Modifier.fillMaxWidth().padding(horizontal = 24.dp).padding(bottom = 20.dp)) {
            Text(title, style = text(20, FontWeight.Bold))
            if (subtitle.isNotEmpty()) Text(subtitle, style = text(14, color = C.grey600), modifier = Modifier.padding(top = 4.dp))
            Spacer(Modifier.size(18.dp))
            Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(18.dp), content = content)
            if (footer != null) {
                Spacer(Modifier.size(20.dp))
                footer()
            }
        }
    }
    if (isWide()) {
        Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Box(Modifier.widthIn(max = 560.dp).padding(24.dp).clip(RoundedCornerShape(24.dp)).background(Color.White)
                .padding(top = 24.dp)) { body() }
        }
    } else {
        ModalBottomSheet(
            onDismissRequest = onDismiss,
            sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
            containerColor = Color.White,
            shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp),
        ) {
            Box(Modifier.navigationBarsPadding()) { body() }
        }
    }
}

@Composable
fun SheetButtons(okLabel: String, onOk: () -> Unit, onCancel: () -> Unit, okEnabled: Boolean = true, danger: Boolean = false) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Btn("취소", onCancel, Modifier.weight(1f), large = true)
        Btn(okLabel, onOk, Modifier.weight(2f), style = if (danger) BtnStyle.DangerSolid else BtnStyle.Primary, large = true,
            enabled = okEnabled)
    }
}

// ---------------------------------------------------------------- 확인 창
@Composable
fun ConfirmDialog(title: String, message: String, okLabel: String, onOk: () -> Unit, onDismiss: () -> Unit,
                  danger: Boolean = true, cancelLabel: String? = "취소") {
    Dialog(onDismissRequest = onDismiss) {
        Column(Modifier.widthIn(max = 420.dp).clip(RoundedCornerShape(24.dp)).background(Color.White).padding(24.dp)) {
            Text(title, style = text(19, FontWeight.Bold))
            Spacer(Modifier.size(10.dp))
            Text(message, style = text(15, color = C.grey700))
            Spacer(Modifier.size(22.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (cancelLabel != null) Btn(cancelLabel, onDismiss, Modifier.weight(1f), large = true)
                Btn(okLabel, { onDismiss(); onOk() }, Modifier.weight(1f), large = true,
                    style = if (danger) BtnStyle.DangerSolid else BtnStyle.Primary)
            }
        }
    }
}

// ---------------------------------------------------------------- 메뉴 / 고르기
data class MenuItem(val label: String, val danger: Boolean = false, val onClick: () -> Unit)

@Composable
fun AppMenu(expanded: Boolean, onDismiss: () -> Unit, items: List<MenuItem>, offset: DpOffset = DpOffset(0.dp, 4.dp)) {
    DropdownMenu(
        expanded = expanded, onDismissRequest = onDismiss, offset = offset,
        shape = RoundedCornerShape(14.dp), containerColor = Color.White, shadowElevation = 8.dp, tonalElevation = 0.dp,
    ) {
        items.forEach { it ->
            DropdownMenuItem(
                text = { Text(it.label, style = text(15, FontWeight.Medium, if (it.danger) C.danger else C.grey900)) },
                onClick = { onDismiss(); it.onClick() },
            )
        }
    }
}

/** 드롭다운으로 고르기 (값 목록 중 하나) */
@Composable
fun <T> Select(
    options: List<Pair<T, String>>,
    selected: T?,
    onSelect: (T) -> Unit,
    modifier: Modifier = Modifier,
    placeholder: String = "고르기",
    onPage: Boolean = false,
) {
    var open by remember { mutableStateOf(false) }
    Box(modifier) {
        Row(
            Modifier.fillMaxWidth().heightIn(min = 48.dp).clip(RoundedCornerShape(12.dp))
                .background(if (onPage) Color.White else C.grey100).clickable { open = true }.padding(horizontal = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(options.firstOrNull { it.first == selected }?.second ?: placeholder, style = text(15),
                modifier = Modifier.weight(1f), maxLines = 1)
            Icon(Icons.Rounded.KeyboardArrowDown, null, tint = C.grey500)
        }
        DropdownMenu(
            expanded = open, onDismissRequest = { open = false },
            shape = RoundedCornerShape(14.dp), containerColor = Color.White, shadowElevation = 8.dp, tonalElevation = 0.dp,
            modifier = Modifier.heightIn(max = 360.dp),
        ) {
            options.forEach { (v, label) ->
                DropdownMenuItem(
                    text = {
                        Text(label, style = text(15, if (v == selected) FontWeight.Bold else FontWeight.Normal,
                            if (v == selected) C.accentText else C.grey900))
                    },
                    onClick = { open = false; onSelect(v) },
                )
            }
        }
    }
}
