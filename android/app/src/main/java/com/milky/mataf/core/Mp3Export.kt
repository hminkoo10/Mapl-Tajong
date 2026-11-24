package com.milky.mataf.core

import android.content.Context
import android.net.Uri
import android.os.Process
import android.provider.DocumentsContract
import com.milky.mataf.data.Sound
import com.milky.mataf.ui.components.Toasts
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.concurrent.Executors

/**
 * 종소리를 MP3로 저장하는 일. 한 번에 하나만 하고, 다른 화면으로 옮겨 가도 이어서 한다.
 * 취소하거나 실패하면 반쯤 만든 파일은 지운다.
 */
object Mp3Export {
    /** progress: 0..1 */
    data class Saving(val soundId: Long, val name: String, val progress: Float = 0f, val cancelling: Boolean = false)

    private val _state = MutableStateFlow<Saving?>(null)
    val state: StateFlow<Saving?> = _state.asStateFlow()
    private var job: Job? = null

    // 종이 먼저 울리도록 낮은 우선순위 스레드 하나에서 바꾼다
    private val worker: CoroutineDispatcher by lazy {
        Executors.newSingleThreadExecutor { r ->
            Thread({ Process.setThreadPriority(Process.THREAD_PRIORITY_BACKGROUND); r.run() }, "mp3-export")
                .apply { isDaemon = true }
        }.asCoroutineDispatcher()
    }

    fun start(ctx: Context, sound: Sound, uri: Uri): Boolean {
        val app = ctx.applicationContext
        return run(sound.id, sound.name, CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate), worker,
            work = { report ->
                app.contentResolver.openOutputStream(uri)!!.buffered().use {
                    AudioEdit.exportMp3(Sounds.file(app, sound.fileName), it, report)
                }
            },
            discard = { runCatching { DocumentsContract.deleteDocument(app.contentResolver, uri) } })
    }

    /** start 의 본체 (시험에서는 작업과 지우기를 바꿔 넣는다) */
    internal fun run(
        soundId: Long, name: String, scope: CoroutineScope, dispatcher: CoroutineDispatcher,
        work: suspend (report: (Float) -> Unit) -> Unit, discard: () -> Unit,
    ): Boolean {
        if (_state.value != null) return false
        _state.value = Saving(soundId, name)
        job = scope.launch {
            try {
                withContext(dispatcher) {
                    work { f -> _state.update { s -> if (s == null || s.cancelling) s else s.copy(progress = f) } }
                }
                Toasts.show("MP3로 저장했어요", "success")
            } catch (e: CancellationException) {
                // 취소된 코루틴은 withContext 에서 돌아올 때 다시 취소되므로, 안내까지 이 안에서 한다
                withContext(NonCancellable + Dispatchers.IO) {
                    discard()
                    Toasts.show("저장을 취소했어요")
                }
            } catch (e: Exception) {
                withContext(NonCancellable + Dispatchers.IO) {
                    discard()
                    Toasts.show("저장하지 못했어요: ${e.message ?: e}", "error")
                }
            } finally {
                job = null
                _state.value = null
            }
        }
        return true
    }

    fun cancel() {
        val j = job ?: return
        _state.update { it?.copy(cancelling = true) }
        j.cancel()
    }
}
