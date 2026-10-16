package io.github.dshpet.mobile

import org.junit.Assert.assertEquals
import org.junit.Test

class PhraseBookTest {
    private val builtin = listOf("好女孩……", "好模型……")

    @Test
    fun cleaningMatchesTheDesktopRules() {
        val cleaned = PhraseBook.clean(listOf("  今天也要认真工作呀。 ", "", "   ", "欧鲸鲸……", "欧鲸鲸……"))
        assertEquals(listOf("今天也要认真工作呀。", "欧鲸鲸……"), cleaned)
    }

    @Test
    fun longLinesAreTruncatedNotDropped() {
        val long = "深".repeat(200)
        val cleaned = PhraseBook.clean(listOf(long))
        assertEquals(1, cleaned.size)
        assertEquals(PhraseBook.MAX_LENGTH, cleaned.first().length)
    }

    @Test
    fun textRoundTripsThroughTheEditorForm() {
        val pool = listOf("再陪你一会儿。", "好女孩……")
        assertEquals(pool, PhraseBook.fromText(PhraseBook.asText(pool)))
    }

    @Test
    fun emptyUserPoolFallsBackToTheBuiltInLines() {
        assertEquals(builtin, PhraseBook.resolve(emptyList(), builtin))
        assertEquals(listOf("mine"), PhraseBook.resolve(listOf("mine"), builtin))
    }

    @Test
    fun pickingFromAnEmptyPoolYieldsNothing() {
        assertEquals(null, PhraseBook.pick(emptyList()))
        assertEquals("only", PhraseBook.pick(listOf("only")))
    }
}
