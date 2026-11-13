import io
import os
import hashlib
import base64
import json
import uuid
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime
import time

import pandas as pd
from PIL import Image
import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
from openai import OpenAI


# -------------------- FREE IMAGE GENERATION (AI HORDE) --------------------
AI_HORDE_API = "https://aihorde.net/api/v2"
AI_HORDE_ANON_KEY = "0000000000"  # Public anonymous key; no paid API key or billing required.
CLOUDFLARE_IMAGE_MODEL = "@cf/leonardo/lucid-origin"


def _jane_secret(name):
    """Read a secret from Streamlit Secrets or the server environment."""
    value = ""
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.environ.get(name, "")).strip()


def cloudflare_lucid_generate_image(prompt, width=512, height=512, timeout_seconds=180):
    """Generate an image with Leonardo Lucid Origin through Cloudflare Workers AI."""
    account_id = _jane_secret("CLOUDFLARE_ACCOUNT_ID")
    api_token = _jane_secret("CLOUDFLARE_API_TOKEN")
    if not account_id or not api_token:
        raise RuntimeError(
            "Cloudflare image credentials are not configured. Add CLOUDFLARE_ACCOUNT_ID "
            "and CLOUDFLARE_API_TOKEN to Streamlit Secrets; AI Horde will remain available as fallback."
        )

    # Keep the longest side at 512 px initially so the first rollout stays within
    # a predictable free-allocation budget. Preserve the selected aspect ratio.
    width, height = int(width), int(height)
    longest_side = max(width, height)
    if longest_side > 512:
        scale = 512 / longest_side
        width = max(64, int(round((width * scale) / 64)) * 64)
        height = max(64, int(round((height * scale) / 64)) * 64)

    payload = {
        "prompt": str(prompt).strip(),
        "width": width,
        "height": height,
        "guidance": 4.5,
        "num_steps": 20,
    }
    endpoint = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{urllib.parse.quote(account_id, safe='')}/ai/run/{CLOUDFLARE_IMAGE_MODEL}"
    )
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "JANE-AI/0.93 (+https://github.com/EDITEX07/JANE-ai)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            result_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:700]
        # Do not include request headers or credentials in any surfaced error.
        raise RuntimeError(f"Cloudflare Workers AI returned HTTP {exc.code}: {detail}") from None
    except urllib.error.URLError:
        raise RuntimeError("Could not connect to Cloudflare Workers AI. Check the connection and try again.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError("Cloudflare Workers AI returned an unreadable response.") from None

    result = result_payload.get("result") or result_payload
    image_value = result.get("image") if isinstance(result, dict) else None
    if not image_value:
        errors = result_payload.get("errors") or []
        message = "; ".join(str(item.get("message", item)) for item in errors)[:500]
        raise RuntimeError(message or "Cloudflare did not return an image.")
    try:
        image_bytes = base64.b64decode(image_value, validate=True)
        return _normalize_image_to_png(image_bytes)
    except Exception:
        raise RuntimeError("Cloudflare returned image data that could not be decoded.") from None


def _horde_json_request(path, method="GET", payload=None, timeout=35):
    """Make a JSON request to AI Horde without exposing any credentials."""
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        AI_HORDE_API + path,
        data=body,
        method=method,
        headers={
            "apikey": AI_HORDE_ANON_KEY,
            "Client-Agent": "JANE-AI:0.92:https://github.com/EDITEX07/JANE-ai",
            # Cloudflare may block urllib's default Python user-agent (Error 1010).
            "User-Agent": "JANE-AI/0.92 (+https://github.com/EDITEX07/JANE-ai)",
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        if "KudosUpfront" in detail:
            raise RuntimeError(
                "AI Horde's anonymous free-work budget rejected this request because of current demand. "
                "J.A.N.E. now uses 512 px output and 20 steps to reduce the work required. "
                "No kudos purchase is required or enabled; please try again later if the free queue is still busy."
            ) from None
        if exc.code == 403 and ("1010" in detail or "browser_signature_banned" in detail):
            raise RuntimeError(
                "AI Horde's Cloudflare protection blocked this server request (Error 1010). "
                "J.A.N.E. now sends an explicit app User-Agent; if this continues, the service "
                "owner may need to allow the hosting server. Please try again later."
            ) from None
        raise RuntimeError(f"AI Horde returned HTTP {exc.code}: {detail}") from None
    except urllib.error.URLError:
        raise RuntimeError("Could not reach the free image-generation service. Check the connection and try again.") from None


def _normalize_image_to_png(image_bytes):
    """Convert the returned WebP/PNG/JPEG bytes into a consistent PNG payload."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        output = io.BytesIO()
        image.convert("RGBA").save(output, format="PNG")
        return output.getvalue()


def horde_generate_image(prompt, width=512, height=512, source_image_bytes=None, timeout_seconds=360):
    """Generate one safe, low-work image using AI Horde's anonymous, community-powered API."""
    # Keep every request at or below 512 px on its longest side. This stays
    # below AI Horde's 698 px anonymous-request threshold and preserves aspect ratio.
    width, height = int(width), int(height)
    longest_side = max(width, height)
    if longest_side > 512:
        scale = 512 / longest_side
        width = max(64, int(round((width * scale) / 64)) * 64)
        height = max(64, int(round((height * scale) / 64)) * 64)
    params = {
        "width": width,
        "height": height,
        "steps": 20,
        "cfg_scale": 7.5,
        "sampler_name": "k_euler_a",
        "karras": True,
        "n": 1,
    }
    request_payload = {
        "prompt": str(prompt).strip(),
        "params": params,
        "nsfw": False,
        "censor_nsfw": True,
        "r2": False,
        "shared": False,
        "replacement_filter": True,
    }

    if source_image_bytes:
        # AI Horde expects a base64-encoded WebP source image for img2img.
        source = Image.open(io.BytesIO(source_image_bytes)).convert("RGB")
        source.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        source_buffer = io.BytesIO()
        source.save(source_buffer, format="WEBP", quality=88)
        request_payload["source_image"] = base64.b64encode(source_buffer.getvalue()).decode("ascii")
        request_payload["source_processing"] = "img2img"
        params["denoising_strength"] = 0.55

    started = _horde_json_request("/generate/async", method="POST", payload=request_payload)
    request_id = started.get("id")
    if not request_id:
        raise RuntimeError(started.get("message") or "The image service did not return a request ID.")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status_check = _horde_json_request(f"/generate/check/{request_id}")
        if status_check.get("faulted"):
            raise RuntimeError("The volunteer image worker could not complete this request. Please try again.")
        if status_check.get("is_possible") is False:
            raise RuntimeError("No compatible volunteer worker is available right now. Please try again later.")
        finished = int(status_check.get("finished", 0) or 0)
        if status_check.get("done") or finished >= 1:
            break
        time.sleep(3)
    else:
        raise TimeoutError("The free image queue is taking too long. Please try again later.")

    full_status = _horde_json_request(f"/generate/status/{request_id}")
    for generation in (full_status.get("generations") or []):
        image_value = generation.get("img")
        if not image_value:
            continue
        if image_value.startswith("data:image") and "," in image_value:
            image_value = image_value.split(",", 1)[1]
            return _normalize_image_to_png(base64.b64decode(image_value))
        if image_value.startswith(("https://", "http://")):
            image_request = urllib.request.Request(image_value, headers={"User-Agent": "JANE-AI/0.92"})
            with urllib.request.urlopen(image_request, timeout=60) as image_response:
                return _normalize_image_to_png(image_response.read())
        try:
            return _normalize_image_to_png(base64.b64decode(image_value))
        except Exception:
            continue
    raise RuntimeError("The service finished the request but did not return an image. Please try again.")


def jane_generate_image(prompt, width=512, height=512, source_image_bytes=None):
    """Use Lucid Origin first; preserve AI Horde for fallback and reference-image edits."""
    if source_image_bytes:
        # Lucid Origin is text-to-image. Keep the existing Horde img2img path intact.
        image_bytes = horde_generate_image(
            prompt, width=width, height=height, source_image_bytes=source_image_bytes
        )
        st.session_state["last_image_engine"] = "AI Horde (reference-image edit)"
        st.session_state["last_image_engine_note"] = "Reference-image editing is still handled by AI Horde."
        return image_bytes

    try:
        image_bytes = cloudflare_lucid_generate_image(prompt, width=width, height=height)
        st.session_state["last_image_engine"] = "Leonardo Lucid Origin via Cloudflare Workers AI"
        st.session_state["last_image_engine_note"] = "Generated with the primary image model."
        return image_bytes
    except Exception as primary_error:
        try:
            image_bytes = horde_generate_image(prompt, width=width, height=height)
            st.session_state["last_image_engine"] = "AI Horde fallback"
            st.session_state["last_image_engine_note"] = (
                "Cloudflare Lucid Origin was unavailable, so J.A.N.E. used its AI Horde fallback. "
                f"Reason: {str(primary_error)[:240]}"
            )
            return image_bytes
        except Exception as fallback_error:
            raise RuntimeError(
                "Both image engines were unavailable. "
                f"Cloudflare: {str(primary_error)[:260]} | "
                f"AI Horde fallback: {str(fallback_error)[:260]}"
            ) from None


def build_studio_image_prompt(user_prompt, style):
    """Add focused style guidance while keeping the user's requested subject intact."""
    style_guidance = {
        "Photorealistic": (
            "Photorealistic photograph, natural real-world appearance, physically plausible details, "
            "realistic materials and textures, subtle natural imperfections, lifelike lighting and shadows, "
            "balanced exposure, realistic depth of field, documentary-quality photography."
        ),
        "Artistic": (
            "Intentional fine-art image, distinctive composition, expressive color and lighting, "
            "cohesive visual style, carefully crafted details, polished artistic finish."
        ),
        "Anime": (
            "High-quality anime illustration, clean intentional linework, expressive character design, "
            "cohesive cel shading, detailed background, polished anime artwork."
        ),
        "Product photography": (
            "Professional commercial product photograph, accurate product geometry, crisp material detail, "
            "controlled studio lighting, realistic contact shadows, clean premium composition."
        ),
    }
    negative_guidance = (
        "plastic skin, waxy face, overly smooth texture, artificial-looking eyes, distorted anatomy, "
        "extra fingers, fused fingers, malformed hands, warped objects, duplicated features, "
        "over-sharpening, excessive glow, fake-looking lighting, low-detail, blurry, watermark, text artifacts"
    )
    return f"{str(user_prompt).strip()}, {style_guidance.get(style, style_guidance['Photorealistic'])} ### {negative_guidance}"


def image_dimensions_for_ratio(ratio, longest_side):
    """Return dimensions in multiples of 64 while preserving the selected orientation."""
    ratio_width, ratio_height = (int(part) for part in ratio.split(":"))
    if ratio_width >= ratio_height:
        width = int(round(longest_side / 64)) * 64
        height = max(64, int(round((width * ratio_height / ratio_width) / 64)) * 64)
    else:
        height = int(round(longest_side / 64)) * 64
        width = max(64, int(round((height * ratio_width / ratio_height) / 64)) * 64)
    return width, height


st.set_page_config(page_title="J.A.N.E. | AI Workspace", page_icon="app-logo.png", layout="wide", initial_sidebar_state="collapsed")

# -------------------- FILE RECOGNITION --------------------
def extract_uploaded_file_text(filename, file_info):
    """Extract readable text from supported uploads for the active chat request."""
    data = file_info.get("data", b"")
    extension = Path(filename).suffix.lower()
    if not data:
        return ""
    try:
        if extension in (".txt", ".md", ".json"):
            return data.decode("utf-8-sig", errors="replace")[:30000]
        if extension == ".csv":
            frame = pd.read_csv(io.BytesIO(data), nrows=300)
            return frame.to_string(index=False, max_rows=300, max_cols=40)[:30000]
        if extension == ".xlsx":
            frame = pd.read_excel(io.BytesIO(data), nrows=300)
            return frame.to_string(index=False, max_rows=300, max_cols=40)[:30000]
        if extension == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                return "PDF text extraction needs the pypdf package. Add pypdf to requirements.txt and redeploy."
            reader = PdfReader(io.BytesIO(data))
            pages = [(page.extract_text() or "") for page in reader.pages[:40]]
            extracted = "\n\n".join(f"[Page {i + 1}]\n{page}" for i, page in enumerate(pages))
            return extracted[:30000] or "No selectable text was found in this PDF. It may be a scanned document; scanned-PDF OCR is not enabled yet."
        if extension == ".docx":
            try:
                from docx import Document
            except ImportError:
                return "Word document reading needs the python-docx package. Add python-docx to requirements.txt and redeploy."
            document = Document(io.BytesIO(data))
            paragraphs = [para.text for para in document.paragraphs if para.text.strip()]
            for table in document.tables[:20]:
                for row in table.rows[:100]:
                    paragraphs.append(" | ".join(cell.text.replace("\n", " ") for cell in row.cells))
            return "\n".join(paragraphs)[:30000]
        if extension in (".png", ".jpg", ".jpeg", ".webp"):
            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
            mime_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}[extension]
            part = types.Part.from_bytes(data=data, mime_type=mime_type)
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=[
                    "Read and describe this uploaded image for the user's question. Extract all visible text faithfully, and also describe relevant objects, charts, diagrams, and layout. Do not guess unclear text; mark it [unclear].",
                    part,
                ],
            )
            return (response.text or "No readable information was returned for this image.")[:20000]
        return f"J.A.N.E. does not recognize the {extension or 'unknown'} file format yet."
    except Exception as exc:
        return f"J.A.N.E. could not read this file ({type(exc).__name__}). Please check that it is not damaged or password-protected."


