package com.milky.mataf.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.milky.mataf.R

/** 데스크톱(app/ui/theme.py)과 같은 색 */
object C {
    val grey50 = Color(0xFFF9FAFB)
    val grey100 = Color(0xFFF2F4F6)
    val grey200 = Color(0xFFE5E8EB)
    val grey300 = Color(0xFFD1D6DB)
    val grey400 = Color(0xFFB0B8C1)
    val grey500 = Color(0xFF8B95A1)
    val grey600 = Color(0xFF6B7684)
    val grey700 = Color(0xFF4E5968)
    val grey800 = Color(0xFF333D4B)
    val grey900 = Color(0xFF191F28)
    val accent = Color(0xFFF76B15)
    val accentPressed = Color(0xFFDD5605)
    val accentText = Color(0xFFE05A00)
    val accentSoft = Color(0xFFFFE9D9)
    val accentSofter = Color(0xFFFFF4EC)
    val g0 = Color(0xFFFFA352)
    val g2 = Color(0xFFF76B15)
    val success = Color(0xFF0E9F6E)
    val successSoft = Color(0xFFE5F6EE)
    val danger = Color(0xFFF04452)
    val dangerSoft = Color(0xFFFFEEEF)
    val warning = Color(0xFFE08A00)
    val warningSoft = Color(0xFFFFF4DE)
    val bg = Color(0xFFF2F4F6)
    val surface = Color.White
}

val Pretendard = FontFamily(
    Font(R.font.pretendard_regular, FontWeight.Normal),
    Font(R.font.pretendard_medium, FontWeight.Medium),
    Font(R.font.pretendard_semibold, FontWeight.SemiBold),
    Font(R.font.pretendard_bold, FontWeight.Bold),
    Font(R.font.pretendard_extrabold, FontWeight.ExtraBold),
)

fun text(size: Int, weight: FontWeight = FontWeight.Normal, color: Color = C.grey900) =
    TextStyle(fontFamily = Pretendard, fontSize = size.sp, fontWeight = weight, color = color, letterSpacing = (-0.2).sp)

@Composable
fun MatafTheme(content: @Composable () -> Unit) {
    val base = MaterialTheme.typography
    val t = TextStyle(fontFamily = Pretendard)
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = C.accent, onPrimary = Color.White, secondary = C.grey700, background = C.bg,
            surface = C.surface, onSurface = C.grey900, surfaceVariant = C.grey100, outline = C.grey200, error = C.danger,
        ),
        typography = base.copy(
            displayLarge = base.displayLarge.merge(t), displayMedium = base.displayMedium.merge(t),
            displaySmall = base.displaySmall.merge(t), headlineLarge = base.headlineLarge.merge(t),
            headlineMedium = base.headlineMedium.merge(t), headlineSmall = base.headlineSmall.merge(t),
            titleLarge = base.titleLarge.merge(t), titleMedium = base.titleMedium.merge(t), titleSmall = base.titleSmall.merge(t),
            bodyLarge = base.bodyLarge.merge(t), bodyMedium = base.bodyMedium.merge(t), bodySmall = base.bodySmall.merge(t),
            labelLarge = base.labelLarge.merge(t), labelMedium = base.labelMedium.merge(t), labelSmall = base.labelSmall.merge(t),
        ),
        content = content,
    )
}
