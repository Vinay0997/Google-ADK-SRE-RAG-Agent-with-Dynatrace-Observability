# OpenTelemetry Collector export backlog runbook
Scope: OpenTelemetry Collector deployment otel-collector in namespace observability.
1. When Dynatrace shows missing or delayed spans, check collector export queue depth and exporter send failures before assuming an application problem.
2. If the export queue is full the collector drops telemetry; separate receiver input rate from exporter send latency.
3. Scale collector replicas and raise the exporter batch timeout before considering any sampling change.
4. Changing trace sampling is a data-quality decision, not a capacity fix; require incident commander approval before reducing sampling during an active incident.
