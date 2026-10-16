package io.github.dshpet.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class FrameBudgetTest {
    @Test
    fun bytesAreCountedAndNothingIsDroppedWhileUnderBudget() {
        val budget = FrameBudget(100)
        budget.record("a", 30)
        budget.record("b", 30)
        budget.record("c", 30)
        assertEquals(90, budget.bytes)
        assertEquals(3, budget.size)
        assertEquals(emptyList<String>(), budget.overflow(0, emptySet()))
    }

    @Test
    fun theLeastRecentlyUsedEntryGoesFirst() {
        val budget = FrameBudget(100)
        budget.record("a", 30)
        budget.record("b", 30)
        budget.record("c", 30)
        budget.markUsed("a")
        assertEquals(listOf("b"), budget.overflow(20, emptySet()))
    }

    @Test
    fun theFramesAPetIsShowingAreNeverDropped() {
        val budget = FrameBudget(100)
        budget.record("a", 30)
        budget.record("b", 30)
        budget.record("c", 30)
        // "a" is the oldest, but the current frame of a pet must survive.
        assertEquals(listOf("b"), budget.overflow(30, setOf("a")))
    }

    @Test
    fun anEntryLargerThanTheBudgetIsStillKeptWhenItIsTheLastResort() {
        val budget = FrameBudget(100)
        budget.record("huge", 500)
        assertEquals(listOf("huge"), budget.overflow(0, emptySet()))
        // The just-decoded frame is protected, so the budget stays soft instead
        // of re-decoding the same frame forever.
        assertTrue(budget.overflow(0, setOf("huge")).isEmpty())
    }

    @Test
    fun replacingAKeyUpdatesItsWeight() {
        val budget = FrameBudget(100)
        budget.record("a", 90)
        budget.record("a", 10)
        assertEquals(10, budget.bytes)
        assertEquals(1, budget.size)
        budget.remove("a")
        assertEquals(0, budget.bytes)
    }
}
