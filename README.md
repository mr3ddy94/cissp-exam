# CISSP Adaptive Practice Exam

A self-built web application for CISSP certification preparation, implementing
Computerized Adaptive Testing (CAT) powered by Item Response Theory and live
AI question generation via the Anthropic Claude API. Built as a practical
demonstration of applied cybersecurity knowledge, Python development, and
cloud deployment.

---

## Overview

This tool replaces passive flashcard review with an intelligent, adaptive
examination environment that mirrors the psychometric methodology used in the
actual CISSP Computer-Based Test. The difficulty of each question adjusts in
real time based on performance, giving an accurate picture of readiness across
all eight CISSP CBK domains rather than a simple pass/fail score.

The application is deployed as a permanent public web app on Streamlit
Community Cloud and can be used from any browser without installation.

---

## Technical Architecture

### Adaptive Testing Engine

The core of the application is a custom implementation of the
3-Parameter Logistic Item Response Theory model (3PL-IRT), the same
psychometric framework used by ISC2 to develop and score the CISSP exam.

The model estimates a candidate's latent ability (theta) on a continuous
scale after each response using a Maximum Likelihood Estimation step:

    P(correct | theta) = c + (1 - c) / (1 + exp(-a(theta - b)))

Where:
- theta = current ability estimate (-3 to +3)
- a     = item discrimination (fixed at 1.2)
- b     = item difficulty (Foundational: -1.5, Applied: 0.0, Expert: +1.5)
- c     = pseudo-guessing parameter (0.25 for 4-option MCQ)

Each subsequent question targets the difficulty level where the candidate
has approximately 65% probability of a correct response. This is the point
of maximum Fisher information on the IRT curve; the optimal zone for
simultaneous learning and ability measurement.

### AI Question Generation

When operating in Online or Hybrid mode, the application calls the
Anthropic Claude API (claude-haiku model) to generate unique CISSP-style
questions at the exact difficulty level requested by the CAT engine.
Questions are generated with a structured prompt that enforces:

- CISSP CBK domain and topic targeting
- Difficulty-appropriate scenario complexity
- Plausible distractor construction
- Detailed answer explanations covering why correct answers are right
  and why each distractor is wrong

### Offline Question Bank

The application ships with a curated JSON question bank covering all
eight CISSP domains. In Hybrid mode the local bank is prioritised for
speed and zero API cost, with AI generation as a fallback. No question
is served twice within a session, a used-ID set is maintained in
session state throughout the test.

### Question Source Modes

| Mode    | Behaviour                                                     |
|---------|---------------------------------------------------------------|
| Offline | Serves exclusively from the local JSON bank. No API required. |
| Online  | Every question generated live by Claude AI.                   |
| Hybrid  | Local bank first. Falls back to AI when bank is exhausted.    |

---

## CISSP Domains Covered

| Domain | Name                                  |
|--------|---------------------------------------|
| D1     | Security and Risk Management          |
| D2     | Asset Security                        |
| D3     | Security Architecture and Engineering |
| D4     | Communication and Network Security    |
| D5     | Identity and Access Management        |
| D6     | Security Assessment and Testing       |
| D7     | Security Operations                   |
| D8     | Software Development Security         |

---

## Features

- Computerized Adaptive Testing with real-time ability estimation
- Three difficulty tiers: Foundational, Applied, Expert
- Domain selection; test a single domain or mix all eight
- Configurable session length (10, 15, 25, 50, or 75 questions)
- Countdown timer with configurable limit (1, 2, 3, or 4 hours)
- No repeated questions within a session
- Detailed AI-generated explanations for every question
- Post-test results dashboard including:
  - Overall score and estimated CISSP pass probability
  - Ability progression chart (theta over time)
  - Breakdown by difficulty tier
  - Breakdown by domain with progress bars
  - Full question-by-question review with filtering

---

## Stack

| Layer       | Technology                              |
|-------------|-----------------------------------------|
| Language    | Python 3.10+                            |
| Framework   | Streamlit                               |
| AI          | Anthropic Claude API (Haiku model)      |
| Algorithm   | Custom IRT 3PL CAT engine               |
| Data        | JSON question bank (local file)         |
| Deployment  | Streamlit Community Cloud               |

---

## Local Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO

# Install dependencies
pip install streamlit anthropic

# Configure API key
mkdir -p .streamlit
echo 'ANTHROPIC_API_KEY = "sk-ant-your-key-here"' > .streamlit/secrets.toml

# Run
streamlit run cissp_app.py
```

---

## Cloud Deployment

The application is deployed on Streamlit Community Cloud, which provides
permanent hosting from a GitHub repository at no cost.

1. Push repository to GitHub (must be public for free tier)
2. Sign in at streamlit.io/cloud using GitHub authentication
3. Select repository, branch, and entry point (cissp_app.py)
4. Add ANTHROPIC_API_KEY to App Settings > Secrets
5. Deploy; the app receives a permanent public URL

---

## Expanding the Question Bank

A batch generation script is included (generate_questions.py) that calls
the Claude API in a continuous loop to build the local question bank up to
a configurable target (default 10,000 questions). The script saves progress
every 10 questions and can be interrupted and resumed at any time.

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
pip install anthropic python-dotenv
python generate_questions.py
```

At Claude Haiku pricing, generating 10,000 questions costs approximately
$8 to $12 USD. Questions are distributed evenly across all eight domains
and three difficulty tiers.

---

## Repository Structure

```
cissp-exam/
├── cissp_app.py             # Main Streamlit application
├── cissp_questions.json     # Local question bank
├── generate_questions.py    # Batch question generation script
└── requirements.txt         # Python dependencies
```

---

## Security Relevance

This project was built as part of active preparation for the CISSP
certification. The domains it covers: risk management, cryptography,
network security, IAM, incident response, and secure software development, represent the core body of knowledge for information security professionals
operating at a strategic and architectural level.

The technical implementation itself demonstrates practical skills relevant
to security engineering roles: API integration with authentication and
secret management, stateful session handling, data validation, and
deployment pipeline configuration.

---

## Author

Edwin Acquah
Cybersecurity Portfolio: github.com/YOUR_USERNAME
