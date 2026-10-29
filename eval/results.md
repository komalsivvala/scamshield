# ScamShield evaluation

Dataset: 50 messages (26 scam, 24 genuine). Flagged = SCAM or SUSPICIOUS.

| System | Accuracy | Precision | Recall | F1 | FP | FN |
|---|---|---|---|---|---|---|
| Rule engine only (baseline) | 88% | 100% | 77% | 0.87 | 0 | 6 |
| ScamShield full agent | 96% | 93% | 100% | 0.96 | 2 | 0 |

**Hard set** (10 subtle messages written after the rules were frozen, no keyword giveaways):

| System | Accuracy | Recall | FP | FN |
|---|---|---|---|---|
| Rule engine only (baseline) | 60% | 20% | 0 | 4 |
| ScamShield full agent | 90% | 100% | 1 | 0 |

Median end-to-end latency: 12.3s

## Errors

- #24 (legit, debit_alert): agent said SUSPICIOUS
- #49 (legit, hard_genuine_cashback): agent said SUSPICIOUS
