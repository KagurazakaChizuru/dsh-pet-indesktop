package io.github.dshpet.mobile

import android.os.SystemClock
import android.view.MotionEvent
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ReleaseVelocityTest {
    @Test fun fastReleaseThrowsButHoldingBeforeReleaseDoesNot() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                val engine = PetEngine(AssetCatalog.load(activity.assets).clips).apply {
                    resize(800.0, 1600.0); restorePosition(.5, .5)
                }
                val view = PetView(activity, 0, engine, RecordingListener())
                activity.setContentView(view)
                fun gesture(releaseDelay: Long) {
                    val start = SystemClock.uptimeMillis()
                    fun deliver(action: Int, elapsed: Long, x: Float) {
                        val event = MotionEvent.obtain(start, start + elapsed, action, x, 100f, 0)
                        event.source = android.view.InputDevice.SOURCE_TOUCHSCREEN
                        event.setLocation(100f, 100f)
                        view.dispatchTouchEvent(event)
                        event.recycle()
                    }
                    deliver(MotionEvent.ACTION_DOWN, 0, 100f)
                    deliver(MotionEvent.ACTION_MOVE, 20, 150f)
                    deliver(MotionEvent.ACTION_MOVE, 40, 200f)
                    deliver(MotionEvent.ACTION_MOVE, 60, 250f)
                    deliver(MotionEvent.ACTION_UP, 60 + releaseDelay, 250f)
                }
                // Lifting within the desktop's 150ms release window still flings.
                gesture(70)
                assertEquals(PetMode.THROWN, engine.mode)
                assertTrue(engine.vx > 500)
                gesture(400)
                assertEquals(PetMode.IDLE, engine.mode)
                assertEquals(0.0, engine.vx, 0.0)
            }
        }
    }
}
