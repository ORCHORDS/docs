# Vue 3 Composition API and Script Setup

## Overview

Vue 3's Composition API introduces a new way to organize and reuse logic in components, offering more flexibility than the traditional Options API. The `script setup` syntax simplifies component definitions by automatically importing and exposing references.

## Key Concepts

### Ref, Reactive, Computed, Watch
```javascript
import { ref, reactive, computed, watch } from 'vue'

const count = ref(0)
const user = reactive({ name: 'John', age: 30 })
const doubled = computed(() => count.value * 2)
watch(count, (newVal) => console.log(`Count is now ${newVal}`))
```

`ref` creates a reactive reference to a primitive value, while `reactive` wraps objects for reactivity. `computed` creates cached, reactive values, and `watch` monitors changes.

### Script Setup in SFC
```vue
<script setup>
import { ref, computed } from 'vue'

const message = ref('Hello')
const reversed = computed(() => message.value.split('').reverse().join(''))
</script>

<template>
  <p>{{ message }}</p>
  <p>{{ reversed }}</p>
</template>
```

The `script setup` syntax automatically exposes all references to the template without needing `export` or `setup()`.

### defineProps and defineEmits
```vue
<script setup>
defineProps({
  title: String,
  count: { type: Number, default: 0 }
})

const emit = defineEmits(['update:count', 'delete'])
</script>
```

These macros replace the need for `props` and `emits` options in traditional components.

### Pinia Stores
```javascript
// stores/user.js
import { defineStore } from 'pinia'

export const useUserStore = defineStore('user', {
  state: () => ({ name: '', isLoggedIn: false }),
  actions: {
    login(name) {
      this.name = name
      this.isLoggedIn = true
    }
  }
})
```

## Symptom

### Common Issues
- **Missing imports**: Forgetting to import `ref`, `reactive` from Vue can cause runtime errors.
- **Reactivity loss**: Using `const` instead of `ref()` for primitives leads to non-reactive data.
- **Template access**: Variables defined in script setup must be referenced directly in template without
