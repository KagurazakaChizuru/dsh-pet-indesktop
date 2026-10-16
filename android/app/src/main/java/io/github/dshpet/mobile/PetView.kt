package io.github.dshpet.mobile

import android.annotation.SuppressLint
import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.view.MotionEvent
import android.view.VelocityTracker
import android.view.View
import android.view.ViewConfiguration
import android.view.animation.LinearInterpolator
import kotlin.math.hypot

/**
 * One pet's transparent surface. The window is the union of every clip's alpha
 * box, so this view keeps a fixed size and each frame is drawn at the offset its
 * crop has inside that union: no window resizing while animating, and the body
 * anchor stays where the engine put it.
 */
@SuppressLint("ViewConstructor") // Constructed by the service, never inflated from XML.
class PetView(
    context: Context,
    val petId: Int,
    private val engine: PetEngine,
    private val listener: Listener,
) : View(context) {
    interface Listener {
        fun onChanged(petId: Int)

        fun onPressed(petId: Int)

        fun onReleased(petId: Int)

        fun onClicked(petId: Int)

        fun onMenu(petId: Int)
    }

    var renderScale = 1.0
    var lastGesture = "none"
        private set
    private var union = SourceBox(0.0, 0.0, 640.0, 360.0)
    private val display = DisplayState<Bitmap>()
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val sourceRect = Rect()
    private val destinationRect = RectF()
    private var squashProgress = INACTIVE
    private var squashAnimator: ValueAnimator? = null
    private var tracker: VelocityTracker? = null
    private var downX = 0f
    private var downY = 0f
    private var originX = 0.0
    private var originY = 0.0
    private var moved = false
    private var menuOpened = false
    private var activePointer = -1
    private var releaseVelocityX = 0f
    private var releaseVelocityY = 0f
    private var lastMoveTime = 0L
    private val longPress = Runnable {
        if (!moved && activePointer >= 0) {
            menuOpened = true
            engine.cancelDrag()
            listener.onMenu(petId)
        }
    }

    private companion object {
        /** 0..1 while the Q 弹 pulse plays; anything below zero means "not squashing". */
        const val INACTIVE = -1.0
    }

    init {
        contentDescription = context.getString(R.string.app_name)
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        isClickable = true
        isLongClickable = true
    }

    /** Fixed geometry for this character and size. */
    fun configure(union: SourceBox, scale: Double) {
        val changed = this.union != union || renderScale != scale
        this.union = union
        renderScale = scale
        if (changed && display.frame != null) invalidate()
    }

    /**
     * Shows a decoded frame. A null frame means the decoder is still behind: the
     * previous frame *and its crop* stay on screen together, so a clip switch can
     * never paint the old image with the new geometry.
     */
    fun present(frame: FrameLoader.DecodedFrame?, crop: SourceBox, mirrored: Boolean) {
        if (display.present(frame?.bitmap, frame?.revision ?: -1L, crop, mirrored)) invalidate()
    }

    /** Starts the desktop's 220 ms Q 弹 pulse: wider and shorter, bottom anchored. */
    fun squash() {
        cancelSquash()
        squashProgress = 0.0
        squashAnimator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = (Squash.DURATION_SECONDS * 1000).toLong()
            interpolator = LinearInterpolator()
            addUpdateListener {
                squashProgress = (it.animatedValue as Float).toDouble()
                invalidate()
            }
            addListener(object : AnimatorListenerAdapter() {
                override fun onAnimationEnd(animation: Animator) {
                    squashProgress = INACTIVE
                    squashAnimator = null
                    invalidate()
                }
            })
            start()
        }
    }

    private fun cancelSquash() {
        squashAnimator?.removeAllListeners()
        squashAnimator?.removeAllUpdateListeners()
        squashAnimator?.cancel()
        squashAnimator = null
        squashProgress = INACTIVE
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val current = display.frame ?: return
        val offset = WindowGeometry.contentOffset(current.crop, union, renderScale)
        val width = (current.crop.width * renderScale).toFloat()
        val height = (current.crop.height * renderScale).toFloat()
        if (squashProgress >= 0.0) {
            val squashed = Squash.geometry(offset.x, offset.y, width, height, squashProgress)
            destinationRect.set(squashed[0], squashed[1], squashed[0] + squashed[2],
                squashed[1] + squashed[3])
        } else {
            destinationRect.set(offset.x, offset.y, offset.x + width, offset.y + height)
        }
        sourceRect.set(current.crop.left.toInt(), current.crop.top.toInt(),
            current.crop.right.toInt(), current.crop.bottom.toInt())
        canvas.save()
        if (current.mirrored) {
            canvas.scale(-1f, 1f, destinationRect.centerX(), destinationRect.centerY())
        }
        canvas.drawBitmap(current.bitmap, sourceRect, destinationRect, paint)
        canvas.restore()
        PetRuntime.draws.incrementAndGet()
    }

    override fun performClick(): Boolean {
        super.performClick()
        engine.click()
        squash()
        listener.onClicked(petId)
        listener.onChanged(petId)
        return true
    }

    override fun performLongClick(): Boolean {
        listener.onMenu(petId)
        return true
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                activePointer = event.getPointerId(0)
                tracker?.recycle()
                tracker = VelocityTracker.obtain()
                trackScreenMovement(event)
                downX = event.rawX; downY = event.rawY
                originX = engine.x; originY = engine.y
                moved = false; menuOpened = false
                releaseVelocityX = 0f; releaseVelocityY = 0f; lastMoveTime = event.eventTime
                engine.beginDrag()
                lastGesture = "down"
                listener.onPressed(petId)
                postDelayed(longPress, ViewConfiguration.getLongPressTimeout().toLong())
                listener.onChanged(petId)
            }
            MotionEvent.ACTION_MOVE -> {
                if (activePointer < 0 || menuOpened) return true
                trackScreenMovement(event)
                tracker?.computeCurrentVelocity(1000)
                releaseVelocityX = tracker?.getXVelocity(activePointer) ?: 0f
                releaseVelocityY = tracker?.getYVelocity(activePointer) ?: 0f
                lastMoveTime = event.eventTime
                val dx = event.rawX - downX
                val dy = event.rawY - downY
                if (hypot(dx, dy) > ViewConfiguration.get(context).scaledTouchSlop) {
                    moved = true
                    removeCallbacks(longPress)
                }
                if (moved) {
                    engine.dragTo(originX + dx / renderScale, originY + dy / renderScale)
                    listener.onChanged(petId)
                }
            }
            MotionEvent.ACTION_UP -> {
                if (activePointer < 0) return true
                removeCallbacks(longPress)
                if (!menuOpened) {
                    if (moved) {
                        // ACTION_UP can clear VelocityTracker; use the last MOVE,
                        // but discard stale velocity after the finger has rested.
                        val age = event.eventTime - lastMoveTime
                        val fresh = age in 0L..150L
                        val vx = if (fresh) releaseVelocityX / renderScale else 0.0
                        val vy = if (fresh) releaseVelocityY / renderScale else 0.0
                        lastGesture = "release vx=$vx vy=$vy age_ms=$age"
                        engine.release(vx, vy)
                        listener.onReleased(petId)
                    } else performClick()
                }
                finishGesture()
                listener.onChanged(petId)
            }
            MotionEvent.ACTION_CANCEL, MotionEvent.ACTION_POINTER_DOWN -> {
                lastGesture = "cancel action=${event.actionMasked}"
                engine.cancelDrag()
                finishGesture()
                listener.onReleased(petId)
                listener.onChanged(petId)
            }
        }
        return true
    }

    private fun trackScreenMovement(event: MotionEvent) {
        // The overlay moves with the finger, so local coordinates hide its speed.
        val screenEvent = MotionEvent.obtain(event)
        screenEvent.offsetLocation(event.rawX - event.x, event.rawY - event.y)
        tracker?.addMovement(screenEvent)
        screenEvent.recycle()
    }

    private fun finishGesture() {
        removeCallbacks(longPress)
        tracker?.recycle(); tracker = null
        activePointer = -1
    }

    override fun onDetachedFromWindow() {
        cancelSquash()
        finishGesture()
        display.clear()
        super.onDetachedFromWindow()
    }
}
