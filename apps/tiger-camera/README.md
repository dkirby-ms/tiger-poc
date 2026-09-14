---
title: Tiger Camera
description: Foreground-only Android H.264 RTSP source for the Tiger vision container
---

## Scope

This separate Kotlin app supplies a camera stream to the existing
[vision container](../detect/container/README.md). It does not contain inference,
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

Open **Tiger Camera** on the phone. Select a lens, acknowledge the lab policy,
and tap **Start streaming**. If Android requests camera permission, grant it
and tap Start again. Preview starts only with that explicit action.

Use an isolated Wi-Fi network with a private IPv4 address. Disable cellular,
VPN and other network connections (airplane mode with Wi-Fi re-enabled is one
option). The app rejects concurrent networks, stops on a network change, and
does not resume automatically. This is a guard, not network isolation: the app
cannot prove that the Wi-Fi network is private or that other devices are trusted.

The RTSP library listens on all phone interfaces. Video is **unencrypted and
unauthenticated** in this lab-only version. Do not use corporate/public networks,
sensitive scenes, or production deployments. Only authorize scenes whose
participants have agreed to capture.

The app displays `rtsp://<phone-private-ip>:8554/`. It supplies H.264,
640x480, 5 fps, about 600 kbit/s, without an audio track. If the camera cannot
prepare that profile, it stops visibly rather than silently switching profiles.
It stops on **Stop**, app backgrounding, preview destruction, camera failure,
network change, or a ten-minute session timeout. Returning to the app never
automatically restarts streaming.

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
