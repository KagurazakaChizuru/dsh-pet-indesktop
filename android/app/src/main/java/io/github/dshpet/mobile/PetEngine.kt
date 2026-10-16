package io.github.dshpet.mobile

import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.tanh
import kotlin.random.Random

enum class PetMode { IDLE, TURN, MOVE, CLICK, DRAG, THROWN }

data class ThrowStep(val x: Double, val y: Double, val vx: Double, val vy: Double, val bounced: Boolean)

/** Source-pixel units, matching pet.physics.throw_step's public behavior. */
object ThrowMath {
    fun step(x: Double, y: Double, vx: Double, vy: Double, dt: Double,
             right: Double, bottom: Double): ThrowStep {
        var nx = x + vx * dt
        var nvy = vy + 1400.0 * dt
        var ny = y + nvy * dt
        var nvx = vx
        var bounced = false
        if (nx < 0) { nx = 0.0; nvx = abs(nvx) * .68; bounced = true }
        else if (nx > right) { nx = right; nvx = -abs(nvx) * .68; bounced = true }
        if (ny < 0) { ny = 0.0; nvy = abs(nvy) * .68; bounced = true }
        else if (ny >= bottom) {
            ny = bottom
            nvx *= max(0.0, 1 - 2.5 * dt)
            nvy = if (abs(nvy) < 120.0) 0.0 else -abs(nvy) * .68
            bounced = true
        }
        return ThrowStep(nx, ny, nvx, nvy, bounced)
    }
}

/** The service owns the clock; this model has no threads, Android calls, or I/O. */
class PetEngine(clips: List<ClipSpec>, private val random: Random = Random.Default) {
    private val groups = clips.groupBy { it.group }
    var clip: ClipSpec = groups.getValue("idle").first()
        private set
    var mode = PetMode.IDLE
        private set
    var x = 0.0
        private set
    var y = 0.0
        private set
    var vx = 0.0
        private set
    var vy = 0.0
        private set
    var facingRight = false
        private set
    var paused = false
    var wander = true
    private var right = 0.0
    private var bottom = 0.0
    private var elapsed = 0.0
    private var moveStart = 0.0
    private var moveTarget = 0.0
    private var pendingMove: ClipSpec? = null
    val normalizedX get() = if (right > 0) (x / right).coerceIn(0.0, 1.0) else 0.0
    val normalizedY get() = if (bottom > 0) (y / bottom).coerceIn(0.0, 1.0) else 0.0
    val frameIndex get() = (elapsed * clip.fps).toInt().coerceIn(0, clip.frames - 1)

    /** Parks the pet: used when the wander module is switched off mid-stride. */
    fun stopWandering() {
        wander = false
        if (mode == PetMode.MOVE || mode == PetMode.TURN) idle()
    }

    /** Source-pixel placement, for a freshly spawned companion. */
    fun placeAt(bodyX: Double, bodyY: Double) {
        if (bodyX.isFinite()) x = bodyX.coerceIn(0.0, right)
        if (bodyY.isFinite()) y = bodyY.coerceIn(0.0, bottom)
    }

    /** Position-only separation from a collision that carried no usable impulse. */
    fun shift(dx: Double, dy: Double) {
        if (paused) return
        if (dx.isFinite()) x = (x + dx).coerceIn(0.0, right)
        if (dy.isFinite()) y = (y + dy).coerceIn(0.0, bottom)
    }

    /** A real collision hit: move, take the impulse, and let gravity take over. */
    fun nudge(dx: Double, dy: Double, dvx: Double, dvy: Double) {
        if (paused || mode == PetMode.DRAG) return
        shift(dx, dy)
        if (!vx.isFinite() || !vy.isFinite() || !dvx.isFinite() || !dvy.isFinite()) return
        vx += dvx
        vy += dvy
        facingRight = vx > 0
        if (mode != PetMode.THROWN) enter(PetMode.THROWN, pick("drag"))
    }

    fun resize(width: Double, height: Double) {
        val rx = normalizedX; val ry = normalizedY
        right = width.takeIf { it.isFinite() }?.coerceAtLeast(0.0) ?: 0.0
        bottom = height.takeIf { it.isFinite() }?.coerceAtLeast(0.0) ?: 0.0
        restorePosition(rx, ry)
        if (mode == PetMode.MOVE || mode == PetMode.TURN || mode == PetMode.DRAG) idle()
    }

