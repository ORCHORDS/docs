# ICU MessageFormat 2026

ICU MessageFormat 2026 introduces significant enhancements to internationalization capabilities with improved pluralization, gender handling, and rich text support. This article covers the latest features and practical implementation examples.

## Pluralization Improvements

The new pluralization system supports more complex rules and better locale-specific handling:

```javascript
import { MessageFormat } from '@formatjs/icu-messageformat-parser';

const msg = new MessageFormat('You have {count, plural, =0{no messages} one{one message} other{# messages}}');
console.log(msg.format({ count: 5 })); // "You have 5 messages"
```

## Gender Support

Enhanced gender handling with automatic gender detection and explicit gender specification:

```javascript
const genderMsg = new MessageFormat('{name, gender, male{He} female{She} other{They}} read the book');
console.log(genderMsg.format({ name: "John", gender: "male" })); // "He read the book"
```

## Select Operations

New select operations provide better conditional formatting:

```javascript
const selectMsg = new MessageFormat('{status, select, active{Online} inactive{Offline} pending{Pending}}');
console.log(selectMsg.format({ status: "active" })); // "Online"
```

## Nested Messages

Complex nested message structures now supported with improved performance:

```javascript
const nestedMsg = new MessageFormat('Hello {user, select, name{{name}} other{Guest}}! {count, plural, one{One item} other{# items}}');
console.log(nestedMsg.format({ user: { name: "Alice" }, count: 3 })); // "Hello Alice! 3 items"
```

## Rich Text Support

Built-in rich text formatting capabilities for HTML content:

```javascript
const richMsg = new MessageFormat('Visit <a >{title}</a> for more information');
console.log(richMsg.format({ url: "https://example.com", title: "Example" }));
```

## API Examples

### Basic Usage
```javascript
import { MessageFormat } from '@formatjs/icu-messageformat-parser';

const mf = new MessageFormat('Hello {name}!');
const result = mf.format({ name: 'World' });
console.log(result); // "Hello World!"
```

### Advanced Formatting
```javascript
const
