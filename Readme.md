🚀 AI Interview Simulator Backend
Claude + Gemini Hybrid • Firebase Auth • ElevenLabs TTS • Flask API

This is a production-ready Flask backend that powers an advanced AI-based mock interview system with:

✅ Anthropic Claude — Real-time interview responses
✅ Google Gemini — Final interview evaluation & scoring
✅ Firebase Authentication — Secure user access
✅ ElevenLabs TTS — Natural AI voice replies
✅ CORS-secured API — For React/Next.js/Netlify frontend
✅ Session-based chat handling
✅ Key rotation support for ElevenLabs

🧠 Features
🎤 1. AI Interview Engine (Claude)

Uses Claude Messages API

Handles multi-turn conversation

Cleans JSON and text responses

Maintains session messages with questions & answers

Warm-up intro + structured interview

📝 2. Interview Results Generator (Gemini)

After session ends, Gemini produces:

Summary

Strengths

Weaknesses

5 category scores

Final selection decision

JSON-strict formatted output

🔐 3. Firebase Auth Integration

Every API route is protected with a custom middleware:

Verifies Firebase ID token

Rejects unauthorized requests

Attaches user_id & email to request context

🔊 4. ElevenLabs TTS

Multi-key rotation (prevents rate limits)

Outputs audio/mpeg

Cleans non-ASCII text

Male/Female voice supported

🌐 5. CORS & Security

Supports only:

https://eightfoldai-chat.netlify.app
http://localhost:3000
http://127.0.0.1:3000


Allows:

GET

POST

OPTIONS

Credentials

📁 Project Structure
project/
│── app.py               # Main Flask backend
│── requirements.txt     # Python dependencies
│── README.md            # Documentation (this file)

🔧 Environment Variables

Add these in your deployment (Railway/Render/Vercel/Ubuntu):

PORT=5000

# Firebase
FIREBASE_CREDENTIALS={...firebase json...}

# Claude
ANTHROPIC_API_KEY=your_key_here

# Gemini
GEMINI_API_KEY=your_key_here

# ElevenLabs
ELEVEN_KEYS=key1,key2,key3
ELEVEN_VOICE_MALE=pNInz6obpgDQGcFmaJgB
ELEVEN_VOICE_FEMALE=21m00Tcm4TlvDq8ikWAM

▶️ Running Locally
Install dependencies
pip install -r requirements.txt

Start server
python app.py


Backend runs at:

http://localhost:5000

📡 API Endpoints
1. Start Interview Session

POST /api/start-session

Body:
{
  "domain": "Software Engineering",
  "role": "Frontend Developer",
  "interview_type": "Technical",
  "difficulty": "Intermediate",
  "duration": 15
}


Returns:

session_id

first question

2. Continue Chat (Claude)

POST /api/chat

Body:
{
  "session_id": "uuid",
  "user_message": "My answer..."
}

3. Generate Final Results (Gemini)

POST /api/results

Body:
{ "session_id": "uuid" }

4. Text to Speech (ElevenLabs)

POST /api/tts

Body:
{
  "text": "Hello...",
  "voice_style": "male"
}


Returns audio/mpeg file.

🧪 Example Frontend (React)
const res = await fetch("/api/chat", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`
  },
  body: JSON.stringify({
    session_id,
    user_message
  })
});

🛡️ Security Notes

Firebase ID Token required for every protected route

ElevenLabs keys auto-rotate

JSON sanitization for LLM responses

Truncation for Gemini prompts to reduce overload

✨ Tech Stack
Component	Technology
Interview Engine	Claude Sonnet
Evaluation	Gemini 1.5 Flash
Backend	Flask
Auth	Firebase
Voice	ElevenLabs
Deployment	Railway / Render / EC2 / Netlify Frontend
