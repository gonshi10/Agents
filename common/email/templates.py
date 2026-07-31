"""Email-client-safe HTML building blocks shared by all agents.

Agents compose these pure functions instead of hand-rolling inline HTML so every
notification email gets the same clean, readable look. The constraints below are
not stylistic preferences — they are what real inboxes (Gmail, Outlook) actually
render:

- **All CSS is inline** (``style="..."`` on each element). Gmail strips ``<head>``
  and ``<style>`` blocks, so classes/stylesheets silently vanish.
- **Layout uses ``<table>``**, never ``flex``/``grid`` — Outlook renders with the
  Word engine and ignores modern layout.
- Web-safe properties only (``background-color``, ``border``, ``padding``,
  ``border-radius``, ``color``, ``font-size``, ``font-weight``). Gradients and
  shadows are avoided as load-bearing styling.
- Single centered column, ~600px wide.
- **Dynamic text must be escaped** with :func:`esc` before interpolation.

These functions only build the HTML body. The plain-text alternative and the
actual sending stay with each agent / :class:`common.email.sender.EmailSender`.
"""

from __future__ import annotations

import html

# ----- palette (single source of truth for the look) -----

ACCENT = "#2c3e50"
BG = "#f4f5f7"
CARD = "#ffffff"
BORDER = "#e3e6ea"
TEXT = "#222222"
MUTED = "#6c757d"

UP_FG, UP_BG = "#0f5132", "#d1e7dd"
DOWN_FG, DOWN_BG = "#842029", "#f8d7da"
NEUTRAL_FG, NEUTRAL_BG = "#383d41", "#e2e3e5"

CALLOUT_BG = "#fff3cd"
CALLOUT_BORDER = "#ffc107"
METRIC_BG = "#f8f9fa"
LINK = "#007bff"

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif"

_BADGE_COLORS = {
    "up": (UP_FG, UP_BG),
    "down": (DOWN_FG, DOWN_BG),
    "neutral": (NEUTRAL_FG, NEUTRAL_BG),
}


def esc(text: object) -> str:
    """Escape dynamic content for safe interpolation into HTML."""
    return html.escape(str(text), quote=False)


def header(title: str, subtitle: str = "") -> str:
    """Accent header bar with a title and optional subtitle."""
    sub = (
        f'<div style="margin:6px 0 0 0;font-size:14px;color:#dfe3e8;">{esc(subtitle)}</div>'
        if subtitle
        else ""
    )
    return (
        f'<div style="background-color:{ACCENT};color:#ffffff;'
        f'padding:24px 28px;border-radius:10px;margin-bottom:20px;">'
        f'<div style="font-size:22px;font-weight:600;">{esc(title)}</div>'
        f"{sub}</div>"
    )


def card(body: str, title: str = "") -> str:
    """White rounded card with a subtle border. ``body`` is raw HTML (already built)."""
    heading = (
        f'<div style="font-size:16px;font-weight:600;color:{ACCENT};'
        f'margin:0 0 12px 0;">{esc(title)}</div>'
        if title
        else ""
    )
    return (
        f'<div style="background-color:{CARD};border:1px solid {BORDER};'
        f'border-radius:10px;padding:20px 22px;margin-bottom:16px;">'
        f"{heading}{body}</div>"
    )


def section(label: str, text: str) -> str:
    """Bold label followed by a paragraph — for AI-insight subsections."""
    return (
        f'<div style="margin:0 0 14px 0;">'
        f'<div style="font-size:13px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.4px;color:{MUTED};margin:0 0 4px 0;">{esc(label)}</div>'
        f'<div style="font-size:15px;line-height:1.6;color:{TEXT};">{esc(text)}</div>'
        f"</div>"
    )


def key_value(label: str, value: str) -> str:
    """Inline ``label: value`` row."""
    return (
        f'<div style="font-size:15px;line-height:1.6;color:{TEXT};margin:0 0 6px 0;">'
        f'<span style="color:{MUTED};">{esc(label)}:</span> '
        f"<strong>{esc(value)}</strong></div>"
    )


