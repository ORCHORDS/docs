# iOS Data Protection: NSFileProtection Complete and Advanced File Protection

On iOS, every file can carry a protection class — an attribute binding the file's readability to the device lock state and key availability. `NSFileProtectionComplete` is the strongest class: the file's encryption key lives in hardware, usable only when the device is unlocked (technically, until first lock after boot for some classes; Complete re-seals at first lock). Files default to a weaker class, so adopting Complete-level protection is an explicit engineering task: classify files, apply classes at write time (or after), understand unlock-window semantics, and handle the APIs that fail while locked. This article covers the protection class model, applying classes in practice, behavior across lock states and boots, and the failure modes of getting the window wrong.

## Scope

This article addresses iOS file protection classes: `NSFileProtectionComplete`, `CompleteUnlessOpen`, `CompleteUntilFirstUserAuthentication`, and `None` — their semantics across lock/unlock and boot, applying classes via `FileManager` attributes and write-time options (`FileProtectionType`), per-file versus whole-app defaults, interaction with background execution and extensions, and migration of existing files. It covers data-at-rest protection on device. It does not cover encrypted Core Data/SQLCipher, keychain access control (`kSecAttrAccessible`, a parallel but distinct mechanism), or backup encryption.

## Workflow or implementation guidance

The four classes, in order of strength:

- **`NSFileProtectionComplete`** — key discarded at first lock after boot; file unreadable and unwritable while locked. After the first unlock following a reboot, the key is derived and held until the *next* first-lock event; the practical contract is "usable only while the device is unlocked" with the first-unlock-after-boot nuance.
- **`CompleteUnlessOpen`** — unreadable to *open* while locked, but a file already open before lock stays usable until closed. Built for exactly one pattern: write-once, stream-to-completion (a download or recording that begins unlocked, continues across lock, finishes, and is only then sealed forever).
- **`CompleteUntilFirstUserAuthentication`** — protected only until the first unlock after boot; usable thereafter even when locked again. The system's *default* for app files: protects against offline extraction after reboot (before first unlock) while allowing background access anytime after.
- **`None`** — no protection class; readable whenever the filesystem is mounted.

The default is `CompleteUntilFirstUserAuthentication`, which means **unclassified app data is protected against the reboot-and-extract attack but fully readable by anything running after first unlock** — including while the screen is locked. If your threat model includes an attacker (or malware, or a seized-while-locked device with a jailbroken path) reading data at rest while locked, `Complete` on the sensitive subset is the mechanism.

Applying classes:

1. **At write time (preferred).** `FileManager` creation with attributes: `FileManager.default.createFile(atPath: path, contents: data, attributes: [.protectionKey: FileProtectionType.complete])`; atomic writes via `Data.write(to:options: .completeFileProtection)`; `FileHandle` and `OutputStream` initializers accept protection options for streaming writes. Write-time application avoids the migration race entirely for new data.
2. **After the fact.** `FileManager.default.setAttributes([.protectionKey: .complete], ofItemAtPath: path)` upgrades an existing file — the migration path for data written before classification existed. Attributes are per-file; directories do not propagate protection to children (create files with explicit classes rather than relying on any directory-level expectation).
3. **Classify by lifecycle, not by convenience.** The design question for each file: "when must this be readable?" Databases the UI opens while foregrounded: `Complete` if the app never touches it from the background. A download in progress begun unlocked: `CompleteUnlessOpen` (open before lock, finish, sealed at close). Crash logs the app must upload from a background task after reboot-free lock: `CompleteUntilFirstUserAuthentication`. Cache of non-sensitive derived data: default is fine; `None` is almost never right.
4. **Background execution and extensions widen the window.** Background fetch, audio sessions, notifications extensions, and widgets can execute while the device is locked. Any file those paths touch cannot be `Complete` — the read will fail with a permissions-style error while locked. Audit every background entry point against the file classes it touches; the audit is the control that prevents "works foregrounded, silently broken from background."
5. **Core Data / SQLite stores.** The store file takes a protection class (via store options/`NSPersistentStoreFileProtectionKey`); with WAL mode the `-wal` and `-shm` siblings must carry compatible classes or writes break at lock. Treat the whole store as the classification unit.
6. **Migration mechanics.** Upgrading classes on first launch after adoption: enumerate the classified directory trees, `setAttributes` per file, and re-run on each launch for new stragglers until the count is zero, then keep the write-time options in place permanently. Log the counts — a persistent non-zero migration count after N launches indicates an unclassified write path still alive.

Semantics that trip implementations:

