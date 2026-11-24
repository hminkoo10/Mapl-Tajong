package com.milky.mataf.core

import com.milky.mataf.ui.components.Toasts
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.File

class Mp3ExportTest {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    @After
    fun tearDown() {
        Mp3Export.cancel()
        waitFor { Mp3Export.state.value == null }
        scope.cancel()
        Toasts.dismiss()
    }

    private fun waitFor(what: () -> Boolean) {
        repeat(500) {
            if (what()) return
            Thread.sleep(10)
        }
        assertTrue(what())
    }

    @Test
    fun showsProgressAndSavesOneAtATime() {
        val gate = CompletableDeferred<Unit>()
        var discarded = false
        assertTrue(Mp3Export.run(7, "1교시 종", scope, Dispatchers.IO,
            work = { report -> report(0.25f); gate.await(); report(1f) }, discard = { discarded = true }))
        waitFor { Mp3Export.state.value?.progress == 0.25f }
        assertEquals(Mp3Export.Saving(7, "1교시 종", 0.25f), Mp3Export.state.value)
        // 저장하는 동안 다른 종소리를 또 저장하려 하면 받지 않는다
        assertFalse(Mp3Export.run(8, "쉬는 시간", scope, Dispatchers.IO, work = {}, discard = {}))
        assertEquals(7L, Mp3Export.state.value?.soundId)

        gate.complete(Unit)
        waitFor { Mp3Export.state.value == null }
        assertEquals("MP3로 저장했어요", Toasts.current.value?.text)
        assertEquals("success", Toasts.current.value?.kind)
        assertFalse(discarded)
    }

    @Test
    fun cancelRemovesHalfMadeFile() {
        var discarded = false
        Mp3Export.run(7, "긴 노래", scope, Dispatchers.IO,
            work = { report -> report(0.4f); awaitCancellation() }, discard = { discarded = true })
        waitFor { Mp3Export.state.value?.progress == 0.4f }
        Mp3Export.cancel()
        waitFor { Mp3Export.state.value == null }
        assertTrue(discarded)
        assertEquals("저장을 취소했어요", Toasts.current.value?.text)
        // 끝나면 다시 저장할 수 있다
        assertTrue(Mp3Export.run(7, "긴 노래", scope, Dispatchers.IO, work = {}, discard = {}))
        waitFor { Mp3Export.state.value == null }
    }

    @Test
    fun failureRemovesHalfMadeFileAndSaysWhy() {
        var discarded = false
        Mp3Export.run(7, "종", scope, Dispatchers.IO,
            work = { throw IllegalStateException("남은 공간이 없어요.") }, discard = { discarded = true })
        waitFor { Mp3Export.state.value == null }
        assertTrue(discarded)
        assertEquals("저장하지 못했어요: 남은 공간이 없어요.", Toasts.current.value?.text)
        assertEquals("error", Toasts.current.value?.kind)
    }

    private fun mp3File(size: Int): File =
        File.createTempFile("bell", ".mp3").apply { deleteOnExit(); writeBytes(ByteArray(size) { (it * 7).toByte() }) }

    @Test
    fun mp3IsCopiedAsIsWithProgressEveryPercent() = runBlocking {
        val src = mp3File(3_000_000)
        val out = ByteArrayOutputStream()
        val seen = mutableListOf<Float>()
        AudioEdit.exportMp3(src, out) { seen += it }
        assertArrayEquals(src.readBytes(), out.toByteArray())
        assertEquals(1f, seen.last())
        assertEquals(seen.sorted().distinct(), seen)          // 1% 오를 때만, 뒤로 가지 않게
        assertTrue(seen.size in 2..101)
    }

    @Test
    fun cancellingStopsCopyMidway() = runBlocking {
        val src = mp3File(3_000_000)
        val out = ByteArrayOutputStream()
        val job = launch(Dispatchers.IO) {
            AudioEdit.exportMp3(src, out) { if (it >= 0.1f) this.cancel() }
        }
        job.join()
        assertTrue(job.isCancelled)
        assertTrue(out.size() in 1 until src.length().toInt())
    }
}
