package io.github.dshpet.mobile

import kotlin.random.Random

/**
 * The user's self-talk lines, cleaned with the desktop's rules
 * (`pet/config.py::_clean_self_talk_texts`): strip, drop blanks, truncate to 120
 * characters, drop duplicates, keep order, and fall back to the built-in lines
 * when the user pool is empty.
 */
object PhraseBook {
    const val MAX_LENGTH = 120

    fun clean(lines: Iterable<String>): List<String> {
        val cleaned = ArrayList<String>()
        for (line in lines) {
            val text = line.trim().take(MAX_LENGTH)
            if (text.isNotEmpty() && text !in cleaned) cleaned += text
        }
        return cleaned
    }

    fun fromText(text: String): List<String> = clean(text.split('\n'))

    fun asText(pool: List<String>): String = pool.joinToString("\n")

    fun resolve(user: List<String>, builtin: List<String>): List<String> =
        if (user.isEmpty()) builtin else user

    fun pick(pool: List<String>, random: Random = Random.Default): String? =
        if (pool.isEmpty()) null else pool[random.nextInt(pool.size)]
}
