package com.milky.mataf.data

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

class AppDbHelper private constructor(ctx: Context) : SQLiteOpenHelper(ctx, DB_NAME, null, DB_VER) {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS sounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                file_name TEXT NOT NULL,
                volume_percent INTEGER NOT NULL DEFAULT 100,
                built_in INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """.trimIndent()
        )

        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                weekday_mask INTEGER NOT NULL,
                hour INTEGER NOT NULL,
                minute INTEGER NOT NULL,
                sound_id INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """.trimIndent()
        )

        db.execSQL("CREATE INDEX IF NOT EXISTS idx_schedules_enabled ON schedules(enabled)")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_schedules_time ON schedules(hour, minute)")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_schedules_sound ON schedules(sound_id)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        db.execSQL("DROP TABLE IF EXISTS schedules")
        db.execSQL("DROP TABLE IF EXISTS sounds")
        onCreate(db)
    }

    companion object {
        private const val DB_NAME = "mataf.db"
        private const val DB_VER = 3

        @Volatile private var inst: AppDbHelper? = null

        fun get(
            ctx: Context): AppDbHelper {
            return inst ?: synchronized(this) {
                inst ?: AppDbHelper(ctx.applicationContext).also { inst = it }
            }
        }
    }
}
