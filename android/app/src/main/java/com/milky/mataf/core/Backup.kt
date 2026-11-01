package com.milky.mataf.core

import android.content.Context
import android.database.Cursor
import com.milky.mataf.BuildConfig
import com.milky.mataf.data.Repo
import com.milky.mataf.data.STAMP
import com.milky.mataf.data.TimeUtil
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.io.OutputStreamWriter
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream

/** 백업 파일을 쓸 수 없을 때. message 는 그대로 사용자에게 보여 준다. */
class BackupError(message: String) : RuntimeException(message)

/**
 * 전체 백업/복원과 시간표 CSV (데스크톱 app/core/backup.py 를 그대로 옮김).
 * zip = manifest.json + data.json + sounds/<파일 이름>. 데스크톱과 서로 주고받을 수 있다.
 * 다듬기 원본(originals)은 데스크톱처럼 넣지 않는다.
 * 파일을 읽고 쓰므로 IO 스레드에서 부른다. 넘겨받은 스트림은 다 쓰고 닫는다.
 */
object Backup {
    private const val FORMAT = 1
    private const val APP = "MaplTajong"
    private const val NOT_BACKUP = "타종 프로그램 백업 파일이 아닙니다."
    private const val TOO_NEW = "더 최신 버전에서 만든 백업입니다. 프로그램을 업데이트해 주세요."

    /** 옮기는 표와 열 (넣는 순서도 데스크톱과 같다: 종소리 → 세트 → 일정) */
    private val TABLES = linkedMapOf(
        "sounds" to listOf("id", "name", "file_name", "volume", "created_at"),
        "schedule_sets" to listOf("id", "name", "created_at"),
        "schedules" to listOf("id", "set_id", "name", "weekday_mask", "time_hhmm", "sound_id", "volume_override",
            "enabled", "sort_order", "created_at", "updated_at"),
    )
    private val SETTING_KEYS = listOf("active_set_id")

    /** manifest.json 내용. counts: sounds / schedule_sets / schedules 개수 */
    data class Manifest(val format: Int, val appVersion: String, val createdAt: String, val counts: Map<String, Int>)

