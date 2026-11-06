# Patient portal API latency runbook
Service: patient-portal-api on Cloud Run. SLO: p95 latency under 800 ms.
1. Compare p95 latency, request rate and 5xx rate for the last 60 minutes.
2. Check whether a new revision was deployed in the last 2 hours. If latency rose right after, roll traffic back to the previous revision.
3. Check cold starts: if instance count drops to zero overnight, set min-instances to 1 for business hours.
4. Check Cloud SQL connections. If active connections exceed 80 percent of the limit, scale the connection pool before adding instances.
5. Inspect traces for slow spans, usually the appointment-search query or the identity provider call.
Escalate to Sev2 if p95 stays above 2 seconds for 15 minutes.
