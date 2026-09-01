---
title: "in-toto Layout and Threshold Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# in-toto Layout and Threshold Governance

## Layout and link semantics

An in-toto layout is signed by the supply-chain owner. It declares `steps`, `inspect`, keys, and `expires`. Each step has a name, expected command, authorized `pubkeys`, `threshold`, and ordered material/product artifact rules. Functionaries produce signed link metadata containing step name, command, materials, products, environment, and byproducts. Verification first authenticates and checks the layout expiration, then verifies enough authorized links and evaluates artifact rules and inspections.

Rules include `MATCH`, `CREATE`, `DELETE`, `MODIFY`, `ALLOW`, and `DISALLOW`, with optional path patterns and prefixes. Rule order matters because artifacts are consumed from a working set. End a strict rule set with `DISALLOW *` so unexpected artifacts do not pass. `MATCH` should connect a product from one step to material in another, preventing an unrecorded substitution.

```json
{"_type":"layout","expires":"2026-12-01T00:00:00Z","keys":{"alice":{"keytype":"ed25519","scheme":"ed25519","keyval":{"public":"..."}}},"steps":[{"name":"build","expected_command":["make","release"],"pubkeys":["alice"],"threshold":1,"expected_materials":[["MATCH","src/*","WITH","PRODUCTS","FROM","clone"],["DISALLOW","*"]],"expected_products":[["CREATE","dist/*"],["DISALLOW","*"]]}],"inspect":[]}
```

## Thresholds, inspections, and rollback

A threshold of two requires distinct authorized keys with consistent artifact views; it does not prove organizational independence if one service controls both keys. Inspections execute during verification, so pin their tools and isolate network and filesystem access. `expected_command` is checked against recorded command metadata but does not prove no additional process ran; artifact rules and worker isolation remain necessary. Sublayouts delegate a step and require their own authenticated keys.

Test missing link, unauthorized key, threshold shortfall, mismatched materials, modified artifact, extra product, expired layout, failed inspection, and two threshold links reporting different hashes. Retain the root layout, signatures, all links, verifier version, stdout/stderr, and final artifact digest.

Rotate by publishing a newly signed layout before the old one expires and testing both verifier trust paths. If a bad layout blocks release, roll back to a still-valid previously authorized layout; never extend expiration by editing signed bytes. Monitor links absent from production paths, layouts near expiry, unexpected functionaries, and artifact-rule failures.

## Sources

- [in-toto specification](https://github.com/in-toto/docs/blob/master/in-toto-spec.md)
- [in-toto](https://in-toto.io/)
