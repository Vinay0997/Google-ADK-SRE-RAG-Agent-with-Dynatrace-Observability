# FHIR gateway TLS certificate renewal runbook
Service: fhir-gateway on GKE namespace clinical-api, TLS terminated at the gateway with certificates managed by cert-manager.
1. When clients report certificate errors, check certificate readiness conditions and the ACME order status in cert-manager.
2. If a renewal is stuck in a pending challenge, verify the DNS-01 or HTTP-01 challenge provider and ingress exposure.
3. If the certificate already expired, issue a short-lived manual certificate only to restore service, then fix automated renewal the same day.
4. Never disable certificate validation on clients to work around an expired server certificate.
Treat as Sev3 while the gateway is reachable, Sev2 when it is not.
