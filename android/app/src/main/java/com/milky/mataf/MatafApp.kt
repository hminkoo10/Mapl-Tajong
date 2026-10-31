package com.milky.mataf

import android.app.Application
import com.milky.mataf.core.Alarms
import com.milky.mataf.core.AppEvents
import com.milky.mataf.core.BellService
import com.milky.mataf.core.Sounds
import kotlin.concurrent.thread

class MatafApp : Application() {
    override fun onCreate() {
        super.onCreate()
        BellService.createChannel(this)
        // 기본 종소리 복사(처음 한 번)는 화면을 막지 않게 뒤에서 한다
        thread(name = "seed") {
            try {
                Sounds.seed(this)
            } catch (_: Exception) {
            }
            AppEvents.changed()
        }
        Alarms.reschedule(this)
    }
}
