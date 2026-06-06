---
name: format-agent-email
description: Redesign an agent's notification email into a clean, readable, email-client-safe layout by composing the shared common/email/templates.py helpers (inline-styled, table-based). Use when asked to make an agent's email nicer / more readable / better designed, or when building the email for a new agent.
---

# Format an agent's email

Each agent builds its notification HTML inside its own email method
(`create_email_content` for earnings/ratings, `create_digest_email` for flights). To keep every
agent's email **clean, readable, and consistent** — and to honor the repo rule that shared code
lives in `common/`, never copied — restyle by **composing the shared helpers in
`common/email/templates.py`**, not by hand-writing inline HTML in the agent.

## Email-client rules (why the helpers look the way they do)

These are hard constraints, not preferences — they're what Gmail/Outlook actually render:

- **All CSS is inline** (`style="..."` per element). Gmail strips `<head>`/`<style>`, so classes
  and stylesheets silently disappear.
- **Layout uses `<table>`**, never `flex`/`grid` — Outlook renders with the Word engine.
- Web-safe properties only (`background-color`, `border`, `padding`, `border-radius`, `color`,
  `font-size`, `font-weight`); no load-bearing gradients/shadows.
- Single centered column, ~600px wide.
- **Escape every dynamic value** with `et.esc(...)` before interpolation.

⚠️ `agents/earnings_agent/data/email_preview.html` is **not** a usable template — it puts CSS in
`<head>` and uses `display:grid` + gradients, which Gmail strips and Outlook can't render. It's a
look reference only; build with the helpers instead.

## The shared helpers (`common/email/templates.py`)

Import as `from common.email import templates as et`. All return HTML strings; compose them:

- `et.page(title, blocks)` — full centered 600px document; `blocks` is a list of the pieces below.
- `et.header(title, subtitle="")` — accent header bar (the visible heading).
- `et.card(body, title="")` — white rounded card; `body` is raw HTML you've already built.
- `et.section(label, text)` — uppercase label + paragraph; use for AI-insight subsections.
- `et.key_value(label, value)` — inline `label: value` row.
- `et.badge(text, kind)` — colored pill; `kind` is `"up"` (green), `"down"` (red), `"neutral"`.
- `et.footer(text)` — muted, centered fine print (timestamps, attribution).
- `et.esc(text)` — escape dynamic content.

The palette lives as module constants at the top of `templates.py` (`ACCENT`, `BG`, badge colors,
…). **Change the look there once** so every agent updates together. If a layout block is missing,
**add a new function to `templates.py`** — do not inline new HTML in an agent.

## Steps

1. **Find the agent's email builder** — `create_email_content` (earnings `agent.py`, ratings
   `agent.py`) or `create_digest_email` (flights `agent.py`). Note which fields it interpolates.
2. **Map the existing content to blocks:** title → `header`; status/banner → `badge`(s) (let a
   direction/beat-miss field drive `kind`, e.g. `"up"`/`"down"`); recommendation/metric rows →
   `key_value` inside a `card`; AI-insight subsections → `section`(s) inside a `card`; timestamp /
   source line → `footer`. Group related rows into one `card`.
3. **Rebuild the HTML body** as `et.page(title, [ et.header(...), card1, card2, et.footer(...) ])`.
   Wrap **all** dynamic values in `et.esc(...)`. Preserve the existing conditional logic (e.g. only
   append a section when its text is non-empty).
4. **Leave the plain-text branch unchanged.** `EmailSender.send` sends a multipart alternative
   (`common/email/sender.py:25-33`); only the HTML is restyled. Confirm the same fields still feed
   both branches.
5. **Don't touch `parse_structured_insights` or its keys** — this is presentation only. Header/parser
   lockstep is a separate concern owned by the `sync-prompts-parser` skill.

## Verification

- **Helpers + agent import clean:**
  `python -c "from common.email import templates"` and
  `python -c "import agents.<name>.agent"`.
- **Offline smoke test passes:** `python -m agents.<name>.tests.test_agent` (standalone script,
  exits non-zero on failure — not pytest).
- **Eyeball the HTML without sending email:** call the agent's email builder with sample data and
  write the returned HTML to a file, then open it:
  ```python
  from agents.ratings_agent.agent import RatingsAgent  # adjust per agent
  html, _ = RatingsAgent.create_email_content(obj, "AAPL", change_dict, insights_dict)
  open("/tmp/email.html", "w").write(html)
  ```
  Confirm: centered 600px column, accent header, white cards, correctly colored badge, readable
  insight sections, muted footer.
- **No client-unsafe markup leaked in:** grep the generated HTML — it must contain no `<style>`
  block and no `grid`/`flex`.
