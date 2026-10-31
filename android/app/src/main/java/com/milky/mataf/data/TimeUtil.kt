package com.milky.mataf.data

import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime

/** 시각·요일 계산 (데스크톱 app/core/timeutil.py 와 같은 규칙) */
object TimeUtil {
    /** 월=1, 화=2, 수=4, 목=8, 금=16, 토=32, 일=64 */
    val WEEKDAYS = listOf("월" to 1, "화" to 2, "수" to 4, "목" to 8, "금" to 16, "토" to 32, "일" to 64)
    const val ALL = 127
    const val WEEKDAYS_MASK = 31
    const val WEEKEND_MASK = 96

    fun bit(date: LocalDate): Int = 1 shl (date.dayOfWeek.value - 1)

    fun maskText(mask: Int): String {
        when (mask) {
            ALL -> return "매일"
            WEEKDAYS_MASK -> return "평일"
            WEEKEND_MASK -> return "주말"
        }
        val on = WEEKDAYS.indices.filter { mask and WEEKDAYS[it].second != 0 }
        if (on.isEmpty()) return "-"
        if (on.size >= 3 && on == (on.first()..on.last()).toList()) return "${WEEKDAYS[on.first()].first}–${WEEKDAYS[on.last()].first}"
        return on.joinToString("·") { WEEKDAYS[it].first }
    }

    fun rotate(mask: Int, days: Int): Int {
        var m = mask and ALL
        repeat(((days % 7) + 7) % 7) { m = ((m shl 1) or (m shr 6)) and ALL }
        return m
    }

    /** 시간을 minutes 만큼 옮긴다. 자정을 넘으면 요일도 함께 옮긴다. */
    fun shift(hhmm: String, mask: Int, minutes: Int): Pair<String, Int> {
        val total = toMinutes(hhmm) + minutes
        val dayShift = Math.floorDiv(total, 1440)
        val rem = Math.floorMod(total, 1440)
        return "%02d:%02d".format(rem / 60, rem % 60) to rotate(mask, dayShift)
    }

    fun toMinutes(hhmm: String): Int = hhmm.substringBefore(":").toInt() * 60 + hhmm.substringAfter(":").toInt()

    fun hhmm(h: Int, m: Int): String = "%02d:%02d".format(h, m)

    /** '14:05' → '오후 2:05' */
    fun ampm(hhmm: String): String {
        val (part, hm) = ampmParts(hhmm)
        return "$part $hm"
    }

    fun ampmParts(hhmm: String): Pair<String, String> {
        val h = hhmm.substringBefore(":").toInt()
        val m = hhmm.substringAfter(":").toInt()
        return (if (h < 12) "오전" else "오후") to "${if (h % 12 == 0) 12 else h % 12}:%02d".format(m)
    }

    fun ampm(t: LocalTime): String = ampm(hhmm(t.hour, t.minute))

    fun at(date: LocalDate, hhmm: String): LocalDateTime = date.atTime(hhmm.substringBefore(":").toInt(), hhmm.substringAfter(":").toInt())

    /** 남은 시간: '1:05:09', '05:09' */
    fun remaining(seconds: Long): String {
        var s = maxOf(0L, seconds)
        val d = s / 86400; s %= 86400
        val h = s / 3600; s %= 3600
        val m = s / 60; val sec = s % 60
        return when {
            d > 0 -> "${d}일 %02d:%02d".format(h, m)
            h > 0 -> "$h:%02d:%02d".format(m, sec)
            else -> "%02d:%02d".format(m, sec)
        }
    }

    /** '3분 후', '1시간 20분 후' */
    fun remainWords(seconds: Long): String {
        val s = maxOf(0L, seconds)
        if (s < 60) return "${s}초 후"
        val m = s / 60
        if (m < 60) return "${m}분 후"
        val h = m / 60
        val r = m % 60
        return if (r > 0) "${h}시간 ${r}분 후" else "${h}시간 후"
    }

    val WEEK_KO = listOf("월", "화", "수", "목", "금", "토", "일")

    fun whenText(at: LocalDateTime, now: LocalDateTime = LocalDateTime.now()): String {
        val hm = ampm(at.toLocalTime())
        val d = java.time.temporal.ChronoUnit.DAYS.between(now.toLocalDate(), at.toLocalDate())
        return when (d) {
            0L -> "오늘 $hm"
            1L -> "내일 $hm"
            else -> "${at.monthValue}월 ${at.dayOfMonth}일 (${WEEK_KO[at.dayOfWeek.value - 1]}) $hm"
        }
    }
}
