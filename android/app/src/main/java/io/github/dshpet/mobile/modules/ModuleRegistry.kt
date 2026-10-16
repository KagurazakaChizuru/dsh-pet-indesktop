package io.github.dshpet.mobile.modules

import io.github.dshpet.mobile.PetHandle

/**
 * Owns the enabled module set. Only enabled modules exist as objects, and only
 * they see frames, events and menu contributions, so switching a capability off
 * removes its work rather than hiding it.
 */
class ModuleRegistry(private val host: ModuleHost, factories: List<ModuleFactory>) {
    private val factories = LinkedHashMap<String, ModuleFactory>().apply {
        factories.forEach { put(it.id, it) }
    }
    private val active = LinkedHashMap<String, PetModule>()

    var enabledCount = 0L
        private set
    var disabledCount = 0L
        private set
    var framesDispatched = 0L
        private set
    var ticksDispatched = 0L
        private set

    fun ids(): Set<String> = factories.keys

    /** The modules that exist right now, for diagnostics and for the settings screen. */
    fun activeIds(): Set<String> = active.keys

    fun isActive(id: String): Boolean = active.containsKey(id)

    fun instance(id: String): PetModule? = active[id]

    /** Creates, enables, disables or drops modules so they match the preferences. */
    fun apply() {
        for ((id, factory) in factories) {
            val wanted = host.options.enables(id)
            val live = active[id]
            when {
                wanted && live == null -> {
                    val module = factory.create()
                    module.enable(host)
                    active[id] = module
                    enabledCount++
                }
                !wanted && live != null -> {
                    live.disable()
                    active.remove(id)
                    disabledCount++
                }
            }
        }
        active.values.toList().forEach { it.onOptionsChanged() }
    }

    fun onFrame(pet: PetHandle, dt: Double) {
        if (active.isEmpty()) return
        framesDispatched++
        active.values.toList().forEach { it.onFrame(pet, dt) }
    }

    /** Once per frame, before the per-pet callbacks. */
    fun onTick(dt: Double) {
        if (active.isEmpty()) return
        ticksDispatched++
        active.values.toList().forEach { it.onTick(dt) }
    }

    fun onEvent(event: PetEvent) {
        if (active.isEmpty()) return
        active.values.toList().forEach { it.onEvent(event) }
    }

    fun menuItems(pet: PetHandle): List<ModuleMenu> {
        if (active.isEmpty()) return emptyList()
        return active.values.toList().flatMap { it.menuItems(pet) }
    }

    fun diagnostics(): String =
        active.values.toList().map { it.diagnostics() }.filter { it.isNotEmpty() }.joinToString(" ")

    /** Stops every module; used when the pet itself is stopping. */
    fun shutdown() {
        active.values.toList().forEach { it.disable() }
        active.clear()
    }
}
