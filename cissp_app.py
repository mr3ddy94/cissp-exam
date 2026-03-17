"""
CISSP Adaptive Practice Exam - Streamlit Web App
=================================================
Supports OFFLINE mode (local question bank) + ONLINE mode (Claude AI generation)
Deploy free: https://streamlit.io/cloud
Secret:      ANTHROPIC_API_KEY = "sk-ant-..."
"""

import json
import math
import os
import random
import time

import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CISSP Adaptive Exam",
    page_icon="🔐",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────────────────
DOMAINS = {
    1: {"name": "Security & Risk Management",         "short": "Risk Mgmt",    "color": "#e05c5c",
        "topics": ["risk management","BIA","threat modeling","security policies","ALE calculations","business continuity","legal regulations","due care"]},
    2: {"name": "Asset Security",                      "short": "Asset Sec",    "color": "#e08c3a",
        "topics": ["data classification","data lifecycle","media sanitization","data ownership","privacy protection","data remanence","retention policies"]},
    3: {"name": "Security Architecture & Engineering", "short": "Architecture", "color": "#c8a820",
        "topics": ["cryptography","PKI","security models","Bell-LaPadula","Biba","Clark-Wilson","TPM","cloud security","secure design principles"]},
    4: {"name": "Communication & Network Security",    "short": "Network Sec",  "color": "#3aae6a",
        "topics": ["OSI model","firewalls","VPN","IPSec","TLS","wireless security","DMZ","network attacks","VLAN","network protocols"]},
    5: {"name": "Identity & Access Management",        "short": "IAM",          "color": "#3a8ae0",
        "topics": ["authentication","MFA","SSO","SAML","OAuth","Kerberos","RBAC","MAC","DAC","provisioning","identity federation"]},
    6: {"name": "Security Assessment & Testing",       "short": "Assessment",   "color": "#9b5fcf",
        "topics": ["penetration testing","vulnerability assessment","security audits","CVSS","log review","black box testing","OWASP","SOC reports"]},
    7: {"name": "Security Operations",                 "short": "Sec Ops",      "color": "#1aaa8a",
        "topics": ["incident response","digital forensics","disaster recovery","backup strategies","SIEM","chain of custody","RTO RPO","change management"]},
    8: {"name": "Software Development Security",       "short": "Dev Sec",      "color": "#5080b0",
        "topics": ["SDLC","DevSecOps","OWASP Top 10","secure coding","input validation","static analysis","software testing","application threats"]},
}

DIFFICULTIES = {
    "easy":   {"label": "Foundational", "theta": -1.5, "emoji": "🟢"},
    "medium": {"label": "Applied",      "theta":  0.0, "emoji": "🟡"},
    "hard":   {"label": "Expert",       "theta":  1.5, "emoji": "🔴"},
}

NEON = "#00ff88"   # neon green — replaces all grey text throughout the app

# ─────────────────────────────────────────────────────────────────────────────
# QUESTION BANK  — load from cissp_questions.json if available
# ─────────────────────────────────────────────────────────────────────────────
def load_question_bank():
    """
    Load questions from cissp_questions.json.
    Stored in session_state so it loads once per session
    but always fresh when the app restarts or redeploys.
    Checks multiple locations so it works locally and on Streamlit Cloud.
    """
    # Return cached version if already loaded this session
    if "question_bank" in st.session_state and st.session_state.question_bank:
        return st.session_state.question_bank

    # All possible locations Streamlit Cloud or local might use
    paths = [
        "cissp_questions.json",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "cissp_questions.json"),
        os.path.join(os.getcwd(), "cissp_questions.json"),
        "/app/cissp_questions.json",
        "/mount/src/cissp_questions.json",
    ]

    for path in paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data:
                    st.session_state.question_bank = data
                    st.session_state.bank_path     = path
                    return data
            except Exception:
                pass

    st.session_state.question_bank = []
    return []


