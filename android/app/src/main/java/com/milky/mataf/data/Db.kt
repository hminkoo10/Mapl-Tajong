package com.milky.mataf.data

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

/** 데스크톱(app/data/schema.sql)과 같은 구조. 백업 파일을 서로 주고받을 수 있다. */
class Db private constructor(ctx: Context) : SQLiteOpenHelper(ctx, NAME, null, VERSION) {

    companion object {
        const val NAME = "tajong.db"
        private const val VERSION = 1

        @Volatile private var inst: Db? = null

        fun get(ctx: Context): Db = inst ?: synchronized(this) {
            inst ?: Db(ctx.applicationContext).also { inst = it }
        }
    }

    override fun onConfigure(db: SQLiteDatabase) {
        db.setForeignKeyConstraintsEnabled(true)
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS sounds (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              file_name TEXT NOT NULL,
              volume REAL NOT NULL DEFAULT 1.0,
              created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )""".trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS schedule_sets (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE,
              created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )""".trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS schedules (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              set_id INTEGER NOT NULL DEFAULT 1,
              name TEXT NOT NULL,
              weekday_mask INTEGER NOT NULL,
              time_hhmm TEXT NOT NULL,
              sound_id INTEGER NOT NULL,
              volume_override REAL,
              enabled INTEGER NOT NULL DEFAULT 1,
              sort_order INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
              FOREIGN KEY(sound_id) REFERENCES sounds(id)
            )""".trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS logs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              occurred_at TEXT NOT NULL,
              schedule_id INTEGER,
              schedule_name TEXT,
              sound_name TEXT,
              result TEXT NOT NULL,
              detail TEXT
            )""".trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS overrides (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              date_yyyymmdd TEXT NOT NULL,
              schedule_id INTEGER NOT NULL,
              action TEXT NOT NULL,
              applied_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
              note TEXT
            )""".trimIndent()
        )
        db.execSQL("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_sched_set ON schedules(set_id, time_hhmm)")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_logs_at ON logs(occurred_at)")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_ov_date ON overrides(date_yyyymmdd, schedule_id)")
        db.execSQL("INSERT INTO schedule_sets(name) VALUES('기본')")
        db.execSQL("INSERT OR REPLACE INTO settings(key, value) VALUES('active_set_id', '1')")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {}
}
