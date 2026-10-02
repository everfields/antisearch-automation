"""Calc pause: a dense programmed motion graphic during the oracle wait.

When ``PUBLISHER_CLIP_PAUSE=calc``, the blinking-caret pause is replaced by a
~2 s black-and-white field of formulas, matrices, numbers and symbols — an
artistic representation of massive computation, not a didactic walkthrough. The
segment is rendered headless with Playwright (canvas), deterministic from the
typed input, then spliced into the existing ffmpeg clip pipeline.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

CALC_PAUSE = "calc"
DEFAULT_PAUSE = "blink"
PAUSE_MODES = (DEFAULT_PAUSE, CALC_PAUSE)

# Monolith palette
BG = "#0A0A0A"
FG = "#E8E4D8"

_FRAGMENTS = (
    "softmax(QKᵀ/√d)V", "∂L/∂θ", "σ²+ε", "θ←θ−η∇L", "L=−∑y log ŷ",
    "tanh(x)", "W·h+b", "∑ᵢαᵢ", "exp(−x²)", "LayerNorm", "GELU", "ReLU",
    "0.734", "−0.291", "∇·F", "×", "Σ", "∏", "∫₀¹", "‖w‖₂", "1/√k",
    "attn", "dropout", "bias", "γ·x+β", "d_model", "h=Wh", "QKᵀ",
    "┌1 −2┐", "│0  3│", "└4  1┘", "[0.12]", "·T", "⊗", "⊙", "∂/∂x",
    "λᵢ", "μ", "φ(x)", "log σ", "argmax", "softmax", "cross-ent",
    "3×3", "128", "512", "0.001", "η=0.03", "epoch", "batch", "token",
    "W₁W₂", "FFN", "MHSA", "residual", "norm", "embed", "vocab",
    "0x7f", "π", "e^z", "1e-5", "∞", "∅", "∈ℝⁿ", "ℝᵈ", "ℤ", "ℕ",
    "f(x)", "g∘f", "J(θ)", "Hess", "grad", "Adam", "SGD", "momentum",
    "0.999", "−1.04", "2.718", "3.141", "0.0", "1.0", "−∞", "+∞",
    "[·|·]", "split", "concat", "mask", "causal", "rope", "pos",
    "d_k", "d_v", "heads", "layers", "blocks", "depth", "width",
    "·", "++", "==", "!=", "≤", "≥", "≈", "≠", "∝", "∴", "∵",
)

_CALC_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
__FONT_FACE__
html,body{margin:0;padding:0;background:__BG__;overflow:hidden}
canvas{display:block}
</style></head><body>
<canvas id="c" width="__W__" height="__H__"></canvas>
<script>
const W=__W__, H=__H__, SEED=__SEED__;
const BG='__BG__', FG='__FG__';
const FRAGMENTS=__FRAGMENTS__;
function mulberry32(a){return function(){let t=a+=0x6D2B79F5;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return((t^t>>>14)>>>0)/4294967296}}
const rng=mulberry32(SEED);
function pick(a){return a[Math.floor(rng()*a.length)]}
function ease(x){x=Math.min(1,Math.max(0,x));return x*x*(3-2*x)}

const particles=[];
const N=140;
for(let i=0;i<N;i++){
  const z=0.3+rng()*2.2;
  particles.push({
    text: pick(FRAGMENTS),
    x:(rng()-0.5)*W*1.4,
    y:(rng()-0.5)*H*1.4,
    z,
    vx:(rng()-0.5)*2.8,
    vy:(rng()-0.5)*2.8,
    rot:(rng()-0.5)*0.8,
    spin:(rng()-0.5)*0.04,
    size:Math.round(28+rng()*52),
    layer:Math.floor(rng()*4),
    phase:rng()*Math.PI*2,
  });
}

const matrices=[];
for(let m=0;m<18;m++){
  const rows=2+Math.floor(rng()*3), cols=2+Math.floor(rng()*3);
  const vals=[];
  for(let r=0;r<rows;r++){
    const row=[];
    for(let c=0;c<cols;c++) row.push((rng()*4-2).toFixed(2));
    vals.push(row);
  }
  matrices.push({
    vals, x:(rng()-0.5)*W, y:(rng()-0.5)*H, z:0.5+rng()*1.5,
    vx:(rng()-0.5)*1.6, vy:(rng()-0.5)*1.6, rot:rng()*0.3, spin:(rng()-0.5)*0.02,
    size:22+Math.floor(rng()*18),
  });
}

const ctx=document.getElementById('c').getContext('2d');
let fontFamily='ui-monospace,monospace';

window.renderFrame=function(t){
  ctx.fillStyle=BG;
  ctx.fillRect(0,0,W,H);
  const collapse=ease(Math.max(0,(t-0.72)/0.28));
  const rush=1+3.5*ease(Math.min(1,t/0.85));
  const swirl=t*Math.PI*2.4;

  const items=[...particles.map(p=>({...p,kind:'t'})),...matrices.map(m=>({...m,kind:'m'}))];
  items.sort((a,b)=>a.z-b.z);

  for(const p of items){
    let x=p.x, y=p.y, z=p.z, rot=p.rot+p.spin*swirl*30;
    const drift=rush*(1+0.3*p.layer);
    x+=p.vx*drift*Math.sin(swirl+p.phase)*12;
    y+=p.vy*drift*Math.cos(swirl*0.7+p.phase)*12;
    if(collapse>0){
      const pull=Math.pow(collapse,1.4+0.2*p.layer);
      x*=1-pull; y*=1-pull;
      z*=1-pull*0.85;
    }
    const scale=1.1/(z+0.15);
    const alpha=Math.min(1,0.12+0.55*scale)*(1-collapse*0.92);
    if(alpha<0.02) continue;
    const cx=W/2+x*scale, cy=H/2+y*scale;
    if(cx<-200||cx>W+200||cy<-200||cy>H+200) continue;
    ctx.save();
    ctx.translate(cx,cy);
    ctx.rotate(rot+swirl*0.08*(p.layer+1));
    ctx.globalAlpha=alpha;
    ctx.fillStyle=FG;
    ctx.font=`${Math.round(p.size*scale)}px ${fontFamily}`;
    ctx.textAlign='center';
    ctx.textBaseline='middle';
    if(p.kind==='m'){
      const lines=p.vals.map(r=>'[ '+r.join('  ')+' ]');
      const lh=p.size*1.15*scale;
      lines.forEach((ln,i)=>ctx.fillText(ln,0,(i-(lines.length-1)/2)*lh));
    } else {
      ctx.fillText(p.text,0,0);
    }
    ctx.restore();
  }

  // dense micro-glyphs — always on, trillions of operations (seeded per frame for determinism)
  ctx.fillStyle=FG;
  const frameSeed=SEED+Math.floor(t*100000);
  for(let i=0;i<900;i++){
    const r2=mulberry32(frameSeed+i*9973);
    const fi=Math.floor(r2()*FRAGMENTS.length);
    let mx=(r2()-0.5)*W*1.3, my=(r2()-0.5)*H*1.3;
    const mz=0.2+r2()*1.8;
    mx+=Math.sin(swirl*2+r2()*6)*rush*18;
    my+=Math.cos(swirl*1.7+r2()*6)*rush*18;
    if(collapse>0){const pull=Math.pow(collapse,1.2);mx*=1-pull;my*=1-pull;}
    const sc=0.35/(mz+0.1);
    const a=0.04+0.18*sc;
    if(a<0.02) continue;
    ctx.globalAlpha=a*(1-collapse*0.9);
    ctx.font=`${Math.round(14*sc)}px ${fontFamily}`;
    ctx.textAlign='center';
    ctx.fillText(FRAGMENTS[fi],W/2+mx*sc,H/2+my*sc);
  }
  ctx.globalAlpha=1;

  if(collapse>0.3){
    const flash=Math.pow(Math.max(0,(collapse-0.3)/0.7),2);
    const r=flash*Math.min(W,H)*0.45;
    const g=ctx.createRadialGradient(W/2,H/2,0,W/2,H/2,r);
    g.addColorStop(0,`rgba(232,228,216,${flash*0.35})`);
    g.addColorStop(1,'rgba(10,10,10,0)');
    ctx.fillStyle=g;
    ctx.fillRect(0,0,W,H);
  }
};

window.setFont=function(fam){fontFamily=fam;}
</script></body></html>"""


