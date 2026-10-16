package io.github.dshpet.mobile

import org.junit.Assert.*
import org.junit.Test

class PetEngineTest {
    private val clips = listOf(
        ClipSpec("idle", "idle", 24.0, 24),
        ClipSpec("turn", "turn", 24.0, 12),
        ClipSpec("walk", "move", 24.0, 24, stride = 120.0),
        ClipSpec("click", "click", 24.0, 12),
        ClipSpec("drag", "drag", 24.0, 24),
    )
    private fun engine() = PetEngine(clips, random = kotlin.random.Random(7)).apply {
        resize(300.0, 600.0)
        restorePosition(.5, .5)
    }

    @Test fun clickPlaysOnceThenReturnsToIdle() {
        val e = engine()
        e.click()
        assertEquals(PetMode.CLICK, e.mode)
        repeat(20) { e.advance(.05) }
        assertEquals(PetMode.IDLE, e.mode)
    }

    @Test fun draggingOwnsPositionAndReleaseClampsSpeed() {
        val e = engine()
        e.beginDrag()
        e.dragTo(1000.0, -200.0)
        e.advance(.05)
        assertEquals(300.0, e.x, .001)
        assertEquals(0.0, e.y, .001)
        e.release(100000.0, -100000.0)
        assertEquals(PetMode.THROWN, e.mode)
        assertTrue(kotlin.math.hypot(e.vx, e.vy) <= 4800.01)
    }

    @Test fun throwSettlesAndAlwaysStaysInBounds() {
        val e = engine()
        e.beginDrag()
        e.release(650.0, -500.0)
        repeat(1200) {
            e.advance(1.0 / 60)
            assertTrue(e.x in 0.0..300.0 && e.y in 0.0..600.0)
        }
        assertNotEquals(PetMode.THROWN, e.mode)
    }

    @Test fun pauseAndScreenOffFreezeWithoutCatchingUp() {
        val e = engine()
        e.beginDrag()
        e.release(300.0, 200.0)
        e.paused = true
        val x = e.x
        val y = e.y
        e.advance(60.0)
        assertEquals(x, e.x, 0.0)
        assertEquals(y, e.y, 0.0)
        e.paused = false
        e.advance(.016)
        assertTrue(kotlin.math.abs(e.x - x) < 10)
    }

    @Test fun rotationPreservesRelativePositionAndHandlesZeroBounds() {
        val e = engine()
        e.restorePosition(.25, .75)
        e.resize(600.0, 300.0)
        assertEquals(150.0, e.x, .001)
        assertEquals(225.0, e.y, .001)
        e.resize(0.0, 0.0)
        assertEquals(0.0, e.x, 0.0)
        assertEquals(0.0, e.y, 0.0)
    }

    @Test fun disablingWanderKeepsPetStillAfterIdleCycles() {
        val e = engine()
        e.wander = false
        val x = e.x
        repeat(300) { e.advance(.05) }
        assertEquals(x, e.x, 0.0)
    }

    @Test fun desktopThrowReferenceMatchesMobileIntegration() {
        val result = ThrowMath.step(100.0, 200.0, 400.0, -300.0, .016,
            300.0, 600.0)
        assertEquals(106.4, result.x, .0001)
        assertEquals(195.5584, result.y, .0001)
        assertEquals(-277.6, result.vy, .0001)
    }
}
