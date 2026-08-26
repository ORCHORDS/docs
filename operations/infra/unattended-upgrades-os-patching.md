# unattended-upgrades-os-patching

**Issue:** Unpatched servers are the leading cause of preventable breaches — most exploited CVEs have patches available for months before incident — but manual patching does not scale past a handful of hosts, and "we'll patch during the next maintenance window" means windows slip forever. The counter-pressure is real: unattended updates have famously broken services (a PHP update disabling a module, a driver update breaking networking, an unexpected reboot at peak). The engineering problem is automating the 95 percent of updates that are safe (security origins only, staged fleets, controlled reboots) while keeping humans in the loop for the risky 5 percent (major version bumps, kernel changes on critical stateful boxes), and doing it with enough audit logging that a 3 a.m. behavior change can be traced to an actual package event.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Scoping what runs automatically

1. **Auto-apply security origins only.** Configure unattended-upgrades on Debian/Ubuntu to pull exclusively from the -security pocket, leaving -updates and -backports to scheduled manual windows. Security patches are the ones attackers reverse-engineer within days, and they are also the most narrowly targeted, which makes them the safest class to apply unattended.

2. **Explicitly exclude fragile packages.** Use the Unattended-Upgrade::Package-Blacklist for anything known to break on your fleet: pinned database versions, custom-kernel-dependent drivers, language runtimes with ABI coupling. An explicit blacklist documents institutional scar tissue in a place the next engineer will actually find it.

3. **Pin major versions, patch the point releases.** Hold major packages (PostgreSQL 16 to 17 jumps, Redis major versions) with apt-mark hold or DNF versionlock, and let point releases flow. Major upgrades are migration projects with runbooks, not patch events.

4. **Handle RPM fleets symmetrically.** Fedora/RHEL use dnf-automatic with apply_updates and installsecurity set to mirror the same policy; the tooling differs but the security-only-by-default rule should not.

5. **Decide update frequency per tier.** Edge and stateless tiers can run daily; stateful database and queue hosts should run on a slower cadence (weekly) inside a defined window, because their failure mode is hours of recovery, not minutes.

## Reboot and service-restart orchestration

1. **Let unattended-upgrades decide when a reboot is needed, but control when it happens.** Set Unattended-Upgrade::Automatic-Reboot to true with Automatic-Reboot-Time pointing at a real maintenance slot (for example 02:00) on tiers where a 30-second reboot is acceptable. On anything stateful, set Automatic-Reboot false and route the reboot-required flag into your ticketing and orchestration instead.

2. **Use needrestart or the Ubuntu livepatch stack to defer reboots.** needrestart (default on modern Debian/Ubuntu) tells you which services still hold old libraries and can restart them; Canonical Livepatch and KernelCare patch running kernels without a reboot, shrinking the vulnerable window on hosts that reboot rarely.

3. **Never let every host reboot the same night.** Stagger Automatic-Reboot-Time across availability zones or rings (day 1: one AZ; day 3: the next), or you have built a self-inflicted outage generator with perfect timing.

4. **Prefer rolling reboots through orchestration for clusters.** For anything clustered (Kubernetes nodes, database replicas, etcd members), drain, verify quorum and replica health, reboot, rejoin, then proceed — the unattended-upgrades reboot flag should trigger that pipeline, not a blind reboot timer.

## Visibility and audit logging

1. **Ship the unattended-upgrades logs and dpkg/dnf history off-host.** The log files under /var/log/unattended-upgrades/ and the dpkg.log history are the only ground truth when someone asks "what changed on this box Tuesday night." Centralize them with your existing log pipeline the day you enable the feature.

2. **Enable email or webhook failure notifications.** Unattended-Upgrade::Mail sends run reports including errors; silence on failures means you will discover the apt lock or a broken sources entry six months later via a CVE audit.

3. **Alert on reboot-required age.** A host carrying a reboot-required flag for more than N days is a patch-compliance violation, not a cosmetic warning; make it a dashboard metric with an owner.

4. **Reconcile installed versions against CVE feeds monthly.** Tools doing package-to-CVE matching (from apt list --installed through dedicated scanners) catch the case every automation scheme misses: packages excluded from auto-update that quietly accumulated critical CVEs.

## Staged rollout and safety rails

1. **Patch in rings.** Ring 0: canary hosts or a single replica per service. Ring 1 after 24 to 48 clean hours: one full tier. Ring 2: the rest of the fleet. This converts any bad update from an outage into a canary alert.

2. **Make rollback a first-class operation.** Keep previous package versions in the local apt cache or a local repository mirror so a bad update can be reverted with dpkg -i or dnf downgrade without depending on upstream availability mid-incident.

3. **Freeze windows around high-traffic events.** An updates-blackout mechanism (disabling the timer, or a config-management flag) for launch nights and peak seasons prevents the classic "the one weekend we didn't watch, the cache tier got upgraded" story.

4. **Test on golden images, not just live hosts.** Since reimaging is how fleets really get rebuilt, bake and test the patched image in CI (boot it, run smoke checks) so the next launch of any instance starts from a known-patched, known-good state rather than replaying months of updates on first boot.
