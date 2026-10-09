plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

// Phones are arm64. For the emulator build with: gradlew assembleDebug -Pabis=x86_64
val abis = (findProperty("abis") as String? ?: "arm64-v8a").split(",")

android {
    namespace = "app.datastore"
    compileSdk = 35

    defaultConfig {
        applicationId = "app.datastore"
        minSdk = 29
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
        ndk { abiFilters += abis }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // rclone ships as lib/<abi>/librclone.so; it must be extracted to disk to be executable.
    packaging { jniLibs { useLegacyPackaging = true } }
}

chaquopy {
    defaultConfig {
        version = "3.12"
        pyc { src = false }
        extractPackages("datastore")  // the web UI is read from files next to the package
    }
    sourceSets {
        getByName("main") { srcDir("build/python-src") }
    }
}

// The Python package is shared with the PC app, so it is copied in at build time, not duplicated.
val syncPython by tasks.registering(Sync::class) {
    from(rootDir.resolve("../datastore")) { exclude("**/__pycache__/**") }
    into(layout.buildDirectory.dir("python-src/datastore"))
}

val checkRclone by tasks.registering {
    val missing = abis.filter { !file("src/main/jniLibs/$it/librclone.so").exists() }
    doLast {
        if (missing.isNotEmpty()) {
            throw GradleException("rclone missing for $missing - run: python fetch_rclone.py ${missing.joinToString(" ")}")
        }
    }
}

tasks.named("preBuild") { dependsOn(syncPython, checkRclone) }
tasks.matching { it.name.startsWith("merge") && it.name.endsWith("PythonSources") }
    .configureEach { dependsOn(syncPython) }
