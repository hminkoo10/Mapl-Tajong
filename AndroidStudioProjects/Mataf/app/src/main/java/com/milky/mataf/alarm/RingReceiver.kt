package com.milky.mataf.alarm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat
import com.milky.mataf.data.AppDbHelper
import com.milky.mataf.storage.SoundStorage
import java.io.File

class RingReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val pending = goAsync()

        Thread {
            try {
                val scheduleId = intent.getLongExtra("schedule_id", -1L)
                if (scheduleId < 0) return@Thread

                val row = queryScheduleWithSound(context, scheduleId) ?: return@Thread

                val play = Intent(context, TajongService::class.java).apply {
                    action = TajongService.ACTION_PLAY
                    putExtra("sound_path", row.soundPath)
                    putExtra("sound_name", row.soundName)
                    putExtra("volume_percent", row.volumePercent)
                }
                ContextCompat.startForegroundService(context, play)

                AlarmScheduler.rescheduleNext(context)
            } finally {
                pending.finish()
            }
        }.start()
    }

    private data class SchSound(
        val soundName: String,
        val soundPath: String,
        val volumePercent: Int
    )

    private fun queryScheduleWithSound(ctx: Context, scheduleId: Long): SchSound? {
        val db = AppDbHelper.get(ctx).readableDatabase

        val c = db.rawQuery(
            """
            SELECT so.name, so.file_name, so.volume_percent
            FROM schedules sc
            JOIN sounds so ON so.id = sc.sound_id
            WHERE sc.id=? AND sc.enabled=1
            LIMIT 1
            """.trimIndent(),
            arrayOf(scheduleId.toString())
        )

        c.use {
            if (!it.moveToFirst()) return null
            val name = it.getString(0) ?: "종"
            val fileName = it.getString(1) ?: return null
            val vol = it.getInt(2)

            val dir = SoundStorage.soundsDir(ctx)
            val soundPath = File(dir, fileName).absolutePath

            return SchSound(name, soundPath, vol)
        }
    }
}
