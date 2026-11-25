pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.PREFER_SETTINGS)
    repositories {
        google()
        mavenCentral()
        maven { url = uri("https://jitpack.io") }   // only used if the engine could not be cloned
    }
}

rootProject.name = "MoonlightVPN"
include(":app")

// The OpenVPN engine is cloned into ./engine by scripts/fetch-engine.sh (done by the CI workflow).
// If it is there we compile it from source as a local module; otherwise app/build.gradle.kts
// falls back to the JitPack artifact of the very same commit.
val engineModule = file("engine/vpnLib")
if (engineModule.isDirectory) {
    include(":vpnLib")
    project(":vpnLib").projectDir = engineModule
}