def badge(text: str, kind: str = "neutral") -> str:
    """Colored pill. ``kind`` is ``"up"`` (green), ``"down"`` (red), or ``"neutral"`` (grey)."""
    fg, bg = _BADGE_COLORS.get(kind, _BADGE_COLORS["neutral"])
    return (
        f'<span style="display:inline-block;background-color:{bg};color:{fg};'
        f'padding:5px 12px;border-radius:14px;font-size:13px;font-weight:600;'
        f'margin:2px 6px 2px 0;">{esc(text)}</span>'
    )


def badge_row(label: str, badges_html: str) -> str:
    """Uppercase label followed by pre-built badge HTML (badges must not be double-escaped)."""
    if not badges_html:
        return ""
    return (
        f'<div style="margin:0 0 14px 0;">'
        f'<div style="font-size:13px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.4px;color:{MUTED};margin:0 0 4px 0;">{esc(label)}</div>'
        f"<div>{badges_html}</div></div>"
    )


def stat_chip(label: str, value: str, kind: str = "neutral") -> str:
    """Compact inline stat pill for metadata rows (e.g. avg delta, counts)."""
    fg, bg = _BADGE_COLORS.get(kind, _BADGE_COLORS["neutral"])
    return (
        f'<span style="display:inline-block;background-color:{bg};color:{fg};'
        f'padding:4px 10px;border-radius:12px;font-size:12px;font-weight:600;'
        f'margin:0 6px 4px 0;">'
        f'<span style="font-weight:500;">{esc(label)}:</span> {esc(value)}</span>'
    )


def section_heading(text: str) -> str:
    """Muted uppercase zone label between major digest sections."""
    return (
        f'<div style="font-size:12px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.6px;color:{MUTED};margin:4px 0 12px 0;">{esc(text)}</div>'
    )


def momentum_row(
    category: str,
    rising: int,
    new: int,
    falling: int,
    market_wide: int,
    *,
    show_border: bool = True,
) -> str:
    """One category row with human-readable label and colored count chips."""
    chips = (
        stat_chip("Rising", str(rising), "up" if rising else "neutral")
        + stat_chip("New", str(new), "up" if new else "neutral")
        + stat_chip("Falling", str(falling), "down" if falling else "neutral")
        + stat_chip("Market-wide", str(market_wide), "up" if market_wide else "neutral")
    )
    border = f"border-bottom:1px solid {BORDER};" if show_border else ""
    return (
        f'<div style="margin:0 0 12px 0;padding:0 0 12px 0;{border}">'
        f'<div style="font-size:15px;font-weight:600;color:{ACCENT};margin:0 0 8px 0;">'
        f"{esc(category)}</div>{chips}</div>"
    )


def overview_block(title: str, body: str) -> str:
    """Card-wrapped intro block with a callout body (``body`` is raw HTML)."""
    return card(callout(body), title=title)


def link_button(text: str, url: str) -> str:
    """Accent call-to-action button (a styled anchor — buttons aren't email-safe)."""
    return (
        f'<a href="{esc(url)}" style="display:inline-block;background-color:{ACCENT};'
        f'color:#ffffff;text-decoration:none;padding:10px 18px;border-radius:8px;'
        f'font-size:14px;font-weight:600;margin-top:6px;">{esc(text)}</a>'
    )


def metric_tile(
    label: str,
    actual: str,
    estimate: str,
    badge_text: str = "",
    badge_kind: str = "neutral",
    surprise: str = "",
) -> str:
    """Single metric cell: large actual value, label, estimate, optional surprise, beat/miss badge."""
    badge_html = badge(badge_text, badge_kind) if badge_text and badge_text != "—" else ""
    surprise_html = surprise_line(surprise) if surprise else ""
    return (
        f'<div style="background-color:{METRIC_BG};border-radius:8px;padding:14px 12px;'
        f'text-align:center;">'
        f'<div style="font-size:22px;font-weight:700;color:{ACCENT};margin:0 0 4px 0;">'
        f"{esc(actual)}</div>"
        f'<div style="font-size:13px;color:{MUTED};margin:0 0 2px 0;">{esc(label)}</div>'
        f'<div style="font-size:12px;color:{MUTED};margin:0 0 4px 0;">Est: {esc(estimate)}</div>'
        f"{surprise_html}"
        f"{badge_html}"
        f"</div>"
    )


