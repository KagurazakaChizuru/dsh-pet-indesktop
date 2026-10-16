package io.github.dshpet.mobile.ui

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.res.stringResource
import io.github.dshpet.mobile.PetOptions
import io.github.dshpet.mobile.R

/**
 * Pet-to-pet collision. The switch is the module's enable bit; the bounce is the
 * one feel knob worth exposing (the desktop also fixes friction, mass and the
 * impulse cap).
 */
@Composable
fun CollisionSection(options: PetOptions, onChanged: (PetOptions) -> Unit) {
    SettingSwitch(R.string.collision, options.collision) {
        onChanged(options.copy(collision = it))
    }
    if (options.collision) {
        var draft by remember(options.collisionRestitution) {
            mutableStateOf(options.collisionRestitution)
        }
        SettingSlider(label = R.string.collision_restitution,
            valueText = "${(draft * 100).toInt()}%",
            value = draft,
            range = 0f..1f,
            changed = { draft = it },
            onFinished = { onChanged(options.copy(collisionRestitution = draft)) })
        Text(stringResource(R.string.collision_hint))
    }
}
