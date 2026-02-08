package com.milky.mataf.alarm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.milky.mataf.data.SoundRepo

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val action = intent?.action ?: return
        if (action != Intent.ACTION_BOOT_COMPLETED &&
            action != Intent.ACTION_LOCKED_BOOT_COMPLETED &&
            action != Intent.ACTION_MY_PACKAGE_REPLACED
        ) return

        SoundRepo(context).seedBuiltInFromAssets()
        AlarmScheduler.rescheduleNext(context)
    }
}
