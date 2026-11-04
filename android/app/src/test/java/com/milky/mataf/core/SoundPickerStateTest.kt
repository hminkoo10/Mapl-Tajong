package com.milky.mataf.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SoundPickerStateTest {
    @Test
    fun pickerBackClearsPendingAndAllowsAnotherSelection() {
        val first = SoundPickerState().begin()
        val cancelled = first.result(first.requestId, null)
        assertTrue(cancelled.idle)
        val next = cancelled.begin()
        assertTrue(next.pending)
        assertEquals("content://sounds/bell", next.result(next.requestId, "content://sounds/bell").uri)
    }

    @Test
    fun appCancelIgnoresALateSelectionFromTheClosedWindow() {
        val picking = SoundPickerState().begin()
        val cancelled = picking.cancel()
        assertTrue(cancelled.idle)
        assertEquals(cancelled, cancelled.result(picking.requestId, "content://sounds/late"))
    }

    @Test
    fun oldWindowDestructionDoesNotCancelTheNewWindow() {
        val first = SoundPickerState().begin()
        val next = first.cancel().begin()
        assertEquals(next, next.result(first.requestId, null))
        assertEquals(next, next.result(first.requestId, "content://sounds/old"))
    }

    @Test
    fun repeatedOpenDoesNotCreateASecondPendingRequest() {
        val picking = SoundPickerState().begin()
        assertEquals(picking, picking.begin())
    }

    @Test
    fun proxyDestructionAfterSelectionKeepsTheSheetUntilDismissed() {
        val picking = SoundPickerState().begin()
        val selected = picking.result(picking.requestId, "content://sounds/bell")
        assertFalse(selected.pending)
        assertEquals(selected, selected.result(picking.requestId, null))
        assertEquals(selected, selected.begin())
        assertTrue(selected.cancel().idle)
    }

    @Test
    fun importRetainsTheSelectionUntilItsOwnCompletion() {
        val picking = SoundPickerState().begin()
        val importing = picking.result(picking.requestId, "content://sounds/bell").beginImport()
        assertEquals(importing, importing.cancel())
        assertEquals(importing, importing.begin())
        assertEquals(importing, importing.imported(picking.requestId - 1))
        assertTrue(importing.imported(picking.requestId).idle)
    }
}
