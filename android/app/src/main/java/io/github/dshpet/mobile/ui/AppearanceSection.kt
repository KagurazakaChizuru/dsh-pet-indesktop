package io.github.dshpet.mobile.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import io.github.dshpet.mobile.PetOptions
import io.github.dshpet.mobile.R

/** Size is committed when the finger leaves the slider (commit_policy: on_finish). */
@Composable
fun AppearanceSection(options: PetOptions, onChanged: (PetOptions) -> Unit) {
    var draft by remember(options.size) { mutableStateOf(options.size) }
    SettingSlider(label = R.string.pet_size,
        valueText = "${(draft * 100).toInt()}%",
        value = draft,
        range = .6f..1.6f,
        changed = { draft = it },
        onFinished = { onChanged(options.copy(size = draft)) })
}
