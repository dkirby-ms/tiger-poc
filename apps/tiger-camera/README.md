---
title: Tiger Camera
description: Foreground-only Android H.264 RTSP source for the Tiger vision container
---

## Scope

This separate Kotlin app supplies a camera stream to the existing
[vision container](../vision/README.md). It does not contain inference,
Rover controls, facial recognition, microphone capture, recording, or cloud calls.
The application ID is `org.tigerpoc.camera`; do not replace an existing app with
that ID without confirming its owner.

The first transport milestone uses a manually configured RTSP URL. ONVIF discovery
is not implemented yet. A working RTSP connection does not establish ONVIF support.

## Build with command-line tools

Android Studio, an emulator and the NDK are not required. Set `JAVA_HOME` to a
JDK 17 installation and `ANDROID_HOME` to an Android SDK installation. Install
Android SDK Platform 37.0 and Build-Tools 37.0.0 with Google's command-line tools.
These compile-time versions match the pinned RTSP dependency; the app supports
Android 6/API 23 or newer and currently targets API 35.

From this directory:

```powershell
.\gradlew.bat --no-daemon :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

On Linux/macOS use `sh ./gradlew` with the same tasks. The official Gradle wrapper
downloads the pinned distribution and checks its SHA-256. Dependency locks and
verification metadata record the resolved build inputs. Changes to them require
review; do not disable verification to bypass a mismatch.

Output: `app/build/outputs/apk/debug/app-debug.apk`. It is a development-signed
APK, not a Play Store or production release.

## Install and operate

Use an authorized, USB-debugging-enabled device. Installation does not start
streaming:

```powershell
adb install .\app\build\outputs\apk\debug\app-debug.apk
```

Position the phone in portrait or landscape, then open **Tiger Camera**.
It automatically makes one streaming attempt when the app is in the foreground
and its preview surface is ready. If Android requests camera permission, granting
it continues that same attempt automatically; denial leaves the camera off.
There is no acknowledgement checkbox or persistent warning banner. Connection
status, Stop and actionable errors remain visible; network limitations are
documented below.
The app uses the saved lens when available, otherwise the rear camera, then the
front camera if there is no rear camera. Tap **Stop streaming** before selecting
a different lens, then tap **Start streaming**. The selected lens is saved locally.

Use an isolated Wi-Fi network with a private IPv4 address. Disable cellular,
VPN and other network connections (airplane mode with Wi-Fi re-enabled is one
option). The app rejects concurrent networks, stops on a network change, and
does not retry automatically within that foreground opening. Correct a rejected
network setup and tap **Start streaming**. This is a guard, not network isolation: the app
cannot prove that the Wi-Fi network is private or that other devices are trusted.

The RTSP library listens on all phone interfaces. Video is **unencrypted and
unauthenticated** in this lab-only version. Do not use corporate/public networks,
sensitive scenes, or production deployments. Only authorize scenes whose
participants have agreed to capture.

The app displays `rtsp://<phone-private-ip>:8554/`. It supplies H.264,
640x480 in landscape or 480x640 in portrait, 5 fps, about 600 kbit/s, without an
audio track. The status shows the session's encoded dimensions. If the camera cannot
prepare that profile, it stops visibly rather than silently switching profiles.
It stops on **Stop**, app backgrounding, preview destruction, camera failure,
network change, or a ten-minute session timeout. Stop, timeout and failures suppress
automatic retries in the current foreground opening. The timeout status explains
the ten-minute limit; tap **Start streaming** for another session.

Leaving the app fully into the background and reopening it allows one new automatic
attempt, including after Stop or timeout. Merely dismissing a permission dialog,
temporarily pausing the Activity, rotating, or recreating its display does not
authorize another attempt. A configuration change before the first attempt can
finish that pending attempt when the replacement preview is ready. Installation
alone, phone boot and background execution never start capture.

## Orientation and preview

Orientation is fixed for each session, including automatic startup. Tap **Stop**, rotate the phone,
then tap **Start** to change it. Cleanup restores the Activity's previous
orientation request, including failed preparation. If Android ignores the lock
and changes the display rotation, the app stops instead of reconfiguring the
encoder or automatically restarting. Activity recreation also stops capture and
retains startup suppression and shutdown-failure state across configuration changes.

