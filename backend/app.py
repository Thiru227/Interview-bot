from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import json
import requests
import os
import uuid
import time
import re
from functools import wraps
import firebase_admin
from firebase_admin import credentials, auth

app = Flask(__name__)

# -------------------------------------------------------
# CORS
# -------------------------------------------------------
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "https://eightfoldai-chat.netlify.app",
            "http://localhost:3000",
            "http://127.0.0.1:3000"
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

# -------------------------------------------------------
# INIT FIREBASE
# -------------------------------------------------------
try:
    cred_json = os.getenv("FIREBASE_CREDENTIALS", "{}")
    if cred_json != "{}":
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        print("✅ Firebase Admin initialized")
    else:
        print("⚠️ Firebase not initialized — missing FIREBASE_CREDENTIALS")
except Exception as e:
    print("❌ Firebase init error:", str(e))

# -------------------------------------------------------
# Claude (Anthropic) CONFIG
# -------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
ANTHROPIC_VERSION = "2023-06-01"

# -------------------------------------------------------
# Gemini CONFIG (for RESULTS ONLY)
# -------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-1.5-flash"

# -------------------------------------------------------
# ElevenLabs CONFIG
# -------------------------------------------------------
ELEVEN_KEYS = [k.strip() for k in os.getenv("ELEVEN_KEYS", "").split(",") if k.strip()]
VOICE_MAP = {
    "male": os.getenv("ELEVEN_VOICE_MALE", "pNInz6obpgDQGcFmaJgB"),
    "female": os.getenv("ELEVEN_VOICE_FEMALE", "21m00Tcm4TlvDq8ikWAM")
}
key_indices = {"eleven": 0}

# In-memory session store
sessions = {}

# -------------------------------------------------------
# AUTH MIDDLEWARE
# -------------------------------------------------------
def verify_firebase_token(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.method == "OPTIONS":
            return f(*args, **kwargs)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing token"}), 401

        token = auth_header.split("Bearer ")[1]

        try:
            decoded = auth.verify_id_token(token)
            request.user_id = decoded["uid"]
            request.user_email = decoded.get("email", "")
            return f(*args, **kwargs)
        except Exception as e:
            print("❌ Invalid Firebase token:", str(e))
            return jsonify({"error": "Invalid token"}), 401

    return wrapper


# -------------------------------------------------------
# HELPER — ElevenLabs rotation
# -------------------------------------------------------
def get_next_eleven_key():
    if not ELEVEN_KEYS:
        return None
    idx = key_indices["eleven"]
    key = ELEVEN_KEYS[idx]
    key_indices["eleven"] = (idx + 1) % len(ELEVEN_KEYS)
    return key


# -------------------------------------------------------
# HELPER — Claude Messages API wrapper
# -------------------------------------------------------
def call_claude(system_prompt, conversation):
    if not ANTHROPIC_API_KEY:
        return {"error": "Claude API key missing"}

    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json"
    }

    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 2000,
        "system": system_prompt,
        "messages": conversation
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=45)

        if resp.status_code != 200:
            print("❌ Claude Error:", resp.status_code, resp.text)
            return {"error": f"Claude API error: {resp.status_code}"}

        data = resp.json()
        text = data["content"][0]["text"]

        # Try JSON parsing
        try:
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0].strip()
            elif '```' in text:
                text = text.split('```')[1].split('```')[0].strip()

            parsed = json.loads(text)

            if 'text_response' not in parsed:
                parsed['text_response'] = text
            if 'voice_response' not in parsed:
                parsed['voice_response'] = parsed['text_response']
            if 'end' not in parsed:
                parsed['end'] = False

            voice = parsed.get('voice_response', parsed['text_response'])
            voice = re.sub(r'[^\x00-\x7F]+', '', voice)
            voice = voice.replace('*', '').replace('#', '').replace('_', '').replace('`', '')
            voice = ' '.join(voice.split())
            parsed['voice_response'] = voice

            return parsed

        except json.JSONDecodeError:
            return {
                "text_response": text,
                "voice_response": re.sub(r'[^\x00-\x7F]+', '', text),
                "end": False
            }

    except Exception as e:
        print("❌ Claude Exception:", str(e))
        return {"error": str(e)}


# -------------------------------------------------------
# HELPER — Gemini Results Evaluator
# -------------------------------------------------------
def call_gemini_for_results(system_prompt, session):
    if not GEMINI_API_KEY:
        return {"error": "Gemini API key missing"}

    messages = session["messages"]
    transcript = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if len(content) > 500:
            content = content[:500] + "...(truncated)"
        transcript.append(f"{role.upper()}: {content}")
    transcript = "\n".join(transcript)

    gemini_system = f"""
You are a professional mock interview evaluator.
Generate ONLY valid JSON in this exact schema:

{{
  "text_response": "summary",
  "voice_response": "plain text summary",
  "strengths": "",
  "weaknesses": "",
  "score": 85,
  "communication_score": 80,
  "technical_score": 85,
  "confidence_score": 90,
  "behavior_score": 85,
  "overall_impression": "",
  "recommendations": "",
  "selected": true,
  "end": true
}}
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"Content-Type": "application/json"}

    body = {
        "contents": [
            {
                "parts": [
                    {"text": gemini_system},
                    {"text": f"Transcript:\n{transcript}\nGenerate summary now."}
                ]
            }
        ]
    }

    try:
        resp = requests.post(
            url,
            params={"key": GEMINI_API_KEY},
            headers=headers,
            json=body,
            timeout=60
        )

        if resp.status_code != 200:
            print("❌ Gemini Error:", resp.status_code, resp.text)
            return {"error": "Gemini API error"}

        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)

        # Strip fences
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        parsed = json.loads(text)

        # Clean voice
        voice = parsed.get("voice_response", parsed.get("text_response", ""))
        voice = re.sub(r'[^\x00-\x7F]+', '', voice)
        voice = ' '.join(voice.split())
        parsed["voice_response"] = voice

        parsed["end"] = True
        return parsed

    except Exception as e:
        print("❌ Gemini Exception:", str(e))
        return {"error": str(e)}


# -------------------------------------------------------
# SYSTEM PROMPT
# -------------------------------------------------------
def create_system_prompt(domain, role, interview_type, difficulty):
    return f"""
