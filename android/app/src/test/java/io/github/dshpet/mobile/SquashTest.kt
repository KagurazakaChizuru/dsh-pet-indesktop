package io.github.dshpet.mobile

import org.junit.Assert.assertEquals
import org.junit.Test

class SquashTest {
    private val left = 40f
    private val top = 10f
    private val width = 200f
    private val height = 150f

    @Test
    fun thePulseStartsAndEndsExactlyInPlace() {
        for (progress in listOf(0.0, 1.0)) {
            val rect = Squash.geometry(left, top, width, height, progress)
            assertEquals(left, rect[0], .01f)
            assertEquals(top, rect[1], .01f)
            assertEquals(width, rect[2], .01f)
            assertEquals(height, rect[3], .01f)
        }
    }

    @Test
    fun thePeakIsWiderShorterAndStaysOnTheGround() {
        val rect = Squash.geometry(left, top, width, height, .5)
        assertEquals(width * 1.1f, rect[2], .01f)
        assertEquals(height * .85f, rect[3], .01f)
        // Bottom and centre are the anchors: the pet must not hop.
        assertEquals(top + height, rect[1] + rect[3], .01f)
        assertEquals(left + width / 2f, rect[0] + rect[2] / 2f, .01f)
    }

    @Test
    fun progressOutsideTheRangeIsClamped() {
        val before = Squash.geometry(left, top, width, height, -3.0)
        val after = Squash.geometry(left, top, width, height, 4.0)
        assertEquals(width, before[2], .01f)
        assertEquals(width, after[2], .01f)
    }

    @Test
    fun aTinyFrameStillHasAPositiveSize() {
        val rect = Squash.geometry(0f, 0f, .5f, .5f, .5)
        assertEquals(true, rect[2] >= 1f && rect[3] >= 1f)
    }

    @Test
    fun theDurationMatchesTheDesktop() {
        assertEquals(.220, Squash.DURATION_SECONDS, 1e-9)
    }
}
