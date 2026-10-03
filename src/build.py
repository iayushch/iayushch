#!/usr/bin/env python3
"""Builds the SVG panels in ../assets that make up the iayushch GitHub profile README.

Every word is shaped with HarfBuzz and written out as vector paths, so the panels look identical on
every platform: GitHub serves README SVGs under a CSP that blocks web fonts. The palette and type are
iayushch.com's hero (.act-hero): near-black stage, one mint accent, Roboto, Roboto Mono, Instrument Serif.

    python3 -m venv .venv && .venv/bin/pip install -r src/requirements.txt
    .venv/bin/python src/build.py

Edit the copy in the panel functions below and rebuild; the numbers live in STATS.
"""
from __future__ import annotations

import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import uharfbuzz as hb
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / 'assets'

# ---- palette (iayushch.com .act-hero) ----
BG = '#080B0E'
SURFACE = '#0E1418'
SURFACE_2 = '#141C21'
TEXT = '#F5F7F6'
TEXT_2 = '#C7CDCB'
MUTED = '#8B948F'
BORDER = 'rgba(255,255,255,0.10)'
BORDER_STRONG = 'rgba(255,255,255,0.18)'
MINT = '#8DF0A6'
MINT_2 = '#62DE8C'
MINT_INK = '#06110B'

W = 1000
PAD = 56

# LeetCode numbers read from leetcode.com/u/iayushch on 2026-10-03.
STATS = {'solved': 865, 'easy': 286, 'medium': 504, 'hard': 75, 'badges': 13}

ICONS = json.loads((ROOT / 'icons.json').read_text())
ICONS['x'] = ('M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 '
              '1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z')

# ---------------------------------------------------------------------------------------------------
# Type: HarfBuzz shaping -> SVG path data
# ---------------------------------------------------------------------------------------------------
FONT_FILES = {
    'sans': 'roboto-latin-wght-normal.woff2',
    'mono': 'roboto-mono-latin-wght-normal.woff2',
    'serif': 'instrument-serif-latin-italic.woff2',
}
_faces: dict[str, hb.Face] = {}
_fonts: dict[tuple[str, int], hb.Font] = {}


def _font(family: str, weight: int) -> hb.Font:
    key = (family, weight)
    if key not in _fonts:
        if family not in _faces:
            tt = TTFont(ROOT / 'fonts' / FONT_FILES[family])
            tt.flavor = None
            buf = io.BytesIO()
            tt.save(buf)
            _faces[family] = hb.Face(buf.getvalue())
        font = hb.Font(_faces[family])
        if family != 'serif':
            font.set_variations({'wght': weight})
        _fonts[key] = font
    return _fonts[key]


@dataclass(frozen=True)
class Style:
    family: str
    size: float
    weight: int = 400
    tracking: float = 0.0  # em


def _n(v: float) -> str:
    s = f'{v:.1f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


class _Pen:
    def __init__(self) -> None:
        self.d: list[str] = []
        self.ox = self.oy = self.s = 0.0

    def _p(self, pt) -> str:
        return f'{_n(self.ox + pt[0] * self.s)} {_n(self.oy - pt[1] * self.s)}'

    def moveTo(self, pt):
        self.d.append('M' + self._p(pt))

    def lineTo(self, pt):
        self.d.append('L' + self._p(pt))

    def qCurveTo(self, *pts):
        self.d.append('Q' + ' '.join(self._p(p) for p in pts))

    def curveTo(self, *pts):
        self.d.append('C' + ' '.join(self._p(p) for p in pts))

    def closePath(self):
        self.d.append('Z')

    def endPath(self):
        pass


def _shape(s: str, st: Style):
    font = _font(st.family, st.weight)
    buf = hb.Buffer()
    buf.add_str(s)
    buf.guess_segment_properties()
    hb.shape(font, buf, {'kern': True, 'liga': st.family != 'mono'})
    scale = st.size / font.face.upem
    track = st.tracking * st.size
    glyphs, x = [], 0.0
    for info, pos in zip(buf.glyph_infos or [], buf.glyph_positions or []):
        if info.codepoint == 0:
            raise ValueError(f'{st.family} has no glyph for {s[info.cluster]!r} in {s!r}')
        glyphs.append((info.codepoint, x + pos.x_offset * scale, pos.y_offset * scale))
        x += pos.x_advance * scale + track
    return font, scale, glyphs, (x - track if glyphs else 0.0)


def measure(s: str, st: Style) -> float:
    return _shape(s, st)[3]


# Each outline is written once per SVG (in font units, under <defs>) and placed with <use>; doc() and
# button() collect them with take_glyphs().
_glyph_ids: dict[tuple[str, int, int], str] = {}
_glyph_defs: list[str] = []


def _glyph_ref(st: Style, gid: int) -> str:
    key = (st.family, st.weight if st.family != 'serif' else 0, gid)
    if key not in _glyph_ids:
        ref = f'{st.family[0]}{key[1] // 100}-{gid}'
        pen = _Pen()
        pen.s = 1
        _font(st.family, st.weight).draw_glyph_with_pen(gid, pen)
        _glyph_ids[key] = ref
        _glyph_defs.append(f'<path id="{ref}" d="{"".join(pen.d)}"/>')
    return _glyph_ids[key]


