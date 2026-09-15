package org.tigerpoc.camera

data class SessionLease(
    val token: Int,
    val originalOrientation: Int,
    val displayId: Int,
    val displayRotation: Int,
)

/** Main-thread ownership of one explicitly authorized foreground camera session. */
class CameraSession {
    private var generation = 0
    private var lease: SessionLease? = null
    private var releasing = false
    var cleanupFailed = false
        private set

    val isBusy: Boolean get() = lease != null || releasing || cleanupFailed

    fun begin(originalOrientation: Int, displayId: Int, displayRotation: Int): SessionLease? {
        if (isBusy) return null
        return SessionLease(++generation, originalOrientation, displayId, displayRotation).also { lease = it }
    }

    fun isCurrent(token: Int): Boolean = lease?.token == token

    fun displayChanged(displayId: Int, rotation: Int?): Boolean =
        lease?.let { it.displayId == displayId && it.displayRotation != rotation } == true

    fun finish(release: () -> Unit, restore: (Int) -> Unit, finishUi: () -> Unit) {
        val previous = lease ?: return
        lease = null
        releasing = true
        try {
            try {
                release()
            } catch (error: RuntimeException) {
                cleanupFailed = true
                throw error
            } finally {
                try {
                    restore(previous.originalOrientation)
                } catch (error: RuntimeException) {
                    cleanupFailed = true
                    throw error
                } finally {
                    finishUi()
                }
            }
        } finally {
            releasing = false
        }
    }
}
