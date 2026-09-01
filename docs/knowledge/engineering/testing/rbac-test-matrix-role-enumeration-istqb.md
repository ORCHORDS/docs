# RBAC Test Matrix Role Enumeration ISTQB

Role-based access control grants permissions through roles, and users acquire roles. The
correctness surface is the *cross product* of roles and operations: every role, against
every operation, with an expected verdict of *allow* or *deny*. A test suite that samples
this cross product — testing the administrator role thoroughly, the guest role sparsely,
and the specialist role not at all — leaves gaps where unauthorised access ships. The RBAC
test matrix is the systematic enumeration of that cross product, derived from the access
control policy and exercised exhaustively rather than by intuition. ISTQB's black-box
technique of equivalence partitioning applied to the role dimension, combined with a
complete operation catalogue, produces a matrix whose coverage can be counted and whose
gaps are visible.

## Scope

Covers the design and execution of a role-based access control test matrix for any system
whose authorisation model is role-based: web applications, APIs, message queues with
per-role access, and administrative consoles. Applies equally to unit tests of the
authorisation layer and to end-to-end tests that exercise the full request path. Does not
cover attribute-based or policy-based access control (ABAC), nor the broader topic of
authentication testing.

## Workflow or implementation guidance

1. **Enumerate the roles from the policy, not from the code.** The access control policy is
   the specification; the code is the implementation. If the policy defines five roles and
   the code defines six, the sixth is a defect or an undocumented decision. The role list
   must come from the policy document and be versioned alongside the code.
2. **Enumerate the operations exhaustively.** An operation is any action the system exposes:
   every HTTP endpoint, every message queue, every admin command. The operation catalogue
   is derived from the API surface (OpenAPI or equivalent) and from the administrative
   interfaces. A test matrix that covers some endpoints but not others is not a matrix;
   it is a sample.
3. **Build the matrix as the cross product.** For each role and each operation, record the
   expected verdict: *allow* or *deny*. The matrix is the full cross product, including
   the combinations nobody expects to matter — those are the combinations where defects
   hide. An unauthenticated caller is a role too (the "anonymous" role), and a
   deactivated account is another.
4. **Derive expected verdicts from the policy, not from the implementation.** Filling in
   the matrix by asking "what does the code do today" produces a matrix that documents the
   current behaviour, including its defects. The expected verdict comes from the policy;
   a disagreement between the matrix and the observed behaviour is a defect, not a
   surprise to be accepted.
5. **Partition the role dimension to control test volume.** Where many roles share the
   same permission set, equivalence partitioning reduces the work: roles with identical
   expected verdicts across all operations form one equivalence class, and one
   representative per class exercises the class. ISTQB's technique is directly
   applicable: the class is the set of roles the policy treats identically, so a single
   representative test exercises the whole class.
6. **Partition the operation dimension where operations share a permission.** Operations
   guarded by the same permission form an equivalence class. Testing one representative
   per class exercises the permission check; a defect in the guard for a specific
   operation outside the representative is then detected by the catalogue completeness
   check, not by the exhaustive cross product.
7. **Test the boundaries of the role transitions.** A user whose role is upgraded, a user
   whose role is revoked, a token issued under one role and used after the role changed,
   a session that spans a role change — these are the boundary conditions of the role
   dimension, and they are where implementations most often diverge from the policy.
8. **Test the deny path explicitly, not only the allow path.** A test that only asserts
   the administrator *can* do everything says nothing about whether the guest *cannot*.
   Every deny cell in the matrix is a test with an assertion that the action is refused
   with the expected status code and error shape, and that no side effect occurred.
9. **Assert on side effects, not only on status codes.** A request that returns 403 but
   has already written to the database is a defect the status code hides. The deny test
   asserts both: the response was refused, and the system state is unchanged.
10. **Regenerate the matrix when the policy or the API changes.** The matrix is a derived
    artefact. A new endpoint or a new role changes the cross product; the matrix must be
    regenerated and the new cells tested before the change ships.

