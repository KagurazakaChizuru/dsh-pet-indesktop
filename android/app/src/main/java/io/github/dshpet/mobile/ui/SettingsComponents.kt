package io.github.dshpet.mobile.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import io.github.dshpet.mobile.R

/** Interval values keep the unit from the resources, so English reads "60 s". */
@Composable
internal fun secondsText(seconds: Float): String = stringResource(R.string.seconds_value, seconds)

/** Bubble duration keeps one decimal: 3.2 s is the desktop default. */
@Composable
internal fun durationText(seconds: Float): String = stringResource(R.string.duration_value, seconds)

/** A whole-row switch: the label, not just the control, is the target. */
@Composable
fun SettingSwitch(label: Int, checked: Boolean, changed: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).toggleable(checked, role = Role.Switch,
        onValueChange = changed), verticalAlignment = Alignment.CenterVertically) {
        Text(stringResource(label), Modifier.weight(1f).padding(end = 16.dp))
        Switch(checked, onCheckedChange = null)
    }
}

/** Label plus current value above a slider, so the value is never colour-only. */
@Composable
fun SettingSlider(label: Int, valueText: String, value: Float, range: ClosedFloatingPointRange<Float>,
                  changed: (Float) -> Unit, onFinished: () -> Unit) {
    val labelText = stringResource(label)
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(labelText, modifier = Modifier.weight(1f))
        Text(valueText)
    }
    Slider(value = value, onValueChange = changed, onValueChangeFinished = onFinished,
        valueRange = range, modifier = Modifier.fillMaxWidth().semantics {
            contentDescription = labelText
        })
}

@Composable
fun SectionTitle(label: Int) {
    Text(stringResource(label), style = MaterialTheme.typography.titleMedium)
}
