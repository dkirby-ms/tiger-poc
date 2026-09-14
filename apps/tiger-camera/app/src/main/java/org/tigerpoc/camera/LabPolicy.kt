package org.tigerpoc.camera

data class LabLink(val identity: String, val wifiOnly: Boolean, val privateIpv4: String?)

object LabPolicy {
    fun select(links: List<LabLink>): LabLink? =
        links.singleOrNull()?.takeIf { it.wifiOnly && it.privateIpv4 != null }

    fun endpoint(link: LabLink): String {
        require(link.wifiOnly && link.privateIpv4 != null) { "An eligible lab network is required" }
        return "rtsp://${link.privateIpv4}:8554/"
    }
}
