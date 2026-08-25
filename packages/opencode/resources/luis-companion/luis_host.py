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


def clean_text(value):
    return re.sub(r"\x1b\[[0-9;]*m", "", str(value or "")).strip()


def clean_speech(value):
    text = re.sub(r"```[\s\S]*?```", " El resultado quedó en pantalla. ", str(value or ""))
    text = re.sub(r"https?://\S+", " enlace ", text)
    text = re.sub(r"[`*_#{}\[\]<>|\\]", " ", text)
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
            "LUIS_TTS_VOICE_OFFLINE", os.environ.get("LUIS_TTS_VOICE", "Microsoft Raul")
        )
        self.online_voice = os.environ.get("LUIS_TTS_VOICE_ONLINE", "es-MX-JorgeNeural")
        self.voice_mode = os.environ.get("LUIS_TTS_MODE", "auto").strip().lower()
        self.ffplay = os.environ.get("LUIS_FFPLAY") or shutil.which("ffplay")
        self.tts_python = self.find_tts_python()
        self.runtime_python = self.tts_python or sys.executable or self.args.python
        if not self.ffplay:
            winget_dir = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
            try:
                self.ffplay = next((str(path) for path in winget_dir.rglob("ffplay.exe")), None)
            except OSError:
                self.ffplay = None

    def find_tts_python(self):
        candidates = [sys.executable, self.args.python, shutil.which(str(self.args.python))]
        for candidate in dict.fromkeys(value for value in candidates if value):
            try:
                result = subprocess.run(
                    [candidate, "-c", "import edge_tts"],
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
        interval = max(0.75, float(os.environ.get("LUIS_VISION_INTERVAL", "1.5")))
        while not self.stop_event.is_set() and self.vision_enabled:
            if self.capture_vision():
                self.save_state(vision_updated=time.time(), vision_error=None)
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
                [self.runtime_python, self.args.listener, "--model", str(model), "--wake", "luis,bro"],
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
                    "Eres Luis, el asistente de escritorio del jefe. Responde en español latinoamericano, sin emojis, "
                    "con personalidad cálida y natural. Sé breve: para una solicitud corta usa una o dos frases. "
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
                return self.speak_online(text)
            if self.speak_online(text):
                return True
            return self.speak_offline(text)

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
                    "--rate=+5%",
                    "--pitch=-3Hz",
                    "--volume=+0%",
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
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$voices=$s.GetInstalledVoices(); "
            "$v=$voices | Where-Object {$_.VoiceInfo.Name -like ('*' + $env:LUIS_TTS_VOICE + '*')} | Select-Object -First 1; "
            "if(-not $v){$v=$voices | Where-Object {$_.VoiceInfo.Name -match 'Raul|Pablo|David|Mark|Jorge|Diego|George|Guy|Ryan'} | Select-Object -First 1}; "
            "if(-not $v){$v=$voices | Where-Object {$_.VoiceInfo.Gender -eq 'Male'} | Select-Object -First 1}; "
            "if(-not $v){$s.Dispose(); exit 2}; "
            "$s.SelectVoice($v.VoiceInfo.Name); $s.Rate=1; $s.Volume=100; $s.Speak($env:LUIS_SPEECH_TEXT); $s.Dispose()"
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

    def speak_from_terminal(self, text):
        if not self.voice:
            return
        self.save_state(status="speaking")
        try:
            if not self.speak(text):
                self.save_state(error="No se pudo reproducir la voz masculina; revisa la conexión o instala una voz masculina de Windows.")
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
            Path(self.args.command).unlink(missing_ok=True)
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
