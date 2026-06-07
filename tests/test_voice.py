import struct

from nuru_bot.voice import HotwordDetector, VoiceActivityDetector


def test_hotword_detector_matches_configured_words():
    detector = HotwordDetector(["nuru", "hey bot"])

    assert detector.matches("hey Nuru, wake up")
    assert detector.matches("please HEY   BOT now")
    assert not detector.matches("just talking")
    assert not detector.matches("manuru is not a wake word")
    assert not detector.matches("hey botany facts")


def test_voice_activity_detector_uses_rms_threshold():
    loud_samples = b"".join(struct.pack("<h", 2000) for _ in range(200))
    quiet_samples = b"".join(struct.pack("<h", 10) for _ in range(200))
    detector = VoiceActivityDetector(rms_threshold=500)

    assert detector.detects_speech(loud_samples)
    assert not detector.detects_speech(quiet_samples)
