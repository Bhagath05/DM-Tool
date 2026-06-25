"""HTML/CSS poster templates → string. Rasterised to PNG by `render.py`.

Three distinct, meaning-first layouts — the business-specific hero image is
the canvas, brand copy is composed on top. CSS is static (scoped by a body
class) so the only per-brand value is the `:root` block; the hero is injected
as an <img>. Fonts differ per layout so posts don't all feel the same.
"""

from __future__ import annotations

import html as _html

from aicmo.modules.poster.schemas import LinkedInCopy, PosterTheme

_FONTS = (
    "https://fonts.googleapis.com/css2?"
    "family=Archivo:wght@600;700;800"
    "&family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700"
    "&family=Manrope:wght@500;600;700"
    "&family=Sora:wght@600;700;800&display=swap"
)

_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:__W__px;height:__H__px}
body{font-family:'Manrope',system-ui,sans-serif;background:var(--bg);color:var(--ink);overflow:hidden;position:relative}
.heroimg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.herofallback{position:absolute;inset:0;background:
  radial-gradient(90% 70% at 78% 22%, color-mix(in srgb, var(--c1) 55%, transparent), transparent 60%),
  radial-gradient(80% 70% at 20% 90%, color-mix(in srgb, var(--c2) 45%, transparent), transparent 60%),
  var(--bg)}
