package io.github.dshpet.mobile

import android.content.Context
import android.os.SystemClock
import android.view.Choreographer
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import io.github.dshpet.mobile.modules.ClickSoundModule
import io.github.dshpet.mobile.modules.ModuleHost
import io.github.dshpet.mobile.modules.PetEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class ClickSoundDeviceTest {
    @Test
    fun selectedAudioPreparesAndThePendingFirstTapPlays() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val args = InstrumentationRegistry.getArguments()
        val volume = args.getString("audioVolume", "0.7").toFloat()
        val source = if (args.getString("audioSource", "custom") == "builtin") null
            else "android.resource://${context.packageName}/${R.raw.click_press}"
        var plays = 0
        lateinit var audio: ClickAudio
        instrumentation.runOnMainSync {
            audio = ClickAudio({ uri, changed -> AndroidClickOutput(context, uri, changed) },
                SystemClock::elapsedRealtime, played = { plays++ })
            audio.configure(source, volume)
            // Deliberately do not wait for prepareAsync's callback.
            audio.press()
        }
        try {
            awaitCondition { plays == 1 }
            // Keep the real output alive until 60 display frames have elapsed.
            val frames = CountDownLatch(1)
            instrumentation.runOnMainSync {
                var count = 0
                val callback = object : Choreographer.FrameCallback {
                    override fun doFrame(time: Long) {
                        if (++count == 60) frames.countDown()
                        else Choreographer.getInstance().postFrameCallback(this)
                    }
                }
                Choreographer.getInstance().postFrameCallback(callback)
            }
            assertTrue(frames.await(10, TimeUnit.SECONDS))
        } finally { instrumentation.runOnMainSync { audio.close() } }
    }

    @Test
    fun missingFileReportsErrorAndClosingWhilePreparingCancelsPlayback() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        instrumentation.runOnMainSync {
            var plays = 0
            val audio = ClickAudio({ uri, changed -> AndroidClickOutput(context, uri, changed) },
                SystemClock::elapsedRealtime, played = { plays++ })
            audio.configure("file:///does-not-exist/dsh-pet.mp3", .7f)
            assertEquals(ClickAudio.State.ERROR, audio.state)
            audio.configure("android.resource://${context.packageName}/${R.raw.click_press}", .7f)
            audio.press()
            audio.close()
            assertEquals(ClickAudio.State.IDLE, audio.state)
            assertEquals(0, plays)
        }
    }

    @Test
    fun quickTapDoesNotThrottleAwayTheReleaseSound() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val host = AudioHost(instrumentation.targetContext)
        instrumentation.runOnMainSync {
            val module = ClickSoundModule()
            module.enable(host)
            try {
                val before = PetRuntime.audioPlays.get()
                module.onEvent(PetEvent.Pressed(host.pets.first()))
                host.clock += 10
                module.onEvent(PetEvent.Clicked(host.pets.first()))
                assertEquals("both halves of a quick tap must play", 2L,
                    PetRuntime.audioPlays.get() - before)
            } finally { module.disable() }
        }
    }
}

private class AudioHost(override val context: Context) : ModuleHost {
    override val options = PetOptions(clickSound = true)
    private val catalog = AssetCatalog.load(context.assets)
    override val pets = listOf(PetHandle(0, PetEngine(catalog.clips)))
    override val bodyBox = catalog.body
    override val builtinPhrases = emptyList<String>()
    var clock = SystemClock.elapsedRealtime()
    override fun now() = clock
    override fun scaleRatio(pet: PetHandle) = 1.0
    override fun effectivePhrases() = emptyList<String>()
    override fun showPhrase(pet: PetHandle, text: String, durationMs: Long) {}
    override fun clearPhrase(pet: PetHandle) {}
    override fun squash(pet: PetHandle) {}
    override fun companionCount() = 0
    override fun spawnCompanion() = false
    override fun exitCompanion(pet: PetHandle) = false
}
