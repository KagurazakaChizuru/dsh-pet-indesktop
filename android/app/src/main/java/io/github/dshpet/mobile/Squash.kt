package io.github.dshpet.mobile

import kotlin.math.PI
import kotlin.math.max
import kotlin.math.sin

/**
 * The tap feedback the desktop calls Q 弹 (`pet/pet_sprite.py::_squashed_rect`):
 * a 220 ms pulse that widens the frame by up to 10% and shortens it by up to
 * 15%, anchored on the bottom centre so the pet squashes in place instead of
 * jumping. `pulse = sin(π·progress)` means it returns to normal on its own.
 */
object Squash {
    const val DURATION_SECONDS = 0.220
    const val WIDEN = 0.10
    private const val SHORTEN = 0.15

    /** Returns {left, top, width, height} for the frame at [progress] 0..1. */
    fun geometry(left: Float, top: Float, width: Float, height: Float,
                 progress: Double): FloatArray {
        val pulse = sin(PI * progress.coerceIn(0.0, 1.0))
        val scaledWidth = max(1f, (width * (1.0 + WIDEN * pulse)).toFloat())
        val scaledHeight = max(1f, (height * (1.0 - SHORTEN * pulse)).toFloat())
        val centre = left + width / 2f
        val bottom = top + height
        return floatArrayOf(centre - scaledWidth / 2f, bottom - scaledHeight,
            scaledWidth, scaledHeight)
    }
}
