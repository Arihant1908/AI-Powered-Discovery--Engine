import httpx

slugs = [
    "ai-powered-discovery-engine",
    "ai-powered-discovery--engine",
    "sip-discovery-engine",
    "sip-discovery",
    "sip-engine",
    "sip-engine-discovery",
    "ai-powered-discovery-engine-service",
    "ai-discovery-engine",
    "arihant-sip-engine",
    "arihant-sip",
    "ai-powered-discovery-engine-web",
    "sip-discovery-engine-web",
    "ai-powered-discovery",
    "discovery-engine-sip",
    "engine-dataset",
    "sip-analyser",
    "sip-engine-live"
]

for s in slugs:
    url = f"https://{s}.onrender.com"
    try:
        r = httpx.get(f"{url}/health", timeout=4.0)
        print(f"{url} -> HTTP {r.status_code}")
    except httpx.ConnectTimeout:
        pass
    except httpx.ReadTimeout:
        print(f"{url} -> ReadTimeout (spinning up)")
    except Exception as e:
        pass

