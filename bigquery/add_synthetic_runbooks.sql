-- Seed the four additional Aurelius synthetic runbooks (aur-09..aur-12) into
-- the BigQuery vector index without modifying existing documents.
-- Source of truth: synthetic/aurelius_runbooks.jsonl (identical content).
-- Idempotent: MERGE on doc_id, so rerunning updates rather than duplicating.

CREATE TEMP TABLE generated_runbooks AS
SELECT *
FROM AI.GENERATE_EMBEDDING(
  MODEL `adk-dynatrace-observability.agent_observability.embedding_model`,
  (
    SELECT
      "aur-09" AS doc_id,
      "Cloud SQL connection saturation runbook" AS title,
      "Service: patient-portal-api on Cloud Run, Cloud SQL PostgreSQL instance appointments-db. 1. If portal latency rises together with database wait time, compare active connections against the instance connection limit in Cloud SQL Insights. 2. If active connections exceed 80 percent of the limit, tune the application connection pool and enable the Cloud SQL connector's connection pooling before adding database capacity. 3. Inspect for long-running queries and missing indexes on appointment-search. 4. Restarting the database is the last resort; connection exhaustion is usually an application leak and a restart only hides the cause. Escalate to Sev2 if p95 latency stays above 1.5 seconds for 30 minutes." AS content,
      'cloud-sql-connection-saturation' AS category,
      'synthetic/aurelius_runbooks.jsonl#aur-09' AS source,
      ['sre', 'clinical_ops'] AS allowed_roles
    UNION ALL
    SELECT
      "aur-10",
      "FHIR gateway TLS certificate renewal runbook",
      "Service: fhir-gateway on GKE namespace clinical-api, TLS terminated at the gateway with certificates managed by cert-manager. 1. When clients report certificate errors, check certificate readiness conditions and the ACME order status in cert-manager. 2. If a renewal is stuck in a pending challenge, verify the DNS-01 or HTTP-01 challenge provider and ingress exposure. 3. If the certificate already expired, issue a short-lived manual certificate only to restore service, then fix automated renewal the same day. 4. Never disable certificate validation on clients to work around an expired server certificate. Treat as Sev3 while the gateway is reachable, Sev2 when it is not.",
      'tls-certificate-renewal',
      'synthetic/aurelius_runbooks.jsonl#aur-10',
      ['sre']
    UNION ALL
    SELECT
      "aur-11",
      "OpenTelemetry Collector export backlog runbook",
      "Scope: OpenTelemetry Collector deployment otel-collector in namespace observability. 1. When Dynatrace shows missing or delayed spans, check collector export queue depth and exporter send failures before assuming an application problem. 2. If the export queue is full the collector drops telemetry; separate receiver input rate from exporter send latency. 3. Scale collector replicas and raise the exporter batch timeout before considering any sampling change. 4. Changing trace sampling is a data-quality decision, not a capacity fix; require incident commander approval before reducing sampling during an active incident.",
      'otel-collector-backlog',
      'synthetic/aurelius_runbooks.jsonl#aur-11',
      ['sre', 'security_privacy']
    UNION ALL
    SELECT
      "aur-12",
      "GKE node pool upgrade disruption runbook",
      "Scope: GKE node pool upgrades for cluster aurelius-prod. 1. Before an upgrade, confirm PodDisruptionBudgets allow the planned upgrade concurrency and that each clinical service has at least one replica outside the upgraded pool. 2. During the upgrade, watch pod eviction counts; restart a stalled surge upgrade rather than forcing node deletion. 3. If a clinical service drops below its minimum availability, pause the upgrade and roll remaining nodes in smaller batches. 4. Never drain a node running the only replica of eprescribing-svc or lab-results-worker; defer that node until another replica is ready.",
      'gke-node-upgrade-disruption',
      'synthetic/aurelius_runbooks.jsonl#aur-12',
      ['sre', 'clinical_ops']
  ),
  STRUCT(
    'RETRIEVAL_DOCUMENT' AS task_type,
    768 AS output_dimensionality
  )
);

ASSERT (
  SELECT COUNT(*) = 4
  FROM generated_runbooks
  WHERE status = ''
    AND ARRAY_LENGTH(embedding) = 768
) AS 'Embedding generation failed or returned unexpected dimensions';

MERGE `adk-dynatrace-observability.agent_observability.runbook_chunks` AS target
USING generated_runbooks AS incoming
ON target.doc_id = incoming.doc_id
WHEN MATCHED THEN
  UPDATE SET
    embedding = incoming.embedding,
    statistics = incoming.statistics,
    status = incoming.status,
    title = incoming.title,
    content = incoming.content,
    category = incoming.category,
    source = incoming.source,
    allowed_roles = incoming.allowed_roles
WHEN NOT MATCHED THEN
  INSERT (
    embedding, statistics, status, doc_id, title,
    content, category, source, allowed_roles
  )
  VALUES (
    incoming.embedding, incoming.statistics, incoming.status,
    incoming.doc_id, incoming.title, incoming.content,
    incoming.category, incoming.source, incoming.allowed_roles
  );

SELECT
  doc_id,
  title,
  allowed_roles,
  ARRAY_LENGTH(embedding) AS embedding_dimensions,
  status
FROM `adk-dynatrace-observability.agent_observability.runbook_chunks`
WHERE doc_id IN ('aur-09', 'aur-10', 'aur-11', 'aur-12')
ORDER BY doc_id;
