"""Reusable J.A.N.E. interface helpers. Extracted from the verified app source."""
import json
import uuid
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components

def make_chat():
    chat_id = str(uuid.uuid4())
    st.session_state.chats[chat_id] = {"title": "New conversation", "messages": [], "created": datetime.now().strftime("%d %b %Y, %H:%M")}
    st.session_state.current_chat = chat_id


def active_chat():
    if st.session_state.current_chat not in st.session_state.chats:
        st.session_state.current_chat = next(iter(st.session_state.chats))
    return st.session_state.chats[st.session_state.current_chat]


def suggest_chat_title(prompt):
    """Create a useful, human-readable title from the first substantive message."""
    import re

    text = re.sub(r"\s+", " ", str(prompt or "")).strip(" \t\r\n.,!?;:")
    if not text:
        return None

    # Greetings and conversational openers should never become chat titles.
    normalized = text.lower()
    greeting = re.match(
        r"^(hi|hello|hey|heya|yo|sup|good morning|good afternoon|good evening|how are you|what's up|whats up|thank you|thanks)(\b|[!.?, ]|$)",
        normalized,
    )
    if greeting:
        return None

    # Make common study/learning conversations feel like purposeful sessions.
    study_patterns = [
        (r"^(?:i am |i'm |im )?(?:studying|study|learning|learn|revising|revision of|revise)\s+(?:about\s+|for\s+)?(.+)$", "Studying"),
        (r"^(?:explain|teach me|help me understand)\s+(.+)$", "Understanding"),
        (r"^(?:solve|help me solve)\s+(.+)$", "Solving"),
        (r"^(?:research|researching)\s+(.+)$", "Researching"),
        (r"^(?:plan|planning)\s+(.+)$", "Planning"),
        (r"^(?:build|building|create|creating|develop|developing)\s+(.+)$", "Building"),
    ]
    for pattern, prefix in study_patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            topic = match.group(1).strip(" .!?;:")
            if topic:
                title = f"{prefix} {topic}"
                return title[:56].rstrip(" ,.-")

    # Use the meaningful prompt itself, with enough room to identify its topic.
    text = re.sub(r"^(please\s+)?(can you|could you|would you|i want you to)\s+", "", text, flags=re.IGNORECASE)
    return text[:56].rstrip(" ,.-") or None


def update_chat_title(chat, prompt):
    """Ignore greetings; allow the first meaningful message to name the chat."""
    title = str(chat.get("title", "New conversation")).strip()
    generic_titles = {"", "new conversation", "hi", "hello", "hey", "yo", "sup", "good morning", "good afternoon", "good evening"}
    # Also repair older sessions that were titled from a greeting.
    candidate = suggest_chat_title(prompt)
    if not candidate:
        return
    if title.lower() in generic_titles:
        chat["title"] = candidate


def intelligence_dialog():
    st.caption("How should J.A.N.E. approach your prompts?")
    descriptions = {
        "General": "Natural, friendly conversation and direct answers.",
        "Adaptive": "Automatically adapts its style to your intent. The default mode.",
        "Thinker": "Deeper analysis for challenging questions and decisions.",
    }
    icons = {"General": "💬", "Adaptive": "🧠", "Thinker": "🔎"}
    for name in ("General", "Adaptive", "Thinker"):
        with st.container(border=True):
            left, right = st.columns([5, 1])
            with left:
                st.markdown(f"**{icons[name]} {name}**")
                st.caption(descriptions[name])
            with right:
                if st.session_state.intelligence_mode == name:
                    st.markdown("**✓ Active**")
                elif st.button("Select", key=f"mode_select_{name}", use_container_width=True):
                    st.session_state.intelligence_mode = name
                    st.rerun()
    st.caption("Your choice stays active until you change it.")


def assistant_style_dialog():
    st.caption("Choose how J.A.N.E. speaks to you.")
    options = {
        "Classic": ("💬", "Natural, friendly, everyday J.A.N.E."),
        "Jarvis": ("🛡️", "Formal, disciplined, mission-focused personal assistant."),
    }
    for name in ("Classic", "Jarvis"):
        icon, description = options[name]
        with st.container(border=True):
            left, right = st.columns([5, 1])
            with left:
                st.markdown(f"**{icon} {name}**")
                st.caption(description)
            with right:
                if st.session_state.assistant_style == name:
                    st.markdown("**✓ Active**")
                elif st.button("Select", key=f"style_select_{name}", use_container_width=True):
                    st.session_state.assistant_style = name
                    st.rerun()
    st.caption("This changes J.A.N.E.'s response style, not its intelligence mode.")


def render_message_content(message):
    content = message.get("content", "")
    if message.get("role") == "user":
        lines = content.splitlines() or [content]
        if len(lines) > 7:
            st.markdown("\n".join(lines[:7]).rstrip() + "…")
            with st.expander("See more"):
                st.markdown(content)
        else:
            st.markdown(content)
    else:
        st.markdown(content)


def render_copy_answer(content, key):
    payload = json.dumps(content, ensure_ascii=False).replace("</", "<\\/")
    components.html(f'''<div style="background:transparent;padding:2px 0 6px"><button id="copy-{key}" style="background:#171217;color:#e9e5eb;border:1px solid #49303b;border-radius:8px;padding:6px 11px;font-size:12px;cursor:pointer">⧉ Copy answer</button><span id="status-{key}" style="margin-left:9px;color:#aaa5b2;font:12px Arial,sans-serif"></span></div>
<script>
const answer={payload};const button=document.getElementById("copy-{key}");const status=document.getElementById("status-{key}");
button.addEventListener("click",async()=>{{try{{await navigator.clipboard.writeText(answer);status.textContent="Copied!";}}catch(err){{const area=document.createElement("textarea");area.value=answer;document.body.appendChild(area);area.select();try{{document.execCommand("copy");status.textContent="Copied!";}}catch(e){{status.textContent="Copy unavailable";}}area.remove();}}}});
</script>''', height=42, scrolling=False)


def render_speak_controls(content, key):
    """Read replies with browser/device speech synthesis, without a TTS API call."""
    safe_key = "voice_" + "".join(ch if ch.isalnum() else "_" for ch in str(key))
    text_payload = json.dumps(str(content or "").strip()[:12000], ensure_ascii=False).replace("</", "<\\/")
    speed = float(st.session_state.get("voice_speed", 1.0))
    components.html(f'''<div style="font-family:Arial,sans-serif;display:flex;gap:8px;align-items:center;background:transparent">
<button id="speak-{safe_key}" style="background:#a10f2b;color:white;border:0;border-radius:18px;padding:8px 13px;cursor:pointer">🔊 Read aloud</button>
<button id="stop-{safe_key}" style="background:#171217;color:#eee;border:1px solid #49303b;border-radius:18px;padding:8px 13px;cursor:pointer">■ Stop</button>
</div>
<script>
(()=>{{
 const text={text_payload};
 const rate={speed};
 const speak=document.getElementById("speak-{safe_key}");
 const stop=document.getElementById("stop-{safe_key}");
 speak.addEventListener("click",()=>{{
   if(!text)return;
   if(!("speechSynthesis" in window)||!("SpeechSynthesisUtterance" in window))return;
   window.speechSynthesis.cancel();
   const utterance=new SpeechSynthesisUtterance(text);
   utterance.rate=Math.max(0.5,Math.min(3,rate));
   window.speechSynthesis.speak(utterance);
 }});
 stop.addEventListener("click",()=>{{if("speechSynthesis" in window)window.speechSynthesis.cancel();}});
}})();
</script>''', height=52, scrolling=False)
