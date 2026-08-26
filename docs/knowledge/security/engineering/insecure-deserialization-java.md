# insecure-deserialization-java

**Issue:** Java native deserialization of untrusted data enables RCE via gadget chains in common libraries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Java's `ObjectInputStream.readObject()` on attacker-controlled data triggers gadget chains in libraries like Commons Collections, Spring, and Jackson. This was the root cause of numerous high-profile RCEs including the 2015 WebLogic/JBoss vulnerabilities.

## Pattern / Solution
```java
// INSECURE
ObjectInputStream ois = new ObjectInputStream(inputStream);
Object obj = ois.readObject(); // dangerous

// SECURE option 1 — use a filtered stream (Java 9+)
ObjectInputStream ois = new ObjectInputStream(inputStream);
ois.setObjectInputFilter(FilterConfig.createFilter(
    "maxdepth=5;maxarray=10000;!*" // deny all classes not explicitly allowed
));

// SECURE option 2 — use a safe deserialization library
// Jackson with no default typing
ObjectMapper mapper = new ObjectMapper();
mapper.disable(MapperFeature.DEFAULT_VIEW_INCLUSION);
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
// Never call enableDefaultTyping() or use @JsonTypeInfo with untrusted data

// SECURE option 3 — use serialization-killswitch agent
// -javaagent:noserializable.jar to block ObjectInputStream entirely
```

## Gotchas
- JSON libraries (Jackson, Gson) can also be vulnerable when polymorphic type handling is enabled.
- `serialver` tool reveals serializable classes — audit your classpath for known gadget libraries.
- SerialKiller and NotSoSerial are JVM agents that block known gadget classes at runtime.
- Spring's `RemoteInvocationSerializingExporter` and older RMI endpoints are common entry points.

## Related
- `yaml-deserialization-attacks.md`
- `prototype-pollution-prevention.md`
