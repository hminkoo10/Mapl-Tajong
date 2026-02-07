package com.milky.mataf.alarm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class BootReceiver : BroadcastReceiver() {

    companion object {
        private const val PREFS_NAME = "mataf_prefs"
        private const val KEY_SUSPEND_UNTIL_OPEN = "suspend_until_open"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return

        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        if (prefs.getBoolean(KEY_SUSPEND_UNTIL_OPEN, false)) {
            return
        }

        AlarmScheduler.rescheduleNext(context)
    }
}
