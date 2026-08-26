# TLS Certificate Expiry Caused Outage

## Symptom

A critical production service experienced unexpected downtime when its TLS certificate expired, causing all HTTPS connections to fail. The outage lasted approximately 30 minutes while the team manually replaced the certificate and restarted services. Users reported connection timeouts and "SSL handshake failed" errors across multiple applications using the affected certificate.

## Gotchas

- **Manual certificate management** creates human error opportunities and delays
- **No automated renewal** means certificates must be manually tracked and renewed
- **ACME protocol failures** can prevent automatic certificate issuance from Let's Encrypt or other CAs
- **Insufficient alerting** meant the team only discovered the issue when users reported it
- **Certificate rotation** without proper testing caused unexpected service disruption
- **Missing certificate expiration monitoring** allowed the issue to go unnoticed until failure

## Practical Solutions

Implement automated certificate monitoring using tools like `certbot`, `acme-tiny`, or commercial solutions. Set up alerts for certificates expiring within 30, 7, and 1 day. Configure automatic renewal with proper rollback mechanisms. Test certificate rotation procedures in staging environments before production deployment. Monitor certificate chains and intermediate certificates, not just root certificates. Use centralized certificate management systems to track all certificates across services.

## Prevention

Deploy certificate monitoring solutions that integrate with your existing alerting infrastructure. Establish automated workflows for certificate renewal that include pre-flight checks and rollback procedures. Implement certificate lifecycle management policies including regular inventory audits. Configure service health checks that monitor certificate validity. Train operations teams on certificate management best practices. Regularly test disaster recovery procedures including certificate replacement scenarios.

## Key Takeaways

Automated certificate management prevents human error and reduces downtime risk. Proactive monitoring identifies issues before they cause outages. Testing rotation procedures ensures smooth transitions during certificate updates. Proper alerting enables rapid response to certificate-related issues. Centralized certificate management provides visibility across all services and applications.
