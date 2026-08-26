# Privacy-Enhancing Technologies (PETs) — Differential Privacy, Homomorphic Encryption, MPC

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your data science team needs to train models on sensitive health records
across three hospital systems. No hospital can share raw patient data
due to HIPAA and GDPR. Your current approach — anonymizing data before
sharing — has already failed a re-identification audit (zip code +
birth year + gender identified 87% of patients). You need to perform
computations on the combined dataset without any party seeing another
party's raw records.

## Context

Privacy-Enhancing Technologies (PETs) are cryptographic and statistical
techniques that enable data analysis while mathematically preserving
individual privacy. The three core PETs are Differential Privacy (DP),
which adds calibrated noise to query results; Homomorphic Encryption
(HE), which enables computation on encrypted data without decryption;
and Secure Multi-Party Computation (MPC), which allows multiple parties
to jointly compute a function while keeping inputs private. In 2026,
the global PET market reached $2.8 billion (up from $1.1 billion in
2022), driven by GDPR, CCPA, the EU AI Act, DORA, and Brazil's LGPD.
Gartner projects the market to exceed $25 billion by 2030. PETs have
shifted from academic curiosities to production infrastructure,
particularly for AI training pipelines in regulated industries.

## Differential privacy

```python
# Using diffprivlib (IBM)
from diffprivlib.mechanisms import Laplace
from diffprivlib import BudgetAccountant

# Track cumulative privacy spend across queries
accountant = BudgetAccountant(epsilon=1.0, delta=1e-5)

# Each query consumes part of the budget
mechanism = Laplace(epsilon=0.5, sensitivity=1, accountant=accountant)
noisy_result = mechanism.randomise(true_value)
# accountant tracks cumulative spend — exceeding budget raises error
```

```
Key concepts:
  Epsilon (ε):   Privacy budget. Smaller = more noise = stronger privacy
  Delta (δ):     Probability of privacy guarantee failure
  Sensitivity:   Maximum change one individual can cause in query output
  Composition:   Each query spends part of the budget — track cumulative

Decision guide:
  ε < 1.0:   Strong privacy, significant accuracy loss
  ε = 1-3:   Moderate privacy, acceptable for most analytics
  ε > 10:    Weak privacy, rarely justified
```

## Homomorphic encryption

```
Types:
  Partially HE:   One operation (add OR multiply), fast
  Somewhat HE:    Limited add + multiply, moderate speed
  Fully HE (FHE): Arbitrary computation, 1000-10000x slower

Libraries (2026):
  Microsoft SEAL:   C++ with Python bindings, BFV/CKKS schemes
  TenSEAL:          Tensor operations on encrypted data (~144 enc/sec)
  OpenFHE:          Research-grade, supports all major schemes
  Concrete:         Zama's Rust FHE compiler, TFHE scheme

Constraint: FHE adds noise to ciphertexts that grows with each
operation. Exceeding the noise budget makes decryption impossible.
Circuit depth must be planned in advance.
```

## Secure multi-party computation

```
How it works:
  1. Each party holds private input
  2. Parties exchange encrypted shares via MPC protocol
  3. Joint computation produces result without revealing inputs
  4. Only the final output is visible to designated parties

Protocols:
  Garbled circuits:   Two-party, constant rounds, high bandwidth
  Secret sharing:     Multi-party, low communication, more rounds
  Oblivious transfer: Building block for other protocols

Use cases:
  → Private set intersection (ad attribution without sharing user lists)
  → Joint model training across organizations
  → Salary benchmarking without disclosing individual compensation
  → Secure auctions (sealed-bid without trusted auctioneer)
```

## Technology comparison

```
                  Differential Privacy   Homomorphic Enc.    MPC
Privacy model:    Statistical            Cryptographic       Cryptographic
Performance:      Minimal overhead       1000-10000x slower  10-1000x slower
Data utility:     Reduced by noise       Exact (encrypted)   Exact (shared)
Trust model:      Trusted aggregator     Untrusted server    No single trust
Best for:         Analytics/ML           Cloud computation   Multi-party
Maturity:         Production-ready       Emerging production Research/pilot
```

## Anti-patterns

- **Silver-bullet thinking** — treating PETs as a substitute for
  organizational data governance. Users can still voluntarily share
  results, breaking privacy guarantees. PETs are one layer in a
  defense-in-depth strategy.
- **Ignoring epsilon budget exhaustion** — running repeated queries
  without tracking cumulative privacy spend. Each query consumes
  part of the budget; once exhausted, no privacy guarantee remains.
  Use a budget accountant for all DP queries.
- **Underestimating computational cost** — prototyping FHE on small
  datasets and assuming production will scale linearly. FHE
  operations are 1000-10000x slower than plaintext. Benchmark with
  production-scale data before committing.
- **Poor key management** — undermining encryption-based PETs with
  weak key storage, shared keys, or missing rotation. Key management
  is the foundation of HE and MPC security.

## Gotchas

- **Composition attacks** — combining multiple differentially private
  releases can erode privacy beyond what individual epsilon values
  suggest. Use advanced composition theorems or Renyi DP for tight
  accounting across many queries.
- **TEE side-channel vulnerabilities** — Trusted Execution
  Environments (SGX, TrustZone) have published side-channel attacks
  that are architecture-specific. Research vulnerabilities for your
  specific deployment before relying on TEEs.
- **Regulatory acceptance varies** — not all regulators recognize
  PETs as sufficient compliance measures. GDPR's position on
  differential privacy as anonymization is still evolving. Get legal
  guidance for your jurisdiction.
- **FHE noise budget planning** — the noise in FHE ciphertexts
  grows with each operation. Exceeding the noise budget makes
  decryption impossible. Circuit depth must be planned and tested
  before deployment.

## Verification

- Privacy budget is tracked with an accountant across all queries.
- Epsilon values are reviewed and approved for each use case.
- HE noise budget is validated for the computational circuit.
- MPC protocol is tested with adversarial party simulations.
- Key management follows organizational cryptographic standards.
- Regulatory counsel has reviewed PET deployment for compliance.

## Related

- `documentation/docs/policies/compliance/gdpr-data-protection-engineering.md`
- `documentation/docs/policies/compliance/data-retention-policy-engineering.md`
- `documentation/docs/policies/security/secrets-management-vault-patterns.md`

## Source URLs (verified 2026-08-16)

- Privacy Enhancing Technologies — U.S. GAO Science & Tech Spotlight — https://www.gao.gov/products/gao-26-109063
- Homomorphic Encryption 2026: From Theory to Enterprise Production — https://www.programming-helper.com/tech/homomorphic-encryption-2026-privacy-preserving-computation-enterprise
- FTC: Keeping Your PET Promises — https://www.ftc.gov/policy/advocacy-research/tech-at-ftc/2024/02/keeping-your-privacy-enhancing-technology-pet-promises
- Differential Privacy + Synthetic Data in 2026: Hands-on Python Tutorial — https://dev.to/pankaj_dhawan_fc4c5bf763a/differential-privacy-synthetic-data-in-2026-hands-on-python-tutorial-to-build-bulletproof-ai-57om