def get_offline_question(domain_id, difficulty, used_ids):
    """
    Pick a random question from the local bank matching domain and difficulty.
    Falls back to any domain-matched question, then any question, if no match.
    Returns None if bank is empty.
    """
    bank = load_question_bank()
    if not bank:
        return None

    # Try exact match: domain + difficulty, not already used
    pool = [q for q in bank
            if q.get("domain") == domain_id
            and q.get("difficulty") == difficulty
            and q.get("id") not in used_ids]

    # Fallback 1: same domain, any difficulty
    if not pool:
        pool = [q for q in bank
                if q.get("domain") == domain_id
                and q.get("id") not in used_ids]

    # Fallback 2: any question not yet used
    if not pool:
        pool = [q for q in bank if q.get("id") not in used_ids]

    # Fallback 3: entire bank (allow repeats)
    if not pool:
        pool = bank

    if not pool:
        return None

    raw = random.choice(pool)
    return {
        "domain_id":   raw.get("domain", domain_id),
        "difficulty":  raw.get("difficulty", difficulty),
        "topic":       raw.get("topic", ""),
        "question":    raw["question"],
        "options":     raw["options"],
        "answer":      int(raw["answer"]),
        "explanation": raw.get("explanation", "No explanation provided."),
        "source":      "offline",
    }


# ─────────────────────────────────────────────────────────────────────────────
# CAT ENGINE
# ─────────────────────────────────────────────────────────────────────────────
class CATEngine:
    def __init__(self, starting_difficulty="medium"):
        self.theta = DIFFICULTIES[starting_difficulty]["theta"]
        self.responses = []

    def probability(self, b, a=1.2, c=0.25):
        return c + (1 - c) / (1 + math.exp(-a * (self.theta - b)))

    def update(self, difficulty, correct):
        b = DIFFICULTIES[difficulty]["theta"]
        p = self.probability(b)
        step = 0.4 * (1 - p) if correct else -0.4 * p
        self.theta = max(-3.0, min(3.0, self.theta + step))
        self.responses.append({"difficulty": difficulty, "correct": correct, "theta": self.theta})

    def next_difficulty(self):
        if len(self.responses) < 2:
            return "medium"
        if self.theta >= 0.8:
            return "hard"
        if self.theta <= -0.8:
            return "easy"
        return "medium"

    def ability_label(self):
        if self.theta >= 1.5:  return "Expert",      "#e05c5c"
        if self.theta >= 0.7:  return "Proficient",  "#c8a820"
        if self.theta >= -0.3: return "Competent",   "#3a8ae0"
        if self.theta >= -1.2: return "Developing",  "#e08c3a"
        return "Foundational", NEON

    def pass_probability(self):
        return max(5, min(97, round(50 + self.theta * 20)))

    def stats(self):
        total   = len(self.responses)
        correct = sum(1 for r in self.responses if r["correct"])
        by_diff = {}
        for d in ("easy", "medium", "hard"):
            items = [r for r in self.responses if r["difficulty"] == d]
            by_diff[d] = {"total": len(items), "correct": sum(1 for r in items if r["correct"])}
        return {
            "total": total, "correct": correct,
            "pct": round(correct / total * 100) if total else 0,
            "by_diff": by_diff,
            "theta_history": [0.0] + [r["theta"] for r in self.responses],
        }


# ─────────────────────────────────────────────────────────────────────────────
# CLAUDE AI  — online generation with retries
# ─────────────────────────────────────────────────────────────────────────────
def get_client():
    try:
        import anthropic
        key = st.secrets["ANTHROPIC_API_KEY"]
        return anthropic.Anthropic(api_key=key)
    except Exception:
        return None


def generate_question_ai(domain_id, difficulty, used_topics):
    """Generate one question via Claude AI. Returns dict or raises RuntimeError."""
    client = get_client()
    if client is None:
        raise RuntimeError("No API client available — check ANTHROPIC_API_KEY in Secrets.")

    domain = DOMAINS[domain_id]
    recent = used_topics[-4:] if len(used_topics) >= 4 else used_topics
    available = [t for t in domain["topics"] if t not in recent]
    topic = random.choice(available if available else domain["topics"])

    diff_guide = {
        "easy":   "A basic recall or definition question. Clear correct answer for anyone who studied.",
        "medium": "A scenario-based question. Realistic workplace situation — what should the professional do?",
        "hard":   "Complex question with competing priorities or subtle distinctions. All options look plausible.",
    }

    prompt = (
        f"Write one CISSP exam question.\n"
        f"Domain: {domain['name']}\n"
        f"Topic: {topic}\n"
        f"Difficulty: {difficulty} — {diff_guide[difficulty]}\n\n"
        f"Rules:\n"
        f"- 4 options only\n"
        f"- Use BEST / MOST / FIRST where appropriate\n"
        f"- All wrong options must be plausible\n"
        f"- answer = 0-based index of correct option (0,1,2, or 3)\n"
        f"- explanation = 2-3 sentences: why correct, why others are wrong\n\n"
        f"Reply with ONLY this JSON:\n"
        f'{{"question":"...","options":["A","B","C","D"],"answer":0,"explanation":"...","topic":"{topic}"}}'
    )

    last_error = None
    for attempt in range(1, 4):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            if not raw.startswith("{"):
                idx = raw.find("{")
                if idx != -1:
                    raw = raw[idx:]
            data = json.loads(raw)
            assert len(data["options"]) == 4
            assert data["answer"] in (0, 1, 2, 3)
            return {
                "domain_id":   domain_id,
                "difficulty":  difficulty,
                "topic":       data.get("topic", topic),
                "question":    data["question"],
                "options":     data["options"],
                "answer":      int(data["answer"]),
                "explanation": data["explanation"],
                "source":      "ai",
            }
        except Exception as e:
            last_error = str(e)
            if attempt < 3:
                time.sleep(1.5)

    raise RuntimeError(f"AI generation failed after 3 attempts: {last_error}")


