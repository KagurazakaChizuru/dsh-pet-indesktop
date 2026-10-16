package io.github.dshpet.mobile

import org.junit.Assert.assertEquals
import org.junit.Test

class LookaheadPlannerTest {
    private fun clip(id: String, frames: Int) =
        ClipSpec(id, "idle", 24.0, frames, crop = SourceBox(0.0, 0.0, 10.0, 10.0))

    @Test
    fun everyConsumerGetsItsCurrentFrameBeforeAnyoneGetsLookAhead() {
        val plan = LookaheadPlanner.pending(
            listOf(CursorState(clip("a", 10), 3), CursorState(clip("b", 10), 5)), 2) { false }
        assertEquals(listOf("a:3", "b:5", "a:4", "b:6", "a:5", "b:7"), plan.map { it.key })
    }

    @Test
    fun duplicatesAndUnavailableFramesAreSkipped() {
        val shared = clip("a", 10)
        val plan = LookaheadPlanner.pending(
            listOf(CursorState(shared, 1), CursorState(shared, 1)), 2) { it == "a:2" }
        assertEquals(listOf("a:1", "a:3"), plan.map { it.key })
    }

    @Test
    fun lookAheadWrapsAroundTheClip() {
        val plan = LookaheadPlanner.pending(listOf(CursorState(clip("a", 3), 2)), 3) { false }
        assertEquals(listOf("a:2", "a:0", "a:1"), plan.map { it.key })
    }

    @Test
    fun aSingleFrameClipAsksForItselfOnlyOnce() {
        val plan = LookaheadPlanner.pending(listOf(CursorState(clip("a", 1), 0)), 4) { false }
        assertEquals(listOf("a:0"), plan.map { it.key })
    }

    @Test
    fun noConsumersMeansNoWork() {
        assertEquals(emptyList<FrameRequest>(),
            LookaheadPlanner.pending(emptyList(), 4) { false })
    }
}
