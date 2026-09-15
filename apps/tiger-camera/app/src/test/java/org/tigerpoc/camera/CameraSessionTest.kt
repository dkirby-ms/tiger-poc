package org.tigerpoc.camera

import org.junit.Assert.*
import org.junit.Test

class CameraSessionTest {
    @Test fun startsOnlyThroughExplicitBeginAndRejectsDuplicateStart() {
        val session = CameraSession()
        assertFalse(session.isBusy)
        assertNotNull(session.begin(-1, 0, 0))
        assertNull(session.begin(3, 0, 1))
    }

    @Test fun cleanupInvalidatesBeforeReleaseAndRestoresBeforeUiExactlyOnce() {
        val session = CameraSession()
        val lease = session.begin(3, 0, 0)!!
        val effects = mutableListOf<String>()
        session.finish(
            {
                assertFalse(session.isCurrent(lease.token))
                assertTrue(session.isBusy)
                effects += "release"
            },
            { effects += "restore:$it" },
            { effects += "ui" },
        )
        session.finish({ fail("duplicate release") }, { fail("duplicate restore") }, { fail("duplicate UI") })
        assertEquals(listOf("release", "restore:3", "ui"), effects)
        assertFalse(session.isBusy)
    }

    @Test fun preparationFailureBeforeResourceAllocationStillRestores() {
        val session = CameraSession()
        session.begin(-1, 0, 0)
        val effects = mutableListOf<String>()
        session.finish({}, { effects += "restore:$it" }, { effects += "ui" })
        assertEquals(listOf("restore:-1", "ui"), effects)
        assertFalse(session.isBusy)
    }

    @Test fun throwingReleaseRestoresAndFinishesUiButBlocksRestart() {
        val session = CameraSession()
        session.begin(4, 0, 0)
        val effects = mutableListOf<String>()
        assertThrows(IllegalStateException::class.java) {
            session.finish(
                { effects += "release"; throw IllegalStateException("failed release") },
                { effects += "restore:$it" },
                { assertTrue(session.cleanupFailed); effects += "ui" },
            )
        }
        assertEquals(listOf("release", "restore:4", "ui"), effects)
        assertNull(session.begin(-1, 0, 0))
    }

    @Test fun throwingRestoreStillFinishesUiAndBlocksRestart() {
        val session = CameraSession()
        session.begin(-1, 0, 0)
        var uiFinished = false
        assertThrows(IllegalStateException::class.java) {
            session.finish({}, { throw IllegalStateException("restore failed") }, { uiFinished = true })
        }
        assertTrue(uiFinished)
        assertTrue(session.cleanupFailed)
        assertNull(session.begin(-1, 0, 0))
    }

    @Test fun reentrantCleanupAndStartCannotAcquireOrientation() {
        val session = CameraSession()
        session.begin(7, 0, 0)
        var restoreCount = 0
        val reenter = {
            session.finish({ fail("reentered release") }, { fail("reentered restore") }, {})
            assertNull(session.begin(-1, 0, 0))
        }
        session.finish(reenter, {
            assertEquals(7, it)
            restoreCount++
            reenter()
        }, { reenter() })
        assertEquals(1, restoreCount)
        assertFalse(session.isBusy)
    }

    @Test fun staleCallbacksCannotStopNewSession() {
        val session = CameraSession()
        val first = session.begin(-1, 0, 0)!!
        session.finish({}, {}, {})
        assertFalse(session.isCurrent(first.token))
        val second = session.begin(-1, 0, 0)!!
        assertFalse(session.isCurrent(first.token))
        assertTrue(session.isCurrent(second.token))
    }

    @Test fun sameDimensionsHalfTurnAndDisplayRemovalStopButUnrelatedDisplayDoesNot() {
        val session = CameraSession()
        session.begin(-1, 4, 0)
        assertFalse(session.displayChanged(4, 0))
        assertTrue(session.displayChanged(4, 2))
        assertTrue(session.displayChanged(4, null))
        assertFalse(session.displayChanged(9, 2))
        session.finish({}, {}, {})
        assertFalse(session.displayChanged(4, 2))
    }

    @Test fun stopEventsCannotCreateSessionOrRepeatOrientationEffects() {
        val session = CameraSession()
        repeat(3) {
            session.finish({ fail("not running") }, { fail("no saved orientation") }, {})
            assertFalse(session.displayChanged(0, 2))
        }
        assertFalse(session.isBusy)
    }
}
