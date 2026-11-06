# FHIR gateway CrashLoopBackOff runbook
Service: fhir-gateway on GKE namespace clinical-api.
1. Run kubectl describe pod and read the Events section for probe failures, image pull errors or OOMKilled.
2. Read logs from the previous container with kubectl logs --previous.
3. A missing or rotated secret for the EHR vendor API key is the most common cause after a key rotation.
4. If the pod is OOMKilled, compare memory usage with the limit of 1 GiB and raise the limit one step at a time.
5. If the liveness probe fails during startup, increase initialDelaySeconds before changing application code.
Never paste patient identifiers into tickets or chat while debugging.
