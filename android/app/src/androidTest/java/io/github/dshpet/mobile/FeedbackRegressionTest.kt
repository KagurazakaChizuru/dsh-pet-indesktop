package io.github.dshpet.mobile

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.view.ViewTreeObserver
import android.widget.FrameLayout
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class FeedbackRegressionTest {
    @Test
    fun pausedPetSquashesAndRestoresWithoutEngineTicks() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            lateinit var view: PetView
            lateinit var target: Bitmap
            val crop = SourceBox(0.0, 0.0, 100.0, 80.0)
            scenario.onActivity { activity ->
                val clips = listOf(ClipSpec("idle", "idle", 24.0, 1, crop = crop),
                    ClipSpec("click", "click", 24.0, 1, crop = crop))
                val engine = PetEngine(clips).apply { paused = true }
                view = PetView(activity, 0, engine, RecordingListener())
                view.configure(crop, 1.0)
                val source = Bitmap.createBitmap(100, 80, Bitmap.Config.ARGB_8888)
                source.eraseColor(Color.RED)
                view.present(FrameLoader.DecodedFrame(source, 1L), crop, false)
                val frame = FrameLayout(activity)
                frame.addView(view, FrameLayout.LayoutParams(120, 80))
                activity.setContentView(frame)
                target = Bitmap.createBitmap(120, 80, Bitmap.Config.ARGB_8888)
            }
            var initial = 0
            fun paintedHeight(): Int {
                target.eraseColor(Color.TRANSPARENT)
                view.draw(Canvas(target))
                val pixels = IntArray(target.width * target.height)
                target.getPixels(pixels, 0, target.width, 0, 0, target.width, target.height)
                return (0 until target.height).count { y ->
                    (0 until target.width).any { x -> Color.alpha(pixels[y * target.width + x]) > 128 }
                }
            }
            awaitCondition { view.width > 0 && paintedHeight() == 80 }
            val peak = CountDownLatch(1)
            val restored = CountDownLatch(1)
            val observer = ViewTreeObserver.OnDrawListener {
                val height = paintedHeight()
                if (height < initial - 3) peak.countDown()
                else if (peak.count == 0L && height == initial) restored.countDown()
            }
            scenario.onActivity {
                initial = paintedHeight()
                view.viewTreeObserver.addOnDrawListener(observer)
                view.performClick()
            }
            try {
                assertTrue("no squashed frame drawn", peak.await(10, TimeUnit.SECONDS))
                assertTrue("pulse did not restore", restored.await(10, TimeUnit.SECONDS))
            } finally { scenario.onActivity { view.viewTreeObserver.removeOnDrawListener(observer) } }
            scenario.onActivity { assertEquals(80, initial) }
        }
    }

    @Test
    fun repeatedPulsesFitAtEverySizeAndDetachRestoresTheDrawing() {
        for (scale in listOf(.6, .75, 1.0, 1.6)) {
            ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                lateinit var view: PetView
                lateinit var frame: FrameLayout
                lateinit var source: Bitmap
                lateinit var target: Bitmap
                val crop = SourceBox(0.0, 0.0, 100.0, 80.0)
                val placement = WindowGeometry.placement(0.0, 0.0, crop, crop, scale, 0, 0)
                scenario.onActivity { activity ->
                    val engine = PetEngine(listOf(ClipSpec("idle", "idle", 24.0, 1, crop = crop)))
                    view = PetView(activity, 1, engine, RecordingListener())
                    view.configure(crop, scale)
                    source = Bitmap.createBitmap(100, 80, Bitmap.Config.ARGB_8888)
                    source.eraseColor(Color.RED)
                    view.present(FrameLoader.DecodedFrame(source, 1L), crop, true)
                    frame = FrameLayout(activity)
                    frame.addView(view, FrameLayout.LayoutParams(placement.width, placement.height))
                    activity.setContentView(frame)
                    target = Bitmap.createBitmap(placement.width, placement.height, Bitmap.Config.ARGB_8888)
                }
                fun painted(): Pair<Int, Int> {
                    target.eraseColor(Color.TRANSPARENT)
                    view.draw(Canvas(target))
                    val pixels = IntArray(target.width * target.height)
                    target.getPixels(pixels, 0, target.width, 0, 0, target.width, target.height)
                    val width = (0 until target.width).count { x ->
                        (0 until target.height).any { y -> Color.alpha(pixels[y * target.width + x]) > 128 }
                    }
                    val height = (0 until target.height).count { y ->
                        (0 until target.width).any { x -> Color.alpha(pixels[y * target.width + x]) > 128 }
                    }
                    return width to height
                }
                awaitCondition { view.width == placement.width }
                var original = 0 to 0
                val peak = CountDownLatch(1)
                val restored = CountDownLatch(1)
                var repeated = false
                val observer = ViewTreeObserver.OnDrawListener {
                    val bounds = painted()
                    if (bounds.first > original.first && bounds.second < original.second) {
                        peak.countDown()
                        if (!repeated) {
                            repeated = true
                            view.post { view.squash() }
                        }
                    } else if (peak.count == 0L && bounds == original) restored.countDown()
                }
                scenario.onActivity {
                    original = painted()
                    view.viewTreeObserver.addOnDrawListener(observer)
                    view.squash()
                }
                try {
                    assertTrue("no widened frame at scale=$scale", peak.await(10, TimeUnit.SECONDS))
                    assertTrue("not restored at scale=$scale", restored.await(10, TimeUnit.SECONDS))
                } finally { scenario.onActivity { view.viewTreeObserver.removeOnDrawListener(observer) } }
                scenario.onActivity {
                    view.squash()
                    frame.removeView(view)
                    frame.addView(view)
                    view.present(FrameLoader.DecodedFrame(source, 2L), crop, true)
                    assertEquals(original, painted())
                }
            }
        }
    }

    @Test
    fun missingSoundPreferenceUsesNewDefaultButSavedOffIsPreserved() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val store = PetPreferences(context)
        try {
            store.reset()
            assertTrue(store.options().clickSound)
            store.save(store.options().copy(clickSound = false, clickSoundVolume = .3f,
                collision = false))
            val reloaded = PetPreferences(context).options()
            assertFalse(reloaded.clickSound)
            assertFalse(reloaded.collision)
            assertEquals(.3f, reloaded.clickSoundVolume, .001f)
            store.reset()
            assertTrue(store.options().clickSound)
            assertTrue(store.options().collision)
        } finally { store.reset() }
    }
}
