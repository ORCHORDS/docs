# CSRF Protection Boundaries

Identify state-changing browser requests that depend on ambient credentials and require anti-CSRF defenses appropriate to the architecture. Combine token or origin-based defenses with safe cookie attributes and avoid using GET for state changes.

Sources: OWASP Cross-Site Request Forgery Prevention Cheat Sheet.