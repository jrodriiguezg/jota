plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
}

// Dependencias principales para el modulo app
// - AndroidX Core & Lifecycle
// - Jetpack Compose (Material3, Icons, UI)
// - OkHttp 4.12+ (WebSockets y llamadas REST)
// - Coroutines
