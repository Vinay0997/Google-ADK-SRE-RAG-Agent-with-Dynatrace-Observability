# Postmortem: claims-engine outage (fictional, Sev2)
Summary: claims submissions failed for 47 minutes after a config change.
Impact: about 3,200 claims delayed, no data lost.
Root cause: a new batch-size setting of 5000 exhausted memory, causing repeated OOM kills in claims-engine.
Detection: queue age alert fired after 12 minutes. Latency alerts did not fire because requests never completed.
Fix: reverted the setting and added a memory-based alert.
Actions: add config validation in CI, add a canary rollout for claims-engine, add a dashboard for queue age.
