package com.milky.mataf

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import com.milky.mataf.core.SoundPicker

/** DocumentsUI를 별도 task에 두어 창의 X가 타종 앱까지 닫지 않게 한다. */
class SoundPickerActivity : Activity() {
    private val requestId get() = intent.getLongExtra(SoundPicker.REQUEST, -1)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!SoundPicker.attach(this, requestId)) {
            finishAndRemoveTask()
            return
        }
        if (savedInstanceState == null) {
            try {
                startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "audio/*"
                }, PICK_FILE)
            } catch (_: Exception) {
                SoundPicker.result(this, requestId, null)
                finishAndRemoveTask()
            }
        }
    }

    @Deprecated("플랫폼 picker를 finishActivity(requestCode)로 닫기 위해 같은 요청 번호를 쓴다.")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != PICK_FILE) return
        SoundPicker.result(this, requestId, data?.data?.takeIf { resultCode == RESULT_OK })
        finishAndRemoveTask()
    }

    fun cancelPicker() {
        finishActivity(PICK_FILE)
        finishAndRemoveTask()
    }

    override fun onDestroy() {
        SoundPicker.detached(this, requestId)
        super.onDestroy()
    }

    private companion object { const val PICK_FILE = 1 }
}
