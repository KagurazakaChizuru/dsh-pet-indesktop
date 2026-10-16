package io.github.dshpet.mobile

import android.app.NotificationManager
import android.content.Intent
import android.graphics.BitmapFactory
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class DeviceAcceptanceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext

    private fun shell(command: String) {
        instrumentation.uiAutomation.executeShellCommand(command).use { descriptor ->
            android.os.ParcelFileDescriptor.AutoCloseInputStream(descriptor).readBytes()
        }
    }

    @After
    fun cleanup() {
        context.stopService(Intent(context, PetOverlayService::class.java))
        awaitCondition { !PetRuntime.state.value.running }
    }

    @Test
    fun bundledCoreAnimationsAreReadableAndTransparent() {
        val catalog = AssetCatalog.load(context.assets)
        assertEquals(11, catalog.clips.size)
        for (clip in catalog.clips) {
            val bitmap = context.assets.open(clip.framePath(0)).use {
                BitmapFactory.decodeStream(it)
            }
            assertNotNull(clip.id, bitmap)
            assertTrue(bitmap.hasAlpha())
            assertEquals(catalog.canvasWidth, bitmap.width)
            assertTrue(clip.frames > 0 && clip.fps > 0)
            assertTrue(catalog.unionCrop.left <= clip.crop.left && catalog.unionCrop.top <= clip.crop.top)
            assertTrue(catalog.unionCrop.right >= clip.crop.right && catalog.unionCrop.bottom >= clip.crop.bottom)
        }
        assertTrue(catalog.phrases.isNotEmpty())
    }

    @Test
    fun preferencesRoundTripAndResetAreImmediate() {
        val store = PetPreferences(context)
        store.save(PetOptions(size = 1.4f, wander = false, speech = false,
            phrases = listOf("只属于我的台词", "只属于我的台词", "  "),
            speechMinSeconds = 30f, speechMaxSeconds = 10f, speechSeconds = 5f,
            clickSound = true, clickSoundVolume = .4f, companions = false))
        store.savePosition(.25, .75)
        store.saveCompanionLayout(listOf(.2 to .9))
        val loaded = PetPreferences(context)
        assertEquals(1.4f, loaded.options().size, .001f)
        assertFalse(loaded.options().wander)
        assertFalse(loaded.options().speech)
        assertEquals(listOf("只属于我的台词"), loaded.options().phrases)
        assertEquals("the shorter value wins, never an inverted window",
            10f, loaded.options().speechMinSeconds, .001f)
        assertEquals(30f, loaded.options().speechMaxSeconds, .001f)
        assertEquals(5f, loaded.options().speechSeconds, .001f)
        assertTrue(loaded.options().clickSound)
        assertEquals(.4f, loaded.options().clickSoundVolume, .001f)
        assertFalse(loaded.options().companions)
        assertEquals(.25, loaded.position().first, .001)
        assertEquals(listOf(.2 to .9), loaded.companionLayout())
        loaded.reset()
        assertEquals(PetOptions(), loaded.options())
        assertEquals(0, loaded.companionLayout().size)
        assertEquals(.7, loaded.position().first, .001)
    }

    @Test
    fun secondPointerCancelsGestureWithoutClickingOnFinalUp() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                val engine = PetEngine(AssetCatalog.load(activity.assets).clips)
                val listener = RecordingListener()
                val view = PetView(activity, 0, engine, listener)
                activity.setContentView(view)
                val start = android.os.SystemClock.uptimeMillis()
                fun deliver(action: Int, count: Int) {
                    val properties = Array(count) { id -> android.view.MotionEvent.PointerProperties().apply {
                        this.id = id; toolType = android.view.MotionEvent.TOOL_TYPE_FINGER
                    } }
                    val coordinates = Array(count) { id -> android.view.MotionEvent.PointerCoords().apply {
                        x = 40f + id * 30; y = 40f; pressure = 1f; size = 1f
                    } }
                    val event = android.view.MotionEvent.obtain(start, android.os.SystemClock.uptimeMillis(),
                        action, count, properties, coordinates, 0, 0, 1f, 1f, 0, 0,
                        android.view.InputDevice.SOURCE_TOUCHSCREEN, 0)
                    view.dispatchTouchEvent(event)
                    event.recycle()
                }
                deliver(android.view.MotionEvent.ACTION_DOWN, 1)
                deliver(android.view.MotionEvent.ACTION_POINTER_DOWN or (1 shl android.view.MotionEvent.ACTION_POINTER_INDEX_SHIFT), 2)
                deliver(android.view.MotionEvent.ACTION_POINTER_UP or (1 shl android.view.MotionEvent.ACTION_POINTER_INDEX_SHIFT), 2)
                deliver(android.view.MotionEvent.ACTION_UP, 1)
                assertEquals(0, listener.clicked)
                assertEquals(0, listener.menu)
                assertNotEquals(PetMode.CLICK, engine.mode)
            }
        }
    }

    @Test
    fun startPauseResumeAndRepeatedStopOwnOneOverlay() {
        shell("appops set ${context.packageName} SYSTEM_ALERT_WINDOW allow")
        if (android.os.Build.VERSION.SDK_INT >= 33) shell("pm grant ${context.packageName} android.permission.POST_NOTIFICATIONS")
        PetPreferences(context).save(PetOptions(companions = false))
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            val previousDraws = PetRuntime.draws.get()
            scenario.onActivity { PetOverlayService.command(it, PetOverlayService.START) }
            awaitCondition { PetRuntime.state.value.running && PetRuntime.draws.get() > previousDraws + 3 }
            scenario.onActivity { PetOverlayService.command(it, PetOverlayService.START) }
            awaitCondition { PetRuntime.windowCount.get() == 1 }
            scenario.onActivity { PetOverlayService.command(it, PetOverlayService.PAUSE) }
            awaitCondition { PetRuntime.state.value.paused }
            scenario.onActivity { PetOverlayService.command(it, PetOverlayService.RESUME) }
            awaitCondition { !PetRuntime.state.value.paused }
            val notification = context.getSystemService(NotificationManager::class.java)
                .activeNotifications.first { it.id == 1 }
            notification.notification.actions.last().actionIntent.send()
            awaitCondition { !PetRuntime.state.value.running && PetRuntime.windowCount.get() == 0 }
            scenario.onActivity { PetOverlayService.command(it, PetOverlayService.STOP) }
            awaitCondition { !PetRuntime.state.value.running }
        }
    }
}
