"""
CISSP Adaptive Practice Exam - Streamlit Web App
=================================================
Deploy on Streamlit Community Cloud (free)
Requires: streamlit, anthropic
Secret:   ANTHROPIC_API_KEY = "sk-ant-..."
"""

import json
import math
import random
import time

import anthropic
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
        return "Foundational", "#9b5fcf"

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
# CLAUDE API  — robust question generation with retries
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_client():
    """Create the Anthropic client once and reuse it."""
    try:
        key = st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        st.error(
            "🔑 **API key missing.** "
            "Go to your Streamlit dashboard → app ⋯ → Settings → Secrets "
            "and add:  ANTHROPIC_API_KEY = \"sk-ant-...\""
        )
        st.stop()
    return anthropic.Anthropic(api_key=key)


def generate_question(domain_id, difficulty, used_topics, attempt=1):
    """
    Generate one CISSP question via Claude.
    Retries up to 3 times on failure with a short pause between attempts.
    """
    domain = DOMAINS[domain_id]
    recent = used_topics[-4:] if len(used_topics) >= 4 else used_topics
    available = [t for t in domain["topics"] if t not in recent]
    topic = random.choice(available if available else domain["topics"])

    diff_guide = {
        "easy":   "A basic recall or definition question. The correct answer is clear to anyone who has read the study material.",
        "medium": "A scenario-based question. Describe a realistic workplace situation and ask what the security professional should do.",
        "hard":   "A complex question with competing priorities or subtle distinctions. Every option should look plausible.",
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
        f"Reply with ONLY this JSON and nothing else:\n"
        f'{{"question":"...","options":["A","B","C","D"],"answer":0,"explanation":"...","topic":"{topic}"}}'
    )

    max_attempts = 3
    last_error = None

    for attempt_num in range(1, max_attempts + 1):
        try:
            client = get_client()
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",   # faster + cheaper than Sonnet
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text.strip()
            # Strip any accidental markdown fences
            raw = raw.replace("```json", "").replace("```", "").strip()
            # Sometimes Claude adds a sentence before the JSON — find the first {
            if not raw.startswith("{"):
                idx = raw.find("{")
                if idx != -1:
                    raw = raw[idx:]

            data = json.loads(raw)

            # Validate
            assert "question"    in data, "missing question"
            assert "options"     in data, "missing options"
            assert "answer"      in data, "missing answer"
            assert "explanation" in data, "missing explanation"
            assert len(data["options"]) == 4, "need exactly 4 options"
            assert data["answer"] in (0, 1, 2, 3), "answer must be 0-3"

            return {
                "domain_id":   domain_id,
                "difficulty":  difficulty,
                "topic":       data.get("topic", topic),
                "question":    data["question"],
                "options":     data["options"],
                "answer":      int(data["answer"]),
                "explanation": data["explanation"],
            }

        except Exception as e:
            last_error = str(e)
            if attempt_num < max_attempts:
                time.sleep(1.5)   # short pause before retrying
            continue

    # All attempts failed — raise so the caller can show an error
    raise RuntimeError(
        f"Could not generate question after {max_attempts} attempts. "
        f"Last error: {last_error}"
    )

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
        "q_answered":       [],
        "error_msg":        None,
        "generating":       False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def reset_test():
    for k in ["cat","questions","current_idx","selected_answer","show_explanation",
              "flagged","start_time","elapsed","domain_cycle","used_topics",
              "q_answered","error_msg","generating"]:
        st.session_state.pop(k, None)
    st.session_state.screen = "home"

def _pick_domain():
    domains = st.session_state.config["selected_domains"]
    idx = st.session_state.domain_cycle % len(domains)
    st.session_state.domain_cycle += 1
    return domains[idx]

