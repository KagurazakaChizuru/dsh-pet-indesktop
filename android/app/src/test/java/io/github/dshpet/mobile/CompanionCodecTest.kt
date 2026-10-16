package io.github.dshpet.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CompanionCodecTest {
    @Test
    fun layoutRoundTripsThroughTheSinglePreferenceString() {
        val layout = listOf(.25 to .75, .5 to 1.0)
        assertEquals(layout, CompanionCodec.decode(CompanionCodec.encode(layout)))
    }

    @Test
    fun missingOrCorruptEntriesAreDroppedInsteadOfCrashing() {
        assertEquals(emptyList<Pair<Double, Double>>(), CompanionCodec.decode(null))
        assertEquals(emptyList<Pair<Double, Double>>(), CompanionCodec.decode(""))
        assertEquals(emptyList<Pair<Double, Double>>(), CompanionCodec.decode("nonsense"))
        assertEquals(emptyList<Pair<Double, Double>>(), CompanionCodec.decode("1.0;2.0"))
        assertEquals(emptyList<Pair<Double, Double>>(), CompanionCodec.decode("a,b"))
        assertEquals(listOf(.5 to .5), CompanionCodec.decode("bad;0.5,0.5"))
    }

    @Test
    fun coordinatesAreClampedAndTheCountIsCapped() {
        assertEquals(listOf(0.0 to 1.0), CompanionCodec.decode("-2,3"))
        val many = List(9) { 0.1 to 0.2 }
        assertEquals(CompanionCodec.MAX_COMPANIONS, CompanionCodec.decode(CompanionCodec.encode(many)).size)
        assertEquals(CompanionCodec.MAX_COMPANIONS, CompanionCodec.encode(many).split(';').size)
    }

    @Test
    fun companionsAreSmallerThanTheMotherAndOffsetFromHerBody() {
        assertTrue(CompanionCodec.COMPANION_SCALE in 0.0..1.0)
        assertEquals(24.0, CompanionCodec.spawnOffset(1), 0.0)
        assertEquals(48.0, CompanionCodec.spawnOffset(2), 0.0)
        assertFalse(CompanionCodec.spawnOffset(0) == 0.0)
    }
}