    fun defaultBackupName(): String = "마고타종_백업_${LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmm"))}.zip"

    /** 시간표·세트·종소리를 zip 으로 쓴다. 돌려준 counts 로 토스트를 띄운다. */
    fun export(ctx: Context, out: OutputStream): Manifest {
        val db = Repo(ctx).raw()
        val data = JSONObject()
        for ((table, cols) in TABLES) {
            val rows = JSONArray()
            db.rawQuery("SELECT ${cols.joinToString(", ")} FROM $table ORDER BY id", null).use { c ->
                while (c.moveToNext()) rows.put(JSONObject().apply { cols.forEachIndexed { i, col -> put(col, value(c, i)) } })
            }
            data.put(table, rows)
        }
        data.put("settings", JSONObject().apply {
            for (k in SETTING_KEYS) {
                val v = db.rawQuery("SELECT value FROM settings WHERE key=?", arrayOf(k)).use { c ->
                    if (c.moveToFirst()) value(c, 0) else null
                }
                if (v != null) put(k, v)
            }
        })
        val counts = TABLES.keys.associateWith { data.getJSONArray(it).length() }
        val createdAt = LocalDateTime.now().format(STAMP)
        val manifest = JSONObject().apply {
            put("app", APP); put("format", FORMAT); put("app_version", BuildConfig.VERSION_NAME); put("created_at", createdAt)
            put("counts", JSONObject().apply { counts.forEach { (k, v) -> put(k, v) } })
        }
        ZipOutputStream(out.buffered()).use { z ->
            z.putNextEntry(ZipEntry("manifest.json")); z.write(manifest.toString(2).toByteArray()); z.closeEntry()
            z.putNextEntry(ZipEntry("data.json")); z.write(data.toString(2).toByteArray()); z.closeEntry()
            val sounds = data.getJSONArray("sounds")
            val done = mutableSetOf<String>()
            for (i in 0 until sounds.length()) {
                val f = Sounds.file(ctx, sounds.getJSONObject(i).optString("file_name"))
                if (!f.isFile || !done.add(f.name)) continue   // 같은 파일을 쓰는 종소리가 여럿이면 한 번만
                z.putNextEntry(ZipEntry("sounds/${f.name}"))
                f.inputStream().use { it.copyTo(z) }
                z.closeEntry()
            }
        }
        return Manifest(FORMAT, BuildConfig.VERSION_NAME, createdAt, counts)
    }

    /** 타종 백업인지 확인하고 manifest 를 돌려준다 (불러오기 전 확인 창용). 아니면 BackupError */
    fun readManifest(input: InputStream): Manifest = parseManifest(try {
        ZipInputStream(input.buffered()).use { z ->
            val e = generateSequence<ZipEntry> { z.nextEntry }.firstOrNull { it.name == "manifest.json" }
            if (e == null) null else String(z.readBytes(), Charsets.UTF_8)
        }
    } catch (e: Exception) {
        null
    })

    /**
     * 지금 시간표·세트·종소리를 백업 내용으로 바꾼다. 기록·쉬는 날·다른 설정은 그대로 둔다.
     * id 는 백업에 적힌 그대로 넣는다. beforeReplaceFiles 는 종소리 파일을 덮어쓰기 직전에 (이 스레드에서) 부른다.
     * 돌려주는 값: 표마다 불러온 개수 (sounds / schedule_sets / schedules)
     */
    fun import(ctx: Context, input: InputStream, beforeReplaceFiles: () -> Unit = {}): Map<String, Int> {
        val tmp = File.createTempFile("restore_", ".zip", ctx.cacheDir)
        try {
            input.use { i -> tmp.outputStream().use { i.copyTo(it) } }
            val zip = try { ZipFile(tmp) } catch (e: Exception) { throw BackupError(NOT_BACKUP) }
            val data = zip.use { z ->
                parseManifest(try { z.text("manifest.json") } catch (e: Exception) { null })
                val d = try { JSONObject(z.text("data.json")!!) } catch (e: Exception) { throw BackupError(NOT_BACKUP) }
                beforeReplaceFiles()
                val sounds = d.optJSONArray("sounds") ?: JSONArray()
                for (i in 0 until sounds.length()) {
                    val s = sounds.getJSONObject(i)
                    val fn = s.get("file_name").toString().substringAfterLast('/').substringAfterLast('\\')   // 경로 조작 방지
                    s.put("file_name", fn)
                    if (fn.isEmpty() || fn == "." || fn == "..") continue
                    val e = z.getEntry("sounds/$fn")
                    if (e != null && !e.isDirectory) writeSound(ctx, fn, z.getInputStream(e))
                }
                d
            }
            val counts = replace(ctx, data)
            // 클라우드에 연결돼 있으면 바뀐 시간표·종소리와 (지운) 건너뛰기를 올린다
            com.milky.mataf.data.DataChanges.notify(com.milky.mataf.data.DataChanges.Kind.CONFIG)
            com.milky.mataf.data.DataChanges.notify(com.milky.mataf.data.DataChanges.Kind.STATE)
            // 다듬기 원본은 종소리 id 로 짝을 찾으므로, 같은 id 의 다른 소리로 잘못 되돌리지 않게 비운다
            AudioEdit.originalsDir(ctx).listFiles()?.forEach { it.delete() }
            AppEvents.changed()
            Alarms.reschedule(ctx)
            return counts
        } finally {
            tmp.delete()
        }
    }

    /** 시간표를 CSV 로 (엑셀용 UTF-8 BOM, 줄 끝 \r\n). 돌려주는 값: 일정 수 */
    fun exportSchedulesCsv(ctx: Context, out: OutputStream): Int {
        val rows = Repo(ctx).raw().rawQuery(
            """SELECT ss.name, s.time_hhmm, s.name, s.weekday_mask, so.name, s.volume_override, so.volume, s.enabled
               FROM schedules s JOIN schedule_sets ss ON ss.id = s.set_id JOIN sounds so ON so.id = s.sound_id
               ORDER BY ss.id, s.time_hhmm, s.id""", null
        ).use { c ->
            fun str(i: Int) = c.getString(i) ?: ""
            buildList {
                while (c.moveToNext()) {
                    val v = if (c.isNull(5)) c.getDouble(6) else c.getDouble(5)
                    // 파이썬 round() 처럼 반올림은 짝수 쪽으로
                    add(listOf(str(0), str(1), str(2), TimeUtil.maskText(c.getInt(3)), str(4), "${Math.rint(v * 100).toInt()}%",
                        if (c.getInt(7) != 0) "ON" else "OFF"))
                }
            }
        }
        OutputStreamWriter(out, Charsets.UTF_8).use { w ->
            w.write(0xFEFF)   // BOM (데스크톱 utf-8-sig)
            for (r in listOf(listOf("세트", "시간", "이벤트", "요일", "종소리", "음량", "활성")) + rows) {
                w.write(r.joinToString(",") { csvField(it) } + "\r\n")
            }
        }
        return rows.size
    }

    private fun parseManifest(text: String?): Manifest {
        val m = try { JSONObject(text!!) } catch (e: Exception) { throw BackupError(NOT_BACKUP) }
        if (m.opt("app") != APP) throw BackupError(NOT_BACKUP)
        val format = when (val f = m.opt("format") ?: 0) {
            is Number -> f.toInt()
            else -> f.toString().trim().toIntOrNull() ?: throw BackupError(NOT_BACKUP)
        }
        if (format > FORMAT) throw BackupError(TOO_NEW)
        val counts = m.optJSONObject("counts")
        return Manifest(format, m.optString("app_version", ""), m.optString("created_at", ""),
            counts?.keys()?.asSequence()?.associateWith { counts.optInt(it) } ?: emptyMap())
    }

    /** 표 내용을 한 번에 바꾼다 (중간에 실패하면 전부 되돌린다) */
    private fun replace(ctx: Context, data: JSONObject): Map<String, Int> {
        val db = Repo(ctx).raw()
        db.beginTransaction()
        try {
            db.execSQL("DELETE FROM schedules")
            db.execSQL("DELETE FROM schedule_sets")
            db.execSQL("DELETE FROM sounds")
            db.execSQL("DELETE FROM overrides WHERE action IN ('SKIP_ONCE','FIRED_ONCE')")
            for ((table, cols) in TABLES) {
                val rows = data.optJSONArray(table) ?: continue
                for (i in 0 until rows.length()) {
                    val row = rows.getJSONObject(i)
                    val present = cols.filter { row.has(it) }
                    db.execSQL("INSERT INTO $table (${present.joinToString(", ")}) VALUES (${present.joinToString(", ") { "?" }})",
                        present.map { if (row.isNull(it)) null else row.get(it) }.toTypedArray())
                }
            }
            if ((data.optJSONArray("schedule_sets")?.length() ?: 0) == 0) db.execSQL("INSERT INTO schedule_sets(name) VALUES('기본')")
            data.optJSONObject("settings")?.let { st ->
                for (k in st.keys()) if (k in SETTING_KEYS) {
                    db.execSQL("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", arrayOf(k, st.get(k).toString()))
                }
            }
            val valid = db.rawQuery(
                "SELECT 1 FROM schedule_sets WHERE id=(SELECT CAST(value AS INTEGER) FROM settings WHERE key='active_set_id')", null
            ).use { it.moveToFirst() }
            if (!valid) {
                val first = db.rawQuery("SELECT id FROM schedule_sets ORDER BY id LIMIT 1", null)
                    .use { it.moveToFirst(); it.getLong(0) }
                db.execSQL("INSERT OR REPLACE INTO settings(key, value) VALUES('active_set_id', ?)", arrayOf(first.toString()))
            }
            db.setTransactionSuccessful()
        } catch (e: Exception) {
            throw BackupError("복원 중 오류가 발생했습니다: ${e.message ?: e}")
        } finally {
            db.endTransaction()
        }
        return TABLES.keys.associateWith { data.optJSONArray(it)?.length() ?: 0 }
    }

    /** 임시 파일에 다 쓴 뒤 바꿔 넣는다 (중간에 실패해도 원래 파일이 깨지지 않게) */
    private fun writeSound(ctx: Context, fn: String, input: InputStream) {
        val dst = File(Sounds.dir(ctx), fn)
        val part = File(Sounds.dir(ctx), ".$fn.part")
        try {
            input.use { i -> part.outputStream().use { i.copyTo(it) } }
            if (!part.renameTo(dst)) throw IOException("종소리 파일을 저장하지 못했어요: $fn")
        } finally {
            part.delete()
        }
    }

    /** sqlite 값을 들어 있는 형식 그대로 (정수·실수·글자·null) — 데스크톱 sqlite3 가 읽는 것과 같다 */
    private fun value(c: Cursor, i: Int): Any = when (c.getType(i)) {
        Cursor.FIELD_TYPE_NULL -> JSONObject.NULL
        Cursor.FIELD_TYPE_INTEGER -> c.getLong(i)
        Cursor.FIELD_TYPE_FLOAT -> c.getDouble(i)
        else -> c.getString(i)
    }

    private fun ZipFile.text(name: String): String? =
        getEntry(name)?.let { e -> getInputStream(e).use { String(it.readBytes(), Charsets.UTF_8) } }

    /** 데스크톱 csv 모듈(excel)과 같게: 쉼표·따옴표·줄바꿈이 있을 때만 따옴표로 감싼다 */
    private fun csvField(s: String) =
        if (s.any { it == ',' || it == '"' || it == '\r' || it == '\n' }) "\"${s.replace("\"", "\"\"")}\"" else s
}
