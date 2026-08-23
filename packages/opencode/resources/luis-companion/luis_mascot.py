import argparse
import base64
import json
import os
import subprocess
import time
from io import BytesIO
from pathlib import Path

import tkinter as tk

try:
    from PIL import Image, ImageTk
    from playwright.sync_api import sync_playwright
except ImportError:
    Image = None
    ImageTk = None
    sync_playwright = None


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TRANSPARENT = "#ff00ff"
WIDTH, HEIGHT = 300, 430
CANVAS_WIDTH, CANVAS_HEIGHT = 280, 340
HTML = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:transparent}
canvas{display:block;width:280px;height:340px;background:transparent}
</style></head><body><canvas id="canvas" width="280" height="340"></canvas>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {VRMLoaderPlugin} from 'https://cdn.jsdelivr.net/npm/@pixiv/three-vrm@3.4.1/lib/three-vrm.module.js';
const canvas=document.getElementById('canvas');canvas.width=280;canvas.height=340;
const scene=new THREE.Scene();
const camera=new THREE.PerspectiveCamera(22,280/340,.01,100);
camera.position.set(0,.88,4.2);
const renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:true,preserveDrawingBuffer:true});
renderer.setClearColor(0,0);renderer.outputColorSpace=THREE.SRGBColorSpace;
scene.add(new THREE.HemisphereLight(0xd9e2ff,0x151827,2.3));
const key=new THREE.DirectionalLight(0xffffff,2.8);key.position.set(1.5,3,4);scene.add(key);
let vrm=null,baseY=0,last=performance.now(),state='idle',leftArm=null,rightArm=null,leftHand=null,rightHand=null,head=null;
function normalize(){
  const box=new THREE.Box3().setFromObject(vrm.scene),size=box.getSize(new THREE.Vector3());
  const scale=1.35/Math.max(size.y,.01);vrm.scene.scale.setScalar(scale);
  const placed=new THREE.Box3().setFromObject(vrm.scene),center=placed.getCenter(new THREE.Vector3());
  vrm.scene.position.set(-center.x,-placed.min.y,-center.z);baseY=vrm.scene.position.y;
  try{
    leftArm=vrm.humanoid?.getNormalizedBoneNode('leftUpperArm');
    rightArm=vrm.humanoid?.getNormalizedBoneNode('rightUpperArm');
    leftHand=vrm.humanoid?.getNormalizedBoneNode('leftHand');
    rightHand=vrm.humanoid?.getNormalizedBoneNode('rightHand');
    head=vrm.humanoid?.getNormalizedBoneNode('head');
    if(leftArm) leftArm.rotation.z=-1.05;
    if(rightArm) rightArm.rotation.z=1.05;
  }catch(_error){}
  camera.lookAt(0,.64,0);
}
const loader=new GLTFLoader();loader.register(parser=>new VRMLoaderPlugin(parser));
loader.load('/luis.vrm',gltf=>{vrm=gltf.userData.vrm;scene.add(vrm.scene);normalize();window.__luisReady=true},undefined,error=>{window.__luisError=String(error)});
window.__luisState=s=>{state=s||'idle'};
function animate(now){
  const delta=Math.min((now-last)/1000,.1);last=now;
  if(vrm){
    vrm.scene.rotation.y=Math.sin(now*.00055)*.035;
    vrm.scene.position.y=baseY+Math.sin(now*.0011)*.012;
    const talking=state==='speaking', wave=talking?Math.sin(now*.006)*.08:Math.sin(now*.0014)*.025;
    if(leftArm) leftArm.rotation.z=-1.05-wave;
    if(rightArm) rightArm.rotation.z=1.05+wave;
    if(leftHand) leftHand.rotation.x=Math.sin(now*.002)*.08;
    if(rightHand) rightHand.rotation.x=Math.cos(now*.0022)*.08;
    if(head){head.rotation.y=Math.sin(now*.0008)*.08;head.rotation.x=Math.sin(now*.0011)*.035}
    if(vrm.expressionManager){
      const mouth=state==='speaking'?(Math.sin(now*.018)*.5+.5):0;
      vrm.expressionManager.setValue('aa',mouth);
    }
    vrm.update(delta)
  }
  renderer.render(scene,camera);requestAnimationFrame(animate)
}
requestAnimationFrame(animate);
</script></body></html>'''


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_json(path, value):
    try:
        temporary = Path(f"{path}.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        pass


def send_command(path, action):
    write_json(path, {"action": action})


class LuisOverlay:
    def __init__(self, args):
        self.args = args
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.configure(bg=TRANSPARENT)
        self.root.wm_attributes("-transparentcolor", TRANSPARENT)
        self.root.wm_attributes("-topmost", True)
        self.root.geometry(self.position())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Button-3>", self.close)
        self.root.bind("<Escape>", self.close)
        self.drag_origin = None
        self.image = None
        self.current_state = {}
        self.browser = None
        self.page = None
        self.playwright = None
        self.image_label = tk.Label(self.root, bg=TRANSPARENT, bd=0, highlightthickness=0)
        self.image_label.place(x=10, y=6, width=CANVAS_WIDTH, height=CANVAS_HEIGHT)
        self.image_label.bind("<ButtonPress-1>", self.drag_start)
        self.image_label.bind("<B1-Motion>", self.drag_move)
        self.image_label.bind("<Button-3>", self.close)
        self.controls_root = tk.Toplevel(self.root)
        self.controls_root.overrideredirect(True)
        self.controls_root.configure(bg=TRANSPARENT)
        self.controls_root.wm_attributes("-transparentcolor", TRANSPARENT)
        self.controls_root.wm_attributes("-topmost", True)
        self.controls_root.geometry(self.controls_position())
        self.controls_root.protocol("WM_DELETE_WINDOW", self.close)
        self.controls_root.bind("<Button-3>", self.close)
        self.controls_drag_origin = None
        self.status = tk.Label(self.controls_root, text="lista", fg="#d8e2ff", bg=TRANSPARENT,
                               font=("Consolas", 10, "bold"))
        self.status.place(x=0, y=0, width=WIDTH, height=24)
        self.controls = tk.Canvas(self.controls_root, width=WIDTH, height=58, bg=TRANSPARENT,
                                  bd=0, highlightthickness=0)
        self.controls.place(x=0, y=24)
        self.draw_controls()
        self.controls.bind("<Button-3>", self.close)
        self.controls.bind("<ButtonPress-1>", self.controls_drag_start)
        self.controls.bind("<B1-Motion>", self.controls_drag_move)

    def position(self):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        return f"{WIDTH}x360+{max(0, screen_width-WIDTH-22)}+{max(24, screen_height-360-106)}"

    def controls_position(self):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        return f"{WIDTH}x82+{max(0, screen_width-WIDTH-22)}+{max(24, screen_height-82-24)}"

    def draw_controls(self):
        self.controls.delete("all")
        voice_on = self.current_state.get("voice", True)
        mic_on = self.current_state.get("listening", False)
        self.controls.create_oval(100, 2, 150, 52, outline="#ef8ddf" if voice_on else "#68728d", width=2, fill="#111a34", tags="voice")
        self.controls.create_line(116, 20, 116, 37, fill="#e4ecff", width=2, tags="voice")
        self.controls.create_line(125, 15 if voice_on else 20, 125, 42 if voice_on else 37, fill="#e4ecff", width=2, tags="voice")
        self.controls.create_line(134, 20, 134, 37, fill="#e4ecff", width=2, tags="voice")
        self.controls.create_oval(170, 2, 220, 52, outline="#70e7bb" if mic_on else "#68728d", width=2, fill="#111a34", tags="mic")
        self.controls.create_oval(187, 14, 203, 33, outline="#e4ecff", width=2, tags="mic")
        self.controls.create_arc(181, 22, 209, 43, start=180, extent=180, outline="#e4ecff", width=2, tags="mic")
        self.controls.create_line(195, 43, 195, 48, fill="#e4ecff", width=2, tags="mic")
        self.controls.create_line(188, 49, 202, 49, fill="#e4ecff", width=2, tags="mic")
        self.controls.tag_bind("voice", "<Button-1>", lambda _e: send_command(self.args.command, "toggle_voice"))
        self.controls.tag_bind("mic", "<Button-1>", lambda _e: send_command(self.args.command, "toggle_listener"))

    def drag_start(self, event):
        self.drag_origin = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())

    def drag_move(self, event):
        if not self.drag_origin:
            return
        start_x, start_y, window_x, window_y = self.drag_origin
        self.root.geometry(f"+{window_x + event.x_root-start_x}+{window_y + event.y_root-start_y}")

    def controls_drag_start(self, event):
        self.controls_drag_origin = (event.x_root, event.y_root, self.controls_root.winfo_x(), self.controls_root.winfo_y())

    def controls_drag_move(self, event):
        if not self.controls_drag_origin:
            return
        start_x, start_y, window_x, window_y = self.controls_drag_origin
        self.controls_root.geometry(f"+{window_x + event.x_root-start_x}+{window_y + event.y_root-start_y}")

    def update_state(self):
        current = read_json(self.args.state)
        if current != self.current_state:
            self.current_state = current
            labels = {"idle": "lista", "listening": "escuchando", "thinking": "pensando",
                      "speaking": "hablando", "working": "trabajando", "acting": "actuando",
                      "reading": "leyendo", "sleeping": "durmiendo", "music": "escuchando música",
                      "muted": "silenciada"}
            self.status.configure(text=labels.get(current.get("status"), current.get("status", "lista")))
            self.draw_controls()
            if self.page:
                self.page.evaluate("status => window.__luisState(status)", current.get("status", "idle"))
        if current.get("visible") is False or current.get("status") == "exit":
            self.close()
            return
        self.root.after(120, self.update_state)

    def update_frame(self):
        if self.page and ImageTk:
            try:
                data_url = self.page.evaluate("document.getElementById('canvas').toDataURL('image/png')")
                raw = base64.b64decode(data_url.split(",", 1)[1])
                frame = Image.open(BytesIO(raw)).convert("RGBA")
                self.image = ImageTk.PhotoImage(frame)
                self.image_label.configure(image=self.image)
            except Exception:
                pass
        if self.root.winfo_exists():
            self.root.after(33, self.update_frame)

    def close(self, _event=None):
        send_command(self.args.command, "exit")
        try:
            self.root.destroy()
            self.controls_root.destroy()
        except tk.TclError:
            pass

    def run(self):
        if not sync_playwright or not ImageTk:
            write_json(self.args.state, {"visible": True, "status": "idle", "error": "Falta Playwright o Pillow para mostrar el cuerpo 3D."})
            return 1
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True, args=["--enable-gpu", "--use-angle=d3d11", "--disable-background-timer-throttling", "--disable-renderer-backgrounding"])
        page = self.browser.new_page(viewport={"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT}, device_scale_factor=1)
        self.page = page
        server = LocalPageServer(self.args.vrm)
        server.start()
        try:
            page.goto(server.url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_function("window.__luisReady === true", timeout=60000)
            write_json(self.args.state, {"visible": True, "status": "idle", "voice": True, "listening": False})
            self.update_state()
            self.update_frame()
            self.root.mainloop()
        except Exception as error:
            write_json(self.args.state, {"visible": True, "status": "idle", "error": str(error)[:220]})
            return 1
        finally:
            server.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            final_state = {"visible": False, "status": "idle", "voice": False, "listening": False}
            error = read_json(self.args.state).get("error")
            if error:
                final_state["error"] = error
            write_json(self.args.state, final_state)
        return 0


class LocalPageServer:
    def __init__(self, vrm_path):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        vrm_file = Path(vrm_path).resolve()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def do_GET(self):
                if self.path == "/luis.vrm":
                    payload = vrm_file.read_bytes()
                    self.send_response(200); self.send_header("Content-Type", "application/octet-stream")
                else:
                    payload = HTML.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        import threading
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.http.server_port}/"

    def start(self):
        return None

    def close(self):
        self.http.shutdown(); self.http.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--vrm", required=True)
    args = parser.parse_args()
    if not Path(args.vrm).exists():
        write_json(args.state, {"visible": True, "status": "idle", "error": f"No encontré el cuerpo: {args.vrm}"})
        return 1
    try:
        return LuisOverlay(args).run()
    except Exception as error:
        write_json(args.state, {"visible": False, "status": "idle", "error": str(error)[:500]})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
