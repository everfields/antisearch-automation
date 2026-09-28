"""Creative 2, "the monolith" (docs/IG_ROTATION.md), and the motion under creative 3.

An 8.5 s cinematic piece around the same typing-to-verdict moment:
1. Frame 0 is dark, so the loop joins.
2. The monolith appears, its rim traced in light, and the camera dives onto the input line.
3. The typed words sit in a sharp close-up, drawn from a 2x render of the app screen.
4. After Enter the camera re-frames onto the verdict line and pushes in while the room darkens.
5. The verdict lands centred; the camera releases to reveal the monolith, with one light sweep.
6. The verdict stands alone in large lowercase type, then everything sinks back to dark.
Scored by `score.template_score`. No chat, one verdict, no share card.
"""

from __future__ import annotations

import math
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from ..render import Layout, RenderError, probe
from ..timeline import Timeline
from .score import _rng, template_score

INK = (232, 229, 224)
STONE = (122, 118, 112)
INTRO_S = 0.4  # motion from frame 0: the typing starts almost at once
OUTRO_CROSS_S = 0.5
OUTRO_HOLD_S = 1.9  # includes the sink back to frame 0
FADE_S = 0.6
INPUT_LINE = 0.29  # the typed line, as a fraction of the screen height (measured)
VERDICT_LINE = 0.38  # where the caret waits and the verdict appears (measured)
REFRAME_S = 0.35  # after Enter the camera re-frames from the input line to the verdict line
DIVE_S = 0.9  # frame 0 shows the whole monolith; the camera dives onto the input line by then
CAMERA_WIDE = 1.1
CAMERA_CLOSE, CAMERA_PEAK = 1.9, 2.05  # close enough that the typed words read in a muted feed


def _run(cmd: list[str], stdin=None) -> None:
    proc = subprocess.run(cmd, capture_output=True, input=stdin)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.decode(errors="replace").strip().splitlines()[-12:])
        raise RenderError(f"ffmpeg failed ({proc.returncode}):\n{tail}")


def _encode_tail(out: Path) -> list[str]:
    return ["-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", "-map_metadata", "-1",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
            "-movflags", "+faststart", str(out)]


def _ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def _ease_out_expo(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)


@dataclass(frozen=True)
class MotionPlan:
    fps: int
    intro: int  # frames before the app screen starts
    classic: int  # frames of the classic clip
    cross: int  # monolith recedes, verdict rises
    hold: int
    fade: int

    @property
    def total(self) -> int:
        return self.intro + self.classic + self.cross + self.hold

    @property
    def outro_start(self) -> int:
        return self.intro + self.classic

    def verdict_at(self, timeline: Timeline) -> int:
        return self.intro + timeline.verdict_frame


def motion_plan(timeline: Timeline) -> MotionPlan:
    f = timeline.fps
    return MotionPlan(f, round(INTRO_S * f), timeline.total_frames, round(OUTRO_CROSS_S * f), round(OUTRO_HOLD_S * f),
                      round(FADE_S * f))


def _font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    light = Path(font_path).with_name(Path(font_path).name.replace("Regular", "Light"))
    return ImageFont.truetype(str(light if light.is_file() else font_path), size)


VERDICT_TRACKING = 5


def verdict_font(font_path: str, verdict: str, width: int) -> ImageFont.FreeTypeFont:
    """The large verdict of the outro: 150 px at 1080 wide, smaller until it fits 82% of the width."""
    size, probe_draw = 150, ImageDraw.Draw(Image.new("RGB", (8, 8)))
    while size > 60 and probe_draw.textlength(verdict, font=_font(font_path, size)) + 5 * len(verdict) > width * 0.82:
        size -= 6
    return _font(font_path, size)


def verdict_y(height: int) -> float:
    """The top of the outro's verdict line, once it has risen into place."""
    return height * 0.44 - 40


def _tracked(draw: ImageDraw.ImageDraw, center_x: float, y: float, text: str, font, fill, tracking: float) -> None:
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * max(0, len(text) - 1)
    x = center_x - total / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + tracking


