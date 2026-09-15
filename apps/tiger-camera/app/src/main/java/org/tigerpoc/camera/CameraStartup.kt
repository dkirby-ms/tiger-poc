package org.tigerpoc.camera

enum class StartupAction { NONE, REQUEST_PERMISSION, NETWORK_REQUIRED, START }

/** One attempt per foreground opening, retained across Activity configuration changes. */
class CameraStartup {
    private var foreground = false
    private var pending = true
    private var reopen = false
    var permissionInFlight = false
        private set

    val isPending: Boolean get() = pending

    fun resume() {
        foreground = true
        if (reopen) {
            pending = true
            reopen = false
        }
    }

    fun pause() {
        foreground = false
    }

    fun background(changingConfiguration: Boolean) {
        // The permission dialog is not a new user opening, even if it stops the Activity.
        if (!changingConfiguration && !permissionInFlight) reopen = true
    }

    fun requestStart() {
        if (foreground && !permissionInFlight) pending = true
    }

    fun stop() {
        pending = false
    }

    fun permissionResult(granted: Boolean) {
        if (!permissionInFlight) return
        permissionInFlight = false
        if (!granted) pending = false
    }

    fun next(surfaceReady: Boolean, permissionGranted: Boolean, networkReady: Boolean, busy: Boolean): StartupAction {
        if (!foreground || !surfaceReady || busy || !pending || permissionInFlight) return StartupAction.NONE
        if (!permissionGranted) {
            permissionInFlight = true
            return StartupAction.REQUEST_PERMISSION
        }
        // Consume before checking/preparing resources, so failures never trigger retry loops.
        pending = false
        return if (networkReady) StartupAction.START else StartupAction.NETWORK_REQUIRED
    }
}
