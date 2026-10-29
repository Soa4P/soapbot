"""Voice: speech in, speech out, and the degradation rules for both.

Both directions fail *open* into text. A group that cannot transcribe a voice message
still sees that one was sent (``[语音]``); a reply that cannot be synthesised is sent
as text instead. Neither ever invents content on the user's behalf.
"""

from soapbot.voice.stt import (
    PLACEHOLDER,
    AudioFetcher,
    ProviderTranscriber,
    Transcription,
    VoiceError,
    check_audio_url,
    http_fetch,
    render_prompt,
)
from soapbot.voice.tts import DEFAULT_MAX_CHARS, EdgeTts, TtsEngine, VoiceUnavailableError

__all__ = [
    "DEFAULT_MAX_CHARS",
    "PLACEHOLDER",
    "AudioFetcher",
    "EdgeTts",
    "ProviderTranscriber",
    "Transcription",
    "TtsEngine",
    "VoiceError",
    "VoiceUnavailableError",
    "check_audio_url",
    "http_fetch",
    "render_prompt",
]
