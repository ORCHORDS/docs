# xxe-injection-prevention

**Issue:** XML External Entity injection via unsafe XML parsers allows file read and SSRF
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Applications that parse XML (SOAP, SAML, document upload, SVG) using default parser settings are vulnerable to XXE. Attackers embed external entity references like `<!ENTITY xxe SYSTEM "file:///etc/passwd">` to read local files or trigger SSRF.

## Pattern / Solution
```java
// Java — disable external entities in DocumentBuilderFactory
DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
dbf.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
dbf.setFeature("http://xml.org/sax/features/external-general-entities", false);
dbf.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
dbf.setXIncludeAware(false);
dbf.setExpandEntityReferences(false);
```
```python
# Python — use defusedxml
from defusedxml import ElementTree
tree = ElementTree.fromstring(xml_input)  # safe by default
```
```javascript
// Node.js — xml2js is safe by default; avoid libxmljs with external entities enabled
const xml2js = require('xml2js');
xml2js.parseString(xmlInput, { explicitArray: false }, callback);
```

## Gotchas
- SAML libraries are frequent XXE vectors — check your SAML stack version and parser config.
- SVG files are XML — image upload endpoints that process SVG are vulnerable.
- Disabling DTD processing entirely (`disallow-doctype-decl`) is safer than cherry-picking entity features.
- JSON APIs that accept XML via `Content-Type` negotiation may still be vulnerable if the XML path is not hardened.

## Related
- `server-side-request-forgery-ssrf.md`
- `saml-sp-workers.md`
- `yaml-deserialization-attacks.md`
