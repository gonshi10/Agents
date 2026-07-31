"""Prompt templates used by the earnings agent.

The section headers below (EXECUTIVE SUMMARY, STRATEGIC ANALYSIS, GUIDANCE OUTLOOK,
RISK FACTORS, ANALYST CONCLUSION, INVESTMENT RECOMMENDATION, EXPERT RECOMMENDATION)
are parsed by hand in ``EarningsAgent.parse_structured_insights``. Changing a header
here REQUIRES updating that parser in lockstep.
"""

SYSTEM_PROMPT = (
    "You are a senior financial analyst specializing in earnings analysis and "
    "strategic insights. You excel at identifying forward-looking guidance, "
    "strategic implications, risk factors, and investment theses. Connect results "
    "to sector and competitive context; explain why the quarter matters, not what "
    "the numbers were. Weigh bull and bear interpretations before concluding. Use "
    "provided sell-side consensus and price targets as context — do not restate them "
    "verbatim. Provide decisive, actionable recommendations with clear reasoning. "
    "Avoid obvious statements and focus on sophisticated, informative analysis."
)

SINGLE_TICKER_TEMPLATE = """
Analyze earnings results for {ticker} (Sector Expert: {expert_type}, Industry: {industry}):

EPS: Est {eps_est} vs Actual {eps_act} (surprise: {eps_surprise})
Revenue: Est {rev_est} vs Actual {rev_act} (surprise: {rev_surprise})

Wall Street Context: {market_context}

News Headlines:
{news}

Guidance & Strategic Context: {guidance}

Provide comprehensive, structured insights:
1. EXECUTIVE SUMMARY: 2-3 sentence strategic "so what". DO NOT restate EPS/revenue numbers.
2. STRATEGIC ANALYSIS: Competitive position, growth drivers, sector read-through.
3. GUIDANCE OUTLOOK: Forward view, management tone, what to watch next quarter.
4. RISK FACTORS: Operational, financial, and market risks.
5. ANALYST CONCLUSION: 2-3 sentence synthesized verdict (distinct from the Buy/Hold/Sell label).
6. INVESTMENT RECOMMENDATION: STRONG BUY / BUY / HOLD / SELL / STRONG SELL with confidence.
7. EXPERT RECOMMENDATION: Which sector expert should review.

Format:
EXECUTIVE SUMMARY: [strategic insights]
STRATEGIC ANALYSIS: [content]
GUIDANCE OUTLOOK: [content]
RISK FACTORS: [content]
ANALYST CONCLUSION: [content]
INVESTMENT RECOMMENDATION: [RECOMMENDATION] ([CONFIDENCE]) - [reasoning]
EXPERT RECOMMENDATION: [Expert Type]
"""

BATCH_TEMPLATE_HEADER = """Analyze earnings results and provide comprehensive, structured insights for each company.

For each company, provide:
1. EXECUTIVE SUMMARY: 2-3 sentence strategic overview (do not restate raw numbers)
2. STRATEGIC ANALYSIS: competitive position, growth drivers, sector read-through
3. GUIDANCE OUTLOOK: forward view, management tone, what to watch next quarter
4. RISK FACTORS: key operational, financial, and market risks
5. ANALYST CONCLUSION: 2-3 sentence synthesized verdict (distinct from the recommendation label)
6. INVESTMENT RECOMMENDATION: STRONG BUY / BUY / HOLD / SELL / STRONG SELL + confidence
7. EXPERT RECOMMENDATION: best sector expert type

Format:
TICKER:
EXECUTIVE SUMMARY: ...
STRATEGIC ANALYSIS: ...
GUIDANCE OUTLOOK: ...
RISK FACTORS: ...
ANALYST CONCLUSION: ...
INVESTMENT RECOMMENDATION: ...
EXPERT RECOMMENDATION: ...
"""
