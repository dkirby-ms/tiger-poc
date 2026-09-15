package org.tigerpoc.camera

object CameraLens {
    const val REAR = 0
    const val FRONT = 1

    fun select(preferred: Int, available: Set<Int>): Int? =
        listOf(preferred, REAR, FRONT).firstOrNull { it in available && it in REAR..FRONT }
}
