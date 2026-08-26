# Use SavedModel Fingerprints as Release Evidence

**Issue:** A directory name or model version label does not prove which TensorFlow graph, signatures, variables, and checkpoint were deployed.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Capture the SavedModel `fingerprint.pb` fields with the artifact digest, TensorFlow version, export code revision, signatures, and training-run identity.
- Compare fingerprints only with documented field semantics; do not collapse the component hashes into an invented compatibility guarantee.
- Sign the release manifest and bind deployment approval to its digest.
- Re-export intentionally when serialization tooling changes, then requalify behavior.

## Verification
- Export the same model twice in the supported toolchain and document expected fingerprint stability.
- Change graph, signature, variable, and checkpoint inputs independently and observe which fields change.
- Fetch the deployed artifact and reconcile its fingerprint to the approved manifest.

## Gotchas
The fingerprint API is experimental. A matching fingerprint identifies SavedModel content; it does not establish model quality, provenance authenticity, or runtime compatibility.

## Official sources
- [TensorFlow SavedModel guide](https://www.tensorflow.org/guide/saved_model)
- [TensorFlow fingerprint API](https://www.tensorflow.org/api_docs/python/tf/saved_model/experimental/Fingerprint)
