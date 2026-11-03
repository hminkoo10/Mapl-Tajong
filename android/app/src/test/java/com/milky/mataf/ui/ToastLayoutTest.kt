package com.milky.mataf.ui

import androidx.compose.ui.unit.dp
import com.milky.mataf.ui.components.toastBottomInset
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ToastLayoutTest {
    @Test
    fun noSelectionKeepsNormalToastPosition() {
        assertEquals(68.dp, toastBottomInset(false, 0.dp))
        assertEquals(8.dp, toastBottomInset(true, 0.dp))
    }

    @Test
    fun measuredSelectionBarClearsToastOnPhoneAndTablet() {
        for (wide in listOf(false, true)) {
            for (height in listOf(78.dp, 100.dp, 140.dp)) {
                val contentBottom = if (wide) 0.dp else 61.dp
                val barTopInset = contentBottom + height - 12.dp
                val toastBottom = toastBottomInset(wide, height) + 16.dp
                assertTrue(toastBottom > barTopInset)
            }
        }
    }

    @Test
    fun dismissalRemovesOnlyMeasuredSelectionInset() {
        for (wide in listOf(false, true)) {
            assertEquals(100.dp, toastBottomInset(wide, 100.dp) - toastBottomInset(wide, 0.dp))
        }
    }
}
