-- Add the existing RAG-quality runbook without modifying existing documents.
-- Intended demo permission: sre only.

CREATE TEMP TABLE generated_runbook AS
SELECT *
FROM AI.GENERATE_EMBEDDING(
  MODEL `adk-dynatrace-observability.agent_observability.embedding_model`,
  (
    SELECT
      "rag-quality" AS doc_id,
      "RAG Quality Degradation" AS title,
      "When RAG quality degrades, separate retrieval quality from generation quality. Record the user question, retrieved document identifiers and relevance scores, and final answer while avoiding sensitive content. Evaluate groundedness/faithfulness, answer relevance, context precision or retrieval quality, and hallucination risk. Use a golden dataset for regression tests and sampled production evaluations for live quality trends." AS content,
      'sre-runbook' AS category,
      'knowledge/runbooks.json#rag-quality' AS source,
      ['sre'] AS allowed_roles
  ),
  STRUCT(
    'RETRIEVAL_DOCUMENT' AS task_type,
    768 AS output_dimensionality
  )
);

ASSERT (
  SELECT COUNT(*) = 1
  FROM generated_runbook
  WHERE status = ''
    AND ARRAY_LENGTH(embedding) = 768
) AS 'Embedding generation failed or returned unexpected dimensions';

MERGE `adk-dynatrace-observability.agent_observability.runbook_chunks` AS target
USING generated_runbook AS incoming
ON target.doc_id = incoming.doc_id
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
WHERE doc_id = 'rag-quality';
