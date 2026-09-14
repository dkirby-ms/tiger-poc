plugins {
    id("com.android.application")
}

android {
    namespace = "org.tigerpoc.camera"
    compileSdk = 37
    buildToolsVersion = "37.0.0"

    defaultConfig {
        applicationId = "org.tigerpoc.camera"
        minSdk = 23
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    lint {
        abortOnError = true
        checkReleaseBuilds = true
    }
    packaging {
        resources.merges += setOf("META-INF/LICENSE*", "META-INF/NOTICE*")
    }
}

dependencyLocking {
    lockAllConfigurations()
}

dependencies {
    implementation("com.github.pedroSG94:RTSP-Server:1.4.3")
    implementation("com.github.pedroSG94.RootEncoder:library:2.8.1")
    testImplementation("junit:junit:4.13.2")
}
