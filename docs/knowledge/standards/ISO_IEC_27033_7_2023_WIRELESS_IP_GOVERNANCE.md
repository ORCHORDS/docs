# ISO/IEC 27033-7:2023 Network Security — Wireless IP Network Security Governance

## 1. Scope

This card governs ORCHORDS adoption of ISO/IEC 27033-7:2023 ("Information technology — Security techniques — Network security — Part 7: Guidelines for network security of wireless IP network access") for enterprise Wi-Fi, private 5G, satellite IP, and other wireless IP-based access networks operated by ORCHORDS.

## 2. Normative references

- ISO/IEC 27033-7:2023 (second edition).
- ISO/IEC 27033-1:2015 — Network security overview and concepts.
- IEEE 802.11ax/be (Wi-Fi 6/7) and IEEE 802.1X-2020.
- 3GPP TS 33.501 (5G security architecture).
- NIST SP 800-153 (Guidelines for Securing Wireless Local Area Networks).

## 3. Wireless IP network design principles

1. **Perimeter**: every wireless IP network is treated as an untrusted network; traffic enters the trusted zone only via an authenticated, encrypted tunnel.
2. **Authentication**: 802.1X with EAP-TLS or EAP-TTLS for Wi-Fi; SUCI/SUPI concealment for 5G.
3. **Encryption**: WPA3-Enterprise (GCMP-256) for Wi-Fi; NIA1/NIA2 integrity and NEA1/NEA2 ciphering for 5G.
4. **Segmentation**: separate VLAN/SSID/Broadcast-Domain for guest, IoT, corporate, and OT/ICS traffic.
5. **Detection**: WIDS/WIPS deployment with rogue AP detection and containment.

## 4. Control families

| Family | Controls | ORCHORDS implementation |
| --- | --- | --- |
| Planning | Inventory of APs, controllers, RF site surveys | Asset register; quarterly RF audit |
| Authentication | 802.1X, EAP-TLS with PKI | Internal CA, short-lived client certs |
| Encryption | WPA3-Enterprise, GCMP-256 | Disabled on all pre-WPA3 hardware |
| Integrity | Management frame protection (802.11w) | Required on every SSID |
| Monitoring | WIDS, RF spectrum, RADIUS accounting | 24×7 SOC alerting |
| Incident response | Rogue AP, evil-twin, deauth attack | Runbook in `playbooks/wireless-incident` |

## 5. Private 5G / satellite IP

- 5G NRF/NEF exposed to the corporate zone only through an SEPP (Security Edge Protection Proxy).
- UPF selection governed by UE subscription; UDM/UDR isolated in a dedicated slice.
- Satellite IP links terminated in a dedicated edge appliance with FIPS-validated encryption.

## 6. Audit and monitoring

- Daily WIDS report summarising rogue AP detections and channel utilization.
- Monthly RADIUS server audit for stale accounts and shared secrets.
- Quarterly RF survey to detect unauthorized APs and coverage drift.

## 7. Exceptions

- Legacy Wi-Fi (802.11n and earlier) devices must be replaced or quarantined within 12 months of this card's effective date.
- Documented in `policies/exceptions/wireless/<device-id>.md`.

## 8. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-06. ISO/IEC 27033 revisions and major wireless-protocol releases (Wi-Fi 8, 6G) trigger out-of-cycle updates.
