# Flutter ProGuard Rules
-keep class io.flutter.app.** { *; }
-keep class io.flutter.plugin.**  { *; }
-keep class io.flutter.util.**  { *; }
-keep class io.flutter.view.**  { *; }
-keep class io.flutter.**  { *; }
-keep class io.flutter.plugins.**  { *; }

# Keep Flutter embedding and plugins
-keepattributes *Annotation*
-keepattributes Signature
-keepattributes InnerClasses
-keepattributes EnclosingMethod

# flutter_secure_storage and AndroidX Security Crypto
-keep class androidx.security.crypto.** { *; }
-dontwarn androidx.security.crypto.**

# OkHttp / Okio / Network libraries
-dontwarn okio.**
-dontwarn okhttp3.**
-dontwarn javax.annotation.**

# Flutter deferred components / Google Play Core (referenced by Flutter engine)
-dontwarn com.google.android.play.core.**

