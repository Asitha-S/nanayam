"""Sarvam model IDs, endpoints and voices. The ONLY place these are written down."""

BASE_URL = "https://api.sarvam.ai"
AUTH_HEADER = "api-subscription-key"

LANGUAGE_CODES = {"ta": "ta-IN", "te": "te-IN", "en": "en-IN"}

# Speech to text (Saaras family)
STT_PATH = "/speech-to-text"
STT_MODEL = "saaras:v4"

# Chat LLM (intent + entity extraction, notice field extraction)
CHAT_PATH = "/v2/chat/completions"
CHAT_MODEL = "sarvam-105b"

# Text to speech (Bulbul)
TTS_PATH = "/text-to-speech"
TTS_MODEL = "bulbul:v3"
TTS_SPEAKERS = {
    "ta": "shubh",
    "te": "shubh",
    "en": "shubh",
}

# Vision / document intelligence (reading the sample notice)
VISION_PATH: str | None = None
VISION_MODEL = "sarvam-vision-v1"

# Timeouts in seconds (VOICE_AND_NOTICE section 3)
TIMEOUT_STT = 8.0
TIMEOUT_CHAT = 8.0
TIMEOUT_TTS = 10.0
TIMEOUT_VISION = 10.0
