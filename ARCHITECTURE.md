# EvoClaw architecture

This file explains the **current codebase shape** in plain language so you can understand where each concern lives without reading every module first.

## 1. Current architecture in one sentence

EvoClaw currently has a working **fetch -> evaluate** foundation, with the future **archive -> evolve -> deploy -> deliver** loop still to be built.

## 2. Main layers

| Layer | Purpose | Current files |
| --- | --- | --- |
| Data collection | Fetch YouTube candidates and cache them locally | `adas/youtube_fetcher.py` |
| Shared configuration | Centralize env-driven settings, paths, weights, and limits | `adas/config.py` |
| Evaluation orchestration | Coordinate request loading, skill execution, scoring, and aggregation | `adas/evaluator.py` |
| Request assembly | Load `SKILL.md`, cache JSON, and feedback JSON into typed request objects | `adas/evaluator_loader.py` |
| Data contracts | Define evaluator DTO-style models | `adas/evaluator_models.py` |
| Deterministic scoring | Score freshness, diversity, and placeholder alignment | `adas/algorithmic_scorer.py` |
| Model judging | Score relevance, substance, and reasoning through an OpenAI-compatible endpoint | `adas/llm_judge.py` |
| Skill execution | Execute the current baseline skill strategies over cached videos | `adas/skill_executor.py` |
| Prompt assets | Hold reusable evaluator prompt templates | `adas/prompts/eval_judge.md` |
| Production skill placeholder | Future deployment target for the best skill | `skills/youtube-curator/SKILL.md` |
| Scheduler stub | Planned automation entrypoints | `cron/jobs.json` |

## 3. How the modules relate

```text
youtube_fetcher.py
    -> produces cached video datasets in adas/test_sets/

evaluator_loader.py
    -> loads skill markdown + cached videos + feedback history
    -> returns EvaluationRequest

skill_executor.py
    -> selects video IDs for supported baseline strategies

algorithmic_scorer.py
    -> scores freshness, diversity, alignment

llm_judge.py
    -> scores relevance, substance, reasoning

evaluator.py
    -> orchestrates the full evaluation flow
    -> returns EvaluationResult
```

## 4. Core design choices already visible in the code

### DTOs are separated from orchestration

If you come from a .NET background, `adas/evaluator_models.py` is the closest thing to a DTO/contracts file. It keeps the request/result shapes away from file I/O and scoring logic.

### File loading is separate from business logic

`adas/evaluator_loader.py` owns markdown parsing and JSON loading, so `Evaluator` does not need to understand low-level file formats.

### Scoring is split by responsibility

- `adas/algorithmic_scorer.py` handles deterministic rules
- `adas/llm_judge.py` handles semantic judging
- `adas/evaluator.py` only coordinates the flow

### Skill execution is replaceable

`adas/skill_executor.py` is intentionally a Python adapter for now. It gives you a working execution path today while keeping the door open for a future real OpenClaw runtime.

### Fetching is internally decomposed

Inside `adas/youtube_fetcher.py`, the fetcher is split into:

- `YouTubeAPIClient`
- `TranscriptProvider`
- `VideoCacheRepository`
- `YouTubeFetcher`

That keeps API access, transcript attachment, cache persistence, and orchestration separate enough to follow.

## 5. Important data objects

| Type | Meaning |
| --- | --- |
| `SkillDocument` | Parsed `SKILL.md` plus YAML frontmatter metadata |
| `VideoRecord` | Normalized cached YouTube video record |
| `FeedbackEntry` | One feedback history record from `feedback.json` |
| `EvaluationRequest` | Combined input for an evaluation run |
| `DimensionScore` | One weighted score entry in the result |
| `EvaluationResult` | Final evaluation output, partial or complete |

## 6. What is implemented vs planned

### Implemented now

- real YouTube fetching and cache generation
- typed settings and path/config organization
- evaluator request loading
- baseline strategy execution through a Python adapter
- algorithmic scoring
- optional LLM judging
- weighted aggregation
- placeholder production skill

### Planned later

- archive entry creation under `adas/archive/skill_*`
- `adas/meta_agent.py`
- meta-agent prompts beyond `eval_judge.md`
- promotion of the best skill into `skills/youtube-curator/SKILL.md`
- Telegram sending and feedback capture
- cron-driven end-to-end automation

## 7. Best files to read first

If you want the easiest learning path through the code:

1. `README.md`
2. `WORKFLOW.md`
3. `adas/README.md`
4. `adas/evaluator_models.py`
5. `adas/evaluator_loader.py`
6. `adas/evaluator.py`
7. `adas/skill_executor.py`
8. `adas/algorithmic_scorer.py`
9. `adas/llm_judge.py`
10. `adas/youtube_fetcher.py`

## 8. How to run unit tests

```bash
# Activate the virtual environment first                                                                                                                                                    
  source .venv/bin/activate                                                                                                                                                                   
                                                                                                                                                                                              
  # Run all tests                                                                                                                                                                             
  python3 -m pytest tests/ -v                                                                                                                                                                 
                                                                                                                                                                                              
  Useful variants:                                                                                                                                                                            
                                                                                                                                                                                              
  # Run a single test file
  python3 -m pytest tests/adas/test_algorithmic_scorer.py -v                                                                                                                                  
   
  # Run a single test class                                                                                                                                                                   
  python3 -m pytest tests/adas/test_skill_executor.py::TestLooksEnglish -v
                                                                                                                                                                                              
  # Run a single test
  python3 -m pytest tests/adas/test_evaluator.py::TestAggregateWeightedScore::test_all_tens_gives_10 -v                                                                                       
                                                                                                                                                                                              
  # Stop on first failure
  python3 -m pytest tests/ -v -x                                                                                                                                                              
                                                                                                                                                                                              
  # Show just a summary (no per-test output)
  python3 -m pytest tests/        
```