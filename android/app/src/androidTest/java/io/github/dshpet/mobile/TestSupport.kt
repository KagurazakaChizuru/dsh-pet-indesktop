package io.github.dshpet.mobile

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertTrue

/** Records what a pet view told its owner, so gesture tests can assert on it. */
class RecordingListener : PetView.Listener {
    var changed = 0
    var pressed = 0
    var released = 0
    var clicked = 0
    var menu = 0

    override fun onChanged(petId: Int) {
        changed++
    }

    override fun onPressed(petId: Int) {
        pressed++
    }

    override fun onReleased(petId: Int) {
        released++
    }

    override fun onClicked(petId: Int) {
        clicked++
    }

    override fun onMenu(petId: Int) {
        menu++
    }
}

/** Polls real state with a deadline; never guesses how long a transition takes. */
fun awaitCondition(timeoutMs: Long = 25_000, condition: () -> Boolean) {
    val reached = CountDownLatch(1)
    val handler = Handler(Looper.getMainLooper())
    val deadline = SystemClock.elapsedRealtime() + timeoutMs
    val check = object : Runnable {
        override fun run() {
            if (condition()) reached.countDown()
            else if (SystemClock.elapsedRealtime() < deadline) handler.postDelayed(this, 50)
        }
    }
    handler.post(check)
    assertTrue("condition not reached within $timeoutMs ms",
        reached.await(timeoutMs + 5_000, TimeUnit.MILLISECONDS))
    handler.removeCallbacks(check)
}

/** Waits until [frames] more draws have been delivered, so tests advance with the pet. */
fun awaitFrames(frames: Int, timeoutMs: Long = 25_000) {
    val start = PetRuntime.draws.get()
    awaitCondition(timeoutMs) { PetRuntime.draws.get() >= start + frames }
}

fun startPet(context: Context) {
    PetOverlayService.command(context, PetOverlayService.START)
    awaitCondition { PetRuntime.state.value.running }
}

fun stopPet(context: Context) {
    PetOverlayService.command(context, PetOverlayService.STOP)
    awaitCondition { !PetRuntime.state.value.running }
}
