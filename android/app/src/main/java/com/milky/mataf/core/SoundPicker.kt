package com.milky.mataf.core

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.SystemClock
import com.milky.mataf.SoundPickerActivity
import com.milky.mataf.ui.components.Toasts
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.lang.ref.WeakReference

/** 선택 창과 종소리 화면 사이의 상태. Activity 재생성에는 유지하고 프로세스 종료 시에는 취소한다. */
object SoundPicker {
    const val REQUEST = "sound_picker_request"
    private val _state = MutableStateFlow(SoundPickerState(requestId = SystemClock.elapsedRealtimeNanos()))
    val state: StateFlow<SoundPickerState> = _state
    private var proxy: WeakReference<SoundPickerActivity>? = null
    private var taskId: Int? = null

    fun open(ctx: Context) {
        if (!_state.value.idle) return
        releasePermission(ctx)
        closeTasks(ctx)
        _state.value = _state.value.begin()
        try {
            ctx.startActivity(Intent(ctx, SoundPickerActivity::class.java)
                .putExtra(REQUEST, _state.value.requestId).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (e: Exception) {
            _state.value = _state.value.cancel()
            Toasts.show("파일 선택 창을 열지 못했어요: ${e.message}", "error")
        }
    }

    fun attach(activity: SoundPickerActivity, id: Long): Boolean {
        if (!_state.value.accepts(id)) return false
        proxy = WeakReference(activity)
        taskId = activity.taskId
        return true
    }

    fun detached(activity: SoundPickerActivity, id: Long) {
        if (proxy?.get() !== activity) return
        proxy = null
        if (!activity.isChangingConfigurations) {
            taskId = null
            _state.value = _state.value.result(id, null)
        }
    }

    fun result(ctx: Context, id: Long, uri: Uri?) {
        if (!_state.value.accepts(id)) return
        if (uri != null) {
            try {
                // proxy 종료 뒤에도 읽는다. 프로세스가 죽어도 다음 실행에서 반환할 수 있게 먼저 기록한다.
                val prefs = ctx.getSharedPreferences("sound_picker", Context.MODE_PRIVATE)
                check(prefs.edit().putString("uri", uri.toString()).commit())
                ctx.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            } catch (e: Exception) {
                releasePermission(ctx)
                _state.value = _state.value.result(id, null)
                Toasts.show("파일을 읽을 수 없어요: ${e.message}", "error")
                return
            }
        }
        _state.value = _state.value.result(id, uri?.toString())
    }

    fun cancel(ctx: Context) {
        if (_state.value.importing) return
        _state.value = _state.value.cancel()
        proxy?.get()?.cancelPicker()
        closeTasks(ctx)
        taskId = null
        releasePermission(ctx)
    }

    fun beginImport() { _state.value = _state.value.beginImport() }

    fun imported(ctx: Context, id: Long) {
        if (_state.value.requestId != id || !_state.value.importing) return
        releasePermission(ctx)
        _state.value = _state.value.imported(id)
    }

    fun reconcile(ctx: Context) {
        if (_state.value.idle) releasePermission(ctx)
        // 창 X/태스크 제거로 콜백이 없는 경우도 복귀 시 정리한다. 멀티 윈도우는 focus 복귀도 확인한다.
        val id = taskId ?: return
        if (_state.value.pending && tasks(ctx).none { runCatching { it.taskInfo.taskId == id }.getOrDefault(false) }) cancel(ctx)
    }

    private fun tasks(ctx: Context) = ctx.getSystemService(ActivityManager::class.java).appTasks

    private fun closeTasks(ctx: Context) {
        tasks(ctx).filter { runCatching { it.taskInfo.baseIntent.component?.className == SoundPickerActivity::class.java.name }.getOrDefault(false) }
            .forEach { it.finishAndRemoveTask() }
    }

    private fun releasePermission(ctx: Context) {
        val prefs = ctx.getSharedPreferences("sound_picker", Context.MODE_PRIVATE)
        val saved = prefs.getString("uri", null) ?: return
        try {
            ctx.contentResolver.releasePersistableUriPermission(Uri.parse(saved), Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } catch (_: SecurityException) {
            // 권한을 받기 전에 종료됐거나 제공자가 이미 회수한 경우.
        }
        prefs.edit().remove("uri").commit()
    }
}
