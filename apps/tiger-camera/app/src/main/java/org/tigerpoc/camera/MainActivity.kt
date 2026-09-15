package org.tigerpoc.camera

import android.Manifest
import android.app.Activity
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.hardware.camera2.CameraAccessException
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.hardware.display.DisplayManager
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
import android.view.WindowManager
import android.widget.Button
import android.widget.Spinner
import android.widget.TextView
import com.pedro.common.ConnectChecker
import com.pedro.common.VideoCodec
import com.pedro.encoder.CodecErrorCallback
import com.pedro.encoder.input.sources.OrientationConfig
import com.pedro.encoder.input.sources.audio.NoAudioSource
import com.pedro.encoder.input.sources.video.Camera2Source
import com.pedro.encoder.input.video.CameraCallbacks
import com.pedro.encoder.input.video.CameraHelper
import com.pedro.encoder.utils.CodecUtil.CodecTypeError
import com.pedro.encoder.utils.gl.AspectRatioMode
import com.pedro.rtspserver.RtspServerStream
import java.net.Inet4Address

class MainActivity : Activity(), SurfaceHolder.Callback {
    private lateinit var preview: AspectPreview
    private lateinit var status: TextView
    private lateinit var lens: Spinner
    private lateinit var start: Button
    private lateinit var stop: Button
    private lateinit var connectivity: ConnectivityManager
    private lateinit var displays: DisplayManager
    private val handler = Handler(Looper.getMainLooper())
    private var stream: RtspServerStream? = null
    private var activeLink: LabLink? = null
    private var session = CameraSession()
    private var startup = CameraStartup()
    private var resumed = false
    private var surfaceReady = false
    private data class RetainedState(val startup: CameraStartup, val session: CameraSession, val message: String)
    private val expire = Runnable { stopSession(R.string.session_expired) }
    private val displayListener = object : DisplayManager.DisplayListener {
        override fun onDisplayAdded(displayId: Int) = Unit
        override fun onDisplayChanged(displayId: Int) = checkDisplay(displayId)
        override fun onDisplayRemoved(displayId: Int) = checkDisplay(displayId)
    }
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
        status.isSaveEnabled = false
        lens = findViewById(R.id.lens)
        start = findViewById(R.id.start)
        stop = findViewById(R.id.stop)
        connectivity = getSystemService(ConnectivityManager::class.java)
        displays = getSystemService(DisplayManager::class.java)
        (lastNonConfigurationInstance as? RetainedState)?.let {
            startup = it.startup
            session = it.session
            status.text = it.message
        }
        lens.setSelection(getPreferences(MODE_PRIVATE).getInt("lens", CameraLens.REAR).coerceIn(0, 1))
        preview.holder.addCallback(this)
        start.setOnClickListener {
            startup.requestStart()
            if (!session.isBusy) status.setText(R.string.starting)
            advanceStartup()
        }
        stop.setOnClickListener { stopSession(R.string.stopped) }
        updateControls()
    }

    override fun onResume() {
        super.onResume()
        resumed = true
        startup.resume()
        preview.display?.let { preview.videoSize = CameraGeometry.forDisplayRotation(it.rotation).encodedSize }
        displays.registerDisplayListener(displayListener, handler)
        val request = NetworkRequest.Builder()
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_NOT_RESTRICTED)
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_TRUSTED)
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN)
            .build()
        connectivity.registerNetworkCallback(request, networkCallback)
        advanceStartup()
    }

    override fun onPause() {
        resumed = false
        startup.pause()
        getPreferences(MODE_PRIVATE).edit().putInt("lens", lens.selectedItemPosition).apply()
        if (session.isBusy) stopSession(R.string.stopped)
        displays.unregisterDisplayListener(displayListener)
        connectivity.unregisterNetworkCallback(networkCallback)
        super.onPause()
    }

    override fun onStop() {
        startup.background(isChangingConfigurations)
        super.onStop()
    }

    override fun onRetainNonConfigurationInstance(): Any =
        RetainedState(startup, session, status.text.toString())

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
            }
        }
    }

    private fun checkDisplay(displayId: Int) {
        if (resumed && session.displayChanged(displayId, displays.getDisplay(displayId)?.rotation)) {
            stopSession(R.string.orientation_changed)
        }
    }

    private fun updateControls() {
        start.isEnabled = !session.isBusy && !startup.permissionInFlight
        stop.isEnabled = stream != null || startup.isPending
        lens.isEnabled = !session.isBusy
    }

    private fun advanceStartup() {
        if (!resumed) return
        val link = currentLink()
        when (startup.next(
            surfaceReady && preview.holder.surface.isValid && preview.display != null,
            checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED,
            link != null,
            session.isBusy,
        )) {
            StartupAction.NONE -> Unit
            StartupAction.REQUEST_PERMISSION -> {
                status.setText(R.string.permission_request)
                requestPermissions(arrayOf(Manifest.permission.CAMERA), 1)
            }
            StartupAction.NETWORK_REQUIRED -> status.setText(R.string.network_needed)
            StartupAction.START -> startSession(requireNotNull(link))
        }
        updateControls()
    }

    private fun startSession(link: LabLink) {
        val display = preview.display
        if (display == null) {
            status.setText(R.string.preview_needed)
            return
        }
        val lease = session.begin(requestedOrientation, display.displayId, display.rotation) ?: return
        val geometry = CameraGeometry.forDisplayRotation(lease.displayRotation)
        status.setText(R.string.preparing)
        val token = lease.token
        var started = false
        try {
            requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LOCKED
            start.isEnabled = false
            lens.isEnabled = false
            preview.videoSize = geometry.encodedSize
            val manager = getSystemService(CameraManager::class.java)
            val facings = manager.cameraIdList.map {
                manager.getCameraCharacteristics(it).get(CameraCharacteristics.LENS_FACING)
            }
            val available = buildSet {
                if (CameraCharacteristics.LENS_FACING_BACK in facings) add(CameraLens.REAR)
                if (CameraCharacteristics.LENS_FACING_FRONT in facings) add(CameraLens.FRONT)
            }
            val selected = CameraLens.select(lens.selectedItemPosition, available)
            if (selected == null) {
                status.setText(R.string.camera_error)
                return
            }
            lens.setSelection(selected)
            getPreferences(MODE_PRIVATE).edit().putInt("lens", selected).apply()
            val camera = Camera2Source(this)
            if (selected == CameraLens.FRONT) camera.switchCamera()
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
            if (!server.prepareVideo(640, 480, 600_000, fps = 5, rotation = geometry.rotation) ||
                !server.prepareAudio(32_000, false, 64_000)) {
                status.setText(R.string.unsupported)
                return
            }
            // Camera2's texture matrix owns sensor/lens mapping. Do not add another
            // sensor rotation; freeze RootEncoder's display-relative GL convention.
            server.getGlInterface().autoHandleOrientation = false
            server.getGlInterface().setOrientationConfig(
                OrientationConfig(cameraOrientation = geometry.cameraOrientation, isPortrait = geometry.portrait),
            )
            server.getGlInterface().setAspectRatioMode(AspectRatioMode.Adjust)
            if (session.displayChanged(display.displayId, displays.getDisplay(display.displayId)?.rotation)) {
                status.setText(R.string.orientation_changed)
                return
            }
            activeLink = link
            server.startPreview(preview, autoHandle = false)
            server.startStream()
            start.isEnabled = false
            stop.isEnabled = true
            lens.isEnabled = false
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            status.text = getString(
                R.string.listening, LabPolicy.endpoint(link),
                geometry.encodedSize.width, geometry.encodedSize.height,
            )
            handler.postDelayed(expire, 10 * 60 * 1000L)
            checkNetwork()
            started = true
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
            if (session.isCurrent(token)) stopSession(message)
        }
    }

    private fun releaseSession(): Boolean {
        try {
            session.finish(
                release = {
                    handler.removeCallbacks(expire)
                    val old = stream
                    stream = null
                    activeLink = null
                    old?.release()
                },
                restore = { requestedOrientation = it },
                finishUi = {
                    window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                },
            )
        } catch (_: RuntimeException) {
            status.setText(R.string.cleanup_error)
        }
        updateControls()
        return !session.cleanupFailed
    }

    private fun stopSession(message: Int) {
        startup.stop()
        if (releaseSession()) status.setText(message)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, results)
        if (requestCode == 1) {
            val granted = results.firstOrNull() == PackageManager.PERMISSION_GRANTED
            startup.permissionResult(granted)
            if (startup.isPending || !granted) {
                status.setText(if (granted) R.string.starting else R.string.permission_needed)
            }
            advanceStartup()
        }
    }

    override fun surfaceCreated(holder: SurfaceHolder) = Unit
    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
        preview.display?.let { checkDisplay(it.displayId) }
        surfaceReady = width > 0 && height > 0
        if (!surfaceReady && session.isBusy) stopSession(R.string.preview_needed)
        else {
            stream?.getGlInterface()?.setPreviewResolution(width, height)
            advanceStartup()
        }
    }
    override fun surfaceDestroyed(holder: SurfaceHolder) {
        surfaceReady = false
        if (session.isBusy) stopSession(R.string.stopped)
    }
}
