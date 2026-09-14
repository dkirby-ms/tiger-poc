package org.tigerpoc.camera

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.hardware.camera2.CameraAccessException
import android.media.MediaCodec
import android.net.ConnectivityManager
import android.net.LinkProperties
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.WindowManager
import android.widget.Button
import android.widget.CheckBox
import android.widget.Spinner
import android.widget.TextView
import com.pedro.common.ConnectChecker
import com.pedro.common.VideoCodec
import com.pedro.encoder.CodecErrorCallback
import com.pedro.encoder.input.sources.audio.NoAudioSource
import com.pedro.encoder.input.sources.video.Camera2Source
import com.pedro.encoder.input.video.CameraCallbacks
import com.pedro.encoder.input.video.CameraHelper
import com.pedro.encoder.utils.CodecUtil.CodecTypeError
import com.pedro.rtspserver.RtspServerStream
import java.net.Inet4Address

class MainActivity : Activity(), SurfaceHolder.Callback {
    private lateinit var preview: SurfaceView
    private lateinit var status: TextView
    private lateinit var consent: CheckBox
    private lateinit var lens: Spinner
    private lateinit var start: Button
    private lateinit var stop: Button
    private lateinit var connectivity: ConnectivityManager
    private val handler = Handler(Looper.getMainLooper())
    private var stream: RtspServerStream? = null
    private var activeLink: LabLink? = null
    private var generation = 0
    private var resumed = false
    private val expire = Runnable { stopSession(R.string.session_expired) }
    private val networkCallback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) = checkNetwork()
        override fun onLost(network: Network) = checkNetwork()
        override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) = checkNetwork()
        override fun onLinkPropertiesChanged(network: Network, properties: LinkProperties) = checkNetwork()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        preview = findViewById(R.id.preview)
        status = findViewById(R.id.status)
        consent = findViewById(R.id.labConsent)
        lens = findViewById(R.id.lens)
        start = findViewById(R.id.start)
        stop = findViewById(R.id.stop)
        connectivity = getSystemService(ConnectivityManager::class.java)
        preview.holder.addCallback(this)
        start.setOnClickListener { startSession() }
        stop.setOnClickListener { stopSession(R.string.stopped) }
        // Never restore consent or streaming state after recreation.
        consent.isSaveEnabled = false
    }

    override fun onResume() {
        super.onResume()
        resumed = true
        val request = NetworkRequest.Builder()
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_NOT_RESTRICTED)
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_TRUSTED)
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN)
            .build()
        connectivity.registerNetworkCallback(request, networkCallback)
    }

    override fun onPause() {
        resumed = false
        stopSession(R.string.stopped)
        consent.isChecked = false
        connectivity.unregisterNetworkCallback(networkCallback)
        super.onPause()
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    private fun currentLink(): LabLink? {
        val links = connectivity.allNetworks.map { network ->
            val caps = connectivity.getNetworkCapabilities(network)
            val addresses = connectivity.getLinkProperties(network)?.linkAddresses.orEmpty()
            val privateAddress = addresses.map { it.address }.filterIsInstance<Inet4Address>()
                .firstOrNull { it.isSiteLocalAddress }?.hostAddress
            LabLink(
                network.toString(),
                caps?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true &&
                    !caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN) &&
                    !caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR),
                privateAddress,
            )
        }
        return LabPolicy.select(links)
    }

    private fun checkNetwork() {
        handler.post {
            if (stream != null && currentLink() != activeLink) {
                stopSession(R.string.network_changed)
                consent.isChecked = false
            }
        }
    }

    private fun startSession() {
        if (stream != null) return
        if (!resumed || !preview.holder.surface.isValid) {
            status.setText(R.string.preview_needed)
            return
        }
        if (!consent.isChecked) {
            status.setText(R.string.lab_needed)
            return
        }
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            status.setText(R.string.permission_needed)
            requestPermissions(arrayOf(Manifest.permission.CAMERA), 1)
            return
        }
        val link = currentLink()
        if (link == null) {
            status.setText(R.string.network_needed)
            return
        }
        status.setText(R.string.preparing)
        val token = ++generation
        var started = false
        try {
            val camera = Camera2Source(this)
            if (lens.selectedItemPosition == 1) camera.switchCamera()
            camera.setCameraCallback(object : CameraCallbacks {
                override fun onCameraChanged(facing: CameraHelper.Facing) = Unit
                override fun onCameraOpened() = Unit
                override fun onCameraError(error: String) = failCurrent(token, R.string.camera_error)
                override fun onCameraDisconnected() = failCurrent(token, R.string.camera_error)
            })
            val server = RtspServerStream(this, 8554, object : ConnectChecker {
                override fun onConnectionStarted(url: String) = Unit
                override fun onConnectionSuccess() = Unit
                override fun onConnectionFailed(reason: String) = failCurrent(token, R.string.server_error)
                override fun onDisconnect() = Unit
                override fun onAuthError() = failCurrent(token, R.string.server_error)
                override fun onAuthSuccess() = Unit
                override fun onNewBitrate(bitrate: Long) = Unit
            }, camera, NoAudioSource())
            stream = server
            server.setEncoderErrorCallback(object : CodecErrorCallback {
                override fun onCodecError(type: CodecTypeError, e: MediaCodec.CodecException) =
                    failCurrent(token, R.string.camera_error)
                override fun onEncodeError(type: CodecTypeError, e: IllegalStateException): Boolean {
                    failCurrent(token, R.string.camera_error)
                    return false
                }
            })
            server.getStreamClient().setOnlyVideo(true)
            server.getStreamClient().setLogs(false)
            server.setVideoCodec(VideoCodec.H264)
            // StreamBase starts both encoders. NoAudioSource supplies no microphone data;
            // preparing its encoder satisfies that lifecycle while SDP stays video-only.
            if (!server.prepareVideo(640, 480, 600_000, fps = 5, rotation = 0) ||
                !server.prepareAudio(32_000, false, 64_000)) {
                status.setText(R.string.unsupported)
                return
            }
            activeLink = link
            server.startPreview(preview)
            server.startStream()
            started = true
            start.isEnabled = false
            stop.isEnabled = true
            lens.isEnabled = false
            consent.isEnabled = false
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            status.text = getString(R.string.listening, LabPolicy.endpoint(link))
            handler.postDelayed(expire, 10 * 60 * 1000L)
            checkNetwork()
        } catch (_: SecurityException) {
            status.setText(R.string.permission_needed)
        } catch (_: IllegalArgumentException) {
            status.setText(R.string.unsupported)
        } catch (_: IllegalStateException) {
            status.setText(R.string.camera_error)
        } catch (_: CameraAccessException) {
            status.setText(R.string.camera_error)
        } finally {
            if (!started) releaseSession()
        }
    }

    private fun failCurrent(token: Int, message: Int) {
        handler.post {
            if (token == generation && stream != null) stopSession(message)
        }
    }

    private fun releaseSession() {
        ++generation
        handler.removeCallbacks(expire)
        val old = stream
        stream = null
        activeLink = null
        try {
            old?.release()
        } finally {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            start.isEnabled = true
            stop.isEnabled = false
            lens.isEnabled = true
            consent.isEnabled = true
        }
    }

    private fun stopSession(message: Int) {
        releaseSession()
        status.setText(message)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, results)
        if (requestCode == 1) {
            status.setText(if (results.firstOrNull() == PackageManager.PERMISSION_GRANTED)
                R.string.permission_granted else R.string.permission_needed)
        }
    }

    override fun surfaceCreated(holder: SurfaceHolder) = Unit
    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
        if (stream != null) stopSession(R.string.stopped)
    }
    override fun surfaceDestroyed(holder: SurfaceHolder) = stopSession(R.string.stopped)
}
