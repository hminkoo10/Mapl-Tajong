package com.milky.mataf.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.RoundRect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathOperation
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.withTransform
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin

/** 날씨 그림 (데스크톱 app/ui/weather_icons.py 와 같은 그림, 코드로 그려 어떤 크기에서도 선명). 기준 격자 24x24 */
private val SUN = Color(0xFFFFB020)
private val MOON = Color(0xFFFFCF5C)
private val RAIN = Color(0xFF4DA3FF)
private val BOLT = Color(0xFFFFC93C)

@Composable
fun WeatherIcon(kind: String, night: Boolean, dark: Boolean, modifier: Modifier = Modifier) {
    Canvas(modifier) { paintWeather(kind, night, dark) }
}

/** 가운데 아래가 평평한 구름 모양. s 는 너비 기준 크기 */
private fun cloudPath(cx: Float, cy: Float, s: Float): Path {
    val w = s
    val h = s * 0.58f
    val left = cx - w / 2
    val bottom = cy + h / 2
    val base = Path().apply { addRoundRect(RoundRect(Rect(left, bottom - h * 0.52f, left + w, bottom), CornerRadius(h * 0.26f))) }
    val a = Path().apply { addOval(Rect(Offset(left + w * 0.34f, bottom - h * 0.52f), w * 0.21f)) }
    val b = Path().apply { addOval(Rect(Offset(left + w * 0.62f, bottom - h * 0.62f), w * 0.27f)) }
    val ab = Path().apply { op(base, a, PathOperation.Union) }
    return Path().apply { op(ab, b, PathOperation.Union) }
}

private fun DrawScope.sun(c: Offset, r: Float, rays: Boolean = true) {
    drawCircle(SUN, r, c)
    if (rays) {
        for (i in 0 until 8) {
            val a = PI / 4 * i
            drawLine(SUN, Offset(c.x + (cos(a) * r * 1.45).toFloat(), c.y + (sin(a) * r * 1.45).toFloat()),
                Offset(c.x + (cos(a) * r * 1.85).toFloat(), c.y + (sin(a) * r * 1.85).toFloat()), r * 0.28f, StrokeCap.Round)
        }
    }
}

private fun DrawScope.moon(c: Offset, r: Float) {
    val full = Path().apply { addOval(Rect(c, r)) }
    val cut = Path().apply { addOval(Rect(Offset(c.x + r * 0.55f, c.y - r * 0.35f), r * 0.85f)) }
    drawPath(Path().apply { op(full, cut, PathOperation.Difference) }, MOON)
}

private fun DrawScope.cloud(cx: Float, cy: Float, s: Float, color: Color, edge: Color?) {
    val path = cloudPath(cx, cy, s)
    drawPath(path, color)
    if (edge != null) drawPath(path, edge, style = Stroke(s * 0.035f))
}

fun DrawScope.paintWeather(kind: String, night: Boolean = false, dark: Boolean = true) {
    val s = min(size.width, size.height)
    val cloud = if (dark) Color(0xFFE8ECF1) else Color(0xFFCDD5DF)
    val cloud2 = if (dark) Color(0xFFB9C2CE) else Color(0xFFAEB8C5)
    val edge = if (dark) null else Color.White

    withTransform({
        translate((size.width - s) / 2, (size.height - s) / 2)
        scale(s / 24f, s / 24f, Offset.Zero)
    }) {
        fun celestial(c: Offset, r: Float, rays: Boolean = true) = if (night) moon(c, r) else sun(c, r, rays)

        when (kind) {
            "clear" -> celestial(Offset(12f, 12f), if (!night) 5.2f else 7.0f)
            "fair" -> {
                celestial(Offset(10.5f, 9.5f), 4.4f)
                cloud(14.5f, 16.0f, 11.5f, cloud, edge)
            }
            "partly" -> {
                celestial(Offset(8.5f, 8.5f), 4.0f, rays = !night)
                cloud(13.5f, 14.5f, 16.5f, cloud, edge)
            }
            "cloudy" -> {
                cloud(9.5f, 10.5f, 12f, cloud2, edge)
                cloud(13.5f, 14.5f, 16.5f, cloud, edge)
            }
            "fog" -> {
                cloud(12f, 10.0f, 16f, cloud, edge)
                for ((y, x0, x1) in listOf(Triple(17.0f, 4.5f, 19.5f), Triple(20.2f, 7.0f, 17.0f))) {
                    drawLine(cloud2, Offset(x0, y), Offset(x1, y), 1.6f, StrokeCap.Round)
                }
            }
            "rain", "sleet", "snow", "thunder" -> {
                cloud(12f, 9.5f, 17f, if (kind == "thunder") cloud2 else cloud, edge)
                if (kind == "thunder") {
                    val pts = listOf(12.8f to 13.2f, 9.6f to 18.0f, 12.0f to 18.0f, 10.8f to 22.4f, 15.0f to 16.6f,
                        12.4f to 16.6f, 13.8f to 13.2f)
                    val bolt = Path().apply {
                        pts.forEachIndexed { i, (x, y) -> if (i == 0) moveTo(x, y) else lineTo(x, y) }
                        close()
                    }
                    drawPath(bolt, BOLT)
                } else {
                    val drops = listOf(8.0f to 16.5f, 12.0f to 17.8f, 16.0f to 16.5f)
                    drops.forEachIndexed { i, (x, y) ->
                        val flake = kind == "snow" || (kind == "sleet" && i == 1)
                        if (flake) {
                            val fc = if (!dark) Color(0xFF9CCBFF) else Color(0xFFDCEBFF)
                            drawCircle(fc, 1.35f, Offset(x, y + 1.2f))
                            drawCircle(fc, 1.1f, Offset(x - 1.6f, y + 4.2f))
                        } else {
                            drawLine(RAIN, Offset(x + 0.6f, y), Offset(x - 0.9f, y + 3.6f), 1.7f, StrokeCap.Round)
                        }
                    }
                }
            }
            else -> cloud(12f, 13f, 17f, cloud, edge)
        }
    }
}
