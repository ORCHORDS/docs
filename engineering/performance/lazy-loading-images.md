# Lazy Loading Images

## Native Lazy Loading

Modern browsers support native lazy loading through the `loading="lazy"` attribute. This built-in solution requires no JavaScript and automatically defers image loading until the element is near the viewport.

```html
<img  alt="Description" loading="lazy">
```

For background images, use CSS with `will-change` property for better performance:

```css
.lazy-bg {
  background-image: url('image.jpg');
  will-change: background-image;
}
```

## Intersection Observer API

For more control over lazy loading behavior, use IntersectionObserver API. This approach provides better performance than scroll event listeners and works even when the page is scrolled rapidly.

```javascript
const imageObserver = new IntersectionObserver((entries, observer) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const img = entry.target;
      img.src = img.dataset.src;
      img.classList.remove('lazy');
      observer.unobserve(img);
    }
  });
});

document.querySelectorAll('img[data-src]').forEach(img => {
  imageObserver.observe(img);
});
```

## Blur Placeholder Technique

Implement blur-up technique with low-resolution placeholders to improve perceived performance. This approach shows a blurred version while the full image loads.

```html
<div class="blur-placeholder">
  <img  class="blur-up" alt="Description">
  <img  class="lazy-loaded" alt="Description" loading="lazy">
</div>
```

```css
.blur-up {
  filter: blur(5px);
  transition: filter 0.3s ease;
}

.lazy-loaded {
  filter: blur(0);
}
```

## Largest Contentful Paint (LCP) Impact

Lazy loading can negatively impact LCP if critical images are delayed. Prioritize above-the-fold content by avoiding lazy loading for essential images.

```html
<!-- Critical image - avoid lazy loading -->
<img  alt="Hero Image" loading="eager">
<!-- Non-critical image - use lazy loading -->
<img  alt="Background" loading="lazy">
```

## Responsive Images

Use `srcset` and `sizes` attributes with lazy loading for responsive images. This ensures the correct image size is loaded based on device capabilities.

```html
<img

  srcset="image-small.jpg 300w, image-medium.jpg 600w, image-large.jpg 1200w"
  sizes="(max-width: 300px) 100vw, (max-width: 600px) 50vw, 33vw"
  loading="lazy"
  alt="Responsive Image">
```

## Priority Hints

Use `fetchpriority` attribute for browsers that support it to indicate image priority:

```html
<!-- High priority
