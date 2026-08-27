import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import tempfile
import time
from pathlib import Path


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def write_json(path, value):
    temporary = Path(f"{path}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        pass


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def claim_json(path):
    """Claim a command atomically so a newer command cannot be deleted by a reader."""
    source = Path(path)
    claimed = source.with_name(f"{source.name}.{os.getpid()}.processing")
    try:
        os.replace(source, claimed)
    except OSError:
        return None
    try:
        return read_json(claimed)
    finally:
        try:
            claimed.unlink(missing_ok=True)
        except OSError:
            pass


def repair_mojibake(value):
    """Repair UTF-8 text decoded once with a Windows/Latin-1 code page."""
    text = str(value or "")
    if not any(marker in text for marker in ("Ã", "Â", "â€", "ðŸ")):
        return text
    try:
        repaired = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return repaired if repaired.count("�") <= text.count("�") else text


def clean_text(value):
    return repair_mojibake(re.sub(r"\x1b\[[0-9;]*m", "", str(value or "")).strip())


def clean_speech(value):
    text = repair_mojibake(str(value or ""))
    text = re.sub(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", " ", text)
    text = re.sub(r"```[\s\S]*?```", " El resultado quedó en pantalla. ", text)
    text = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"https?://\S+", " enlace ", text)
    text = re.sub(r"\basync\s*/\s*await\b", "asíncrono y espera", text, flags=re.IGNORECASE)
    text = re.sub(r"\basync\b", "asíncrono", text, flags=re.IGNORECASE)
    text = re.sub(r"\bawait\b", "espera", text, flags=re.IGNORECASE)
    text = re.sub(r"[`*_#{}\[\]<>|\\/$=~^%]", " ", text)
    text = re.sub(r"(?<!\w)[&@+]+(?!\w)", " ", text)
    text = re.sub(r"(?:^|\s)[>$]+(?=\s|$)", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:1600]


class LuisHost:
    def __init__(self, args):
        self.args = args
        self.stop_event = threading.Event()
        self.command_thread = None
        self.listener_process = None
        self.mascot_process = None
        self.busy = False
        self.speech_lock = threading.Lock()
        self.speech_process = None
        self.speech_cancel = threading.Event()
        self.voice = True
        self.listening = False
        self.vision_enabled = os.environ.get("LUIS_VISION", "1").strip().lower() not in {"0", "false", "off"}
        self.vision_thread = None
        self.vision_path = Path(tempfile.gettempdir()) / "luis-vision-latest.png"
        self.state = {"visible": True, "voice": True, "listening": False, "status": "idle"}
        self.pid_file = Path(args.state).with_suffix(".pid")
        self.input_file = Path(args.command).with_name("luis-companion-input.json")
        self.voice_name = os.environ.get(
            "LUIS_TTS_VOICE_OFFLINE", os.environ.get("LUIS_TTS_VOICE", "Microsoft Sabina")
        )
        self.online_voice = os.environ.get("LUIS_TTS_VOICE_ONLINE", "es-MX-DaliaNeural")
        self.voice_mode = os.environ.get("LUIS_TTS_MODE", "auto").strip().lower()
        default_piper_model = (
            Path(__file__).resolve().parent
            / "models"
            / "piper"
            / "es_MX-claude-high.onnx"
        )
        self.piper_model = Path(os.environ.get("LUIS_TTS_PIPER_MODEL", str(default_piper_model)))
        self.ffplay = self.find_ffplay()
        self.tts_python = self.find_tts_python()
        self.runtime_python = self.tts_python or sys.executable or self.args.python

    def find_ffplay(self):
        configured = os.environ.get("LUIS_FFPLAY")
        candidates = [
            configured,
            shutil.which("ffplay"),
            Path.home() / "AppData" / "Local" / "Rem" / "ffmpeg" / "ffplay.exe",
            Path.home() / "AppData" / "Local" / "Rem" / "ffmpeg" / "ffmpeg-9.0.1-essentials_build" / "bin" / "ffplay.exe",
        ]
        winget_dir = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
        try:
            candidates.extend(winget_dir.rglob("ffplay.exe"))
        except OSError:
            pass
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return str(candidate)
        return None

    def find_tts_python(self):
        candidates = [sys.executable, self.args.python, shutil.which(str(self.args.python))]
        for candidate in dict.fromkeys(value for value in candidates if value):
            try:
                result = subprocess.run(
                    [
                        candidate,
                        "-c",
                        "import importlib.util; "
                        "assert importlib.util.find_spec('piper') or importlib.util.find_spec('edge_tts')",
                    ],
                    creationflags=CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=8,
                    check=False,
                )
                if result.returncode == 0:
                    return candidate
            except (OSError, subprocess.SubprocessError):
                pass
        return None

    def save_state(self, **updates):
        self.state.update(updates)
        self.state["voice"] = self.voice
        self.state["listening"] = self.listening
        self.state["vision"] = self.vision_enabled
        write_json(self.args.state, self.state)

    def capture_vision(self):
        try:
            from PIL import ImageGrab

            image = ImageGrab.grab(all_screens=True)
            if image.width > 1600:
                height = max(1, round(image.height * 1600 / image.width))
                image = image.resize((1600, height))
            temporary = self.vision_path.with_suffix(f".{os.getpid()}.tmp.png")
            image.save(temporary, "PNG", optimize=True)
            os.replace(temporary, self.vision_path)
            return True
        except Exception as error:
            try:
                self.state["vision_error"] = str(error)[:180]
                write_json(self.args.state, self.state)
            except OSError:
                pass
            return False

    def vision_loop(self):
        # Keep the last screen available without running a high-frequency
        # capture loop while Luis is idle. The model only receives the image
        # when it calls desktop(vision); this observer is just a cheap cache.
        idle_interval = max(2.0, float(os.environ.get("LUIS_VISION_IDLE_INTERVAL", "3.0")))
        active_interval = max(0.75, float(os.environ.get("LUIS_VISION_INTERVAL", "1.5")))
        while not self.stop_event.is_set() and self.vision_enabled:
            if self.capture_vision():
                self.save_state(vision_updated=time.time(), vision_error=None)
            status = str(self.state.get("status", "idle")).lower()
            interval = idle_interval if status in {"idle", "muted"} else active_interval
            self.stop_event.wait(interval)

    def start_vision(self):
        if not self.vision_enabled or (self.vision_thread and self.vision_thread.is_alive()):
            return self.vision_enabled
        self.vision_thread = threading.Thread(target=self.vision_loop, daemon=True, name="luis-screen-observer")
        self.vision_thread.start()
        self.save_state(vision=True)
        return True

    def stop_vision(self):
        self.vision_enabled = False
        self.save_state(vision=False)

    def stop_old_host(self):
        try:
            old_pid = self.pid_file.read_text(encoding="utf-8").strip()
            if old_pid.isdigit() and int(old_pid) != os.getpid():
                subprocess.run(["taskkill", "/PID", old_pid, "/T", "/F"], creationflags=CREATE_NO_WINDOW,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except OSError:
            pass
        try:
            self.pid_file.write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            pass

    def start_mascot(self):
        try:
            self.mascot_process = subprocess.Popen(
                [self.runtime_python, self.args.mascot, "--state", self.args.state, "--command", self.args.command, "--vrm", self.args.vrm],
                cwd=str(Path(self.args.mascot).parent), creationflags=CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        except OSError as error:
            self.save_state(status="error", error=f"No se pudo iniciar el cuerpo: {error}")
            return False

    def start_listener(self):
        if self.listener_process and self.listener_process.poll() is None:
            return True
        model = Path(self.args.model)
        if not model.exists():
            self.save_state(status="idle")
            return False
        try:
            self.listener_process = subprocess.Popen(
                [self.runtime_python, self.args.listener, "--model", str(model), "--wake", "rem,guapa"],
                cwd=str(Path(self.args.listener).parent), creationflags=CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
            )
        except OSError:
            self.listener_process = None
            return False
        threading.Thread(target=self.read_listener, daemon=True).start()
        return True

    def stop_listener(self):
        process = self.listener_process
        self.listener_process = None
        if process and process.poll() is None:
            process.terminate()
        self.listening = False
        self.save_state()

    def read_listener(self):
        process = self.listener_process
        if not process or not process.stdout:
            return
        for line in process.stdout:
            if self.stop_event.is_set():
                break
            event = read_line(line)
            if not event:
                continue
            if event.get("type") == "ready":
                self.listening = True
                self.save_state(status="idle")
            elif event.get("type") == "error":
                self.listening = False
                self.save_state(status="idle")
            elif event.get("type") == "listening":
                self.save_state(status="listening")
            elif event.get("type") == "command" and event.get("text"):
                self.submit_to_terminal(str(event["text"]))

        if process is self.listener_process and not self.stop_event.is_set():
            self.listener_process = None
            self.listening = False
            self.save_state(status="idle", error="El micrófono se cerró; pulsa el botón para reintentarlo.")

    def submit_to_terminal(self, request, source="microfono"):
        text = request.strip()
        if not text:
            return
        write_json(self.input_file, {"text": text, "source": source, "created": time.time()})
        self.save_state(status="idle")

    def stop_speech(self):
        self.speech_cancel.set()
        process = self.speech_process
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def answer(self, request):
        if self.busy:
            return
        self.busy = True
        self.save_state(status="thinking")
        try:
            normalized = request.strip().lower()
            if normalized in {"hola", "buenas", "buenos dias", "buenas tardes", "hey"}:
                answer = "Hola, jefe."
            else:
                prompt = (
                    "Eres Rem de Re:ZERO, una asistente de escritorio femenina. Eres una oni superviviente, hermana gemela de Ram "
                    "y antigua maid de la mansión de Roswaal; tu pasado te hizo disciplinada, protectora, empática y valiente. "
                    "Responde en español latinoamericano, sin emojis, con personalidad cálida, cariñosa, serena y natural. "
                    "Habla de ti misma en femenino: 'lista', 'atenta', 'preparada' y 'tranquila'; nunca uses formas masculinas para ti. "
                    "Sé breve: para una solicitud corta usa una o dos frases. "
                    "No repitas la instrucción ni escribas un testamento. Si debes trabajar, indica primero qué harás.\n\n"
                    f"Solicitud del jefe: {request}"
                )
                result = subprocess.run(
                    [self.args.luis_bin, "run", "--format", "default", prompt],
                    cwd=self.args.cwd, creationflags=CREATE_NO_WINDOW,
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
                    env={**os.environ, "LUIS_COMPANION": "0"}, check=False,
                )
                answer = clean_text(result.stdout or result.stderr) or "No pude responderte, jefe."
            self.save_state(status="speaking")
            if self.voice:
                self.speak(answer)
        except (OSError, subprocess.SubprocessError) as error:
            self.save_state(status="idle", error=str(error)[:220])
        finally:
            self.busy = False
            self.save_state(status="idle")

    def speak(self, answer):
        text = clean_speech(answer)
        if not text or not self.voice:
            return False
        with self.speech_lock:
            self.speech_cancel.clear()
            if self.voice_mode == "offline":
                return self.speak_offline(text)
            if self.voice_mode == "online":
                return self.speak_online(text) or self.speak_offline(text)
            # Local Piper is immediate and works without internet. In auto mode
            # it is the reliable default; online TTS remains available through
            # LUIS_TTS_MODE=online and falls back to Piper when explicitly used.
            if self.speak_offline(text):
                return True
            return self.speak_online(text)

    def speak_online(self, text):
        if not self.ffplay or not self.tts_python or not self.voice or self.speech_cancel.is_set():
            return False
        output = Path(tempfile.gettempdir()) / f"luis-voz-{os.getpid()}-{int(time.time() * 1000)}.mp3"
        try:
            generated = subprocess.run(
                [
                    self.tts_python,
                    "-m",
                    "edge_tts",
                    "--voice",
                    self.online_voice,
                    "--rate=-10%",
                    "--pitch=+1Hz",
                    "--volume=-1%",
                    "--text",
                    text,
                    "--write-media",
                    str(output),
                ],
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=45,
                check=False,
            )
            if generated.returncode != 0 or not output.exists():
                return False
            if not self.voice or self.speech_cancel.is_set():
                return False
            self.speech_process = subprocess.Popen(
                [self.ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet", str(output)],
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            while self.speech_process.poll() is None:
                if not self.voice or self.speech_cancel.is_set() or self.stop_event.is_set():
                    self.stop_speech()
                    return False
                time.sleep(0.05)
            return self.speech_process.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
        finally:
            self.speech_process = None
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass

    def speak_offline(self, text):
        if self.speak_piper(text):
            return True
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$voices=$s.GetInstalledVoices(); "
            "$v=$voices | Where-Object {$_.VoiceInfo.Name -like ('*' + $env:LUIS_TTS_VOICE + '*')} | Select-Object -First 1; "
            "if(-not $v){$v=$voices | Where-Object {$_.VoiceInfo.Name -match 'Sabina|Helena|Laura|Zira|Hazel|Eva|Samantha|Maria|Female'} | Select-Object -First 1}; "
            "if(-not $v){$v=$voices | Where-Object {$_.VoiceInfo.Gender -eq 'Female'} | Select-Object -First 1}; "
            "if(-not $v){$s.Dispose(); exit 2}; "
            "$s.SelectVoice($v.VoiceInfo.Name); $s.Rate=0; $s.Volume=100; $s.Speak($env:LUIS_SPEECH_TEXT); $s.Dispose()"
        )
        process = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            creationflags=CREATE_NO_WINDOW,
            env={**os.environ, "LUIS_TTS_VOICE": self.voice_name, "LUIS_SPEECH_TEXT": text},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.speech_process = process
        try:
            while process.poll() is None:
                if not self.voice or self.speech_cancel.is_set() or self.stop_event.is_set():
                    self.stop_speech()
                    return False
                time.sleep(0.05)
            return process.returncode == 0
        finally:
            self.speech_process = None

    def speak_piper(self, text):
        if not self.piper_model.exists() or not self.tts_python:
            return False
        output = Path(tempfile.gettempdir()) / f"luis-voz-local-{os.getpid()}-{int(time.time() * 1000)}.wav"
        try:
            generated = subprocess.run(
                [
                    self.tts_python,
                    "-m",
                    "piper",
                    "--model",
                    str(self.piper_model),
                    "--output_file",
                    str(output),
                    "--length_scale",
                    "1.03",
                    "--noise_scale",
                    "0.40",
                    "--noise_w_scale",
                    "0.50",
                    "--sentence_silence",
                    "0.10",
                ],
                input=text,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=45,
                check=False,
            )
            if generated.returncode != 0 or not output.exists():
                return False
            if not self.voice or self.speech_cancel.is_set():
                return False
            player = (
                [self.ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet", str(output)]
                if self.ffplay
                else [
                    self.tts_python,
                    "-c",
                    "import sys, winsound; winsound.PlaySound(sys.argv[1], winsound.SND_FILENAME)",
                    str(output),
                ]
            )
            process = subprocess.Popen(
                player,
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.speech_process = process
            while process.poll() is None:
                if not self.voice or self.speech_cancel.is_set() or self.stop_event.is_set():
                    self.stop_speech()
                    return False
                time.sleep(0.05)
            return process.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
        finally:
            self.speech_process = None
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass

    def speak_from_terminal(self, text):
        if not self.voice:
            return
        self.save_state(status="speaking")
        try:
            if not self.speak(text):
                self.save_state(error="No se pudo reproducir la voz femenina; revisa la conexión o instala una voz femenina de Windows.")
        finally:
            if not self.stop_event.is_set():
                self.save_state(status="idle")

    def commands(self):
        while not self.stop_event.is_set():
            command = claim_json(self.args.command)
            if command:
                action = command.get("action")
                if action == "toggle_voice":
                    self.voice = not self.voice
                    if not self.voice:
                        self.stop_speech()
                    self.save_state(status="idle" if self.voice else "muted")
                elif action == "toggle_listener":
                    if self.listening:
                        self.stop_listener()
                    else:
                        started = self.start_listener()
                        self.listening = bool(started)
                        self.save_state(status="listening" if started else "idle")
                elif action == "vision_on":
                    self.vision_enabled = True
                    self.start_vision()
                    self.save_state(status="idle")
                elif action == "vision_off":
                    self.stop_vision()
                    self.save_state(status="idle")
                elif action == "speak" and command.get("text"):
                    threading.Thread(
                        target=self.speak_from_terminal,
                        args=(str(command["text"]),),
                        daemon=True,
                    ).start()
                elif action in {"submit", "message"} and command.get("text"):
                    self.submit_to_terminal(str(command["text"]), source="panel")
                elif action == "status":
                    self.save_state(status=str(command.get("status") or "idle"))
                elif action == "exit":
                    self.stop_event.set()
                    break
            time.sleep(0.15)

    def run(self):
        self.stop_old_host()
        try:
            self.input_file.unlink(missing_ok=True)
        except OSError:
            pass
        self.save_state(status="idle")
        self.start_vision()
        if not self.start_mascot():
            return
        self.listening = self.start_listener()
        self.save_state()
        self.command_thread = threading.Thread(target=self.commands, daemon=True)
        self.command_thread.start()
        try:
            while not self.stop_event.wait(0.5):
                if self.mascot_process and self.mascot_process.poll() is not None:
                    if self.mascot_process.returncode:
                        self.save_state(
                            status="error",
                            error=f"El cuerpo se cerró con código {self.mascot_process.returncode}",
                        )
                    break
        finally:
            self.vision_enabled = False
            self.stop_listener()
            if self.mascot_process and self.mascot_process.poll() is None:
                subprocess.run(["taskkill", "/PID", str(self.mascot_process.pid), "/T", "/F"], creationflags=CREATE_NO_WINDOW,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            self.save_state(visible=False, status="idle")
            try:
                self.vision_path.unlink(missing_ok=True)
            except OSError:
                pass
            try:
                self.pid_file.unlink(missing_ok=True)
            except OSError:
                pass


def read_line(line):
    try:
        return json.loads(line)
    except (TypeError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--mascot", required=True)
    parser.add_argument("--vrm", required=True)
    parser.add_argument("--listener", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--luis-bin", required=True)
    parser.add_argument("--cwd", default=os.getcwd())
    args = parser.parse_args()
    LuisHost(args).run()


if __name__ == "__main__":
    main()
