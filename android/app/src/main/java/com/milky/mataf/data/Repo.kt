package com.milky.mataf.data

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

data class Sound(val id: Long, val name: String, val fileName: String, val volume: Double)

data class ScheduleSet(val id: Long, val name: String, val count: Int)

data class Schedule(
    val id: Long,
    val setId: Long,
    val name: String,
    val mask: Int,
    val hhmm: String,
    val soundId: Long,
    val volumeOverride: Double?,
    val enabled: Boolean,
    val soundName: String,
    val soundFile: String,
    val soundVolume: Double,
) {
    val volume: Double get() = volumeOverride ?: soundVolume
    val hour: Int get() = hhmm.substringBefore(":").toInt()
    val minute: Int get() = hhmm.substringAfter(":").toInt()
}

data class LogEntry(
    val id: Long,
    val at: String,
    val scheduleId: Long?,
    val scheduleName: String,
    val soundName: String,
    val result: String,
    val detail: String,
)

/** 일정 여러 개를 한 번에 바꿀 때의 변경 내용 (null 이면 그대로 둔다) */
data class BatchChange(
    val enabled: Boolean? = null,
    val mask: Int? = null,
    val shiftMinutes: Int? = null,
    val time: String? = null,
    val soundId: Long? = null,
    val volume: Double? = null,
    val clearVolume: Boolean = false,
    val nameFind: String? = null,
    val nameReplace: String? = null,
    val setId: Long? = null,
)

val DATE: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd")
val STAMP: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")

/** 데이터 읽고 쓰기. 모든 함수는 짧게 끝나므로 화면 스레드에서 불러도 된다. */
class Repo(ctx: Context) {
    private val db: SQLiteDatabase = Db.get(ctx).writableDatabase

    // ---------------- 설정 ----------------
    fun setting(key: String, def: String = ""): String =
        db.rawQuery("SELECT value FROM settings WHERE key=?", arrayOf(key)).use { if (it.moveToFirst()) it.getString(0) ?: def else def }

    fun setSetting(key: String, value: String) {
        db.execSQL("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", arrayOf(key, value))
    }

    // ---------------- 종소리 ----------------
    fun sounds(): List<Sound> = db.rawQuery("SELECT id, name, file_name, volume FROM sounds ORDER BY id", null).use { c ->
        buildList { while (c.moveToNext()) add(Sound(c.getLong(0), c.getString(1), c.getString(2), c.getDouble(3))) }
    }

    fun sound(id: Long): Sound? = db.rawQuery("SELECT id, name, file_name, volume FROM sounds WHERE id=?", arrayOf(id.toString())).use { c ->
        if (c.moveToFirst()) Sound(c.getLong(0), c.getString(1), c.getString(2), c.getDouble(3)) else null
    }

    fun insertSound(name: String, fileName: String, volume: Double): Long =
        db.insertOrThrow("sounds", null, ContentValues().apply {
            put("name", name); put("file_name", fileName); put("volume", volume)
        })

    fun updateSound(id: Long, name: String, volume: Double) {
        db.update("sounds", ContentValues().apply { put("name", name); put("volume", volume) }, "id=?", arrayOf(id.toString()))
    }

    fun updateSoundFile(id: Long, fileName: String) {
        db.update("sounds", ContentValues().apply { put("file_name", fileName) }, "id=?", arrayOf(id.toString()))
    }

    fun deleteSound(id: Long) {
        db.delete("sounds", "id=?", arrayOf(id.toString()))
    }

    fun soundUsage(): Map<Long, Int> = db.rawQuery("SELECT sound_id, COUNT(*) FROM schedules GROUP BY sound_id", null).use { c ->
        buildMap { while (c.moveToNext()) put(c.getLong(0), c.getInt(1)) }
    }

