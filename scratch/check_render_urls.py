import httpx

urls = [
    "https://sip-discovery-engine.onrender.com",
    "https://ai-powered-discovery-engine.onrender.com",
    "https://ai-powered-discovery-engine-sip.onrender.com",
    "https://sip-engine.onrender.com"
]

for u in urls:
    try:
        r = httpx.get(f"{u}/health", timeout=5.0)
        print(f"{u}/health -> HTTP {r.status_code}")
    except Exception as e:
        print(f"{u}/health -> {e}")

