# Aurelius Healthcare (synthetic)
Fictional company used only for demos. All services, thresholds and incidents are invented. No real patient data (PHI) appears here.
Platform: patient-portal-api (Cloud Run), fhir-gateway (GKE), eprescribing-svc (Cloud Run), lab-results-worker (GKE + Pub/Sub), claims-engine (GKE), Cloud SQL for PostgreSQL, OpenTelemetry Collector (namespace observability), GKE cluster aurelius-prod.
Runbooks aur-09 through aur-12 cover Cloud SQL connection saturation, TLS certificate renewal, collector export backlog, and node pool upgrade disruption.
