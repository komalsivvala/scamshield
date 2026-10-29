# Token Factory latency benchmark (2026-10-30)

Task: small JSON extraction, 3 runs each, median shown. `thinking` = Nemotron 3 `enable_thinking` chat-template flag.

| Model | Thinking | Median | Runs (ms) |
|---|---|---|---|
| nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B | off | 6254 ms | 3835, 8354, 6254 |
| nvidia/nemotron-3-super-120b-a12b | off | **803 ms** | 803, 601, 843 |
| nvidia/Nemotron-3_5-Lightning | off | 604 ms | 605, 521, 604 |
| nvidia/Nemotron-3-Ultra-550b-a55b | on | 884 ms | 924, 884, 650 |
| nvidia/Nemotron-3-Ultra-550b-a55b | off | 638 ms | 579, 638, 2558 |

Nano with thinking ON and max_tokens=600 spent the entire budget reasoning and returned empty content (23.7 s).

**Decision:** Super (thinking off) for extraction; Ultra (thinking on) for the verdict; Ultra (thinking off) for
family explanations, because in side-by-side Telugu/Hindi tests Super mixed scripts ("షcam") while Ultra produced
clean, natural text.
