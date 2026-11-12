# Cloud SQL connection saturation runbook
Service: patient-portal-api on Cloud Run, Cloud SQL PostgreSQL instance appointments-db.
1. If portal latency rises together with database wait time, compare active connections against the instance connection limit in Cloud SQL Insights.
2. If active connections exceed 80 percent of the limit, tune the application connection pool and enable the Cloud SQL connector's connection pooling before adding database capacity.
3. Inspect for long-running queries and missing indexes on appointment-search.
4. Restarting the database is the last resort; connection exhaustion is usually an application leak and a restart only hides the cause.
Escalate to Sev2 if p95 latency stays above 1.5 seconds for 30 minutes.
