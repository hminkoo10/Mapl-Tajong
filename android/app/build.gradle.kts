import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// 버전은 version.properties 한 곳에서 관리 (CI가 릴리스 이름과 맞는지 확인한다)
val versionProps = Properties().apply { rootProject.file("version.properties").inputStream().use { load(it) } }
val appVersionName: String = versionProps.getProperty("versionName")
val appVersionCode: Int = versionProps.getProperty("versionCode").toInt()

android {
    namespace = "com.milky.mataf"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.milky.mataf"
        minSdk = 26
        targetSdk = 35
        versionCode = appVersionCode
        versionName = appVersionName
    }

    // 서명: CI 비밀값(ANDROID_KEYSTORE_*)이 있으면 그 키로, 없으면 시험용(디버그) 키로
    val ksFile = System.getenv("ANDROID_KEYSTORE_FILE")
    signingConfigs {
        if (!ksFile.isNullOrBlank() && file(ksFile).exists()) {
            create("release") {
                storeFile = file(ksFile)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS")
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release") ?: signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        isCoreLibraryDesugaringEnabled = true
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    androidResources {
        noCompress += setOf("wav", "mp3", "ogg", "m4a")
    }

    packaging {
        resources {
            excludes += setOf("META-INF/DEPENDENCIES", "META-INF/LICENSE*", "META-INF/NOTICE*", "META-INF/*.kotlin_module")
        }
    }
}

// 업데이트 기록: android/CHANGELOG.md 를 앱(assets)에 함께 넣는다
abstract class CopyChangelog : DefaultTask() {
    @get:InputFile abstract val source: RegularFileProperty
    @get:OutputDirectory abstract val outDir: DirectoryProperty

    @TaskAction
    fun run() {
        source.get().asFile.copyTo(outDir.get().file("CHANGELOG.md").asFile, overwrite = true)
    }
}

val copyChangelog = tasks.register<CopyChangelog>("copyChangelog") { source.set(rootProject.file("CHANGELOG.md")) }
androidComponents {
    onVariants { it.sources.assets?.addGeneratedSourceDirectory(copyChangelog, CopyChangelog::outDir) }
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.3")

    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")

    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    debugImplementation("androidx.compose.ui:ui-tooling")
    implementation("androidx.compose.ui:ui-tooling-preview")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    // YouTube·SoundCloud 검색과 소리 주소 (NewPipe 앱이 쓰는 라이브러리).
    // 릴리스 v0.26.5 의 Android 클라이언트는 YouTube 가 막아서, NewPipe 앱 dev 가 쓰는 커밋(2026-10-21)을 쓴다.
    implementation("com.github.TeamNewPipe:NewPipeExtractor:e8f89145a830b4d6cae32412007f24ea8b36c73a")
    // 구글 로그인 창(WebView)에서 앱 이름 헤더 빼기
    implementation("androidx.webkit:webkit:1.12.1")
    // YouTube 주소의 n 값·서명 풀기 스크립트를 돌리는 JavaScript 엔진 (core/JsChallenge.kt)
    implementation("androidx.javascriptengine:javascriptengine:1.1.1")

    testImplementation("junit:junit:4.13.2")
}
