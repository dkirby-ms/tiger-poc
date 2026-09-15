package org.tigerpoc.camera

import org.junit.Assert.*
import org.junit.Test

class CameraStartupTest {
    private fun CameraStartup.ready(
        surface: Boolean = true,
        permission: Boolean = true,
        network: Boolean = true,
        busy: Boolean = false,
    ) = next(surface, permission, network, busy)

    @Test fun launchWaitsForForegroundAndSurfaceThenStartsOnce() {
        val startup = CameraStartup()
        assertEquals(StartupAction.NONE, startup.ready())
        startup.resume()
        assertEquals(StartupAction.NONE, startup.ready(surface = false))
        assertEquals(StartupAction.START, startup.ready())
        repeat(5) { assertEquals(StartupAction.NONE, startup.ready()) }
    }

    @Test fun surfaceBeforeResumeAlsoStartsExactlyOnce() {
        val startup = CameraStartup()
        assertEquals(StartupAction.NONE, startup.ready())
        startup.resume()
        assertEquals(StartupAction.START, startup.ready())
        assertEquals(StartupAction.NONE, startup.ready())
    }

    @Test fun permissionRequestWaitsForVisibleSurfaceAndDoesNotRepeat() {
        val startup = CameraStartup()
        startup.resume()
        assertEquals(StartupAction.NONE, startup.ready(surface = false, permission = false))
        assertEquals(StartupAction.REQUEST_PERMISSION, startup.ready(permission = false))
        repeat(5) { assertEquals(StartupAction.NONE, startup.ready(permission = false)) }
        startup.permissionResult(true)
        assertEquals(StartupAction.START, startup.ready())
        assertEquals(StartupAction.NONE, startup.ready())
    }

    @Test fun permissionDialogPauseAndStopDoNotCountAsReopening() {
        val startup = CameraStartup()
        startup.resume()
        startup.ready(permission = false)
        startup.pause()
        startup.background(changingConfiguration = false)
        startup.permissionResult(true)
        assertEquals(StartupAction.NONE, startup.ready())
        startup.resume()
        assertEquals(StartupAction.START, startup.ready())
        assertEquals(StartupAction.NONE, startup.ready())
    }

    @Test fun denialDoesNotLoopAfterPermissionDialogCloses() {
        val startup = CameraStartup()
        startup.resume()
        startup.ready(permission = false)
        startup.pause()
        startup.background(changingConfiguration = false)
        startup.permissionResult(false)
        startup.resume()
        repeat(5) { assertEquals(StartupAction.NONE, startup.ready(permission = false)) }
        startup.requestStart()
        assertEquals(StartupAction.REQUEST_PERMISSION, startup.ready(permission = false))
    }

    @Test fun manualStopWhileWaitingForSurfaceSuppressesStartup() {
        val startup = CameraStartup()
        startup.resume()
        startup.ready(surface = false)
        startup.stop()
        assertEquals(StartupAction.NONE, startup.ready())
        startup.requestStart()
        assertEquals(StartupAction.START, startup.ready())
    }

    @Test fun stopDuringPermissionRequestCannotBeUndoneByGrant() {
        val startup = CameraStartup()
        startup.resume()
        startup.ready(permission = false)
        startup.stop()
        startup.pause()
        startup.background(changingConfiguration = false)
        startup.permissionResult(true)
        startup.resume()
        assertEquals(StartupAction.NONE, startup.ready())
        startup.requestStart()
        assertEquals(StartupAction.START, startup.ready())
    }

    @Test fun unsolicitedPermissionResultCannotAuthorizeAnotherAttempt() {
        val startup = CameraStartup()
        startup.resume()
        startup.ready()
        startup.stop()
        startup.permissionResult(true)
        assertEquals(StartupAction.NONE, startup.ready())
    }

    @Test fun manualStopRemainsStoppedThroughSurfaceAndResumeCallbacks() {
        val startup = CameraStartup()
        startup.resume()
        startup.ready()
        startup.stop()
        startup.pause()
        startup.resume()
        repeat(5) { assertEquals(StartupAction.NONE, startup.ready()) }
        startup.requestStart()
        assertEquals(StartupAction.START, startup.ready())
    }

    @Test fun actualBackgroundAndReopenAllowOneNewAttemptAfterStop() {
        val startup = CameraStartup()
        startup.resume()
        startup.ready()
        startup.stop()
        startup.pause()
        startup.background(changingConfiguration = false)
        assertEquals(StartupAction.NONE, startup.ready())
        startup.resume()
        assertEquals(StartupAction.START, startup.ready())
        assertEquals(StartupAction.NONE, startup.ready())
    }

