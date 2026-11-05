from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_serve_dashboard_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "SIP Discovery Engine" in html
    assert 'href="/upload"' in html
    assert 'href="/insights"' in html
    assert "Export (.csv)" in html

    # Rule 1 verification: no hardcoded Stitch placeholder records or IDs
    assert "ID-00101" not in html
    assert "ID-00102" not in html
    assert "ID-00103" not in html
    assert "Share report" not in html
    assert "Mark for action" not in html

def test_serve_upload_page():
    response = client.get("/upload")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "SIP Discovery Engine" in html
    assert "Upload Data" in html or "Upload Investor Feedback" in html
    assert 'href="/"' in html
    assert 'href="/insights"' in html
    assert 'id="dropZone"' in html
    assert 'id="fileUploadInput"' in html
    assert 'id="btnSampleData"' in html
    assert 'href="/api/template.csv"' in html
    assert 'id="btnViewInsights"' in html
    assert 'src="/static/upload.js"' in html

    # Rule 1 verification: no hardcoded Stitch placeholder records or IDs
    assert "ID-00101" not in html
    assert "ID-00102" not in html
    assert "ID-00103" not in html
    assert "SIP auto-debit bounced because salary" not in html

def test_serve_insights_page():
    response = client.get("/insights")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "SIP Discovery Engine" in html
    assert "AI insight summary" in html
    assert 'href="/"' in html
    assert 'href="/upload"' in html
    assert 'id="btnRegenerate"' in html
    assert 'id="cardsContainer"' in html
    assert 'id="nextQuestionsSection"' in html
    assert 'id="segmentViewContainer"' in html
    assert 'id="evidenceModal"' in html
    assert "Small sample. Treat as patterns, not proof." in html
    assert 'src="/static/insights.js"' in html

    # Rule 1 verification: no hardcoded Stitch placeholder records or IDs
    assert "ID-00101" not in html
    assert "ID-00201" not in html
    assert "ID-00301" not in html
    assert "Variable-income investors cancel instead of pausing" not in html

def test_static_files():
    resp_app_js = client.get("/static/app.js")
    assert resp_app_js.status_code == 200

    resp_api_js = client.get("/static/api.js")
    assert resp_api_js.status_code == 200

    resp_upload_js = client.get("/static/upload.js")
    assert resp_upload_js.status_code == 200

    resp_insights_js = client.get("/static/insights.js")
    assert resp_insights_js.status_code == 200

