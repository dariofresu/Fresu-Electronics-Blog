#!/usr/bin/env python3
"""Render exact Wix blog copies into post/<slug>/index.html.

Reads the handoff archive (posts.json + rich/<slug>.json) and writes pages that
keep the Ricos document order and text. Site header/footer match the blog.
Images are downloaded at full resolution into assets/images/wix/.

The ~660 MB motherboard-review video is NOT downloaded. The page embeds it from
https://video.wixstatic.com/video/61d609_5e04865093204e7a9e791f19a7f932a1/1080p/mp4/file.mp4
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REMOTE_VIDEO = (
    "https://video.wixstatic.com/video/"
    "61d609_5e04865093204e7a9e791f19a7f932a1/1080p/mp4/file.mp4"
)
WIX_ORIGIN = "https://www.fresuelectronics.com"
BLOG_ORIGIN = "https://blog.fresuelectronics.com"
MAX_BYTES = 95 * 1024 * 1024  # stay under GitHub's 100 MB hard limit

SPOT = (
    "what-is-impedance",
    "pcb-design-review-for-low-emi-motherboard-design",
    "a-field-centric-perspective-on-charge-and-energy-transfer-in-classical-electromagnetism",
)

NOTES = Counter()


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def text_to_html(s: str) -> str:
    return "<br>".join(esc(part) for part in (s or "").split("\n"))


def concrete_color(c):
    if not c:
        return None
    c = str(c).strip()
    if c.lower() == "transparent":
        return None
    if c.startswith("var("):
        found = re.findall(r"#[0-9A-Fa-f]{3,8}", c)
        return found[-1] if found else None
    return c


def rgba(c):
    raw = concrete_color(c)
    if not raw:
        return None
    m = re.fullmatch(r"#([0-9A-Fa-f]{6})", raw)
    if m:
        h = m.group(1)
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4)) + (1.0,)
    m = re.fullmatch(r"#([0-9A-Fa-f]{3})", raw)
    if m:
        h = m.group(1)
        return tuple(int(ch * 2, 16) for ch in h) + (1.0,)
    m = re.fullmatch(
        r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)",
        raw,
    )
    if m:
        a = float(m.group(4)) if m.group(4) is not None else 1.0
        return (float(m.group(1)), float(m.group(2)), float(m.group(3)), a)
    return None


def lum(rgb) -> float:
    r, g, b = rgb[:3]
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def color_styles(color_data) -> list[str]:
    """Preserve highlight colours. Leave Wix's default near-black body text
    unpainted so it inherits the site's light-on-dark type."""
    if not color_data:
        return []
    fg_raw = color_data.get("foreground")
    bg_raw = color_data.get("background")
    fg = rgba(fg_raw) if fg_raw else None
    bg = rgba(bg_raw) if bg_raw else None
    styles = []
    bg_css = concrete_color(bg_raw) if bg and bg[3] > 0.05 else None
    light_bg = bool(bg and bg[3] > 0.05 and lum(bg) > 0.62)
    if bg_css:
        styles.append(f"background-color:{bg_css}")
    use_fg = bool(fg and fg[3] > 0.2 and (light_bg or lum(fg) > 0.35))
    if use_fg:
        styles.append(f"color:{concrete_color(fg_raw)}")
    elif light_bg:
        styles.append("color:#141414")
    elif fg and fg[3] > 0.2 and not light_bg and lum(fg) <= 0.35:
        NOTES["dark_foreground_skipped"] += 1
    return styles


