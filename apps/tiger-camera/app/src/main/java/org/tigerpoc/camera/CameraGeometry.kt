package org.tigerpoc.camera

data class VideoSize(val width: Int, val height: Int)

data class CameraGeometry(val rotation: Int) {
    init {
        require(rotation in setOf(0, 90, 180, 270))
    }

    val portrait: Boolean = rotation == 90 || rotation == 270
    val encodedSize: VideoSize = if (portrait) VideoSize(480, 640) else VideoSize(640, 480)
    val cameraOrientation: Int = (rotation + 270) % 360

    companion object {
        // RootEncoder 2.8.1 CameraHelper convention, not physical sensor rotation.
        fun forDisplayRotation(rotation: Int): CameraGeometry {
            require(rotation in 0..3)
            return CameraGeometry((450 - rotation * 90) % 360)
        }

        fun fit(size: VideoSize, maxWidth: Int, maxHeight: Int): VideoSize {
            require(size.width > 0 && size.height > 0 && maxWidth >= 0 && maxHeight >= 0)
            if (maxWidth == 0 || maxHeight == 0) return VideoSize(0, 0)
            return if (maxWidth.toLong() * size.height <= maxHeight.toLong() * size.width) {
                VideoSize(maxWidth, (maxWidth.toLong() * size.height / size.width).toInt())
            } else {
                VideoSize((maxHeight.toLong() * size.width / size.height).toInt(), maxHeight)
            }
        }
    }
}
