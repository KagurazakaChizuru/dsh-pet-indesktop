package io.github.dshpet.mobile

import kotlin.math.max
import kotlin.math.ceil
import kotlin.math.min
import kotlin.math.roundToInt

/** Where a pet window sits, and where the current frame is drawn inside it. */
data class WindowPlacement(val x: Int, val y: Int, val width: Int, val height: Int)

data class ContentOffset(val x: Float, val y: Float)

/**
 * The overlay window is the union of every clip's alpha box, so its size is
 * fixed for a character instead of changing with each animation. Only the
 * drawing offset inside the window changes, which keeps the body anchor and the
 * on-screen position of every clip identical to the earlier per-clip windows.
 */
object WindowGeometry {
    fun union(clips: Collection<ClipSpec>): SourceBox {
        require(clips.isNotEmpty()) { "no clips" }
        var left = Double.MAX_VALUE
        var top = Double.MAX_VALUE
        var right = -Double.MAX_VALUE
        var bottom = -Double.MAX_VALUE
        for (clip in clips) {
            left = min(left, clip.crop.left)
            top = min(top, clip.crop.top)
            right = max(right, clip.crop.right)
            bottom = max(bottom, clip.crop.bottom)
        }
        return SourceBox(left, top, right, bottom)
    }

    fun placement(bodyX: Double, bodyY: Double, body: SourceBox, union: SourceBox,
                  scale: Double, safeLeft: Int, safeTop: Int): WindowPlacement {
        val pad = pulsePadding(union, scale)
        val width = max(1, ceil(union.width * scale).toInt()) + 2 * pad
        val height = max(1, (union.height * scale).roundToInt())
        val x = (safeLeft + (bodyX + union.left - body.left) * scale).roundToInt() - pad
        val y = (safeTop + (bodyY + union.top - body.top) * scale).roundToInt()
        return WindowPlacement(x, y, width, height)
    }

    fun contentOffset(crop: SourceBox, union: SourceBox, scale: Double): ContentOffset =
        ContentOffset(((crop.left - union.left) * scale + pulsePadding(union, scale)).toFloat(),
            ((crop.top - union.top) * scale).toFloat())

    private fun pulsePadding(union: SourceBox, scale: Double) =
        ceil(union.width * scale * Squash.WIDEN / 2).toInt().coerceAtLeast(0)
}
