package io.github.dshpet.mobile

import android.content.res.AssetManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import java.io.BufferedInputStream
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

/**
 * Decoded frames for every pet, in one decoder and one cache.
 *
 * Three things make a 24 fps clip keep up on a phone:
 *  - a byte budget instead of a fixed frame count, so the cache holds whatever
 *    fits (about 26 frames) rather than three;
 *  - per-pet cursors planned nearest-first (all current frames, then all of
 *    their frame+1, …), so a pet that just switched clips outranks look-ahead;
 *  - bitmap reuse, so the steady state stops allocating 0.9 MB frames.
 *
 * A bitmap that any view might still be drawing is never handed back out as a
 * decode target, and nothing is ever recycled: dropping a reference is enough
 * and cannot leave a view holding a recycled bitmap.
 */
class FrameLoader(
    private val assets: AssetManager,
    private val ready: () -> Unit,
    private val failed: (Exception) -> Unit,
    private val budgetBytes: Long = DEFAULT_BUDGET_BYTES,
    private val lookahead: Int = DEFAULT_LOOKAHEAD,
    threads: Int = 1,
) : AutoCloseable {
    companion object {
        const val DEFAULT_BUDGET_BYTES = 24L * 1024 * 1024
        const val DEFAULT_LOOKAHEAD = 4

        /** Keep at most this many spare bitmaps alive for reuse (~2.7 MB). */
        private const val POOL_LIMIT = 3

        /** How many recently returned frames per pet stay off limits for reuse. */
        private const val KEEP_RECENT = 2
        private const val IDLE_WAIT_MS = 200L
    }

    class DecodedFrame(val bitmap: Bitmap, val revision: Long)

    private class Entry(val bitmap: Bitmap, val revision: Long)

    private class Decoded(val bitmap: Bitmap, val reused: Boolean)

    /** One pet's playback position. */
    inner class Cursor internal constructor(private val consumerId: Int) {
        fun request(clip: ClipSpec, index: Int): DecodedFrame? = requestFor(consumerId, clip, index)

        fun close() = detach(consumerId)
    }

    private val lock = ReentrantLock()
    private val workReady = lock.newCondition()
    private val handler = Handler(Looper.getMainLooper())
    private val frames = HashMap<String, Entry>()
    private val budget = FrameBudget(budgetBytes)
    private val wanted = HashMap<Int, CursorState>()
    private val recent = HashMap<Int, ArrayDeque<Bitmap>>()
    private val inFlight = HashSet<String>()
    private val pool = ArrayDeque<Bitmap>()
    private val warmQueue = ArrayDeque<FrameRequest>()
    private val executor = Executors.newFixedThreadPool(threads) { runnable ->
        Thread(runnable, "pet-frame-decoder")
    }
    private var revision = 0L
    private var closed = false
    private var failures = 0
    private val notifyPending = AtomicBoolean(false)

    val decoded = AtomicLong()
    val reused = AtomicLong()
    val cacheHits = AtomicLong()
    val cacheMisses = AtomicLong()

    init {
        repeat(threads.coerceAtLeast(1)) { executor.execute(::decodeLoop) }
    }

    fun cursor(consumerId: Int): Cursor = Cursor(consumerId)

    /** Low-priority background fill, used to have the first click frames ready. */
    fun warm(clips: Collection<ClipSpec>, framesPerClip: Int) {
        lock.withLock {
            if (closed || framesPerClip <= 0) return
            for (clip in clips) {
                for (index in 0 until minOf(framesPerClip, clip.frames)) {
                    warmQueue.addLast(FrameRequest(frameKey(clip, index), clip, index))
                }
            }
            workReady.signalAll()
        }
    }

    fun cachedFrames(): Int = lock.withLock { frames.size }

    fun cachedBytes(): Long = lock.withLock { budget.bytes }

    override fun close() {
        lock.withLock {
            closed = true
            wanted.clear()
            recent.clear()
            frames.clear()
            pool.clear()
            inFlight.clear()
            warmQueue.clear()
            workReady.signalAll()
        }
        handler.removeCallbacksAndMessages(null)
        executor.shutdownNow()
    }

    private fun requestFor(consumerId: Int, clip: ClipSpec, index: Int): DecodedFrame? {
        if (clip.frames <= 0) return null
        val safeIndex = index.coerceIn(0, clip.frames - 1)
        val result = lock.withLock {
            if (closed) return null
            wanted[consumerId] = CursorState(clip, safeIndex)
            workReady.signalAll()
            val key = frameKey(clip, safeIndex)
            val entry = frames[key]
            if (entry == null) {
                cacheMisses.incrementAndGet()
                null
            } else {
                cacheHits.incrementAndGet()
                budget.markUsed(key)
                rememberLocked(consumerId, entry.bitmap)
                DecodedFrame(entry.bitmap, entry.revision)
            }
        }
        return result
    }

    private fun rememberLocked(consumerId: Int, bitmap: Bitmap) {
        val queue = recent.getOrPut(consumerId) { ArrayDeque() }
        if (queue.none { it === bitmap }) queue.addLast(bitmap)
        while (queue.size > KEEP_RECENT) queue.removeFirst()
    }

    private fun detach(consumerId: Int) {
        lock.withLock {
            wanted.remove(consumerId)
            recent.remove(consumerId)
        }
    }

    private fun decodeLoop() {
        while (true) {
            val request = nextRequest()
            if (request == null) {
                if (!awaitWork()) return
                continue
            }
            decode(request)
        }
    }

    private fun nextRequest(): FrameRequest? = lock.withLock {
        if (closed) return null
        val next = LookaheadPlanner.pending(wanted.values.toList(), lookahead) { key ->
            frames.containsKey(key) || key in inFlight
        }.firstOrNull() ?: takeWarmLocked()
        if (next != null) inFlight += next.key
        next
    }

    private fun takeWarmLocked(): FrameRequest? {
        while (warmQueue.isNotEmpty()) {
            val candidate = warmQueue.removeFirst()
            if (!frames.containsKey(candidate.key) && candidate.key !in inFlight) return candidate
        }
        return null
    }

    private fun hasWorkLocked(): Boolean =
        warmQueue.any { !frames.containsKey(it.key) && it.key !in inFlight } ||
            LookaheadPlanner.pending(wanted.values.toList(), lookahead) { key ->
                frames.containsKey(key) || key in inFlight
            }.isNotEmpty()

    /** Returns false when the loader is closed. */
    private fun awaitWork(): Boolean = lock.withLock {
        if (closed) return false
        if (hasWorkLocked()) return true
        workReady.await(IDLE_WAIT_MS, TimeUnit.MILLISECONDS)
        !closed
    }

    private fun decode(request: FrameRequest) {
        val decodedFrame = try {
            decodeFrame(request)
        } catch (e: Exception) {
            finishFailed(request, e)
            return
        }
        if (decodedFrame == null) {
            finishFailed(request, IllegalStateException("Unreadable animation frame: ${request.key}"))
            return
        }
        failures = 0
        decoded.incrementAndGet()
        if (decodedFrame.reused) reused.incrementAndGet()
        publish(request, decodedFrame.bitmap)
    }

    private fun finishFailed(request: FrameRequest, error: Exception) {
        failures++
        lock.withLock {
            inFlight -= request.key
            workReady.signalAll()
        }
        if (failures >= 3) handler.post { if (!isClosed()) failed(error) }
    }

    private fun decodeFrame(request: FrameRequest): Decoded? {
        val spare = lock.withLock { pool.removeFirstOrNull() }
        if (spare != null) {
            val reused = decodeStream(request, spare)
            if (reused != null) return Decoded(reused, true)
            // BitmapFactory refused the spare; decode into a fresh bitmap instead.
            lock.withLock { if (pool.size < POOL_LIMIT) pool.addLast(spare) }
        }
        return decodeStream(request, null)?.let { Decoded(it, false) }
    }

    private fun decodeStream(request: FrameRequest, inBitmap: Bitmap?): Bitmap? {
        val options = BitmapFactory.Options()
        if (inBitmap != null) {
            options.inBitmap = inBitmap
            options.inMutable = true
        }
        return assets.open(request.clip.framePath(request.index)).use { stream ->
            BitmapFactory.decodeStream(BufferedInputStream(stream), null, options)
        }
    }

    private fun publish(request: FrameRequest, bitmap: Bitmap) {
        lock.withLock {
            inFlight -= request.key
            if (closed) return
            revision++
            frames.put(request.key, Entry(bitmap, revision))?.let { releaseToPoolLocked(it.bitmap) }
            budget.record(request.key, bitmap.allocationByteCount.toLong())
            // The frame we just produced is never the one we drop: evicting it
            // would ask the decoder for it again, forever.
            for (key in budget.overflow(0, keepKeysLocked() + request.key)) {
                frames.remove(key)?.let {
                    budget.remove(key)
                    releaseToPoolLocked(it.bitmap)
                }
            }
            workReady.signalAll()
        }
        if (notifyPending.compareAndSet(false, true)) {
            handler.post {
                notifyPending.set(false)
                if (!isClosed()) ready()
            }
        }
    }

    /** The frame each pet is showing right now; never evicted. */
    private fun keepKeysLocked(): Set<String> =
        wanted.values.mapTo(HashSet()) { frameKey(it.clip, it.index) }

    /**
     * A bitmap is only kept for reuse when no live frame and no recently
     * returned frame is that same object: a view could still paint it.
     */
    private fun releaseToPoolLocked(bitmap: Bitmap) {
        if (!bitmap.isMutable || pool.size >= POOL_LIMIT) return
        if (frames.values.any { it.bitmap === bitmap }) return
        if (recent.values.any { queue -> queue.any { it === bitmap } }) return
        pool.addLast(bitmap)
    }

    private fun isClosed(): Boolean = lock.withLock { closed }
}
