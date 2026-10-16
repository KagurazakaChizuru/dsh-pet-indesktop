package io.github.dshpet.mobile.modules

import io.github.dshpet.mobile.ModuleIds
import io.github.dshpet.mobile.PetOptions
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Off costs nothing" is the point of the module kernel, so it is asserted
 * directly: a disabled module is never even constructed, and it never sees a
 * frame, an event or a menu request.
 */
class ModuleRegistryTest {
    private class Spy(override val id: String) : PetModule {
        var enabled = 0
        var disabled = 0
        var frames = 0
        var events = 0
        var optionChanges = 0

        override fun enable(host: ModuleHost) {
            enabled++
        }

        override fun disable() {
            disabled++
        }

        override fun onFrame(pet: io.github.dshpet.mobile.PetHandle, dt: Double) {
            frames++
        }

        override fun onEvent(event: PetEvent) {
            events++
        }

        override fun menuItems(pet: io.github.dshpet.mobile.PetHandle) = listOf(ModuleMenu(0) { })

        override fun onOptionsChanged() {
            optionChanges++
        }
    }

    private class Fixture(options: PetOptions) {
        val host = FakeHost(options)
        var constructed = 0
        val speech = Spy(ModuleIds.SPEECH)
        val sound = Spy(ModuleIds.CLICK_SOUND)
        val registry = ModuleRegistry(host, listOf(
            ModuleFactory(ModuleIds.SPEECH) { constructed++; speech },
            ModuleFactory(ModuleIds.CLICK_SOUND) { constructed++; sound },
        ))
    }

    @Test
    fun aDisabledModuleIsNeverConstructed() {
        val fixture = Fixture(PetOptions(speech = false, clickSound = false))
        fixture.registry.apply()
        assertEquals(0, fixture.constructed)
        assertEquals(0, fixture.speech.enabled)
        assertNull(fixture.registry.instance(ModuleIds.SPEECH))
        assertFalse(fixture.registry.isActive(ModuleIds.SPEECH))
    }

    @Test
    fun aDisabledModuleSeesNoFramesEventsOrMenus() {
        val fixture = Fixture(PetOptions(speech = false, clickSound = false))
        fixture.registry.apply()
        val pet = FakeHost.pet()
        fixture.registry.onFrame(pet, .016)
        fixture.registry.onEvent(PetEvent.Clicked(pet))
        assertEquals(emptyList<ModuleMenu>(), fixture.registry.menuItems(pet))
        assertEquals(0, fixture.speech.frames)
        assertEquals(0, fixture.speech.events)
        assertEquals(0L, fixture.registry.framesDispatched)
    }

    @Test
    fun enablingConstructsOnceAndDisablingReleasesExactlyOnce() {
        val fixture = Fixture(PetOptions(speech = true, clickSound = false))
        fixture.registry.apply()
        fixture.registry.apply()
        assertEquals(1, fixture.constructed)
        assertEquals(1, fixture.speech.enabled)
        assertTrue(fixture.registry.isActive(ModuleIds.SPEECH))

        fixture.host.options = fixture.host.options.copy(speech = false)
        fixture.registry.apply()
        fixture.registry.apply()
        assertEquals(1, fixture.speech.disabled)
        assertNull(fixture.registry.instance(ModuleIds.SPEECH))
        assertEquals(0, fixture.sound.enabled)
    }

    @Test
    fun framesAndEventsReachOnlyTheActiveModules() {
        val fixture = Fixture(PetOptions(speech = true, clickSound = false))
        fixture.registry.apply()
        val pet = FakeHost.pet()
        fixture.registry.onFrame(pet, .016)
        fixture.registry.onEvent(PetEvent.Clicked(pet))
        assertEquals(1, fixture.speech.frames)
        assertEquals(1, fixture.speech.events)
        assertEquals(0, fixture.sound.frames)
        assertEquals(0, fixture.sound.events)
    }

    @Test
    fun menuItemsComeFromActiveModulesOnly() {
        val fixture = Fixture(PetOptions(speech = false, clickSound = true))
        fixture.registry.apply()
        assertEquals(1, fixture.registry.menuItems(FakeHost.pet()).size)
    }

    @Test
    fun aPreferenceChangeReachesTheEnabledModules() {
        val fixture = Fixture(PetOptions(speech = true, clickSound = true))
        fixture.registry.apply()
        fixture.registry.apply()
        assertEquals(2, fixture.speech.optionChanges)
        assertEquals(2, fixture.sound.optionChanges)
    }

    @Test
    fun shutdownDisablesEverythingItBuilt() {
        val fixture = Fixture(PetOptions(speech = true, clickSound = true))
        fixture.registry.apply()
        fixture.registry.shutdown()
        assertEquals(1, fixture.speech.disabled)
        assertEquals(1, fixture.sound.disabled)
        assertEquals(2, fixture.constructed)
        assertEquals(2, fixture.registry.ids().size)
    }
}
