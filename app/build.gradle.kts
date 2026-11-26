plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.moonhpro4.moonlightvpn"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.moonhpro4.moonlightvpn"
        minSdk = 21
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"

        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    // OpenVPN runs as its own process from libovpnexec.so, so the native
    // libraries MUST be extracted on install, otherwise the tunnel dies instantly.
    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    implementation("androidx.localbroadcastmanager:localbroadcastmanager:1.1.0")

    // OpenVPN engine (ics-openvpn based). Local module if cloned, else JitPack (same pinned commit).
    if (rootProject.findProject(":vpnLib") != null) {
        implementation(project(":vpnLib"))
    } else {
        implementation("com.github.nizwar:openvpn_library:ccd61bc39b")
    }
}
