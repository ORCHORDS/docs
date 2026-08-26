# emoji-i18n-pitfalls

## 🌍 Flag Emojis by Region

Flag emojis are region-specific and can cause internationalization issues. The Unicode standard defines flags using regional indicator symbols, but not all regions have consistent representations.

```javascript
// ❌ Problematic flag handling
const countryFlags = {
  'US': '🇺🇸', // United States
  'GB': '🇬🇧', // Great Britain
  'CN': '🇨🇳', // China
  'FR': '🇫🇷'  // France
};

// ✅ Better approach with proper region codes
function getCountryFlag(countryCode) {
  if (!countryCode || countryCode.length !== 2) return '';

  const base = countryCode.toUpperCase();
  return base.split('').map(char =>
    String.fromCodePoint(127397 + char.charCodeAt(0))
  ).join('');
}
```

## 👨‍🦰 Skin Tone Modifiers

Skin tone modifiers are optional and may not render consistently across platforms, causing display issues for users with different emoji support levels.

```javascript
// ❌ Inconsistent skin tone rendering
const person = '👨'; // Default skin tone
const personDark = '👨🏿'; // Dark skin tone

// ✅ Safe approach with fallbacks
function safeSkinTone(emoji, skinTone = 'default') {
  const tones = {
    'default': '',
    'light': '🏻',
    'medium-light': '🏼',
    'medium': '🏽',
    'medium-dark': '🏾',
    'dark': '🏿'
  };

  if (skinTone === 'default' || !tones[skinTone]) return emoji;

  // Check if platform supports skin tone
  try {
    const test = emoji + tones[skinTone];
    const rendered = new Intl.DisplayNames(['en'], { type: 'emoji' }).of(test);
    return test;
  } catch {
    return emoji; // Fallback to base emoji
  }
}
```

## 🧑‍🤝‍🧑 ZWJ Sequences

Zero-width joiner (ZWJ) sequences create complex emojis but often lack proper server-side rendering support, causing broken displays.

```javascript
// ❌ Server-side ZWJ issues
const familyEmoji = '👨‍👩‍👧‍👦'; // Family emoji
