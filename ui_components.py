
"""Reusable J.A.N.E. interface helpers."""

import json
import re
import uuid
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components


# --------------------------------------------------
# CHAT MANAGEMENT
# --------------------------------------------------

def make_chat():
    """Create a new chat and make it active."""
    chat_id = str(uuid.uuid4())

    st.session_state.chats[chat_id] = {
        "title": "New conversation",
        "messages": [],
        "created": datetime.now().strftime("%d %b %Y, %H:%M"),
    }

    st.session_state.current_chat = chat_id


def active_chat():
    """Return the active chat, recovering safely if necessary."""
    chats = st.session_state.chats

    if not chats:
        make_chat()
        chats = st.session_state.chats

    current_chat = st.session_state.get("current_chat")

    if current_chat not in chats:
        st.session_state.current_chat = next(iter(chats))

    return chats[st.session_state.current_chat]


def suggest_chat_title(prompt):
    """Create a useful title from the first meaningful message."""
    text = re.sub(r"\s+", " ", str(prompt or "")).strip(
        " \t\r\n.,!?;:"
    )

    if not text:
        return None

    normalized = text.lower()

    greeting = re.match(
        r"^(hi|hello|hey|heya|yo|sup|good morning|good afternoon|"
        r"good evening|how are you|what's up|whats up|thank you|"
        r"thanks)(\b|[!.?, ]|$)",
        normalized,
    )

    if greeting:
        return None

    study_patterns = [
        (
            r"^(?:i am |i'm |im )?(?:studying|study|learning|learn|"
            r"revising|revision of|revise)\s+(?:about\s+|for\s+)?(.+)$",
            "Studying",
        ),
        (r"^(?:explain|teach me|help me understand)\s+(.+)$", "Understanding"),
        (r"^(?:solve|help me solve)\s+(.+)$", "Solving"),
        (r"^(?:research|researching)\s+(.+)$", "Researching"),
        (r"^(?:plan|planning)\s+(.+)$", "Planning"),
        (
            r"^(?:build|building|create|creating|develop|developing)\s+(.+)$",
            "Building",
        ),
    ]

    for pattern, prefix in study_patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)

        if match:
            topic = match.group(1).strip(" .!?;:")

            if topic:
                return f"{prefix} {topic}"[:56].rstrip(" ,.-")

    text = re.sub(
        r"^(please\s+)?(can you|could you|would you|i want you to)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text[:56].rstrip(" ,.-") or None


def update_chat_title(chat, prompt):
    """Ignore greetings and name a chat after its first meaningful prompt."""
    title = str(chat.get("title", "New conversation")).strip()

    generic_titles = {
        "",
        "new conversation",
        "hi",
        "hello",
        "hey",
        "yo",
        "sup",
        "good morning",
        "good afternoon",
        "good evening",
    }

    candidate = suggest_chat_title(prompt)

    if not candidate:
        return

    if title.lower() in generic_titles:
        chat["title"] = candidate


# --------------------------------------------------
# INTELLIGENCE MODE DIALOG
# --------------------------------------------------

INTELLIGENCE_MODES = {
    "General": {
        "icon": "💬",
        "description": (
            "Natural, friendly conversation and direct answers."
        ),
    },
    "Adaptive": {
        "icon": "🧠",
        "description": (
            "Adapts its approach to your intent. The default mode."
        ),
    },
    "Thinker": {
        "icon": "🔎",
        "description": (
            "Deeper analysis for challenging questions and decisions."
        ),
    },
}


@st.dialog("Select the intelligence mode", width="small")
def intelligence_dialog():
    """
    Display a separate Streamlit modal.

    The caller in app.py must invoke this function when the user
    presses the existing intelligence-mode control.
    """
    current_mode = st.session_state.get(
        "intelligence_mode", "Adaptive"
    )

    st.caption("How should J.A.N.E. approach your prompts?")

    for name, details in INTELLIGENCE_MODES.items():
        with st.container(border=True):
            left, right = st.columns(
                [4, 1],
                vertical_alignment="center",
            )

            with left:
                st.markdown(
                    f"**{details['icon']} {name}**"
                )
                st.caption(details["description"])

            with right:
                if current_mode == name:
                    st.markdown("**✓ Active**")
                else:
                    if st.button(
                        "Select",
                        key=f"mode_select_{name}",
                        use_container_width=True,
                    ):
                        st.session_state.intelligence_mode = name
                        st.rerun()

    st.caption(
        f"Current mode: {current_mode}. "
        "Your selection stays active until you change it."
    )


# --------------------------------------------------
# ASSISTANT PERSONALITY DIALOG
# --------------------------------------------------

@st.dialog("Choose J.A.N.E.'s response style", width="small")
def assistant_style_dialog():
    """Choose the assistant's speaking style."""
    options = {
        "Classic": (
            "💬",
            "Natural, friendly, everyday J.A.N.E.",
        ),
        "Jarvis": (
            "🛡️",
            "Formal, disciplined, mission-focused personal assistant.",
        ),
    }

    current_style = st.session_state.get(
        "assistant_style", "Classic"
    )

    st.caption("Choose how J.A.N.E. speaks to you.")

    for name, (icon, description) in options.items():
        with st.container(border=True):
            left, right = st.columns(
                [4, 1],
                vertical_alignment="center",
            )

            with left:
                st.markdown(f"**{icon} {name}**")
                st.caption(description)

            with right:
                if current_style == name:
                    st.markdown("**✓ Active**")
                else:
                    if st.button(
                        "Select",
                        key=f"style_select_{name}",
                        use_container_width=True,
                    ):
                        st.session_state.assistant_style = name
                        st.rerun()

    st.caption(
        "This changes J.A.N.E.'s response style, "
        "not its intelligence mode."
    )


# --------------------------------------------------
# MESSAGE DISPLAY
# --------------------------------------------------

def render_message_content(message):
    """Render a chat message, collapsing long user messages."""
    content = message.get("content", "")

    if message.get("role") == "user":
        lines = content.splitlines() or [content]

        if len(lines) > 7:
            st.markdown(
                "\n".join(lines[:7]).rstrip() + "…"
            )

            with st.expander("See more"):
                st.markdown(content)
        else:
            st.markdown(content)
    else:
        st.markdown(content)


# --------------------------------------------------
# COPY ANSWER CONTROL
# --------------------------------------------------

def render_copy_answer(content, key):
    """Render a copy button for an assistant response."""
    payload = json.dumps(
        content,
        ensure_ascii=False,
    ).replace("</", "<\\/")

    safe_key = re.sub(r"[^a-zA-Z0-9_-]", "_", str(key))

    components.html(
        f"""
        <div style="
            background:transparent;
            padding:2px 0 6px;
        ">
            <button
                id="copy-{safe_key}"
                style="
                    background:#171217;
                    color:#e9e5eb;
                    border:1px solid #49303b;
                    border-radius:8px;
                    padding:6px 11px;
                    font-size:12px;
                    cursor:pointer;
                "
            >⧉ Copy answer</button>

            <span
                id="status-{safe_key}"
                style="
                    margin-left:9px;
                    color:#aaa5b2;
                    font:12px Arial,sans-serif;
                "
            ></span>
        </div>

        <script>
        (() => {{
            const answer = {payload};
            const button = document.getElementById("copy-{safe_key}");
            const status = document.getElementById("status-{safe_key}");

            if (!button || !status) return;

            button.addEventListener("click", async () => {{
                try {{
                    await navigator.clipboard.writeText(answer);
                    status.textContent = "Copied!";
                }} catch (err) {{
                    const area = document.createElement("textarea");
                    area.value = answer;
                    document.body.appendChild(area);
                    area.select();

                    try {{
                        document.execCommand("copy");
                        status.textContent = "Copied!";
                    }} catch (error) {{
                        status.textContent = "Copy unavailable";
                    }}

                    area.remove();
                }}
            }});
        }})();
        </script>
        """,
        height=42,
        scrolling=False,
    )


# --------------------------------------------------
# READ ALOUD CONTROLS
# --------------------------------------------------

def render_speak_controls(content, key):
    """Read replies using browser/device speech synthesis."""
    safe_key = "voice_" + "".join(
        ch if ch.isalnum() else "_"
        for ch in str(key)
    )

    text_payload = json.dumps(
        str(content or "").strip()[:12000],
        ensure_ascii=False,
    ).replace("</", "<\\/")

    speed = float(st.session_state.get("voice_speed", 1.0))

    components.html(
        f"""
        <div style="
            font-family:Arial,sans-serif;
            display:flex;
            gap:8px;
            align-items:center;
            background:transparent;
        ">
            <button
                id="speak-{safe_key}"
                style="
                    background:#a10f2b;
                    color:white;
                    border:0;
                    border-radius:18px;
                    padding:8px 13px;
                    cursor:pointer;
                "
            >🔊 Read aloud</button>

            <button
                id="stop-{safe_key}"
                style="
                    background:#171217;
                    color:#eee;
                    border:1px solid #49303b;
                    border-radius:18px;
                    padding:8px 13px;
                    cursor:pointer;
                "
            >■ Stop</button>
        </div>

        <script>
        (() => {{
            const text = {text_payload};
            const rate = {speed};

            const speak = document.getElementById("speak-{safe_key}");
            const stop = document.getElementById("stop-{safe_key}");

            if (!speak || !stop) return;

            speak.addEventListener("click", () => {{
                if (!text) return;

                if (
                    !("speechSynthesis" in window) ||
                    !("SpeechSynthesisUtterance" in window)
                ) {{
                    return;
                }}

                window.speechSynthesis.cancel();

                const utterance = new SpeechSynthesisUtterance(text);
                utterance.rate = Math.max(0.5, Math.min(3, rate));

                window.speechSynthesis.speak(utterance);
            }});

            stop.addEventListener("click", () => {{
                if ("speechSynthesis" in window) {{
                    window.speechSynthesis.cancel();
                }}
            }});
        }})();
        </script>
        """,
        height=52,
        scrolling=False,
    )
