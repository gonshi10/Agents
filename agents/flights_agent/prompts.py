"""Prompt templates used by the flights agent.

The section headers below (DEAL SUMMARY, PRICE CONTEXT, BOOKING TIP) are parsed
by hand in ``FlightsAgent.parse_structured_insights``. Changing a header here
REQUIRES updating that parser in lockstep.
"""

SYSTEM_PROMPT = (
    "You are a savvy travel deals analyst. You judge whether a flight fare is a "
    "genuinely good deal for the route and travel month, and give travelers "
    "decisive, practical advice on whether to book now. Be concise and concrete; "
    "do not simply restate the raw price numbers."
)

SINGLE_ROUTE_TEMPLATE = """
Assess this flight fare:

Route: {origin} -> {destination}
Travel month: {depart_month}{return_note}
Current cheapest fare: {price}
Previous seen fare: {prev_price}
Trigger: {trigger}

Provide structured insights:
1. DEAL SUMMARY: 1-2 sentences on whether this is a good deal and why. Do not restate the raw price.
2. PRICE CONTEXT: How this compares to typical fares for this route/season.
3. BOOKING TIP: Decisive advice (book now / wait) with a short reason.

Format:
DEAL SUMMARY: [content]
PRICE CONTEXT: [content]
BOOKING TIP: [content]
"""

BATCH_TEMPLATE_HEADER = """Assess each flight fare below and say whether it is a good deal worth booking.

For each route, provide:
1. DEAL SUMMARY: 1-2 sentences on whether it is a good deal (do not restate raw prices)
2. PRICE CONTEXT: how it compares to typical fares for that route/season
3. BOOKING TIP: decisive book-now / wait advice with a short reason

Format:
ROUTE:
DEAL SUMMARY: ...
PRICE CONTEXT: ...
BOOKING TIP: ...
"""
