# yaml-deserialization-attacks

**Issue:** Unsafe YAML deserialization of user input enables remote code execution via arbitrary object construction
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
YAML parsers that support arbitrary Python/Ruby/Java object construction (PyYAML `yaml.load`, Ruby `YAML.load`, SnakeYAML) allow attackers to construct OS command execution payloads when user-controlled YAML is parsed.

## Pattern / Solution
```python
# INSECURE — yaml.load with default Loader executes arbitrary Python
import yaml
data = yaml.load(user_input)  # RCE possible

# SECURE — use SafeLoader
data = yaml.safe_load(user_input)
# or explicitly
data = yaml.load(user_input, Loader=yaml.SafeLoader)
```
```ruby
# Ruby — avoid YAML.load with untrusted input
# INSECURE
YAML.load(user_input)
# SECURE
YAML.safe_load(user_input)
```
```java
// SnakeYAML — use SafeConstructor
Yaml yaml = new Yaml(new SafeConstructor());
Object data = yaml.load(userInput);
```

## Gotchas
- PyYAML `yaml.load` prints a warning since 5.1 but still executes unless `Loader` is specified — always specify `Loader=yaml.SafeLoader`.
- Config files loaded at startup that accept user-provided paths can be an indirect vector.
- `!!python/object/apply` tags are the classic RCE payload — SafeLoader rejects these.
- JSON is a subset of YAML — JSON payloads passed to YAML parsers are equally dangerous.

## Related
- `xxe-injection-prevention.md`
- `insecure-deserialization-java.md`
