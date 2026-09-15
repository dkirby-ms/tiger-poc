package org.tigerpoc.camera

import android.content.Context
import android.util.AttributeSet
import android.view.SurfaceView

class AspectPreview(context: Context, attrs: AttributeSet) : SurfaceView(context, attrs) {
    var videoSize = VideoSize(640, 480)
        set(value) {
            field = value
            requestLayout()
        }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val size = CameraGeometry.fit(
            videoSize, MeasureSpec.getSize(widthMeasureSpec), MeasureSpec.getSize(heightMeasureSpec),
        )
        setMeasuredDimension(size.width, size.height)
    }
}
