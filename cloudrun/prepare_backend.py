import json
import sys

source = json.load(sys.stdin)
source_spec = source["spec"]["template"]["spec"]
app = source_spec["containers"][0]

# Preserve existing application configuration, excluding telemetry overrides.
replaced = {
    "DYNATRACE_API_TOKEN",
    "DYNATRACE_OTLP_ENDPOINT",
    "OTEL_COLLECTOR_ENDPOINT",
    "OTEL_SERVICE_NAME",
    "DEPLOYMENT_ENVIRONMENT",
    "CAPTURE_PROMPTS",
}
env = [
    item for item in app.get("env", [])
    if item["name"] not in replaced
]
env.extend([
    {
        "name": "DYNATRACE_API_TOKEN",
        "valueFrom": {
            "secretKeyRef": {
                "name": "dynatrace-api-token",
                "key": "2",
            }
        },
    },
    {
        "name": "DYNATRACE_OTLP_ENDPOINT",
        "value": "https://irm77846.live.dynatrace.com/api/v2/otlp",
    },
    {
        "name": "OTEL_COLLECTOR_ENDPOINT",
        "value": "http://127.0.0.1:4318",
    },
    {"name": "OTEL_SERVICE_NAME", "value": "sre-agent-cloudrun-demo"},
    {"name": "DEPLOYMENT_ENVIRONMENT", "value": "cloud-run-demo"},
    {"name": "CAPTURE_PROMPTS", "value": "false"},
])

backend = {
    "name": "app",
    "image": app["image"],
    "ports": [{"containerPort": 8080}],
    "env": env,
    "resources": {"limits": {"cpu": "1", "memory": "512Mi"}},
    "startupProbe": {
        "tcpSocket": {"port": 8080},
        "periodSeconds": 5,
        "timeoutSeconds": 2,
        "failureThreshold": 24,
    },
}
for field in ("command", "args"):
    if field in app:
        backend[field] = app[field]

collector = {
    "name": "collector",
    "image": (
        "us-central1-docker.pkg.dev/adk-dynatrace-observability/"
        "cloud-run-source-deploy/sre-agent-otel-collector:cloudrun-v1"
    ),
    "env": [
        {
            "name": "DT_OTLP_ENDPOINT",
            "value": "https://irm77846.live.dynatrace.com/api/v2/otlp",
        },
        {
            "name": "DT_API_TOKEN",
            "valueFrom": {
                "secretKeyRef": {
                    "name": "dynatrace-api-token",
                    "key": "2",
                }
            },
        },
    ],
    "resources": {"limits": {"cpu": "1", "memory": "256Mi"}},
    "startupProbe": {
        "httpGet": {"path": "/", "port": 13133},
        "periodSeconds": 5,
        "timeoutSeconds": 2,
        "failureThreshold": 24,
    },
}

service = {
    "apiVersion": "serving.knative.dev/v1",
    "kind": "Service",
    "metadata": {
        "name": "sre-agent-cloudrun-demo",
        "labels": {"cloud.googleapis.com/location": "us-central1"},
    },
    "spec": {
        "template": {
            "metadata": {
                "annotations": {
                    "run.googleapis.com/execution-environment": "gen2",
                    "run.googleapis.com/cpu-throttling": "false",
                    "run.googleapis.com/startup-cpu-boost": "true",
                    "run.googleapis.com/container-dependencies":
                        '{"app":["collector"]}',
                    "autoscaling.knative.dev/minScale": "0",
                    "autoscaling.knative.dev/maxScale": "2",
                }
            },
            "spec": {
                "serviceAccountName": source_spec["serviceAccountName"],
                "containerConcurrency": source_spec.get(
                    "containerConcurrency", 80
                ),
                "timeoutSeconds": source_spec.get("timeoutSeconds", 300),
                "containers": [backend, collector],
            },
        }
    },
}

with open("cloudrun/backend.service.json", "w") as output:
    json.dump(service, output, indent=2)

print("Prepared new service: sre-agent-cloudrun-demo")
print("Backend image:", backend["image"])
print("Dynatrace token: Secret Manager version 2")
print("Prompt capture: disabled")
print("Minimum instances: 0; maximum instances: 2")
print("No deployment performed.")
