# ScamShield evaluation

Dataset: 50 messages (26 scam, 24 genuine). Flagged = SCAM or SUSPICIOUS.

| System | Accuracy | Precision | Recall | F1 | FP | FN |
|---|---|---|---|---|---|---|
| Rule engine only (baseline) | 88% | 100% | 77% | 0.87 | 0 | 6 |

**Hard set** (10 subtle messages written after the rules were frozen, no keyword giveaways):

| System | Accuracy | Recall | FP | FN |
|---|---|---|---|---|
| Rule engine only (baseline) | 60% | 20% | 0 | 4 |
