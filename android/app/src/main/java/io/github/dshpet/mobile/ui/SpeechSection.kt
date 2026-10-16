package io.github.dshpet.mobile.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import io.github.dshpet.mobile.PetOptions
import io.github.dshpet.mobile.PhraseBook
import io.github.dshpet.mobile.R

/**
 * The speech module: the bubble switch, the user's line pool and the schedule.
 * The pool commits on finish (save button or leaving the field); empty falls
 * back to the built-in lines, exactly like the desktop config.
 */
@Composable
fun SpeechSection(options: PetOptions, builtinCount: Int, onChanged: (PetOptions) -> Unit) {
    SettingSwitch(R.string.speech, options.speech) { onChanged(options.copy(speech = it)) }
    if (options.speech) {
        val savedText = PhraseBook.asText(options.phrases)
        var draft by remember(options.phrases) { mutableStateOf(savedText) }
        val commit = { onChanged(options.copy(phrases = PhraseBook.fromText(draft))) }
        Text(stringResource(R.string.speech_phrases))
        OutlinedTextField(
            value = draft,
            onValueChange = { draft = it },
            modifier = Modifier.fillMaxWidth().onFocusChanged { if (!it.isFocused && draft != savedText) commit() },
            minLines = 3,
            maxLines = 6,
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences,
                imeAction = ImeAction.Done),
            placeholder = { Text(stringResource(R.string.speech_phrases_hint)) })
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TextButton(onClick = commit, enabled = draft != savedText) {
                Text(stringResource(R.string.speech_save))
            }
            TextButton(onClick = {
                draft = ""
                onChanged(options.copy(phrases = emptyList()))
            }) { Text(stringResource(R.string.speech_clear)) }
        }
        Text(stringResource(R.string.speech_builtin_hint, builtinCount))
        HorizontalDivider()
        var minDraft by remember(options.speechMinSeconds) { mutableStateOf(options.speechMinSeconds) }
        var maxDraft by remember(options.speechMaxSeconds) { mutableStateOf(options.speechMaxSeconds) }
        var durationDraft by remember(options.speechSeconds) { mutableStateOf(options.speechSeconds) }
        SettingSlider(label = R.string.speech_interval_min,
            valueText = secondsText(minDraft), value = minDraft, range = 5f..600f,
            changed = { minDraft = it },
            onFinished = { onChanged(options.copy(speechMinSeconds = minDraft)) })
        SettingSlider(label = R.string.speech_interval_max,
            valueText = secondsText(maxDraft), value = maxDraft, range = 5f..600f,
            changed = { maxDraft = it },
            onFinished = { onChanged(options.copy(speechMaxSeconds = maxDraft)) })
        SettingSlider(label = R.string.speech_duration,
            valueText = durationText(durationDraft), value = durationDraft, range = 1f..30f,
            changed = { durationDraft = it },
            onFinished = { onChanged(options.copy(speechSeconds = durationDraft)) })
        Text(stringResource(R.string.speech_interval_hint))
    }
}