def get_question(domain_id, difficulty, used_topics, used_ids, mode):
    """
    Master question fetcher.
    mode: 'offline' | 'online' | 'hybrid'
    hybrid = try offline first, fall back to AI
    """
    if mode == "online":
        return generate_question_ai(domain_id, difficulty, used_topics)

    if mode == "offline":
        q = get_offline_question(domain_id, difficulty, used_ids)
        if q is None:
            raise RuntimeError(
                "Question bank is empty or cissp_questions.json not found. "
                "Switch to Online or Hybrid mode, or add the question bank file."
            )
        return q

    # Hybrid — offline first
    q = get_offline_question(domain_id, difficulty, used_ids)
    if q is not None:
        return q
    return generate_question_ai(domain_id, difficulty, used_topics)


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
def init_session():
    defaults = {
        "screen":           "home",
        "cat":              None,
        "questions":        [],
        "current_idx":      0,
        "selected_answer":  None,
        "show_explanation": False,
        "flagged":          set(),
        "config":           {},
        "start_time":       None,
        "elapsed":          0,
        "domain_cycle":     0,
        "used_topics":      [],
        "used_ids":         set(),
        "q_answered":       [],
        "error_msg":        None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_test():
    for k in ["cat","questions","current_idx","selected_answer","show_explanation",
              "flagged","start_time","elapsed","domain_cycle","used_topics",
              "used_ids","q_answered","error_msg"]:
        st.session_state.pop(k, None)
    st.session_state.screen = "home"


def _pick_domain():
    domains = st.session_state.config["selected_domains"]
    idx = st.session_state.domain_cycle % len(domains)
    st.session_state.domain_cycle += 1
    return domains[idx]


def _load_next_question():
    cat        = st.session_state.cat
    difficulty = cat.next_difficulty()
    domain_id  = _pick_domain()
    mode       = st.session_state.config.get("mode", "hybrid")
    try:
        q = get_question(domain_id, difficulty,
                         st.session_state.used_topics,
                         st.session_state.used_ids,
                         mode)
        st.session_state.questions.append(q)
        if q.get("topic"):
            st.session_state.used_topics.append(q["topic"])
        if q.get("id"):
            st.session_state.used_ids.add(q["id"])
        st.session_state.selected_answer  = None
        st.session_state.show_explanation = False
        st.session_state.error_msg        = None
        return True
    except Exception as exc:
        st.session_state.error_msg = str(exc)
        return False


def _fmt(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# CSS  — neon green replaces all grey
# ─────────────────────────────────────────────────────────────────────────────
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif;
}}

/* ── Background ── */
.stApp {{
    background-color: #0d0f16;
    color: #e4e7f0;
}}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {{
    background-color: #0a0c12;
    border-right: 1px solid #1a1e2e;
}}

/* ── ALL grey / muted text → neon green ── */
.stMarkdown p, .stMarkdown li,
[data-testid="stCaptionContainer"],
.stCaption, label, .stRadio label,
.stCheckbox label, .stSelectSlider label,
div[data-testid="stMarkdownContainer"] p,
[data-testid="stMetricLabel"],
.st-emotion-cache-1gulkj5,
.st-emotion-cache-q8sbsg,
small, caption,
[data-testid="stExpander"] summary p {{
    color: {NEON} !important;
}}

