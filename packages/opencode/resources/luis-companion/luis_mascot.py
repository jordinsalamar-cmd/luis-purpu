import argparse
import base64
import json
import math
import mimetypes
import os
import subprocess
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlsplit

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
# Capturing the WebGL canvas is the most expensive part of the overlay. Keep a
# smooth enough preview while leaving CPU for the model, vision and speech.
# Advanced users can raise the rate with LUIS_MASCOT_FRAME_MS.
FRAME_INTERVAL_MS = max(90, int(os.environ.get("LUIS_MASCOT_FRAME_MS", "120")))
HTML = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:transparent}
canvas{display:block;width:280px;height:340px;background:transparent}
</style></head><body><canvas id="canvas" width="280" height="340"></canvas>
<script type="importmap">{"imports":{"three":"/vendor/three.module.js","three/addons/":"/vendor/three/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {VRMLoaderPlugin} from '/vendor/three-vrm.module.js';
const canvas=document.getElementById('canvas');canvas.width=280;canvas.height=340;
const scene=new THREE.Scene();
const camera=new THREE.PerspectiveCamera(22,280/340,.01,100);
const defaultCameraZ=4.9;
camera.position.set(0,.88,defaultCameraZ);
const renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:true,preserveDrawingBuffer:true});
renderer.setClearColor(0,0);renderer.outputColorSpace=THREE.SRGBColorSpace;
scene.add(new THREE.HemisphereLight(0xd9e2ff,0x151827,2.3));
const key=new THREE.DirectionalLight(0xffffff,2.8);key.position.set(1.5,3,4);scene.add(key);
  let vrm=null,baseY=0,last=performance.now(),state='idle',currentAction='idle',actionStarted=performance.now(),motionBlend=1;
  let leftShoulder=null,rightShoulder=null,leftArm=null,rightArm=null,leftForearm=null,rightForearm=null,leftHand=null,rightHand=null;
  let leftIndex1=null,leftIndex2=null,rightIndex1=null,rightIndex2=null,leftThumb1=null,rightThumb1=null,leftLeg=null,rightLeg=null,leftUpperLeg=null,rightUpperLeg=null,leftFoot=null,rightFoot=null,hips=null,spine=null,chest=null,head=null,neck=null;
