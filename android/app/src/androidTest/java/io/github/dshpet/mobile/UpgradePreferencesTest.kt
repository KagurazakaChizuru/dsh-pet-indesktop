package io.github.dshpet.mobile

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Run with -e upgradePhase before on 0.2.0, install -r 0.2.1, then run with after. */
@RunWith(AndroidJUnit4::class)
class UpgradePreferencesTest {
    @Test fun savedChoicesSurviveInstallingTheNewApk() {
        val phase = InstrumentationRegistry.getArguments().getString("upgradePhase")
        assumeTrue("requires two real APK installs", phase in listOf("before", "after"))
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val store = PetPreferences(context)
        if (phase == "before") {
            store.save(PetOptions(size = 1.3f, clickSound = false, clickSoundVolume = .4f,
                collision = false, phrases = listOf("upgrade fixture")))
            store.savePosition(.2, .3)
            // Instrumentation can terminate without an Activity.onStop flush.
            assertTrue(context.getSharedPreferences("pet", 0).edit()
                .putBoolean("upgradeFixtureReady", true).commit())
        } else {
            val options = store.options()
            assertEquals("0.2.1", context.packageManager.getPackageInfo(context.packageName, 0).versionName)
            assertFalse(options.clickSound)
            assertFalse(options.collision)
            assertEquals(.4f, options.clickSoundVolume, .001f)
            assertEquals(1.3f, options.size, .001f)
            assertEquals(listOf("upgrade fixture"), options.phrases)
            assertEquals(.2, store.position().first, .001)
            assertEquals(.3, store.position().second, .001)
            store.reset()
        }
    }
}
