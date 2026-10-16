package io.github.dshpet.mobile

/**
 * Companion pets are stored as normalized positions in one preference string
 * ("x,y;x,y"), so the private phone store stays flat and migratable.
 */
object CompanionCodec {
    /** Mother plus four companions; every one is an independent overlay window. */
    const val MAX_COMPANIONS = 4

    /** New companions are drawn smaller than the mother, as baby whales. */
    const val COMPANION_SCALE = .75

    fun encode(layout: List<Pair<Double, Double>>): String = layout.take(MAX_COMPANIONS)
        .joinToString(";") {
            "${it.first.takeIf(Double::isFinite)?.coerceIn(0.0, 1.0) ?: 0.0}," +
                "${it.second.takeIf(Double::isFinite)?.coerceIn(0.0, 1.0) ?: 0.0}"
        }

    fun decode(text: String?): List<Pair<Double, Double>> {
        if (text.isNullOrBlank()) return emptyList()
        val layout = ArrayList<Pair<Double, Double>>(MAX_COMPANIONS)
        for (entry in text.split(';')) {
            val parts = entry.split(',')
            if (parts.size != 2) continue
            val x = parts[0].trim().toDoubleOrNull() ?: continue
            val y = parts[1].trim().toDoubleOrNull() ?: continue
            if (!x.isFinite() || !y.isFinite()) continue
            layout += x.coerceIn(0.0, 1.0) to y.coerceIn(0.0, 1.0)
            if (layout.size == MAX_COMPANIONS) break
        }
        return layout
    }

    /** Desktop `_spawn_sprite_pos`: body right edge plus 24 source pixels per sibling. */
    fun spawnOffset(index: Int) = 24.0 * index.coerceAtLeast(1)
}
