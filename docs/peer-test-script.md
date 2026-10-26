# Peer test: ten-minute walkthrough and feedback form

Purpose: feedback from peers and test users on the early prototype, as the Week 8 checkpoint asks. Run it with classmates from other groups, coworkers who trade, or friends under 35 with an options or margin account. Two or three sessions each by Tuesday evening gives six to nine; the results go on the feedback slide and in the journal of changes.

Keep the session to ten minutes. Do not sell the product. Write down what they say, not what you hoped they would say.

## Before you start (1 minute)

Say: "This is an early prototype of a tool that checks your own trading rules before an order goes to the broker. Sample account, simulated broker. I will drive for the first half, then you drive. I want your reactions, including the negative ones."

Record: date, tester's first name or initials, whether they trade options, margin, or neither, how often they trade (fewer than four times a year, four to twenty, more), which broker apps they use.

## Part 1: you drive (4 minutes)

1. Account page. Read one position explanation aloud. Ask: "Is this the sentence you would want to see about a position?"
2. Rules page. Ask: "Which of these eight would you set on your own account? Which one would you delete?"
3. Check an order, example 1 (buy 40 NVDA, held on position size). Ask: "Do you understand why it was held? Would you believe the number?"
4. Example 2 (sell 8 NVDA inside the minimum hold). Ask: "Have you done this? Would you want to be stopped, or warned?"
5. Example 5 (buy 5 MSFT, passes, confirm). Ask: "Was the stop field a nuisance or a help?"

## Part 2: they drive (4 minutes)

Hand over the keyboard. "Place the trade you most regret from the last year, as closely as you can with these symbols." Watch what they do with the plan fields and whether they read the explanation. Note where they hesitate or ask what something means.

Then show the Journal. Ask: "If you placed a trade at your broker's app that broke one of these rules, would you want it counted against your score?"

## Close (1 minute)

Three questions, record the exact words:

- "What is the one rule you would want enforced that is not here?"
- "Would you pay $15 to $30 a month for this once it connects to your broker? Why or why not?"
- "What would make you stop using it after a month?"

Thank them. Do not argue with the answers.

## Feedback form (one page, filled in by the tester or by you from their words)

| | Question | Answer |
|---|---|---|
| 1 | I understood why each held order was held. (1 strongly disagree to 5 strongly agree) | |
| 2 | The explanation used numbers I would trust. (1 to 5) | |
| 3 | Being asked for a stop before an order is: a help / neutral / a nuisance | |
| 4 | For a sale inside the minimum holding period I would want: a hold / a warning / nothing | |
| 5 | The rule I would set first on my own account: | |
| 6 | The rule I would delete: | |
| 7 | A rule I want that is not here: | |
| 8 | Trades placed at the broker's app should count against my score: yes / no / depends | |
| 9 | Would pay $15 to $30 a month once it connects to my broker: yes / no / maybe, because: | |
| 10 | What would make me stop using it after a month: | |

## Tally (Michael, Tuesday night)

Add one row per session to `docs/peer-test-log.csv` (columns: date, tester, trades_options, trades_margin, frequency, brokers, q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, note). The feedback slide reports: number of sessions, the median of questions 1 and 2, the counts for 3, 4, 8 and 9, the rules named in 5 to 7, and one design change we made or scheduled because of what we heard. The change goes in the resource slide "Feedback and what changed" next to the September 30 and October 14 items.
