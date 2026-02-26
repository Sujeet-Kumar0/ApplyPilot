## Draft PR: Smart Tailoring State Machine

**Status:** Draft - Pending Foundation Features  
**Branch:** `feature/smart-tailoring` → `dev` (then to `main` after v2.0 foundation)  
**Depends on:** #XX (Job Intelligence + Resume Formatting PRs)

### Summary
Core v2.0 feature: Iterative resume tailoring system with bullet bank, quality gates, and state machine for continuous improvement.

### Changes
- **New:** `src/applypilot/tailoring/` package
  - `models.py` - `Bullet`, `BulletVariant`, `GateResult`, `TailoringResult`
  - `bullet_bank.py` - SQLite persistence with feedback tracking
  - `quality_gates.py` - `MetricsGate` and `RelevanceGate`
  - `state_machine.py` - `SmartTailoringEngine` with 9 states

- **New:** Test suite
  - `tests/tailoring/test_state_machine.py` (27 tests)
  - Covers all states, transitions, gates, bullet bank

- **New:** Dependency
  - `transitions` library for state machine

### State Machine Flow
```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌───────┐
│ ANALYZE │───→│ EXTRACT  │───→│ GENERATE │───→│ SCORE │
└─────────┘    └──────────┘    └──────────┘    └───┬───┘
                                                   │
   ┌───────────────────────────────────────────────┘
   ↓
┌────────┐    ┌──────────┐    ┌───────┐    ┌──────────┐
│ SELECT │───→│ VALIDATE │───→│ JUDGE │───→│ ASSEMBLE │
└────────┘    └──────────┘    └───┬───┘    └─────┬────┘
                                  │              │
                              (fail)             │
                                  │              ↓
                                  └──────────→┌────────┐
                                              │  LEARN │
                                              └────────┘
```

### Key Features
1. **Bullet Bank** (SQLite)
   - Store reusable bullets with metadata
   - Track use_count and success_rate
   - Tag-based organization
   - Feedback recording per application

2. **Quality Gates**
   - `MetricsGate`: Ensures quantifiable achievements (%/$/#)
   - `RelevanceGate`: LLM-based job relevance scoring
   - Configurable thresholds

3. **Iterative Improvement**
   - Loop back to GENERATE if quality gates fail
   - Max iterations prevents infinite loops
   - Learns from feedback for future tailoring

### Usage Example
```python
from applypilot.tailoring.state_machine import SmartTailoringEngine

engine = SmartTailoringEngine({
    'bullet_bank_path': '~/.applypilot/bullets.db',
    'max_iterations': 3,
    'target_score': 8.0
})

engine.initialize({
    'job': {'title': '...', 'description': '...'},
    'resume': {'text': '...'}
})

# Step through states
while engine.state != 'LEARN':
    engine.step()
    
result = engine.get_result()
```

### Testing
```bash
pip install transitions
pytest tests/tailoring/ -v  # 27 tests
```

### Architecture
```
Job + Resume → ANALYZE → JobIntel
                    ↓
              EXTRACT → Achievements
                    ↓
              GENERATE → Variants
                    ↓
              [SCORE → SELECT → VALIDATE → JUDGE] (loop)
                    ↓
              ASSEMBLE → Resume
                    ↓
              LEARN → Update success rates
```

### Checklist
- [x] 9-state state machine implemented
- [x] Bullet bank with SQLite
- [x] 2 quality gates
- [x] Tests passing (27)
- [ ] Integration with apply command
- [ ] Real-world iteration testing
- [ ] Performance optimization

### Database Schema
```sql
bullets (id, text, context, tags, metrics, created_at, use_count, success_rate)
feedback (id, bullet_id, job_title, outcome, created_at)
```

### Notes
- State machine uses `transitions` library
- Step-based execution prevents recursion
- All LLM calls mocked in tests
- Bullet bank persists across sessions
