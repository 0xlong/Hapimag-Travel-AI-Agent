# Hapimag Agentic Travel Assistant (Proof of Concept)

An intelligent, AI-powered travel search and booking assistant built for **Hapimag**. This project serves as a proof of concept demonstrating how **Generative AI** can be combined with **deterministic business rules** to create a seamless, natural-language booking experience.

The prototype is designed with an "AI Transformation Lead" mindset, emphasizing:
1. **Separation of Concerns:** Using LLMs for natural language understanding (NLU) and deterministic code for math, pricing, and business rules (preventing LLM calculation hallucinations).
2. **Agentic Workflows:** Orchestrating dynamic tool execution (fetching live weather data via API based on user intent) to enrich the customer experience.
3. **Upsell Opportunities:** Dynamically comparing trip costs against the user's points balance and offering a friction-free purchase call-to-action (CTA) to buy shortfalls.

---

## 🏗️ Architecture & Data Flow

This diagram illustrates how an unstructured user query flows through the AI layer, executes API tool calls, evaluates points requirements deterministically, and presents personalized booking or upsell options to the user.

<img width="3970" height="8192" alt="AI-Driven Hiking Points-2026-07-14-120657" src="https://github.com/user-attachments/assets/eb43ebd7-592e-4b22-9752-f677e41522ec" />

---

## 🌟 Key Features

### 1. Natural Language Intent Parsing
Users can search using raw, conversational phrases (e.g., *"something close to the beach on the Adriatic sea next month"* or *"skiing in early December, I have 150 points"*).
* The LLM maps vague terms (e.g., "pizza" ➡️ Italy, "Adriatic" ➡️ Croatia) to structured tags and countries present in our actual resort catalog.
* Relative dates (e.g., *"next month"*) are resolved using the current server year.

### 2. Live Weather Integration (Function Calling)
* If the user mentions a specific travel window, the backend evaluates if those dates fall within the **next 16 days**.
* If so, the LLM initiates a tool call to fetch daily temperatures, precipitation probability, and weather codes using the **Open-Meteo API** (free, no-key weather forecast).
* The React frontend renders this as a clean, custom-styled daily weather strip directly within the resort card.

### 3. Deterministic Points Evaluation & Upsell Engine
* **No LLM Math:** To prevent LLMs from hallucinating points math, the Python backend executes the calculations:

  **totalPoints = duration_days X pointsPerNight**
* **Shortfall Calculation:** The engine calculates:

  **pointsShortfall = max(0, totalPoints - budget)**
* **Frictionless Upsell:** If the user is short on points, the UI renders an orange **Upsell Panel** displaying the exact shortfall, a calculated cost to purchase the missing points (€12 per point), and a call-to-action button: **"BUY X POINTS (€Y) & BOOK"**.
* If the user has sufficient points, it renders a green panel with a **"BOOK NOW"** button.

### 4. Robust Local Fallback
* If the Gemini API key is missing or the external API call fails, the server automatically falls back to a local search engine utilizing normalized keywords, synonym-tag mapping, and a backup regex engine to parse points budgets.

---

## 🛠️ Technology Stack

* **Frontend:** React 18, Vite, Lucide Icons, Custom Vanilla CSS (with modern, harmonized palettes, glassmorphism, and micro-animations).
* **Backend:** Lightweight Python 3 HTTP Server (`BaseHTTPRequestHandler`) with zero external dependencies.
* **AI Integration:** Google Gemini API (supporting structured schema inputs and tool/function calling).
* **Weather Service:** Open-Meteo API.

---

## 📂 Project Structure

```text
hapimag_agentic_travel/
├── .env                         # Shared environment variables (API keys, models)
├── .gitignore                   # Excluded directories (node_modules, logs)
└── hapimag_website/
    ├── package.json             # React dependencies & scripts
    ├── vite.config.js           # Vite server configuration
    ├── index.html               # Main HTML shell
    ├── src/
    │   ├── App.jsx              # Main React Application & UI components
    │   ├── main.jsx             # React DOM entrypoint
    │   ├── styles.css           # Custom UI stylesheets
    │   └── data/
    │       └── destinations.js  # Static frontend destination catalog
    └── backend/
        ├── server.py            # Python Search & API server
        ├── destinations.json    # Backend resort catalog (with nightly points rates)
        ├── destination_coords.json # Latitude/longitude for weather calls
        └── prompts/
            └── trip_search_prompt.txt # Prompt instructions for Gemini
```

---

## 🚀 Setup & Installation

### 1. Prerequisites
* [Node.js](https://nodejs.org/) (v16 or higher)
* [Python 3](https://www.python.org/)

### 2. Configure Environment Variables
Create a `.env` file in the **root** folder of the project:

```env
# Google AI Studio API Key (obtain from https://aistudio.google.com/)
GEMINI_API_KEY=your_gemini_api_key_here

# Selected Gemini model
GEMINI_MODEL=gemini-2.5-flash

# Logging settings (true/false)
DEBUG_GEMINI=true
DEBUG_GEMINI_VERBOSE=false
```

### 3. Run the Frontend (React/Vite)
Navigate to the `hapimag_website` directory, install dependencies, and start the development server:

```powershell
cd hapimag_website
npm install
npm run dev
```
The frontend will run at `http://localhost:5173/`.

### 4. Run the Backend API (Python)
In a new terminal window, navigate to the `hapimag_website` directory and start the Python API server:

```powershell
cd hapimag_website
npm run api
```
*(Alternatively, run: `python backend/server.py`)*

The backend server will run at `http://localhost:8000/`.

---

## 🔍 Debugging & Logs

The backend includes a comprehensive logging system to trace LLM inputs, tool calls, and model responses:
* Logs are printed to the terminal console.
* Safe outputs are logged directly to `hapimag_website/backend/gemini_debug.log`.
* Set `DEBUG_GEMINI_VERBOSE=true` in your `.env` file to output full prompt payloads and raw JSON responses for detailed troubleshooting.
