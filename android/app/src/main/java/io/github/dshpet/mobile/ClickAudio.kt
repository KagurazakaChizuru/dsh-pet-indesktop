package io.github.dshpet.mobile

/** Shared by pet taps and the settings preview. All calls stay on the UI thread. */
class ClickAudio(
    private val factory: (String?, () -> Unit) -> Output,
    private val now: () -> Long,
    private val changed: (State) -> Unit = {},
    private val played: () -> Unit = {},
) : AutoCloseable {
    enum class Sound { PRESS, RELEASE }
    enum class State { IDLE, LOADING, READY, ERROR }

    /** The Android audio boundary; tests replace only the platform player. */
    interface Output : AutoCloseable {
        val failed: Boolean
        fun ready(sound: Sound): Boolean
        fun play(sound: Sound, volume: Float): Boolean
        fun setVolume(volume: Float)
        fun diagnostics(): String
    }

    private var output: Output? = null
    private var source: String? = null
    private var volume = .7f
    private var generation = 0L
    private val pending = mutableMapOf<Sound, Long>()
    private val lastRequest = mutableMapOf<Sound, Long>()
    var state = State.IDLE
        private set

    fun configure(uri: String?, gain: Float) {
        volume = if (gain.isFinite()) gain.coerceIn(0f, 1f) else .7f
        if (output != null && source == uri) {
            output?.setVolume(volume)
            return
        }
        close()
        source = uri
        val revision = generation
        setState(State.LOADING)
        output = factory(uri) { if (revision == generation) refresh() }
        output?.setVolume(volume)
        refresh()
    }

    fun press() = request(Sound.PRESS)

    fun release() { if (source == null) request(Sound.RELEASE) }

    private fun request(sound: Sound) {
        val active = output ?: return
        if (active.failed) return
        val time = now()
        if (lastRequest[sound]?.let { time - it < 80 } == true) return
        lastRequest[sound] = time
        pending[sound] = time
        flush(sound)
    }

    private fun flush(sound: Sound) {
        val requested = pending[sound] ?: return
        val active = output ?: return
        // Never replay stale gestures when a slow or inaccessible file finally opens.
        if (now() - requested > 1_000 || active.failed) {
            pending.remove(sound)
        } else if (active.ready(sound)) {
            pending.remove(sound)
            if (active.play(sound, volume)) played() else setState(State.ERROR)
        }
    }

    private fun refresh() {
        val active = output ?: return
        if (active.failed) {
            pending.clear()
            setState(State.ERROR)
            return
        }
        val ready = active.ready(Sound.PRESS) && (source != null || active.ready(Sound.RELEASE))
        setState(if (ready) State.READY else State.LOADING)
        Sound.entries.forEach(::flush)
    }

    private fun setState(value: State) { state = value; changed(value) }

    fun diagnostics() = "audioState=$state ${output?.diagnostics().orEmpty()} pending=${pending.size}"

    override fun close() {
        generation++
        pending.clear()
        lastRequest.clear()
        output?.close()
        output = null
        setState(State.IDLE)
    }
}
