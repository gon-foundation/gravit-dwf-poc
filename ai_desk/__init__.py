"""
AI loan desk under observation (synthetic experiment).

A model decides on collateral loan requests (APPROVE or REJECT). Its decision
is executed by the partner's own system, as today. Afterwards the post-trade
observer re-checks every executed decision with the collateral gate (signed,
independently corroborated oracle prices; valuation; concentration; LTV;
allowed and resolved markets) and records CONSISTENT or EXCEPTION, signed,
hash-chained and sealed daily.

Nothing here touches the risk path, and every finding goes to the partner only.
All requests, prices, oracles, keys and the policy are fictitious test data.
"""