def resolve_href(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if not url:
        return ""
    if url.startswith("/"):
        NOTES["root_relative_rewritten"] += 1
        return WIX_ORIGIN + url
    if url.startswith("#"):
        return url
    if url.startswith(("http://", "https://", "mailto:", "tel:")):
        return url
    if re.match(r"^[\w.-]+\.[A-Za-z]{2,}(/|$)", url):
        NOTES["schemeless_rewritten"] += 1
        return "https://" + url
    return url


def link_attrs(link: dict) -> str:
    link = link or {}
    href = resolve_href(link.get("url") or "")
    if not href and link.get("anchor"):
        href = "#" + link["anchor"]
    if not href:
        return ""
    parts = [f'href="{esc(href)}"']
    target = link.get("target") or ""
    if target == "BLANK":
        parts.append('target="_blank"')
    elif target == "TOP":
        parts.append('target="_top"')
    rel = link.get("rel") or {}
    rel_bits = []
    if rel.get("nofollow"):
        rel_bits.append("nofollow")
    if rel.get("sponsored"):
        rel_bits.append("sponsored")
    if rel.get("noreferrer") or target == "BLANK":
        rel_bits.append("noreferrer")
    if target == "BLANK":
        rel_bits.append("noopener")
    # preserve order, drop dupes
    seen = []
    for bit in rel_bits:
        if bit not in seen:
            seen.append(bit)
    if seen:
        parts.append(f'rel="{" ".join(seen)}"')
    return " ".join(parts)


def render_text(node) -> str:
    td = node.get("textData") or {}
    raw = td.get("text") or ""
    inner = text_to_html(raw)
    styles = []
    link = None
    bold = italic = underline = False
    for dec in td.get("decorations") or []:
        kind = dec.get("type")
        if kind == "BOLD":
            bold = True
        elif kind == "ITALIC":
            italic = True
        elif kind == "UNDERLINE":
            underline = True
        elif kind == "LINK":
            link = (dec.get("linkData") or {}).get("link") or {}
        elif kind == "COLOR":
            styles.extend(color_styles(dec.get("colorData") or {}))
        elif kind == "FONT_SIZE":
            fs = dec.get("fontSizeData") or {}
            unit = {"PX": "px", "EM": "em", "PT": "pt"}.get(fs.get("unit") or "PX", "px")
            if fs.get("value") is not None:
                styles.append(f"font-size:{fs['value']}{unit}")
        else:
            NOTES["decoration:" + str(kind)] += 1
    if styles:
        inner = f'<span style="{";".join(styles)}">{inner}</span>'
    if underline:
        inner = f"<u>{inner}</u>"
    if italic:
        inner = f"<em>{inner}</em>"
    if bold:
        inner = f"<strong>{inner}</strong>"
    if link is not None:
        attrs = link_attrs(link)
        if attrs:
            inner = f"<a {attrs}>{inner}</a>"
    return inner


def inline_text(nodes) -> str:
    parts = []

    def walk(n):
        if n.get("type") == "TEXT":
            parts.append((n.get("textData") or {}).get("text") or "")
        for c in n.get("nodes") or []:
            walk(c)

    for n in nodes or []:
        walk(n)
    return "".join(parts)


def inline_links(nodes) -> tuple:
    found = []

    def walk(n):
        if n.get("type") == "TEXT":
            td = n.get("textData") or {}
            raw = td.get("text") or ""
            for dec in td.get("decorations") or []:
                if dec.get("type") == "LINK":
                    link = (dec.get("linkData") or {}).get("link") or {}
                    href = resolve_href(link.get("url") or "")
                    if not href and link.get("anchor"):
                        href = "#" + link["anchor"]
                    found.append((href, raw))
        for c in n.get("nodes") or []:
            walk(c)

    for n in nodes or []:
        walk(n)
    return tuple(found)


def block_style(data: dict) -> tuple[str, str | None, int]:
    data = data or {}
    align = (data.get("textStyle") or {}).get("textAlignment")
    if align in (None, "AUTO"):
        align = None
    indent = int(data.get("indentation") or 0)
    bits = []
    if align == "JUSTIFY":
        bits.append("text-align:justify")
    elif align == "CENTER":
        bits.append("text-align:center")
    elif align == "RIGHT":
        bits.append("text-align:right")
    elif align == "LEFT":
        bits.append("text-align:left")
    if indent:
        bits.append(f"margin-left:{indent * 2}em")
    style = f' style="{";".join(bits)}"' if bits else ""
    return style, align, indent


def media_name(media_id: str) -> str:
    return media_id.strip().split("/")[-1].split("?")[0]


def image_public(media_id: str) -> str:
    return f"/assets/images/wix/{media_name(media_id)}"


def full_image_url(media_id: str) -> str:
    return "https://static.wixstatic.com/media/" + media_name(media_id)


def product_media_id(url: str) -> str:
    path = urlparse(url).path
    # /media/<id>/v1/fit/...
    m = re.search(r"/media/([^/]+)", path)
    if not m:
        raise ValueError(url)
    return m.group(1)


def yt_id(url: str) -> str | None:
    if not url:
        return None
    m = re.search(r"(?:youtu\.be/|youtube\.com/(?:embed/|watch\?v=|shorts/)|[?&]v=)([\w-]{11})", url)
    return m.group(1) if m else None


def product_dest(url: str) -> str:
    q = parse_qs(urlparse(url).query)
    dest = (q.get("d") or [None])[0]
    return dest or url


def alt_norm(s: str) -> str:
    return (s or "").replace("\r", "").replace("\n", " ")


class Renderer:
    def __init__(self, root: Path):
        self.root = root
        self.assets: dict[str, str] = {}  # url -> dest relative to root

    def need(self, url: str, rel: str):
        prev = self.assets.get(url)
        if prev and prev != rel:
            NOTES["asset_path_conflict"] += 1
        self.assets[url] = rel

    def render_children(self, node) -> str:
        return "".join(self.render_block(c) for c in node.get("nodes") or [])

    def render_block(self, node) -> str:
        t = node.get("type")
        NOTES["node:" + str(t)] += 1
        if t == "PARAGRAPH":
            return self.render_p(node)
        if t == "HEADING":
            return self.render_h(node)
        if t == "BULLETED_LIST":
            return "<ul>\n" + self.render_children(node) + "</ul>\n"
        if t == "ORDERED_LIST":
            start = int((node.get("orderedListData") or {}).get("start") or 1)
            attr = f' start="{start}"' if start != 1 else ""
            return f"<ol{attr}>\n" + self.render_children(node) + "</ol>\n"
        if t == "LIST_ITEM":
            return "<li>\n" + self.render_children(node) + "</li>\n"
        if t == "BLOCKQUOTE":
            return "<blockquote>\n" + self.render_children(node) + "</blockquote>\n"
        if t == "DIVIDER":
            return "<hr>\n"
        if t == "IMAGE":
            return self.render_image(node)
        if t == "BUTTON":
            return self.render_button(node)
        if t == "APP_EMBED":
            return self.render_card(node)
        if t == "VIDEO":
            return self.render_video(node)
        if t == "FILE":
            return self.render_file(node)
        if t == "TEXT":
            return render_text(node)
        if t == "CAPTION":
            return "".join(render_text(c) if c.get("type") == "TEXT" else self.render_block(c) for c in node.get("nodes") or [])
        NOTES["unsupported:" + str(t)] += 1
        return self.render_children(node)

    def render_p(self, node) -> str:
        style, _, _ = block_style(node.get("paragraphData") or {})
        inner = "".join(
            render_text(c) if c.get("type") == "TEXT" else self.render_block(c)
            for c in node.get("nodes") or []
        )
        return f"<p{style}>{inner}</p>\n"

    def render_h(self, node) -> str:
        hd = node.get("headingData") or {}
        level = int(hd.get("level") or 2)
        level = min(max(level, 1), 6)
        style, _, _ = block_style(hd)
        inner = "".join(
            render_text(c) if c.get("type") == "TEXT" else self.render_block(c)
            for c in node.get("nodes") or []
        )
        return f"<h{level}{style}>{inner}</h{level}>\n"

    def render_image(self, node) -> str:
        d = node.get("imageData") or {}
        src = (d.get("image") or {}).get("src") or {}
        media_id = src.get("id") or ""
        if not media_id and src.get("url"):
            media_id = product_media_id(src["url"])
        rel = f"assets/images/wix/{media_name(media_id)}"
        self.need(full_image_url(media_id), rel)
        alt = alt_norm(d.get("altText") or "")
        cap_nodes = [c for c in node.get("nodes") or [] if c.get("type") == "CAPTION"]
        cap_html = "".join(
            render_text(t) if t.get("type") == "TEXT" else self.render_block(t)
            for cap in cap_nodes
            for t in cap.get("nodes") or []
        )
        cd = d.get("containerData") or {}
        width = cd.get("width") or {}
        attrs = []
        style_bits = []
        if "custom" in width and str(width["custom"]).isdigit():
            px = int(width["custom"])
            attrs.append(f'data-wix-width="{px}"')
            style_bits.append(f"max-width:{px}px")
        elif width.get("size") == "SMALL":
            attrs.append('data-wix-width="SMALL"')
            NOTES["image_small_preset"] += 1
        align = cd.get("alignment") or "CENTER"
        if align == "LEFT":
            style_bits.append("margin-left:0;margin-right:auto;text-align:left")
        elif align == "RIGHT":
            style_bits.append("margin-left:auto;margin-right:0;text-align:right")
        style = f' style="{";".join(style_bits)}"' if style_bits else ""
        extra = (" " + " ".join(attrs)) if attrs else ""
        cap = f"<figcaption>{cap_html}</figcaption>" if cap_html else ""
        return (
            f'<figure class="wix-fig"{extra}{style}>'
            f'<img src="/{rel}" alt="{esc(alt)}" loading="lazy">'
            f"{cap}</figure>\n"
        )

    def render_button(self, node) -> str:
        b = node.get("buttonData") or {}
        text = b.get("text") or ""
        link = b.get("link") or {}
        styles = b.get("styles") or {}
        colors = styles.get("colors") or {}
        bg = colors.get("background") or "#116dff"
        radius = (styles.get("border") or {}).get("radius")
        radius_css = f"{int(radius)}px" if isinstance(radius, (int, float)) else "8px"
        if not styles:
            NOTES["button_default_style"] += 1
        css = [
            f"background:{bg}",
            f"border-radius:{radius_css}",
            "color:#ffffff",
        ]
        width = (b.get("containerData") or {}).get("width") or {}
        if "custom" in width and str(width["custom"]).isdigit():
            css.append(f"width:min({int(width['custom'])}px,100%)")
        style = ";".join(css)
        attrs = link_attrs(link)
        if attrs:
            inner = f'<a class="wix-btn" {attrs} style="{style}">{esc(text)}</a>'
        else:
            NOTES["button_without_url"] += 1
            inner = f'<span class="wix-btn" style="{style}">{esc(text)}</span>'
        return f'<p class="wix-btn-wrap">{inner}</p>\n'

    def render_card(self, node) -> str:
        a = node.get("appEmbedData") or {}
        if a.get("type") and a.get("type") != "PRODUCT":
            NOTES["embed:" + a.get("type")] += 1
        name = a.get("name") or ""
        dest = product_dest(a.get("url") or "")
        im = (a.get("image") or {}).get("src") or {}
        url = im.get("url") or ""
        mid = product_media_id(url) if url else ""
        rel = f"assets/images/wix/{media_name(mid)}" if mid else ""
        if mid:
            self.need(full_image_url(mid), rel)
        img = f'<img src="/{rel}" alt="">' if rel else ""
        return (
            f'<aside class="wix-card"><a href="{esc(dest)}">{img}'
            f'<span class="wix-card-name">{esc(name)}</span></a></aside>\n'
        )

    def render_video(self, node) -> str:
        v = node.get("videoData") or {}
        src = (v.get("video") or {}).get("src") or {}
        title = v.get("title") or ""
        thumb = (v.get("thumbnail") or {}).get("src") or {}
        poster = ""
        if thumb.get("id"):
            rel = f"assets/images/wix/{media_name(thumb['id'])}"
            self.need("https://static.wixstatic.com/" + thumb["id"].lstrip("/"), rel)
            poster = f' poster="/{rel}"'
        elif thumb.get("url"):
            poster = f' poster="{esc(thumb["url"])}"'
        if src.get("url"):
            yid = yt_id(src["url"])
            if yid:
                tattr = f' title="{esc(title)}"' if title else ""
                return (
                    f'<div class="wix-embed"><iframe src="https://www.youtube.com/embed/{yid}"'
                    f'{tattr} allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"'
                    f" allowfullscreen loading=\"lazy\"></iframe></div>\n"
                )
            return f'<p><a href="{esc(src["url"])}">{esc(src["url"])}</a></p>\n'
        vid = src.get("id") or ""
        remote = "https://video.wixstatic.com/" + vid.lstrip("/")
        if remote == REMOTE_VIDEO or "61d609_5e04865093204e7a9e791f19a7f932a1" in vid:
            NOTES["remote_video"] += 1
            play = REMOTE_VIDEO
        else:
            # small hosted file — commit it
            stem = vid.split("/")[1] if "/" in vid else media_name(vid)
            rel = f"assets/videos/{stem}.mp4"
            self.need(remote, rel)
            play = "/" + rel
        preload = "none" if play == REMOTE_VIDEO else "metadata"
        return (
            f'<figure class="wix-video"><video controls preload="{preload}"{poster} '
            f'src="{esc(play)}"></video></figure>\n'
        )

    def render_file(self, node) -> str:
        f = node.get("fileData") or {}
        fid = (f.get("src") or {}).get("id") or ""
        name = f.get("name") or fid
        rel = f"assets/files/{media_name(fid)}"
        self.need("https://static.wixstatic.com/ugd/" + fid, rel)
        size = f.get("sizeInKb")
        size_html = f' <span class="wix-filesize">({esc(str(size))} KB)</span>' if size else ""
        return (
            f'<p class="wix-file"><a href="/{rel}">{esc(name)}</a>{size_html}</p>\n'
        )

    def cover(self, doc) -> tuple[str, str]:
        """Return (html, og image public path or remote url)."""
        media = doc.get("media") or {}
        if "wixMedia" in media and (media["wixMedia"].get("image") or {}).get("id"):
            im = media["wixMedia"]["image"]
            rel = f"assets/images/wix/{media_name(im['id'])}"
            url = im.get("url") or full_image_url(im["id"])
            # prefer the canonical full-res media URL
            self.need(full_image_url(im["id"]), rel)
            alt = alt_norm(media.get("altText") or im.get("altText") or "")
            html_bit = (
                f'<figure class="wix-cover"><img src="/{rel}" alt="{esc(alt)}"></figure>\n'
            )
            return html_bit, "/" + rel
        if "embedMedia" in media:
            video = (media["embedMedia"].get("video") or {})
            thumb = (media["embedMedia"].get("thumbnail") or {})
            yid = yt_id(video.get("url") or "")
            og = thumb.get("url") or ""
            if yid:
                rel = f"assets/images/wix/yt-{yid}.jpg"
                if og:
                    self.need(og, rel)
                    og_public = "/" + rel
                else:
                    og_public = og
                html_bit = (
                    f'<div class="wix-embed wix-cover-embed"><iframe '
                    f'src="https://www.youtube.com/embed/{yid}" '
                    f'title="{esc(video.get("url") or "")}" '
                    f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
                    f'allowfullscreen loading="lazy"></iframe></div>\n'
                )
                return html_bit, og_public
        return "", ""


def expected_tree(node_list) -> list:
    out = []
    for n in node_list or []:
        t = n.get("type")
        if t == "PARAGRAPH":
            _, align, indent = block_style(n.get("paragraphData") or {})
            out.append(("p", inline_text(n.get("nodes")), align, indent, inline_links(n.get("nodes"))))
        elif t == "HEADING":
            hd = n.get("headingData") or {}
            _, align, indent = block_style(hd)
            out.append(
                (
                    "h",
                    int(hd.get("level") or 2),
                    inline_text(n.get("nodes")),
                    align,
                    indent,
                    inline_links(n.get("nodes")),
                )
            )
        elif t == "BULLETED_LIST":
            out.append(("ul", [expected_li(c) for c in n.get("nodes") or []]))
        elif t == "ORDERED_LIST":
            start = int((n.get("orderedListData") or {}).get("start") or 1)
            out.append(("ol", start, [expected_li(c) for c in n.get("nodes") or []]))
        elif t == "BLOCKQUOTE":
            out.append(("bq", expected_tree(n.get("nodes"))))
        elif t == "DIVIDER":
            out.append(("hr",))
        elif t == "IMAGE":
            out.append(expected_image(n))
        elif t == "BUTTON":
            b = n.get("buttonData") or {}
            href = resolve_href((b.get("link") or {}).get("url") or "")
            out.append(("btn", b.get("text") or "", href))
        elif t == "APP_EMBED":
            a = n.get("appEmbedData") or {}
            im = ((a.get("image") or {}).get("src") or {}).get("url") or ""
            mid = product_media_id(im) if im else ""
            out.append(("card", a.get("name") or "", product_dest(a.get("url") or ""), media_name(mid) if mid else ""))
        elif t == "VIDEO":
            out.append(expected_video(n))
        elif t == "FILE":
            f = n.get("fileData") or {}
            fid = (f.get("src") or {}).get("id") or ""
            out.append(("file", f.get("name") or "", media_name(fid)))
        elif t == "LIST_ITEM":
            out.append(("li", expected_tree(n.get("nodes"))))
        else:
            out.append(("other", t, expected_tree(n.get("nodes"))))
    return out


def expected_li(n) -> tuple:
    return ("li", expected_tree(n.get("nodes")))


def expected_image(n) -> tuple:
    d = n.get("imageData") or {}
    src = (d.get("image") or {}).get("src") or {}
    media_id = src.get("id") or ""
    caps = [c for c in n.get("nodes") or [] if c.get("type") == "CAPTION"]
    cap_nodes = []
    for c in caps:
        cap_nodes.extend(c.get("nodes") or [])
    width = (d.get("containerData") or {}).get("width") or {}
    if "custom" in width and str(width["custom"]).isdigit():
        w = str(int(width["custom"]))
    elif width.get("size") == "SMALL":
        w = "SMALL"
    else:
        w = ""
    return (
        "img",
        media_name(media_id),
        alt_norm(d.get("altText") or ""),
        inline_text(cap_nodes),
        w,
        inline_links(cap_nodes),
    )


def expected_video(n) -> tuple:
    v = n.get("videoData") or {}
    src = (v.get("video") or {}).get("src") or {}
    if src.get("url"):
        yid = yt_id(src["url"])
        if yid:
            return ("yt", yid)
        return ("linkvideo", src["url"])
    vid = src.get("id") or ""
    remote = "https://video.wixstatic.com/" + vid.lstrip("/")
    if "61d609_5e04865093204e7a9e791f19a7f932a1" in vid:
        return ("video", REMOTE_VIDEO)
    stem = vid.split("/")[1] if "/" in vid else media_name(vid)
    return ("video", f"/assets/videos/{stem}.mp4")


class BodyParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = [{"kind": "root", "kids": [], "tag": "root"}]
        self.pushed = []

    def _top(self):
        return self.stack[-1]

    def _text_target(self):
        for n in reversed(self.stack):
            if n.get("collect"):
                return n
        return None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        classes = set(cls.split())
        if tag == "br":
            t = self._text_target()
            if t is not None:
                t["text"].append("\n")
            return
        if tag == "hr":
            self._top()["kids"].append(("hr",))
            return
        if tag == "img":
            for n in reversed(self.stack):
                if n["kind"] in ("fig", "card", "videofig"):
                    n["src"] = a.get("src", "")
                    n["alt"] = a.get("alt", "")
                    break
            return
        if tag == "video":
            for n in reversed(self.stack):
                if n["kind"] == "videofig":
                    n["src"] = a.get("src", "")
                    break
            return
        if tag == "iframe":
            for n in reversed(self.stack):
                if n["kind"] == "yt":
                    n["src"] = a.get("src", "")
                    break
            return
        if tag == "p" and "wix-btn-wrap" in classes:
            self._push("btn", "p", collect=True)
            return
        if tag == "p" and "wix-file" in classes:
            self._push("file", "p", collect=False)
            return
        if tag == "p":
            align, indent = _style_align(a.get("style", ""))
            self._push("p", "p", collect=True, align=align, indent=indent, links=[])
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            align, indent = _style_align(a.get("style", ""))
            self._push("h", tag, collect=True, level=int(tag[1]), align=align, indent=indent, links=[])
            return
        if tag == "ul":
            self._push("ul", "ul", kids=[])
            return
        if tag == "ol":
            self._push("ol", "ol", kids=[], start=int(a.get("start") or 1))
            return
        if tag == "li":
            self._push("li", "li", kids=[])
            return
        if tag == "blockquote":
            self._push("bq", "blockquote", kids=[])
            return
        if tag == "figure" and "wix-video" in classes:
            self._push("videofig", "figure", src="")
            return
        if tag == "figure":
            self._push(
                "fig",
                "figure",
                src="",
                alt="",
                caption="",
                links=[],
                width=a.get("data-wix-width", ""),
            )
            return
        if tag == "figcaption":
            self._push("cap", "figcaption", collect=True, links=[])
            return
        if tag == "div" and "wix-embed" in classes:
            self._push("yt", "div", src="")
            return
        if tag == "aside" and "wix-card" in classes:
            self._push("card", "aside", src="", name="", href="")
            return
        if tag == "a":
            self._push("a", "a", collect=True, href=a.get("href", ""))
            return
        # span, strong, em, u: transparent

    def handle_endtag(self, tag):
        if not self.pushed or self.pushed[-1] != tag:
            return
        self.pushed.pop()
        node = self.stack.pop()
        parent = self._top()
        parent["kids"].append(self._finalize(node, parent))

    def handle_data(self, data):
        t = self._text_target()
        if t is not None:
            t["text"].append(data)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def _push(self, kind, tag, **kw):
        node = {"kind": kind, "tag": tag, "kids": [], "text": []}
        node.update(kw)
        self.stack.append(node)
        self.pushed.append(tag)

    def _finalize(self, node, parent):
        kind = node["kind"]
        text = "".join(node.get("text") or [])
        if kind == "a":
            if parent["kind"] in ("p", "h", "cap"):
                parent.setdefault("text_parts", [])
                # text is also held on the anchor; bubble into parent text buffer
                parent["text"].append(text)
                parent.setdefault("links", []).append((node.get("href") or "", text))
            elif parent["kind"] == "btn":
                parent["href"] = node.get("href") or ""
                parent["text"].append(text)
            elif parent["kind"] == "card":
                parent["href"] = node.get("href") or ""
                parent["name"] = text
            elif parent["kind"] == "file":
                parent["href"] = node.get("href") or ""
                parent["name"] = text
            return ("a-skip",)
        if kind == "cap":
            if parent["kind"] == "fig":
                parent["caption"] = text
                parent["links"] = tuple(node.get("links") or [])
            return ("cap-skip",)
        if kind == "p":
            return ("p", text, node.get("align"), node.get("indent"), tuple(node.get("links") or []))
        if kind == "h":
            return ("h", node["level"], text, node.get("align"), node.get("indent"), tuple(node.get("links") or []))
        if kind == "ul":
            return ("ul", [k for k in node["kids"] if k[0] != "a-skip"])
        if kind == "ol":
            return ("ol", node.get("start") or 1, [k for k in node["kids"] if k[0] != "a-skip"])
        if kind == "li":
            return ("li", [k for k in node["kids"] if not (isinstance(k, tuple) and k and str(k[0]).endswith("-skip"))])
        if kind == "bq":
            return ("bq", [k for k in node["kids"] if not (isinstance(k, tuple) and k and str(k[0]).endswith("-skip"))])
        if kind == "fig":
            src = node.get("src") or ""
            base = src.split("/")[-1].split("?")[0]
            return ("img", base, node.get("alt") or "", node.get("caption") or "", node.get("width") or "", tuple(node.get("links") or []))
        if kind == "btn":
            return ("btn", text, node.get("href") or "")
        if kind == "card":
            src = node.get("src") or ""
            base = src.split("/")[-1].split("?")[0]
            return ("card", node.get("name") or "", node.get("href") or "", base)
        if kind == "videofig":
            return ("video", node.get("src") or "")
        if kind == "yt":
            return ("yt", yt_id(node.get("src") or "") or "")
        if kind == "file":
            href = node.get("href") or ""
            base = href.split("/")[-1].split("?")[0]
            return ("file", node.get("name") or "", base)
        return ("other", kind, node.get("kids"))

    def result(self):
        kids = self.stack[0]["kids"]
        return [k for k in kids if not (isinstance(k, tuple) and k and str(k[0]).endswith("-skip"))]


def _style_align(style: str):
    align = None
    if "text-align:justify" in style:
        align = "JUSTIFY"
    elif "text-align:center" in style:
        align = "CENTER"
    elif "text-align:right" in style:
        align = "RIGHT"
    elif "text-align:left" in style:
        align = "LEFT"
    indent = 0
    m = re.search(r"margin-left:(\d+)em", style or "")
    if m:
        indent = int(m.group(1)) // 2
    return align, indent


def first_diff(a, b, path="$"):
    if type(a) is not type(b) and not (isinstance(a, tuple) and isinstance(b, tuple)):
        return f"{path}: type {type(a).__name__} vs {type(b).__name__}\n  A={a!r:.400}\n  B={b!r:.400}"
    if isinstance(a, list):
        if len(a) != len(b):
            return (
                f"{path}: length {len(a)} vs {len(b)}\n"
                f"  A0={a[len(b)]!r:.300}" if len(a) > len(b) else
                f"{path}: length {len(a)} vs {len(b)}\n  B0={b[len(a)]!r:.300}"
            )
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    if isinstance(a, tuple):
        if len(a) != len(b):
            return f"{path}: tuple len {len(a)} vs {len(b)}\n  A={a!r:.400}\n  B={b!r:.400}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_diff(x, y, f"{path}/{a[0]}:{i}")
            if d:
                return d
        return None
    if a != b:
        return f"{path}:\n  A={a!r:.500}\n  B={b!r:.500}"
    return None


def page_html(post, body, cover_html, og_path) -> str:
    title = post["title"]
    slug = post["slug"]
    date = post["first_published"][:10]
    excerpt = (post.get("excerpt") or "").strip()
    desc = excerpt or title
    url = f"{BLOG_ORIGIN}/post/{slug}/"
    og_image = ""
    if og_path:
        if og_path.startswith("http"):
            og_abs = og_path
        else:
            og_abs = BLOG_ORIGIN + og_path
        og_image = f'  <meta property="og:image" content="{esc(og_abs)}">\n'
    cats = post.get("categories") or []
    tags = post.get("tags") or []
    tax = ""
    bits = []
    if cats:
        bits.append("Categories: " + ", ".join(cats))
    if tags:
        bits.append("Tags: " + ", ".join(tags))
    if bits:
        tax = f'  <p class="taxo">{esc(" · ".join(bits))}</p>\n'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(title)} — Fresu Electronics</title>
  <meta name="description" content="{esc(desc)}">
  <link rel="canonical" href="{esc(url)}">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(desc)}">
  <meta property="og:url" content="{esc(url)}">
{og_image}  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Poppins:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,400;1,700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/assets/wix-exact.css">
</head>
<body>
<header>
  <div class="site-header">
    <a href="https://www.fresuelectronics.com">
      <img src="https://raw.githubusercontent.com/dariofresu/Fresu-Electronics-Blog/main/assets/logo.png" alt="Fresu Electronics">
    </a>
    <nav class="header-nav">
      <a href="{BLOG_ORIGIN}/">Blog</a>
      <a href="{BLOG_ORIGIN}/tools/">Tools</a>
      <a href="https://www.fresuelectronics.com/trainings">Courses</a>
      <a href="https://www.fresuelectronics.com/about">About</a>
      <a href="https://www.fresuelectronics.com/emc-audit" class="header-cta">Book EMC Audit</a>
    </nav>
  </div>
