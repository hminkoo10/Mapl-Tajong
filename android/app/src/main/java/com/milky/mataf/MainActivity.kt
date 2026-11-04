package com.milky.mataf

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.KeyEvent
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import com.milky.mataf.core.Alarms
import com.milky.mataf.core.SoundPicker
import com.milky.mataf.core.Updates
import com.milky.mataf.data.Repo
import com.milky.mataf.ui.App
import com.milky.mataf.ui.theme.MatafTheme

class MainActivity : ComponentActivity() {
    private val askNotif = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
        )
        super.onCreate(savedInstanceState)
        setContent { MatafTheme { App() } }
        if (savedInstanceState == null) askNotificationOnce()
    }

    override fun onResume() {
        super.onResume()
        SoundPicker.reconcile(this)
        // 권한이나 시각이 바뀌었을 수 있으니 다음 종을 다시 건다
        Alarms.reschedule(this)
        Updates.onAppVisible(this)
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) SoundPicker.reconcile(this)
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.keyCode == KeyEvent.KEYCODE_ESCAPE && SoundPicker.state.value.pending) {
            if (event.action == KeyEvent.ACTION_UP) SoundPicker.cancel(this)
            return true
        }
        return super.dispatchKeyEvent(event)
    }

    private fun askNotificationOnce() {
        if (Build.VERSION.SDK_INT < 33) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) return
        val repo = Repo(this)
        if (repo.setting("asked_notif", "0") == "1") return
        repo.setSetting("asked_notif", "1")
        askNotif.launch(Manifest.permission.POST_NOTIFICATIONS)
    }
}
