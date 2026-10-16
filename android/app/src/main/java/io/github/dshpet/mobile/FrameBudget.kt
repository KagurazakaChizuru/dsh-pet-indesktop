package io.github.dshpet.mobile

/** One consumer's playback position, as the decoder needs to see it. */
data class CursorState(val clip: ClipSpec, val index: Int)

/** A frame the decoder should produce. */
data class FrameRequest(val key: String, val clip: ClipSpec, val index: Int)

fun frameKey(clip: ClipSpec, index: Int) = "${clip.id}:$index"

/**
 * Nearest-first decode order across every consumer, duplicates merged: all
 * consumers' current frames, then all of their frame+1, and so on. Recomputing
 * this every time means a pet that just switched clips immediately outranks the
 * look-ahead work of the pets that did not.
 */
object LookaheadPlanner {
    fun pending(cursors: Collection<CursorState>, lookahead: Int,
                unavailable: (String) -> Boolean): List<FrameRequest> {
        if (cursors.isEmpty()) return emptyList()
        val ordered = ArrayList<FrameRequest>(cursors.size * (lookahead + 1))
        val seen = HashSet<String>()
        for (distance in 0..lookahead.coerceAtLeast(0)) {
            for (cursor in cursors) {
                if (cursor.clip.frames <= 0) continue
                val index = (cursor.index + distance) % cursor.clip.frames
                val key = frameKey(cursor.clip, index)
                if (!seen.add(key) || unavailable(key)) continue
                ordered += FrameRequest(key, cursor.clip, index)
            }
        }
        return ordered
    }
}

/**
 * Byte-budget LRU over cache keys. It never owns bitmaps, so it has no Android
 * dependency and can be reasoned about on its own.
 */
class FrameBudget(private val capacityBytes: Long) {
    private val weights = LinkedHashMap<String, Long>(16, .75f, true)

    val bytes: Long get() = weights.values.sum()
    val size: Int get() = weights.size

    fun contains(key: String) = weights.containsKey(key)

    /** Marks [key] as most recently used without changing its weight. */
    fun markUsed(key: String) {
        val weight = weights[key] ?: return
        weights[key] = weight
    }

    fun record(key: String, weight: Long) {
        weights[key] = weight.coerceAtLeast(0L)
    }

    fun remove(key: String) {
        weights.remove(key)
    }

    fun clear() = weights.clear()

    /** Least-recently-used keys to drop so that [incoming] more bytes fit. */
    fun overflow(incoming: Long, keep: Set<String>): List<String> {
        var total = bytes + incoming
        if (total <= capacityBytes) return emptyList()
        val dropped = ArrayList<String>(4)
        for (key in weights.keys.toList()) {
            if (total <= capacityBytes) break
            if (key in keep) continue
            dropped += key
            total -= weights.getValue(key)
        }
        return dropped
    }
}
