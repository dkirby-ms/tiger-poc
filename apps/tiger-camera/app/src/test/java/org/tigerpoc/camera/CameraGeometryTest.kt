package org.tigerpoc.camera

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraGeometryTest {
    @Test fun displayRotationMatchesRootEncoderConvention() {
        val expected = listOf(90, 0, 270, 180)
        expected.forEachIndexed { display, rotation ->
            assertEquals(rotation, CameraGeometry.forDisplayRotation(display).rotation)
        }
    }

    @Test fun quarterTurnsSwapEncoderDimensionsOnlyOnce() {
        assertEquals(VideoSize(480, 640), CameraGeometry(90).encodedSize)
        assertEquals(VideoSize(480, 640), CameraGeometry(270).encodedSize)
        assertEquals(VideoSize(640, 480), CameraGeometry(0).encodedSize)
        assertEquals(VideoSize(640, 480), CameraGeometry(180).encodedSize)
    }

    @Test fun cameraTextureRotationUsesLibraryOffset() {
        assertEquals(listOf(270, 0, 90, 180), listOf(0, 90, 180, 270).map {
            CameraGeometry(it).cameraOrientation
        })
    }

    @Test fun previewFitsWideAndTallBoundsWithoutStretching() {
        assertEquals(VideoSize(150, 200), CameraGeometry.fit(VideoSize(480, 640), 1000, 200))
        assertEquals(VideoSize(200, 150), CameraGeometry.fit(VideoSize(640, 480), 200, 1000))
        assertEquals(VideoSize(480, 640), CameraGeometry.fit(VideoSize(480, 640), 480, 640))
    }

    @Test fun fitRoundingStaysWithinOnePixelAndBounds() {
        for (rotation in 0..3) {
            val source = CameraGeometry.forDisplayRotation(rotation).encodedSize
            for (width in listOf(101, 377, 1920)) {
                for (height in listOf(99, 200, 1080)) {
                    val fit = CameraGeometry.fit(source, width, height)
                    assertTrue(fit.width <= width && fit.height <= height)
                    assertTrue(kotlin.math.abs(fit.width.toLong() * source.height -
                        fit.height.toLong() * source.width) < maxOf(source.width, source.height))
                }
            }
        }
    }

    @Test fun unavailableBoundsDoNotCreateInvalidSurfaceSizes() {
        assertEquals(VideoSize(0, 0), CameraGeometry.fit(VideoSize(640, 480), 0, 200))
        assertEquals(VideoSize(0, 0), CameraGeometry.fit(VideoSize(640, 480), 200, 0))
    }

    @Test fun fitAvoidsIntermediateIntegerOverflow() {
        assertEquals(VideoSize(Int.MAX_VALUE, 1_610_612_735),
            CameraGeometry.fit(VideoSize(640, 480), Int.MAX_VALUE, Int.MAX_VALUE))
    }

    @Test fun invalidGeometryIsRejected() {
        assertThrows { CameraGeometry(45) }
        assertThrows { CameraGeometry.forDisplayRotation(-1) }
        assertThrows { CameraGeometry.forDisplayRotation(4) }
        assertThrows { CameraGeometry.fit(VideoSize(0, 480), 100, 100) }
        assertThrows { CameraGeometry.fit(VideoSize(640, 480), -1, 100) }
    }

    private fun assertThrows(action: () -> Unit) {
        org.junit.Assert.assertThrows(IllegalArgumentException::class.java, action)
    }
}
