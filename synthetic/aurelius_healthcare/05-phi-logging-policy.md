# PHI in logs and telemetry policy
Logs, traces and metrics must never contain patient names, dates of birth, medical record numbers or free-text clinical notes.
Use opaque internal IDs only. Telemetry attributes are reviewed in code review.
If PHI is found in logs: 1) declare a security incident, 2) restrict access to the affected log bucket, 3) notify the privacy officer within 24 hours, 4) fix the code path, 5) purge affected entries under the privacy officer's guidance.
