package io.github.dshpet.mobile

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.MediaPlayer
import android.media.SoundPool
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.util.Log

/** Short bundled samples use SoundPool, with prepared MediaPlayers as a fallback. */
class AndroidClickOutput(context: Context, uri: String?, private val changed: () -> Unit) : ClickAudio.Output {
    private val attributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_GAME)
        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build()
    private val handler = Handler(Looper.getMainLooper())
    private var closed = false
    private var pool: SoundPool? = null
    private val ids = mutableMapOf<ClickAudio.Sound, Int>()
    private val loaded = mutableSetOf<Int>()
    private val failedIds = mutableSetOf<Int>()
    private val streams = mutableMapOf<ClickAudio.Sound, Int>()
    private val players = mutableMapOf<ClickAudio.Sound, MediaPlayer>()
    private val prepared = mutableSetOf<ClickAudio.Sound>()
    private var gain = .7f
    private var path = "loading"
    override var failed = false
        private set
    private val timeout = Runnable {
        if (!closed && !ready(ClickAudio.Sound.PRESS)) fail()
    }

    init {
        if (uri == null) loadBundled(context) else loadCustom(context, uri)
        if (!ready(ClickAudio.Sound.PRESS) && !failed) handler.postDelayed(timeout, 5_000)
    }

    private fun loadBundled(context: Context) {
        val resources = mapOf(ClickAudio.Sound.PRESS to R.raw.click_press,
            ClickAudio.Sound.RELEASE to R.raw.click_release)
        try {
            pool = SoundPool.Builder().setMaxStreams(2).setAudioAttributes(attributes).build().also { pool ->
                pool.setOnLoadCompleteListener { current, id, status ->
                    if (!closed && current === this.pool) {
                        if (status == 0) loaded += id else failedIds += id
                        failed = ids.any { (sound, sample) -> sample in failedIds && sound !in prepared }
                        changed()
                    }
                }
                resources.forEach { (sound, resource) -> ids[sound] = pool.load(context, resource, 1) }
            }
        } catch (error: RuntimeException) { Log.e("PetOverlay", "SoundPool unavailable", error) }
        resources.forEach { (sound, resource) ->
            try {
                MediaPlayer.create(context, resource, attributes, AudioManager.AUDIO_SESSION_ID_GENERATE)
                    ?.let { player ->
                        players[sound] = player
                        prepared += sound
                        player.setVolume(gain, gain)
                        player.setOnErrorListener { _, _, _ ->
                            prepared -= sound
                            failed = ids[sound] !in loaded
                            changed()
                            true
                        }
                    }
            } catch (error: RuntimeException) { Log.e("PetOverlay", "Tap fallback unavailable", error) }
        }
        failed = resources.keys.any { !ready(it) && (ids[it] ?: 0) == 0 }
    }

    private fun loadCustom(context: Context, uri: String) {
        val sound = ClickAudio.Sound.PRESS
        val player = MediaPlayer()
        players[sound] = player
        try {
            player.setAudioAttributes(attributes)
            player.setDataSource(context, Uri.parse(uri))
            player.setOnPreparedListener {
                if (!closed && players[sound] === it) {
                    prepared += sound
                    handler.removeCallbacks(timeout)
                    it.setVolume(gain, gain)
                    changed()
                }
            }
            player.setOnErrorListener { _, _, _ -> if (!closed) fail(); true }
            player.prepareAsync()
        } catch (error: Exception) {
            Log.e("PetOverlay", "Cannot open selected tap audio", error)
            fail()
        }
    }

    private fun fail() {
        failed = true
        handler.removeCallbacks(timeout)
        prepared.clear()
        players.values.forEach { it.release() }
        players.clear()
        changed()
    }

    override fun ready(sound: ClickAudio.Sound) = !closed && !failed &&
        (sound in prepared || ids[sound] in loaded)

    override fun play(sound: ClickAudio.Sound, volume: Float): Boolean {
        if (!ready(sound)) return false
        setVolume(volume)
        val id = ids[sound]
        if (id != null && id in loaded) {
            val stream = pool?.play(id, gain, gain, 1, 0, 1f) ?: 0
            if (stream != 0) {
                streams[sound] = stream
                path = "pool-${sound.name.lowercase()}"
                return true
            }
        }
        val player = players[sound] ?: return false
        return try {
            player.setVolume(gain, gain)
            player.seekTo(0)
            player.start()
            path = "media-${sound.name.lowercase()}"
            true
        } catch (error: IllegalStateException) {
            Log.e("PetOverlay", "Tap playback failed", error)
            fail()
            false
        }
    }

    override fun setVolume(volume: Float) {
        gain = volume
        streams.values.forEach { pool?.setVolume(it, gain, gain) }
        prepared.forEach { sound -> players[sound]?.setVolume(gain, gain) }
    }

    override fun diagnostics() = "path=$path loaded=${loaded.size} prepared=${prepared.size}"

    override fun close() {
        if (closed) return
        closed = true
        handler.removeCallbacksAndMessages(null)
        pool?.release()
        pool = null
        players.values.forEach { it.release() }
        players.clear()
        prepared.clear()
        loaded.clear()
        streams.clear()
    }
}
