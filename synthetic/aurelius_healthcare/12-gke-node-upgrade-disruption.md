# GKE node pool upgrade disruption runbook
Scope: GKE node pool upgrades for cluster aurelius-prod.
1. Before an upgrade, confirm PodDisruptionBudgets allow the planned upgrade concurrency and that each clinical service has at least one replica outside the upgraded pool.
2. During the upgrade, watch pod eviction counts; restart a stalled surge upgrade rather than forcing node deletion.
3. If a clinical service drops below its minimum availability, pause the upgrade and roll remaining nodes in smaller batches.
4. Never drain a node running the only replica of eprescribing-svc or lab-results-worker; defer that node until another replica is ready.