def surprise_line(text: str) -> str:
    """Muted surprise-vs-estimate line under a metric tile."""
    return (
        f'<div style="font-size:12px;color:{MUTED};margin:0 0 8px 0;">'
        f"{esc(text)}</div>"
    )


def metric_row(*tiles: str) -> str:
    """Place metric tiles side-by-side in a table row (email-safe two-column layout)."""
    cells = "".join(
        f'<td width="50%" style="width:50%;padding:0 4px;vertical-align:top;">{tile}</td>'
        for tile in tiles
    )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="width:100%;border-collapse:collapse;margin:0 0 4px 0;">'
        f"<tr>{cells}</tr></table>"
    )


# Backward-compatible alias used by older agent code paths.
metrics_row = metric_row


def news_item(headline: str, url: str) -> str:
    """Bordered news row with a linked headline."""
    return (
        f'<div style="padding:10px 0;border-bottom:1px solid {BORDER};">'
        f'<a href="{esc(url)}" style="color:{LINK};text-decoration:none;font-size:15px;'
        f'line-height:1.5;">{esc(headline)}</a></div>'
    )


def callout(body: str) -> str:
    """Light accent block for grouped content (e.g. AI insight sections)."""
    return (
        f'<div style="background-color:{CALLOUT_BG};border-left:4px solid {CALLOUT_BORDER};'
        f'padding:16px 18px;border-radius:4px;">{body}</div>'
    )


def divider() -> str:
    """Horizontal rule for separating sections inside a card."""
    return f'<div style="border-top:1px solid {BORDER};margin:14px 0;"></div>'


def verdict_block(
    rating: str,
    confidence: str = "",
    expert: str = "",
    conclusion: str = "",
    reasoning: str = "",
    badge_kind: str = "neutral",
) -> str:
    """Structured verdict layout: rating badge, confidence, expert, conclusion, reasoning."""
    fg, bg = _BADGE_COLORS.get(badge_kind, _BADGE_COLORS["neutral"])
    rating_badge = (
        f'<span style="display:inline-block;background-color:{bg};color:{fg};'
        f'padding:8px 16px;border-radius:14px;font-size:16px;font-weight:700;'
        f'margin:0 8px 0 0;">{esc(rating)}</span>'
    )
    confidence_html = badge(confidence, "neutral") if confidence else ""

    top_row = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="width:100%;border-collapse:collapse;">'
        f"<tr><td style=\"padding:0;\">{rating_badge}{confidence_html}</td></tr></table>"
    )

    parts = [top_row]
    if expert:
        parts.append(
            f'<div style="font-size:13px;color:{MUTED};margin:10px 0 0 0;">'
            f"Reviewed by {esc(expert)}</div>"
        )

    show_reasoning = bool(reasoning.strip()) and reasoning.strip() != conclusion.strip()
    if conclusion or show_reasoning:
        parts.append(divider())

    if conclusion:
        parts.append(
            f'<div style="font-size:16px;line-height:1.65;color:{TEXT};margin:0 0 8px 0;">'
            f"{esc(conclusion)}</div>"
        )

    if show_reasoning:
        parts.append(
            f'<div style="font-size:14px;line-height:1.55;color:{MUTED};margin:0;">'
            f"{esc(reasoning)}</div>"
        )

    return "".join(parts)


def footer(text: str) -> str:
    """Muted, centered fine print."""
    return (
        f'<div style="text-align:center;color:{MUTED};font-size:12px;'
        f'margin-top:8px;padding:4px;">{esc(text)}</div>'
    )


def page(title: str, blocks: list[str]) -> str:
    """Wrap ``blocks`` in a full, centered 600px email document.

    ``title`` becomes the ``<title>`` (mostly for clients that show it); use
    :func:`header` inside ``blocks`` for the visible heading.
    """
    inner = "".join(blocks)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        '<head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<title>{esc(title)}</title></head>\n"
        f'<body style="margin:0;padding:0;background-color:{BG};">'
        f'<table role="presentation" align="center" width="600" cellpadding="0" '
        f'cellspacing="0" style="width:600px;max-width:600px;margin:0 auto;">'
        "<tr><td style=\"padding:24px 16px;font-family:" + FONT + ';">'
        f"{inner}"
        "</td></tr></table></body></html>"
    )
