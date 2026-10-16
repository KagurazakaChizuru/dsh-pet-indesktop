package io.github.dshpet.mobile

import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference
import kotlinx.coroutines.flow.MutableStateFlow

data class RuntimeState(val running: Boolean = false, val paused: Boolean = false,
                        val error: String? = null, val companions: Int = 0,
                        val modules: List<String> = emptyList())

object PetRuntime {
    val state = MutableStateFlow(RuntimeState())
    val draws = AtomicLong()
    val windowCount = AtomicInteger()
    /** Window geometry transactions: the counter that shows the resize churn is gone. */
    val windowOps = AtomicLong()
    /** Bubble windows created; stays 0 while the speech module is disabled. */
    val bubbles = AtomicLong()
    /** Frames the decoder was not ready for. The display keeps the previous frame. */
    val staleFrames = AtomicLong()
    /** Last phrase drawn, so device tests can verify a user-edited pool. */
    val lastPhrase = AtomicReference("")
    val audioPlays = AtomicLong()
    val audioError = MutableStateFlow(false)
}
