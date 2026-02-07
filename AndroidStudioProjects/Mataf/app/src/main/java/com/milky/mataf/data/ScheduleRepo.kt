package com.milky.mataf.data

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import java.util.Calendar

class ScheduleRepo(ctx: Context) {

    private val helper = AppDbHelper.get(ctx)

    fun listSchedules(): List<ScheduleRow> {
        val db = helper.readableDatabase
        val out = ArrayList<ScheduleRow>()
        val c = db.rawQuery(
            """
            SELECT id, name, weekday_mask, hour, minute, sound_id, enabled
            FROM schedules
            ORDER BY hour ASC, minute ASC, id ASC
            """.trimIndent(),
            null
        )
        c.use {
            while (it.moveToNext()) out.add(readRow(it))
        }
        return out
    }

    fun insertSchedule(
        name: String,
        weekdayMask: Int,
        hour: Int,
        minute: Int,
        soundId: Long,
        enabled: Int
    ): Long {
        val db = helper.writableDatabase
        val cv = ContentValues().apply {
            put("name", name)
            put("weekday_mask", weekdayMask)
            put("hour", hour)
            put("minute", minute)
            put("sound_id", soundId)
            put("enabled", enabled)
        }
        return db.insert("schedules", null, cv)
    }

    fun updateSchedule(
        id: Long,
        name: String,
        weekdayMask: Int,
        hour: Int,
        minute: Int,
        soundId: Long,
        enabled: Int
    ) {
        val db = helper.writableDatabase
        val cv = ContentValues().apply {
            put("name", name)
            put("weekday_mask", weekdayMask)
            put("hour", hour)
            put("minute", minute)
            put("sound_id", soundId)
            put("enabled", enabled)
        }
        db.update("schedules", cv, "id=?", arrayOf(id.toString()))
    }

    fun deleteSchedule(id: Long) {
        val db = helper.writableDatabase
        db.delete("schedules", "id=?", arrayOf(id.toString()))
    }

    data class NextSchedule(
        val scheduleId: Long,
        val runAtMillis: Long,
        val title: String,
        val soundId: Long
    )

    fun computeNext(nowMillis: Long = System.currentTimeMillis()): NextSchedule? {
        val all = listSchedules().filter { it.enabled == 1 }
        if (all.isEmpty()) return null

        val best = arrayOfNulls<NextSchedule>(1)

        for (dayOffset in 0..7) {
            val base = Calendar.getInstance().apply {
                timeInMillis = nowMillis
                add(Calendar.DAY_OF_YEAR, dayOffset)
                set(Calendar.SECOND, 0)
                set(Calendar.MILLISECOND, 0)
            }

            val bit = weekdayBit(base)
            val todays = all.filter { (it.weekdayMask and bit) != 0 }

            for (s in todays) {
                val runAt = Calendar.getInstance().apply {
                    timeInMillis = base.timeInMillis
                    set(Calendar.HOUR_OF_DAY, s.hour)
                    set(Calendar.MINUTE, s.minute)
                    set(Calendar.SECOND, 0)
                    set(Calendar.MILLISECOND, 0)
                }.timeInMillis

                if (dayOffset == 0 && runAt <= nowMillis) continue

                val cand = NextSchedule(
                    scheduleId = s.id,
                    runAtMillis = runAt,
                    title = s.name,
                    soundId = s.soundId
                )

                val cur = best[0]
                if (cur == null || cand.runAtMillis < cur.runAtMillis) best[0] = cand
            }

            if (best[0] != null) break
        }

        return best[0]
    }

    private fun weekdayBit(cal: Calendar): Int {
        return when (cal.get(Calendar.DAY_OF_WEEK)) {
            Calendar.MONDAY -> 1
            Calendar.TUESDAY -> 2
            Calendar.WEDNESDAY -> 4
            Calendar.THURSDAY -> 8
            Calendar.FRIDAY -> 16
            Calendar.SATURDAY -> 32
            Calendar.SUNDAY -> 64
            else -> 0
        }
    }

    private fun readRow(c: Cursor): ScheduleRow {
        return ScheduleRow(
            id = c.getLong(0),
            name = c.getString(1),
            weekdayMask = c.getInt(2),
            hour = c.getInt(3),
            minute = c.getInt(4),
            soundId = c.getLong(5),
            enabled = c.getInt(6)
        )
    }
}
