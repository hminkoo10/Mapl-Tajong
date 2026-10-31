package com.milky.mataf.core

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import com.milky.mataf.MainActivity
import com.milky.mataf.data.Repo
import java.time.ZoneId

/**
 * 다음 종 하나만 AlarmManager 에 '알람 시계'로 걸어 둔다. (절전 중에도 정확히 깨어난다)
 * 종이 울리면 그다음 종을 다시 건다. 시간표가 바뀔 때도 다시 건다.
 */
object Alarms {
    private const val REQ_RING = 7001
    private const val REQ_SHOW = 7002
    const val ACTION_RING = "com.milky.mataf.RING"
    const val EXTRA_ID = "schedule_id"
    const val EXTRA_AT = "run_at"

    fun canExact(ctx: Context): Boolean {
        val am = ctx.getSystemService(AlarmManager::class.java)
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.S || am.canScheduleExactAlarms()
    }

    fun openExactSettings(ctx: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            ctx.startActivity(Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM).apply {
                data = Uri.parse("package:${ctx.packageName}")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            })
        }
    }

    private fun ringIntent(ctx: Context, id: Long = -1, at: Long = 0): PendingIntent {
        val i = Intent(ctx, RingReceiver::class.java).apply {
            action = ACTION_RING
            putExtra(EXTRA_ID, id)
            putExtra(EXTRA_AT, at)
        }
        return PendingIntent.getBroadcast(ctx, REQ_RING, i, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    private fun showIntent(ctx: Context): PendingIntent {
        val i = Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        return PendingIntent.getActivity(ctx, REQ_SHOW, i, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    /** 다음 종을 다시 계산해서 건다. 멈춤 중이거나 종이 없으면 걸린 알람을 지운다. */
    fun reschedule(ctx: Context) {
        val am = ctx.getSystemService(AlarmManager::class.java)
        val repo = Repo(ctx)
        val ev = if (Scheduler.isPaused(repo)) null else Scheduler.next(repo)
        if (ev == null) {
            am.cancel(ringIntent(ctx))
            AppEvents.changed()
            return
        }
        val at = ev.runAt.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
        val pi = ringIntent(ctx, ev.scheduleId, at)
        try {
            if (canExact(ctx)) {
                am.setAlarmClock(AlarmManager.AlarmClockInfo(at, showIntent(ctx)), pi)
            } else {
                // 정확한 알람 권한이 없을 때: 조금 늦을 수 있지만 절전 중에도 울리게
                am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi)
            }
        } catch (e: SecurityException) {
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi)
        }
        AppEvents.changed()
    }
}

/** 알람이 울리면 종을 울리는 서비스를 깨운다. */
class RingReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        val id = intent.getLongExtra(Alarms.EXTRA_ID, -1)
        val at = intent.getLongExtra(Alarms.EXTRA_AT, 0)
        if (id >= 0) BellService.ringScheduled(ctx, id, at) else Alarms.reschedule(ctx)
    }
}

/** 부팅·앱 업데이트·시간 변경 뒤에 다음 종을 다시 건다. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        Alarms.reschedule(ctx)
    }
}