def build_attached_file_context():
    """Build bounded context from files attached in the current app session."""
    uploaded = st.session_state.get("uploaded_files", {})
    if not uploaded:
        return ""
    sections = []
    total_chars = 0
    cache = st.session_state.setdefault("file_text_cache", {})
    for filename, info in uploaded.items():
        remaining = 50000 - total_chars
        if remaining <= 0:
            sections.append("[Additional attached files were omitted because the context limit was reached.]")
            break
        digest = hashlib.sha256(info.get("data", b"")).hexdigest()
        cache_key = f"{filename}:{digest}"
        if cache_key not in cache:
            cache[cache_key] = extract_uploaded_file_text(filename, info)
        extracted = cache[cache_key]
        excerpt = str(extracted or "No readable content was extracted.")[:min(20000, remaining)]
        sections.append(f"FILE: {filename}\n{excerpt}")
        total_chars += len(excerpt)
    return "\n\n---\n\n".join(sections)


# -------------------- SESSION STATE --------------------
if "chats" not in st.session_state:
    first_id = str(uuid.uuid4())
    st.session_state.chats = {first_id: {"title": "New conversation", "messages": [], "created": datetime.now().strftime("%d %b %Y, %H:%M")}}
    st.session_state.current_chat = first_id
for key, default in {
    "profile_name": "Explorer", "api_enabled": True, "uploaded_files": {},
    "pending_prompt": None, "intelligence_mode": "Adaptive", "assistant_style": "Classic",
    "auth_user": None, "auth_token": None, "auth_refresh_token": None, "auth_mode": "signin", "voice_speed": 1.0, "ui_theme": "Red",
    "image_gallery": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# Normalize legacy selector values so an older saved "Javis" value cannot crash the app.
if st.session_state.get("assistant_style") in ("Javis", "Jarvis", "JARVIS", "jarvis"):
    st.session_state.assistant_style = "Jarvis"
elif st.session_state.get("assistant_style") != "Classic":
    st.session_state.assistant_style = "Classic"
if st.session_state.get("ui_theme") not in {"Red", "Blue", "Green", "Pink", "Purple", "White"}:
    st.session_state.ui_theme = "Red"

# Live AI requests are always enabled; there is no user-facing on/off switch.
st.session_state.api_enabled = True


def make_chat():
    chat_id = str(uuid.uuid4())
    st.session_state.chats[chat_id] = {"title": "New conversation", "messages": [], "created": datetime.now().strftime("%d %b %Y, %H:%M")}
    st.session_state.current_chat = chat_id


def active_chat():
    if st.session_state.current_chat not in st.session_state.chats:
        st.session_state.current_chat = nex
