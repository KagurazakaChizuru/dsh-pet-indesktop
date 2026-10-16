package io.github.dshpet.mobile

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * One pet's collision body, expressed in a single shared space: the mother's
 * source pixels. A companion passes its geometry through its own scale ratio,
 * so a baby whale really is a smaller, lighter obstacle.
 */
data class CollisionBody(
    val id: Int,
    val left: Double,
    val top: Double,
    val width: Double,
    val height: Double,
    val vx: Double,
    val vy: Double,
    val mass: Double,
    /** Being dragged: the finger owns it, so it pushes others but never moves. */
    val immovable: Boolean,
)

/** What the solver decided for one body this tick. */
data class CollisionOutcome(
    val id: Int,
    val dx: Double,
    val dy: Double,
    val dvx: Double,
    val dvy: Double,
    val impulse: Double,
) {
    val hit get() = impulse >= Collision.HIT_MIN_DV
    val moved get() = dx != 0.0 || dy != 0.0
}

/**
 * Pet-to-pet collision, ported from `pet/collision.py`: a three-circle chain
 * inscribed in the body box, one impulse per pair per tick, then inverse-mass
 * weighted position separation, deepest overlap first, recomputed for a few
 * rounds. A fast pet also gets a swept test, because a thrown pet crosses about
 * 200 source pixels per frame and would otherwise pass straight through.
 *
 * Deviations from the desktop, deliberately small and documented:
 *  - units stay the engine's source pixels (0.1.0 already ported gravity and the
 *    speed caps numerically), so the visual trigger speed differs by the render
 *    scale ratio;
 *  - the swept test uses one circle per body rather than all nine pairs;
 *  - the desktop's "three consecutive overlapping ticks" anti-jitter override and
 *    its island/static world are not ported (Android has no static world).
 */
object Collision {
    const val RESTITUTION = .82
    const val FRICTION = .08
    const val IMPULSE_CAP = 9000.0
    const val MIN_APPROACH_SPEED = 80.0

    /** Below this the impulse is absorbed rather than applied (`HIT_MIN_DV`). */
    const val HIT_MIN_DV = 300.0

    const val MIN_SEPARATION = 1.0
    const val MAX_SEPARATION = 12.0
    const val SLOP = .5
    const val OVERLAP_RATIO = .6
    const val ITERATIONS = 4

    /** `calculate_mass`: size matters through the scale ratio, clamped like the desktop. */
    fun mass(scaleRatio: Double): Double = (scaleRatio * scaleRatio).coerceIn(.5, 2.5)

    /** Three equal circles inscribed in the body rect (`circles_from_rect`). */
    fun circles(left: Double, top: Double, width: Double, height: Double): List<DoubleArray> {
        val radius = min(width, height) / 2.0
        val cx = left + width / 2.0
        val cy = top + height / 2.0
        return if (width >= height) {
            listOf(doubleArrayOf(left + radius, cy, radius),
                doubleArrayOf(cx, cy, radius),
                doubleArrayOf(left + width - radius, cy, radius))
        } else {
            listOf(doubleArrayOf(cx, top + radius, radius),
                doubleArrayOf(cx, cy, radius),
                doubleArrayOf(cx, top + height - radius, radius))
        }
    }

    private class Contact(val i: Int, val j: Int, val overlap: Double,
                          val nx: Double, val ny: Double, val forceFull: Boolean)

    private class Overlap(val overlap: Double, val nx: Double, val ny: Double)