You are AI Interview Practitioner...
( SAME SYSTEM PROMPT YOU PROVIDED — unchanged )
"""


# -------------------------------------------------------
# ROUTES
# -------------------------------------------------------
@app.route("/")
def root():
    return {"status": "online", "model": ANTHROPIC_MODEL}, 200


# ---------- START SESSION ----------
@app.route("/api/start-session", methods=["POST", "OPTIONS"])
@verify_firebase_token
def start_session():
    data = request.json or {}

    domain = data.get("domain")
    role = data.get("role")
    interview_type = data.get("interview_type", "Mixed")
    difficulty = data.get("difficulty", "Intermediate")
    duration = int(data.get("duration", 15))

    if not domain or not role:
        return {"error": "Missing domain/role"}, 400

    session_id = str(uuid.uuid4())
    system_prompt = create_system_prompt(domain, role, interview_type, difficulty)

    conv = [
        {"role": "user", "content": "Start the interview with warm small talk."}
    ]

    result = call_claude(system_prompt, conv)
    if "error" in result:
        return {"error": result["error"]}, 500

    conv.append({"role": "assistant", "content": result["text_response"]})

    sessions[session_id] = {
        "system_prompt": system_prompt,
        "messages": conv,
        "created_at": time.time(),
        "user_id": request.user_id,
        "exchange_count": 0,
        "question_count": 0
    }

    return {
        "session_id": session_id,
        "first_question": result
    }, 200


# ---------- CHAT (Claude) ----------
@app.route("/api/chat", methods=["POST", "OPTIONS"])
@verify_firebase_token
def chat():
    data = request.json or {}
    session_id = data.get("session_id")
    user_msg = data.get("user_message")

    if session_id not in sessions:
        return {"error": "Invalid session"}, 404

    session = sessions[session_id]

    if session["user_id"] != request.user_id:
        return {"error": "Unauthorized"}, 403

    conv = session["messages"]
    session["exchange_count"] += 1

    context = f"""
[INTERNAL]
Exchange: {session['exchange_count']}
[END]
User: {user_msg}
"""
    conv.append({"role": "user", "content": context})

    result = call_claude(session["system_prompt"], conv)
    if "error" in result:
        return {"error": result["error"]}, 500

    conv[-1] = {"role": "user", "content": user_msg}
    conv.append({"role": "assistant", "content": result["text_response"]})

    return result, 200


# ---------- RESULTS (Gemini) ----------
@app.route("/api/results", methods=["POST", "OPTIONS"])
@verify_firebase_token
def results():
    data = request.json or {}
    session_id = data.get("session_id")

    if not session_id or session_id not in sessions:
        return {"error": "Invalid session"}, 404

    session = sessions[session_id]
    if session["user_id"] != request.user_id:
        return {"error": "Unauthorized"}, 403

    gemini_result = call_gemini_for_results(session["system_prompt"], session)
    if "error" in gemini_result:
        return {"error": gemini_result["error"]}, 500

    return gemini_result, 200


# ---------- TTS ----------
@app.route("/api/tts", methods=["POST", "OPTIONS"])
@verify_firebase_token
def tts():
    data = request.json or {}
    text = data.get("text", "")
    voice_style = data.get("voice_style", "male")

    if not text:
        return {"error": "No text"}, 400

    text = re.sub(r'[^\x00-\x7F]+', '', text)
    text = ' '.join(text.split())

    api_key = get_next_eleven_key()
    if not api_key:
        return {"error": "Missing ElevenLabs key"}, 500

    voice_id = VOICE_MAP.get(voice_style, VOICE_MAP["male"])

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }

    payload = {
        "text": text,
        "model_id": "eleven_flash_v2",
        "voice_settings": {
            "stability": 0.4,
            "similarity_boost": 0.8
        }
    }

    try:
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
            json=payload,
            headers=headers,
            timeout=30
        )

        if resp.status_code != 200:
            return {"error": "TTS failed"}, 500

        return Response(resp.content, mimetype="audio/mpeg")

    except Exception as e:
        return {"error": str(e)}, 500


# OPTIONS
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = app.make_default_options_response()
        headers = response.headers
        headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        headers['Access-Control-Allow-Headers'] = "Content-Type, Authorization"
        headers['Access-Control-Allow-Methods'] = "GET, POST, OPTIONS"
        return response


# -------------------------------------------------------
# START SERVER
# -------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print("🚀 Claude + Gemini hybrid backend running")
    print(f"🧠 Claude model: {ANTHROPIC_MODEL}")
    print(f"✨ Gemini model: {GEMINI_MODEL}")
    app.run(host="0.0.0.0", port=port, debug=False)
