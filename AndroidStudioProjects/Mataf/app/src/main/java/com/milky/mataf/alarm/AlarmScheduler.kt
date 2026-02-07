package com.milky.mataf.alarm

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.content.ContextCompat
import com.milky.mataf.MainActivity
import com.milky.mataf.data.AppDbHelper
import com.milky.mataf.data.ScheduleRepo

object AlarmScheduler {

    private const val REQ_NEXT = 2001
    private const val REQ_SHOW = 2002

    fun rescheduleNext(ctx: Context) {
        val repo = ScheduleRepo(ctx)
        val next = repo.computeNext()

        if (next == null) {
            cancelNext(ctx)
            StatusStore.clear(ctx)
            ContextCompat.startForegroundService(
                ctx,
                Intent(ctx, TajongService::class.java).apply { action = TajongService.ACTION_START }
            )
            return
        }

        val soundName = querySoundName(ctx, next.soundId)
        StatusStore.setNext(ctx, next.runAtMillis, next.title, soundName)

        scheduleAlarmClockExact(ctx, next.runAtMillis, next.scheduleId)

        ContextCompat.startForegroundService(
            ctx,
            Intent(ctx, TajongService::class.java).apply { action = TajongService.ACTION_START }
        )
    }

    fun cancelNext(ctx: Context) {
        val am = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        am.cancel(nextPendingIntent(ctx, -1L))
    }

    fun canScheduleExact(ctx: Context): Boolean {
        val am = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) am.canScheduleExactAlarms() else true
    }

    fun openExactAlarmSettings(ctx: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return false
        val i = Intent(android.provider.Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM).apply {
            data = android.net.Uri.parse("package:${ctx.packageName}")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        ctx.startActivity(i)
        return true
    }

    private fun scheduleAlarmClockExact(ctx: Context, atMillis: Long, scheduleId: Long) {
        val am = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager

        val ringPi = nextPendingIntent(ctx, scheduleId)
        val showPi = showAppPendingIntent(ctx)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !am.canScheduleExactAlarms()) {
            ContextCompat.startForegroundService(
                ctx,
                Intent(ctx, TajongService::class.java).apply { action = TajongService.ACTION_START }
            )
            return
        }

        val info = AlarmManager.AlarmClockInfo(atMillis, showPi)
        am.setAlarmClock(info, ringPi)
    }

    private fun nextPendingIntent(ctx: Context, scheduleId: Long): PendingIntent {
        val intent = Intent(ctx, RingReceiver::class.java).apply {
            action = "TAJONG_RING_NEXT"
            if (scheduleId >= 0) putExtra("schedule_id", scheduleId)
        }
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        return PendingIntent.getBroadcast(ctx, REQ_NEXT, intent, flags)
    }

    private fun showAppPendingIntent(ctx: Context): PendingIntent {
        val intent = Intent(ctx, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        return PendingIntent.getActivity(ctx, REQ_SHOW, intent, flags)
    }

    private fun querySoundName(ctx: Context, soundId: Long): String {
        val db = AppDbHelper.get(ctx).readableDatabase
        val c = db.rawQuery(
            "SELECT name FROM sounds WHERE id=? LIMIT 1",
            arrayOf(soundId.toString())
        )
        c.use {
            if (it.moveToFirst()) return it.getString(0) ?: ""
        }
        return ""
    }
}
