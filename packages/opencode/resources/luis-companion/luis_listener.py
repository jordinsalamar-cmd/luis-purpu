"""Low-resource Spanish microphone listener for Rem."""

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None


class StreamingCleaner:
    """Filtro ligero de reducción de ruido para el micrófono local."""

    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.prev_x = 0.0
        self.prev_y = 0.0
        self.profile = None
        self.alpha = 0.994

    def _stft(self, samples):
        n_fft = 512
        hop = 128
        window = np.hanning(n_fft)
        count = max(1, 1 + (len(samples) - n_fft) // hop)
        result = np.zeros((count, n_fft // 2 + 1), dtype=np.complex128)
        for index in range(count):
            start = index * hop
            frame = samples[start:start + n_fft]
            if len(frame) < n_fft:
                frame = np.pad(frame, (0, n_fft - len(frame)))
            result[index] = np.fft.rfft(frame * window)
        return result

    def _istft(self, spectrum, length):
        n_fft = 512
        hop = 128
        window = np.hanning(n_fft)
        output = np.zeros(length + n_fft)
        weights = np.zeros(length + n_fft)
        for index, frame in enumerate(spectrum):
            start = index * hop
            output[start:start + n_fft] += np.fft.irfft(frame, n_fft) * window
            weights[start:start + n_fft] += window ** 2
        weights[weights < 1e-8] = 1.0
        return output[:length] / weights[:length]

    def clean(self, data):
        if np is None or not data:
            return data
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float64) / 32768.0
        if not len(samples):
            return data

        filtered = np.empty_like(samples)
        previous_x = self.prev_x
        previous_y = self.prev_y
        for index, value in enumerate(samples):
            previous_y = self.alpha * (previous_y + value - previous_x)
            previous_x = value
            filtered[index] = previous_y
        self.prev_x = previous_x
        self.prev_y = previous_y

        rms = float(np.sqrt(np.mean(filtered ** 2)))
        if rms < 0.0005:
            return bytes(len(data))

        spectrum = self._stft(filtered)
        magnitude = np.abs(spectrum)
        if self.profile is None:
            self.profile = np.median(magnitude, axis=0) + 1e-12
            cleaned = filtered
        else:
            gain = 1.0 - 0.3 * self.profile / (magnitude + 1e-12)
            gain = np.clip(gain, 0.0, 1.0)
            cleaned = self._istft(magnitude * gain * np.exp(1j * np.angle(spectrum)), len(filtered))

        cleaned_rms = float(np.sqrt(np.mean(cleaned ** 2))) + 1e-12
        cleaned *= min(12.0, 0.12 / cleaned_rms)
        return (np.clip(cleaned, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()


def emit(payload):
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def normalize(text):
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def wake_words(value):
    words = [normalize(item.strip()) for item in re.split(r"[,|]", value or "") if item.strip()]
    if "ren" in words:
        words.extend(["rem"])
    return list(dict.fromkeys(words))


def tail_after_wake(text, wakes):
    normalized = normalize(text)
    for wake in sorted(wakes, key=len, reverse=True):
        match = re.search(rf"\b{re.escape(wake)}\b(.*)$", normalized, re.IGNORECASE)
        if match:
            return match.group(1).strip(" ,;:.-")
    return ""


def transcribe_audio(chunks, whisper_cli, whisper_model, sample_rate):
    if not whisper_cli or not whisper_model or not chunks:
        return ""
    audio_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="luis-orden-", suffix=".wav", delete=False) as audio_file:
            audio_path = audio_file.name
        with wave.open(audio_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"".join(chunks))
        result = subprocess.run(
            [
                str(whisper_cli), "-m", str(whisper_model), "-f", audio_path,
                "-l", "es", "-t", "4", "-ng", "-np", "-nt",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
            check=False,
        )
        lines = []
        for line in result.stdout.splitlines():
            clean = re.sub(r"\[[^\]]+-->[^\]]+\]", " ", line).strip()
            if clean and not clean.startswith(("whisper_", "ggml_", "system_info:")):
                lines.append(clean)
        return " ".join(lines).strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    finally:
        if audio_path:
            try:
                os.remove(audio_path)
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--wake", default="ren,guapa")
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--whisper-cli")
    parser.add_argument("--whisper-model")
    args = parser.parse_args()

    try:
        import sounddevice as sd
        from vosk import KaldiRecognizer, Model, SetLogLevel
    except ImportError as error:
        emit({"type": "error", "message": f"Faltan dependencias de micrófono: {error}"})
        return 2

    model_path = Path(args.model)
    if not model_path.exists():
        emit({"type": "error", "message": f"No encontré el modelo de voz: {model_path}"})
        return 3

    SetLogLevel(-1)
    whisper_cli = Path(args.whisper_cli) if args.whisper_cli else None
    whisper_model = Path(args.whisper_model) if args.whisper_model else None
    if not (whisper_cli and whisper_cli.exists() and whisper_model and whisper_model.exists()):
        whisper_cli = None
        whisper_model = None
    try:
        model = Model(str(model_path))
        audio_queue = queue.Queue(maxsize=24)
        cleaner = StreamingCleaner(args.sample_rate) if np is not None else None
    except Exception as error:
        emit({"type": "error", "message": f"No pude cargar el modelo de voz: {error}"})
        return 4

    def callback(indata, frames, callback_time, status):
        del frames, callback_time
        if status:
            print(f"audio: {status}", file=sys.stderr, flush=True)
        try:
            audio_queue.put_nowait(bytes(indata))
        except queue.Full:
            pass

    continuous_mode = args.continuous or not args.wake.strip()
    command_recognizer = KaldiRecognizer(model, args.sample_rate) if continuous_mode else None
    wake_recognizer = KaldiRecognizer(model, args.sample_rate) if not continuous_mode else None
    wake_audio = []
    command_audio = []
    command_deadline = 0.0
    wake_normalized = wake_words(args.wake)
    emit({
        "type": "ready",
        "wake": args.wake or None,
        "mode": "continuous" if continuous_mode else "wake",
        "engine": "vosk+whisper" if whisper_cli and not continuous_mode else "vosk",
    })

    try:
        with sd.RawInputStream(
            samplerate=args.sample_rate,
            blocksize=4000,
            dtype="int16",
            channels=1,
            callback=callback,
        ):
            while True:
                try:
                    data = audio_queue.get(timeout=0.5)
                except queue.Empty:
                    if not continuous_mode and command_recognizer and time.monotonic() > command_deadline:
                        command_recognizer = None
                        command_audio = []
                    continue

                if cleaner is not None:
                    data = cleaner.clean(data)

                if continuous_mode:
                    command_audio.append(data)
                    if command_recognizer.AcceptWaveform(data):
                        result = json.loads(command_recognizer.Result()).get("text", "").strip()
                        if result:
                            emit({"type": "command", "text": result, "source": "microfono", "engine": "vosk"})
                        command_audio = []
                    continue

                if command_recognizer is not None:
                    command_audio.append(data)
                    if command_recognizer.AcceptWaveform(data):
                        result = json.loads(command_recognizer.Result()).get("text", "").strip()
                        accurate = transcribe_audio(command_audio, whisper_cli, whisper_model, args.sample_rate)
                        command = accurate or result
                        if command:
                            emit({"type": "command", "text": command, "source": "microfono", "engine": "whisper" if accurate else "vosk"})
                            command_recognizer = None
                            command_audio = []
                        elif time.monotonic() > command_deadline:
                            command_recognizer = None
                            command_audio = []
                    command_deadline = time.monotonic() + 8.0
                    continue

                wake_audio.append(data)
                if len(wake_audio) > 24:
                    wake_audio.pop(0)
                if wake_recognizer.AcceptWaveform(data):
                    result = json.loads(wake_recognizer.Result()).get("text", "").strip()
                    normalized_result = normalize(result)
                    if any(wake in normalized_result for wake in wake_normalized):
                        accurate = transcribe_audio(wake_audio, whisper_cli, whisper_model, args.sample_rate)
                        transcribed = accurate or result
                        command = tail_after_wake(transcribed, wake_normalized)
                        if accurate and not command and not any(wake in normalize(accurate) for wake in wake_normalized):
                            command = accurate.strip(" ,;:.-")
                        if command:
                            emit({"type": "command", "text": command, "source": "microfono", "engine": "whisper" if accurate else "vosk"})
                        else:
                            command_recognizer = KaldiRecognizer(model, args.sample_rate)
                            command_audio = []
                            command_deadline = time.monotonic() + 8.0
                            emit({"type": "listening", "wake": args.wake})
                        wake_recognizer = KaldiRecognizer(model, args.sample_rate)
                        wake_audio = []
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        emit({"type": "error", "message": f"No pude abrir el micrófono: {error}"})
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
