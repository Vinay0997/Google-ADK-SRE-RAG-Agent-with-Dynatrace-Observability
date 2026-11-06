# Lab results Pub/Sub backlog runbook
Service: lab-results-worker on GKE, subscription lab-results-sub.
1. Check oldest unacked message age. Target: under 5 minutes.
2. If the backlog grows while workers are healthy, scale the deployment and check the horizontal pod autoscaler metrics.
3. If many messages are redelivered, look for a poison message that fails parsing and move it to the dead-letter topic.
4. Confirm downstream FHIR writes succeed before replaying messages, to avoid duplicate lab results in patient charts.
