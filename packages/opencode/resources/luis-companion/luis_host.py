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
        self.voice = True
        self.listening = False
        self.state = {"visible": True, "voice": True, "listening": False, "status": "idle"}
        self.pid_file = Path(args.state).with_suffix(".pid")
        self.input_file = Path(args.command).with_name("luis-companion-input.json")
        self.voice_name = os.environ.get(
            "LUIS_TTS_VOICE_OFFLINE", os.environ.get("LUIS_TTS_VOICE", "Microsoft Raul")
        )
        self.online_voice = os.environ.get("LUIS_TTS_VOICE_ONLINE", "es-MX-JorgeNeural")
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
        write_json(self.args.state, self.state)

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

    def submit_to_terminal(self, request):
        text = request.strip()
        if not text:
            return
        write_json(self.input_file, {"text": text, "source": "microfono", "created": time.time()})
        self.save_state(status="idle")

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
        if not text:
            return False
        with self.speech_lock:
            if self.speak_online(text):
                return True
            return self.speak_offline(text)

    def speak_online(self, text):
        if not self.ffplay or not self.tts_python:
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
            played = subprocess.run(
                [self.ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet", str(output)],
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=90,
                check=False,
            )
            return played.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
        finally:
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass

    def speak_offline(self, text):
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$v=$s.GetInstalledVoices() | Where-Object {$_.VoiceInfo.Name -eq $env:LUIS_TTS_VOICE} | Select-Object -First 1; "
            "if(-not $v){$v=$s.GetInstalledVoices() | Where-Object {$_.VoiceInfo.Name -eq 'Microsoft Raul'} | Select-Object -First 1}; "
            "if($v){$s.SelectVoice($v.VoiceInfo.Name)}; $s.Rate=1; $s.Volume=100; $s.Speak($env:LUIS_SPEECH_TEXT); $s.Dispose()"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            creationflags=CREATE_NO_WINDOW,
            env={**os.environ, "LUIS_TTS_VOICE": self.voice_name, "LUIS_SPEECH_TEXT": text},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0

    def speak_from_terminal(self, text):
        if not self.voice:
            return
        self.save_state(status="speaking")
        try:
            if not self.speak(text):
                self.save_state(error="No se pudo reproducir la voz; revisa el volumen o instala edge_tts.")
        finally:
            if not self.stop_event.is_set():
                self.save_state(status="idle")

    def commands(self):
        while not self.stop_event.is_set():
            command = read_json(self.args.command)
            if command:
                try:
                    Path(self.args.command).unlink(missing_ok=True)
                except OSError:
                    pass
                action = command.get("action")
                if action == "toggle_voice":
                    self.voice = not self.voice
                    self.save_state(status="idle" if self.voice else "muted")
                elif action == "toggle_listener":
                    if self.listening:
                        self.stop_listener()
                    else:
                        started = self.start_listener()
                        self.listening = bool(started)
                        self.save_state(status="listening" if started else "idle")
                elif action == "speak" and command.get("text"):
                    threading.Thread(
                        target=self.speak_from_terminal,
                        args=(str(command["text"]),),
                        daemon=True,
                    ).start()
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
            self.stop_listener()
            if self.mascot_process and self.mascot_process.poll() is None:
                subprocess.run(["taskkill", "/PID", str(self.mascot_process.pid), "/T", "/F"], creationflags=CREATE_NO_WINDOW,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            self.save_state(visible=False, status="idle")
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
