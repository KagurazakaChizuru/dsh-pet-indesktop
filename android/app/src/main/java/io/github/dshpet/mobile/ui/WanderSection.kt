package io.github.dshpet.mobile.ui

import androidx.compose.runtime.Composable
import io.github.dshpet.mobile.PetOptions
import io.github.dshpet.mobile.R

/** The wander module's one switch; switching it off parks every pet in its idle loop. */
@Composable
fun WanderSection(options: PetOptions, onChanged: (PetOptions) -> Unit) {
    SettingSwitch(R.string.wander, options.wander) { onChanged(options.copy(wander = it)) }
}
