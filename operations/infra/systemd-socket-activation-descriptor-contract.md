# systemd socket-activation descriptor contract

**Issue:** A daemon that opens its own listener or assumes a fixed descriptor can race systemd, bind twice, or accept traffic on the wrong socket after activation.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Define the `.socket` and `.service` units as one interface. In the daemon, consume activation descriptors through the systemd library APIs where possible, validate `LISTEN_PID`, count and identify all descriptors, and use `LISTEN_FDNAMES` rather than relying only on order when multiple sockets exist. Close unknown descriptors and unset the activation environment after parsing so child processes cannot misinterpret it.

Choose `Accept=no` when the service owns the listening socket and accepts connections, or `Accept=yes` only for a reviewed per-connection service model. Align socket type, address, permissions, backlog, and shutdown behavior with the application's protocol. Test the implementation with `systemd-socket-activate` before enabling boot-time demand activation.

## Verification

Test zero, one, multiple, reordered, renamed, and unexpected descriptors; stream/datagram types; IPv4/IPv6; service restart while the socket stays active; descriptor inheritance; and graceful shutdown under queued traffic. Assert there is one listener owner and no port-binding fallback that bypasses policy.

## Gotchas

- Activation descriptors normally begin at file descriptor 3, but code should use the documented API contract.
- Socket activation changes readiness and restart timing.
- `Accept=yes` can create an unbounded per-connection process load without service limits.

## Official sources

- [systemd.socket](https://www.freedesktop.org/software/systemd/man/latest/systemd.socket.html)
- [sd_listen_fds](https://www.freedesktop.org/software/systemd/man/latest/sd_listen_fds.html)
- [systemd-socket-activate](https://www.freedesktop.org/software/systemd/man/latest/systemd-socket-activate.html)