    // ---------------- 세트 ----------------
    fun sets(): List<ScheduleSet> = db.rawQuery(
        "SELECT s.id, s.name, (SELECT COUNT(*) FROM schedules WHERE set_id=s.id) FROM schedule_sets s ORDER BY s.id", null
    ).use { c -> buildList { while (c.moveToNext()) add(ScheduleSet(c.getLong(0), c.getString(1), c.getInt(2))) } }

    fun activeSetId(): Long {
        val v = setting("active_set_id", "").toLongOrNull()
        val ids = sets().map { it.id }
        return if (v != null && v in ids) v else ids.firstOrNull() ?: createSet("기본")
    }

    fun setActiveSet(id: Long) = setSetting("active_set_id", id.toString())

    fun createSet(name: String): Long =
        db.insertOrThrow("schedule_sets", null, ContentValues().apply { put("name", uniqueSetName(name)) })

    fun renameSet(id: Long, name: String) {
        db.update("schedule_sets", ContentValues().apply { put("name", uniqueSetName(name, id)) }, "id=?", arrayOf(id.toString()))
    }

    fun deleteSet(id: Long) {
        db.beginTransaction()
        try {
            db.delete("schedules", "set_id=?", arrayOf(id.toString()))
            db.delete("schedule_sets", "id=?", arrayOf(id.toString()))
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    fun uniqueSetName(name: String, exceptId: Long? = null): String {
        val taken = sets().filter { it.id != exceptId }.map { it.name }.toSet()
        val base = name.trim().ifEmpty { "새 세트" }
        if (base !in taken) return base
        var n = 2
        while ("$base ($n)" in taken) n++
        return "$base ($n)"
    }

    fun duplicateSet(id: Long, name: String): Long {
        db.beginTransaction()
        try {
            val newId = createSet(name)
            db.execSQL(
                """INSERT INTO schedules(set_id, name, weekday_mask, time_hhmm, sound_id, volume_override, enabled, sort_order)
                   SELECT ?, name, weekday_mask, time_hhmm, sound_id, volume_override, enabled, sort_order FROM schedules WHERE set_id=?""",
                arrayOf<Any>(newId, id)
            )
            db.setTransactionSuccessful()
            return newId
        } finally {
            db.endTransaction()
        }
    }

    // ---------------- 일정 ----------------
    private val scheduleSelect = """
        SELECT s.id, s.set_id, s.name, s.weekday_mask, s.time_hhmm, s.sound_id, s.volume_override, s.enabled,
               so.name, so.file_name, so.volume
        FROM schedules s JOIN sounds so ON so.id = s.sound_id
    """.trimIndent()

    private fun readSchedule(c: Cursor) = Schedule(
        id = c.getLong(0), setId = c.getLong(1), name = c.getString(2), mask = c.getInt(3), hhmm = c.getString(4),
        soundId = c.getLong(5), volumeOverride = if (c.isNull(6)) null else c.getDouble(6), enabled = c.getInt(7) == 1,
        soundName = c.getString(8), soundFile = c.getString(9), soundVolume = c.getDouble(10),
    )

    fun schedules(setId: Long): List<Schedule> =
        db.rawQuery("$scheduleSelect WHERE s.set_id=? ORDER BY s.time_hhmm, s.id", arrayOf(setId.toString())).use { c ->
            buildList { while (c.moveToNext()) add(readSchedule(c)) }
        }

    fun schedule(id: Long): Schedule? =
        db.rawQuery("$scheduleSelect WHERE s.id=?", arrayOf(id.toString())).use { c -> if (c.moveToFirst()) readSchedule(c) else null }

    fun insertSchedule(setId: Long, name: String, mask: Int, hhmm: String, soundId: Long, volume: Double?, enabled: Boolean): Long =
        db.insertOrThrow("schedules", null, ContentValues().apply {
            put("set_id", setId); put("name", name); put("weekday_mask", mask); put("time_hhmm", hhmm)
            put("sound_id", soundId); if (volume == null) putNull("volume_override") else put("volume_override", volume)
            put("enabled", if (enabled) 1 else 0)
        })

    fun updateSchedule(id: Long, name: String, mask: Int, hhmm: String, soundId: Long, volume: Double?, enabled: Boolean) {
        val old = schedule(id)
        db.update("schedules", ContentValues().apply {
            put("name", name); put("weekday_mask", mask); put("time_hhmm", hhmm); put("sound_id", soundId)
            if (volume == null) putNull("volume_override") else put("volume_override", volume)
            put("enabled", if (enabled) 1 else 0)
            put("updated_at", LocalDateTime.now().format(STAMP))
        }, "id=?", arrayOf(id.toString()))
        if (old != null && old.hhmm != hhmm) resetOneTime(id)
    }

    fun deleteSchedules(ids: Collection<Long>) {
        if (ids.isEmpty()) return
        val q = ids.joinToString(",") { "?" }
        db.delete("schedules", "id IN ($q)", ids.map { it.toString() }.toTypedArray())
    }

    fun setEnabled(ids: Collection<Long>, on: Boolean) {
        if (ids.isEmpty()) return
        val q = ids.joinToString(",") { "?" }
        db.update("schedules", ContentValues().apply { put("enabled", if (on) 1 else 0) }, "id IN ($q)",
            ids.map { it.toString() }.toTypedArray())
    }

    fun duplicateSchedules(ids: Collection<Long>, shiftMinutes: Int = 0, toSet: Long? = null): List<Long> {
        val out = mutableListOf<Long>()
        db.beginTransaction()
        try {
            for (id in ids) {
                val s = schedule(id) ?: continue
                val (t, m) = TimeUtil.shift(s.hhmm, s.mask, shiftMinutes)
                out += insertSchedule(toSet ?: s.setId, s.name, m, t, s.soundId, s.volumeOverride, s.enabled)
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        return out
    }

    fun batchUpdate(ids: Collection<Long>, ch: BatchChange) {
        db.beginTransaction()
        try {
            for (id in ids) {
                val s = schedule(id) ?: continue
                var name = s.name
                var mask = s.mask
                var hhmm = s.hhmm
                if (ch.mask != null) mask = ch.mask
                if (ch.time != null) hhmm = ch.time
                if (ch.shiftMinutes != null && ch.shiftMinutes != 0) {
                    val (t, m) = TimeUtil.shift(hhmm, mask, ch.shiftMinutes)
                    hhmm = t; mask = m
                }
                if (!ch.nameFind.isNullOrEmpty()) name = name.replace(ch.nameFind, ch.nameReplace ?: "")
                val vol = when {
                    ch.clearVolume -> null
                    ch.volume != null -> ch.volume
                    else -> s.volumeOverride
                }
                updateSchedule(id, name.ifBlank { s.name }, mask, hhmm, ch.soundId ?: s.soundId, vol, ch.enabled ?: s.enabled)
                if (ch.setId != null) {
                    db.update("schedules", ContentValues().apply { put("set_id", ch.setId) }, "id=?", arrayOf(id.toString()))
                }
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    // ---------------- 한 번만 적용되는 변경 (건너뛰기·미리 울림·오늘 쉼) ----------------
    fun addOverride(date: LocalDate, scheduleId: Long, action: String, note: String = "") {
        db.insertOrThrow("overrides", null, ContentValues().apply {
            put("date_yyyymmdd", date.format(DATE)); put("schedule_id", scheduleId); put("action", action); put("note", note)
        })
    }

    fun removeOverride(date: LocalDate, scheduleId: Long, action: String): Int =
        db.delete("overrides", "date_yyyymmdd=? AND schedule_id=? AND action=?",
            arrayOf(date.format(DATE), scheduleId.toString(), action))

    fun hasOverride(date: LocalDate, scheduleId: Long, action: String): Boolean =
        db.rawQuery("SELECT 1 FROM overrides WHERE date_yyyymmdd=? AND schedule_id=? AND action=? LIMIT 1",
            arrayOf(date.format(DATE), scheduleId.toString(), action)).use { it.moveToFirst() }

    /** (날짜, 일정 id) → 그날의 동작들 */
    fun overridesBetween(from: LocalDate, to: LocalDate): Map<Pair<String, Long>, Set<String>> =
        db.rawQuery("SELECT date_yyyymmdd, schedule_id, action FROM overrides WHERE date_yyyymmdd BETWEEN ? AND ?",
            arrayOf(from.format(DATE), to.format(DATE))).use { c ->
            val m = mutableMapOf<Pair<String, Long>, MutableSet<String>>()
            while (c.moveToNext()) m.getOrPut(c.getString(0) to c.getLong(1)) { mutableSetOf() }.add(c.getString(2))
            m
        }

    fun purgeOldOverrides(today: LocalDate) {
        db.delete("overrides", "date_yyyymmdd < ?", arrayOf(today.format(DATE)))
    }

    fun isPauseDay(date: LocalDate): Boolean = hasOverride(date, 0, "PAUSE_DAY")

    fun setPauseDay(date: LocalDate, on: Boolean) {
        db.delete("overrides", "date_yyyymmdd=? AND action='PAUSE_DAY'", arrayOf(date.format(DATE)))
        if (on) addOverride(date, 0, "PAUSE_DAY", "admin")
    }

    /** 시각을 바꾸면 오늘 걸려 있던 건너뛰기·미리 울림은 의미가 없어지므로 지운다 */
    private fun resetOneTime(scheduleId: Long) {
        db.delete("overrides", "schedule_id=? AND action IN ('SKIP_ONCE','FIRED_ONCE') AND date_yyyymmdd >= ?",
            arrayOf(scheduleId.toString(), LocalDate.now().format(DATE)))
    }

    // ---------------- 기록 ----------------
    fun log(scheduleId: Long?, scheduleName: String, soundName: String, result: String, detail: String = "") {
        db.insert("logs", null, ContentValues().apply {
            put("occurred_at", LocalDateTime.now().format(STAMP))
            if (scheduleId == null) putNull("schedule_id") else put("schedule_id", scheduleId)
            put("schedule_name", scheduleName); put("sound_name", soundName); put("result", result); put("detail", detail)
        })
    }

    fun logs(from: LocalDate, to: LocalDate, result: String? = null): List<LogEntry> {
        val args = mutableListOf(from.format(DATE) + " 00:00:00", to.format(DATE) + " 23:59:59")
        var sql = "SELECT id, occurred_at, schedule_id, schedule_name, sound_name, result, detail FROM logs " +
            "WHERE occurred_at BETWEEN ? AND ?"
        if (result != null) {
            sql += " AND result=?"; args += result
        }
        sql += " ORDER BY occurred_at DESC, id DESC LIMIT 2000"
        return db.rawQuery(sql, args.toTypedArray()).use { c ->
            buildList {
                while (c.moveToNext()) add(LogEntry(c.getLong(0), c.getString(1), if (c.isNull(2)) null else c.getLong(2),
                    c.getString(3) ?: "", c.getString(4) ?: "", c.getString(5), c.getString(6) ?: ""))
            }
        }
    }

    /** 오늘 일정별 마지막 결과 (PLAYED/SKIPPED/FAILED/MISSED) */
    fun todayResults(date: LocalDate): Map<Long, String> = db.rawQuery(
        "SELECT schedule_id, result FROM logs WHERE occurred_at LIKE ? AND schedule_id IS NOT NULL ORDER BY id",
        arrayOf(date.format(DATE) + "%")
    ).use { c -> buildMap { while (c.moveToNext()) put(c.getLong(0), c.getString(1)) } }

    fun countPlayed(date: LocalDate): Int = db.rawQuery(
        "SELECT COUNT(*) FROM logs WHERE occurred_at LIKE ? AND result='PLAYED'", arrayOf(date.format(DATE) + "%")
    ).use { if (it.moveToFirst()) it.getInt(0) else 0 }

    // ---------------- 백업용 ----------------
    fun raw(): SQLiteDatabase = db
}