const baseRotations=new Map();
const aliases={ready:'idle',looking:'look',greeting:'greet',greet:'greet',saludar:'greet',listening:'listening',speaking:'speaking',talking:'speaking',thinking:'thinking','head-touch':'head-touch',crossed:'crossed',reading:'reading',coding:'coding',typing:'typing',reviewing:'reviewing',searching:'searching',graph:'graph',opening:'acting',acting:'acting',pointing:'pointing',mouse:'mouse',loading:'loading',confirm:'confirm',error:'error',success:'success',sleeping:'sleeping',music:'dancing',dance:'dancing',dancing:'dancing',bailando:'dancing',move:'roaming',moving:'roaming',mover:'roaming',moverse:'roaming',muevete:'roaming','muévete':'roaming',moviéndose:'roaming',bow:'bow',agacharse:'bow',side:'side','turn-side':'side',virarse:'side',nod:'nod',asentir:'nod','shake-head':'shake-head',negar:'shake-head',shy:'shy',timida:'shy',stretch:'stretch',estirarse:'stretch','wave-both':'wave-both',celebrate:'celebrate',celebrar:'celebrate',salute:'salute',clap:'clap',aplaudir:'clap',shrug:'shrug',encogerse:'shrug',sit:'sit',sentarse:'sit',kneel:'kneel',arrodillarse:'kneel',walk:'walk',caminar:'walk',run:'run',correr:'run',spin:'spin',girar:'spin',working:'coding',idle:'idle'};
function actionFor(value){return aliases[String(value||'idle').toLowerCase()]||'idle'}
function rememberBone(name){const bone=vrm.humanoid?.getNormalizedBoneNode(name);if(bone){baseRotations.set(bone,{x:bone.rotation.x,y:bone.rotation.y,z:bone.rotation.z})}return bone}
function pose(bone,x=0,y=0,z=0){if(!bone)return;const base=baseRotations.get(bone)||{x:0,y:0,z:0};bone.rotation.set(base.x+x*motionBlend,base.y+y*motionBlend,base.z+z*motionBlend)}
function resetPose(){for(const [bone,base] of baseRotations)bone.rotation.set(base.x,base.y,base.z)}
function normalize(){
  const box=new THREE.Box3().setFromObject(vrm.scene),size=box.getSize(new THREE.Vector3());
  const scale=1.35/Math.max(size.y,.01);vrm.scene.scale.setScalar(scale);
  const placed=new THREE.Box3().setFromObject(vrm.scene),center=placed.getCenter(new THREE.Vector3());
  vrm.scene.position.set(-center.x,-placed.min.y,-center.z);baseY=vrm.scene.position.y;
  try{
    leftShoulder=rememberBone('leftShoulder');
    rightShoulder=rememberBone('rightShoulder');
    leftArm=rememberBone('leftUpperArm');
    rightArm=rememberBone('rightUpperArm');
    leftForearm=rememberBone('leftLowerArm');
    rightForearm=rememberBone('rightLowerArm');
    leftHand=rememberBone('leftHand');
    rightHand=rememberBone('rightHand');
    leftIndex1=rememberBone('leftIndexProximal');
    leftIndex2=rememberBone('leftIndexDistal');
    rightIndex1=rememberBone('rightIndexProximal');
    rightIndex2=rememberBone('rightIndexDistal');
    leftThumb1=rememberBone('leftThumbMetacarpal');
    rightThumb1=rememberBone('rightThumbMetacarpal');
    leftUpperLeg=rememberBone('leftUpperLeg');
    rightUpperLeg=rememberBone('rightUpperLeg');
    leftLeg=rememberBone('leftLowerLeg');
    rightLeg=rememberBone('rightLowerLeg');
    leftFoot=rememberBone('leftFoot');
    rightFoot=rememberBone('rightFoot');
    hips=rememberBone('hips');
    spine=rememberBone('spine');
    chest=rememberBone('chest')||spine;
    neck=rememberBone('neck');
    head=rememberBone('head');
    // Pose inicial relajada: ambos brazos caen desde los hombros y quedan abiertos.
    if(leftArm) leftArm.rotation.z=-.95;
    if(rightArm) rightArm.rotation.z=.95;
    baseRotations.set(leftArm,{x:leftArm.rotation.x,y:leftArm.rotation.y,z:leftArm.rotation.z});
    baseRotations.set(rightArm,{x:rightArm.rotation.x,y:rightArm.rotation.y,z:rightArm.rotation.z});
  }catch(_error){}
  camera.lookAt(0,.64,0);
}
const loader=new GLTFLoader();loader.register(parser=>new VRMLoaderPlugin(parser));
loader.load('/luis.vrm',gltf=>{vrm=gltf.userData.vrm;scene.add(vrm.scene);normalize();window.__luisReady=true},undefined,error=>{window.__luisError=String(error)});
window.__luisState=s=>{const next=actionFor(s);state=s||'idle';if(next!==currentAction){currentAction=next;actionStarted=performance.now()}};
function applyZoom(scale){
  const value=Math.max(.3,Math.min(4,Number(scale)||1));
  camera.position.z=defaultCameraZ/value;
  // Al acercarse, enfoca gradualmente la cara para que no desaparezca por arriba.
  const focusY=Math.min(1.16,.64+Math.max(0,value-1)*.17);
  camera.lookAt(0,focusY,0);
}
window.__luisZoom=applyZoom;
function animate(now){
  const delta=Math.min((now-last)/1000,.1);last=now;
  if(vrm){
    const t=now*.001, action=currentAction, pulse=Math.sin(t*2.4), slow=Math.sin(t*1.2);
    const transition=Math.min(1,(now-actionStarted)/420);motionBlend=transition*transition*(3-2*transition);
    resetPose();
    const idle=action==='idle', still=idle||action==='greet';
    vrm.scene.rotation.y=still?(idle?Math.sin(t*.35)*.01:0):Math.sin(t*.55)*.035;
    vrm.scene.rotation.z=0;
    vrm.scene.position.y=still?(idle?baseY+Math.sin(t*.8)*.006:baseY):baseY+Math.sin(t*1.1)*.012;
    if(idle||action==='greet'){
      if(chest) pose(chest,Math.sin(t*.8)*.012,Math.sin(t*.8)*.018,0);
      if(hips) pose(hips,0,0,Math.sin(t*.55)*.008);
      if(head) pose(head,Math.sin(t*.45)*.012,Math.sin(t*.6)*.018,Math.sin(t*.38)*.008);
      // La pose base ya deja los brazos abajo y abiertos; solo relajamos las manos.
      pose(leftForearm,0,.06,.06); pose(rightForearm,0,-.06,-.06);
      pose(leftHand,0,.10,.06); pose(rightHand,0,-.10,-.06);
    } else if(!still){
      if(chest) pose(chest,0,slow*.025,0);
      if(hips) pose(hips,0,0,slow*.018);
    }
    switch(action){
      case 'look':
        pose(head,0,Math.sin(t*1.4)*.22,0);
        break;
      case 'greet':
        // Saludo sin cambiar la pose: los dos brazos permanecen abajo.
        break;
      case 'listening':
        pose(head,.05+Math.sin(t*.7)*.02,-.12+Math.sin(t*.5)*.01,.16);
        pose(rightArm,-.75,0,-.25+Math.sin(t*1.8)*.03);
        pose(rightForearm,-.5,0,.2);
        // Movimiento sutil del cuerpo mientras escucha
        if(chest) pose(chest,0,slow*.03,0);
        break;
      case 'speaking':
        pose(leftArm,0,0,-pulse*.16); pose(rightArm,0,0,pulse*.16); pose(leftHand,0,0,pulse*.18); pose(rightHand,0,0,-pulse*.18);
        pose(head,Math.sin(t*2.1)*.035,Math.sin(t*1.7)*.08,0);
        break;
      case 'thinking':
        pose(head,.1+Math.sin(t*.6)*.02,-.1+Math.sin(t*.4)*.01,.08);
        pose(leftArm,-.9,0,.28+Math.sin(t*1.3)*.02);
        pose(leftForearm,-.8,.15,.2);
        pose(leftHand,-.15,Math.sin(t*2)*.03,0);
        // Balanceo sutil mientras piensa
        if(chest) pose(chest,0,slow*.02,0);
        break;
      case 'head-touch':
        pose(head,-.08,0,.12); pose(rightArm,-1.05,0,.08); pose(rightForearm,-.85,0,.2); pose(rightHand,-.25,0,0);
        break;
      case 'crossed':
        pose(leftArm,-.3,0,.52); pose(rightArm,-.3,0,-.52); pose(leftForearm,-.65,.25,.2); pose(rightForearm,-.65,-.25,-.2);
        break;
      case 'reading':
        pose(head,.12,0,0); pose(leftArm,-.55,0,.3); pose(rightArm,-.55,0,-.3); pose(leftForearm,-.35,0,0); pose(rightForearm,-.35,0,0);
        break;
      case 'coding':
        pose(leftArm,-.35,0,.2); pose(rightArm,-.45,0,-.25); pose(leftForearm,-.35,0,0); pose(rightForearm,-.35,0,0); pose(rightHand,Math.sin(t*8)*.12,0,0);
        break;
      case 'typing':
        pose(leftArm,-.48,0,.28); pose(rightArm,-.48,0,-.28); pose(leftForearm,-.45,0,0); pose(rightForearm,-.45,0,0); pose(leftHand,Math.sin(t*9)*.12,0,0); pose(rightHand,Math.cos(t*9)*.12,0,0);
        break;
      case 'reviewing':
        pose(head,.08,-.15,0); pose(rightArm,-.65,0,-.1); pose(rightForearm,-.45,0,0);
        break;
      case 'searching':
        pose(head,0,Math.sin(t*2)*.25,0); pose(chest,0,Math.sin(t*2)*.06,0);
        break;
      case 'graph':
        pose(leftArm,-.55,0,.6); pose(rightArm,-.55,0,-.6); pose(leftHand,0,0,.2); pose(rightHand,0,0,-.2);
        break;
      case 'acting':
      case 'pointing':
        pose(head,.02,.14,0); pose(rightArm,-.45,0,-.62); pose(rightForearm,-.2,0,-.15); pose(rightHand,0,0,-.25);
        break;
      case 'mouse':
        pose(rightArm,-.5,0,-.35); pose(rightForearm,-.55,0,0); pose(rightHand,Math.sin(t*7)*.1,0,0);
        break;
      case 'loading':
        pose(chest,0,slow*.08,0); pose(head,slow*.05,0,0);
        break;
      case 'confirm':
      case 'success':
        pose(leftArm,-1.15,0,.25); pose(rightArm,-1.15,0,-.25); pose(leftHand,0,0,.25); pose(rightHand,0,0,-.25); pose(chest,0,0,slow*.03);
        break;
      case 'error':
        pose(head,0,Math.sin(t*8)*.18,0); pose(leftArm,.1,0,.18); pose(rightArm,.1,0,-.18);
        break;
      case 'sleeping':
        // Incluso durmiendo tiene respiración y micro-movimientos
        pose(head,.35+Math.sin(t*.3)*.01,0,.2);
        pose(leftArm,.12,0,.05+Math.sin(t*.8)*.02);
        pose(rightArm,.12,0,-.05-Math.sin(t*.8)*.02);
        pose(chest,.04+Math.sin(t*.5)*.005,0,0);
        break;
      case 'dancing':
        vrm.scene.rotation.z=Math.sin(t*3.2)*.09; pose(hips,0,0,Math.sin(t*3.2)*.08); pose(chest,0,0,-Math.sin(t*3.2)*.06);
        pose(leftArm,-.35,0,.65+Math.sin(t*5)*.22); pose(rightArm,-.35,0,-.65-Math.sin(t*5)*.22); pose(leftForearm,-.25,0,.2); pose(rightForearm,-.25,0,-.2);
        pose(leftLeg,Math.max(0,Math.sin(t*3.2))*.18,0,0); pose(rightLeg,Math.max(0,-Math.sin(t*3.2))*.18,0,0); pose(head,Math.sin(t*3.2)*.08,0,0);
        break;
      case 'bow':
        pose(chest,.34,0,0); pose(hips,.12,0,0); pose(head,.42,0,0); pose(leftArm,-.18,0,.16); pose(rightArm,-.18,0,-.16);
        break;
      case 'side':
        vrm.scene.rotation.y=.42; pose(head,0,-.18,0); pose(chest,0,-.08,0); pose(leftArm,0,0,-.08); pose(rightArm,0,0,.08);
        break;
      case 'nod':
        pose(head,.16+Math.sin(t*3.8)*.15,0,0); pose(chest,Math.sin(t*3.8)*.025,0,0);
        break;
      case 'shake-head':
        pose(head,0,Math.sin(t*3.2)*.25,0); pose(chest,0,-Math.sin(t*3.2)*.025,0);
        break;
      case 'shy':
        pose(head,.08,.16,.08); pose(leftArm,-.52,0,.42); pose(rightArm,-.52,0,-.42); pose(leftForearm,-.62,.2,.18); pose(rightForearm,-.62,-.2,-.18);
        break;
      case 'stretch':
        pose(leftArm,-1.18,0,.12+Math.sin(t*1.8)*.04); pose(rightArm,-1.18,0,-.12-Math.sin(t*1.8)*.04); pose(leftForearm,-.2,0,.08); pose(rightForearm,-.2,0,-.08);
        pose(head,-.06,0,0);
        break;
      case 'wave-both':
        pose(leftArm,-.78,0,.25); pose(rightArm,-.78,0,-.25); pose(leftForearm,-.45,0,.62+Math.sin(t*5.6)*.28); pose(rightForearm,-.45,0,-.62-Math.sin(t*5.6)*.28);
        pose(leftHand,0,0,Math.sin(t*5.6)*.18); pose(rightHand,0,0,-Math.sin(t*5.6)*.18);
        break;
      case 'celebrate':
        pose(leftArm,-1.02,0,.46); pose(rightArm,-1.02,0,-.46); pose(leftForearm,-.28,0,.28); pose(rightForearm,-.28,0,-.28); pose(chest,0,0,Math.sin(t*3)*.05);
        break;
      case 'salute':
        pose(rightArm,-.92,0,-.32); pose(rightForearm,-.88,0,-.28); pose(rightHand,-.18,0,.18); pose(head,.04,.12,0);
        break;
      case 'clap':
        pose(leftArm,-.46,0,.36); pose(rightArm,-.46,0,-.36); pose(leftForearm,-.58,.30,.12); pose(rightForearm,-.58,-.30,-.12);
        pose(leftHand,0,Math.sin(t*5)*.08,.18); pose(rightHand,0,-Math.sin(t*5)*.08,-.18);
        break;
      case 'shrug':
        pose(leftShoulder,0,0,.18); pose(rightShoulder,0,0,-.18); pose(leftArm,-.22,0,.48); pose(rightArm,-.22,0,-.48); pose(head,.04,0,0);
        break;
      case 'sit':
        pose(hips,-.18,0,0); pose(chest,.08,0,0); pose(leftUpperLeg,-.82,0,0); pose(rightUpperLeg,-.82,0,0); pose(leftLeg,1.12,0,0); pose(rightLeg,1.12,0,0);
        pose(leftFoot,-.28,0,0); pose(rightFoot,-.28,0,0); pose(leftArm,-.18,0,.18); pose(rightArm,-.18,0,-.18);
        break;
      case 'kneel':
        pose(hips,-.12,0,0); pose(chest,.18,0,0); pose(leftUpperLeg,-.55,0,0); pose(rightUpperLeg,-.55,0,0); pose(leftLeg,1.42,0,0); pose(rightLeg,1.42,0,0);
        pose(leftFoot,-.72,0,0); pose(rightFoot,-.72,0,0); pose(head,.12,0,0);
        break;
      case 'walk':
        pose(hips,0,0,Math.sin(t*3.4)*.06); pose(chest,0,0,-Math.sin(t*3.4)*.04); pose(leftUpperLeg,Math.sin(t*3.4)*.28,0,0); pose(rightUpperLeg,-Math.sin(t*3.4)*.28,0,0);
        pose(leftLeg,Math.max(0,-Math.sin(t*3.4))*.22,0,0); pose(rightLeg,Math.max(0,Math.sin(t*3.4))*.22,0,0); pose(leftArm,Math.sin(t*3.4)*.18,0,0); pose(rightArm,-Math.sin(t*3.4)*.18,0,0);
        break;
      case 'run':
        pose(hips,0,0,Math.sin(t*6)*.1); pose(chest,.04,0,-Math.sin(t*6)*.06); pose(leftUpperLeg,Math.sin(t*6)*.62,0,0); pose(rightUpperLeg,-Math.sin(t*6)*.62,0,0);
        pose(leftLeg,Math.max(0,-Math.sin(t*6))*.5,0,0); pose(rightLeg,Math.max(0,Math.sin(t*6))*.5,0,0); pose(leftArm,-Math.sin(t*6)*.42,0,0); pose(rightArm,Math.sin(t*6)*.42,0,0);
        break;
      case 'spin':
        vrm.scene.rotation.y=Math.sin(t*.8)*1.15; pose(chest,0,0,Math.sin(t*1.6)*.08); pose(leftArm,-.35,0,.3); pose(rightArm,-.35,0,-.3); pose(head,0,-Math.sin(t*.8)*.15,0);
        break;
      default:
        break;
    }
    if(vrm.expressionManager){
      const mouth=action==='speaking'?(Math.sin(now*.018)*.5+.5):Math.sin(now*.003)*.1;
      vrm.expressionManager.setValue('aa',mouth);
      // Micro-expresiones constantes para dar vida
      // Parpadeo corto y natural durante el reposo, aproximadamente cada 5 segundos.
      const blinkPhase=(now/1000)%5.2;
      const blink=blinkPhase>4.95?Math.sin(Math.min(1,(blinkPhase-4.95)/.25)*Math.PI):0;
      vrm.expressionManager.setValue('blink',blink);
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


def send_command(path, action, **payload):
    write_json(path, {"action": action, **payload})


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
        self.root.bind("<Escape>", self.close)
        self.drag_origin = None
        self.image = None
        self.current_state = {}
        self.zoom = 1.0
        self.browser = None
        self.page = None
        self.playwright = None
        self.image_label = tk.Label(self.root, bg=TRANSPARENT, bd=0, highlightthickness=0)
        self.image_label.place(x=10, y=6, width=CANVAS_WIDTH, height=CANVAS_HEIGHT)
        self.image_label.bind("<ButtonPress-1>", self.drag_start)
        self.image_label.bind("<B1-Motion>", self.drag_move)
        self.image_label.bind("<MouseWheel>", self.change_zoom)
        self.controls_root = tk.Toplevel(self.root)
        self.controls_root.overrideredirect(True)
        self.controls_root.configure(bg=TRANSPARENT)
        self.controls_root.wm_attributes("-transparentcolor", TRANSPARENT)
        self.controls_root.wm_attributes("-topmost", True)
        self.controls_root.geometry(self.controls_position())
        self.controls_root.protocol("WM_DELETE_WINDOW", self.close)
        self.controls_drag_origin = None
        self.message_window = None
        self.roaming = False
        self.roam_started = 0.0
        self.status = tk.Label(self.controls_root, text="lista", fg="#d8e2ff", bg=TRANSPARENT,
                               font=("Consolas", 10, "bold"))
        self.status.place(x=0, y=0, width=WIDTH, height=24)
        self.controls = tk.Canvas(self.controls_root, width=WIDTH, height=58, bg=TRANSPARENT,
                                  bd=0, highlightthickness=0)
        self.controls.place(x=0, y=24)
        self.draw_controls()
        self.controls.bind("<ButtonPress-1>", self.controls_drag_start)
        self.controls.bind("<B1-Motion>", self.controls_drag_move)

    def position(self):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        # Deja un espacio visible entre Rem y los controles independientes.
        return f"{WIDTH}x360+{max(0, screen_width-WIDTH-22)}+{max(24, screen_height-360-150)}"

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
        self.controls.create_oval(240, 2, 290, 52, outline="#86b7ff", width=2, fill="#111a34", tags="message")
        self.controls.create_rectangle(252, 16, 278, 35, outline="#e4ecff", width=2, tags="message")
        self.controls.create_polygon(257, 35, 262, 35, 257, 41, fill="#e4ecff", outline="#e4ecff", tags="message")
        self.controls.create_line(257, 21, 273, 21, fill="#e4ecff", width=2, tags="message")
        self.controls.create_line(257, 26, 270, 26, fill="#e4ecff", width=2, tags="message")
        self.controls.tag_bind("voice", "<Button-1>", lambda _e: send_command(self.args.command, "toggle_voice"))
        self.controls.tag_bind("mic", "<Button-1>", lambda _e: send_command(self.args.command, "toggle_listener"))
        self.controls.tag_bind("message", "<Button-1>", lambda _e: self.open_message_box())

    def open_message_box(self):
        if self.message_window and self.message_window.winfo_exists():
            self.message_window.deiconify()
            self.message_window.lift()
            self.message_entry.focus_set()
            return

        window = tk.Toplevel(self.controls_root)
        self.message_window = window
        window.title("Escribir a Rem")
        window.configure(bg="#111827")
        window.resizable(False, False)
        window.attributes("-topmost", True)
        x = max(0, self.controls_root.winfo_x() - 55)
        y = max(24, self.controls_root.winfo_y() - 105)
        window.geometry(f"360x100+{x}+{y}")
        window.protocol("WM_DELETE_WINDOW", window.destroy)

        self.message_entry = tk.Entry(window, bg="#20283d", fg="#f3f6ff", insertbackground="#ffffff",
                                      relief="flat", font=("Segoe UI", 11))
        self.message_entry.pack(fill="x", padx=12, pady=(12, 8), ipady=7)

        def submit(_event=None):
            text = self.message_entry.get().strip()
            if not text:
                return "break"
            send_command(self.args.command, "submit", text=text)
            window.destroy()
            self.message_window = None
            return "break"

        self.message_entry.bind("<Return>", submit)
        self.message_entry.focus_set()
        tk.Button(window, text="Enviar", command=submit, bg="#536dfe", fg="white",
                  activebackground="#7184ff", activeforeground="white", relief="flat",
                  font=("Segoe UI", 9, "bold")).pack(pady=(0, 10))

    def change_zoom(self, event):
        if not self.page:
            return "break"
        self.zoom = max(0.3, min(4.0, self.zoom * (1.12 if event.delta > 0 else 0.89)))
        try:
            self.page.evaluate("scale => window.__luisZoom(scale)", self.zoom)
        except Exception:
            pass
        return "break"

    def drag_start(self, event):
        self.drag_origin = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())

    def drag_move(self, event):
        if not self.drag_origin:
            return
        start_x, start_y, window_x, window_y = self.drag_origin
        delta_x = event.x_root - start_x
        delta_y = event.y_root - start_y
        self.root.geometry(f"+{window_x + delta_x}+{window_y + delta_y}")

    def controls_drag_start(self, event):
        self.controls_drag_origin = (event.x_root, event.y_root, self.controls_root.winfo_x(), self.controls_root.winfo_y())

    def controls_drag_move(self, event):
        if not self.controls_drag_origin:
            return
        start_x, start_y, window_x, window_y = self.controls_drag_origin
        delta_x = event.x_root - start_x
        delta_y = event.y_root - start_y
        self.controls_root.geometry(f"+{window_x + delta_x}+{window_y + delta_y}")

    def update_roaming(self, active):
        if not active:
            self.roaming = False
            return
        if not self.roaming:
            self.roaming = True
            self.roam_started = time.monotonic()
        elapsed = time.monotonic() - self.roam_started
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        max_x = max(0, screen_width - WIDTH - 18)
        max_y = max(24, screen_height - 360 - 82 - 18)
        x = int(max_x * (0.5 + 0.43 * math.sin(elapsed * 0.42)))
        y = int(24 + max(0, max_y - 24) * (0.5 + 0.40 * math.cos(elapsed * 0.57)))
        self.root.geometry(f"{WIDTH}x360+{x}+{y}")
        # El personaje puede moverse sin arrastrar los controles con él.

    def update_state(self):
        current = read_json(self.args.state)
        if current != self.current_state:
            self.current_state = current
            labels = {"idle": "lista", "listening": "escuchando", "thinking": "pensando",
                      "speaking": "hablando", "working": "trabajando", "coding": "escribiendo código",
                      "typing": "tecleando", "acting": "actuando", "pointing": "señalando",
                      "reading": "leyendo", "reviewing": "revisando", "searching": "buscando",
                      "graph": "analizando el grafo", "head-touch": "analizando",
                      "crossed": "esperando", "loading": "cargando", "confirm": "confirmando",
                      "success": "terminado", "error": "hubo un error", "sleeping": "durmiendo",
                      "music": "escuchando música", "dance": "bailando", "dancing": "bailando",
                       "greet": "saludando", "bow": "saludando con una reverencia", "side": "de perfil", "nod": "asintiendo",
                      "shake-head": "negando", "shy": "tímida", "stretch": "estirándose",
                      "wave-both": "saludando con las dos manos", "celebrate": "celebrando",
                      "look": "mirando", "roaming": "moviéndose", "move": "moviéndose", "moving": "moviéndose",
                      "muted": "silenciada"}
            self.status.configure(text=labels.get(current.get("status"), current.get("status", "lista")))
            self.draw_controls()
            if self.page:
                self.page.evaluate("status => window.__luisState(status)", current.get("status", "idle"))
        self.update_roaming(current.get("status") in {"dancing", "dance", "music", "roaming", "move", "moving", "mover", "moverse", "muevete", "muévete", "moviéndose"})
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
            self.root.after(FRAME_INTERVAL_MS, self.update_frame)

    def close(self, _event=None):
        send_command(self.args.command, "exit")
        try:
            if self.message_window and self.message_window.winfo_exists():
                self.message_window.destroy()
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
        vendor_root = (Path(__file__).resolve().parent / "assets" / "vendor").resolve()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def do_GET(self):
                request_path = urlsplit(self.path).path
                if request_path == "/luis.vrm":
                    payload = vrm_file.read_bytes()
                    content_type = "application/octet-stream"
                elif request_path.startswith("/vendor/"):
                    relative = Path(unquote(request_path.removeprefix("/vendor/")))
                    candidate = (vendor_root / relative).resolve()
                    if not candidate.is_file() or not candidate.is_relative_to(vendor_root):
                        self.send_error(404)
                        return
                    payload = candidate.read_bytes()
                    content_type = "text/javascript" if candidate.suffix == ".js" else (mimetypes.guess_type(candidate.name)[0] or "application/octet-stream")
                else:
                    payload = HTML.encode()
                    content_type = "text/html; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
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
