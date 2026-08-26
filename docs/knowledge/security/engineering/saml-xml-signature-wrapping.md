# saml-xml-signature-wrapping

**Issue:** XML Signature Wrapping (XSW) attacks forge SAML assertions by moving signed elements and inserting malicious content
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SAML responses contain a signed XML element. XSW attacks exploit the disconnect between what the XML signature covers and what the SP's application code reads. An attacker can move the legitimate signed element, insert a forged assertion with admin privileges, and the SP verifies the (now-detached) valid signature while using the unsigned forged element.

## Pattern / Solution
```
XSW attack pattern:
1. Intercept legitimate SAML response
2. Copy the signed <Assertion> element to a new location
3. Insert malicious <Assertion> with elevated claims in the location the SP reads
4. SP verifies signature of the copied (legitimate) element — passes
5. SP uses the unsigned malicious element — attacker is now admin

Mitigation:
- Verify that the element the signature references is the same element your code reads
- Use a battle-tested SAML library (python3-saml, OneLogin, ruby-saml)
- Never write your own SAML parser
```
```python
# python3-saml — validates ID references and signature coverage
from onelogin.saml2.auth import OneLogin_Saml2_Auth
auth = OneLogin_Saml2_Auth(request, custom_base_path=settings_path)
auth.process_response()
if not auth.is_authenticated():
    raise AuthError("SAML authentication failed")
# Library checks: signature coverage, schema, ID references
```

## Gotchas
- The vulnerability is in the SP implementation, not the IdP — patch your SP library.
- ruby-saml < 1.17.0 and python-saml < 2.6.0 had XSW vulnerabilities — check versions.
- Enable schema validation in your SAML library — it rejects structurally malformed responses.
- Log all SAML authentication events including the assertion subject for forensics.

## Related
- `saml-replay-attack-prevention.md`
- `saml-sp-workers.md`
- `xxe-injection-prevention.md`
