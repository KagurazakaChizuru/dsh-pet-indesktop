package io.github.dshpet.mobile.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import io.github.dshpet.mobile.PetOptions
import io.github.dshpet.mobile.R

/**
 * The click sound module. The bundled MIT duck pair is the
 * default source; a file picked on the phone replaces it until cleared.
 */
@Composable
@OptIn(ExperimentalLayoutApi::class)
fun ClickSoundSection(options: PetOptions, sourceLabel: String?, onChanged: (PetOptions) -> Unit,
                      onPick: () -> Unit, onPreview: () -> Unit, loading: Boolean, failed: Boolean) {
    SettingSwitch(R.string.click_sound, options.clickSound) {
        onChanged(options.copy(clickSound = it))
    }
    if (options.clickSound) {
        var volumeDraft by remember(options.clickSoundVolume) { mutableStateOf(options.clickSoundVolume) }
        SettingSlider(label = R.string.click_sound_volume,
            valueText = "${(volumeDraft * 100).toInt()}%",
            value = volumeDraft,
            range = 0f..1f,
            changed = { volumeDraft = it },
            onFinished = { onChanged(options.copy(clickSoundVolume = volumeDraft)) })
        HorizontalDivider()
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(stringResource(R.string.click_sound_source))
            Text(if (options.clickSoundUri == null) stringResource(R.string.click_sound_builtin)
                else sourceLabel ?: stringResource(R.string.click_sound_selected))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = onPreview, enabled = !loading) {
                    Icon(Icons.AutoMirrored.Filled.VolumeUp, null)
                    Text(stringResource(if (loading) R.string.click_sound_loading else R.string.click_sound_preview))
                }
                TextButton(onClick = onPick) { Text(stringResource(R.string.click_sound_pick)) }
                if (options.clickSoundUri != null) {
                    TextButton(onClick = { onChanged(options.copy(clickSoundUri = null)) }) {
                        Text(stringResource(R.string.click_sound_clear))
                    }
                }
            }
            if (failed) Text(stringResource(R.string.click_sound_failed),
                color = MaterialTheme.colorScheme.error)
            Text(stringResource(R.string.click_sound_hint))
        }
    }
}
