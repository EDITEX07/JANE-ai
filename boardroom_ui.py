"""J.A.N.E. Boardroom Mode UI (standalone Streamlit module).

Import render_boardroom() from this file when integrating with the main app.
This module provides the interface and interaction state; it does not call an
LLM or modify the existing app.py.
"""

from __future__ import annotations

from typing import Any, Callable
from html import escape
import base64

import streamlit as st
import streamlit.components.v1 as components

try:
    from boardroom_agents import ACCENT_COLOR, get_boardroom_roster
except ImportError as exc:  # Helpful message when the two modules aren't together.
    raise ImportError(
        "boardroom_ui.py requires boardroom_agents.py in the same project folder."
    ) from exc


ACCENT = ACCENT_COLOR
DARK = "#08080b"
PANEL = "#111116"
MUTED = "#a7a7b2"


def _inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{ background: radial-gradient(circle at 50% -20%, #321018 0%, {DARK} 46%); }}
        .br-wrap {{ max-width: 1180px; margin: 0 auto; }}
        .br-eyebrow {{ color: {ACCENT}; font-size: .72rem; letter-spacing: .22em;
                       font-weight: 800; text-transform: uppercase; }}
        .br-heading {{ color: #fff; font-size: clamp(2rem, 5vw, 3.1rem);
                       font-weight: 850; letter-spacing: -.045em; margin: .15rem 0 0; }}
        .br-subtitle {{ color: {MUTED}; margin: .2rem 0 1.35rem; font-size: .94rem; }}
        .br-section {{ color: #fff; font-size: 1.05rem; font-weight: 750;
                       margin: 1.1rem 0 .7rem; }}
        .br-card {{ background: linear-gradient(145deg, #17171e, #0c0c11);
                    border: 1px solid #303039; border-radius: 15px; padding: 13px 12px;
                    min-height: 145px; text-align: center; transition: .2s ease; }}
        .br-card.active {{ border: 1px solid {ACCENT};
                    box-shadow: 0 0 0 1px {ACCENT}55, 0 0 22px {ACCENT}55; }}
        .br-avatar {{ width: 58px; height: 58px; border-radius: 50%; margin: 0 auto 9px;
                      display:flex; align-items:center; justify-content:center;
                      background: radial-gradient(circle at 35% 25%, #73313d, #211116 72%);
                      border: 1px solid #6d3942; color: #fff; font-size: 1.1rem;
                      font-weight: 850; }}
        .br-name {{ color:#fff; font-weight:800; font-size:.88rem; line-height:1.2; }}
        .br-role {{ color:#aaaab5; font-size:.7rem; margin-top:4px; line-height:1.25; }}
        .br-status {{ color:{ACCENT}; font-size:.65rem; font-weight:800; letter-spacing:.1em;
                      text-transform:uppercase; margin-top:7px; }}
        .br-chair {{ background: linear-gradient(110deg, #241015, #111116 65%);
                     border:1px solid {ACCENT}88; border-radius:18px; padding:16px;
                     box-shadow: 0 0 24px {ACCENT}20; }}
        .br-chair-title {{ color:#fff; font-size:1.12rem; font-weight:850; }}
        .br-chair-copy {{ color:#c4bfc3; font-size:.82rem; margin-top:4px; }}
        .br-panel {{ background:{PANEL}; border:1px solid #292932; border-radius:15px;
                     padding:16px; }}
        .br-empty {{ color:#9999a5; text-align:center; padding:34px 12px;
                     border:1px dashed #393943; border-radius:13px; }}
        div.stButton > button {{ border-radius:10px; font-weight:750; }}
        div.stButton > button[kind="primary"] {{ background:{ACCENT}; border-color:{ACCENT}; }}
        @media (max-width: 700px) {{ .br-card {{ min-height:132px; padding:10px 7px; }}
          .br-avatar {{ width:49px; height:49px; }} }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _initials(name: str) -> str:
    return "".join(part[0] for part in name.split()[:2]).upper()


def _render_member_card(name: str, role: str, active: bool, status: str) -> None:
    class_name = "br-card active" if active else "br-card"
    status_html = f'<div class="br-status">{status}</div>' if status else ""
    st.markdown(
        f"""<div class="{class_name}">
          <div class="br-avatar">{_initials(name)}</div>
          <div class="br-name">{name}</div>
          <div class="br-role">{role}</div>{status_html}
        </div>""",
        unsafe_allow_html=True,
    )



def _render_answer_tools(text: str, key: str) -> None:
    """Render per-answer copy and browser-native read-aloud controls."""
    encoded = base64.b64encode(str(text).encode("utf-8")).decode("ascii")
    safe_key = "brtools-" + "".join(ch for ch in key if ch.isalnum() or ch in "-_")
    html = f'''
    <div id="{safe_key}" style="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 14px;">
      <button id="{safe_key}-copy" style="background:#24242c;color:#fff;border:1px solid #454550;border-radius:8px;padding:7px 12px;font-weight:700;cursor:pointer;">Copy answer</button>
      <button id="{safe_key}-read" style="background:#a10f2b;color:#fff;border:1px solid #ff465c;border-radius:8px;padding:7px 12px;font-weight:700;cursor:pointer;">▶ Read aloud</button>
      <button id="{safe_key}-stop" style="background:#24242c;color:#ddd;border:1px solid #454550;border-radius:8px;padding:7px 12px;cursor:pointer;">■ Stop</button>
      <span id="{safe_key}-status" style="color:#aaa;font:12px sans-serif;align-self:center;"></span>
    </div>
    <script>
    (() => {{
      const root = document.getElementById({safe_key!r});
      if (!root) return;
      const raw = atob({encoded!r});
      const bytes = Uint8Array.from(raw, c => c.charCodeAt(0));
      const answer = new TextDecoder().decode(bytes);
      const status = root.querySelector('#{safe_key}-status');
      root.querySelector('#{safe_key}-copy').addEventListener('click', async () => {{
        try {{
          if (navigator.clipboard && navigator.clipboard.writeText) await navigator.clipboard.writeText(answer);
          else {{
            const area = document.createElement('textarea'); area.value = answer;
            document.body.appendChild(area); area.select(); document.execCommand('copy'); area.remove();
          }}
          status.textContent = 'Copied';
        }} catch (e) {{ status.textContent = 'Copy unavailable in this browser'; }}
      }});
      root.querySelector('#{safe_key}-read').addEventListener('click', () => {{
        if (!('speechSynthesis' in window)) {{ status.textContent = 'Read aloud is not supported'; return; }}
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(answer);
        utterance.rate = 1; utterance.pitch = 1;
        utterance.onstart = () => status.textContent = 'Reading…';
        utterance.onend = () => status.textContent = 'Finished';
        utterance.onerror = () => status.textContent = 'Speech could not start';
        window.speechSynthesis.speak(utterance);
      }});
      root.querySelector('#{safe_key}-stop').addEventListener('click', () => {{
        if ('speechSynthesis' in window) window.speechSynthesis.cancel();
        status.textContent = 'Stopped';
      }});
    }})();
    </script>
    <style>body{{margin:0;background:transparent;}}</style>
    '''
    components.html(html, height=54, scrolling=False)

def render_boardroom(
    on_submit: Callable[[str, str, int, bool], Any] | None = None,
    meeting_history: list[dict[str, Any]] | None = None,
) -> None:
    """Render Boardroom Mode.

    Args:
        on_submit: Callback receiving (question, debate_mode, rounds, roast_mode)
                   and running the connected Boardroom debate engine.
    """
    _inject_css()
    roster = get_boardroom_roster()
    advisors = roster["advisors"]

    st.markdown('<div class="br-wrap">', unsafe_allow_html=True)
    st.markdown(
        '<div class="br-eyebrow">J.A.N.E. // Strategic intelligence chamber</div>'
        '<div class="br-heading">THE BOARDROOM</div>'
        '<div class="br-subtitle">Seven independent perspectives. One chaired decision.</div>',
        unsafe_allow_html=True,
    )

    # Chairman is deliberately separate from the seven voting advisors.
    chair = roster["chairperson"]
    chair_left, chair_right = st.columns([1, 3], vertical_alignment="center")
    with chair_left:
        _render_member_card("J.A.N.E.", "Male Chairman · Non-voting", True, "CHAIRPERSON")
    with chair_right:
        st.markdown(
            '<div class="br-chair"><div class="br-eyebrow">Presiding officer</div>'
            '<div class="br-chair-title">J.A.N.E. — The Chairman</div>'
            '<div class="br-chair-copy">Moderates the discussion, challenges weak reasoning, '
            'summarises the seven votes and delivers the final verdict. He does not vote.</div></div>',
            unsafe_allow_html=True,
        )

    # Persistent meeting history is loaded from the signed-in user's private Firestore path.
    history = meeting_history or []
    with st.expander(f"📚 Saved Boardroom meetings ({len(history)})", expanded=False):
        if history:
            for history_index, record in enumerate(history):
                label = str(record.get("question") or record.get("title") or "Boardroom meeting")
                date_label = str(record.get("date") or record.get("updatedAt") or "")
                left, right = st.columns([5, 1])
                with left:
                    st.markdown(f"**{escape(label[:110])}**")
                    st.caption(date_label)
                with right:
                    if st.button("Open", key=f"br_open_saved_{history_index}", use_container_width=True):
                        st.session_state["br_transcript"] = record.get("transcript", []) or []
                        st.session_state["br_verdict"] = record.get("verdict", "")
                        st.session_state["br_vote_tally"] = record.get("votes", {}) or {}
                        st.session_state["br_last_question"] = record.get("question", "")
                        st.session_state["br_last_run_at"] = date_label
                        st.session_state["br_loaded_meeting_id"] = record.get("id", "")
                        st.rerun()
        else:
            st.caption("Completed meetings will appear here automatically after they are saved.")
    save_status = st.session_state.get("br_save_status")
    if save_status:
        st.info(save_status)

    st.markdown('<div class="br-section">The seven advisors</div>', unsafe_allow_html=True)
    active_speaker = st.session_state.get("br_active_speaker", "")
    columns = st.columns(4, gap="small")
    for index, advisor in enumerate(advisors):
        with columns[index % 4]:
            _render_member_card(
                advisor["name"], advisor["title"],
                active_speaker == advisor["id"],
                "SPEAKING" if active_speaker == advisor["id"] else "",
            )
            st.write("")

    st.markdown('<div class="br-section">Convene a meeting</div>', unsafe_allow_html=True)
    with st.container(border=True):
        question = st.text_area(
            "Decision or question for the board",
            key="br_question",
            height=115,
            placeholder="Example: Should J.A.N.E. launch a paid business subscription?",
        )
        col_a, col_b, col_c = st.columns([1.5, 1, 1])
        with col_a:
            debate_mode = st.selectbox(
                "Debate format",
                ["Full Board Debate", "Independent Analysis", "Rebuttal Round", "Rapid Verdict"],
                key="br_debate_mode",
            )
        with col_b:
            rounds = st.selectbox("Rounds", [1, 2, 3], index=1, key="br_rounds")
        with col_c:
            roast_mode = st.toggle("Roast Mode", value=False, key="br_roast_mode")
        st.caption("Roast Mode means tough criticism of ideas and assumptions—not personal attacks.")
        submitted = st.button("Start Board Meeting", type="primary", use_container_width=True)
        if submitted:
            if not question.strip():
                st.warning("Enter a question before starting the meeting.")
            else:
                st.session_state["br_last_question"] = question.strip()
                st.session_state["br_meeting_requested"] = True
                if on_submit is not None:
                    try:
                        on_submit(question.strip(), debate_mode, int(rounds), bool(roast_mode))
                        st.success("The board meeting is complete. Review the transcript and Chairman’s verdict below.")
                    except Exception as exc:
                        st.error("The board meeting could not be completed.")
                        st.caption(f"Technical detail: {type(exc).__name__}: {exc}")
                else:
                    st.error("The debate engine is not connected. Please check the app integration.")

    st.markdown('<div class="br-section">Live debate transcript</div>', unsafe_allow_html=True)
    transcript = st.session_state.get("br_transcript", [])
    if transcript:
        for index, item in enumerate(transcript):
            speaker = str(item.get("speaker", "Advisor"))
            message = str(item.get("message", ""))
            with st.container(border=True):
                st.markdown(f'<div class="br-eyebrow">{escape(speaker)}</div>', unsafe_allow_html=True)
                # Streamlit Markdown renders headings, bold, lists, tables, links and code safely.
                st.markdown(message)
                _render_answer_tools(message, f"transcript-{index}-{speaker}")
    else:
        st.markdown(
            '<div class="br-empty">The board is waiting for its first question.<br>'
            'Start a meeting to receive seven independent analyses and a chaired verdict.</div>',
            unsafe_allow_html=True,
        )

    tally = st.session_state.get("br_vote_tally")
    if tally:
        st.markdown('<div class="br-section">Final advisor vote</div>', unsafe_allow_html=True)
        vote_cols = st.columns(4)
        for col, (label, count) in zip(vote_cols, tally.items()):
            with col:
                st.metric(label, count)

    st.markdown('<div class="br-section">Chairman’s final verdict</div>', unsafe_allow_html=True)
    verdict = st.session_state.get("br_verdict", "")
    if verdict:
        with st.container(border=True):
            st.markdown(str(verdict))
            _render_answer_tools(str(verdict), "chairman-verdict")
        if st.session_state.get("br_last_run_at"):
            st.caption("Meeting completed · " + str(st.session_state["br_last_run_at"]))
    else:
        st.markdown(
            '<div class="br-empty">No verdict yet.<br>J.A.N.E. will publish the decision, '
            'vote tally, confidence assessment and action plan after the meeting.</div>',
            unsafe_allow_html=True,
        )

    st.markdown('</div>', unsafe_allow_html=True)


__all__ = ["render_boardroom"]
