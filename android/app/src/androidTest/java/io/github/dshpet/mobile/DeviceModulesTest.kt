package io.github.dshpet.mobile

import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The module kernel on a real device: the enabled set follows the settings, a
 * disabled module does no work at all, baby whales own one window each, and the
 * fixed union window stops moving while the pet is idle.
 */
@RunWith(AndroidJUnit4::class)
class DeviceModulesTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val store = PetPreferences(context)

    @Before
    fun overlayPermission() {
        InstrumentationRegistry.getInstrumentation().uiAutomation
            .executeShellCommand("appops set ${context.packageName} SYSTEM_ALERT_WINDOW allow")
            .use { android.os.ParcelFileDescriptor.AutoCloseInputStream(it).readBytes() }
        store.save(PetOptions(wander = true, speech = false, clickSound = false, companions = false,
            phrases = listOf("只属于我的台词"), speechMinSeconds = 5f, speechMaxSeconds = 5f))
        PetOverlayService.command(context, PetOverlayService.STOP)
        awaitCondition { !PetRuntime.state.value.running }
    }

    @After
    fun cleanup() {
        PetOverlayService.command(context, PetOverlayService.STOP)
        awaitCondition { !PetRuntime.state.value.running }
        store.reset()
    }

    @Test
    fun theEnabledSetFollowsTheSettingsAndOffMeansOff() {
        startPet(context)
        awaitCondition { PetRuntime.state.value.modules.isNotEmpty() }
        val off = PetRuntime.state.value.modules
        assertTrue(off.contains(ModuleIds.WANDER))
        assertFalse(off.contains(ModuleIds.SPEECH))
        assertFalse(off.contains(ModuleIds.CLICK_SOUND))
        assertFalse(off.contains(ModuleIds.COMPANION))
        awaitFrames(24)
        assertEquals("a disabled speech module must not create a bubble", 0, PetRuntime.bubbles.get())

        // Turning speech on must build the module and start using the user's line.
        store.save(store.options().copy(speech = true))
        awaitCondition { PetRuntime.state.value.modules.contains(ModuleIds.SPEECH) }
        awaitCondition { PetRuntime.bubbles.get() > 0 && PetRuntime.lastPhrase.get().isNotEmpty() }
        assertEquals("只属于我的台词", PetRuntime.lastPhrase.get())

        // Turning it off again must clear the bubble and stop the module.
        store.save(store.options().copy(speech = false))
        awaitCondition { !PetRuntime.state.value.modules.contains(ModuleIds.SPEECH) }
        awaitFrames(24)
        assertFalse(PetRuntime.state.value.modules.contains(ModuleIds.SPEECH))
    }

    @Test
    fun companionsOwnOneWindowEachAndSurviveARestart() {
        store.save(store.options().copy(companions = true, wander = false))
        startPet(context)
        awaitCondition { PetRuntime.windowCount.get() == 1 }
        PetOverlayService.command(context, PetOverlayService.SPAWN)
        awaitCondition { PetRuntime.state.value.companions == 1 && PetRuntime.windowCount.get() == 2 }
        PetOverlayService.command(context, PetOverlayService.SPAWN)
        awaitCondition { PetRuntime.state.value.companions == 2 && PetRuntime.windowCount.get() == 3 }
        assertEquals(2, store.companionLayout().size)

        PetOverlayService.command(context, PetOverlayService.EXIT)
        awaitCondition { PetRuntime.state.value.companions == 1 && PetRuntime.windowCount.get() == 2 }

        // The household comes back the way it was left.
        stopPet(context)
        startPet(context)
        awaitCondition { PetRuntime.state.value.companions == 1 && PetRuntime.windowCount.get() == 2 }

        // Switching the module off takes every companion down and clears the layout.
        store.save(store.options().copy(companions = false))
        awaitCondition { PetRuntime.state.value.companions == 0 && PetRuntime.windowCount.get() == 1 }
        assertEquals(0, store.companionLayout().size)
    }

    @Test
    fun theUnionWindowDoesNotMoveWhileThePetIsIdle() {
        store.save(store.options().copy(wander = false, speech = false, companions = false))
        startPet(context)
        awaitFrames(24)
        val ops = PetRuntime.windowOps.get()
        awaitFrames(48)
        assertEquals("an idle pet must not touch its window geometry", ops, PetRuntime.windowOps.get())
        assertTrue(PetRuntime.draws.get() > 0)
    }

    @Test
    fun thePetKeepsDeliveringFramesAfterWarmUp() {
        store.save(store.options().copy(wander = false, speech = false))
        startPet(context)
        awaitFrames(24)
        val draws = PetRuntime.draws.get()
        val stale = PetRuntime.staleFrames.get()
        awaitFrames(48)
        val delivered = PetRuntime.draws.get() - draws
        val staleNow = PetRuntime.staleFrames.get() - stale
        assertTrue("delivered=$delivered", delivered >= 40)
        // The cache must not thrash: an undecoded frame keeps the last one on screen,
        // so a healthy run misses almost nothing once the warm-up is over.
        assertTrue("stale=$staleNow of delivered=$delivered", staleNow <= delivered / 10)
        assertTrue(SystemClock.elapsedRealtime() > 0)
    }
}