- **First unlock after boot.** Between reboot and first unlock, *all* classes except `None` are sealed (the keystore isn't unwrapped). After first unlock, `CompleteUntilFirstUserAuthentication` files stay available even after re-lock; `Complete` files seal again at next lock. Code that assumes "locked means nothing works" or "unlocked once means everything works" is wrong in both directions.
- **Complete ≠ self-destruct.** Protection classes constrain access, not persistence: after the user unlocks, `Complete` files are fully available to the app. Data elimination is a different feature (`encryptor`/`FileProtection` do not wipe; deletion and key-destruction semantics are separate APIs).
- **Backups.** Protection classes do not survive into backups as protection: unencrypted computer backups (opt-in, deprecated path) and iCloud backups store decrypted content under their own encryption. Threat-model accordingly: on-device-at-rest is what these classes address.

A worked example: a notes app storing notes in per-note files plus a search index. Classification: note files `Complete` (read only in UI, never from background); search index rebuilt-on-open, classified default (`CompleteUntilFirstUserAuthentication`) so a background re-index task after first-unlock keeps working; an in-flight audio-memo recording opened unlocked uses `CompleteUnlessOpen` so locking mid-recording doesn't truncate the memo. A first-launch migration walks the documents directory upgrading note files created before adoption, logging counts to telemetry until zero.

## Controls

- File inventory with classification per store: every persistent path carries a documented protection class and a justification tied to its access windows; new files require the inventory entry in review.
- Write-time options are the default in shared file-IO helpers (one code path applies classes); direct `FileManager` writes that skip the helper are lint-flagged.
- Background-entry-point audit: for each background mode/extension, the file classes touched are listed and compatible; the audit reruns when a new background capability is added.
- Migration telemetry: per-launch upgrade counts until steady zero; non-zero after a stable window pages the owning team (an unclassified writer survived).
- Test matrix includes lock-state behavior: unit/integration tests (or manual protocol) verifying `Complete` files fail reads while locked and succeed unlocked, and `CompleteUnlessOpen` streams survive lock-while-open — the semantics proven in your actual configuration, not assumed from documentation.

## Validation evidence

- The four `NSFileProtection…` classes, their lock/boot semantics (including the first-unlock-after-boot behavior), `FileProtectionType` write options, the `.protectionKey` file attribute, `NSPersistentStoreFileProtectionKey` for Core Data, and the system default class are specified in Apple's Foundation documentation (FileManager, FileProtectionType) and the App Encryption Export Compliance / data-protection documentation on developer.apple.com.
- The hardware key architecture underlying the classes (SEP-wrapped keys, effaceable storage) is described in Apple Platform Security, the platform's security architecture publication.
- A reproducible on-device check: write a file with `.complete` protection; lock the device; from a locked-background-capable path (or an MDM/console-triggered locked state) attempt a read and observe failure; unlock and observe success — the class contract validated against the running system, and a lock-while-open stream written with `.completeUnlessOpen` observed completing across the lock boundary.

## Failure modes and correction

- **Background read failures after class upgrade.** Symptom: widgets/notifications/extensions silently fail or crash while locked. Correct by reclassifying the touched files to match access windows (and the background audit control preventing recurrence).
- **SQLite WAL corruption at lock.** Symptom: store errors exactly at lock transitions. Correct by setting the store protection option (which covers sidecar files) rather than patching file-by-file.
- **Migration never converges.** Symptom: upgrade counts never reach zero. Correct by finding the unclassified writer (helper-path lint) — the count telemetry exists for this.
- **Assuming Complete survives into backups.** Symptom: sensitive data readable from unencrypted computer backups. Correct by backup-policy alignment (the class governs on-device at rest only).
- **Directory-level expectation.** Symptom: files created later unprotected. Correct by write-time classes in the single IO helper.

## Limitations

- Protection classes constrain access by lock state; they do not encrypt against a user-unlocked device (post-unlock malware with the app's sandbox sees plaintext).
- Backups, iCloud sync, and app extensions each transport data under their own protection regimes — classes govern the local file only.
- Long-running open handles (`CompleteUnlessOpen`) remain writable across lock by design; the pattern is for streams that finish, not databases.
- Behavior verification on locked devices is operationally awkward (needs MDM/console or background paths), so the test matrix is partly manual protocol.

## Canonical sources

- Apple, FileProtectionType and FileManager attributes (protection classes, write options): https://developer.apple.com/documentation/foundation/fileprotectiontype
- Apple, NSFileProtectionType complete-class semantics and data protection overview (App Support documentation): https://developer.apple.com/documentation/foundation/nsfileprotectiontype
