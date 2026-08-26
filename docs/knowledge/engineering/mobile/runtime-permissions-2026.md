# Runtime Permissions in Modern Mobile Development

## Overview

Modern mobile platforms require apps to request permissions at runtime, especially for sensitive data access. iOS 14+ and Android 13+ introduced significant changes to how permissions are handled, requiring developers to implement proper permission groups and user consent flows.

## iOS Privacy Manifest Implementation

iOS 14+ requires apps to declare privacy practices through the `PrivacyInfo.xcprivacy` file. This file must be added to your Xcode project and contains declarations about data usage.

```swift
// Example PrivacyInfo.xcprivacy content
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>NSPhotoLibraryUsageDescription</key>
    <string>This app needs access to photos to save captured images</string>
    <key>NSBluetoothAlwaysUsageDescription</key>
    <string>This app uses Bluetooth to connect with fitness devices</string>
</dict>
</plist>
```

## Android 13+ Permission Groups

Android 13 introduced new permission groups and the photo picker API, which simplifies image selection while respecting user privacy.

```kotlin
// Requesting permissions in Android 13+
private fun requestPermissions() {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        // Request notification permission
        if (ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.POST_NOTIFICATIONS
            ) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                NOTIFICATION_PERMISSION_REQUEST_CODE
            )
        }
    }

    // Request photo library access
    if (ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.READ_MEDIA_IMAGES
        ) != PackageManager.PERMISSION_GRANTED) {
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.READ_MEDIA_IMAGES),
            PHOTO_PERMISSION_REQUEST_CODE
        )
    }
}
```

## Permission Group Handling

Both platforms now group related permissions together, requiring developers to understand these relationships:

```swift
// iOS - Check multiple related permissions
func checkPhotoPermissions() {
    PHPhotoLibrary.requestAuthorization(.readWrite) { status in
        DispatchQueue.main.async {
            switch status {
            case .authorized:
