"""J.A.N.E. Boardroom debate engine using the app's configured Gemini service."""
from __future__ import annotations

from datetime import datetime
from typing import Any
import re

import streamlit as st
from google import genai
from google.genai import types

from boardroom_agents import (
    AGENTS,
    build_agent_system_prompt,
    build_chairperson_system_prompt,
)

def _model_name() -> str:
    try:
        return str(
            st.secrets.get(
                "BOARDROOM_MODEL",
                st.secrets.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            )
        ).strip() or "gemini-3.5-flash-lite"
    except Exception:
        return "gemini-3.5-flash-lite"


def _generate(client: Any, system_instruction: str, prompt: str) -> str:
    response = client.models.generate_content(
        model=_model_name(),
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.65,
            max_output_tokens=1400,
        ),
    )
    answer = str(getattr(response, "text", "") or "").strip()
    if not answer:
        raise RuntimeError("The AI service returned an empty response.")
    return answer


def _position(text: str) -> str:
    match = re.search(
        r"(?im)^\s*(?:1[\).]\s*)?Position\s*:\s*(support|oppose|conditional)\b",
        text,
    )
    if match:
        return match.group(1).title()
    first = text[:500].lower()
    if re.search(r"\b(oppose|against|reject)\b", first):
        return "Oppose"
    if re.search(r"\b(support|for|approve)\b", first):
        return "Support"
    return "Conditional"


def run_board_meeting(
    question: str,
    debate_mode: str = "Full Board Debate",
    rounds: int = 2,
    roast_mode: bool = False,
) -> dict[str, Any]:
    """Run seven independent analyses, moderated debate, simulated votes and verdict."""
    question = str(question or "").strip()
    if not question:
        raise ValueError("Enter a decision or question before starting the meeting.")

    api_key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing from Streamlit Secrets.")

    client = genai.Client(api_key=api_key)
    transcript: list[dict[str, str]] = []
    analyses: list[dict[str, str]] = []
    roster = list(AGENTS.items())
    roast_instruction = (
        "ROAST MODE IS ON: be unusually direct and rigorous when challenging weak assumptions, "
        "contradictions, vague plans, and unsupported claims. Criticise ideas only, never people."
        if roast_mode else
        "Use a firm, professional tone. Challenge weak reasoning respectfully."
    )

    st.session_state["br_transcript"] = []
    st.session_state["br_verdict"] = ""
    st.session_state["br_active_speaker"] = "jane_chairperson"

    with st.status("J.A.N.E. is convening the board…", expanded=True) as status:
        st.write("**Chairman:** Framing the decision and assigning independent analysis.")
        # Independent first-round responses: each advisor receives only the brief,
        # not the other advisors' opinions, to reduce groupthink.
        for index, (agent_id, agent) in enumerate(roster, start=1):
            st.session_state["br_active_speaker"] = agent_id
            st.write(f"**{agent['name']}** is analysing ({index}/7)…")
            prompt = (
                f"BOARD MEETING QUESTION\n{question}\n\n"
                "This is the independent first round. Do not assume other advisors' views. "
                "Give a concise, decision-useful answer using the exact six-part response format "
                "in your system instructions. State a provisional position clearly. "
                + roast_instruction
            )
            try:
                answer = _generate(client, build_agent_system_prompt(agent_id), prompt)
            except Exception as exc:
                answer = (
                    f"Analysis unavailable ({type(exc).__name__}). This advisor did not cast "
                    "a supported position; do not infer a vote."
                )
            item = {"speaker": agent["name"], "message": answer, "agent_id": agent_id}
            analyses.append({
                "id": agent_id,
                "name": agent["name"],
                "position": _position(answer) if "unavailable" not in answer.lower() else "No vote",
                "analysis": answer,
            })
            transcript.append(item)
            st.session_state["br_transcript"] = transcript.copy()

        debate_enabled = debate_mode in ("Full Board Debate", "Rebuttal Round")
        debate_summaries: list[str] = []
        if debate_enabled:
            for round_no in range(1, max(1, min(int(rounds), 3)) + 1):
                st.session_state["br_active_speaker"] = "jane_chairperson"
                st.write(f"**J.A.N.E.** is moderating debate round {round_no}…")
                discussion = "\n\n".join(
                    f"{a['name']} — {a['position']}:\n{a['analysis']}" for a in analyses
                )
                debate_prompt = (
                    f"MEETING QUESTION\n{question}\n\n"
                    f"DEBATE ROUND {round_no} OF {rounds}\n"
                    "Below are the seven independent opening positions. Conduct a fair, substantive "
                    "cross-examination. Identify direct disagreements, test assumptions, and give each "
                    "advisor a concise rebuttal or clarification. Do not invent new facts. "
                    f"{roast_instruction}\n\n"
                    "Return seven clearly labelled sections, one for each advisor, followed by "
                    "a short 'CHAIRMAN'S ROUND SUMMARY' section. Keep each advisor section concise.\n\n"
                    f"{discussion}"
                )
                debate_text = _generate(client, build_chairperson_system_prompt(), debate_prompt)
                debate_summaries.append(debate_text)
                transcript.append({
                    "speaker": f"J.A.N.E. — Debate Round {round_no}",
                    "message": debate_text,
                    "agent_id": "jane_chairperson",
                })
                st.session_state["br_transcript"] = transcript.copy()

        # A single structured voting call asks the seven simulated advisors to
        # reconsider after debate; J.A.N.E. remains non-voting.
        st.session_state["br_active_speaker"] = "jane_chairperson"
        st.write("**The seven advisors** are recording their final positions…")
        debate_context = "\n\n".join(debate_summaries) if debate_summaries else "No rebuttal round was selected."
        vote_prompt = (
            f"QUESTION\n{question}\n\n"
            "Based only on the independent analyses and debate below, produce a final simulated "
            "vote for each of the seven advisors. Use exactly one of SUPPORT, OPPOSE, CONDITIONAL, "
            "or NO VOTE per advisor, and one short reason. Do not invent evidence. "
            "J.A.N.E. does not vote.\n\n"
            "Use this exact format:\n"
            "Warren Buffett: SUPPORT — reason\nSam Altman: CONDITIONAL — reason\n"
            "Elon Musk: ...\nCharlie Munger: ...\nSteve Jobs: ...\nRay Dalio: ...\nSundar Pichai: ...\n\n"
            f"OPENING ANALYSES\n{json_safe(analyses)}\n\nDEBATE\n{debate_context}"
        )
        vote_text = _generate(
            client,
            "You are a neutral board vote recorder. Follow the requested format exactly. "
            "Do not act as an eighth voter.",
            vote_prompt,
        )
        transcript.append({"speaker": "Board Vote", "message": vote_text, "agent_id": "board_vote"})
        st.session_state["br_transcript"] = transcript.copy()

        # Derive a transparent tally from the actual labels in the vote recorder output.
        vote_counts = {"Support": 0, "Oppose": 0, "Conditional": 0, "No vote": 0}
        for _, agent in roster:
            line = re.search(
                rf"(?im)^\s*{re.escape(agent['name'])}\s*:\s*(SUPPORT|OPPOSE|CONDITIONAL|NO VOTE)\b",
                vote_text,
            )
            label = line.group(1).title() if line else "No vote"
            if label == "No Vote":
                label = "No vote"
            vote_counts[label] += 1

        st.session_state["br_active_speaker"] = "jane_chairperson"
        st.write("**J.A.N.E.** is preparing the Chairman’s verdict…")
        all_openings = "\n\n".join(
            f"{a['name']} — provisional position: {a['position']}\n{a['analysis']}"
            for a in analyses
        )
        verdict_prompt = (
            f"DECISION BEFORE THE BOARD\n{question}\n\n"
            f"DEBATE FORMAT: {debate_mode}; ROUNDS: {rounds}; ROAST MODE: {roast_mode}.\n\n"
            f"OPENING ANALYSES\n{all_openings}\n\n"
            f"DEBATE RECORD\n{debate_context}\n\n"
            f"FINAL SIMULATED VOTES\n{vote_text}\n\n"
            f"PARSED VOTE TALLY\n{vote_counts}\n\n"
            "As Chairman, write the final verdict using all eight headings from your system "
            "instructions. Be fair to minority views. Distinguish known facts from assumptions. "
            "Do not claim that research was independently verified. If key information is missing, "
            "make the recommendation conditional and list exactly what must be checked. "
            "Do not expose hidden chain-of-thought."
        )
        verdict = _generate(client, build_chairperson_system_prompt(), verdict_prompt)
        transcript.append({"speaker": "J.A.N.E. — Chairman", "message": verdict, "agent_id": "jane_chairperson"})
        st.session_state["br_transcript"] = transcript
        st.session_state["br_verdict"] = verdict
        st.session_state["br_vote_tally"] = vote_counts
        st.session_state["br_last_run_at"] = datetime.now().strftime("%d %b %Y, %H:%M")
        st.session_state["br_active_speaker"] = "jane_chairperson"
        status.update(label="Board meeting completed", state="complete", expanded=False)

    return {
        "question": question,
        "transcript": transcript,
        "verdict": verdict,
        "votes": vote_counts,
    }


def json_safe(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, indent=2)
