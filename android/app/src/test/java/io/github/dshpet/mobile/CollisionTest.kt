package io.github.dshpet.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CollisionTest {
    private val bodyWidth = 216.0
    private val bodyHeight = 270.0

    private fun body(id: Int, left: Double, top: Double = 0.0, vx: Double = 0.0, vy: Double = 0.0,
                     ratio: Double = 1.0, immovable: Boolean = false) = CollisionBody(
        id = id,
        left = left,
        top = top,
        width = bodyWidth * ratio,
        height = bodyHeight * ratio,
        vx = vx,
        vy = vy,
        mass = Collision.mass(ratio),
        immovable = immovable)

    @Test
    fun theShapeIsAThreeCircleChainInscribedInTheBodyBox() {
        val circles = Collision.circles(0.0, 0.0, 216.0, 270.0)
        assertEquals(3, circles.size)
        val radius = 108.0
        assertTrue(circles.all { it[2] == radius })
        // Taller than wide: the chain runs down the middle.
        assertEquals(listOf(108.0, 108.0, 108.0, 135.0, 108.0, 162.0),
            circles.flatMap { listOf(it[0], it[1]) })
    }

    @Test
    fun aWideBodySpreadsTheChainHorizontally() {
        val circles = Collision.circles(0.0, 0.0, 400.0, 100.0)
        assertEquals(listOf(50.0, 50.0, 200.0, 50.0, 350.0, 50.0),
            circles.flatMap { listOf(it[0], it[1]) })
    }

    @Test
    fun twoOverlappingPetsArePushedApart() {
        val a = body(0, 0.0)
        val b = body(1, 196.0) // 20 px of overlap
        val outcomes = Collision.solve(listOf(a, b), Collision.RESTITUTION, 1.0 / 24)
        val first = outcomes.first { it.id == 0 }
        val second = outcomes.first { it.id == 1 }
        assertTrue("A must move left, dx=${first.dx}", first.dx < 0)
        assertTrue("B must move right, dx=${second.dx}", second.dx > 0)
        assertEquals(first.dx, -second.dx, .01)
        assertEquals("static overlap is inelastic", 0.0, first.impulse, 0.0)
    }

    @Test
    fun theLighterBodyTakesMoreOfThePush() {
        val mother = body(0, 0.0)
        val baby = body(1, 196.0, ratio = CompanionCodec.COMPANION_SCALE)
        val outcomes = Collision.solve(listOf(mother, baby), Collision.RESTITUTION, 1.0 / 24)
        val moved = outcomes.first { it.id == 0 }
        val pushed = outcomes.first { it.id == 1 }
        assertTrue(kotlin.math.abs(pushed.dx) > kotlin.math.abs(moved.dx))
    }

    @Test
    fun aFastPetBouncesTheOneItHits() {
        val a = body(0, 0.0, vx = 1000.0)
        val b = body(1, 196.0)
        val outcomes = Collision.solve(listOf(a, b), Collision.RESTITUTION, 1.0 / 24)
        val first = outcomes.first { it.id == 0 }
        val second = outcomes.first { it.id == 1 }
        assertTrue("A must slow down, dvx=${first.dvx}", first.dvx < 0)
        assertTrue("B must be thrown, dvx=${second.dvx}", second.dvx > 0)
        assertTrue("a real hit must clear HIT_MIN_DV, impulse=${first.impulse}",
            first.hit && second.hit)
    }

    @Test
    fun petsThatAreAlreadySeparatingGetNoImpulse() {
        val a = body(0, 0.0, vx = -900.0)
        val b = body(1, 196.0)
        val outcomes = Collision.solve(listOf(a, b), Collision.RESTITUTION, 1.0 / 24)
        assertEquals(0.0, outcomes.first { it.id == 0 }.impulse, 0.0)
        assertEquals(0.0, outcomes.first { it.id == 1 }.impulse, 0.0)
    }

    @Test
    fun aThrownPetIsNotMissedBetweenTwoFrames() {
        // Both the start and the end of the step are clear of each other, but the
        // straight line between them goes through the other pet.
        val a = body(0, 108.0, vx = 14400.0)
        val b = body(1, 108.0 + 300.0)
        val outcomes = Collision.solve(listOf(a, b), Collision.RESTITUTION, 1.0 / 24)
        assertNotNull(outcomes)
        val first = outcomes.first { it.id == 0 }
        assertTrue("the swept test must catch this pass-through, dx=${first.dx}", first.moved)
        assertTrue("and it must count as a real hit, impulse=${first.impulse}", first.hit)
    }

    @Test
    fun aDraggedPetPushesOthersButIsNeverMoved() {
        val dragged = body(0, 0.0, immovable = true)
        val other = body(1, 196.0)
        val outcomes = Collision.solve(listOf(dragged, other), Collision.RESTITUTION, 1.0 / 24)
        val held = outcomes.first { it.id == 0 }
        val pushed = outcomes.first { it.id == 1 }
        assertEquals(0.0, held.dx, 0.0)
        assertEquals(0.0, held.dy, 0.0)
        assertTrue("the finger always wins", held.dvx == 0.0 && held.dvy == 0.0)
        assertTrue(kotlin.math.abs(pushed.dx) > 0.0)
    }

    @Test
    fun massClampsLikeTheDesktopAndGrowsWithSize() {
        assertEquals(.5, Collision.mass(.1), 1e-9)
        assertEquals(.5625, Collision.mass(CompanionCodec.COMPANION_SCALE), 1e-9)
        assertEquals(1.0, Collision.mass(1.0), 1e-9)
        assertEquals(2.5, Collision.mass(9.0), 1e-9)
    }

    @Test
    fun aSinglePetHasNothingToCollideWith() {
        assertEquals(emptyList<CollisionOutcome>(),
            Collision.solve(listOf(body(0, 0.0)), Collision.RESTITUTION, 1.0 / 24))
    }

    @Test
    fun identicalCentresStillSeparateDeterministically() {
        val a = body(0, 0.0)
        val b = body(1, 0.0)
        val first = Collision.solve(listOf(a, b), Collision.RESTITUTION, 1.0 / 24)
        val second = Collision.solve(listOf(a, b), Collision.RESTITUTION, 1.0 / 24)
        assertEquals(first.map { it.dx to it.dy }, second.map { it.dx to it.dy })
    }
}
