package io.github.dshpet.mobile

/**
 * What the pet is currently showing. The bitmap and the crop it belongs to are
 * replaced together or not at all: a frame that has not decoded yet leaves the
 * previous pair on screen instead of being drawn with the next clip's crop,
 * which is what made every clip switch flash. [revision] identifies the decoded
 * pixels, because a reused bitmap can be the same instance with new content.
 *
 * Generic so the rule can be exercised without a device.
 */
class DisplayState<T : Any> {
    data class Frame<T : Any>(val bitmap: T, val revision: Long, val crop: SourceBox,
                              val mirrored: Boolean)

    var frame: Frame<T>? = null
        private set

    /** Returns true when the view must redraw. A null bitmap means "not decoded yet". */
    fun present(bitmap: T?, revision: Long, crop: SourceBox, mirrored: Boolean): Boolean {
        if (bitmap == null) return false
        val current = frame
        if (current != null && current.revision == revision && current.crop == crop &&
            current.mirrored == mirrored) return false
        frame = Frame(bitmap, revision, crop, mirrored)
        return true
    }

    fun clear() {
        frame = null
    }
}
