from app.rag import retrieve_runbooks


def test_cloud_run_5xx_retrieval():
    results = retrieve_runbooks("Cloud Run has 5xx errors after a new deployment", top_k=2)
    assert results
    assert results[0]["id"] == "cloud-run-5xx"
    assert 0.0 <= results[0]["score"] <= 1.0


def test_gke_crash_retrieval():
    results = retrieve_runbooks("My GKE pod is CrashLoopBackOff", top_k=2)
    assert results
    assert results[0]["id"] == "gke-crashloop"
