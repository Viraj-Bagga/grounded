"""Self-test for the schema the demo sends llama-server.

    python 06-demo/selftest_schema.py

The demo caps every array (pipeline.ARRAY_CAPS) so a looping list ends and
the answer still parses: on 2026-09-27, 5 of 30 answers for Dad's hill were
cut off at the token limit, each "Call emergency services now" written about
145 times, and 0 of 30 after the caps. See results/2026-09-27-fix2-cutoffs/.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "02-pairs")]
from pair_format import ASSISTANT_SCHEMA  # noqa: E402
from pipeline import ARRAY_CAPS, DEMO_SCHEMA  # noqa: E402

fails = []


def check(name, ok):
    if not ok:
        fails.append(name)
    print(("ok    " if ok else "FAIL  ") + name)


def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


props = DEMO_SCHEMA["properties"]
arrays = [k for k, v in props.items() if v.get("type") == "array"]
check("every array in the demo schema has a cap", all("maxItems" in props[k] for k in arrays))
check("the caps are the ones measured", {k: props[k]["maxItems"] for k in arrays} == ARRAY_CAPS)
check("every cap is above the most any normal answer used (3 flags, 6 steps, 3 citations, 2 questions)",
      ARRAY_CAPS["red_flags"] >= 3 and ARRAY_CAPS["next_steps"] >= 6 and ARRAY_CAPS["citations"] >= 3
      and ARRAY_CAPS["follow_up_questions"] >= 2)
check("hard constraint 3: no maxLength anywhere in the demo schema",
      not any("maxLength" in d for d in walk(DEMO_SCHEMA)))
check("the shared schema, used by the pairs and the evals, is unchanged",
      not any("maxItems" in d or "maxLength" in d for d in walk(ASSISTANT_SCHEMA)))
check("the demo schema is otherwise the shared one",
      DEMO_SCHEMA["required"] == ASSISTANT_SCHEMA["required"]
      and set(props) == set(ASSISTANT_SCHEMA["properties"]))

print(f"{len(fails)} failed" if fails else "6/6 self-tests passed.")
sys.exit(1 if fails else 0)
