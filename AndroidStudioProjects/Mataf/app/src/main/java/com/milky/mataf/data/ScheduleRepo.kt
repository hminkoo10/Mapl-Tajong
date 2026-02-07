package com.milky.mataf.data

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteConstraintException
import android.database.sqlite.SQLiteException
import java.util.Calendar

class ScheduleRepo(ctx: Context) {

    private val helper = AppDbHelper.get(ctx)

    init {
        helper.writableDatabase
    }

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
        val nm = name.trim()
        require(nm.isNotBlank())
        require(weekdayMask != 0)
        require(hour in 0..23)
        require(minute in 0..59)
        require(soundId > 0L)
        require(enabled == 0 || enabled == 1)

        val db = helper.writableDatabase
        val cv = ContentValues().apply {
            put("name", nm)
            put("weekday_mask", weekdayMask)
            put("hour", hour)
            put("minute", minute)
            put("sound_id", soundId)
            put("enabled", enabled)
        }

        return try {
            db.insertOrThrow("schedules", null, cv)
        } catch (e: SQLiteConstraintException) {
            -1L
        } catch (e: SQLiteException) {
            -1L
        }
    }

    fun updateSchedule(
        id: Long,
        name: String,
        weekdayMask: Int,
        hour: Int,
        minute: Int,
        soundId: Long,
        enabled: Int
    ): Boolean {
        val nm = name.trim()
        require(id > 0L)
        require(nm.isNotBlank())
        require(weekdayMask != 0)
        require(hour in 0..23)
        require(minute in 0..59)
        require(soundId > 0L)
        require(enabled == 0 || enabled == 1)

        val db = helper.writableDatabase
        val cv = ContentValues().apply {
            put("name", nm)
            put("weekday_mask", weekdayMask)
            put("hour", hour)
            put("minute", minute)
            put("sound_id", soundId)
            put("enabled", enabled)
        }

        val rows = db.update("schedules", cv, "id=?", arrayOf(id.toString()))
        return rows > 0
    }

    fun deleteSchedule(id: Long): Boolean {
        val db = helper.writableDatabase
        val rows = db.delete("schedules", "id=?", arrayOf(id.toString()))
        return rows > 0
    }

    data class NextSchedule(
        val scheduleId: Long,
        val runAtMillis: Long,
        val title: String,
        val soundId: Long
    )

    data class UpcomingSchedule(
        val scheduleId: Long,
        val runAtMillis: Long,
        val title: String,
        val soundId: Long
    )

    fun computeNext(nowMillis: Long = System.currentTimeMillis()): NextSchedule? {
        val all = listSchedules().filter { it.enabled == 1 }
        if (all.isEmpty()) return null

        var bestLocal: NextSchedule? = null

        for (dayOffset in 0..7) {
            val base = Calendar.getInstance().apply {
                timeInMillis = nowMillis
                add(Calendar.DAY_OF_YEAR, dayOffset)
                set(Calendar.SECOND, 0)
                set(Calendar.MILLISECOND, 0)
            }

            val bit = weekdayBit(base)

            for (s in all) {
                if ((s.weekdayMask and bit) == 0) continue

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

                if (bestLocal == null || cand.runAtMillis < bestLocal!!.runAtMillis) {
                    bestLocal = cand
                }
            }

            if (bestLocal != null) break
        }

        return bestLocal
    }

    fun listUpcomingWithin(
        nowMillis: Long = System.currentTimeMillis(),
        horizonMillis: Long = nowMillis + 3L * 60L * 60L * 1000L,
        limit: Int = 10
    ): List<UpcomingSchedule> {
        val all = listSchedules().filter { it.enabled == 1 }
        if (all.isEmpty()) return emptyList()

        val out = ArrayList<UpcomingSchedule>()

        for (dayOffset in 0..1) {
            val base = Calendar.getInstance().apply {
                timeInMillis = nowMillis
                add(Calendar.DAY_OF_YEAR, dayOffset)
                set(Calendar.SECOND, 0)
                set(Calendar.MILLISECOND, 0)
            }

            val bit = weekdayBit(base)

            for (s in all) {
                if ((s.weekdayMask and bit) == 0) continue

                val runAt = Calendar.getInstance().apply {
                    timeInMillis = base.timeInMillis
                    set(Calendar.HOUR_OF_DAY, s.hour)
                    set(Calendar.MINUTE, s.minute)
                    set(Calendar.SECOND, 0)
                    set(Calendar.MILLISECOND, 0)
                }.timeInMillis

                if (runAt <= nowMillis) continue
                if (runAt >= horizonMillis) continue

                out.add(
                    UpcomingSchedule(
                        scheduleId = s.id,
                        runAtMillis = runAt,
                        title = s.name,
                        soundId = s.soundId
                    )
                )
            }
        }

        return out.sortedBy { it.runAtMillis }.take(limit)
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
        val name = c.getString(1) ?: ""
        return ScheduleRow(
            id = c.getLong(0),
            name = name,
            weekdayMask = c.getInt(2),
            hour = c.getInt(3),
            minute = c.getInt(4),
            soundId = c.getLong(5),
            enabled = c.getInt(6)
        )
    }
}
