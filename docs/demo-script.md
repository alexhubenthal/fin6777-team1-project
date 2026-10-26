# Live demo script (Hubert, about 90 seconds)

Before class: `streamlit run app.py`, open http://localhost:8501 in the browser (it does not open by itself), then open `Demo controls` and press `Reset demo data`. Keep the deck's screenshots open in case the laptop or the projector fails; the slides show the same screens.

**Account (10 seconds).** "Sample account, $25,000. Two losing closes already today, $234 down. Three positions, each explained in a sentence: what it cost, where it is, where the stop is, how long it has been held. NVDA was bought yesterday and is inside the three-day minimum hold."

**Rules (10 seconds).** "Eight rules. All set by the user, none by us. Four are from our canvas. Three came out of this room on September 30: the minimum holding period, the losing-streak cooldown, and a plan with a stop in place of a strategy template. The last one is from the overtrading research."

**Check an order, example 1: buy 40 NVDA (20 seconds).** "The trader wants 40 more NVDA. Held. Position size: it would be 36 percent of equity against a 10 percent limit. The copilot names the rule, shows the numbers, and says five shares would clear it. It also notes the daily loss limit would trip. No override button; if they want it anyway, they place it at the broker and the journal counts it."

**Example 2: sell 8 NVDA (15 seconds).** "Now they want out of yesterday's NVDA, down 2 percent. Held. Minimum hold is three days and the stop at $179.54 has not been hit, so this is a change of mind, not the plan. If the stop had been hit, the sale would pass; exiting on plan is always allowed."

**Example 4: buy 15 PLTR (10 seconds).** "Nothing breached, but this order would use 81 percent of the daily loss budget. Review: the trader has to tick the box before the confirm button works."

**Example 5: buy 5 MSFT, confirm (15 seconds).** "A sized order with a stop. Every rule clear. Confirm, and it routes to the simulated broker; Alpaca paper trading uses the same adapter. The fill is in the journal and the position is on the Account page with its own explanation."

**Journal (10 seconds).** "Thirty-day adherence: 88 percent. Sixteen fills checked, counting the one we just routed; two of them were placed at the broker's app and imported, both would have been held, so they count as breaks. Three orders held in the window, with about $5,300 of planned risk that never went out."

Hand back to Alex for the stack and the feasibility slide.

If the professor asks about the strategy templates: "Templates are now a label on the trade plan. The rule the copilot enforces is the exit the user stated. That change came from your question on September 30."
