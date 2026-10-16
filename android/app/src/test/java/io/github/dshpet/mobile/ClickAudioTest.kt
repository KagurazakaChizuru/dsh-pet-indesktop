package io.github.dshpet.mobile

import org.junit.Assert.*
import org.junit.Test

class ClickAudioTest {
    private class Output(val changed: () -> Unit) : ClickAudio.Output {
        var ready = false
        override var failed = false
        var closed = false
        var gain = -1f
        val played = mutableListOf<Pair<ClickAudio.Sound, Float>>()
        override fun ready(sound: ClickAudio.Sound) = ready
        override fun play(sound: ClickAudio.Sound, volume: Float): Boolean {
            if (!ready || closed || failed) return false
            played += sound to volume
            return true
        }
        override fun setVolume(volume: Float) { gain = volume }
        override fun close() { closed = true }
        override fun diagnostics() = "fake"
        fun prepared() { ready = true; changed() }
    }

    private class Fixture {
        var now = 0L
        val outputs = mutableListOf<Output>()
        val states = mutableListOf<ClickAudio.State>()
        var plays = 0
        val audio = ClickAudio({ _, changed -> Output(changed).also { outputs += it } },
            { now }, { states += it }, { plays++ })
        val output get() = outputs.last()
    }

    @Test fun firstTapWaitsForLoadingAndUsesTheLatestVolume() {
        val f = Fixture()
        f.audio.configure("content://picked", .7f)
        f.audio.press()
        f.audio.configure("content://picked", .3f)
        assertEquals(0, f.plays)
        f.now = 100
        f.output.prepared()
        assertEquals(listOf(ClickAudio.Sound.PRESS to .3f), f.output.played)
        assertEquals(ClickAudio.State.READY, f.states.last())
        assertEquals(1, f.outputs.size)
    }

    @Test fun pressAndReleaseHaveSeparateThrottlesEvenAtClockZero() {
        val f = Fixture()
        f.audio.configure(null, .7f)
        f.output.prepared()
        f.audio.press()
        f.now = 10
        f.audio.release()
        f.audio.press()
        f.audio.release()
        assertEquals(listOf(ClickAudio.Sound.PRESS, ClickAudio.Sound.RELEASE),
            f.output.played.map { it.first })
        f.now = 100
        f.audio.press()
        assertEquals(3, f.plays)
    }

    @Test fun pendingPairIsBoundedAndDoesNotPlayAnOldGestureMuchLater() {
        val f = Fixture()
        f.audio.configure(null, 1f)
        repeat(20) { f.now += 100; f.audio.press(); f.audio.release() }
        f.output.prepared()
        assertEquals(2, f.plays)
        f.audio.configure("content://slow", 1f)
        f.audio.press()
        f.now += 5_000
        f.output.prepared()
        assertEquals(2, f.plays)
    }

    @Test fun changingTheSourceOrClosingCancelsOldCallbacksAndPendingAudio() {
        val f = Fixture()
        f.audio.configure("content://old", .7f)
        f.audio.press()
        val old = f.output
        f.audio.configure("content://new", .7f)
        old.prepared()
        assertTrue(old.closed)
        assertEquals(0, f.plays)
        f.audio.press()
        f.audio.close()
        f.output.prepared()
        assertTrue(f.output.closed)
        assertEquals(0, f.plays)
        assertEquals(ClickAudio.State.IDLE, f.states.last())
    }

    @Test fun liveVolumeAppliesToTheOutputAndEverySubsequentPlay() {
        val f = Fixture()
        f.audio.configure(null, .7f)
        f.output.prepared()
        for (volume in listOf(0f, .5f, 1f)) {
            f.now += 100
            f.audio.configure(null, volume)
            assertEquals(volume, f.output.gain, 0f)
            f.audio.press()
            assertEquals(volume, f.output.played.last().second, 0f)
        }
    }

    @Test fun customSoundPlaysOnceAndReportsAFileError() {
        val f = Fixture()
        f.audio.configure("content://custom", 1f)
        f.output.prepared()
        f.audio.press()
        f.audio.release()
        assertEquals(1, f.plays)
        f.output.failed = true
        f.output.changed()
        assertEquals(ClickAudio.State.ERROR, f.states.last())
        f.now += 100
        f.audio.press()
        assertEquals(1, f.plays)
    }
}
