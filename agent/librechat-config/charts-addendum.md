# Chart rules (not active)

These were part of the agent's instructions while it ran on Claude, which can draw charts in the chat
(LibreChat "Artifacts"). A small local model can't do this reliably, so they are switched off.
To use them with a stronger model: paste the block below into the instructions just before "## How to answer",
and add `artifacts: default` to the model spec.

```
          ## Charts
          When an answer compares groups, ranks things, or shows a trend with at least 3 numbers, also draw one chart as an artifact (React with Recharts).
          - Use only numbers your queries returned. Never invent, estimate or re-round them beyond what the table shows.
          - One chart per answer. Sort bars from largest to smallest unless the order is meaningful (like release year).
          - The title states the finding (for example "Country and Latin songs grow fastest"), the axes carry units, and growth is labelled "% of lifetime streams, per day".
          - One blue for the bars and one orange to highlight the item the question is about. Leave the background transparent so it reads in light and dark mode. At most about 15 bars.
          - Skip the chart for single numbers, lists of songs, or fewer than 3 values.
```
