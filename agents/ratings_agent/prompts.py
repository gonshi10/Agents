"""Prompt templates used by the ratings agent.

The section headers below (EXECUTIVE SUMMARY, RATING RATIONALE, RISK FACTORS,
INVESTMENT RECOMMENDATION, EXPERT RECOMMENDATION) are parsed by hand in
``RatingsAgent.parse_structured_insights``. Changing a header here REQUIRES
updating that parser in lockstep.
"""

SYSTEM_PROMPT = (
    "You are a senior equity analyst who interprets shifts in Wall Street "
    "sentiment. You explain why analyst consensus and price targets move, what "
    "it signals about a company's prospects, and what an investor should do. "
    "Provide decisive, actionable analysis with clear reasoning. Avoid obvious "
    "statements and do not simply restate the raw numbers."
)

SINGLE_TICKER_TEMPLATE = """
Analyze the change in analyst sentiment for {ticker} (Sector Expert: {expert_type}):

Change type: {change_type}
Recommendation consensus: {rec_before} -> {rec_after}
Analyst breakdown (latest): {rec_breakdown}
Price target (mean): {pt_before} -> {pt_after} ({pt_pct})

Provide comprehensive, structured insights:
1. EXECUTIVE SUMMARY: 2-3 sentence overview of what the shift signals. DO NOT restate the raw numbers.
2. RATING RATIONALE: Likely drivers behind the consensus/price-target move.
3. RISK FACTORS: Key risks to the new sentiment.
4. INVESTMENT RECOMMENDATION: Clear Buy/Hold/Sell with confidence level.
5. EXPERT RECOMMENDATION: Which sector expert should review.

Format:
EXECUTIVE SUMMARY: [strategic insights]
RATING RATIONALE: [content]
RISK FACTORS: [content]
INVESTMENT RECOMMENDATION: [RECOMMENDATION] ([CONFIDENCE]) - [reasoning]
EXPERT RECOMMENDATION: [Expert Type]
"""

BATCH_TEMPLATE_HEADER = """Analyze shifts in analyst sentiment and provide comprehensive, structured insights for each company.

For each company, provide:
1. EXECUTIVE SUMMARY: 2-3 sentence overview of what the shift signals (do not restate raw numbers)
2. RATING RATIONALE: likely drivers behind the consensus/price-target move
3. RISK FACTORS: key risks to the new sentiment
4. INVESTMENT RECOMMENDATION: STRONG BUY / BUY / HOLD / SELL / STRONG SELL + confidence
5. EXPERT RECOMMENDATION: best sector expert type

Format:
TICKER:
EXECUTIVE SUMMARY: ...
RATING RATIONALE: ...
RISK FACTORS: ...
INVESTMENT RECOMMENDATION: ...
EXPERT RECOMMENDATION: ...
"""