/* ── Metric values stay white/bright ── */
[data-testid="stMetricValue"] {{
    font-size: 2rem !important;
    font-weight: 900 !important;
    color: #ffffff !important;
}}

/* ── Headings ── */
h1, h2, h3, h4 {{
    color: #e4e7f0 !important;
}}

/* ── Progress bar ── */
div[data-testid="stProgress"] > div > div {{
    background-color: #3b6bfa !important;
}}

/* ── Info / success / error boxes ── */
[data-testid="stAlert"] p {{
    color: #e4e7f0 !important;
}}

/* ── Sidebar text ── */
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
    color: {NEON} !important;
}}

/* ── Selectbox / radio options ── */
div[data-baseweb="select"] span,
div[data-baseweb="radio"] label {{
    color: {NEON} !important;
}}

/* ── Expander header text ── */
.streamlit-expanderHeader p {{
    color: {NEON} !important;
}}

/* ── Badge helper ── */
.badge {{
    display: inline-block;
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 700;
    margin-right: 6px;
}}

/* ── Source tag ── */
.src-tag {{
    font-size: 10px;
    font-weight: 700;
    border-radius: 4px;
    padding: 2px 7px;
    margin-left: 6px;
    vertical-align: middle;
}}
.src-offline {{ background: #00ff8822; color: {NEON}; border: 1px solid {NEON}55; }}
.src-ai      {{ background: #3b6bfa22; color: #3b6bfa; border: 1px solid #3b6bfa55; }}
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN — HOME
# ─────────────────────────────────────────────────────────────────────────────
def screen_home():
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown("# 🔐 CISSP Adaptive Practice Exam")
    st.markdown("*AI-generated questions and a local question bank that adapt to your ability level.*")
    st.divider()

    bank      = load_question_bank()
    bank_size = len(bank)

    with st.sidebar:
        st.markdown("## ⚙️ Configuration")

        # Mode selector
        st.markdown("### 🌐 Question Source")
        mode_options = {
            "hybrid":  "🔀 Hybrid  (bank first, AI fallback)",
            "offline": "📦 Offline (local bank only)",
            "online":  "🤖 Online  (Claude AI only)",
        }
        mode = st.radio("Source mode", list(mode_options.keys()),
                        format_func=lambda k: mode_options[k], index=0)

        if mode == "offline" and bank_size == 0:
            st.error("❌ cissp_questions.json not found in repo. Upload it to GitHub.")
        elif bank_size > 0:
            st.success(f"✅ Bank loaded: {bank_size} questions")
            st.caption(f"From: {st.session_state.get('bank_path', 'unknown')}")
        else:
            st.warning("⚠️ No local bank found — Online (AI) mode only")
        st.markdown("### 📚 Domains")
        all_sel = st.checkbox("All domains", value=True, key="chk_all")
        selected_domains = []
        for did, info in DOMAINS.items():
            if st.checkbox(f"D{did}: {info['short']}", value=all_sel, key=f"d_{did}"):
                selected_domains.append(did)

        st.markdown("### 🎯 Questions")
        q_count = st.select_slider("How many?", options=[10, 15, 25, 50, 75], value=25)

        st.markdown("### 📈 Starting Difficulty")
        start_diff = st.radio(
            "CAT adapts from here",
            ["easy", "medium", "hard"], index=1,
            format_func=lambda d: f"{DIFFICULTIES[d]['emoji']} {DIFFICULTIES[d]['label']}"
        )

        st.markdown("### ⏱ Timer")
        timed       = st.toggle("Enable countdown timer", value=True)
        timer_hours = st.select_slider("Hours", options=[1,2,3,4], value=3) if timed else None

        st.divider()
        go = st.button("🚀 Start Test", type="primary",
                       use_container_width=True,
                       disabled=len(selected_domains) == 0)

    # ── Info cards ────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    c1.metric("Domains",   "8 covered")
    c2.metric("Algorithm", "IRT 3-PL CAT")
    c3.metric("Bank",      f"{bank_size} Qs" if bank_size else "AI only")

    st.info(
        f"**Hybrid mode** uses your local question bank first (fast, no API cost), "
        f"then falls back to Claude AI for fresh questions when the bank runs low. "
        f"**Offline mode** uses only the bank — no API key needed. "
        f"**Online mode** generates every question live with Claude AI."
    )

    st.markdown("### 📋 CISSP Domains")
    for did, info in DOMAINS.items():
        with st.expander(f"D{did}: {info['name']}"):
            st.caption(", ".join(info["topics"]))

    if go:
        if not selected_domains:
            st.error("Pick at least one domain.")
            return
        st.session_state.config = {
            "selected_domains": selected_domains,
            "q_count":          q_count,
            "start_diff":       start_diff,
            "timed":            timed,
            "timer_secs":       timer_hours * 3600 if timed else None,
            "mode":             mode,
        }
        st.session_state.cat          = CATEngine(start_diff)
        st.session_state.questions    = []
        st.session_state.current_idx  = 0
        st.session_state.domain_cycle = 0
        st.session_state.used_topics  = []
        st.session_state.used_ids     = set()
        st.session_state.q_answered   = []
        st.session_state.flagged      = set()
        st.session_state.start_time   = time.time()
        st.session_state.screen       = "loading"
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN — LOADING
# ─────────────────────────────────────────────────────────────────────────────
def screen_loading():
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown("## ⏳ Preparing your test…")

    cfg   = st.session_state.config
    names = [f"D{d}: {DOMAINS[d]['short']}" for d in cfg["selected_domains"]]
    st.write(f"**Domains:** {', '.join(names)}")
    st.write(f"**Questions:** {cfg['q_count']}  ·  **Start level:** {DIFFICULTIES[cfg['start_diff']]['label']}  ·  **Mode:** {cfg['mode']}")

    spinner_msg = (
        "Loading from question bank…" if cfg["mode"] == "offline"
        else "Claude is writing your first question (5–10 sec)…" if cfg["mode"] == "online"
        else "Fetching first question…"
    )

    with st.spinner(spinner_msg):
        ok = _load_next_question()

    if ok:
        st.session_state.screen = "test"
        st.rerun()
    else:
        st.error(f"❌ {st.session_state.error_msg}")
        st.markdown("**Common fixes:**")
        st.markdown(f"- If using Online/Hybrid: check `ANTHROPIC_API_KEY` is set in Streamlit Secrets and your account has credits at console.anthropic.com")
        st.markdown(f"- If using Offline: make sure `cissp_questions.json` is in the same folder as `cissp_app.py`")
        c1, c2 = st.columns(2)
        if c1.button("🔄 Retry"):
            st.rerun()
        if c2.button("← Back to Home"):
            reset_test()
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN — TEST
# ─────────────────────────────────────────────────────────────────────────────
def screen_test():
    st.markdown(CSS, unsafe_allow_html=True)

    cat       = st.session_state.cat
    cfg       = st.session_state.config
    questions = st.session_state.questions
    idx       = st.session_state.current_idx

    if idx >= len(questions):
        with st.spinner("Fetching question…"):
            if not _load_next_question():
                st.error(st.session_state.error_msg)
                if st.button("🔄 Retry"):
                    st.rerun()
                return

    q        = questions[idx]
    total_q  = cfg["q_count"]
    answered = st.session_state.selected_answer is not None
    a_label, _ = cat.ability_label()

    # ── Top bar ───────────────────────────────────────────────────────────
    left, mid, right = st.columns([4, 2, 1])
    with left:
        st.progress((idx + (1 if answered else 0)) / total_q)
        st.caption(f"Q{idx+1} of {total_q}  ·  θ={cat.theta:.2f}  ·  **{a_label}**")
    with mid:
        if cfg["timed"] and cfg["timer_secs"]:
            remaining = cfg["timer_secs"] - int(time.time() - st.session_state.start_time)
            if remaining <= 0:
                st.session_state.elapsed = cfg["timer_secs"]
                st.session_state.screen  = "results"
                st.rerun()
            icon = "🔴" if remaining < 600 else "🟡" if remaining < 1800 else "🟢"
            st.markdown(f"**{icon} {_fmt(remaining)}**")
        else:
            st.caption(f"⏱ {_fmt(int(time.time() - st.session_state.start_time))}")
    with right:
        if st.button("Finish"):
            st.session_state.elapsed = int(time.time() - st.session_state.start_time)
            st.session_state.screen  = "results"
            st.rerun()

    st.divider()

    # ── Badges ────────────────────────────────────────────────────────────
    d_info   = DOMAINS[q["domain_id"]]
    dif_info = DIFFICULTIES[q["difficulty"]]
    src      = q.get("source", "offline")
    src_html = (
        f'<span class="src-tag src-offline">📦 Bank</span>' if src == "offline"
        else f'<span class="src-tag src-ai">🤖 AI</span>'
    )

    st.markdown(
        f'<span class="badge" style="background:{d_info["color"]}22;color:{d_info["color"]};'
        f'border:1px solid {d_info["color"]}55;">D{q["domain_id"]}: {d_info["short"]}</span>'
        f'<span class="badge" style="background:#1a1e2e;color:{NEON};">'
        f'{dif_info["emoji"]} {dif_info["label"]}</span>'
        + (f'<span class="badge" style="background:#1a1e2e;color:{NEON};">{q["topic"]}</span>'
           if q.get("topic") else "")
        + src_html,
        unsafe_allow_html=True,
    )

    # Flag button
    flagged: set = st.session_state.flagged
    fc, _ = st.columns([1, 9])
    with fc:
        if st.button("🚩 Flagged" if idx in flagged else "⬜ Flag"):
            flagged.discard(idx) if idx in flagged else flagged.add(idx)
            st.rerun()

    # ── Question ──────────────────────────────────────────────────────────
    st.markdown(f"### {q['question']}")
    st.write("")

    letters = ["A", "B", "C", "D"]

    if not answered:
        for i, opt in enumerate(q["options"]):
            if st.button(f"**{letters[i]}.** {opt}", key=f"opt_{i}", use_container_width=True):
                st.session_state.selected_answer = i
                correct = (i == q["answer"])
                cat.update(q["difficulty"], correct)
                st.session_state.q_answered.append(correct)
                st.session_state.show_explanation = True
                st.rerun()
    else:
        sel = st.session_state.selected_answer
        for i, opt in enumerate(q["options"]):
            if i == q["answer"]:
                st.success(f"**{letters[i]}.** {opt}  ✓")
            elif i == sel:
                st.error(f"**{letters[i]}.** {opt}  ✗  ← your answer")
            else:
                st.markdown(f"**{letters[i]}.** {opt}")

    # ── Explanation ───────────────────────────────────────────────────────
    if st.session_state.show_explanation:
        is_correct = (st.session_state.selected_answer == q["answer"])
        if is_correct:
            st.success("✅ Correct!")
        else:
            st.error(f"❌ Incorrect — correct answer was **{letters[q['answer']]}**")

        with st.expander("📖 Explanation", expanded=True):
            st.write(q["explanation"])

        new_label, _ = cat.ability_label()
        next_diff    = cat.next_difficulty()
        st.info(
            f"θ updated to **{cat.theta:.2f}** · Ability: **{new_label}** · "
            f"Next: **{DIFFICULTIES[next_diff]['label']}** level"
        )

    # ── Navigation ────────────────────────────────────────────────────────
    st.divider()
    nl, nr = st.columns(2)

    with nl:
        if idx > 0 and st.button("← Previous", use_container_width=True):
            st.session_state.current_idx     -= 1
            prev_q = questions[st.session_state.current_idx]
            st.session_state.selected_answer  = prev_q.get("_user_answer")
            st.session_state.show_explanation = prev_q.get("_user_answer") is not None
            st.rerun()

    with nr:
        if answered:
            is_last = (idx + 1 >= total_q)
            if st.button("🏁 See Results" if is_last else "Next Question →",
                         type="primary", use_container_width=True):
                questions[idx]["_user_answer"] = st.session_state.selected_answer
                if is_last:
                    st.session_state.elapsed = int(time.time() - st.session_state.start_time)
                    st.session_state.screen  = "results"
                    st.rerun()
                else:
                    st.session_state.current_idx += 1
                    nxt = st.session_state.current_idx
                    if nxt >= len(questions):
                        with st.spinner("Loading next question…"):
                            ok = _load_next_question()
                        if not ok:
                            st.error(f"⚠️ {st.session_state.error_msg}")
                    else:
                        nq = questions[nxt]
                        st.session_state.selected_answer  = nq.get("_user_answer")
                        st.session_state.show_explanation = nq.get("_user_answer") is not None
                    st.rerun()

    # ── Sidebar navigator ─────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 📋 Progress")
        cols = st.columns(5)
        for i in range(len(questions)):
            c = cols[i % 5]
            if i < len(st.session_state.q_answered):
                c.markdown("✅" if st.session_state.q_answered[i] else "❌")
            elif i in flagged:
                c.markdown("🚩")
            elif i == idx:
                c.markdown(f"**{i+1}**")
            else:
                c.markdown(f"_{i+1}_")
        st.divider()
        st.caption("✅ Correct  ❌ Wrong  🚩 Flagged")
        st.divider()
        if st.button("🏠 Home", use_container_width=True):
            reset_test()
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# SCREEN — RESULTS
# ─────────────────────────────────────────────────────────────────────────────
def screen_results():
    st.markdown(CSS, unsafe_allow_html=True)
    cat       = st.session_state.cat
    questions = st.session_state.questions
    elapsed   = st.session_state.get("elapsed", 0)
    stats     = cat.stats()
    a_label, _ = cat.ability_label()
    pass_prob  = cat.pass_probability()

    st.markdown("# 🎓 Your Results")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Score",    f"{stats['pct']}%")
    c2.metric("Correct",  f"{stats['correct']}/{stats['total']}")
    c3.metric("Ability",  a_label)
    c4.metric("θ",        f"{cat.theta:.2f}")

    if pass_prob >= 65:
        st.success(f"🎯 Estimated CISSP pass probability: **{pass_prob}%** — You're on track!")
    else:
        st.warning(f"📚 Estimated CISSP pass probability: **{pass_prob}%** — Keep studying!")

    st.caption(f"Time: {_fmt(elapsed)}")
    st.divider()

    # Θ chart
    st.markdown("### 📈 Ability (θ) Over Time")
    st.line_chart({"θ": stats["theta_history"]})
    st.caption("Below −1 = Foundational · −1 to 0 = Developing · 0 to +1 = Competent · Above +1 = Proficient/Expert")

    st.divider()

    # Difficulty breakdown
    st.markdown("### 🎯 By Difficulty")
    dc = st.columns(3)
    for ci, dk in enumerate(("easy", "medium", "hard")):
        inf = stats["by_diff"][dk]
        pct = round(inf["correct"] / inf["total"] * 100) if inf["total"] else 0
        dc[ci].metric(DIFFICULTIES[dk]["label"], f"{inf['correct']}/{inf['total']}", f"{pct}%")

    st.divider()

    # Domain breakdown
    st.markdown("### 📚 By Domain")
    dom_stats = {}
    for i, q in enumerate(questions):
        did = q["domain_id"]
        dom_stats.setdefault(did, {"total": 0, "correct": 0})
        dom_stats[did]["total"] += 1
        if i < len(cat.responses) and cat.responses[i]["correct"]:
            dom_stats[did]["correct"] += 1
    for did, ds in sorted(dom_stats.items()):
        pct = round(ds["correct"] / ds["total"] * 100) if ds["total"] else 0
        st.progress(pct / 100,
                    text=f"D{did}: {DOMAINS[did]['short']} — {ds['correct']}/{ds['total']} ({pct}%)")

    st.divider()

    # Full review
    st.markdown("### 🔍 Review Every Question")
    show = st.radio("Filter:", ["All", "Correct only", "Incorrect only"], horizontal=True)

    for i, q in enumerate(questions):
        if i >= len(cat.responses):
            break
        correct = cat.responses[i]["correct"]
        if show == "Correct only"   and not correct: continue
        if show == "Incorrect only" and correct:     continue

        d_info  = DOMAINS[q["domain_id"]]
        di_info = DIFFICULTIES[q["difficulty"]]
        icon    = "✅" if correct else "❌"
        src     = q.get("source", "offline")
        src_lbl = "📦" if src == "offline" else "🤖"

        with st.expander(
            f"{icon} Q{i+1} · D{q['domain_id']}: {d_info['short']} · "
            f"{di_info['label']} · {q.get('topic','')} {src_lbl}"
        ):
            st.markdown(f"**{q['question']}**")
            st.write("")
            letters = ["A","B","C","D"]
            for j, opt in enumerate(q["options"]):
                if j == q["answer"]:
                    st.success(f"**{letters[j]}.** {opt}  ✓")
                else:
                    st.markdown(f"**{letters[j]}.** {opt}")
            st.divider()
            st.markdown("**Explanation:**")
            st.write(q["explanation"])

    st.divider()
    if st.button("🔄 New Test", type="primary", use_container_width=True):
        reset_test()
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    init_session()
    s = st.session_state.screen
    if   s == "home":    screen_home()
    elif s == "loading": screen_loading()
    elif s == "test":    screen_test()
    elif s == "results": screen_results()
    else:
        st.error(f"Unknown screen: {s}")
        reset_test()


if __name__ == "__main__":
    main()
