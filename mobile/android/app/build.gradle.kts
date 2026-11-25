plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

/**
 * Release signing, read from `mobile/android/key.properties` (git-ignored).
 *
 * Read during configuration, but only *required* when a release build is requested — see
 * the task-graph check at the bottom of this file. A debug build therefore needs no setup.
 */
val keystoreProperties = java.util.Properties().apply {
    val file = rootProject.file("key.properties")
    if (file.exists()) {
        file.inputStream().use { load(it) }
    }
}

android {
    namespace = "dev.soapbot.archive"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "dev.soapbot.archive"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (keystoreProperties.isNotEmpty()) {
            create("release") {
                storeFile = file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // `null` when no keystore is configured: an unsigned release APK is a build
            // failure (see the task-graph check below), not a silently debug-signed one.
            signingConfig = signingConfigs.findByName("release")
        }
    }
}

// The failure must happen only when a release build is actually requested: throwing
// during configuration would break `flutter build apk --debug`, every IDE sync and
// `flutter test` on a machine without a keystore — which is exactly how a guard gets
// deleted. The Flutter template signed release with the *debug* key "so
// `flutter run --release` works"; that key's password is `android` and it is shared by
// every Flutter project, so anyone could sign an update for the same applicationId and
// Play refuses the upload (audit S-FE-02).
gradle.taskGraph.whenReady {
    val buildingRelease = allTasks.any { task ->
        task.name.startsWith("assemble") && task.name.contains("Release", ignoreCase = true)
    }
    if (buildingRelease && keystoreProperties.isEmpty) {
        throw GradleException(
            "release signing is not configured: create mobile/android/key.properties " +
                "(storeFile / storePassword / keyAlias / keyPassword — see " +
                "key.properties.example) or build a debug APK with " +
                "`flutter build apk --debug`. A debug-signed release APK uses a public, " +
                "shared key and must not be distributed."
        )
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
