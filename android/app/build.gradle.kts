plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "io.github.dshpet.mobile"
    compileSdk = 36
    defaultConfig {
        applicationId = "io.github.dshpet.mobile"
        minSdk = 26
        targetSdk = 36
        versionCode = 3
        versionName = "0.2.1"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true; buildConfig = true }
    sourceSets["main"].assets.srcDir(layout.buildDirectory.dir("generated/petAssets"))
    sourceSets["main"].res.srcDir(layout.buildDirectory.dir("generated/petRes"))
    testOptions { unitTests.isReturnDefaultValues = true }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
}

val exportPetAssets by tasks.registering(Exec::class) {
    val repository = rootProject.projectDir.parentFile
    val python = providers.gradleProperty("petPython").orElse("python")
    inputs.dir(repository.resolve("assets/characters/shenshen/videos"))
    inputs.dir(repository.resolve("assets/sounds/duck"))
    inputs.file(repository.resolve("scripts/export_android_assets.py"))
    inputs.file(repository.resolve("pet/frameseq_provision.py"))
    inputs.file(repository.resolve("pet/config.py"))
    inputs.file(repository.resolve("scripts/make_icon.py"))
    inputs.file(rootProject.file("NOTICE.txt"))
    inputs.file(rootProject.file("LICENSE-APACHE-2.0.txt"))
    outputs.dir(layout.buildDirectory.dir("generated/petAssets"))
    outputs.dir(layout.buildDirectory.dir("generated/petRes"))
    workingDir(repository)
    commandLine(python.get(), "scripts/export_android_assets.py", "--output",
        layout.buildDirectory.dir("generated/petAssets").get().asFile.absolutePath,
        "--res-output", layout.buildDirectory.dir("generated/petRes").get().asFile.absolutePath)
}
tasks.named("preBuild").configure { dependsOn(exportPetAssets) }

dependencies {
    implementation(platform("androidx.compose:compose-bom:2025.05.01"))
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test:rules:1.6.1")
}
