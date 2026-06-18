# Lab 16 Benchmark Report

## Metadata
- Dataset: hotpot_mini.json
- Mode: mock
- Records: 100
- Agents: react, reflexion

## Summary
| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| EM | 0.5 | 1.0 | 0.5 |
| Avg attempts | 1 | 1.5 | 0.5 |
| Avg token estimate | 75.44 | 155.1 | 79.66 |
| Avg latency (ms) | 0 | 0 | 0 |

## Failure modes
```json
{
  "none": 75,
  "entity_drift": 12,
  "incomplete_multi_hop": 7,
  "wrong_final_answer": 6,
  "looping": 0,
  "reflection_overfit": 0,
  "by_agent": {
    "react": {
      "none": 25,
      "entity_drift": 12,
      "incomplete_multi_hop": 7,
      "wrong_final_answer": 6,
      "looping": 0,
      "reflection_overfit": 0
    },
    "reflexion": {
      "none": 50,
      "entity_drift": 0,
      "incomplete_multi_hop": 0,
      "wrong_final_answer": 0,
      "looping": 0,
      "reflection_overfit": 0
    }
  }
}
```

## Extensions implemented
- structured_evaluator
- reflection_memory
- benchmark_report_json
- mock_mode_for_autograding

## Discussion
The comparison isolates the effect of verbal reflection by running ReAct and Reflexion over the same examples. Reflexion is most useful when an answer stops at an intermediate entity or selects an unsupported second-hop entity: the evaluator names the missing hop, the reflector converts that diagnosis into a reusable strategy, and the next actor attempt must verify the final entity against the supplied context. The improvement is not free: additional attempts increase token use and latency, and a weak evaluator can reinforce a bad diagnosis. Exact-match accuracy should therefore be read together with attempts, cost, latency, and the per-agent failure breakdown. Remaining risks include evaluator false positives, reflection overfitting, repeated strategies, and contexts that do not contain enough evidence. Production use should cap retries, validate structured outputs, and retain mock mode as a deterministic regression test.