    @Test fun configurationRecreationPreservesConsumedAttempt() {
        val startup = CameraStartup()
        startup.resume()
        startup.ready()
        startup.stop()
        startup.pause()
        startup.background(changingConfiguration = true)
        // The Activity retains this policy object, not a running camera or surface.
        startup.resume()
        assertEquals(StartupAction.NONE, startup.ready())
        startup.requestStart()
        assertEquals(StartupAction.START, startup.ready())
    }

    @Test fun configurationBeforeSurfaceCanCompleteOriginalPendingAttempt() {
        val startup = CameraStartup()
        startup.resume()
        startup.ready(surface = false)
        startup.pause()
        startup.background(changingConfiguration = true)
        startup.resume()
        assertEquals(StartupAction.START, startup.ready())
        assertEquals(StartupAction.NONE, startup.ready())
    }

    @Test fun networkFailureConsumesAttemptAndNetworkRecoveryDoesNotRetry() {
        val startup = CameraStartup()
        startup.resume()
        assertEquals(StartupAction.NETWORK_REQUIRED, startup.ready(network = false))
        repeat(5) {
            assertEquals(StartupAction.NONE, startup.ready(network = false))
            assertEquals(StartupAction.NONE, startup.ready())
        }
        startup.requestStart()
        assertEquals(StartupAction.START, startup.ready())
    }

    @Test fun activeOrFailedCleanupSessionBlocksAllNewPreparation() {
        val startup = CameraStartup()
        startup.resume()
        assertEquals(StartupAction.NONE, startup.ready(busy = true))
        assertEquals(StartupAction.NONE, startup.ready(permission = false, busy = true))
        assertEquals(StartupAction.START, startup.ready())
    }

    @Test fun timeoutAndAsynchronousFailuresStayStoppedUntilManualStart() {
        // Timeout, camera, network, orientation and server errors share stopSession.
        repeat(5) {
            val startup = CameraStartup()
            startup.resume()
            assertEquals(StartupAction.START, startup.ready())
            startup.stop()
            repeat(5) { assertEquals(StartupAction.NONE, startup.ready()) }
            startup.requestStart()
            assertEquals(StartupAction.START, startup.ready())
        }
    }

    @Test fun failedPreparationRestoresGeometryLeaseWithoutAutomaticRetry() {
        val startup = CameraStartup()
        val session = CameraSession()
        startup.resume()
        assertEquals(StartupAction.START, startup.ready())
        val lease = session.begin(-1, 0, 0)!!
        assertEquals(VideoSize(480, 640), CameraGeometry.forDisplayRotation(lease.displayRotation).encodedSize)
        val effects = mutableListOf<String>()
        session.finish({ effects += "release" }, { effects += "restore:$it" }, { effects += "ui" })
        assertEquals(listOf("release", "restore:-1", "ui"), effects)
        assertFalse(session.isCurrent(lease.token))
        repeat(5) { assertEquals(StartupAction.NONE, startup.ready(busy = session.isBusy)) }
        startup.requestStart()
        assertEquals(StartupAction.START, startup.ready(busy = session.isBusy))
        val next = session.begin(-1, 0, 1)!!
        assertEquals(VideoSize(640, 480), CameraGeometry.forDisplayRotation(next.displayRotation).encodedSize)
    }

    @Test fun backgroundCleanupRestoresOrientationAndReopenGetsFreshLease() {
        val startup = CameraStartup()
        val session = CameraSession()
        startup.resume()
        startup.ready()
        val first = session.begin(3, 0, 2)!!
        startup.pause()
        startup.stop()
        var restored = 0
        session.finish({}, { restored = it }, {})
        startup.background(changingConfiguration = false)
        assertEquals(3, restored)
        assertFalse(session.isCurrent(first.token))
        assertEquals(StartupAction.NONE, startup.ready())
        startup.resume()
        assertEquals(StartupAction.START, startup.ready())
        val second = session.begin(3, 0, 3)!!
        assertNotEquals(first.token, second.token)
        assertFalse(session.isCurrent(first.token))
    }

    @Test fun cleanupFailureStillBlocksOnReopenAndConfigurationRecreation() {
        val startup = CameraStartup()
        val session = CameraSession()
        startup.resume()
        startup.ready()
        session.begin(-1, 0, 0)
        assertThrows(IllegalStateException::class.java) {
            session.finish({ throw IllegalStateException("release failed") }, {}, {})
        }
        startup.pause()
        startup.stop()
        startup.background(changingConfiguration = false)
        startup.resume()
        assertEquals(StartupAction.NONE, startup.ready(busy = session.isBusy))
        startup.pause()
        startup.background(changingConfiguration = true)
        startup.resume()
        assertEquals(StartupAction.NONE, startup.ready(busy = session.isBusy))
    }
}
