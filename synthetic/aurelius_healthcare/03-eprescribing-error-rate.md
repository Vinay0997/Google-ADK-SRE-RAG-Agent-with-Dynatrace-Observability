# E-prescribing service elevated 5xx runbook
Service: eprescribing-svc on Cloud Run. It calls the fictional partner network RxLink.
1. Split 5xx errors by upstream: our code, RxLink timeouts, or database errors.
2. If RxLink timeouts dominate, check the partner status page and enable the retry queue with a maximum of 3 retries.
3. Do not drop prescriptions. Failed submissions must stay in the dead-letter topic until a pharmacist reviews them.
4. If the error rate exceeds 5 percent for 10 minutes, declare Sev2 and notify the clinical operations lead.
