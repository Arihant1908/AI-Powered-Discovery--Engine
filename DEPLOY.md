# SIP Discovery Engine — Deployment Guide

This guide details how to deploy the **SIP Discovery Engine** to **Render** (free tier).

---

## Live URL

- **Production URL:** `[To be updated after deployment]`
- **Health Check Endpoint:** `[To be updated]/health`

---

## Production Architecture & Protections

1. **Dynamic Port Binding**:
   - The application binds to `0.0.0.0` and listens on the port dynamically assigned by Render via the `$PORT` environment variable (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`).
   - Health check path is `/health` which returns `{"status": "ok"}`.

2. **Zero Secret Leakage**:
   - `.env`, `runtime/`, and test caches are excluded via `.gitignore`.
   - The production environment injects the `GEMINI_API_KEY` securely via Render's Environment Variable Secrets.
   - Code never prints or logs API keys.

3. **Public Abuse Protection**:
   - Built-in in-memory rate limiter protects the tagging API (`POST /api/upload` and `POST /api/upload/sample`): maximum 10 upload jobs per hour per client IP address.
   - Hard cap of 500 rows and 25 MB per upload.
   - Friendly HTTP 429 response is shown to users if exceeded.

4. **Ephemeral Storage Resilience**:
   - Render's free tier uses ephemeral containers. If a container restarts or spins down after inactivity, missing upload jobs are handled gracefully.
   - The backend and frontend display a clear notification: `"This upload job has expired or the server restarted. Please upload your dataset again."` with a one-click button to upload again.

5. **Production Error Handling**:
   - FastAPI debug mode is disabled. Internal stack traces are never exposed to end-users.

---

## Step-by-Step Deployment Walkthrough

### Step 1: Create a New GitHub Repository
1. Log in to [GitHub](https://github.com/).
2. In the top-right corner, click the **`+`** icon and select **New repository**.
3. Name your repository (e.g., `sip-discovery-engine`).
4. Set visibility to **Public** or **Private** (both work with Render).
5. **Do NOT** initialize with a README, .gitignore, or license (these already exist locally).
6. Click **Create repository**.
7. Copy the repository URL (e.g., `https://github.com/<your-username>/sip-discovery-engine.git`).

---

### Step 2: Push Local Code to GitHub
Open your terminal in the project directory (`c:\Users\ariha\Desktop\sip engine`) and run:
```bash
git remote add origin https://github.com/<your-username>/sip-discovery-engine.git
git branch -M main
git push -u origin main
```

---

### Step 3: Deploy on Render
1. Sign up or log in to [Render](https://render.com/).
2. On your Render dashboard, click **New +** (top right) and select **Web Service**.
3. Connect your GitHub account and select your repository (`sip-discovery-engine`).
4. Configure the Web Service settings:
   - **Name:** `sip-discovery-engine` (or your preferred name)
   - **Region:** Choose the region closest to your users (e.g., *Singapore* or *Frankfurt*)
   - **Branch:** `main`
   - **Root Directory:** *(leave blank)*
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** `Free`
5. Expand **Advanced**:
   - **Health Check Path:** `/health`
6. Under **Environment Variables**, add:
   - `PYTHON_VERSION` = `3.11.7`
   - `GEMINI_MODEL` = `gemini-3.1-flash-lite`
   - `MOCK_LLM` = `0`
   - `GEMINI_API_KEY` = `<your-gemini-api-key>` (Mark as Secret)
7. Click **Create Web Service**.

---

### Step 4: Verification & Live Link
1. Render will build and deploy the application. Watch the deploy logs until you see:
   `Application startup complete.`
2. Visit the assigned Render URL (e.g., `https://sip-discovery-engine.onrender.com/`).
3. Verify that `/health` returns `{"status":"ok"}`.
4. Test the pre-loaded dataset on `/` (Dashboard), `/insights`, and test a sample upload on `/upload`.

