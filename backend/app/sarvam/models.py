"""Sarvam model IDs, endpoints and voices. The ONLY place these are written down.

TODO(Charulatha): confirm every value below against docs.sarvam.ai (VOICE_AND_NOTICE section 2)
and replace the placeholders. Changing any model or parameter changes the cache keys, so re-run
the demo cache warm-up afterwards.
"""

BASE_URL = "https://api.sarvam.ai"  # TODO(Charulatha): confirm
AUTH_HEADER = "api-subscription-key"  # TODO(Charulatha): confirm

LANGUAGE_CODES = {"ta": "ta-IN", "te": "te-IN", "en": "en-IN"}

# Speech to text (Saarika / Saaras family)
STT_PATH = "/speech-to-text"  # TODO(Charulatha): confirm
STT_MODEL = "saarika:v2.5"  # TODO(Charulatha): confirm current model ID

# Chat LLM (intent + entity extraction, notice field extraction)
CHAT_PATH = "/v1/chat/completions"  # TODO(Charulatha): confirm
CHAT_MODEL = "sarvam-m"  # TODO(Charulatha): confirm current model ID

# Text to speech (Bulbul)
TTS_PATH = "/text-to-speech"  # TODO(Charulatha): confirm
TTS_MODEL = "bulbul:v2"  # TODO(Charulatha): confirm current model ID
TTS_SPEAKERS = {  # one friendly voice per language, used everywhere
    "ta": "anushka",  # TODO(Charulatha): pick the Tamil voice
    "te": "anushka",  # TODO(Nagasai Sree): pick the Telugu voice
    "en": "anushka",
}

# Vision / document intelligence (reading the sample notice)
VISION_PATH: str | None = None  # TODO(Charulatha): set when the API is confirmed; None = cache only
VISION_MODEL = "TODO-vision-model"  # TODO(Charulatha): confirm

# Timeouts in seconds (VOICE_AND_NOTICE section 3)
TIMEOUT_STT = 8.0
TIMEOUT_CHAT = 8.0
TIMEOUT_TTS = 10.0
TIMEOUT_VISION = 10.0