def clip_pause(env: Mapping[str, str] | None = None) -> str:
    """``PUBLISHER_CLIP_PAUSE``: ``blink`` (default) or ``calc``. Blank means ``blink``."""
    source = os.environ if env is None else env
    raw = (source.get("PUBLISHER_CLIP_PAUSE") or "").strip().lower()
    if not raw:
        return DEFAULT_PAUSE
    if raw not in PAUSE_MODES:
        raise ValueError(f"PUBLISHER_CLIP_PAUSE={raw!r}; use blink or calc")
    return raw


def calc_seed(category: str) -> int:
    return int.from_bytes(hashlib.sha256(f"calc|{category}".encode()).digest()[:8], "big")


def _calc_html(width: int, height: int, seed: int, font_path: str) -> str:
    font_face = ""
    font_family = "ui-monospace, monospace"
    if font_path:
        uri = Path(font_path).resolve().as_uri()
        font_face = f'@font-face {{ font-family: ClipSans; src: url("{uri}") format("truetype"); }}'
        font_family = "ClipSans, ui-monospace, monospace"
    return (
        _CALC_HTML.replace("__FONT_FACE__", font_face)
        .replace("__W__", str(width))
        .replace("__H__", str(height))
        .replace("__SEED__", str(seed))
        .replace("__BG__", BG)
        .replace("__FG__", FG)
        .replace("__FRAGMENTS__", json.dumps(list(_FRAGMENTS)))
        .replace("ui-monospace,monospace", font_family)
    )


