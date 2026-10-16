package io.github.dshpet.mobile

import kotlin.math.abs
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The union window must not move the pet. For every clip, the on-screen rect of
 * the crop has to match the per-clip window the 0.1.0 client placed, within the
 * one pixel that independent rounding can cost.
 */
class WindowGeometryTest {
    private val body = SourceBox(212.0, 60.0, 428.0, 330.0)
    private val idle = SourceBox(194.0, 58.0, 446.0, 332.0)
    private val wideClick = SourceBox(114.0, 62.0, 526.0, 332.0)
    private val tallClick = SourceBox(181.0, 17.0, 459.0, 333.0)
    private val move = SourceBox(119.0, 56.0, 521.0, 337.0)
    private val union = SourceBox(114.0, 17.0, 526.0, 337.0)
    private val scale = 1.2444

    @Test
    fun unionCoversEveryClipCrop() {
        val clips = listOf(idle, wideClick, tallClick, move).map {
            ClipSpec("clip", "idle", 24.0, 241, crop = it)
        }
        val computed = WindowGeometry.union(clips)
        assertEquals(union, computed)
        for (crop in listOf(idle, wideClick, tallClick, move)) {
            assertTrue(computed.left <= crop.left && computed.top <= crop.top)
            assertTrue(computed.right >= crop.right && computed.bottom >= crop.bottom)
        }
    }

    @Test
    fun everyClipKeepsThePositionAndSizeThePerClipWindowHad() {
        val bodyX = 300.0
        val bodyY = 400.0
        val safeLeft = 0
        val safeTop = 100
        val placement = WindowGeometry.placement(bodyX, bodyY, body, union, scale, safeLeft, safeTop)
        assertEquals((safeTop + (bodyY + union.top - body.top) * scale).toInt(), placement.y)
        for (crop in listOf(idle, wideClick, tallClick, move)) {
            val offset = WindowGeometry.contentOffset(crop, union, scale)
            val legacyLeft = (safeLeft + (bodyX + crop.left - body.left) * scale).toInt()
            val legacyTop = (safeTop + (bodyY + crop.top - body.top) * scale).toInt()
            assertTrue("clip ${crop.left} moved horizontally",
                abs((placement.x + offset.x) - legacyLeft) <= 1.5)
            assertTrue("clip ${crop.top} moved vertically",
                abs((placement.y + offset.y) - legacyTop) <= 1.5)
        }
    }

    @Test
    fun theWidestPulseFitsWithoutChangingTheBodyAnchor() {
        val offset = WindowGeometry.contentOffset(union, union, scale)
        val placement = WindowGeometry.placement(300.0, 400.0, body, union, scale, 0, 0)
        val pulse = Squash.geometry(offset.x, offset.y,
            (union.width * scale).toFloat(), (union.height * scale).toFloat(), .5)
        assertTrue("left=${pulse[0]}", pulse[0] >= 0)
        assertTrue("right=${pulse[0] + pulse[2]} window=${placement.width}",
            pulse[0] + pulse[2] <= placement.width)
        assertEquals(0f, offset.y, 0f)
    }

    @Test
    fun windowNeverCollapsesToAnEmptySurface() {
        val tiny = SourceBox(0.0, 0.0, 0.4, 0.4)
        val placement = WindowGeometry.placement(0.0, 0.0, body, tiny, .1, 0, 0)
        assertTrue(placement.width >= 1 && placement.height >= 1)
    }
}
