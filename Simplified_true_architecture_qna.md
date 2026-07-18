# OPAL MVP Reality: True Tech Stack & Q&A

Before diving into the questions, here is the exact technology stack actively driving the application right now. This is a rapid-prototyping MVP built for speed, heavily relying on mocks rather than complex infrastructure.

## The Actual Active Tech Stack

### Frontend
* **Framework:** Next.js (App Router, v13.5.1) with TypeScript.
* **Styling & UI:** TailwindCSS, Radix UI headless components.
* **Animations:** Framer Motion and GSAP.
* **Authentication:** Clerk Auth (Frontend UI and session token generation only).
* **State Management:** Native React state and `react-hook-form`.

### Backend
* **Framework:** Python with FastAPI & Uvicorn (`app_minimal.py`).
* **Database & State:** **None.** (Ephemeral in-memory Python dictionaries).
* **Security:** **None.** (Backend blindly accepts requests without verifying Clerk JWTs).
* **AI & Machine Learning:** **None.** (Uses string-matching heuristics to return hardcoded JSON).
* **Integration Layer:** `ngrok` tunnels exposing the local backend to the frontend.

---

## Part 1: Generic Tech Stack Q&A (Short Answer)

These questions cover the foundational reasons for choosing the specific frameworks and tools used in the project.

**Q: Why did you choose Next.js for the frontend?**
* **Built-in Routing:** The App Router simplifies page navigation and layouts.
* **TypeScript Support:** Excellent out-of-the-box type safety.
* **Performance:** Fast rendering and built-in optimizations for production.
* **Ecosystem:** Massive community and seamless integration with modern tooling.

**Q: Why use FastAPI over Django or Flask?**
* **Performance:** Asynchronous by default, making it incredibly fast.
* **Auto-Documentation:** Generates interactive Swagger/OpenAPI docs automatically.
* **Validation:** Built-in data validation using Pydantic ensures clean data.
* **Lightweight:** Very easy to set up a mock or MVP quickly without bloated boilerplate.

**Q: Why Python for the backend?**
* **AI/ML Standard:** It is the industry standard language for machine learning.
* **Ecosystem:** Massive library support (pandas, scikit-learn) for when we integrate the real Track 2 ML risk triage.
* **Flexibility:** Easy to transition from simple mock scripts to complex data processing pipelines.

**Q: Why Clerk for authentication?**
* **Speed:** Drop-in UI components save hours of custom development time.
* **Security:** Handles complex edge cases like MFA and password resets out-of-the-box.
* **Next.js Integration:** Pairs perfectly with Next.js middleware for route protection.

**Q: Why TailwindCSS and Radix UI?**
* **Velocity:** Tailwind allows for rapid styling without switching between CSS and JSX files.
* **Accessibility:** Radix provides robust, accessible, unstyled primitives (like dialogs and dropdowns) that we can fully customize.

---

## Part 2: Architecture & MVP Reality Q&A (Defensive)

These questions address the specific "smoke-and-mirrors" architecture of the MVP (e.g., using an in-memory mock instead of a real database/AI pipeline).

**Q: If the backend is just a mock serving static dictionaries, why use FastAPI instead of Next.js API Routes?**
* **API Contract:** Enforces a strict OpenAPI contract upfront for both teams to follow.
* **Parallel Work:** Allows frontend and backend teams to build independently.
* **Future Proofing:** Ensures the frontend won't need any rewrites when we swap the mock logic for the real Python ML backend.

**Q: You integrated Clerk on the frontend, but the backend doesn't validate the tokens. Why?**
* **UX Focus:** Clerk was added purely to validate the user onboarding experience for the MVP.
* **Ephemeral State:** Backend security was deferred because the current in-memory data is wiped on restart anyway.
* **Easy Switch:** The middleware for JWT validation is already written in our production `main.py` and can be enabled instantly when the real database is hooked up.

**Q: The financial compliance triage uses hardcoded string matching instead of actual AI. How will you transition this to real ML?**
* **Wizard of Oz MVP:** The heuristics perfectly mimic the exact JSON signature of the real ML service to unblock frontend UI development.
* **Seamless Swap:** FastAPI's async nature means replacing the `if/else` logic with background ML inference won't change the API signature.
* **Background Processing:** The heavy ML tasks will eventually be offloaded to Celery workers while FastAPI handles the routing.

**Q: Why rely on ngrok for frontend-to-backend communication instead of local Docker setups?**
* **Speed over Latency:** Prioritized raw development velocity for a fast-paced hackathon.
* **Zero Overhead:** Eliminated the need to configure complex Docker networks or VPC peering.
* **Cross-Team Access:** Allowed frontend devs to hit a teammate's local backend instantly from anywhere.

**Q: The frontend UI assumes instantaneous backend responses. How will it handle the delay of real AI generation or Blockchain mining later?**
* **Promise-Based Abstraction:** The frontend `api.ts` client already wraps all network calls in standard promises.
* **Loading States Ready:** UI components are already built with standard React loading spinners/skeletons.
* **Progressive Enhancement:** Future streaming or delayed mining can be handled by upgrading to WebSockets or polling without changing the base component structure.
