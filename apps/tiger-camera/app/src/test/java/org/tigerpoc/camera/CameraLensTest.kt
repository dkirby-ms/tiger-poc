package org.tigerpoc.camera

import org.junit.Assert.*
import org.junit.Test

class CameraLensTest {
    @Test fun defaultsToRearAndPreservesAvailableSavedLens() {
        assertEquals(CameraLens.REAR, CameraLens.select(-1, setOf(CameraLens.REAR, CameraLens.FRONT)))
        assertEquals(CameraLens.FRONT, CameraLens.select(CameraLens.FRONT, setOf(CameraLens.REAR, CameraLens.FRONT)))
    }

    @Test fun unavailablePreferenceFallsBackToAnExistingLens() {
        assertEquals(CameraLens.REAR, CameraLens.select(CameraLens.FRONT, setOf(CameraLens.REAR)))
        assertEquals(CameraLens.FRONT, CameraLens.select(CameraLens.REAR, setOf(CameraLens.FRONT)))
    }

    @Test fun missingSupportedLensesFailRatherThanInventingACamera() {
        assertNull(CameraLens.select(CameraLens.REAR, emptySet()))
        assertNull(CameraLens.select(2, setOf(2)))
    }
}
