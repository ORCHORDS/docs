# Web Accessibility: Focus Management and Keyboard Navigation

## Symptom

Users relying on keyboard navigation or screen readers experience frustration when navigating websites due to poor focus management. Common issues include focus disappearing, tab order confusion, inaccessible modals, and inability to skip repetitive content.

## Gotchas

- **Focus loss**: Content dynamically added/removed causes focus to disappear
- **Modal traps**: Users can't escape modal dialogs without keyboard
- **Tabindex confusion**: Misuse of tabindex creates unexpected navigation flows
- **Roving tabindex issues**: Inconsistent focus management in dynamic components
- **Skip link placement**: Links don't work properly when content structure changes

## Focus Management Strategies

### Basic Focus Control
Use `focus()` method to programmatically set focus:
```javascript
const element = document.getElementById('my-button');
element.focus();
```

### Tabindex Attribute
Control tab order with `tabindex`:
- `tabindex="0"`: Normal tab order
- `tabindex="-1"`: Focusable programmatically only
- `tabindex="1+"`: Custom tab order (avoid when possible)

### Focus Traps for Modals
Implement proper focus trapping in modal dialogs:
```javascript
function createFocusTrap(modal) {
  const focusableElements = modal.querySelectorAll('button, input, select, textarea, a[href]');
  const firstElement = focusableElements[0];
  const lastElement = focusableElements[focusableElements.length - 1];

  function trapFocus(event) {
    if (event.key === 'Tab') {
      if (event.shiftKey && document.activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      } else if (!event.shiftKey && document.activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    }
  }

  modal.addEventListener('keydown', trapFocus);
}
```

### Roving Tabindex
Manage focus in dynamic components:
```javascript
class RovingTabindex {
  constructor(container) {
    this.container = container;
    this.items = container.querySelectorAll('[role="menuitem"]');
    this.selectedIndex = 0;
    this.init();
  }

  init() {
    this.updateFocus();
    this.container.addEventListener('keydown', this.handleKeydown.bind(this));
  }

  updateFocus() {
    this.items.forEach((item, index) => {
      item.setAttribute('tabindex', index === this.selectedIndex ? '0'
