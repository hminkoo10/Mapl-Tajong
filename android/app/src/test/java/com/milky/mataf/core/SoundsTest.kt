package com.milky.mataf.core

import org.junit.Assert.assertEquals
import org.junit.Test

class SoundsTest {
    @Test
    fun durationShowsHoursFromOneHour() {
        assertEquals("-", Sounds.formatDuration(null))
        assertEquals("-", Sounds.formatDuration(0))
        assertEquals("5.5초", Sounds.formatDuration(5_500))
        assertEquals("1:15", Sounds.formatDuration(75_200))
        assertEquals("59:59", Sounds.formatDuration((59 * 60 + 59) * 1000 + 400))   // 1시간 아래는 예전 그대로
        assertEquals("1:00:00", Sounds.formatDuration(3_600_000))
        assertEquals("1:15:03", Sounds.formatDuration((75 * 60 + 3) * 1000))         // 예전에는 75:03
        assertEquals("10:00:05", Sounds.formatDuration((10 * 3600 + 5) * 1000))
    }
}
