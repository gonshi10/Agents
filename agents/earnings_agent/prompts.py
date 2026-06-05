"""Prompt templates used by the earnings agent."""

SYSTEM_PROMPT = (
    "You are a senior financial analyst specializing in earnings analysis and "
    "strategic insights. You excel at identifying forward-looking guidance, "
    "strategic implications, risk factors, and investment theses. Provide "
    "decisive, actionable recommendations with clear reasoning. Avoid obvious "
    "statements and focus on sophisticated, informative analysis."
)

SINGLE_TICKER_TEMPLATE = """
Analyze earnings results for {ticker} (Sector Expert: {expert_type}):

EPS: Est {eps_est} vs Actual {eps_act}
Revenue: Est {rev_est} vs Actual {rev_act}

News: {news}

Provide comprehensive, structured insights:
1. EXECUTIVE SUMMARY: 2-3 sentence overview of strategic implications and key takeaways. DO NOT restate EPS/revenue numbers.
2. STRATEGIC ANALYSIS: What the results mean strategically.
3. RISK FACTORS: Key risks identified.
4. INVESTMENT RECOMMENDATION: Clear Buy/Hold/Sell with confidence level.
5. EXPERT RECOMMENDATION: Which sector expert should review.

Format:
EXECUTIVE SUMMARY: [strategic insights]
STRATEGIC ANALYSIS: [content]
RISK FACTORS: [content]
INVESTMENT RECOMMENDATION: [RECOMMENDATION] ([CONFIDENCE]) - [reasoning]
EXPERT RECOMMENDATION: [Expert Type]
"""

BATCH_TEMPLATE_HEADER = """Analyze earnings results and provide comprehensive, structured insights for each company.

For each company, provide:
1. EXECUTIVE SUMMARY: 2-3 sentence strategic overview (do not restate raw numbers)
2. STRATEGIC ANALYSIS: implications for competitive position and growth
3. RISK FACTORS: key operational, financial, and market risks
4. INVESTMENT RECOMMENDATION: STRONG BUY / BUY / HOLD / SELL / STRONG SELL + confidence
5. EXPERT RECOMMENDATION: best sector expert type

Format:
TICKER:
EXECUTIVE SUMMARY: ...
STRATEGIC ANALYSIS: ...
RISK FACTORS: ...
INVESTMENT RECOMMENDATION: ...
EXPERT RECOMMENDATION: ...
"""

