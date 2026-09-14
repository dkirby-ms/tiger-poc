package org.tigerpoc.camera

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LabPolicyTest {
    private val wifi = LabLink("lab", true, "192.168.50.2")

    @Test fun acceptsOnePrivateWifi() {
        assertEquals(wifi, LabPolicy.select(listOf(wifi)))
        assertEquals("rtsp://192.168.50.2:8554/", LabPolicy.endpoint(wifi))
    }
    @Test fun rejectsMissingNetwork() = assertNull(LabPolicy.select(emptyList()))
    @Test fun rejectsPublicOrMissingIpv4() =
        assertNull(LabPolicy.select(listOf(wifi.copy(privateIpv4 = null))))
    @Test fun rejectsCellularOrVpn() =
        assertNull(LabPolicy.select(listOf(wifi.copy(wifiOnly = false))))
    @Test fun rejectsConcurrentNetwork() =
        assertNull(LabPolicy.select(listOf(wifi, LabLink("cell", false, "10.0.0.2"))))
    @Test fun detectsAddressChange() {
        org.junit.Assert.assertNotEquals(wifi, wifi.copy(privateIpv4 = "192.168.50.3"))
    }
}