    fun restorePosition(normalizedX: Double, normalizedY: Double) {
        x = (normalizedX.takeIf { it.isFinite() } ?: .7).coerceIn(0.0, 1.0) * right
        y = (normalizedY.takeIf { it.isFinite() } ?: 1.0).coerceIn(0.0, 1.0) * bottom
    }

    private fun pick(group: String) = groups.getValue(group).random(random)
    private fun enter(next: PetMode, animation: ClipSpec) {
        mode = next; clip = animation; elapsed = 0.0
    }
    private fun idle() {
        vx = 0.0; vy = 0.0; pendingMove = null
        enter(PetMode.IDLE, pick("idle"))
    }
    fun click() { vx = 0.0; vy = 0.0; pendingMove = null; enter(PetMode.CLICK, pick("click")) }
    fun beginDrag() { vx = 0.0; vy = 0.0; pendingMove = null; enter(PetMode.DRAG, pick("drag")) }
    fun cancelDrag() { if (mode == PetMode.DRAG) idle() }
    fun dragTo(bodyX: Double, bodyY: Double) {
        if (mode != PetMode.DRAG) return
        if (bodyX.isFinite()) x = bodyX.coerceIn(0.0, right)
        if (bodyY.isFinite()) y = bodyY.coerceIn(0.0, bottom)
    }
    fun release(velocityX: Double, velocityY: Double) {
        if (mode != PetMode.DRAG) return
        val speed = hypot(velocityX, velocityY)
        if (paused || !speed.isFinite() || speed < 500) { idle(); return }
        val capped = 4800 * tanh(speed / 4800)
        vx = velocityX * capped / speed
        vy = velocityY * capped / speed
        facingRight = vx > 0
        enter(PetMode.THROWN, pick("drag"))
    }

    fun advance(seconds: Double) {
        if (paused || !seconds.isFinite() || seconds <= 0) return
        val dt = min(seconds, .05)
        elapsed += dt
        when (mode) {
            PetMode.DRAG -> elapsed %= clip.duration
            PetMode.THROWN -> {
                elapsed %= clip.duration
                val step = ThrowMath.step(x, y, vx, vy, dt, right, bottom)
                x = step.x; y = step.y; vx = step.vx; vy = step.vy
                if (abs(vx) > 15) facingRight = vx > 0
                if ((y >= bottom - 1 && abs(vy) < 1 && abs(vx) < 15) ||
                    (step.bounced && hypot(vx, vy) < 40 && abs(vy) < 1)) idle()
            }
            PetMode.MOVE -> {
                if (!wander) { idle(); return }
                val phase = (elapsed / clip.duration).coerceIn(0.0, 1.0)
                val progress = if (clip.curve.size < 2) phase else {
                    val offset = phase * (clip.curve.size - 1)
                    val i = offset.toInt()
                    val a = clip.curve[i]
                    val b = clip.curve[min(i + 1, clip.curve.lastIndex)]
                    a + (b - a) * (offset - i)
                }
                x = (moveStart + (moveTarget - moveStart) * progress).coerceIn(0.0, right)
                if (elapsed >= clip.duration) idle()
            }
            PetMode.CLICK -> if (elapsed >= clip.duration) idle()
            PetMode.TURN -> if (elapsed >= clip.duration) {
                val next = pendingMove
                if (next != null && wander) {
                    facingRight = moveTarget > x
                    moveStart = x
                    enter(PetMode.MOVE, next)
                } else idle()
            }
            PetMode.IDLE -> if (elapsed >= clip.duration) {
                if (!wander || right == 0.0 || random.nextDouble() < .6) idle()
                else {
                    val animation = pick("move")
                    val direction = if (x < right * .2) 1 else if (x > right * .8) -1 else if (random.nextBoolean()) 1 else -1
                    moveTarget = (x + direction * animation.stride).coerceIn(0.0, right)
                    moveStart = x
                    pendingMove = animation
                    if ((moveTarget > x) != facingRight) enter(PetMode.TURN, pick("turn"))
                    else enter(PetMode.MOVE, animation)
                }
            }
        }
    }
}