The preview fits inside a bounded black panel without stretching or cropping.
Empty space is intentional. Harmless preview size changes update only the
renderer's preview dimensions; surface destruction still stops the session.
If shutdown itself fails, Start stays disabled and the app does not claim the
camera is off. Close it and verify the device's camera indicator before reopening.

The 640x480 camera-source request remains unchanged. RootEncoder 2.8.1 uses
display-relative preparation rotations of 90, 0, 270 and 180 degrees for Android
display rotations 0, 90, 180 and 270 degrees. It swaps actual encoder dimensions
at 90/270; this is not merely RTSP orientation metadata. The app freezes the
corresponding GL orientation and uses aspect-fit rendering. Camera2's texture
matrix and RootEncoder retain responsibility for sensor/lens mapping; the app
does not add a second physical sensor rotation or manual front-camera mirror.
See upstream [StreamBase](https://github.com/pedroSG94/RootEncoder/blob/2.8.1/library/src/main/java/com/pedro/library/base/StreamBase.kt)
and [CameraHelper](https://github.com/pedroSG94/RootEncoder/blob/2.8.1/encoder/src/main/java/com/pedro/encoder/input/video/CameraHelper.java).

This startup increment has local startup/lens/geometry/session unit tests, an APK
build and Android lint validation. It has **not** been installed or qualified on a device.
Portrait person detection, unusual sensor mounts and both lenses remain unproven.
The previous successful landscape detections do not isolate rotation from framing.

For the next authorized device qualification:

1. Test rear/front lenses in portrait, landscape and their reverse orientations.
   Check upright preview and decoded video, natural proportions, expected encoded
   dimensions and intentional front-camera mirroring behavior.
2. Hold framing and lighting comparable and rerun person detection at the same
   model/confidence settings. Record actual results, not preview-based inference.
3. Confirm launch and permission grant each produce one automatic attempt, while
   denial, Stop, network/preparation failures, rotation/recreation and timeout do
   not retry. Check that the timeout reason remains visible and Start retries.
4. Exercise Home/background and reopen. Confirm capture/listening stop while
   backgrounded and one fresh attempt starts only on return. Check permission-dialog
   pauses, preview readiness, both lens defaults and saved lens selection.
5. Check preview resizes, repeated Start/Stop and unsupported-camera preparation.
   Confirm controls remain reachable and SDP still has no audio track.

## Connect the vision container

The container pulls the stream. No HTTP upload endpoint or inbound port on the
container is needed. Its Docker network must be able to reach the phone's
private address and TCP port 8554; USB debugging alone does not provide this route.

Follow the vision guide to configure an external RTSP secret file with the
displayed URL, an approved local model and its SHA-256, and an output directory.
Keep the URL and local configuration out of Git. The existing container requests
RTSP/TCP interleaving, so video packets use the RTSP TCP connection.

A transport-only check can decode frames with the image's OpenCV without loading
any model. Actual JSONL detections additionally require the approved model.
Do not equate an APK build, camera preview, or model-free decode with successful
end-to-end inference.

## Dependencies and limitations

RTSP-Server 1.4.3 and RootEncoder 2.8.1 are Apache-2.0 dependencies, consumed through
their public APIs rather than copying Rover code. The app explicitly uses
`Camera2Source`, `NoAudioSource` and `setOnlyVideo(true)`. RootEncoder starts both
encoders internally, so the inactive audio encoder is prepared without a
microphone source. The merged manifest removes `RECORD_AUDIO`; live qualification
must also confirm that the SDP contains no audio track.

The Gradle wrapper is an unmodified upstream Gradle distribution component,
not a custom development script. Third-party source links and license notices
are included under `app/src/main/assets`.

This app is not a safety controller or a production camera service. It has no
background service, automatic reconnect, TLS, device fleet management, ONVIF
surface, or unattended operation. Keep Rover stopped and its motor controller
disconnected during camera qualification.
