"""Prompt templates used by the techstack agent.

The section headers below (SECTOR READ, INVESTMENT VIEW, CONFIDENCE,
EXPERT RECOMMENDATION) are parsed by hand in ``TechstackAgent.parse_structured_insights``.
Changing a header here REQUIRES updating that parser in lockstep.
"""

SYSTEM_PROMPT = (
    "You are a senior technology investment analyst who reads enterprise engineering "
    "hiring patterns as leading indicators. You write as a category specialist — "
    "Data Infrastructure Analyst, Cloud & DevOps Specialist, Cybersecurity Specialist, "
    "etc. — depending on the technology domain. Focus on products and vendors, not "
    "programming languages. Be concrete and mechanism-driven: explain WHY the hiring "
    "pattern matters for the vendor's revenue or competitive position. "
    "Keep each section to 1-2 sentences. Never restate employer name lists verbatim — "
    "interpret the pattern (e.g. 'Financials-led adoption suggests…'). "
    "Avoid generic advice and obvious statements."
)

BATCH_TEMPLATE_HEADER = """Analyze each trending technology signal below and return a concise investment view.

Ignore programming languages entirely. Focus on the technology product and the company behind it.
Do NOT list employer names — interpret adoption patterns and sector mix instead.

For each technology, provide:
1. SECTOR READ: 2 sentences max — vendor, public ticker if listed, and why this hiring pattern matters.
2. INVESTMENT VIEW: BUY / WATCH / AVOID plus one-sentence actionable thesis tied to the vendor.
3. CONFIDENCE: LOW / MEDIUM / HIGH and one short reason.
4. EXPERT RECOMMENDATION: [Category Expert Type] — one line naming the specialist persona.

Format:
TECHNOLOGY: <name>
SECTOR READ: ...
INVESTMENT VIEW: ...
CONFIDENCE: ...
EXPERT RECOMMENDATION: ...
"""

SINGLE_TECHNOLOGY_TEMPLATE = """Analyze this technology adoption signal:

TECHNOLOGY: {technology}
CATEGORY: {category}
SECTOR EXPERT: {expert_type}
ADOPTER SECTORS: {adopter_sectors}
RISING AT: {rising}
NEW AT: {new}
FALLING AT: {falling}
AVG SHARE DELTA: {avg_delta}
MARKET-WIDE: {market_wide}

Provide structured insights (1-2 sentences per section, do NOT restate employer lists):
1. SECTOR READ: vendor, ticker if listed, why this hiring pattern matters.
2. INVESTMENT VIEW: BUY / WATCH / AVOID plus one-sentence thesis.
3. CONFIDENCE: LOW / MEDIUM / HIGH and one short reason.
4. EXPERT RECOMMENDATION: [Category Expert Type]

Format:
SECTOR READ: ...
INVESTMENT VIEW: ...
CONFIDENCE: ...
EXPERT RECOMMENDATION: ...
"""

MARKET_OVERVIEW_TEMPLATE = """Write a 2-3 sentence market overview for this month's enterprise tech hiring trends.

Category momentum:
{category_summary}

Top signals:
{top_signals}

Focus on cross-category themes, market-wide shifts, and what an investor should watch this month.
Do not list individual employer names. Return only the overview text — no headers or labels.
"""
