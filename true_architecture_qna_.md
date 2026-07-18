# OPAL MVP Reality: True Tech Stack & Defensive Q&A

Before diving into the questions, it is crucial to establish exactly what technology is actively driving the application right now. The architecture running under the hood is a rapid-prototyping MVP built for speed and UI validation, heavily relying on mocks rather than the complex infrastructure outlined in the older READMEs.

## The Actual Active Tech Stack

### Frontend Architecture
* **Framework:** Next.js (App Router, v13.5.1) with TypeScript.
* **Styling & UI:** TailwindCSS, Radix UI headless components.
* **Animations:** Framer Motion and GSAP (used simultaneously for complex micro-interactions and transitions).
* **Authentication:** Clerk Auth (Frontend UI and session token generation only).
* **State Management:** Native React state and `react-hook-form` (Zustand was removed).

### Backend Architecture
* **Framework:** Python with FastAPI & Uvicorn (`app_minimal.py`).
* **Database & State:** **None.** All state is purely ephemeral, stored in in-memory Python dictionaries (`storage = {"matters": [], "queries": [], "runs": []}`).
* **Security:** **None.** The backend blindly accepts requests without verifying the Clerk JWTs.
* **AI & Machine Learning:** **None.** The "AI" endpoints use simple string-matching heuristics (e.g., checking if the substring "pep" or "cash" exists in the input) to return hardcoded JSON responses.
* **Blockchain:** **None.** The notarization endpoints are bypassed or mocked in this minimal setup.

### Integration Layer
* **Networking:** `ngrok` is used to create a tunnel exposing the local FastAPI server directly to the frontend, bypassing standard cloud deployments or Docker networks.

---

## Defensive Q&A

Here are the hard-hitting questions an interviewer or judge might ask when looking at this specific architecture, along with robust, defensive answers you can use to justify these technical decisions.

### 1. The Disjointed Backend (FastAPI vs Next.js API Routes)
**Question:** If the backend is simply returning static JSON and doing basic string-matching heuristics from an in-memory dictionary, why spin up a separate FastAPI Python server at all? Why not just put this mock logic directly into Next.js API Routes (Serverless Functions) to eliminate the need for cross-origin setups and ngrok tunnels?

**Answer:** 
> "While building the mock directly in Next.js would have been faster on day one, we chose FastAPI to strictly enforce the API contract (via OpenAPI/Swagger) from the very beginning. By decoupling the frontend and backend entirely during the MVP phase, our teams could work in parallel. The frontend developers programmed against the FastAPI contract, knowing that when we are ready to swap the `app_minimal.py` dictionary for our real Postgres DB and Python-based ML models (XGBoost/Scikit-learn), they won't have to rewrite a single line of client-side API code."

### 2. Authentication Facade (Clerk vs Backend Security)
**Question:** You integrated a heavy, third-party authentication provider (Clerk) on the frontend, but the backend doesn't actually validate any tokens or enforce Row Level Security. For an MVP, wouldn't it have been faster to just use a fake 'mock login' screen rather than integrating Clerk, since the backend ignores it anyway?

**Answer:** 
> "We integrated Clerk strictly to validate the user experience (UX) and onboarding friction, which is critical for a legal tech platform. For this hackathon phase, our primary goal was proving the core workflow and the risk triage interface. We deliberately deferred implementing backend JWT verification because the mock state is ephemeral anyway. Our production `main.py` already has the `clerk_auth` middleware written; we simply disabled it in the minimal app to maximize development velocity. Turning it on later is just a matter of flipping a switch."

### 3. The "AI" Risk Triage (Heuristics vs ML)
**Question:** The core value proposition of the financial risk track relies on advanced AI anomaly detection, but the current implementation in `/v1/compliance/triage` is just a hardcoded keyword scanner (e.g., `if "pep" in desc_lower`). What is your architectural plan to safely swap out this synchronous string-matcher for actual asynchronous ML inference models?

**Answer:** 
> "The current heuristics act as a 'Wizard of Oz' placeholder to perfectly mock the JSON signature of the real ML service, allowing our frontend to build out the complex reporting UI immediately. When we swap in the actual pipeline, the structure remains exactly the same. Because FastAPI is inherently asynchronous, we plan to shift the heavy ML inference to background Celery workers, and the FastAPI route will either wait for the result or return a task ID for the frontend to poll, ensuring the event loop is never blocked."

### 4. The Ngrok Architecture Tunneling
**Question:** The integration guide heavily emphasizes tunneling the frontend to the backend via ngrok. Relying on ngrok for core frontend-to-backend communication introduces significant latency. Why was this approach chosen over simply running both services locally via Docker Compose, or deploying the mock server to a free tier on Render or Vercel?

**Answer:** 
> "In a time-constrained environment with team members distributed across different networks, ngrok provided the absolute fastest path to integration testing. It completely eliminated the overhead of managing Docker networks, CORS edge cases across localhosts, or waiting for CI/CD pipelines to build on a cloud provider. It was a conscious trade-off prioritizing raw development velocity and immediate feedback loops over network latency."

### 5. Transitioning from Mock to Reality
**Question:** The frontend UI is highly polished (using GSAP and Framer Motion) and assumes a deeply complex, instantaneous backend state. When you eventually hook up the *real* blockchain notarization (which takes time to mine) and real AI agents (which stream responses), how much of this frontend state management will have to be completely rewritten?

**Answer:** 
> "Very little. Our frontend API client (`lib/api.ts`) already abstracts all network calls behind structured promises. While responses are instantaneous now, the UI components are built to handle standard React loading states. For the blockchain notarization, we intend to implement optimistic UI updates where the frontend assumes success while the backend processes the transaction. For the streaming AI responses, we will progressively enhance the existing chat endpoint to use Server-Sent Events (SSE), utilizing the same component structures."
