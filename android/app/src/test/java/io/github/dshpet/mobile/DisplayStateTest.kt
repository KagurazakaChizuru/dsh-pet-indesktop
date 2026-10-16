package io.github.dshpet.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The rule that fixes the click flash: the bitmap and the crop it belongs to
 * are replaced together or not at all. Shipping 0.1.0 assigned the crop
 * unconditionally, so an undecoded frame painted the old image with the next
 * clip's geometry.
 */
class DisplayStateTest {
    private val idle = SourceBox(194.0, 58.0, 446.0, 332.0)
    private val click = SourceBox(114.0, 62.0, 526.0, 332.0)

    @Test
    fun undecodedFrameKeepsThePreviousCropAndBitmap() {
        val display = DisplayState<String>()
        assertTrue(display.present("idle-frame", 1L, idle, false))
        assertFalse(display.present(null, -1L, click, false))
        assertEquals(idle, display.frame?.crop)
        assertEquals("idle-frame", display.frame?.bitmap)
    }

    @Test
    fun nothingIsShownBeforeTheFirstDecodedFrame() {
        val display = DisplayState<String>()
        assertFalse(display.present(null, -1L, click, false))
        assertNull(display.frame)
    }

    @Test
    fun sameRevisionAndCropNeedsNoRedraw() {
        val display = DisplayState<String>()
        assertTrue(display.present("frame", 7L, idle, false))
        assertFalse(display.present("frame", 7L, idle, false))
    }

    @Test
    fun newRevisionRedrawsEvenWhenTheBitmapObjectIsReused() {
        val display = DisplayState<String>()
        assertTrue(display.present("pooled-bitmap", 1L, idle, false))
        assertTrue(display.present("pooled-bitmap", 2L, idle, false))
    }

    @Test
    fun mirrorChangeRedrawsAndClearDropsTheFrame() {
        val display = DisplayState<String>()
        assertTrue(display.present("frame", 1L, idle, false))
        assertTrue(display.present("frame", 1L, idle, true))
        display.clear()
        assertNull(display.frame)
    }
}
