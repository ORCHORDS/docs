# IPv6 Email Deliverability Guide

## Symptom

Emails sent from IPv6-enabled servers may experience deliverability issues, including being marked as spam, rejected by recipients, or failing to reach their destination. Common symptoms include delivery failures, spam folder placement, and increased bounce rates when transitioning from IPv4 to IPv6.

## Gotchas

Several critical factors can prevent successful IPv6 email delivery:
- Missing AAAA records in DNS configuration
- Incorrect PTR/rDNS setup for IPv6 addresses
- DMARC policy misalignment with IPv6 configurations
- Postfix/Dovecot not properly handling IPv6 connections
- ISP restrictions like Comcast blocking IPv6 email traffic
- Gmail's specific IPv6 requirements and validation processes

## AAAA Records Configuration

AAAA records are essential for IPv6 email deliverability. They map domain names to IPv6 addresses. Without proper AAAA records, receiving servers cannot verify your IPv6 connectivity.

```bash
# Add AAAA record in DNS zone file
example.com.  IN  AAAA  2001:db8::1

# Verify AAAA record resolution
dig AAAA example.com
```

## PTR/rDNS for IPv6

Reverse DNS (rDNS) is crucial for email deliverability. For IPv6, you must configure PTR records that map IP addresses back to domain names.

```bash
# Configure reverse DNS zone file
0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.IN-ADDR.ARPA.  IN  PTR  mail.example.com.

# Verify rDNS resolution
dig -x 2001:db8::1
```

## DMARC Alignment

DMARC alignment ensures that your email authentication aligns with your domain configuration. IPv6 addresses must be properly included in SPF records and DKIM signatures.

```bash
# SPF record including IPv6 addresses
example.com.  IN  TXT  "v=spf1 ip6:2001:db8::1 include:_spf.example.com ~all"

# DMARC policy
_dmarc.example.com.  IN  TXT  "v=DMARC1; p=quarantine; rua=mailto:dmar
