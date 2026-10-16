package io.github.dshpet.mobile

import android.content.res.AssetManager
import org.json.JSONArray
import org.json.JSONObject

data class SourceBox(val left: Double, val top: Double, val right: Double, val bottom: Double) {
    val width get() = right - left
    val height get() = bottom - top
}

data class ClipSpec(
    val id: String,
    val group: String,
    val fps: Double,
    val frames: Int,
    val stride: Double = 180.0,
    val curve: List<Double> = emptyList(),
    val path: String = "",
    val crop: SourceBox = SourceBox(0.0, 0.0, 640.0, 360.0),
) {
    val duration get() = frames / fps

    fun framePath(index: Int): String =
        "pet/$path/f_${(index.coerceIn(0, frames - 1) + 1).toString().padStart(4, '0')}.webp"
}

data class AssetCatalog(
    val canvasWidth: Int,
    val canvasHeight: Int,
    val body: SourceBox,
    val unionCrop: SourceBox,
    val clips: List<ClipSpec>,
    val phrases: List<String>,
) {
    fun clipsIn(group: String): List<ClipSpec> = clips.filter { it.group == group }

    companion object {
        private fun JSONArray.box() = SourceBox(getDouble(0), getDouble(1), getDouble(2), getDouble(3))
        fun load(assets: AssetManager): AssetCatalog {
            val root = assets.open("pet/manifest.json").bufferedReader(Charsets.UTF_8).use {
                JSONObject(it.readText())
            }
            require(root.getInt("schema_version") == 1) { "Unsupported asset schema" }
            val canvas = root.getJSONArray("canvas")
            val body = root.getJSONArray("body_box").box()
            require(body.width > 0 && body.height > 0)
            val entries = root.getJSONArray("clips")
            val clips = (0 until entries.length()).map { index ->
                val entry = entries.getJSONObject(index)
                val curve = entry.optJSONArray("curve") ?: JSONArray()
                ClipSpec(entry.getString("id"), entry.getString("group"), entry.getDouble("fps"),
                    entry.getInt("frames"), entry.getDouble("stride"),
                    (0 until curve.length()).map { curve.getDouble(it) },
                    entry.getString("path"), entry.getJSONArray("crop_box").box()).also {
                    require(it.frames in 1..10000 && it.fps.isFinite() && it.fps in 1.0..120.0)
                    require(it.path.matches(Regex("clips/[a-z]+_[a-f0-9]{12}")))
                    require(it.crop.width > 0 && it.crop.height > 0)
                }
            }
            require(clips.map { it.id }.distinct().size == clips.size)
            require(clips.map { it.group }.containsAll(listOf("idle", "turn", "move", "click", "drag")))
            val phrases = root.getJSONArray("phrases")
            return AssetCatalog(canvas.getInt(0), canvas.getInt(1), body,
                WindowGeometry.union(clips), clips,
                (0 until phrases.length()).map { phrases.getString(it) })
        }
    }
}
