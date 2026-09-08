import wave

from vss_worker.harmonic_synth import F0Frame, synthesize_harmonic, write_wav


def test_harmonic_synth_respects_voicing_and_writes_pcm16(tmp_path) -> None:
    frames = [
        F0Frame(0.0, 440.0, 0.9),
        F0Frame(0.01, 440.0, 0.9),
        F0Frame(0.02, 0.0, 0.1),
    ]
    pcm, report = synthesize_harmonic(frames, sample_rate=1_000, harmonics=3)
    assert report["voiced_frame_count"] == 2
    assert len(pcm) == 30 * 2
    assert pcm[-10:] == b"\0" * 10
    target = tmp_path / "harmonic.wav"
    write_wav(target, pcm, 1_000)
    with wave.open(str(target), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getframerate() == 1_000
        assert audio.getnframes() == 30