def _background(w: int, h: int) -> Image.Image:
    top, bottom = (9, 10, 12), (20, 21, 24)
    grad = Image.new("RGB", (1, h))
    for y in range(h):
        p = y / (h - 1)
        grad.putpixel((0, y), tuple(round(a + (b - a) * p) for a, b in zip(top, bottom)))
    return grad.resize((w, h))


def _vignette(w: int, h: int) -> Image.Image:
    small = Image.new("L", (w // 8, h // 8))
    cx, cy = small.width / 2, small.height * 0.46
    for y in range(small.height):
        for x in range(small.width):
            d = math.hypot((x - cx) / (small.width * 0.62), (y - cy) / (small.height * 0.62))
            small.putpixel((x, y), round(255 * (1 - 0.55 * min(1.0, d) ** 2.2)))
    return small.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(6)).convert("RGB")


def _sweep_band(w: int, h: int, angle: float = -24.0) -> Image.Image:
    """A soft diagonal band of light, long enough that its ends never cross the slab."""
    length = int(math.hypot(w, h) * 2.2)
    band = Image.new("L", (length, 320), 0)
    d = ImageDraw.Draw(band)
    for y in range(320):
        a = math.exp(-((y - 160) / 62) ** 2) * 30
        d.line([(0, y), (length, y)], fill=round(a))
    band = band.rotate(angle, expand=True, resample=Image.BICUBIC)
    white = Image.new("RGBA", band.size, (235, 240, 248, 0))
    white.putalpha(band)
    return white


def _slab_mask(w: int, h: int, radius: int) -> Image.Image:
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    return m


class _Monolith:
    """Precomputed layers for the motion piece, and the frame at index i.

    The camera works in scene space: the slab is drawn at the camera's zoom straight from the
    (sharper) source, so a close-up never upscales text; the background stays put (depth).
    """

    def __init__(self, plan: MotionPlan, timeline: Timeline, *, category: str, verdict: str, font_path: str,
                 layout: Layout, screen: tuple[int, int, int, int], source_size: tuple[int, int]):
        self.plan, self.fps = plan, timeline.fps
        self.W, self.H = layout.width, layout.height
        self.screen, self.source_size = screen, source_size
        sx, sy, sw, sh = screen
        self.base_h = round(self.H * 0.72)
        self.base_w = round(self.base_h * sw / sh)
        rng = _rng(f"camera|{category}|{verdict}")  # per-input variation, one system
        self.drift = 18 * (1 if rng.random() < 0.5 else -1)
        self.bg = _background(self.W, self.H)
        self.vig = _vignette(self.W, self.H)
        self.band = _sweep_band(self.base_w * 2, self.base_h * 2, -18 - 12 * rng.random())
        self.grains = [Image.merge("RGB", [Image.effect_noise((self.W // 2, self.H // 2), 2.6)] * 3)
                       .resize((self.W, self.H), Image.BICUBIC) for _ in range(4)]  # dither, not a 100 MB clip
        sh_w, sh_h = round(self.base_w * 1.4), 140
        shadow = Image.new("L", (sh_w, sh_h), 0)
        ImageDraw.Draw(shadow).ellipse([sh_w * 0.07, 40, sh_w * 0.93, 100], fill=150)
        self.shadow = shadow.filter(ImageFilter.GaussianBlur(24))
        fade = Image.new("L", (1, 256))
        for y in range(256):
            fade.putpixel((0, y), round(30 * (1 - y / 255) ** 2))
        self.reflect_fade = fade
        self.category, self.verdict = category, verdict
        self.small = _font(font_path, 44)
        self.big = verdict_font(font_path, verdict, self.W)
        self.submit_i = plan.intro + timeline.submit_frame
        self.verdict_i = plan.verdict_at(timeline)
        self.black = Image.new("RGB", (self.W, self.H))
        self.overlay = None
        self.lift = Image.new("RGB", (self.W, self.H), (26, 28, 32))

    def camera(self, i: int) -> tuple[float, float]:
        """(zoom, focus): the zoom, and which fraction of the slab's height sits at the frame's centre.

        Wide on the monolith at frame 0, diving onto the input line; after Enter re-framing onto
        the verdict line and pushing in faster (held breath); on the verdict released to the
        whole slab."""
        plan = self.plan
        dive_end = round(DIVE_S * self.fps)
        if i < min(dive_end, self.submit_i):  # the hook
            p = _ease(i / dive_end)
            return CAMERA_WIDE + (CAMERA_CLOSE - CAMERA_WIDE) * p, 0.5 + (INPUT_LINE - 0.5) * p
        if i < self.submit_i:
            return CAMERA_CLOSE + 0.04 * _ease((i - dive_end) / max(1, self.submit_i - dive_end)), INPUT_LINE
        if i < self.verdict_i:
            p = (i - self.submit_i) / max(1, self.verdict_i - self.submit_i)
            focus = INPUT_LINE + (VERDICT_LINE - INPUT_LINE) * _ease((i - self.submit_i) / (REFRAME_S * self.fps))
            return CAMERA_CLOSE + 0.04 + (CAMERA_PEAK - CAMERA_CLOSE - 0.04) * p * p, focus
        release = _ease_out_expo((i - self.verdict_i) / (0.9 * self.fps))
        zoom = CAMERA_PEAK + (1.0 - CAMERA_PEAK) * release
        if i >= plan.outro_start:
            zoom = 1.0 + 0.025 * _ease((i - plan.outro_start) / max(1, plan.total - plan.outro_start))
        return zoom, VERDICT_LINE + (0.5 - VERDICT_LINE) * release

    def frame(self, i: int, source: Image.Image) -> Image.Image:
        W, H, plan = self.W, self.H, self.plan
        sx, sy, sw, sh = self.screen
        face = source.crop((sx, sy, sx + sw, sy + sh))
        black = face.getpixel((round(sw * 0.1), round(sh * 0.15)))  # the app's own black
        fd, edge = ImageDraw.Draw(face), round(sw * 0.07)
        fd.rectangle([0, 0, sw, sh * 0.06], fill=black)  # no camera dot, no top edge: a clean zoom
        for cx0, cy0 in ((0, 0), (sw - edge, 0), (0, sh - edge), (sw - edge, sh - edge)):
            fd.rectangle([cx0, cy0, cx0 + edge, cy0 + edge], fill=black)  # no phone corners either
        t = i / self.fps
        dv = (i - self.verdict_i) / self.fps
        zoom, focus = self.camera(i)
        if dv >= 0:
            zoom *= 1.0 + 0.012 * math.exp(-dv / 0.6) * math.sin(min(math.pi, dv * math.pi / 0.9))  # a breath
        w, h = round(self.base_w * zoom), round(self.base_h * zoom)
        radius = round(10 * zoom)
        drift = self.drift * math.sin(math.pi * i / plan.total)
        x0 = round(W / 2 - w / 2 + drift)
        y0 = round(H / 2 - focus * h)
        out_i = i - plan.outro_start
        recede = _ease(out_i / plan.cross) if out_i >= 0 else 0.0
        slab_left = (1 - _ease(min(1.0, recede * 2))) * _ease(t / 0.15)  # dark frame 0 (the loop), then present
        # Until the verdict releases the camera there is only the app's own black: no rim, no room,
        # no reflection, no grain, so the zoom onto the input is clean. The monolith comes with the release.
        reveal = _ease_out_expo(dv / 0.9) if dv >= 0 else 0.0
        screen_black = Image.new("RGB", (W, H), black)
        frame = self.bg.copy() if reveal >= 1 else Image.blend(screen_black, self.bg, reveal)
        if slab_left > 0 and reveal > 0:
            shw, shh = round(self.shadow.width * zoom), round(self.shadow.height * zoom)
            shadow = self.shadow.resize((shw, shh)).point(lambda v: round(v * slab_left * reveal))
            frame.paste((0, 0, 0), (round(W / 2 - shw / 2 + drift), y0 + h - round(40 * zoom)), shadow)
        slab = face.resize((w, h), Image.BICUBIC).convert("RGBA")
        if 0 <= dv < 1.1:  # one soft light sweep over the verdict
            p = _ease(dv / 1.1)
            bw, bh = self.band.size
            ox, oy = round(w / 2 - bw / 2), round(-bh / 2 - h * 0.1 + p * (h * 1.2))
            layer = Image.new("RGBA", slab.size, (0, 0, 0, 0))
            layer.alpha_composite(self.band, (max(0, ox), max(0, oy)), (max(0, -ox), max(0, -oy), bw, bh))
            slab.alpha_composite(layer)
        if reveal > 0:  # the rim blooms with the release
            glow = (44 + round(40 * math.exp(-dv / 0.7))) * reveal
            rim = tuple(round(b + (g - b) * reveal) for b, g in zip(black, (glow, glow, glow + 6)))
            ImageDraw.Draw(slab).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, outline=rim,
                                                   width=max(2, round(2 * zoom)))
        mask = _slab_mask(w, h, radius)
        if slab_left < 1:
            mask = mask.point(lambda v: round(v * slab_left))
        if slab_left > 0 and reveal > 0 and y0 + h < H:  # a faint reflection on the stone floor
            depth = min(round(h * 0.22), H - (y0 + h))
            if depth > 4:
                refl = slab.crop((0, h - depth, w, h)).transpose(Image.FLIP_TOP_BOTTOM).convert("RGB")
                ra = self.reflect_fade.resize((w, depth)).point(lambda v: round(v * slab_left * reveal))
                frame.paste(refl, (x0, y0 + h + 4), ra)
        frame.paste(slab.convert("RGB"), (x0, y0), mask)
        if dv >= 0:  # the room lifts a little when the verdict lands
            frame = Image.blend(frame, ImageChops.screen(frame, self.lift), 0.06 * math.exp(-dv / 1.2) * slab_left)
        left = plan.total - i
        sink = _ease((left - 1) / plan.fade) if left <= plan.fade else 1.0  # back to frame 0's darkness
        type_in = _ease((recede - 0.4) / 0.6) * sink
        if type_in > 0:
            txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(txt)
            rise = round(30 * (1 - _ease((recede - 0.4) / 0.6)))
            alpha = round(255 * type_in)
            _tracked(d, W / 2, H * 0.44 - 150 + rise, self.category, self.small, (*STONE, alpha), 6)
            _tracked(d, W / 2, verdict_y(H) + rise, self.verdict, self.big, (*INK, alpha), VERDICT_TRACKING)
            frame = Image.alpha_composite(frame.convert("RGBA"), txt).convert("RGB")
        if self.submit_i <= i < self.verdict_i + 0.35 * self.fps:  # the room darkens through the wait
            p = min(1.0, (i - self.submit_i) / max(1, self.verdict_i - self.submit_i))
            dark = 0.14 * _ease(p) if i < self.verdict_i else 0.14 * (1 - (i - self.verdict_i) / (0.35 * self.fps))
            frame = Image.blend(frame, self.black, dark)
        if self.overlay is not None:  # e.g. the computation, drawn in screen space over the wait
            layer = self.overlay(i)
            if layer is not None:
                frame = ImageChops.add(frame, layer)
        if reveal <= 0:  # before the release: the app's black only, no vignette, no grain
            return frame
        vignetted = ImageChops.multiply(frame, self.vig)
        frame = vignetted if reveal >= 1 else Image.blend(frame, vignetted, reveal)
        grained = ImageChops.add(frame, self.grains[(i // 2) % len(self.grains)], 1.0, -128)
        return grained if reveal >= 1 else Image.blend(frame, grained, reveal)


def _motion(clip: Path, timeline: Timeline, out: Path, work: Path, *, category: str, verdict: str, font_path: str,
            layout: Layout, screen: tuple[int, int, int, int] | None, audio: bool, meta: list[str],
            source: Path | None = None, overlay=None, ticks: bool = False) -> None:
    W, H, fps = layout.width, layout.height, timeline.fps
    plan = motion_plan(timeline)
    src = source or clip
    src_info = probe(src)
    SW, SH = src_info.width, src_info.height
    mono = _Monolith(plan, timeline, category=category, verdict=verdict, font_path=font_path, layout=layout,
                     screen=screen or (0, 0, SW, SH), source_size=(SW, SH))
    if overlay is not None:
        mono.overlay = overlay(mono)
    total_s = plan.total / fps
    inputs = ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-"]
    if audio:
        wav = work / "motion.wav"
        template_score(f"{category}|{verdict}", total_s, INTRO_S, mono.submit_i / fps, mono.verdict_i / fps,
                       ticks=ticks).write(wav)
        delay = round(INTRO_S * 1000)
        inputs += ["-i", str(clip), "-i", str(wav)]
        amap = ["-filter_complex", f"[1:a]adelay={delay}|{delay},apad[k];[k][2:a]amix=inputs=2:normalize=0:"
                                   f"weights='0.8 1':duration=shortest,atrim=0:{total_s:.3f},"
                                   "loudnorm=I=-17:TP=-1.5:LRA=11,aresample=44100[a]", "-map", "0:v", "-map", "[a]"]
    else:
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        amap = ["-map", "0:v", "-map", "1:a"]
    enc = subprocess.Popen(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs, *amap,
                            "-t", f"{total_s:.4f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                            "-maxrate", "6M", "-bufsize", "12M",
                            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.1", "-g", str(fps),
                            "-bf", "2", *meta, *_encode_tail(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    dec = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(src), "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    size = SW * SH * 3
    cur = None
    read = 0
    try:
        for i in range(plan.total):
            j = min(max(0, i - plan.intro), plan.classic - 1)
            while read <= j:
                raw = dec.stdout.read(size)
                if len(raw) < size:
                    break
                cur = Image.frombytes("RGB", (SW, SH), raw)
                read += 1
            if cur is None:
                raise RenderError("motion: the classic clip has no frames")
            enc.stdin.write(mono.frame(i, cur).tobytes())
    finally:
        dec.stdout.close()
        dec.wait()
        enc.stdin.close()
        err = enc.stderr.read().decode(errors="replace")
        code = enc.wait()
    if code != 0:
        raise RenderError(f"ffmpeg (motion encode) failed:\n{err[-1500:]}")


def _meta(metadata: dict[str, str] | None) -> list[str]:
    return [arg for k, v in (metadata or {}).items() for arg in ("-metadata", f"{k}={v}")]


def cover_s(timeline: Timeline) -> float:
    """A moment in the outro where the verdict stands alone in large type: the reel's cover frame."""
    plan = motion_plan(timeline)
    return round((plan.total - plan.fade) / plan.fps - 0.3, 3)


def render_motion(clip: Path, source: Path, source_screen: tuple[int, int, int, int], timeline: Timeline, out: Path, *,
                  category: str, verdict: str, font_path: str, layout: Layout, overlay=None, ticks: bool = False,
                  metadata: dict[str, str] | None = None) -> None:
    """The monolith, from the classic clip (its keys audio) and a 2x render of the same timeline.
    `overlay(mono)` returns a per-frame layer drawn over the wait (the computation creative)."""
    with tempfile.TemporaryDirectory(prefix="monolith-") as td:
        _motion(clip, timeline, out, Path(td), category=category, verdict=verdict, font_path=font_path,
                layout=layout, screen=source_screen, audio=True, meta=_meta(metadata), source=source, overlay=overlay,
                ticks=ticks)


def add_score(clip: Path, timeline: Timeline, out: Path, *, category: str, verdict: str,
              metadata: dict[str, str] | None = None) -> None:
    """The classic picture untouched, the keys plus the template score under it: the music axis on its own."""
    fps = timeline.fps
    total = timeline.total_frames / fps
    verdict_s = timeline.verdict_frame / fps
    with tempfile.TemporaryDirectory(prefix="score-") as td:
        wav = Path(td) / "score.wav"
        template_score(f"{category}|{verdict}", total, 0.2, timeline.submit_frame / fps, verdict_s).write(wav)
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(clip), "-i", str(wav),
              "-filter_complex", "[0:a][1:a]amix=inputs=2:normalize=0:weights='0.8 1':duration=first,"
                                 "loudnorm=I=-17:TP=-1.5:LRA=11,aresample=44100[a]",
              "-map", "0:v", "-map", "[a]", "-c:v", "copy", *_meta(metadata), *_encode_tail(out)])