def take_glyphs() -> str:
    out = ''.join(_glyph_defs)
    _glyph_ids.clear()
    _glyph_defs.clear()
    return out


def text(s: str, x: float, y: float, st: Style, fill: str, anchor: str = 'start', attrs: str = '') -> str:
    font, scale, glyphs, w = _shape(s, st)
    x -= {'start': 0, 'middle': w / 2, 'end': w}[anchor]
    k = f'{scale:.6f}'.rstrip('0')
    uses = []
    for gid, gx, gy in glyphs:
        ext = font.get_glyph_extents(gid)
        if not ext or ext.width == 0:
            continue  # spaces
        ref = _glyph_ref(st, gid)
        uses.append(f'<use href="#{ref}" transform="matrix({k} 0 0 {k} {_n(x + gx)} {_n(y - gy)})"/>')
    return f'<g fill="{fill}"{attrs}>{"".join(uses)}</g>'


def runs(parts, x: float, y: float, attrs: str = '') -> tuple[str, float]:
    """parts = [(string, Style, fill), ...] set on one baseline; returns (svg, width)."""
    out, cx = [], x
    for s, st, fill in parts:
        out.append(text(s, cx, y, st, fill))
        cx += measure(s, st)
    return f'<g{attrs}>{"".join(out)}</g>', cx - x


def wrap(s: str, st: Style, max_w: float) -> list[str]:
    lines, cur = [], ''
    for word in s.split(' '):
        trial = f'{cur} {word}'.strip()
        if cur and measure(trial, st) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur]


# ---- type scale ----
H1 = Style('sans', 62, 500, -0.025)
H1_SERIF = Style('serif', 74)
H2 = Style('sans', 36, 500, -0.02)
H2_SERIF = Style('serif', 42)
TITLE = Style('sans', 27, 600, -0.01)
BODY = Style('sans', 16.5, 400)
BODY_SM = Style('sans', 15, 400)
NUM = Style('sans', 38, 500, -0.02)
LABEL = Style('mono', 12.5, 500, 0.14)
LABEL_SM = Style('mono', 11, 500, 0.12)

