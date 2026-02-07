package com.milky.mataf.data

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import com.milky.mataf.storage.SoundStorage
import java.io.File

data class SoundRow(
    val id: Long,
    val name: String,
    val fileName: String,
    val volumePercent: Int,
    val builtIn: Int
)

class SoundRepo(private val ctx: Context) {

    private val helper = AppDbHelper.get(ctx)

    fun listSounds(): List<SoundRow> {
        val db = helper.readableDatabase
        val out = ArrayList<SoundRow>()
        val c = db.rawQuery(
            """
            SELECT id, name, file_name, volume_percent,
                   COALESCE(built_in, 0) AS built_in
            FROM sounds
            ORDER BY built_in DESC, id ASC
            """.trimIndent(),
            null
        )
        c.use {
            while (it.moveToNext()) {
                out.add(
                    SoundRow(
                        id = it.getLong(0),
                        name = it.getString(1),
                        fileName = it.getString(2),
                        volumePercent = it.getInt(3),
                        builtIn = it.getInt(4)
                    )
                )
            }
        }
        return out
    }

    fun soundPath(fileName: String): String {
        val dir = SoundStorage.soundsDir(ctx)
        return File(dir, fileName).absolutePath
    }

    fun seedBuiltInFromAssets() {
        val db = helper.writableDatabase
        ensureSchema(db)

        val existing = HashSet<String>()
        db.rawQuery("SELECT file_name FROM sounds WHERE COALESCE(built_in,0)=1", null).use {
            while (it.moveToNext()) existing.add(it.getString(0))
        }

        val allowed = setOf("wav", "mp3", "ogg", "m4a", "aac", "flac")
        val list = ctx.assets.list("sounds") ?: emptyArray()

        for (assetName in list) {
            val ext = assetName.substringAfterLast('.', "")
            if (ext.isBlank()) continue
            if (ext.lowercase() !in allowed) continue
            if (existing.contains(assetName)) continue

            SoundStorage.copyAssetIfMissing(ctx, "sounds/$assetName", assetName)
            val name = assetName.substringBeforeLast('.', assetName)

            val cv = ContentValues().apply {
                put("name", name)
                put("file_name", assetName)
                put("volume_percent", 100)
                put("built_in", 1)
            }
            db.insert("sounds", null, cv)
        }
    }

    private fun ensureSchema(db: android.database.sqlite.SQLiteDatabase) {
        db.execSQL(
            """
        CREATE TABLE IF NOT EXISTS sounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            file_name TEXT NOT NULL,
            volume_percent INTEGER NOT NULL DEFAULT 100,
            built_in INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """.trimIndent()
        )
        db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS idx_sounds_file_name ON sounds(file_name)")

        db.execSQL(
            """
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            weekday_mask INTEGER NOT NULL DEFAULT 0,
            hour INTEGER NOT NULL DEFAULT 0,
            minute INTEGER NOT NULL DEFAULT 0,
            sound_id INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """.trimIndent()
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_schedules_time ON schedules(hour, minute)")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_schedules_enabled ON schedules(enabled)")
    }

    fun addUserSoundFromUri(uri: Uri, nameOverride: String?, volumePercent: Int) {
        val displayName = queryDisplayName(uri) ?: "sound.wav"
        val copied = SoundStorage.copyUriToInternal(ctx, uri, displayName)
        val fileName = copied.name
        val name = nameOverride?.trim()?.takeIf { it.isNotBlank() } ?: fileName.substringBeforeLast('.', fileName)

        val db = helper.writableDatabase
        val cv = ContentValues().apply {
            put("name", name)
            put("file_name", fileName)
            put("volume_percent", volumePercent.coerceIn(0, 200))
            put("built_in", 0)
        }
        db.insert("sounds", null, cv)
    }

    fun updateSound(id: Long, name: String, volumePercent: Int) {
        val db = helper.writableDatabase
        val cv = ContentValues().apply {
            put("name", name)
            put("volume_percent", volumePercent.coerceIn(0, 200))
        }
        db.update("sounds", cv, "id=?", arrayOf(id.toString()))
    }

    fun removeUserSoundAndFile(row: SoundRow) {
        if (row.builtIn == 1) return
        val db = helper.writableDatabase
        db.delete("sounds", "id=?", arrayOf(row.id.toString()))

        val f = File(SoundStorage.soundsDir(ctx), row.fileName)
        if (f.exists()) {
            try { f.delete() } catch (_: Exception) {}
        }
    }

    private fun queryDisplayName(uri: Uri): String? {
        val c = ctx.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
        c?.use {
            if (it.moveToFirst()) return it.getString(0)
        }
        return null
    }
}