</header>
<article class="post">
  <p class="crumb"><a href="{BLOG_ORIGIN}/">Blog</a> · <a href="{BLOG_ORIGIN}/#wix-archive">Original posts</a></p>
  <header class="post-head">
    <h1>{esc(title)}</h1>
    <p class="meta"><time datetime="{esc(date)}">{esc(date)}</time> · <a href="{esc(post['url'])}">Original on Wix</a></p>
{tax}  </header>
  {cover_html}<div class="wix-body" id="wix-body">
{body}</div><!-- /wix-body -->
</article>
<footer>
  <div class="site-footer">
    <span>© 2026 Fresu Electronics SRL</span>
    <span><a href="https://www.fresuelectronics.com">fresuelectronics.com</a> · <a href="https://www.fresuelectronics.com/free-tool-1">Free Stackup Tool</a></span>
  </div>
</footer>
</body>
</html>
"""


CSS = r"""*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #0a0a0a;
  --surface: #111111;
  --surface-2: #181818;
  --border: #242424;
  --fg: #ffffff;
  --label: #a0aab8;
  --accent: #00FF94;
  --accent-dim: rgba(0, 255, 148, 0.10);
  --accent-hover: #00e085;
}
body {
  background: var(--bg);
  color: #ffffff;
  font-family: 'Poppins', sans-serif;
  font-size: 17px;
  line-height: 1.75;
  min-height: 100vh;
}
body::before {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 1000;
  opacity: 0.2;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
}
header { border-bottom: 1px solid var(--border); }
.site-header {
  max-width: 1100px;
  margin: 0 auto;
  padding: 18px 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.site-header img { height: 44px; width: auto; display: block; }
.header-nav { display: flex; align-items: center; gap: 28px; }
.header-nav a {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #ffffff;
  text-decoration: none;
  opacity: 0.6;
}
.header-nav a:hover { opacity: 1; }
.header-cta {
  opacity: 1 !important;
  background: var(--accent);
  color: #0a0a0a !important;
  padding: 9px 20px;
  border-radius: 3px;
}
.header-cta:hover { background: var(--accent-hover) !important; }
.post { max-width: 760px; margin: 0 auto; padding: 48px 24px 96px; }
.crumb { font-size: 12px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--label); margin-bottom: 28px; }
.crumb a { color: var(--label); text-decoration: none; }
.crumb a:hover { color: var(--accent); }
.post-head h1 {
  font-size: clamp(30px, 4vw, 44px);
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.15;
  color: #ffffff;
  margin: 0 0 14px;
}
.meta { color: var(--label); font-size: 13px; margin-bottom: 8px; }
.meta a { color: var(--accent); text-decoration: none; }
.taxo { color: var(--label); font-size: 13px; margin-bottom: 22px; }
.wix-cover { margin: 22px 0 8px; }
.wix-cover img, .wix-body img, .wix-body video { max-width: 100%; height: auto; }
.wix-body { margin-top: 8px; }
.wix-body p { margin: 0.75em 0; }
.wix-body h1, .wix-body h2, .wix-body h3, .wix-body h4, .wix-body h5, .wix-body h6 {
  color: #ffffff;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.02em;
  margin: 1.35em 0 0.5em;
}
.wix-body h1 { font-size: 2rem; }
.wix-body h2 { font-size: 1.6rem; }
.wix-body h3 { font-size: 1.3rem; }
.wix-body h4 { font-size: 1.12rem; }
.wix-body h5, .wix-body h6 { font-size: 1rem; }
.wix-body a { color: #8ec5ff; text-decoration: underline; text-underline-offset: 2px; }
.wix-body strong { font-weight: 700; }
.wix-body em { font-style: italic; }
.wix-body u { text-decoration: underline; }
.wix-body ul, .wix-body ol { margin: 0.7em 0 0.7em 1.3em; padding: 0; }
.wix-body li { margin: 0.28em 0; }
.wix-body li > p { margin: 0.2em 0; }
.wix-body blockquote {
  border-left: 4px solid #116dff;
  margin: 1.2em 0;
  padding: 0.15em 0 0.15em 1em;
  color: #e7eef7;
}
.wix-body hr { border: 0; border-top: 1px solid #3a3a3a; margin: 1.8em 0; }
.wix-body figure { margin: 1.4em auto; text-align: center; }
.wix-body figcaption { color: #a0aab8; font-size: 0.92rem; line-height: 1.5; margin-top: 0.45em; }
.wix-body figure[data-wix-width="SMALL"] { max-width: 300px; }
.wix-btn-wrap { text-align: center; margin: 1.3em 0; }
a.wix-btn, span.wix-btn {
  display: inline-block;
  color: #ffffff !important;
  text-decoration: none !important;
  font-weight: 600;
  font-size: 16px;
  line-height: 1.35;
  padding: 12px 22px;
  border: 0;
}
.wix-card { margin: 1.2em 0; border: 1px solid var(--border); background: var(--surface); border-radius: 8px; overflow: hidden; }
.wix-card a {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 12px;
  color: #ffffff !important;
  text-decoration: none !important;
}
.wix-card a:hover { color: var(--accent) !important; }
.wix-card img { width: 96px; height: auto; flex: 0 0 96px; background: #fff; }
.wix-card-name { font-weight: 600; font-size: 16px; line-height: 1.35; }
.wix-embed { position: relative; width: 100%; padding-top: 56.25%; margin: 1.2em 0; background: #000; }
.wix-embed iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }
.wix-video video { width: 100%; background: #000; }
.wix-file { margin: 1em 0; }
.wix-filesize { color: var(--label); font-size: 0.9em; }
footer { border-top: 1px solid var(--border); }
.site-footer {
  max-width: 1100px;
  margin: 0 auto;
  padding: 28px 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  color: #ffffff;
  opacity: 0.5;
  flex-wrap: wrap;
  gap: 12px;
}
.site-footer a { color: var(--accent); text-decoration: none; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (max-width: 760px) {
  .site-header, .site-footer { padding-left: 20px; padding-right: 20px; }
  .header-nav a:not(.header-cta) { display: none; }
  .post { padding: 32px 20px 72px; }
}
"""

ARCHIVE_CSS = """
    .wix-archive { margin-top: 72px; }
    .wix-archive h2 { font-size: 28px; font-weight: 800; letter-spacing: -0.02em; color: #fff; margin-bottom: 8px; }
    .wix-archive .archive-note { color: var(--label); font-size: 14px; line-height: 1.6; margin-bottom: 20px; max-width: 680px; }
    .archive-list { list-style: none; border-top: 1px solid var(--border); }
    .archive-list li { border-bottom: 1px solid var(--border); }
    .archive-list a { display: flex; gap: 18px; align-items: baseline; padding: 12px 2px; text-decoration: none; color: #fff; }
    .archive-list a:hover .archive-title { color: var(--accent); }
    .archive-date { flex: 0 0 108px; color: var(--label); font-size: 13px; font-variant-numeric: tabular-nums; }
    .archive-title { font-size: 15px; font-weight: 500; line-height: 1.4; }
    @media (max-width: 760px) {
      .archive-list a { flex-direction: column; gap: 2px; }
      .archive-date { flex-basis: auto; }
    }
"""


def archive_section(posts) -> str:
    rows = []
    ordered = sorted(posts, key=lambda p: p["first_published"], reverse=True)
    for p in ordered:
        date = p["first_published"][:10]
        rows.append(
            f'    <li><a href="./post/{esc(p["slug"])}/">'
            f'<span class="archive-date">{esc(date)}</span>'
            f'<span class="archive-title">{esc(p["title"])}</span></a></li>'
        )
    inner = "\n".join(rows)
    return (
        '<section class="wix-archive" id="wix-archive">\n'
        "  <h2>Original posts</h2>\n"
        '  <p class="archive-note">Exact copies of the 89 English posts from the Wix blog, '
        "with the original text, figures, captions, and order. Edited posts above are unchanged.</p>\n"
        f'  <ul class="archive-list">\n{inner}\n  </ul>\n'
        "</section>\n"
    )


def patch_index(root: Path, section: str):
    path = root / "index.html"
    text = path.read_text(encoding="utf-8")
    css_block = "\n    /* WIX-ARCHIVE-LIST */" + ARCHIVE_CSS + "    /* /WIX-ARCHIVE-LIST */\n"
    if "/* WIX-ARCHIVE-LIST */" in text:
        text = re.sub(
            r"\n    /\* WIX-ARCHIVE-LIST \*/.*?/\* /WIX-ARCHIVE-LIST \*/\n",
            css_block,
            text,
            count=1,
            flags=re.S,
        )
    else:
        needle = "  </style>"
        if needle not in text:
            raise SystemExit("index.html: style close not found")
        text = text.replace(needle, css_block + needle, 1)
    html_block = "\n<!-- WIX-ARCHIVE-LIST -->\n" + section + "<!-- /WIX-ARCHIVE-LIST -->\n"
    if "<!-- WIX-ARCHIVE-LIST -->" in text:
        text = re.sub(
            r"\n<!-- WIX-ARCHIVE-LIST -->.*?<!-- /WIX-ARCHIVE-LIST -->\n",
            html_block,
            text,
            count=1,
            flags=re.S,
        )
    else:
        if "</main>" not in text:
            raise SystemExit("index.html: </main> not found")
        text = text.replace("</main>", html_block + "</main>", 1)
    path.write_text(text, encoding="utf-8")


def looks_valid(path: Path) -> bool:
    data = path.read_bytes()[:32]
    if not data or data.lstrip().startswith(b"<") or data.lstrip().startswith(b"{"):
        return False
    if path.suffix.lower() == ".pdf":
        return data.startswith(b"%PDF")
    if path.suffix.lower() == ".mp4":
        return b"ftyp" in data or True
    if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        return (
            data.startswith(b"\x89PNG")
            or data.startswith(b"\xff\xd8")
            or data.startswith(b"GIF8")
            or data.startswith(b"RIFF")
        )
    return True


def download_one(url: str, dest: Path) -> tuple[str, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0 and looks_valid(dest):
        return url, "cached"
    tmp = dest.with_suffix(dest.suffix + ".part")
    if tmp.exists():
        tmp.unlink()
    cmd = [
        "curl", "-fsSL", "--retry", "4", "--retry-delay", "1",
        "--connect-timeout", "20", "--max-time", "180",
        "-A", "Mozilla/5.0",
        "-o", str(tmp), url,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        if tmp.exists():
            tmp.unlink()
        # youtube maxres fallback
        if "maxresdefault" in url:
            alt = url.replace("maxresdefault", "hqdefault")
            return download_one(alt, dest)
        err = (r.stderr or "").strip().splitlines()
        return url, "FAIL " + (err[-1] if err else f"exit {r.returncode}")
    if tmp.stat().st_size > MAX_BYTES:
        tmp.unlink()
        return url, f"FAIL too large ({tmp.stat().st_size} bytes)"
    os.replace(tmp, dest)
    if not looks_valid(dest):
        dest.unlink(missing_ok=True)
        return url, "FAIL invalid file signature"
    return url, "ok"


def extract_body(page: str) -> str:
    start_marker = '<div class="wix-body" id="wix-body">'
    end_marker = "</div><!-- /wix-body -->"
    start = page.index(start_marker) + len(start_marker)
    end = page.index(end_marker, start)
    return page[start:end]


def verify_page(page: str, rich_nodes) -> str | None:
    body = extract_body(page)
    parser = BodyParser()
    parser.feed(body)
    parser.close()
    got = parser.result()
    exp = expected_tree(rich_nodes)
    return first_diff(exp, got)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--handoff", type=Path, default=Path("/tmp/wix-handoff"))
    ap.add_argument("--root", type=Path, default=Path("/workspace"))
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    handoff = args.handoff
    root = args.root
    posts = json.loads((handoff / "posts.json").read_text(encoding="utf-8"))
    if len(posts) != 89:
        raise SystemExit(f"expected 89 posts, found {len(posts)}")
    langs = {p.get("language") for p in posts}
    if langs != {"en"}:
        raise SystemExit(f"expected English only, found {langs}")

    # reset note counter across resolve_href calls that happen twice (render + expected)
    # We'll snapshot notes after render, then expected_tree calls resolve_href again.
    renderer = Renderer(root)
    rendered = []
    for post in posts:
        slug = post["slug"]
        doc = json.loads((handoff / "rich" / f"{slug}.json").read_text(encoding="utf-8"))
        nodes = (doc.get("richContent") or {}).get("nodes") or []
        body = renderer.render_children({"nodes": nodes})
        cover_html, og = renderer.cover(doc)
        page = page_html(post, body, cover_html, og)
        rendered.append((post, doc, nodes, page))

    print(f"pages built: {len(rendered)}; assets to fetch: {len(renderer.assets)}", flush=True)
    jobs = []
    for url, rel in renderer.assets.items():
        dest = root / rel
        jobs.append((url, dest))

    fails = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(download_one, url, dest): url for url, dest in jobs}
        for fut in as_completed(futs):
            url, status = fut.result()
            done += 1
            if status.startswith("FAIL"):
                fails.append((url, status))
                print(f"FAIL {status} {url}", flush=True)
            if done % 40 == 0 or done == len(jobs):
                print(f"downloaded {done}/{len(jobs)}", flush=True)
    if fails:
        print(f"{len(fails)} downloads failed", file=sys.stderr)
        for url, status in fails:
            print(status, url, file=sys.stderr)
        raise SystemExit(1)

    # size guard
    big = []
    total = 0
    nfiles = 0
    for _, rel in renderer.assets.items():
        p = root / rel
        sz = p.stat().st_size
        total += sz
        nfiles += 1
        if sz >= 50 * 1024 * 1024:
            big.append((sz, rel))
        if sz >= 100 * 1024 * 1024:
            raise SystemExit(f"file over GitHub limit: {rel} {sz}")

    (root / "assets" / "wix-exact.css").write_text(CSS, encoding="utf-8")
    mismatches = []
    for post, doc, nodes, page in rendered:
        # second pass of resolve_href bumps counters; that's ok, we divide later? 
        err = verify_page(page, nodes)
        if err:
            mismatches.append((post["slug"], err))
        out = root / "post" / post["slug"] / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")
        # remote-only check
        if "static.wixstatic.com" in page:
            mismatches.append((post["slug"], "page still references static.wixstatic.com"))
        for m in re.findall(r"https://video\.wixstatic\.com/[^\"'\s]+", page):
            if m != REMOTE_VIDEO:
                mismatches.append((post["slug"], "unexpected remote video " + m))

    if mismatches:
        for slug, err in mismatches[:12]:
            print(f"\nMISMATCH {slug}\n{err}", file=sys.stderr)
        raise SystemExit(f"{len(mismatches)} pages failed verification")

    patch_index(root, archive_section(posts))

    # referenced files exist
    missing = []
    for post, doc, nodes, page in rendered:
        for src in re.findall(r'(?:src|href)="(/assets/[^"]+)"', page):
            if not (root / src.lstrip("/")).exists():
                missing.append((post["slug"], src))
    if missing:
        for item in missing[:20]:
            print("missing", item, file=sys.stderr)
        raise SystemExit(f"{len(missing)} missing local assets")

    print("\nSPOT CHECKS")
    for slug in SPOT:
        post, doc, nodes, page = next(x for x in rendered if x[0]["slug"] == slug)
        body = extract_body(page)
        parser = BodyParser()
        parser.feed(body)
        got = parser.result()
        exp = expected_tree(nodes)
        err = first_diff(exp, got)
        types = Counter(n.get("type") for n in nodes)
        imgs = len(re.findall(r"<img ", body))
        print(f"  {slug}: {'OK' if not err else 'FAIL'} top_nodes={len(nodes)} types={dict(types)} body_imgs={imgs} html_bytes={len(page)}")
        if err:
            print(err)

    print("\nNOTES")
    for k, v in sorted(NOTES.items()):
        print(f"  {k}: {v}")
    print(f"\nassets: {nfiles} files, {total} bytes ({total/1024/1024:.1f} MiB)")
    if big:
        print("over 50 MiB:", big)
    print(f"posts: {len(rendered)}")
    # counters were incremented by render AND by expected_tree inside verify (and spot).
    # root_relative and schemeless run in render_text/link_attrs AND inline_links.
    print("remote video kept:", REMOTE_VIDEO)


if __name__ == "__main__":
    main()