# ---------------------------------------------------------------------------------------------------
# SVG scaffolding
# ---------------------------------------------------------------------------------------------------
BASE_CSS = """
.rise{animation:rise 1.1s cubic-bezier(.16,1,.3,1) both}
@keyframes rise{from{opacity:0;transform:translateY(14px)}}
.fade{animation:fade 1.6s ease both}
@keyframes fade{from{opacity:0}}
.blink{animation:blink 1.1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
.pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2.4s cubic-bezier(.2,.6,.3,1) infinite}
@keyframes pulse{from{transform:scale(1);opacity:.8}to{transform:scale(3.6);opacity:0}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""


def doc(w: float, h: float, label: str, body: str, defs: str = '', css: str = '', radius: float = 20) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" '
        f'role="img" aria-labelledby="title"><title id="title">{escape(label)}</title>'
        f'<defs><clipPath id="clip"><rect width="{w}" height="{h}" rx="{radius}"/></clipPath>{defs}{take_glyphs()}</defs>'
        f'<style>{BASE_CSS}{css}</style>'
        f'<g clip-path="url(#clip)"><rect width="{w}" height="{h}" fill="{BG}"/>{body}</g>'
        f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="{radius - .5}" stroke="{BORDER}"/></svg>'
    )


def delay(i: int, step: float = .09, base: float = .05) -> str:
    return f' class="rise" style="animation-delay:{base + i * step:.2f}s"'


def glyph(name: str, x: float, y: float, size: float, fill: str) -> str:
    """A 24-box simple-icons mark placed at (x, y)."""
    k = size / 24
    return f'<path transform="translate({_n(x)} {_n(y)}) scale({k:.4f})" d="{ICONS[name]}" fill="{fill}"/>'


def corners(w: float, h: float, inset: float = 18, arm: float = 14, colour: str = 'rgba(141,240,166,0.45)') -> str:
    a, b, c, d = inset, w - inset, inset, h - inset
    path = (f'M{a} {c + arm}V{c}H{a + arm} M{b - arm} {c}H{b}V{c + arm} '
            f'M{b} {d - arm}V{d}H{b - arm} M{a + arm} {d}H{a}V{d - arm}')
    return f'<path d="{path}" stroke="{colour}" stroke-width="1.5"/>'


def glow_defs(gid: str, cx: float, cy: float, r: float, opacity: float) -> str:
    return (f'<radialGradient id="{gid}" cx="{cx}" cy="{cy}" r="{r}" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{MINT}" stop-opacity="{opacity}"/>'
            f'<stop offset="1" stop-color="{MINT}" stop-opacity="0"/></radialGradient>')


def section_head(index: str, name: str, right: str, title_parts, y: float = 60) -> str:
    out = [text(index, PAD, y, LABEL, MINT)]
    nx = PAD + measure(index, LABEL) + 10
    out.append(text(f'/ {name}', nx, y, LABEL, TEXT_2))
    rx = W - PAD - measure(right, LABEL_SM)
    lx0 = nx + measure(f'/ {name}', LABEL) + 18
    out.append(f'<path d="M{_n(lx0)} {y - 4.5}H{_n(rx - 18)}" stroke="{BORDER}"/>')
    out.append(f'<path d="M{_n(lx0)} {y - 4.5}h48" stroke="{MINT}" stroke-opacity=".7"/>')
    out.append(text(right, rx, y, LABEL_SM, MUTED))
    title, _ = runs(title_parts, PAD, y + 62)
    out.append(title)
    return ''.join(out)


def sheen(x0: float, x1: float, y: float, dur: float, begin: float = 0, width: float = 120) -> str:
    """A mint glint that travels along a hairline."""
    return (f'<rect x="{_n(x0)}" y="{_n(y - .75)}" width="{width}" height="1.5" fill="url(#glint)">'
            f'<animate attributeName="x" values="{_n(x0)};{_n(x1 - width)}" dur="{dur}s" begin="{begin}s" '
            f'repeatCount="indefinite"/></rect>')


GLINT = (f'<linearGradient id="glint"><stop offset="0" stop-color="{MINT}" stop-opacity="0"/>'
         f'<stop offset=".7" stop-color="{MINT}"/><stop offset="1" stop-color="{MINT}" stop-opacity="0"/>'
         f'</linearGradient>')
SOFT = '<filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4"/></filter>'


# ---------------------------------------------------------------------------------------------------
# 01 — hero
# ---------------------------------------------------------------------------------------------------
def hero() -> str:
    H = 600
    body, defs = [], [glow_defs('g1', 860, -40, 620, .17), glow_defs('g2', 790, 268, 210, .10), GLINT, SOFT]
    defs.append('<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
                '<circle cx="1" cy="1" r="1" fill="rgba(255,255,255,0.09)"/></pattern>'
                '<radialGradient id="dotfade" cx="800" cy="250" r="380" gradientUnits="userSpaceOnUse">'
                '<stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>'
                '</radialGradient><mask id="dotmask"><rect width="1000" height="600" fill="url(#dotfade)"/></mask>')
    body.append(f'<rect width="{W}" height="{H}" fill="url(#g1)"/>')
    body.append(f'<rect width="{W}" height="{H}" fill="url(#dots)" mask="url(#dotmask)"/>')
    # slow scan band
    defs.append(f'<linearGradient id="scan" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{MINT}" '
                f'stop-opacity="0"/><stop offset=".5" stop-color="{MINT}" stop-opacity=".045"/>'
                f'<stop offset="1" stop-color="{MINT}" stop-opacity="0"/></linearGradient>')
    body.append(f'<rect y="-160" width="{W}" height="160" fill="url(#scan)"><animate attributeName="y" '
                f'values="-160;{H}" dur="7s" repeatCount="indefinite"/></rect>')
    body.append(corners(W, H))

    # HUD row
    hud = [f'<rect x="{PAD}" y="31" width="34" height="34" rx="10" fill="rgba(141,240,166,0.08)" '
           f'stroke="rgba(141,240,166,0.55)"/>',
           text('AK', PAD + 17, 52.5, Style('mono', 13, 600, .02), MINT, 'middle')]
    name_x = PAD + 50
    hud.append(text('AYUSH KUMAR', name_x, 53, LABEL, TEXT))
    hud.append(text('/  @IAYUSHCH', name_x + measure('AYUSH KUMAR', LABEL) + 14, 53, LABEL, MUTED))
    pill = 'HAVE A PROJECT? LET’S TALK'
    pst = Style('mono', 11.5, 500, .12)
    pw = 44 + measure(pill, pst) + 18
    px = W - PAD - pw
    hud.append(f'<rect x="{_n(px)}" y="32" width="{_n(pw)}" height="32" rx="16" fill="rgba(141,240,166,0.07)" '
               f'stroke="rgba(141,240,166,0.38)"/>')
    hud.append(f'<circle class="pulse" cx="{_n(px + 22)}" cy="48" r="4" fill="{MINT}"/>')
    hud.append(f'<circle cx="{_n(px + 22)}" cy="48" r="4" fill="{MINT}"/>')
    hud.append(text(pill, px + 38, 52, pst, TEXT))
    body.append(f'<g{delay(0)}>{"".join(hud)}</g>')
    body.append(f'<path d="M{PAD} 92H{W - PAD}" stroke="{BORDER}"/>' + sheen(PAD, W - PAD, 92, 6, 1.2, 160))

    # eyebrow + headline
    body.append(f'<g{delay(1)}><path d="M{PAD} 140.5h22" stroke="{MINT}"/>'
                + text('SENIOR SOFTWARE DEVELOPER  ·  BENGALURU, IN', PAD + 34, 145, LABEL, MINT) + '</g>')
    body.append(f'<g{delay(2)}>{text("I ship complete", PAD - 3, 218, H1, TEXT)}</g>')
    body.append(f'<g{delay(3)}>{text("products,", PAD, 292, H1_SERIF, MINT)}</g>')
    line3, w3 = runs([('end', H1_SERIF, MINT), (' to ', H1, TEXT), ('end.', H1_SERIF, MINT)], PAD, 366)
    caret = f'<rect class="blink" x="{_n(PAD + w3 + 12)}" y="314" width="5" height="56" fill="{MINT}"/>'
    body.append(f'<g{delay(4)}>{line3}{caret}</g>')

    sub = ('Full-stack engineer taking products from a blank page to production. React, Spring Boot, '
           'Kafka, Kubernetes, AWS. I build it, ship it, and stay to run it.')
    lines = wrap(sub, BODY, 500)
    body.append(f'<g{delay(5)}>' + ''.join(text(l, PAD, 414 + i * 26, BODY, TEXT_2) for i, l in enumerate(lines))
                + '</g>')

    # orbital system: five layers, one owner
    cx, cy = 790, 262
    orb = [f'<circle cx="{cx}" cy="{cy}" r="210" fill="url(#g2)"/>',
           f'<circle cx="{cx}" cy="{cy}" r="160" stroke="{MINT}" stroke-opacity=".28" stroke-width="7" '
           f'stroke-dasharray="1.2 11.4"><animateTransform attributeName="transform" type="rotate" '
           f'from="0 {cx} {cy}" to="360 {cx} {cy}" dur="120s" repeatCount="indefinite"/></circle>',
           f'<circle cx="{cx}" cy="{cy}" r="172" stroke="{BORDER}" stroke-dasharray="2 6"/>',
           f'<path d="M{cx - 196} {cy}H{cx + 196}M{cx} {cy - 196}V{cy + 196}" stroke="rgba(255,255,255,0.06)" '
           f'stroke-dasharray="3 5"/>',
           f'<circle cx="{cx}" cy="{cy}" r="112" stroke="{BORDER_STRONG}"/>']
    layers = ['UI', 'API', 'DATA', 'INFRA', 'OBS']
    for i, lab in enumerate(layers):
        a = math.radians(-90 + i * 72)
        nx, ny = cx + 112 * math.cos(a), cy + 112 * math.sin(a)
        lx, ly = cx + 138 * math.cos(a), cy + 138 * math.sin(a) + 4
        orb.append(f'<circle cx="{_n(nx)}" cy="{_n(ny)}" r="5" fill="{BG}" stroke="{MINT}" stroke-opacity=".8"/>')
        orb.append(text(lab, lx, ly, Style('mono', 10.5, 500, .1), TEXT_2, 'middle'))
        # each node flares as the packet passes it (8s orbit, starting at the top)
        t = i / 5
        orb.append(f'<circle cx="{_n(nx)}" cy="{_n(ny)}" r="5" fill="{MINT}" opacity="0"><animate '
                   f'attributeName="opacity" values="0;0;1;0;0" keyTimes="0;{max(t - .001, 0):.3f};{t:.3f};'
                   f'{min(t + .12, .999):.3f};1" dur="8s" repeatCount="indefinite"/></circle>')
    orb.append(f'<g><animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" '
               f'to="360 {cx} {cy}" dur="8s" repeatCount="indefinite"/>'
               f'<circle cx="{cx}" cy="{cy - 112}" r="9" fill="{MINT}" opacity=".55" filter="url(#soft)"/>'
               f'<circle cx="{cx}" cy="{cy - 112}" r="3.5" fill="{MINT}"/></g>')
    circ = 2 * math.pi * 70
    orb.append(f'<circle cx="{cx}" cy="{cy}" r="70" stroke="{MINT}" stroke-opacity=".14" stroke-width="2"/>')
    for sw, op, filt in ((8, .5, ' filter="url(#soft)"'), (2.5, 1, '')):
        orb.append(f'<circle cx="{cx}" cy="{cy}" r="70" stroke="{MINT}" stroke-opacity="{op}" stroke-width="{sw}" '
                   f'stroke-linecap="round" stroke-dasharray="{circ * .22:.1f} {circ:.1f}"{filt}>'
                   f'<animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" '
                   f'to="-360 {cx} {cy}" dur="5s" repeatCount="indefinite"/></circle>')
    orb.append(f'<circle cx="{cx}" cy="{cy}" r="38" fill="{SURFACE_2}" stroke="rgba(141,240,166,0.45)"/>')
    orb.append(text('›', cx - 13, cy + 8, Style('mono', 24, 600), MINT))
    orb.append(f'<rect class="blink" x="{cx + 2}" y="{cy + 5}" width="12" height="3" fill="{MINT}"/>')
    orb.append(text('12.97°N  ·  77.59°E  ·  IST', cx, 468, Style('mono', 10.5, 500, .14), MUTED, 'middle'))
    body.append(f'<g class="fade" style="animation-delay:.5s">{"".join(orb)}</g>')

    # telemetry
    ty = 500
    body.append(f'<path d="M{PAD} {ty}H{W - PAD}" stroke="{BORDER}"/>' + sheen(PAD, W - PAD, ty, 9, 3, 200))
    cells = [(str(STATS['solved']), '', 'PROBLEMS SOLVED'), (str(STATS['badges']), '', 'LEETCODE BADGES'),
             ('04', '', 'PRODUCTS, END TO END'), ('24', 'h', 'REPLY TO EVERY BRIEF')]
    cw = (W - 2 * PAD) / 4
    for i, (num, unit, lab) in enumerate(cells):
        x0 = PAD + i * cw
        xi = x0 + (0 if i == 0 else 26)
        cell = [] if i == 0 else [f'<path d="M{_n(x0)} {ty + 18}V{ty + 78}" stroke="{BORDER}"/>']
        g, _ = runs([(num, NUM, TEXT), (unit, Style('sans', 24, 500), MINT)], xi, ty + 52)
        cell += [g, text(lab, xi, ty + 76, LABEL_SM, MUTED)]
        body.append(f'<g{delay(6 + i, .08)}>{"".join(cell)}</g>')

    label = ('Ayush Kumar (@iayushch), Senior Software Developer in Bengaluru. I ship complete products, end to '
             'end. Have a project? Let’s talk. 865 LeetCode problems solved, 13 LeetCode badges, '
             '4 products owned end to end, replies within 24 hours.')
    return doc(W, H, label, ''.join(body), ''.join(defs))


# ---------------------------------------------------------------------------------------------------
# Link buttons
# ---------------------------------------------------------------------------------------------------
GLOBE = ('M12 2.75a9.25 9.25 0 1 0 0 18.5 9.25 9.25 0 0 0 0-18.5Z M2.75 12h18.5 M12 2.75c2.4 2.5 3.6 5.6 3.6 9.25S14.4 '
         '18.75 12 21.25 M12 2.75C9.6 5.25 8.4 8.35 8.4 12s1.2 6.75 3.6 9.25')
MAIL = 'M3.5 5.75h17a.75.75 0 0 1 .75.75v11a.75.75 0 0 1-.75.75h-17a.75.75 0 0 1-.75-.75v-11a.75.75 0 0 1 .75-.75Z M3 6.5l9 6.75 9-6.75'
ARROW = 'M7 17 17 7 M8.5 7H17v8.5'


def button(label: str, icon: str, primary: bool = False, stroke_icon: bool = False) -> str:
    H, st = 52, Style('sans', 16, 500, .005)
    tw = measure(label, st)
    w = 22 + 20 + 11 + tw + 12 + 16 + 20
    fg = MINT_INK if primary else TEXT
    bg = MINT if primary else SURFACE
    parts = [f'<rect x=".75" y=".75" width="{_n(w - 1.5)}" height="{H - 1.5}" rx="{(H - 1.5) / 2}" fill="{bg}" '
             f'stroke="{MINT if primary else BORDER_STRONG}" stroke-width="1.5"/>']
    if stroke_icon:
        parts.append(f'<path transform="translate(22 16) scale(.8333)" d="{icon}" stroke="{fg}" stroke-width="1.8" '
                     f'stroke-linecap="round" stroke-linejoin="round"/>')
    else:
        parts.append(glyph(icon, 22, 16, 20, fg))
    parts.append(text(label, 53, 31.5, st, fg))
    parts.append(f'<path transform="translate({_n(w - 36)} 18) scale(.6667)" d="{ARROW}" '
                 f'stroke="{fg if primary else MINT}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{_n(w)}" height="{H}" viewBox="0 0 {_n(w)} {H}" '
            f'fill="none" role="img" aria-label="{escape(label)}"><title>{escape(label)}</title><defs>{take_glyphs()}</defs>'
            f'{"".join(parts)}</svg>')


# ---------------------------------------------------------------------------------------------------
# 02 — shipping
# ---------------------------------------------------------------------------------------------------
PROJECTS = [
    ('01', 'QuizKool', 'FULL-STACK', 'LEAD ENGINEER', 'LAUNCHING DEC 2026', True,
     'AI-powered MCQ platform for students and teachers: practice, exams and progress in one place.'),
    ('02', 'Basera', 'MOBILE', 'FOUNDER', 'LAUNCHING DEC 2026', True,
     'Rent and billing app for PG and flat owners, growing into listings the whole city can find.'),
    ('03', 'RasoiBox', 'PLATFORM', 'FREELANCE BUILD', 'LIVE · ONGOING', False,
     'Multi-branch tiffin subscription platform: ordering, delivery and admin, built from scratch.'),
    ('04', 'NGO Platform', 'WEB', 'FREELANCE BUILD', 'LIVE · ONGOING', False,
     'Donations, volunteers and events for an NGO serving people in remote areas.'),
]


def shipping() -> str:
    H = 630
    body = [f'<rect width="{W}" height="{H}" fill="url(#g1)"/>',
            section_head('02', 'SHIPPING', 'TWO LAUNCHING DEC 2026  ·  TWO RUNNING FOR CLIENTS',
                         [('Four products, each owned ', H2, TEXT), ('end to end.', H2_SERIF, MINT)])]
    defs = [glow_defs('g1', 120, 700, 520, .07), GLINT,
            f'<linearGradient id="rim" x1="0" x2="1"><stop offset="0" stop-color="{MINT}"/>'
            f'<stop offset="1" stop-color="{MINT}" stop-opacity="0"/></linearGradient>']
    gap, cw, ch = 20, (W - 2 * PAD - 20) / 2, 210
    for i, (idx, name, tag, role, status, launching, desc) in enumerate(PROJECTS):
        x, y = PAD + (i % 2) * (cw + gap), 168 + (i // 2) * (ch + gap)
        c = [f'<rect x="{_n(x)}" y="{y}" width="{_n(cw)}" height="{ch}" rx="16" fill="{SURFACE}" stroke="{BORDER}"/>',
             f'<path d="M{_n(x + 24)} {y + .5}h150" stroke="url(#rim)" stroke-width="1.5"/>',
             text(idx, x + 26, y + 40, LABEL_SM, MUTED)]
        tw = measure(tag, Style('mono', 10, 500, .12))
        c.append(f'<rect x="{_n(x + 54)}" y="{y + 25}" width="{_n(tw + 20)}" height="22" rx="11" stroke="{BORDER_STRONG}"/>')
        c.append(text(tag, x + 64, y + 40, Style('mono', 10, 500, .12), TEXT_2))
        sw = measure(status, Style('mono', 10, 500, .12))
        sx = x + cw - 26 - sw
        c.append(text(status, sx, y + 40, Style('mono', 10, 500, .12), MINT if launching else TEXT_2))
        if launching:
            c.append(f'<circle class="pulse" cx="{_n(sx - 12)}" cy="{y + 36.5}" r="3.5" fill="{MINT}" '
                     f'style="animation-delay:{i * .6:.1f}s"/>')
        c.append(f'<circle cx="{_n(sx - 12)}" cy="{y + 36.5}" r="3.5" fill="{MINT if launching else MINT_2}"/>')
        nm, nw = runs([(name, TITLE, TEXT)], x + 26, y + 92)
        c.append(nm)
        c.append(text(role, x + 26 + nw + 14, y + 92, LABEL_SM, MINT))
        for j, line in enumerate(wrap(desc, BODY_SM, cw - 52)):
            c.append(text(line, x + 26, y + 130 + j * 23, BODY_SM, TEXT_2))
        ly = y + ch - 26
        c.append(f'<path d="M{_n(x + 26)} {ly}H{_n(x + cw - 26)}" stroke="{BORDER}"/>')
        c.append(sheen(x + 26, x + cw - 26, ly, 4.5 if launching else 7, i * .9, 90))
        body.append(f'<g{delay(i, .1, .1)}>{"".join(c)}</g>')
    label = ('Shipping: four products, each owned end to end. QuizKool, AI-powered MCQ platform, lead engineer, '
             'launching December 2026. Basera, rent and billing app for PG and flat owners, founder, launching '
             'December 2026. RasoiBox, multi-branch tiffin subscription platform, freelance build, ongoing. NGO '
             'Platform, donations, volunteers and events for an NGO, freelance build, ongoing.')
    return doc(W, H, label, ''.join(body), ''.join(defs))


# ---------------------------------------------------------------------------------------------------
# 03 — stack
# ---------------------------------------------------------------------------------------------------
JAVA_CUP = ('M5 9.5h11v4.5a5 5 0 0 1-5 5h-1a5 5 0 0 1-5-5Z M16 11h1.5a2.25 2.25 0 0 1 0 4.5H16 M8 3.5c-.8 1 .8 2 0 3 '
            'M11 3.5c-.8 1 .8 2 0 3 M3.5 21h14')
AWS_SMILE = 'M3 15.5C5.8 18.7 9 20.2 12 20.2s6.2-1.5 9-4.7 M18.4 14.6l2.8.7-.9 2.8'
TIERS = [
    ('01', 'CLIENT', 'Two front ends, one design language.',
     [('react', 'React', '#61DAFB'), ('react', 'React Native', '#C084FC'), ('typescript', 'TypeScript', '#5B9CF3')]),
    ('02', 'SERVICES', 'Spring Boot services I designed, not inherited.',
     [('spring', 'Spring Boot', '#7CCB4A'), ('java', 'Java', '#F89820'), ('python', 'Python', '#5FA8E6')]),
    ('03', 'DATA & MESSAGING', 'Schemas designed for the access pattern.',
     [('postgresql', 'PostgreSQL', '#6F8DFF'), ('kafka', 'Kafka', '#C4B5FD'), ('redis', 'Redis', '#FF5C4F'),
      ('mongodb', 'MongoDB', '#5DC85E')]),
    ('04', 'INFRA', 'Containerised, orchestrated, on AWS.',
     [('docker', 'Docker', '#3EA8FF'), ('kubernetes', 'Kubernetes', '#5E8EF7'), ('aws', 'AWS', '#FF9900'),
      ('ansible', 'Ansible', '#FF5A5A')]),
    ('05', 'OBSERVABILITY', 'I’ve been on call for it.',
     [('grafana', 'Grafana', '#FF8A3D'), ('prometheus', 'Prometheus', '#FF7A55'),
      ('opensearch', 'OpenSearch', '#4BA3FF')]),
]


def chip(icon: str, label: str, colour: str, x: float, y: float) -> tuple[str, float]:
    st = Style('sans', 14, 500)
    w = 12 + 18 + 9 + measure(label, st) + 14
    out = [f'<rect x="{_n(x)}" y="{y}" width="{_n(w)}" height="38" rx="10" fill="{SURFACE_2}" stroke="{BORDER}"/>']
    gx, gy = x + 12, y + 10
    if icon == 'java':
        out.append(f'<path transform="translate({_n(gx)} {gy}) scale(.75)" d="{JAVA_CUP}" stroke="{colour}" '
                   f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')
    elif icon == 'aws':
        out.append(text('aws', gx + 9, gy + 10, Style('sans', 9.5, 700), TEXT, 'middle'))
        out.append(f'<path transform="translate({_n(gx)} {gy}) scale(.75)" d="{AWS_SMILE}" stroke="{colour}" '
                   f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')
    else:
        out.append(glyph(icon, gx, gy, 18, colour))
    out.append(text(label, gx + 27, y + 24, st, TEXT))
    return ''.join(out), w


def stack() -> str:
    top, row_h = 168, 88
    H = top + row_h * len(TIERS) + 34
    body = [f'<rect width="{W}" height="{H}" fill="url(#g1)"/>',
            section_head('03', 'STACK', 'FIVE LAYERS  ·  ONE OWNER',
                         [('Every layer, ', H2, TEXT), ('in production.', H2_SERIF, MINT)])]
    defs = [glow_defs('g1', 1000, 0, 560, .09), SOFT]
    spine_x = PAD + 8
    ys = [top + row_h * i + row_h / 2 for i in range(len(TIERS))]
    body.append(f'<path d="M{spine_x} {ys[0]}V{ys[-1]}" stroke="{BORDER_STRONG}"/>')
    dur = 6.0
    for i, (idx, name, claim, chips) in enumerate(TIERS):
        y = top + row_h * i
        cy = ys[i]
        r = []
        if i:
            r.append(f'<path d="M{PAD + 40} {y}H{W - PAD}" stroke="{BORDER}"/>')
        r.append(f'<circle cx="{spine_x}" cy="{cy}" r="6" fill="{BG}" stroke="{MINT}" stroke-opacity=".7"/>')
        t = .8 * i / (len(TIERS) - 1)
        r.append(f'<circle cx="{spine_x}" cy="{cy}" r="6" fill="{MINT}" opacity="0"><animate attributeName="opacity" '
                 f'values="0;0;1;0;0" keyTimes="0;{max(t - .001, 0):.3f};{t + .001:.3f};{t + .14:.3f};1" '
                 f'dur="{dur}s" repeatCount="indefinite"/></circle>')
        r.append(text(f'{idx}  {name}', PAD + 40, cy - 6, LABEL, TEXT))
        r.append(text(claim, PAD + 40, cy + 19, BODY_SM, MUTED))
        built, total = [], 0.0
        for icon, label, colour in chips:
            built.append((icon, label, colour))
            total += chip(icon, label, colour, 0, 0)[1] + 8
        cx = W - PAD - (total - 8)
        for icon, label, colour in built:
            svg, w = chip(icon, label, colour, cx, cy - 19)
            r.append(svg)
            cx += w + 8
        body.append(f'<g{delay(i, .08, .1)}>{"".join(r)}</g>')
    # the request packet: top to bottom of the stack, then a pause
    vals = ';'.join(_n(v) for v in (ys[0], ys[-1], ys[-1]))
    for rad, op, filt in ((10, .55, ' filter="url(#soft)"'), (4, 1, '')):
        body.append(f'<circle cx="{spine_x}" cy="{ys[0]}" r="{rad}" fill="{MINT}" opacity="{op}"{filt}>'
                    f'<animate attributeName="cy" values="{vals}" keyTimes="0;.8;1" dur="{dur}s" '
                    f'repeatCount="indefinite"/></circle>')
    label = ('Stack, every layer in production. Client: React, React Native, TypeScript. Services: Spring Boot, '
             'Java, Python. Data and messaging: PostgreSQL, Kafka, Redis, MongoDB. Infra: Docker, Kubernetes, AWS, '
             'Ansible. Observability: Grafana, Prometheus, OpenSearch.')
    return doc(W, H, label, ''.join(body), ''.join(defs))


# ---------------------------------------------------------------------------------------------------
# 04 — protocol
# ---------------------------------------------------------------------------------------------------
RULES = [
    ('Put in the reps.', f'{STATS["solved"]} LeetCode problems solved, {STATS["hard"]} of them hard.'),
    ('Own it end to end.', 'Interface, API, data, deploy, monitoring. No handoffs.'),
    ('Measure, don’t guess.', 'If it isn’t on a dashboard, it isn’t done.'),
    ('Stay after v1.', 'I run what I build. Retainers welcome.'),
]


def protocol() -> str:
    H = 560
    body = [f'<rect width="{W}" height="{H}" fill="url(#g1)"/>',
            section_head('04', 'PROTOCOL', 'DISCIPLINE, MEASURED',
                         [('Motivation starts it. ', H2, TEXT), ('Discipline ships it.', H2_SERIF, MINT)])]
    defs = [glow_defs('g1', 780, 560, 460, .10), GLINT,
            '<style>.col{animation:wave 3.6s ease-in-out infinite}@keyframes wave{0%,100%{opacity:.5}'
            '45%{opacity:1}}</style>']
    for i, (head, sub) in enumerate(RULES):
        y = 214 + i * 84
        r = [text(f'0{i + 1}', PAD, y, LABEL, MINT),
             text(head, PAD + 44, y + 2, Style('sans', 21, 500, -.01), TEXT),
             text(sub, PAD + 44, y + 29, BODY_SM, MUTED)]
        if i < len(RULES) - 1:
            r.append(f'<path d="M{PAD + 44} {y + 52}H500" stroke="{BORDER}"/>')
        body.append(f'<g{delay(i, .1, .1)}>{"".join(r)}</g>')

    # LeetCode card: one dot per solved problem, easy to hard
    x, y, cw = 548, 168, W - PAD - 548
    card = [text('LEETCODE  /  @IAYUSHCH', x + 26, y + 40, LABEL_SM, MUTED),
            text(f'{STATS["badges"]} BADGES', x + cw - 26, y + 40, LABEL_SM, MINT, 'end')]
    big, bw = runs([(str(STATS['solved']), Style('sans', 88, 500, -.03), TEXT)], x + 22, y + 130)
    card.append(big)
    card.append(text('solved', x + 22 + bw + 12, y + 130, Style('serif', 40), MINT))
    card.append(text('ONE DOT PER PROBLEM  ·  EASY TO HARD', x + 26, y + 158, LABEL_SM, TEXT_2))
    tiers = [('easy', MINT, .32), ('medium', MINT, .78), ('hard', '#E6FFEE', 1)]
    dots = [(c, o) for key, c, o in tiers for _ in range(STATS[key])]
    rows, gx0, gy0 = 15, x + 26, y + 180
    cols = math.ceil(len(dots) / rows)
    pitch = (cw - 52) / cols
    size = pitch - 1.5
    for c in range(cols):
        cells = [f'<rect x="{_n(gx0 + c * pitch)}" y="{_n(gy0 + r * pitch)}" width="{_n(size)}" height="{_n(size)}" '
                 f'rx="1.1" fill="{colour}" fill-opacity="{op}"/>'
                 for r, (colour, op) in enumerate(dots[c * rows:(c + 1) * rows])]
        card.append(f'<g class="col" style="animation-delay:{c * .045:.3f}s">{"".join(cells)}</g>')
    ly, lx = gy0 + rows * pitch + 34, x + 26
    for key, colour, op in tiers:
        label = f'{STATS[key]} {key.upper()}'
        card.append(f'<rect x="{_n(lx)}" y="{_n(ly - 8.5)}" width="8" height="8" rx="1.5" fill="{colour}" '
                    f'fill-opacity="{op}"/>')
        card.append(text(label, lx + 16, ly, LABEL_SM, TEXT_2))
        lx += 16 + measure(label, LABEL_SM) + 24
    ch = ly + 32 - y
    card[:0] = [f'<rect x="{x}" y="{y}" width="{cw}" height="{_n(ch)}" rx="18" fill="{SURFACE}" stroke="{BORDER}"/>',
                f'<path d="M{x + 24} {y + .5}h170" stroke="{MINT}" stroke-opacity=".8" stroke-width="1.5"/>']
    body.append(f'<g class="fade" style="animation-delay:.3s">{"".join(card)}</g>')
    label = ('Protocol: motivation starts it, discipline ships it. 01 Put in the reps. '
             '02 Own it end to end: interface, API, data, deploy, monitoring. 03 Measure, don’t guess. 04 Stay '
             f'after v1: I run what I build. LeetCode: {STATS["solved"]} problems solved ({STATS["easy"]} easy, '
             f'{STATS["medium"]} medium, {STATS["hard"]} hard), {STATS["badges"]} badges.')
    return doc(W, H, label, ''.join(body), ''.join(defs))


# ---------------------------------------------------------------------------------------------------
# 05 — sign-off
# ---------------------------------------------------------------------------------------------------
def footer() -> str:
    H = 330
    body = [f'<rect width="{W}" height="{H}" fill="url(#g1)"/>', corners(W, H)]
    defs = [glow_defs('g1', 500, 420, 520, .16), GLINT]
    body.append(text('05', PAD, 64, LABEL, MINT) + text('/ SIGNAL', PAD + measure('05', LABEL) + 10, 64, LABEL, TEXT_2))
    l1, _ = runs([('Let’s build something', Style('sans', 46, 500, -.025), TEXT)], PAD - 2, 140)
    l2, _ = runs([('that ships.', Style('serif', 56), MINT)], PAD, 198)
    body.append(f'<g{delay(0)}>{l1}</g><g{delay(1)}>{l2}</g>')
    rows = [('EMAIL', 'iayushch@gmail.com'), ('WEB', 'iayushch.com'), ('BASE', 'Bengaluru, IN · UTC+5:30'),
            ('REPLY', 'Within 24 hours')]
    for i, (k, v) in enumerate(rows):
        y = 100 + i * 34
        body.append(f'<g{delay(2 + i, .08)}>' + text(k, 610, y, LABEL_SM, MUTED)
                    + text(v, 680, y, Style('mono', 14, 500, .02), TEXT if i < 2 else TEXT_2) + '</g>')
    body.append(f'<path d="M{PAD} 256H{W - PAD}" stroke="{BORDER}"/>' + sheen(PAD, W - PAD, 256, 5, .5, 240))
    body.append(text('GOOD SOFTWARE CREATES A BRIGHTER TOMORROW.', W / 2, 294, Style('mono', 11.5, 500, .24),
                     MUTED, 'middle'))
    label = ('Let’s build something that ships. Email iayushch@gmail.com, web iayushch.com, based in Bengaluru, '
             'India, replies within 24 hours. Good software creates a brighter tomorrow.')
    return doc(W, H, label, ''.join(body), ''.join(defs))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    files = {
        'hero.svg': hero(),
        'shipping.svg': shipping(),
        'stack.svg': stack(),
        'protocol.svg': protocol(),
        'signoff.svg': footer(),
        'btn-site.svg': button('iayushch.com', GLOBE, primary=True, stroke_icon=True),
        'btn-linkedin.svg': button('LinkedIn', 'linkedin'),
        'btn-x.svg': button('X', 'x'),
        'btn-leetcode.svg': button('LeetCode', 'leetcode'),
        'btn-email.svg': button('Email', MAIL, stroke_icon=True),
    }
    for name, svg in files.items():
        (OUT / name).write_text(svg)
        print(f'{name:18} {len(svg) / 1024:6.1f} KB')


if __name__ == '__main__':
    main()
