# OpenSSH Host-Key Rotation with UpdateHostKeys

**Issue:** Replacing an SSH host key without a trust-overlap period can cause outages or train operators to bypass host verification.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Publish old and new host keys together before retiring the old key.
- Use the OpenSSH hostkeys protocol and UpdateHostKeys only after the server was authenticated by an already trusted key.
- Maintain an out-of-band fingerprint channel for high-risk systems and emergency recovery.
- Remove the retired key only after clients have had sufficient opportunity to learn the replacement.

## Verification

- Connect with a client holding only the old key and confirm the new key is learned.
- Retire the old server key and confirm reconnection succeeds without an interactive trust bypass.
- Present an unexpected key from an untrusted server and confirm it is not learned.

## Gotchas

- UpdateHostKeys behavior depends on client configuration and known-hosts location.
- DNS host-key verification and host certificates have different rotation mechanics.

## Official sources

- https://man.openbsd.org/ssh_config#UpdateHostKeys
- https://man.openbsd.org/sshd_config#HostKey
