package com.milky.mataf.data

data class ScheduleRow(
    val id: Long,
    val name: String,
    val weekdayMask: Int,
    val hour: Int,
    val minute: Int,
    val soundId: Long,
    val enabled: Int
)
