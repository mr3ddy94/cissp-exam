"""
CISSP Adaptive Practice Exam - Streamlit Web App
=================================================
Deployment: Streamlit Community Cloud (free, permanent URL)
Required:   pip install streamlit anthropic

Run locally:   streamlit run cissp_app.py
Deploy free:   https://streamlit.io/cloud  →  Connect GitHub repo → Deploy

Set your Anthropic API key:
  Local:  Create .streamlit/secrets.toml  →  ANTHROPIC_API_KEY = "sk-ant-..."
  Cloud:  Streamlit Cloud dashboard → App settings → Secrets
"""

# ── Standard library ──────────────────────────────────────────────────────────
import json
import math
import random
import time

# ── Third-party ───────────────────────────────────────────────────────────────
import anthropic
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CISSP Adaptive Practice Exam",
    page_icon="🔐",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN DATA
# ─────────────────────────────────────────────────────────────────────────────
DOMAINS = {
    1: {
        "name": "Security & Risk Management",
        "short": "Risk Mgmt",
        "color": "#e05c5c",
        "topics": [
            "risk frameworks", "BIA", "threat modeling", "ethics",
            "legal regulations", "security policies", "business continuity",
            "risk response strategies", "ALE/ARO/SLE calculations",
            "due care vs due diligence",
        ],
    },
    2: {
        "name": "Asset Security",
        "short": "Asset Sec",
        "color": "#e08c3a",
        "topics": [
            "data classification", "data lifecycle", "ownership roles",
            "data retention", "media sanitization", "privacy protection",
            "data remanence", "scoping and tailoring",
        ],
    },
    3: {
        "name": "Security Architecture & Engineering",
        "short": "Architecture",
        "color": "#c8a820",
        "topics": [
            "security models", "cryptography", "PKI", "security controls",
            "secure design principles", "cloud security", "hardware security",
            "Bell-LaPadula", "Biba", "Clark-Wilson", "TPM", "HSM",
        ],
    },
    4: {
        "name": "Communication & Network Security",
        "short": "Network Sec",
        "color": "#3aae6a",
        "topics": [
            "OSI model", "network protocols", "firewalls", "VPN",
            "wireless security", "network attacks", "secure communication",
            "DMZ", "VLAN", "IPSec", "TLS",
        ],
    },
    5: {
        "name": "Identity & Access Management",
        "short": "IAM",
        "color": "#3a8ae0",
        "topics": [
            "authentication", "authorization", "access control models",
            "identity federation", "SSO", "MFA", "provisioning",
            "Kerberos", "SAML", "OAuth", "RBAC", "MAC", "DAC",
        ],
    },
    6: {
        "name": "Security Assessment & Testing",
        "short": "Assessment",
        "color": "#9b5fcf",
        "topics": [
            "penetration testing", "vulnerability assessment", "security audits",
            "log review", "CVSS", "testing methodologies", "SOC reports",
            "black/gray/white box testing", "OWASP", "bug bounty",
        ],
    },
    7: {
        "name": "Security Operations",
        "short": "Sec Ops",
        "color": "#1aaa8a",
        "topics": [
            "incident response", "forensics", "disaster recovery",
            "backup strategies", "change management", "monitoring",
            "SIEM", "chain of custody", "RTO/RPO", "BCP vs DRP",
        ],
    },
    8: {
        "name": "Software Development Security",
        "short": "Dev Sec",
        "color": "#5080b0",
        "topics": [
            "SDLC", "DevSecOps", "secure coding", "OWASP Top 10",
            "code review", "software testing", "application threats",
            "static vs dynamic analysis", "fuzzing", "input validation",
        ],
    },
}

