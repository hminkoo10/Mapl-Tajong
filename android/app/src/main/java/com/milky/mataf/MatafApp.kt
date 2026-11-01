package com.milky.mataf

import android.app.Activity
import android.app.Application
import android.os.Bundle
import com.milky.mataf.core.Alarms
import com.milky.mataf.core.AppEvents
import com.milky.mataf.core.BellService
import com.milky.mataf.core.Cloud
import com.milky.mataf.core.CloudService
import com.milky.mataf.core.Sounds
import kotlin.concurrent.thread

class MatafApp : Application() {
    override fun onCreate() {
        super.onCreate()
        BellService.createChannel(this)
        CloudService.createChannel(this)
        Cloud.init(this)
        // 화면이 보이는 동안만 클라우드 실시간 알림에 붙어 있는다 (종을 울리는 기기는 CloudService 가 계속)
        registerActivityLifecycleCallbacks(object : ActivityLifecycleCallbacks {
            private var started = 0
            override fun onActivityStarted(a: Activity) { if (started++ == 0) Cloud.onVisible(true) }
            override fun onActivityStopped(a: Activity) { if (--started == 0) Cloud.onVisible(false) }
            override fun onActivityCreated(a: Activity, b: Bundle?) {}
            override fun onActivityResumed(a: Activity) {}
            override fun onActivityPaused(a: Activity) {}
            override fun onActivitySaveInstanceState(a: Activity, b: Bundle) {}
            override fun onActivityDestroyed(a: Activity) {}
        })
        // 기본 종소리 복사(처음 한 번)는 화면을 막지 않게 뒤에서 한다
        thread(name = "seed") {
            try {
                Sounds.seed(this)
            } catch (_: Exception) {
            }
            AppEvents.changed()
        }
        Alarms.reschedule(this)
        CloudService.sync(this)
    }
}