def _load_next_question():
    """Generate the next question. Returns True on success, False on failure."""
    cat = st.session_state.cat
    difficulty  = cat.next_difficulty()
    domain_id   = _pick_domain()
    try:
        q = generate_question(domain_id, difficulty, st.session_state.used_topics)
        st.session_state.questions.append(q)
        if q.get("topic"):
            st.session_state.used_topics.append(q["topic"])
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
# CSS
# ─────────────────────────────────────────────────────────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background-color: #0d0f16; color: #e4e7f0; }
section[data-testid="stSidebar"] { background-color: #13161f; border-right: 1px solid #22263a; }
div[data-testid="stProgress"] > div > div { background-color: #3b6bfa !important; }
[data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 900 !important; }
h1, h2, h3 { color: #e4e7f0; }
.badge {
    display: inline-block; border-radius: 6px;
    padding: 3px 10px; font-size: 12px; font-weight: 700; margin-right: 6px;
}
</style>
"""

# ─────────────────────────────────────────────────────────────────────────────
# SCREEN — HOME
# ─────────────────────────────────────────────────────────────────────────────
def screen_home():
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown("# 🔐 CISSP Adaptive Practice Exam")
    st.markdown("*AI-generated questions that adapt in real time to your ability level.*")
    st.divider()

    with st.sidebar:
        st.markdown("## ⚙️ Configuration")

        st.markdown("### 📚 Domains")
        all_selected = st.checkbox("All domains", value=True, key="chk_all")
        selected_domains = []
        for did, info in DOMAINS.items():
            if st.checkbox(f"D{did}: {info['short']}", value=all_selected, key=f"d_{did}"):
                selected_domains.append(did)

        st.markdown("### 🎯 Questions")
        q_count = st.select_slider("How many questions?",
                                   options=[10, 15, 25, 50, 75], value=25)

        st.markdown("### 📈 Starting difficulty")
        start_diff = st.radio("CAT adapts from here",
                              ["easy", "medium", "hard"], index=1,
                              format_func=lambda d: f"{DIFFICULTIES[d]['emoji']} {DIFFICULTIES[d]['label']}")

        st.markdown("### ⏱ Timer")
        timed = st.toggle("Enable countdown timer", value=True)
        timer_hours = st.select_slider("Hours", options=[1,2,3,4], value=3) if timed else None

        st.divider()
        go = st.button("🚀 Start Test", type="primary",
                       use_container_width=True,
                       disabled=len(selected_domains) == 0)

    # Info cards
    c1, c2, c3 = st.columns(3)
    c1.metric("Domains", "8 covered")
    c2.metric("Algorithm", "IRT 3-PL CAT")
    c3.metric("Questions", "AI generated")

    st.info(
        "**How it works:** Every question is written live by Claude AI at a difficulty "
        "matched to your current ability estimate (θ). Get one right → harder next question. "
        "Get one wrong → recalibrated. The goal is always ~65% success rate — "
        "the sweet spot for accurate measurement."
    )

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
        }
        st.session_state.cat          = CATEngine(start_diff)
        st.session_state.questions    = []
        st.session_state.current_idx  = 0
        st.session_state.domain_cycle = 0
        st.session_state.used_topics  = []
        st.session_state.q_answered   = []
        st.session_state.flagged      = set()
        st.session_state.start_time   = time.time()
        st.session_state.screen       = "loading"
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# SCREEN — LOADING (generates first question)
# ─────────────────────────────────────────────────────────────────────────────
def screen_loading():
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown("## ⏳ Preparing your test…")

    cfg    = st.session_state.config
    domains = cfg["selected_domains"]
    names  = [f"D{d}: {DOMAINS[d]['short']}" for d in domains]
    st.write(f"**Selected domains:** {', '.join(names)}")
    st.write(f"**Questions:** {cfg['q_count']}  ·  **Starting level:** {DIFFICULTIES[cfg['start_diff']]['label']}")

    with st.spinner("Claude is writing your first question — this takes 5–10 seconds…"):
        ok = _load_next_question()

    if ok:
        st.session_state.screen = "test"
        st.rerun()
    else:
        st.error(f"Failed to generate question: {st.session_state.error_msg}")
        st.write("**Common fixes:**")
        st.write("- Check your API key is saved correctly in Streamlit Secrets")
        st.write("- Make sure your Anthropic account has credits")
        st.write("- Try clicking Retry below")
        if st.button("🔄 Retry"):
            st.rerun()
        if st.button("← Back to Home"):
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

    # Safety: generate question if somehow missing
    if idx >= len(questions):
        with st.spinner("Generating question…"):
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
    st.markdown(
        f'<span class="badge" style="background:{d_info["color"]}22;color:{d_info["color"]};'
        f'border:1px solid {d_info["color"]}55;">D{q["domain_id"]}: {d_info["short"]}</span>'
        f'<span class="badge" style="background:#22263a;color:#aaa;">'
        f'{dif_info["emoji"]} {dif_info["label"]}</span>'
        + (f'<span class="badge" style="background:#22263a;color:#777;">{q["topic"]}</span>'
           if q.get("topic") else ""),
        unsafe_allow_html=True,
    )

    # Flag toggle
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

    # ── Options ───────────────────────────────────────────────────────────
    if not answered:
        for i, opt in enumerate(q["options"]):
            if st.button(f"**{letters[i]}.** {opt}", key=f"opt_{i}",
                         use_container_width=True):
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
            f"Next question will be: **{DIFFICULTIES[next_diff]['label']}**"
        )

    # ── Navigation ────────────────────────────────────────────────────────
    st.divider()
    nl, nr = st.columns(2)

    with nl:
        if idx > 0 and st.button("← Previous", use_container_width=True):
            st.session_state.current_idx      -= 1
            prev_q = questions[st.session_state.current_idx]
            st.session_state.selected_answer  = prev_q.get("_user_answer")
            st.session_state.show_explanation = prev_q.get("_user_answer") is not None
            st.rerun()

    with nr:
        if answered:
            is_last = (idx + 1 >= total_q)
            label   = "🏁 See Results" if is_last else "Next Question →"
            if st.button(label, type="primary", use_container_width=True):
                questions[idx]["_user_answer"] = st.session_state.selected_answer
                if is_last:
                    st.session_state.elapsed = int(time.time() - st.session_state.start_time)
                    st.session_state.screen  = "results"
                    st.rerun()
                else:
                    st.session_state.current_idx += 1
                    nxt = st.session_state.current_idx
                    if nxt >= len(questions):
                        with st.spinner("Generating next question…"):
                            ok = _load_next_question()
                        if not ok:
                            st.error(f"⚠️ {st.session_state.error_msg}")
                            st.write("Click the button again to retry.")
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

    st.markdown("### 📈 Ability (θ) over time")
    st.line_chart({"θ": stats["theta_history"]})
    st.caption("Below −1 = Foundational · −1 to 0 = Developing · 0 to +1 = Competent · Above +1 = Proficient/Expert")

    st.divider()
    st.markdown("### 🎯 By Difficulty")
    dc = st.columns(3)
    for ci, dk in enumerate(("easy", "medium", "hard")):
        inf = stats["by_diff"][dk]
        pct = round(inf["correct"] / inf["total"] * 100) if inf["total"] else 0
        dc[ci].metric(DIFFICULTIES[dk]["label"], f"{inf['correct']}/{inf['total']}", f"{pct}%")

    st.divider()
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

        with st.expander(
            f"{icon} Q{i+1} · D{q['domain_id']}: {d_info['short']} · "
            f"{di_info['label']} · {q.get('topic','')}"
        ):
            st.markdown(f"**{q['question']}**")
            st.write("")
            for j, opt in enumerate(q["options"]):
                letters = ["A","B","C","D"]
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