A representative matrix fragment for a document service with roles `admin`, `editor`,
`viewer`, and `anonymous`:

| Operation | admin | editor | viewer | anonymous |
|---|---|---|---|---|
| `GET /documents` | allow | allow | allow | deny |
| `POST /documents` | allow | allow | deny | deny |
| `DELETE /documents/{id}` | allow | deny | deny | deny |
| `GET /admin/audit-log` | allow | deny | deny | deny |

Each cell is a test; the deny cells assert the refusal and the absence of side effects.

## Controls

- The role list and the operation catalogue are versioned artefacts, derived from the
  policy and the API surface respectively.
- The matrix is committed to the repository; a change to the policy or the API regenerates
  it, and the diff is reviewed.
- Equivalence partitioning on both dimensions is documented; the chosen representatives
  are named so the partitioning is auditable.
- Every deny cell asserts both the refusal and the absence of side effects.
- Role-transition boundary cases (upgrade, revocation, stale token) are explicitly
  enumerated and tested.

## Validation evidence

- A deliberate permission error (granting `DELETE /documents/{id}` to `viewer`) is caught
  by the matrix test; the suite fails before the change ships.
- The matrix covers every operation in the API catalogue; a new endpoint added without a
  matrix row fails a catalogue-completeness check.
- Deny-path tests assert that the database is unchanged after the refused request; a
  defect that writes before authorising is caught.
- The equivalence-class partitioning is reviewed and matches the policy; roles that are
  expected to behave identically are verified to do so.

## Failure modes and correction

- *Matrix filled from the implementation.* Regenerate from the policy; treat disagreements
  as defects to triage, not as expected values to accept.
- *Operations enumerated incompletely.* Derive the catalogue from the OpenAPI
  specification or the router definitions; automate the completeness check.
- *Deny path not tested.* Add deny tests with side-effect assertions; a suite of allow
  tests alone is not an access control test suite.
- *Role transitions untested.* Add boundary tests for upgrade, revocation, and stale
  tokens.
- *Anonymous role omitted.* Treat unauthenticated access as a role; every operation has
  an expected verdict for it.
- *Matrix drifts from the policy.* Regenerate the matrix on every policy change; treat a
  stale matrix as a defect in the change that updated the policy.
- *Equivalence classes assumed without verification.* Verify that roles in the same class
  behave identically; if they do not, the partitioning is wrong.

## Limitations

- The matrix tests role-based checks. Authorisation that depends on attributes beyond the
  role (ownership, tenant, time, geographic location) needs additional dimensions and
  additional techniques.
- A complete cross product grows quickly. With many roles and many operations, exhaustive
  testing becomes expensive; equivalence partitioning reduces the volume but relies on
  the policy treating the class members identically — an assumption that must itself be
  verified periodically.
- The matrix verifies the *policy as written*, not the policy as intended. A policy that
  grants a permission it should not grants it consistently; the matrix passes; the
  vulnerability ships. Policy review is a separate discipline.
- The matrix does not cover authorisation bypasses that operate below the role layer:
  parameter tampering, mass assignment, insecure direct object references. Those require
  dedicated security tests.
- End-to-end execution of the full matrix is slow. Most of the value is captured at the
  authorisation layer's unit or integration level; run the full cross product there and
  spot-check the end-to-end surface.

## Canonical sources

- ISTQB, *Certified Tester Foundation Level (CTFL) syllabus* (equivalence partitioning
  and boundary value analysis applied to access control test design):
  https://istqb.org/downloads/category/2-foundation-level-documents.html
- OWASP, *OWASP Testing Guide* community resources (authorisation testing patterns,
  including role enumeration and deny-path verification): https://owasp.org/www-community/
- OWASP ZAP, *ZAP documentation* (automated passive scanning that complements an
  exhaustive RBAC matrix): https://www.zaproxy.org/docs/
