"""Firebase authentication, Firestore chat history, and memory services."""
import json
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from pathlib import Path
import streamlit as st

def firebase_auth_request(endpoint, email, password):
    # Firebase Authentication REST API helper; API key stays in Streamlit Secrets.
    try:
        api_key = st.secrets.get("FIREBASE_API_KEY", "")
    except Exception:
        api_key = ""
    if not api_key:
        raise RuntimeError("Firebase is not configured. Add FIREBASE_API_KEY to Streamlit Secrets.")
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:{endpoint}?key={api_key}"
    body = json.dumps({"email": email.strip(), "password": password, "returnSecureToken": True}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            code = json.loads(error.read().decode("utf-8")).get("error", {}).get("message", "Authentication failed")
        except Exception:
            code = "Authentication failed"
        friendly = {
            "EMAIL_EXISTS": "An account with this email already exists. Try signing in.",
            "OPERATION_NOT_ALLOWED": "Email/password sign-in is disabled in Firebase Console → Authentication → Sign-in method.",
            "WEAK_PASSWORD": "Choose a stronger password with at least 6 characters.",
            "EMAIL_NOT_FOUND": "No account was found for this email. Create an account first.",
            "INVALID_PASSWORD": "That password doesn't match this account.",
            "INVALID_LOGIN_CREDENTIALS": "Email or password is incorrect.",
            "USER_DISABLED": "This account has been disabled.",
            "INVALID_EMAIL": "Enter a valid email address.",
            "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Please wait a while and try again.",
            "API_KEY_INVALID": "The Firebase API key is invalid. Check Streamlit Secrets.",
        }
        raise ValueError(friendly.get(code, f"Firebase authentication failed: {code}")) from None


def _firebase_project_id():
    try:
        return str(st.secrets.get("FIREBASE_PROJECT_ID", "")).strip()
    except Exception:
        return ""


def _refresh_firebase_id_token():
    """Refresh the short-lived Firebase ID token using the sign-in refresh token."""
    refresh_token = st.session_state.get("auth_refresh_token")
    if not refresh_token:
        raise RuntimeError("Your sign-in session has expired. Sign out and sign in again, then retry chat history.")
    try:
        api_key = str(st.secrets.get("FIREBASE_API_KEY", "")).strip()
    except Exception:
        api_key = ""
    if not api_key:
        raise RuntimeError("Add FIREBASE_API_KEY to Streamlit Secrets.")
    url = f"https://securetoken.googleapis.com/v1/token?key={api_key}"
    body = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": refresh_token}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise RuntimeError("Your Firebase session could not be refreshed. Sign out and sign in again.") from None
    st.session_state.auth_token = result.get("id_token")
    if result.get("refresh_token"):
        st.session_state.auth_refresh_token = result["refresh_token"]
    if not st.session_state.auth_token:
        raise RuntimeError("Firebase did not return a refreshed sign-in token. Sign in again.")
    return st.session_state.auth_token


def _firestore_request(method, path, payload=None):
    """Call Firestore REST using the user's Firebase ID token, refreshing once if expired."""
    user = st.session_state.get("auth_user") or {}
    token = st.session_state.get("auth_token")
    project_id = _firebase_project_id()
    if not user.get("uid") or not token:
        raise RuntimeError("Sign in to use personal memory and saved chat history.")
    if not project_id:
        raise RuntimeError("Add FIREBASE_PROJECT_ID to Streamlit Secrets to enable memory and chat history.")
    url = "https://firestore.googleapis.com/v1/" + path.lstrip("/")
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def send(current_token):
        request = urllib.request.Request(url, data=data, headers={
            "Authorization": "Bearer " + current_token,
            "Content-Type": "application/json; charset=utf-8",
        }, method=method)
        return urllib.request.urlopen(request, timeout=12)

    try:
        try:
            response = send(token)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                token = _refresh_firebase_id_token()
                response = send(token)
            else:
                raise
        with response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:350]
        if exc.code == 401:
            raise RuntimeError("Firebase rejected the sign-in token. Sign out and sign in again.") from None
        if exc.code == 403:
            raise RuntimeError("Firestore returned PERMISSION_DENIED. Check that FIREBASE_PROJECT_ID is the correct project and publish rules allowing /users/{userId}/chats/{chatId} and /users/{userId}/memories/{memoryId} only when request.auth.uid == userId. Firebase detail: " + detail) from None
        raise RuntimeError(f"Firestore request failed ({exc.code}). {detail}") from None


def _memory_collection_path():
    uid = (st.session_state.get("auth_user") or {}).get("uid", "")
    if not uid or "/" in uid:
        raise RuntimeError("A valid signed-in user is required.")
    return f"projects/{_firebase_project_id()}/databases/(default)/documents/users/{uid}/memories"


def _chat_collection_path():
    uid = (st.session_state.get("auth_user") or {}).get("uid", "")
    if not uid or "/" in uid:
        raise RuntimeError("A valid signed-in user is required.")
    return f"projects/{_firebase_project_id()}/databases/(default)/documents/users/{uid}/chats"


def _firestore_string(value):
    return {"stringValue": str(value)}


def _decode_firestore_value(value):
    if "stringValue" in value: return value["stringValue"]
    if "booleanValue" in value: return value["booleanValue"]
    if "integerValue" in value:
        try: return int(value["integerValue"])
        except Exception: return value["integerValue"]
    if "timestampValue" in value: return value["timestampValue"]
    return None