    /** [dt] only feeds the swept test; everything else is position/velocity based. */
    fun solve(bodies: List<CollisionBody>, restitution: Double, dt: Double,
              iterations: Int = ITERATIONS): List<CollisionOutcome> {
        if (bodies.size < 2) return emptyList()
        val inverseMass = bodies.map {
            if (it.immovable || it.mass <= 0.0) 0.0 else 1.0 / it.mass
        }
        val dx = DoubleArray(bodies.size)
        val dy = DoubleArray(bodies.size)
        val dvx = DoubleArray(bodies.size)
        val dvy = DoubleArray(bodies.size)
        val impulseAcc = DoubleArray(bodies.size)

        val contacts = ArrayList<Contact>(4)
        val passedThrough = ArrayList<Contact>(2)
        for (i in bodies.indices) {
            for (j in i + 1 until bodies.size) {
                val a = bodies[i]
                val b = bodies[j]
                val discrete = overlap(a, b)
                val contact = if (discrete != null) {
                    Contact(i, j, discrete.overlap, discrete.nx, discrete.ny, false)
                } else {
                    val swept = swept(a, b, dt) ?: continue
                    Contact(i, j, swept.overlap, swept.nx, swept.ny, true)
                }
                contacts += contact
                if (contact.forceFull) passedThrough += contact
                val push = applyImpulse(bodies[i], bodies[j], inverseMass[i], inverseMass[j],
                    contact, restitution)
                if (push != null) {
                    dvx[i] -= push[0] * inverseMass[i]
                    dvy[i] -= push[1] * inverseMass[i]
                    dvx[j] += push[0] * inverseMass[j]
                    dvy[j] += push[1] * inverseMass[j]
                    val applied = hypot(push[0], push[1])
                    impulseAcc[i] = max(impulseAcc[i], applied * inverseMass[i])
                    impulseAcc[j] = max(impulseAcc[j], applied * inverseMass[j])
                }
            }
        }
        if (contacts.isEmpty()) return emptyList()

        // A pass-through has no *current* overlap to separate, so it is separated
        // once from its own contact geometry (the desktop does the same for swept
        // pairs) instead of going through the iteration rounds below.
        for (contact in passedThrough) {
            separate(inverseMass, contact, contact.overlap, contact.nx, contact.ny, dx, dy)
        }

        for (round in 0 until iterations.coerceAtLeast(1)) {
            val work = contacts.mapNotNull { contact ->
                if (contact.forceFull) return@mapNotNull null
                val current = overlapNow(bodies, contact, dx, dy) ?: return@mapNotNull null
                if (current.overlap <= SLOP) null else Triple(contact, current, current.overlap)
            }.sortedWith(compareByDescending<Triple<Contact, Overlap, Double>> { it.third }
                .thenBy { it.first.i }.thenBy { it.first.j })
            if (work.isEmpty()) break
            for ((contact, current, _) in work) {
                separate(inverseMass, contact, current.overlap, current.nx, current.ny, dx, dy)
            }
        }

        return bodies.indices.map { index ->
            CollisionOutcome(bodies[index].id, dx[index], dy[index], dvx[index], dvy[index],
                impulseAcc[index])
        }
    }

    /** Inverse-mass weighted separation: A moves along −n, B along +n. */
    private fun separate(inverseMass: List<Double>, contact: Contact, overlap: Double,
                         nx: Double, ny: Double, dx: DoubleArray, dy: DoubleArray) {
        val sum = inverseMass[contact.i] + inverseMass[contact.j]
        if (sum <= 0.0) return
        val forceFull = contact.forceFull || overlap > MAX_SEPARATION * 4
        val effective = max(0.0, overlap - SLOP)
        val distance = if (forceFull) min(overlap, MAX_SEPARATION * 4)
        else max(MIN_SEPARATION, min(MAX_SEPARATION, effective * OVERLAP_RATIO))
        val fractionA = inverseMass[contact.i] / sum
        val fractionB = inverseMass[contact.j] / sum
        dx[contact.i] -= nx * distance * fractionA
        dy[contact.i] -= ny * distance * fractionA
        dx[contact.j] += nx * distance * fractionB
        dy[contact.j] += ny * distance * fractionB
    }

    /** Deepest overlapping circle pair, broad-phased by the body boxes. */
    private fun overlap(a: CollisionBody, b: CollisionBody): Overlap? {
        val acx = a.left + a.width / 2.0
        val acy = a.top + a.height / 2.0
        val bcx = b.left + b.width / 2.0
        val bcy = b.top + b.height / 2.0
        if (abs(bcx - acx) >= a.width / 2 + b.width / 2 ||
            abs(bcy - acy) >= a.height / 2 + b.height / 2) return null
        var best: Overlap? = null
        for (circleA in circles(a.left, a.top, a.width, a.height)) {
            for (circleB in circles(b.left, b.top, b.width, b.height)) {
                val dx = circleB[0] - circleA[0]
                val dy = circleB[1] - circleA[1]
                val distance = hypot(dx, dy)
                val overlap = circleA[2] + circleB[2] - distance
                if (overlap <= 0.0) continue
                if (best != null && overlap <= best!!.overlap) continue
                if (distance <= 1e-6) {
                    val direction = fallbackDirection(a.id, b.id)
                    best = Overlap(overlap, direction[0], direction[1])
                } else {
                    best = Overlap(overlap, dx / distance, dy / distance)
                }
            }
        }
        return best
    }

