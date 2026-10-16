package io.github.dshpet.mobile.modules

import io.github.dshpet.mobile.Collision
import io.github.dshpet.mobile.CollisionBody
import io.github.dshpet.mobile.ModuleIds
import io.github.dshpet.mobile.PetHandle
import io.github.dshpet.mobile.PetMode

/**
 * Pet-to-pet collision, the desktop's 多开碰撞. Off means pets pass through each
 * other; on, they push and bounce with the desktop's constants. A pet being
 * dragged is immovable, so the finger always wins; a real hit (the desktop's
 * `HIT_MIN_DV`) also plays the Q 弹 pulse, exactly like the desktop's overlay.
 */
class CollisionModule : HostBoundModule() {
    override val id = ModuleIds.COLLISION

    var hits = 0L
        private set
    var separations = 0L
        private set

    override fun onTick(dt: Double) {
        val pets = host.pets
        if (pets.size < 2) return
        val body = host.bodyBox
        val bodies = pets.mapNotNull { pet ->
            val ratio = host.scaleRatio(pet)
            if (!ratio.isFinite() || ratio <= 0.0) return@mapNotNull null
            CollisionBody(
                id = pet.id,
                // Engine positions already name the body's top-left, not the canvas.
                left = pet.engine.x * ratio,
                top = pet.engine.y * ratio,
                width = body.width * ratio,
                height = body.height * ratio,
                vx = pet.engine.vx * ratio,
                vy = pet.engine.vy * ratio,
                mass = Collision.mass(ratio),
                immovable = pet.engine.mode == PetMode.DRAG || pet.engine.paused,
            )
        }
        if (bodies.size < 2) return
        val outcomes = Collision.solve(bodies, host.options.collisionRestitution.toDouble(), dt)
        for (outcome in outcomes) {
            if (!outcome.hit && !outcome.moved) continue
            val pet = pets.firstOrNull { it.id == outcome.id } ?: continue
            val ratio = host.scaleRatio(pet)
            if (!ratio.isFinite() || ratio <= 0.0) continue
            if (outcome.hit) {
                hits++
                pet.engine.nudge(outcome.dx / ratio, outcome.dy / ratio,
                    outcome.dvx / ratio, outcome.dvy / ratio)
                host.squash(pet)
            } else {
                separations++
                pet.engine.shift(outcome.dx / ratio, outcome.dy / ratio)
            }
        }
    }

    override fun diagnostics() = "collisionHits=$hits collisionPushes=$separations"
}