def save_chat_history(chat_id, chat_data):
    """Persist a user's conversation as a JSON string in their own Firestore chat document."""
    if not st.session_state.get("auth_user"):
        return False
    if not chat_id or "/" in str(chat_id) or ".." in str(chat_id):
        raise RuntimeError("Invalid chat ID.")
    # Binary image data and uploaded file bytes are deliberately not stored in chat history.
    safe_messages = []
    for message in chat_data.get("messages", []):
        safe = {k: v for k, v in message.items() if k not in ("image_bytes",)}
        if isinstance(safe.get("attachments"), list):
            safe["attachments"] = [str(name) for name in safe["attachments"]]
        safe_messages.append(safe)
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    payload = {
        "id": str(chat_id),
        "title": str(chat_data.get("title", "New conversation"))[:160],
        "created": str(chat_data.get("created", now)),
        "updatedAt": now,
        "messages": safe_messages,
    }
    document = {"fields": {
        "payload": {"stringValue": json.dumps(payload, ensure_ascii=False)},
        "title": {"stringValue": payload["title"]},
        "created": {"stringValue": payload["created"]},
        "updatedAt": {"timestampValue": now},
    }}
    path = _chat_collection_path() + "/" + str(chat_id)
    try:
        _firestore_request("PATCH", path + "?updateMask.fieldPaths=payload&updateMask.fieldPaths=title&updateMask.fieldPaths=created&updateMask.fieldPaths=updatedAt", document)
    except RuntimeError as exc:
        if "(404)" not in str(exc):
            raise
        _firestore_request("POST", _chat_collection_path() + "?documentId=" + str(chat_id), document)
    return True


def load_chat_history():
    """Load persisted conversations for the currently authenticated account."""
    if not st.session_state.get("auth_user"):
        return {}
    result = _firestore_request("GET", _chat_collection_path())
    chats = {}
    for document in result.get("documents", []):
        fields = {k: _decode_firestore_value(v) for k, v in document.get("fields", {}).items()}
        try:
            payload = json.loads(fields.get("payload", "{}"))
            chat_id = str(payload.get("id") or document.get("name", "").rsplit("/", 1)[-1])
            messages = payload.get("messages", [])
            if not isinstance(messages, list):
                messages = []
            chats[chat_id] = {
                "title": str(payload.get("title", "New conversation")),
                "created": str(payload.get("created", "")),
                "messages": messages,
            }
        except (TypeError, ValueError):
            continue
    return chats


def delete_chat_history(chat_id):
    if not chat_id or "/" in str(chat_id) or ".." in str(chat_id):
        raise RuntimeError("Invalid chat ID.")
    _firestore_request("DELETE", _chat_collection_path() + "/" + str(chat_id))


def load_memories():
    if not st.session_state.get("auth_user"):
        return []
    result = _firestore_request("GET", _memory_collection_path())
    memories = []
    for doc in result.get("documents", []):
        fields = {k: _decode_firestore_value(v) for k, v in doc.get("fields", {}).items()}
        memories.append({"id": doc.get("name", "").rsplit("/", 1)[-1], **fields})
    memories.sort(key=lambda item: str(item.get("updatedAt", "")), reverse=True)
    return memories


def save_memory(text, source="automatic"):
    text = " ".join(str(text or "").split()).strip()
    if not text or len(text) > 600:
        return False
    # Do not save duplicates; compare normalized memory text.
    memories = load_memories()
    normalized = text.casefold().rstrip(".! ")
    for item in memories:
        if str(item.get("text", "")).casefold().rstrip(".! ") == normalized:
            return False
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    fields = {
        "text": {"stringValue": text},
        "source": {"stringValue": source},
        "createdAt": {"timestampValue": now},
        "updatedAt": {"timestampValue": now},
    }
    doc_id = "m_" + uuid.uuid4().hex
    _firestore_request("POST", _memory_collection_path() + "?documentId=" + doc_id, {"fields": fields})
    return True


def delete_memory(memory_id):
    if not memory_id or "/" in memory_id or ".." in memory_id:
        raise RuntimeError("Invalid memory ID.")
    _firestore_request("DELETE", _memory_collection_path() + "/" + memory_id)


def extract_memories(user_text, assistant_text):
    """Use Gemini to extract a few durable, non-sensitive facts; never for Guest sessions."""
    if not st.session_state.get("auth_user"):
        return []
    # Explicit remember commands are handled locally without an extraction call.
    try:
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
        instruction = (
            "Extract up to 3 durable, useful user memories from the exchange. Return ONLY a JSON array of short strings. "
            "Save preferences, long-running projects, goals, and stable workflow choices. Do not save one-off questions, "
            "temporary details, passwords, API keys, precise location, financial account details, health data, or other sensitive personal data. "
            "Do not infer facts not explicitly supported by the exchange. Return [] if nothing merits memory. Each string max 240 characters.\n"
            + "USER: " + str(user_text)[:2500] + "\nASSISTANT: " + str(assistant_text)[:1200]
        )
        result = client.models.generate_content(model="gemini-3.5-flash-lite", contents=instruction)
        raw = (result.text or "[]").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = json.loads(raw)
        return [" ".join(str(x).split())[:240] for x in parsed if isinstance(x, str) and x.strip()][:3] if isinstance(parsed, list) else []
    except Exception:
        return []


def handle_explicit_memory_command(prompt):
    """Return a memory payload for explicit remember requests, otherwise None."""
    import re
    match = re.match(r"^\s*(?:j\.a\.n\.e\.\s*)?(?:remember(?:\s+that)?|save\s+to\s+memory)\s*[:,-]?\s*(.+?)\s*$", prompt, re.I | re.S)
    return match.group(1).strip() if match else None