    /** The same overlap, measured from the positions the solver has produced so far. */
    private fun overlapNow(bodies: List<CollisionBody>, contact: Contact,
                           dx: DoubleArray, dy: DoubleArray): Overlap? {
        val a = bodies[contact.i].shifted(dx[contact.i], dy[contact.i])
        val b = bodies[contact.j].shifted(dx[contact.j], dy[contact.j])
        return overlap(a, b)
    }

    private fun CollisionBody.shifted(x: Double, y: Double) =
        CollisionBody(id, left + x, top + y, width, height, vx, vy, mass, immovable)

    /**
     * Relative motion test: a thrown pet crosses far more than its own width in
     * one frame, so a discrete overlap check would miss the other pet entirely.
     */
    private fun swept(a: CollisionBody, b: CollisionBody, dt: Double): Overlap? {
        if (dt <= 0.0) return null
        val ax = a.left + a.width / 2.0
        val ay = a.top + a.height / 2.0
        val bx = b.left + b.width / 2.0
        val by = b.top + b.height / 2.0
        val radius = min(a.width, a.height) / 2.0 + min(b.width, b.height) / 2.0
        val px = ax - bx
        val py = ay - by
        val vx = (a.vx - b.vx) * dt
        val vy = (a.vy - b.vy) * dt
        val start = px * px + py * py - radius * radius
        if (start <= 0.0) return null
        val speedSquared = vx * vx + vy * vy
        if (speedSquared <= 1e-9) return null
        val linear = px * vx + py * vy
        val discriminant = linear * linear - speedSquared * start
        if (discriminant < 0.0) return null
        val time = (-linear - sqrt(discriminant)) / speedSquared
        if (time !in 0.0..1.0) return null
        val cx = px + vx * time
        val cy = py + vy * time
        val distance = hypot(cx, cy)
        if (distance <= 1e-9) return null
        // The normal points from A to B; the contact is reported as a full overlap.
        return Overlap(1.0, -cx / distance, -cy / distance)
    }

    private fun applyImpulse(a: CollisionBody, b: CollisionBody, invA: Double, invB: Double,
                             contact: Contact, restitution: Double): DoubleArray? {
        val sum = invA + invB
        if (sum <= 0.0) return null
        val normalVelocity = (b.vx - a.vx) * contact.nx + (b.vy - a.vy) * contact.ny
        if (normalVelocity >= 0.0) return null
        var bounce = restitution.coerceIn(0.0, 1.0)
        // A slow touch is inelastic: it kills the approach speed without jitter.
        if (normalVelocity >= -MIN_APPROACH_SPEED) bounce = 0.0
        var jn = -(1.0 + bounce) * normalVelocity / sum
        val cap = IMPULSE_CAP / max(invA, invB)
        jn = min(jn, cap)
        var jx = jn * contact.nx
        var jy = jn * contact.ny
        // Tangential friction, Coulomb-limited by the normal impulse.
        val tx = -contact.ny
        val ty = contact.nx
        val tangential = (b.vx - a.vx) * tx + (b.vy - a.vy) * ty
        if (abs(tangential) > 1e-6) {
            val ideal = -tangential / sum
            val limit = FRICTION * abs(jn)
            val jt = ideal.coerceIn(-limit, limit)
            jx += jt * tx
            jy += jt * ty
        }
        return doubleArrayOf(jx, jy)
    }

    /** Coincident centres have no direction; derive one deterministically. */
    private fun fallbackDirection(idA: Int, idB: Int): DoubleArray {
        val angle = ((idA * 31 + idB * 17) % 360) * (Math.PI / 180.0)
        return doubleArrayOf(cos(angle), sin(angle))
    }
}
