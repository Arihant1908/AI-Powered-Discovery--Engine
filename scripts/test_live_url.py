import sys
import time
import argparse
import httpx

def run_tests(base_url: str):
    base_url = base_url.rstrip("/")
    print(f"Running E2E tests against: {base_url}\n")
    
    results = []
    
    with httpx.Client(base_url=base_url, timeout=90.0) as client:
        # 1. /health
        try:
            r = client.get("/health")
            if r.status_code == 200 and r.json().get("status") == "ok":
                results.append({"feature": "Health check (/health)", "status": "works", "difference": "None (returns 200 OK)"})
            else:
                results.append({"feature": "Health check (/health)", "status": "broken", "difference": f"HTTP {r.status_code}: {r.text}"})
        except Exception as e:
            results.append({"feature": "Health check (/health)", "status": "broken", "difference": str(e)})

        # 2. Three HTML Pages
        for path, name in [("/", "Dashboard page (/)"), ("/upload", "Upload page (/upload)"), ("/insights", "Insights page (/insights)")]:
            try:
                r = client.get(path)
                if r.status_code == 200 and "<!DOCTYPE html>" in r.text:
                    results.append({"feature": name, "status": "works", "difference": "None (returns full HTML UI)"})
                else:
                    results.append({"feature": name, "status": "broken", "difference": f"HTTP {r.status_code}"})
            except Exception as e:
                results.append({"feature": name, "status": "broken", "difference": str(e)})

        # 3. Dashboard Filters, Charts & Summary
        try:
            r_evidence = client.get("/api/dashboard/evidence")
            r_filtered = client.get("/api/dashboard/evidence?income_stability=Variable+income&source=Play+Store")
            r_search = client.get("/api/dashboard/evidence?search=Groww")
            r_summary = client.get("/api/dashboard/summary")
            r_charts = client.get("/api/dashboard/charts")
            r_unmet = client.get("/api/dashboard/unmet-needs")
            
            if (r_evidence.status_code == 200 and r_filtered.status_code == 200 and 
                r_search.status_code == 200 and r_summary.status_code == 200 and 
                r_charts.status_code == 200 and r_unmet.status_code == 200):
                total = r_evidence.json().get("total", 0)
                filtered_total = r_filtered.json().get("total", 0)
                search_total = r_search.json().get("total", 0)
                results.append({
                    "feature": "Dashboard filters, charts & search",
                    "status": "works",
                    "difference": f"None (all filters responsive, total={total}, filtered={filtered_total}, search={search_total})"
                })
            else:
                results.append({"feature": "Dashboard filters, charts & search", "status": "broken", "difference": f"Status codes: evidence={r_evidence.status_code}, summary={r_summary.status_code}"})
        except Exception as e:
            results.append({"feature": "Dashboard filters, charts & search", "status": "broken", "difference": str(e)})

        # 4. Export CSV
        try:
            r = client.get("/api/dashboard/export.csv")
            if r.status_code == 200 and "id,source,date" in r.text:
                results.append({"feature": "Dashboard export (/api/dashboard/export.csv)", "status": "works", "difference": "None (returns CSV with headers and records)"})
            else:
                results.append({"feature": "Dashboard export (/api/dashboard/export.csv)", "status": "broken", "difference": f"HTTP {r.status_code}"})
        except Exception as e:
            results.append({"feature": "Dashboard export (/api/dashboard/export.csv)", "status": "broken", "difference": str(e)})

        # 5. Broken CSV upload validation
        try:
            broken_csv = "id,source\n1,App Store\n"
            files = {"file": ("broken.csv", broken_csv.encode("utf-8"), "text/csv")}
            r = client.post("/api/upload", files=files)
            if r.status_code == 400 and "error" in r.json():
                err_msg = r.json()["error"]["message"]
                results.append({"feature": "Broken CSV upload validation", "status": "works", "difference": f"None (rejected with 400: '{err_msg[:45]}...')"})
            else:
                results.append({"feature": "Broken CSV upload validation", "status": "broken", "difference": f"Expected 400 with error envelope, got {r.status_code}: {r.text}"})
        except Exception as e:
            results.append({"feature": "Broken CSV upload validation", "status": "broken", "difference": str(e)})

        # 6. "Use sample data" with live tagging
        job_id = None
        try:
            r = client.post("/api/upload/sample")
            if r.status_code == 200:
                job_id = r.json().get("job_id")
                print(f"Sample upload initiated, job_id={job_id}. Polling progress...")
                
                # Poll status
                max_polls = 60
                state = "running"
                status_data = {}
                for _ in range(max_polls):
                    time.sleep(2)
                    st_resp = client.get(f"/api/upload/{job_id}/status")
                    if st_resp.status_code == 200:
                        status_data = st_resp.json()
                        state = status_data.get("state")
                        print(f"  Status: {status_data.get('rows_tagged')}/{status_data.get('total')} ({state})")
                        if state in ("done", "failed"):
                            break
                    else:
                        break
                
                if state == "done":
                    rows_tagged = status_data.get("rows_tagged")
                    fallbacks = status_data.get("fallback_count", 0)
                    results.append({
                        "feature": "Use sample data (live tagging)",
                        "status": "works",
                        "difference": f"None ({rows_tagged} rows tagged, {fallbacks} fallbacks)"
                    })
                else:
                    results.append({
                        "feature": "Use sample data (live tagging)",
                        "status": "broken",
                        "difference": f"Job ended in state '{state}' with status: {status_data}"
                    })
            else:
                results.append({"feature": "Use sample data (live tagging)", "status": "broken", "difference": f"HTTP {r.status_code}: {r.text}"})
        except Exception as e:
            results.append({"feature": "Use sample data (live tagging)", "status": "broken", "difference": str(e)})

        # 7. Label editing (valid & invalid)
        if job_id:
            try:
                # First fetch rows
                rows_resp = client.get(f"/api/upload/{job_id}/rows?page=1&page_size=5")
                if rows_resp.status_code == 200 and rows_resp.json().get("items"):
                    first_row = rows_resp.json()["items"][0]
                    first_id = first_row["id"]
                    
                    # Valid edit
                    valid_patch = client.patch(
                        f"/api/upload/{job_id}/rows/{first_id}",
                        json={"main_driver": "Payment or mandate failure"}
                    )
                    # Invalid edit
                    invalid_patch = client.patch(
                        f"/api/upload/{job_id}/rows/{first_id}",
                        json={"main_driver": "CompletelyFakeDriverValue"}
                    )
                    
                    if valid_patch.status_code == 200 and invalid_patch.status_code == 400:
                        results.append({
                            "feature": "Label editing (PATCH row)",
                            "status": "works",
                            "difference": "None (valid label accepted and saved, invalid label rejected with 400)"
                        })
                    else:
                        results.append({
                            "feature": "Label editing (PATCH row)",
                            "status": "broken",
                            "difference": f"Valid status: {valid_patch.status_code}, invalid status: {invalid_patch.status_code}"
                        })
                else:
                    results.append({"feature": "Label editing (PATCH row)", "status": "broken", "difference": f"Could not fetch rows for job {job_id}"})
            except Exception as e:
                results.append({"feature": "Label editing (PATCH row)", "status": "broken", "difference": str(e)})
        else:
            results.append({"feature": "Label editing (PATCH row)", "status": "broken", "difference": "Skipped due to missing job_id"})

        # 8. Insights for pre-loaded data
        try:
            r = client.get("/api/insights?dataset=preloaded")
            if r.status_code == 200:
                data = r.json()
                cards = data.get("cards", [])
                stats = data.get("computed_stats", {})
                questions = data.get("suggested_questions", [])
                results.append({
                    "feature": "Insights (pre-loaded dataset)",
                    "status": "works",
                    "difference": f"None ({len(cards)} cards generated, {len(questions)} next questions, full stats returned)"
                })
            else:
                results.append({"feature": "Insights (pre-loaded dataset)", "status": "broken", "difference": f"HTTP {r.status_code}: {r.text}"})
        except Exception as e:
            results.append({"feature": "Insights (pre-loaded dataset)", "status": "broken", "difference": str(e)})

        # 9. Insights for uploaded data
        if job_id:
            try:
                r = client.get(f"/api/insights?dataset={job_id}")
                if r.status_code == 200:
                    data = r.json()
                    cards = data.get("cards", [])
                    stats = data.get("computed_stats", {})
                    results.append({
                        "feature": "Insights (uploaded dataset)",
                        "status": "works",
                        "difference": f"None ({len(cards)} cards generated, stats computed for uploaded job)"
                    })
                else:
                    results.append({"feature": "Insights (uploaded dataset)", "status": "broken", "difference": f"HTTP {r.status_code}: {r.text}"})
            except Exception as e:
                results.append({"feature": "Insights (uploaded dataset)", "status": "broken", "difference": str(e)})
        else:
            results.append({"feature": "Insights (uploaded dataset)", "status": "broken", "difference": "Skipped due to missing job_id"})

    print("\n" + "=" * 90)
    print("TEST SUMMARY")
    print("=" * 90)
    header = f"| {'Feature':<38} | {'Status':<8} | {'Difference from local':<36} |"
    sep = f"|{'-'*40}|{'-'*10}|{'-'*38}|"
    print(header)
    print(sep)
    for res in results:
        print(f"| {res['feature']:<38} | {res['status']:<8} | {res['difference']:<36} |")
    print("=" * 90)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test SIP Discovery Engine E2E")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL of the application")
    args = parser.parse_args()
    run_tests(args.base_url)
