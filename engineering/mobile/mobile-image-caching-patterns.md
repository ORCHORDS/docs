# mobile-image-caching-patterns

**Issue:** Efficiently loading and caching images in mobile apps
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Images are the largest contributor to memory and network usage in most apps. Without caching, images reload on every scroll, causing jank and wasted bandwidth.

## Pattern / Solution
**React Native — expo-image (recommended):**
```tsx
import { Image } from 'expo-image';

<Image
  source={{ uri: 'https://example.com/photo.jpg' }}
  placeholder={{ blurhash: 'L6PZfSi_.AyE_3t7t7R**0o#DgR4' }}
  contentFit="cover"
  transition={{ duration: 200, effect: 'cross-dissolve' }}
  cachePolicy="memory-disk"  // memory-only | disk-only | memory-disk | none
  recyclingKey={item.id}     // reuse view for different images in lists
  style={{ width: 300, height: 200 }}
/>
```

**Generate blurhash on server:**
```ts
import { encode } from 'blurhash';
const blurhash = encode(pixels, width, height, 4, 3); // returns ~30-char string
```

**Progressive loading pattern:**
```tsx
const [loaded, setLoaded] = useState(false);
<View>
  <Image source={{ uri: thumbnailUrl }} style={StyleSheet.absoluteFill} />
  <Image
    source={{ uri: fullUrl }}
    onLoad={() => setLoaded(true)}
    style={[StyleSheet.absoluteFill, { opacity: loaded ? 1 : 0 }]}
  />
</View>
```

**iOS — NSCache (Swift):**
```swift
let cache = NSCache<NSString, UIImage>()
cache.countLimit = 100
cache.totalCostLimit = 50 * 1024 * 1024 // 50 MB

func loadImage(url: URL) async -> UIImage? {
    let key = url.absoluteString as NSString
    if let cached = cache.object(forKey: key) { return cached }
    let (data, _) = try await URLSession.shared.data(from: url)
    let image = UIImage(data: data)
    image.map { cache.setObject($0, forKey: key, cost: data.count) }
    return image
}
```

## Gotchas
- `expo-image` uses SDWebImage (iOS) and Glide (Android) under the hood — both have battle-tested caching
- `recyclingKey` is critical in FlatLists; without it, React Native can display the wrong image during fast scroll
- Disk cache size is not managed automatically in all libraries; implement periodic cache eviction
- Animated GIFs and WebP animations require explicit library support; check expo-image's supported formats per platform
- High-resolution images should be requested at the device's actual display size (consider `PixelRatio.get()`)

## Related
- `react-native-performance-optimization.md`
- `mobile-performance-profiling.md`
- `pwa-offline-caching-strategies.md`
