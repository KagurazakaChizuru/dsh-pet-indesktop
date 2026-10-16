package io.github.dshpet.mobile.modules

import io.github.dshpet.mobile.CompanionCodec
import io.github.dshpet.mobile.ModuleIds
import io.github.dshpet.mobile.PetHandle
import io.github.dshpet.mobile.R

/**
 * Baby whales: up to four independent companions beside the mother pet. The
 * policy lives here; the service creates and tears down the windows. Switching
 * the module off takes every companion down with it.
 */
class CompanionModule : HostBoundModule() {
    override val id = ModuleIds.COMPANION

    override fun menuItems(pet: PetHandle): List<ModuleMenu> {
        val items = ArrayList<ModuleMenu>(2)
        if (host.companionCount() < CompanionCodec.MAX_COMPANIONS) {
            items += ModuleMenu(R.string.spawn_companion) { host.spawnCompanion() }
        }
        if (host.companionCount() > 0) {
            items += ModuleMenu(R.string.exit_companion) { host.exitCompanion(pet) }
        }
        return items
    }

    override fun onDisable() {
        host.pets.filter { it.isCompanion }.forEach { host.exitCompanion(it) }
    }

    override fun diagnostics() = "companions=${host.companionCount()}"
}
