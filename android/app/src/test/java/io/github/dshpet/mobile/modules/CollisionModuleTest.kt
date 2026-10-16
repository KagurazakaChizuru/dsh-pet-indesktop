package io.github.dshpet.mobile.modules

import io.github.dshpet.mobile.ModuleIds
import io.github.dshpet.mobile.PetMode
import io.github.dshpet.mobile.PetOptions
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CollisionModuleTest {
    @Test
    fun separatedRenderedBodiesWithDifferentScalesDoNotCollide() {
        val host = FakeHost(PetOptions())
        val mother = FakeHost.pet(0)
        val baby = FakeHost.pet(1)
        listOf(mother, baby).forEach { it.engine.resize(2000.0, 2000.0) }
        // In the mother's space these are x=100..316 and x=360..522, a 44px gap.
        mother.engine.placeAt(100.0, 100.0)
        baby.engine.placeAt(480.0, (100.0 + 270.0 / 2 - 270.0 * .75 / 2) / .75)
        host.pets.addAll(listOf(mother, baby))
        val module = CollisionModule().also { it.enable(host) }
        val babyY = baby.engine.y
        module.onTick(1.0 / 24)
        assertEquals(100.0, mother.engine.x, .001)
        assertEquals(480.0, baby.engine.x, .001)
        assertEquals(babyY, baby.engine.y, .001)
        assertEquals(0L, module.separations)
    }

    @Test
    fun touchingRenderedBodiesSeparateWithARealBodyOrigin() {
        val host = FakeHost(PetOptions())
        val mother = FakeHost.pet(0)
        val baby = FakeHost.pet(1)
        listOf(mother, baby).forEach { it.engine.resize(2000.0, 2000.0) }
        mother.engine.placeAt(100.0, 100.0)
        baby.engine.placeAt(300.0 / .75, (100.0 + 270.0 / 2 - 270.0 * .75 / 2) / .75)
        host.pets.addAll(listOf(mother, baby))
        val module = CollisionModule().also { it.enable(host) }
        module.onTick(1.0 / 24)
        assertTrue(mother.engine.x < 100.0)
        assertTrue(baby.engine.x > 400.0)
    }

    /** Two pets deliberately overlapping by 20 source pixels. */
    private fun household(options: PetOptions = PetOptions()): Pair<FakeHost, CollisionModule> {
        val host = FakeHost(options)
        val mother = FakeHost.pet(0)
        val baby = FakeHost.pet(1)
        for (pet in listOf(mother, baby)) {
            pet.engine.resize(2000.0, 2000.0)
        }
        mother.engine.placeAt(500.0, 100.0)
        // The companion's engine space is its own, so its scaled body centre must
        // land to the right of the mother's for the overlap this test wants.
        baby.engine.placeAt(780.0, 100.0)
        host.pets += mother
        host.pets += baby
        val module = CollisionModule()
        module.enable(host)
        return host to module
    }

    @Test
    fun overlappingPetsArePushedApartWithoutAnImpulse() {
        val (host, module) = household()
        module.onTick(1.0 / 24)
        assertTrue("mother must move left, x=${host.pets[0].engine.x}",
            host.pets[0].engine.x < 500.0)
        assertTrue("baby must move right, x=${host.pets[1].engine.x}",
            host.pets[1].engine.x > 780.0)
        assertEquals("a static overlap is not a hit", 0L, module.hits)
        assertTrue("but it is still a push, pushed=${module.separations}", module.separations > 0)
        assertTrue("and it must not play the Q 弹 pulse", host.squashed.isEmpty())
    }

    @Test
    fun theLighterCompanionIsPushedFurther() {
        val (host, module) = household()
        module.onTick(1.0 / 24)
        val motherMoved = kotlin.math.abs(host.pets[0].engine.x - 500.0)
        val babyMoved = kotlin.math.abs(host.pets[1].engine.x - 780.0)
        assertTrue("baby=$babyMoved mother=$motherMoved", babyMoved > motherMoved)
    }

    @Test
    fun aRealHitThrowsTheOtherPetAndSquashesBoth() {
        val (host, module) = household()
        val mother = host.pets[0]
        mother.engine.beginDrag()
        mother.engine.release(1200.0, 0.0)
        assertTrue("the test needs a real throw, vx=${mother.engine.vx}", mother.engine.vx > 500)
        module.onTick(1.0 / 24)
        assertEquals("both bodies took the hit", 2L, module.hits)
        assertEquals(PetMode.THROWN, host.pets[1].engine.mode)
        assertTrue("the desktop squashes both pets on a hit", host.squashed.containsAll(listOf(0, 1)))
    }

    @Test
    fun aSinglePetHasNothingToCollideWith() {
        val host = FakeHost(PetOptions())
        host.pets += FakeHost.pet(0)
        val module = CollisionModule()
        module.enable(host)
        module.onTick(1.0 / 24)
        assertEquals(0L, module.hits)
        assertEquals(0L, module.separations)
    }

    @Test
    fun aDisabledModuleIsNeverBuiltAndNeverTouchesThePets() {
        val host = FakeHost(PetOptions(collision = false))
        val mother = FakeHost.pet(0)
        val baby = FakeHost.pet(1)
        for (pet in listOf(mother, baby)) {
            pet.engine.resize(2000.0, 2000.0)
        }
        mother.engine.placeAt(500.0, 100.0)
        // The companion's engine space is its own, so its scaled body centre must
        // land to the right of the mother's for the overlap this test wants.
        baby.engine.placeAt(780.0, 100.0)
        host.pets += mother
        host.pets += baby
        var created = 0
        val registry = ModuleRegistry(host, listOf(
            ModuleFactory(ModuleIds.COLLISION) {
                created++
                CollisionModule()
            }))
        registry.apply()
        assertEquals("off means never constructed", 0, created)
        registry.onTick(1.0 / 24)
        assertEquals(500.0, mother.engine.x, 0.0)
        assertEquals(780.0, baby.engine.x, 0.0)

        host.options = host.options.copy(collision = true)
        registry.apply()
        assertEquals(1, created)
        registry.onTick(1.0 / 24)
        assertTrue("on means the same pair separates", mother.engine.x < 500.0)
    }

    @Test
    fun separationNeverLeavesTheScreen() {
        val (host, module) = household(PetOptions(collisionRestitution = 1f))
        repeat(20) { module.onTick(1.0 / 24) }
        for (pet in host.pets) {
            assertTrue("x=${pet.engine.x}", pet.engine.x in 0.0..2000.0)
            assertTrue("y=${pet.engine.y}", pet.engine.y in 0.0..2000.0)
        }
    }

    @Test
    fun draggingKeepsTheFingerAnchorAndSwitchingOffStopsAllPushes() {
        val (host, _) = household()
        val mother = host.pets[0]
        val baby = host.pets[1]
        mother.engine.beginDrag()
        val registry = ModuleRegistry(host, listOf(ModuleFactory(ModuleIds.COLLISION) { CollisionModule() }))
        registry.apply()
        registry.onTick(1.0 / 24)
        assertEquals(500.0, mother.engine.x, .001)
        assertTrue(baby.engine.x > 780.0)
        host.options = host.options.copy(collision = false)
        registry.apply()
        baby.engine.placeAt(780.0, 100.0)
        repeat(10) { registry.onTick(1.0 / 24) }
        assertEquals(780.0, baby.engine.x, .001)
    }

    @Test
    fun fivePetsSettleWithoutMovingTheDraggedOne() {
        val (host, module) = household()
        for (id in 2..4) host.pets += FakeHost.pet(id).also {
            it.engine.resize(2000.0, 2000.0)
            it.engine.placeAt(780.0 + id * 20, 100.0)
        }
        host.pets.first().engine.beginDrag()
        repeat(100) { module.onTick(1.0 / 60) }
        assertEquals(500.0, host.pets.first().engine.x, .001)
        assertTrue(module.separations > 0)
        host.pets.forEach { assertTrue(it.engine.x.isFinite() && it.engine.y.isFinite()) }
    }
}
