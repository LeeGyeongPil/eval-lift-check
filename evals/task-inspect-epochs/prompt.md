---
name: task-inspect-epochs
max_turns: 15
---

base.json and cand.json are Inspect logs (JSON) of the same rubric-scored task for two models, 30 questions with 3 epochs each. Keep every epoch as its own row but account for the epochs of one question being correlated. Is the candidate better? Save the full machine-readable report as report.json.
