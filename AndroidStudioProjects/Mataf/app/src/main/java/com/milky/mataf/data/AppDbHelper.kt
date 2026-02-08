package com.milky.mataf.data

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

class AppDbHelper private constructor(ctx: Context) : SQLiteOpenHelper(ctx, DB_NAME, null, DB_VERSION) {

    companion object {
        private const val DB_NAME = "mataf.db"
        private const val DB_VERSION = 2

        @Volatile private var inst: AppDbHelper? = null

        fun get(ctx: Context): AppDbHelper {
            return inst ?: synchronized(this) {
                inst ?: AppDbHelper(ctx.applicationContext).also { inst = it }
            }
        }
    }

    override fun onCreate(db: SQLiteDatabase) {
        ensureSchema(db)
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        ensureSchema(db)
    }

    private fun ensureSchema(db: SQLiteDatabase) {
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
}