.grain{position:absolute;inset:0;opacity:.05;mix-blend-mode:overlay;background-image:radial-gradient(rgba(255,255,255,.8) .5px,transparent .6px);background-size:3px 3px}
.brand{display:flex;align-items:center;gap:13px}
.brand .mark{width:48px;height:48px;border-radius:13px;background:linear-gradient(140deg,var(--c1),var(--c2));display:flex;align-items:center;justify-content:center;box-shadow:0 6px 26px rgba(0,0,0,.4)}
.brand .mark span{font-family:'Archivo';font-weight:800;font-size:21px;color:#0a0c10}
.brand .name{font-weight:700;font-size:23px;letter-spacing:.01em;color:#fff;text-shadow:0 2px 16px rgba(0,0,0,.5)}
.site{display:inline-flex;align-items:center;gap:8px;color:var(--muted);font-weight:600;font-size:16px}
.site svg{width:17px;height:17px;stroke:var(--c1);fill:none}
.chip{display:inline-flex;align-items:center;gap:8px;padding:9px 15px;border-radius:999px;border:1px solid rgba(255,255,255,.28);background:rgba(0,0,0,.32);backdrop-filter:blur(5px);font-weight:700;font-size:13px;letter-spacing:.07em;text-transform:uppercase;color:#fff}
.chip .dot{width:7px;height:7px;border-radius:50%;background:var(--c1)}
.eyebrow{display:inline-flex;align-items:center;gap:12px;font-weight:700;font-size:14.5px;letter-spacing:.30em;text-transform:uppercase;color:var(--c1)}
.eyebrow::before{content:"";width:40px;height:2px;background:linear-gradient(90deg,var(--c1),transparent)}
.cta{display:inline-flex;align-items:center;gap:11px;padding:16px 25px;border-radius:14px;background:linear-gradient(140deg,var(--c1),var(--c2));color:#0a0c10;font-weight:700;font-size:18px;box-shadow:0 12px 32px rgba(0,0,0,.32);width:fit-content}
.cta svg{width:19px;height:19px;stroke:#0a0c10}
.frame{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:space-between}

/* ---------- EDITORIAL (full-bleed) ---------- */
body.editorial .scrim{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.55) 0%,rgba(0,0,0,0) 24%,rgba(0,0,0,0) 40%,rgba(0,0,0,.62) 74%,rgba(0,0,0,.93) 100%)}
body.editorial .edge{position:absolute;inset:0;box-shadow:inset 0 0 0 1.5px color-mix(in srgb,var(--c1) 30%,transparent),inset 0 0 140px rgba(0,0,0,.5)}
body.editorial .frame{padding:66px 70px}
body.editorial h1{font-family:'Fraunces';font-weight:600;font-size:90px;line-height:.99;letter-spacing:-.015em;color:#fff;text-shadow:0 4px 40px rgba(0,0,0,.55);margin-top:18px}
body.editorial h1 em{font-style:italic;background:linear-gradient(100deg,var(--c1),var(--c2));-webkit-background-clip:text;background-clip:text;color:transparent}
body.editorial .sub{margin-top:20px;font-size:27px;line-height:1.4;font-weight:500;color:#e9e3da;max-width:760px;text-shadow:0 2px 16px rgba(0,0,0,.6)}
body.editorial .cta{margin-top:28px}
body.editorial .copy{max-width:880px}

/* ---------- SPLIT ---------- */
body.split .grid{position:absolute;inset:0;display:grid;grid-template-columns:560px 1fr}
body.split .panel{position:relative;padding:70px 58px;display:flex;flex-direction:column;justify-content:space-between;background:radial-gradient(120% 80% at 0% 0%,color-mix(in srgb,var(--c1) 14%,var(--bg)),var(--bg) 62%)}
body.split .panel::after{content:"";position:absolute;top:0;right:-1px;width:2px;height:100%;background:linear-gradient(180deg,transparent,var(--c2),transparent);opacity:.5}
body.split h1{font-family:'Archivo';font-weight:800;font-size:64px;line-height:1.0;letter-spacing:-.02em;margin-top:18px;color:var(--ink)}
body.split h1 .g{background:linear-gradient(100deg,var(--c1),var(--c2));-webkit-background-clip:text;background-clip:text;color:transparent}
body.split .bullets{margin-top:28px;display:flex;flex-direction:column;gap:14px}
body.split .b{display:flex;align-items:flex-start;gap:13px;font-size:18.5px;color:var(--ink);font-weight:600}
body.split .b .ic{width:27px;height:27px;flex:none;border-radius:8px;background:color-mix(in srgb,var(--c1) 16%,transparent);display:flex;align-items:center;justify-content:center;margin-top:1px}
body.split .b .ic svg{width:15px;height:15px;stroke:var(--c1);fill:none;stroke-width:2.6}
body.split .cta{margin-top:30px}
body.split .media{position:relative}
body.split .media .tint{position:absolute;inset:0;background:linear-gradient(90deg,var(--bg) 0%,color-mix(in srgb,var(--bg) 20%,transparent) 16%,transparent 38%)}
body.split .media .tag{position:absolute;top:34px;right:34px}

/* ---------- BANNER (image top, card bottom) ---------- */
body.banner .media{position:absolute;top:0;left:0;right:0;height:60%}
body.banner .media .tint{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.25),transparent 40%,var(--bg))}
body.banner .media .tag{position:absolute;top:40px;left:46px}
body.banner .card{position:absolute;left:0;right:0;bottom:0;height:46%;padding:0 70px 64px;display:flex;flex-direction:column;justify-content:flex-end;gap:0}
body.banner h1{font-family:'Sora';font-weight:800;font-size:60px;line-height:1.0;letter-spacing:-.02em;margin-top:14px;color:var(--ink)}
body.banner h1 .g{background:linear-gradient(100deg,var(--c1),var(--c2));-webkit-background-clip:text;background-clip:text;color:transparent}
body.banner .sub{margin-top:16px;font-size:24px;line-height:1.4;color:var(--muted);font-weight:500;max-width:840px}
body.banner .pills{margin-top:20px;display:flex;flex-wrap:wrap;gap:10px}
body.banner .pill{display:inline-flex;align-items:center;gap:8px;padding:9px 15px;border-radius:11px;background:color-mix(in srgb,var(--c1) 10%,transparent);border:1px solid color-mix(in srgb,var(--c1) 22%,transparent);font-weight:600;font-size:15px;color:var(--ink)}
body.banner .pill::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--c1)}
body.banner .row{margin-top:26px;display:flex;align-items:center;justify-content:space-between;gap:20px}
"""

_ARROW = '<svg viewBox="0 0 24 24" fill="none" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>'
_CHECK = '<svg viewBox="0 0 24 24"><path d="M5 12.5l4 4 10-11"/></svg>'
_GLOBE = '<svg viewBox="0 0 24 24" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.5 2.5 15 0 18M12 3c-2.5 2.5-2.5 15 0 18"/></svg>'


def _esc(s: str) -> str:
    return _html.escape(s or "", quote=True)


def _root_vars(theme: PosterTheme) -> str:
    return (
        ":root{"
        f"--bg:{theme.bg};--ink:{theme.ink};--muted:{theme.muted};"
        f"--c1:{theme.c1};--c2:{theme.c2};--c3:{theme.c3};"
        "}"
    )


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "•"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _logo(theme: PosterTheme) -> str:
    if theme.logo_data_uri:
        return f'<img src="{theme.logo_data_uri}" alt="" style="height:48px;max-width:230px;object-fit:contain"/>'
    return (
        f'<span class="mark"><span>{_esc(_initials(theme.brand_name))}</span></span>'
        f'<span class="name">{_esc(theme.brand_name)}</span>'
    )


def _site(theme: PosterTheme) -> str:
    if not theme.website:
        return ""
    return f'<span class="site">{_GLOBE}{_esc(theme.website)}</span>'


def _hero(hero: str | None) -> str:
    if hero:
        return f'<img class="heroimg" src="{hero}" alt=""/>'
    return '<div class="herofallback"></div>'


def _headline(copy: LinkedInCopy, em_tag: str) -> str:
    lead = _esc(copy.headline_lead)
    accent = _esc(copy.headline_accent)
    return f"<h1>{lead} <{em_tag}>{accent}</{em_tag}></h1>"


def _cta(copy: LinkedInCopy) -> str:
    if not copy.cta.strip():
        return ""
    return f'<span class="cta">{_esc(copy.cta)}{_ARROW}</span>'


# ---- layouts ----


def _editorial(copy: LinkedInCopy, theme: PosterTheme) -> str:
    return (
        '<div class="scrim"></div><div class="edge"></div>'
        '<div class="frame">'
        f'<div style="display:flex;align-items:center;justify-content:space-between">'
        f'<div class="brand">{_logo(theme)}</div>{_site(theme)}</div>'
        '<div class="copy">'
        f'<span class="eyebrow">{_esc(copy.eyebrow)}</span>'
        f'{_headline(copy, "em")}'
        f'<p class="sub">{_esc(copy.subheadline)}</p>'
        f'{_cta(copy)}</div></div>'
    )


def _split(copy: LinkedInCopy, theme: PosterTheme) -> str:
    bullets = "".join(
        f'<div class="b"><span class="ic">{_CHECK}</span><span>{_esc(b)}</span></div>'
        for b in copy.bullets[:3]
        if b.strip()
    )
    tag = (
        f'<span class="chip tag"><span class="dot"></span>{_esc(copy.eyebrow)}</span>'
        if copy.eyebrow
        else ""
    )
    return (
        '<div class="grid">'
        '<div class="panel">'
        f'<div class="brand">{_logo(theme)}</div>'
        "<div>"
        f'<span class="eyebrow">{_esc(copy.eyebrow)}</span>'
        f'<h1>{_esc(copy.headline_lead)} <span class="g">{_esc(copy.headline_accent)}</span></h1>'
        f'<div class="bullets">{bullets}</div>'
        f"{_cta(copy)}</div>"
        f"{_site(theme)}</div>"
        f'<div class="media">{_hero_for_split()}<div class="tint"></div>{tag}</div>'
        "</div>"
    )


def _hero_for_split() -> str:
    # placeholder replaced in render_html with the actual hero markup
    return "__HERO__"


def _banner(copy: LinkedInCopy, theme: PosterTheme) -> str:
    pills = "".join(
        f'<span class="pill">{_esc(b)}</span>' for b in copy.bullets[:3] if b.strip()
    )
    tag = (
        f'<span class="chip tag"><span class="dot"></span>{_esc(copy.eyebrow)}</span>'
        if copy.eyebrow
        else ""
    )
    return (
        f'<div class="media">{_hero_for_split()}<div class="tint"></div>{tag}</div>'
        '<div class="card">'
        f'<div class="brand" style="margin-bottom:14px">{_logo(theme)}</div>'
        f'<h1>{_esc(copy.headline_lead)} <span class="g">{_esc(copy.headline_accent)}</span></h1>'
        f'<p class="sub">{_esc(copy.subheadline)}</p>'
        f'<div class="pills">{pills}</div>'
        f'<div class="row">{_cta(copy)}{_site(theme)}</div>'
        "</div>"
    )


_LAYOUTS = {"editorial": _editorial, "split": _split, "banner": _banner}


def render_html(
    copy: LinkedInCopy,
    theme: PosterTheme,
    *,
    hero_data_uri: str | None = None,
    width: int = 1200,
    height: int = 1200,
) -> str:
    layout = copy.layout if copy.layout in _LAYOUTS else "editorial"
    css = _CSS.replace("__W__", str(width)).replace("__H__", str(height))
    body_inner = _LAYOUTS[layout](copy, theme)

    # editorial puts the hero as the page background; split/banner embed it in
    # their .media block via the __HERO__ placeholder.
    hero_markup = _hero(hero_data_uri)
    if layout == "editorial":
        body_inner = hero_markup + '<div class="grain"></div>' + body_inner
    else:
        body_inner = body_inner.replace("__HERO__", hero_markup)

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'/>"
        f"<link rel='stylesheet' href='{_FONTS}'/>"
        f"<style>{_root_vars(theme)}{css}</style></head>"
        f"<body class='{layout}'>{body_inner}</body></html>"
    )