DIFFICULTIES = {
    "easy": {
        "label": "Foundational",
        "description": "Core definitions and concepts",
        "theta": -1.5,
        "emoji": "🟢",
    },
    "medium": {
        "label": "Applied",
        "description": "Scenario-based application",
        "theta": 0.0,
        "emoji": "🟡",
    },
    "hard": {
        "label": "Expert",
        "description": "Complex multi-factor analysis",
        "theta": 1.5,
        "emoji": "🔴",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# CAT ENGINE  (Item Response Theory — 3-Parameter Logistic Model)
# ─────────────────────────────────────────────────────────────────────────────
class CATEngine:
    """
    Computerized Adaptive Testing engine using a simplified 3PL IRT model.

    θ  = ability estimate  (range: −3 to +3)
    a  = discrimination    (fixed at 1.2 for CISSP items)
    b  = difficulty        (easy=−1.5, medium=0, hard=+1.5)
    c  = pseudo-guessing   (fixed at 0.25 for 4-option MCQ)

    P(correct | θ) = c + (1−c) / (1 + exp(−a(θ−b)))
    """

    def __init__(self, starting_difficulty: str = "medium"):
        self.theta: float = DIFFICULTIES[starting_difficulty]["theta"]
        self.responses: list = []

    def probability(self, b: float, a: float = 1.2, c: float = 0.25) -> float:
        return c + (1 - c) / (1 + math.exp(-a * (self.theta - b)))

    def update(self, difficulty: str, correct: bool) -> None:
        b = DIFFICULTIES[difficulty]["theta"]
        p = self.probability(b)
        step = 0.4 * (1 - p) if correct else -0.4 * p
        self.theta = max(-3.0, min(3.0, self.theta + step))
        self.responses.append(
            {"difficulty": difficulty, "correct": correct, "theta": self.theta}
        )

    def next_difficulty(self) -> str:
        if len(self.responses) < 2:
            return "medium"
        if self.theta >= 0.8:
            return "hard"
        if self.theta <= -0.8:
            return "easy"
        return "medium"

    def ability_label(self) -> tuple:
        if self.theta >= 1.5:
            return "Expert", "#e05c5c"
        if self.theta >= 0.7:
            return "Proficient", "#c8a820"
        if self.theta >= -0.3:
            return "Competent", "#3a8ae0"
        if self.theta >= -1.2:
            return "Developing", "#e08c3a"
        return "Foundational", "#9b5fcf"

    def pass_probability(self) -> int:
        pct = 50 + self.theta * 20
        return max(5, min(97, round(pct)))

    def stats(self) -> dict:
        total = len(self.responses)
        correct = sum(1 for r in self.responses if r["correct"])
        by_diff = {}
        for d in ("easy", "medium", "hard"):
            items = [r for r in self.responses if r["difficulty"] == d]
            by_diff[d] = {
                "total": len(items),
                "correct": sum(1 for r in items if r["correct"]),
            }
        return {
            "total": total,
            "correct": correct,
            "pct": round(correct / total * 100) if total else 0,
            "by_diff": by_diff,
            "theta_history": [0.0] + [r["theta"] for r in self.responses],
        }


# ─────────────────────────────────────────────────────────────────────────────
# CLAUDE AI  — question generation
# ─────────────────────────────────────────────────────────────────────────────
def get_anthropic_client() -> anthropic.Anthropic:
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.error(
            "🔑 **API key not found.**\n\n"
            "Add `ANTHROPIC_API_KEY = \"sk-ant-...\"` to `.streamlit/secrets.toml` "
            "or to Streamlit Cloud → App settings → Secrets."
        )
        st.stop()
    return anthropic.Anthropic(api_key=api_key)


DIFFICULTY_PROMPTS = {
    "easy": (
        "Write a straightforward definitional or recall question testing "
        "foundational CISSP knowledge. The correct answer should be clear "
        "to someone who has studied the basics."
    ),
    "medium": (
        "Write a scenario-based question requiring applied understanding. "
        "Present a realistic organisational situation and ask what the "
        "security professional should do or which concept applies. "
        "Include plausible distractors."
    ),
    "hard": (
        "Write a complex, nuanced question involving trade-offs, competing "
        "priorities, or subtle distinctions that challenges even well-prepared "
        "candidates. All options should seem plausible to an intermediate "
        "student. May involve regulatory constraints or multi-step reasoning."
    ),
}


def generate_question(domain_id: int, difficulty: str, used_topics: list) -> dict:
    client = get_anthropic_client()
    domain = DOMAINS[domain_id]

    available = [t for t in domain["topics"] if t not in used_topics[-4:]]
    topic = random.choice(available if available else domain["topics"])

    prompt = f"""You are a senior CISSP exam question writer.

Domain: {domain_id} — {domain['name']}
Difficulty: {difficulty.upper()} — {DIFFICULTY_PROMPTS[difficulty]}
Topic focus: {topic}

Generate ONE realistic CISSP exam question following these rules:
1. Use CISSP-style phrasing: BEST, MOST, FIRST, PRIMARY where appropriate.
2. Write exactly 4 answer options.
3. Every wrong option must be plausible — never obviously incorrect.
4. The answer field is the 0-based index of the correct option (0=A … 3=D).
5. The explanation must be 3–5 sentences: why the answer is correct AND
   why each distractor is wrong.

Respond ONLY with valid JSON — no markdown fences, no preamble:
{{
  "question": "...",
  "options": ["A text", "B text", "C text", "D text"],
  "answer": 0,
  "explanation": "...",
  "topic": "{topic}"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude returned invalid JSON: {exc}\n\nRaw: {raw}") from exc

    required = {"question", "options", "answer", "explanation", "topic"}
    if not required.issubset(data.keys()):
        raise ValueError(f"Missing keys in response: {required - data.keys()}")
    if len(data["options"]) != 4:
        raise ValueError("Expected exactly 4 options.")
    if data["answer"] not in range(4):
        raise ValueError(f"answer index {data['answer']} out of range 0-3.")

    return {
        "domain_id": domain_id,
        "difficulty": difficulty,
        "topic": data["topic"],
        "question": data["question"],
        "options": data["options"],
        "answer": int(data["answer"]),
        "explanation": data["explanation"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def init_session() -> None:
    defaults = {
        "screen": "home",
        "cat": None,
        "questions": [],
        "current_idx": 0,
        "selected_answer": None,
        "show_explanation": False,
        "flagged": set(),
        "config": {},
        "start_time": None,
        "elapsed": 0,
        "domain_cycle": 0,
        "used_topics": [],
        "q_answered": [],
        "error_msg": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def reset_test() -> None:
    keys_to_clear = [
        "cat", "questions", "current_idx", "selected_answer",
        "show_explanation", "flagged", "start_time", "elapsed",
        "domain_cycle", "used_topics", "q_answered", "error_msg",
    ]
    for k in keys_to_clear:
        if k in st.session_state:
            del st.session_state[k]
    st.session_state.screen = "home"


# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.stApp { background-color: #0d0f16; color: #e4e7f0; }

section[data-testid="stSidebar"] {
    background-color: #13161f;
    border-right: 1px solid #22263a;
}

.card {
    background: #13161f;
    border: 1px solid #22263a;
    border-radius: 14px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
}

.domain-badge {
    display: inline-block;
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 700;
    margin-right: 6px;
}

div[data-testid="stProgress"] > div > div { background-color: #3b6bfa !important; }

[data-testid="stMetricValue"] { font-size: 2.5rem !important; font-weight: 900 !important; }

.correct   { color: #27ae60; }
.incorrect { color: #e05c5c; }

h1, h2, h3 { color: #e4e7f0; }
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# SCREENS
# ─────────────────────────────────────────────────────────────────────────────

def screen_home() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown("# 🔐 CISSP Adaptive Practice Exam")
    st.markdown(
        "_Computerized Adaptive Testing powered by **Claude AI**. "
        "Questions are generated live and adapt to your performance._"
    )
    st.divider()

    with st.sidebar:
        st.markdown("## ⚙️ Test Configuration")

        st.markdown("### 📚 Domains")
        select_all = st.checkbox("Select all domains", value=True)
        selected_domains = []
        for did, info in DOMAINS.items():
            checked = st.checkbox(
                f"D{did}: {info['short']}",
                value=select_all,
                key=f"domain_{did}",
            )
            if checked:
                selected_domains.append(did)

        st.markdown("### 🎯 Questions")
        q_count = st.select_slider(
            "Number of questions",
            options=[10, 15, 25, 50, 75],
            value=25,
        )

        st.markdown("### 📈 Starting Level")
        start_diff = st.radio(
            "CAT will adapt from here",
            options=["easy", "medium", "hard"],
            index=1,
            format_func=lambda d: f"{DIFFICULTIES[d]['emoji']} {DIFFICULTIES[d]['label']}",
        )

        st.markdown("### ⏱ Timer")
        timed = st.toggle("Enable timer", value=True)
        if timed:
            timer_hours = st.select_slider(
                "Time limit (hours)",
                options=[1, 2, 3, 4],
                value=3,
            )
        else:
            timer_hours = None

        st.divider()
        start_clicked = st.button(
            "🚀 Start Adaptive Test",
            type="primary",
            use_container_width=True,
            disabled=len(selected_domains) == 0,
        )

    col1, col2, col3 = st.columns(3)
    col1.metric("8 CISSP Domains", "Covered")
    col2.metric("CAT Algorithm", "IRT 3-PL")
    col3.metric("Questions", "AI Generated")

    st.markdown("---")
    st.markdown("### 🧠 How Adaptive Testing Works")
    st.info(
        "Each question is **generated live by Claude AI** at a difficulty tuned to "
        "your current ability estimate (θ). Answer correctly → harder question. "
        "Answer incorrectly → recalibrated level. The system uses the "
        "**3-Parameter Logistic IRT model** to find the difficulty where you have "
        "~65% probability of success — the optimal zone for measurement accuracy."
    )

    st.markdown("### 📋 CISSP Domains")
    for did, info in DOMAINS.items():
        with st.expander(f"**D{did}: {info['name']}**"):
            st.write(", ".join(info["topics"]))

    if start_clicked:
        if not selected_domains:
            st.error("Please select at least one domain.")
            return
        st.session_state.config = {
            "selected_domains": selected_domains,
            "q_count": q_count,
            "start_diff": start_diff,
            "timed": timed,
            "timer_secs": timer_hours * 3600 if timed else None,
        }
        st.session_state.cat = CATEngine(start_diff)
        st.session_state.questions = []
        st.session_state.current_idx = 0
        st.session_state.selected_answer = None
        st.session_state.show_explanation = False
        st.session_state.flagged = set()
        st.session_state.domain_cycle = 0
        st.session_state.used_topics = []
        st.session_state.q_answered = []
        st.session_state.start_time = time.time()
        st.session_state.screen = "loading"
        st.rerun()


def screen_loading() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown("## ⏳ Generating your first question…")
    with st.spinner("Claude AI is crafting a personalised question…"):
        _load_next_question()
    st.session_state.screen = "test"
    st.rerun()


def _pick_domain() -> int:
    cfg = st.session_state.config
    domains = cfg["selected_domains"]
    idx = st.session_state.domain_cycle % len(domains)
    st.session_state.domain_cycle += 1
    return domains[idx]


def _load_next_question() -> bool:
    cat: CATEngine = st.session_state.cat
    difficulty = cat.next_difficulty()
    domain_id = _pick_domain()
    try:
        q = generate_question(domain_id, difficulty, st.session_state.used_topics)
        st.session_state.questions.append(q)
        if q.get("topic"):
            st.session_state.used_topics.append(q["topic"])
        st.session_state.selected_answer = None
        st.session_state.show_explanation = False
        st.session_state.error_msg = None
        return True
    except Exception as exc:
        st.session_state.error_msg = str(exc)
        return False


def _format_time(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def screen_test() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    cat: CATEngine = st.session_state.cat
    cfg = st.session_state.config
    questions = st.session_state.questions
    current_idx = st.session_state.current_idx

    if current_idx >= len(questions):
        st.warning("Generating question…")
        with st.spinner():
            _load_next_question()
        st.rerun()

    q = questions[current_idx]
    total_q = cfg["q_count"]
    answered = st.session_state.selected_answer is not None
    ability_label, ability_color = cat.ability_label()

    col_prog, col_timer, col_finish = st.columns([4, 2, 1])

    with col_prog:
        progress = (current_idx + (1 if answered else 0)) / total_q
        st.progress(progress)
        st.caption(
            f"Q{current_idx + 1} of {total_q}  ·  "
            f"θ = {cat.theta:.2f}  ·  "
            f"**{ability_label}**"
        )

    with col_timer:
        if cfg["timed"] and cfg["timer_secs"]:
            elapsed = int(time.time() - st.session_state.start_time)
            remaining = cfg["timer_secs"] - elapsed
            if remaining <= 0:
                st.session_state.screen = "results"
                st.rerun()
            colour = "🔴" if remaining < 600 else "🟡" if remaining < 1800 else "🟢"
            st.markdown(f"**{colour} {_format_time(remaining)}**")
        else:
            elapsed = int(time.time() - st.session_state.start_time)
            st.caption(f"⏱ {_format_time(elapsed)}")

    with col_finish:
        if st.button("Finish", type="secondary"):
            st.session_state.elapsed = int(time.time() - st.session_state.start_time)
            st.session_state.screen = "results"
            st.rerun()

    st.divider()

    domain_info = DOMAINS[q["domain_id"]]
    diff_info = DIFFICULTIES[q["difficulty"]]

    badge_html = (
        f'<span class="domain-badge" style="background:{domain_info["color"]}22;'
        f'color:{domain_info["color"]};border:1px solid {domain_info["color"]}55;">'
        f'D{q["domain_id"]}: {domain_info["short"]}</span>'
        f'<span class="domain-badge" style="background:#22263a;color:#aaa;">'
        f'{diff_info["emoji"]} {diff_info["label"]}</span>'
    )
    if q.get("topic"):
        badge_html += (
            f'<span class="domain-badge" style="background:#22263a;color:#888;">'
            f'{q["topic"]}</span>'
        )
    st.markdown(badge_html, unsafe_allow_html=True)

    flag_col, _ = st.columns([1, 9])
    with flag_col:
        flagged_set: set = st.session_state.flagged
        is_flagged = current_idx in flagged_set
        if st.button("🚩" if is_flagged else "⬜ Flag"):
            if is_flagged:
                flagged_set.discard(current_idx)
            else:
                flagged_set.add(current_idx)
            st.rerun()

    st.markdown(f"### {q['question']}")
    st.write("")

    letters = ["A", "B", "C", "D"]

    if not answered:
        for i, option in enumerate(q["options"]):
            if st.button(f"**{letters[i]}.** {option}", key=f"opt_{i}", use_container_width=True):
                st.session_state.selected_answer = i
                correct = i == q["answer"]
                cat.update(q["difficulty"], correct)
                st.session_state.q_answered.append(correct)
                st.session_state.show_explanation = True
                st.rerun()
    else:
        sel = st.session_state.selected_answer
        for i, option in enumerate(q["options"]):
            if i == q["answer"]:
                st.success(f"**{letters[i]}.** {option}  ✓")
            elif i == sel:
                st.error(f"**{letters[i]}.** {option}  ✗ (your answer)")
            else:
                st.markdown(f"**{letters[i]}.** {option}")

    if st.session_state.show_explanation:
        sel = st.session_state.selected_answer
        is_correct = sel == q["answer"]

        if is_correct:
            st.success("✅ **Correct!**")
        else:
            st.error(
                f"❌ **Incorrect.** Correct answer: **{letters[q['answer']]}**"
            )

        with st.expander("📖 Detailed Explanation (AI-generated)", expanded=True):
            st.write(q["explanation"])

        new_label, new_color = cat.ability_label()
        st.info(
            f"**Ability updated** · θ = {cat.theta:.2f} · **{new_label}**  "
            f"| Next question: **{DIFFICULTIES[cat.next_difficulty()]['label']}** level"
        )

    st.divider()
    nav_left, nav_right = st.columns([1, 1])

    with nav_left:
        if current_idx > 0 and st.button("← Previous", use_container_width=True):
            st.session_state.current_idx -= 1
            st.session_state.selected_answer = st.session_state.questions[
                st.session_state.current_idx
            ].get("_user_answer")
            st.session_state.show_explanation = st.session_state.selected_answer is not None
            st.rerun()

    with nav_right:
        if answered:
            if current_idx + 1 >= total_q:
                if st.button("🏁 View Results →", type="primary", use_container_width=True):
                    st.session_state.elapsed = int(time.time() - st.session_state.start_time)
                    st.session_state.screen = "results"
                    st.rerun()
            else:
                if st.button("Next Question →", type="primary", use_container_width=True):
                    st.session_state.questions[current_idx]["_user_answer"] = (
                        st.session_state.selected_answer
                    )
                    next_idx = current_idx + 1
                    st.session_state.current_idx = next_idx
                    if next_idx >= len(questions):
                        with st.spinner("Generating next question…"):
                            _load_next_question()
                    else:
                        prev_q = questions[next_idx]
                        st.session_state.selected_answer = prev_q.get("_user_answer")
                        st.session_state.show_explanation = (
                            st.session_state.selected_answer is not None
                        )
                    st.rerun()

    if st.session_state.get("error_msg"):
        st.error(f"⚠️ {st.session_state.error_msg}")
        if st.button("Retry"):
            _load_next_question()
            st.rerun()

    with st.sidebar:
        st.markdown("### 📋 Navigator")
        cols = st.columns(5)
        for i in range(len(questions)):
            c = cols[i % 5]
            answered_i = i < len(st.session_state.q_answered)
            correct_i = st.session_state.q_answered[i] if answered_i else None
            label = str(i + 1)
            if i == current_idx:
                c.markdown(f"**[{label}]**")
            elif correct_i is True:
                c.markdown(f"✅{label}")
            elif correct_i is False:
                c.markdown(f"❌{label}")
            elif i in st.session_state.flagged:
                c.markdown(f"🚩{label}")
            else:
                c.markdown(f"_{label}_")

        st.divider()
        st.markdown("**Legend**")
        st.markdown("✅ Correct  ❌ Incorrect  🚩 Flagged")
        st.divider()
        if st.button("🏠 Back to Home", use_container_width=True):
            reset_test()
            st.rerun()


def screen_results() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    cat: CATEngine = st.session_state.cat
    questions = st.session_state.questions
    elapsed = st.session_state.get("elapsed", 0)

    stats = cat.stats()
    ability_label, ability_color = cat.ability_label()
    pass_prob = cat.pass_probability()

    st.markdown("# 🎓 Results")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Score", f"{stats['pct']}%")
    c2.metric("Correct", f"{stats['correct']}/{stats['total']}")
    c3.metric("Ability", ability_label)
    c4.metric("θ Estimate", f"{cat.theta:.2f}")

    if pass_prob >= 65:
        st.success(f"🎯 **Estimated CISSP pass probability: {pass_prob}%** — On track!")
    else:
        st.warning(f"📚 **Estimated CISSP pass probability: {pass_prob}%** — Keep studying!")

    st.caption(f"Time taken: {_format_time(elapsed)}")
    st.divider()

    st.markdown("### 📈 Ability Progression (θ)")
    theta_hist = stats["theta_history"]
    st.line_chart({"θ (ability estimate)": theta_hist})
    st.caption(
        "θ < −1: Foundational  |  −1 to 0: Developing  |  "
        "0 to +1: Competent  |  +1 to +1.5: Proficient  |  > +1.5: Expert"
    )

    st.divider()
    st.markdown("### 🎯 Performance by Difficulty")
    d_cols = st.columns(3)
    for ci, dk in enumerate(("easy", "medium", "hard")):
        info = stats["by_diff"][dk]
        pct = round(info["correct"] / info["total"] * 100) if info["total"] else 0
        d_cols[ci].metric(
            DIFFICULTIES[dk]["label"],
            f"{info['correct']}/{info['total']}",
            f"{pct}%",
        )

    st.divider()
    st.markdown("### 📚 Performance by Domain")
    domain_stats: dict = {}
    for i, q in enumerate(questions):
        did = q["domain_id"]
        if did not in domain_stats:
            domain_stats[did] = {"total": 0, "correct": 0}
        domain_stats[did]["total"] += 1
        if i < len(cat.responses) and cat.responses[i]["correct"]:
            domain_stats[did]["correct"] += 1

    for did, ds in sorted(domain_stats.items()):
        pct = round(ds["correct"] / ds["total"] * 100) if ds["total"] else 0
        st.progress(
            pct / 100,
            text=f"D{did}: {DOMAINS[did]['short']} — {ds['correct']}/{ds['total']} ({pct}%)"
        )

    st.divider()
    st.markdown("### 🔍 Question-by-Question Review")
    filter_opt = st.radio(
        "Show:", ["All", "Correct only", "Incorrect only"], horizontal=True
    )

    for i, q in enumerate(questions):
        if i >= len(cat.responses):
            break
        correct = cat.responses[i]["correct"]
        if filter_opt == "Correct only" and not correct:
            continue
        if filter_opt == "Incorrect only" and correct:
            continue

        domain_info = DOMAINS[q["domain_id"]]
        diff_info = DIFFICULTIES[q["difficulty"]]
        icon = "✅" if correct else "❌"

        with st.expander(
            f"{icon} Q{i + 1} · D{q['domain_id']}: {domain_info['short']} · "
            f"{diff_info['label']} · {q.get('topic', '')}"
        ):
            st.markdown(f"**{q['question']}**")
            st.write("")
            letters = ["A", "B", "C", "D"]
            for j, opt in enumerate(q["options"]):
                if j == q["answer"]:
                    st.success(f"**{letters[j]}.** {opt}  ✓ Correct")
                else:
                    st.markdown(f"**{letters[j]}.** {opt}")
            st.divider()
            st.markdown("**🤖 AI Explanation:**")
            st.write(q["explanation"])

    st.divider()
    if st.button("🔄 Start New Adaptive Test", type="primary", use_container_width=True):
        reset_test()
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    init_session()
    screen = st.session_state.screen

    if screen == "home":
        screen_home()
    elif screen == "loading":
        screen_loading()
    elif screen == "test":
        screen_test()
    elif screen == "results":
        screen_results()
    else:
        st.error(f"Unknown screen: {screen}")
        reset_test()


if __name__ == "__main__":
    main()
