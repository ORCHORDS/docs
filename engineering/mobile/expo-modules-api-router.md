# Expo Modules API + Expo Router: Modern Native Navigation for React Native

## Overview

Expo Modules API and Expo Router represent the modern approach to building native mobile applications with React Native. Together, they provide a powerful combination for creating seamless navigation experiences while maintaining access to native device capabilities.

## Expo Router: File-Based Navigation

Expo Router introduces file-based routing that simplifies navigation setup. Instead of traditional configuration-based approaches, you define routes through your file structure.

```javascript
// app/_layout.tsx
import { Stack } from 'expo-router';

export default function RootLayout() {
  return (
    <Stack>
      <Stack.Screen name="index" options={{ title: 'Home' }} />
      <Stack.Screen name="profile" options={{ title: 'Profile' }} />
    </Stack>
  );
}
```

```javascript
// app/index.tsx
import { Button, View } from 'react-native';
import { useRouter } from 'expo-router';

export default function HomeScreen() {
  const router = useRouter();

  return (
    <View style={{ flex: 1, justifyContent: 'center' }}>
      <Button
        title="Go to Profile"
        onPress={() => router.push('/profile')}
      />
    </View>
  );
}
```

## Expo Modules Core: Native Module Integration

Expo Modules API provides access to native device features through a unified JavaScript interface.

```javascript
// Using expo-camera module
import { Camera } from 'expo-camera';
import { useEffect, useState } from 'react';

export default function CameraScreen() {
  const [hasPermission, setHasPermission] = useState(null);

  useEffect(() => {
    (async () => {
      const { status } = await Camera.requestCameraPermissionsAsync();
      setHasPermission(status === 'granted');
    })();
  }, []);

  if (hasPermission === null) {
    return <View />;
  }

  if (hasPermission === false) {
    return <Text>No access to camera</Text>;
  }

  return (
    <Camera style={{ flex: 1 }} />
  );
}
```

## EAS Build Integration

EAS Build streamlines the build process for Expo applications, working seamlessly with both Expo Router and Modules API.

```json
// app.json
{
  "expo": {
    "name": "MyApp",
    "slug": "my-app",
    "version":