def render_calc_frames(
    category: str,
    out_dir: Path,
    *,
    frame_count: int,
    width: int = 1080,
    height: int = 1920,
    font_path: str = "",
) -> list[Path]:
    """Render ``frame_count`` PNG frames into ``out_dir``. Deterministic from ``category``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    seed = calc_seed(category)
    html = _calc_html(width, height, seed, font_path)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("playwright is required for PUBLISHER_CLIP_PAUSE=calc; pip install playwright") from exc

    paths: list[Path] = []
    html_path = out_dir / "calc.html"
    html_path.write_text(html, encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height, "device_scale_factor": 1})
        page.goto(html_path.resolve().as_uri(), wait_until="load")
        page.wait_for_function("() => typeof window.renderFrame === 'function'")
        for i in range(frame_count):
            t = i / max(1, frame_count - 1)
            page.evaluate("t => window.renderFrame(t)", t)
            path = out_dir / f"frame_{i:04d}.png"
            page.screenshot(path=str(path), type="png", omit_background=False)
            paths.append(path)
        browser.close()
    return paths


def frames_to_video(frames_dir: Path, dest: Path, *, fps: int) -> None:
    """Encode a PNG sequence as a short h264 clip."""
    pattern = str(frames_dir / "frame_%04d.png")
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", str(fps), "-start_number", "0", "-i", pattern,
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", str(fps),
            str(dest),
        ],
        check=True,
        capture_output=True,
    )


def frame_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def formula_fragments() -> tuple[str, ...]:
    """The programmed symbol set (for tests)."""
    return _FRAGMENTS


def playwright_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return False
    if not shutil.which("ffmpeg"):
        return False
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            browser.close()
    except Exception:
        return False
    return True
