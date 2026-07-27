"""Deterministic scale-corpus generator.

Produces 1,000- and 10,000-note corpora from the frozen seed. The output is
never committed and never written inside a tracked repository path; the runner
places it in a disposable directory and removes it after measurement.

The generator reuses the curated vocabulary so that scale measurements are
taken against text of the same shape, and it seeds a known needle so warm-query
correctness can be checked at every scale rather than only timed.
"""

from __future__ import annotations

import random
from pathlib import Path

from .contract import CONFUSION_PROJECT_ID, SEED, SOMA_PROJECT_ID
from .corpus import NoteSpec
from .vault import write_vault

_SUBJECTS = (
    "worker lease", "durable store", "runtime listener", "tunnel endpoint",
    "executable profile", "publication hash", "recovery path", "scope binding",
    "artifact digest", "operation lock", "capability epoch", "journal mode",
)
_PREDICATES = (
    "was measured during a routine survey",
    "was reviewed and left unchanged",
    "was adjusted after an operational observation",
    "was recorded as part of a maintenance window",
    "was confirmed against the running build",
    "was noted while reconciling evidence",
)
_KINDS = ("fact", "decision", "lesson", "procedure", "source_ref")

#: A unique needle planted once per generated corpus so that retrieval
#: correctness, not merely latency, can be asserted at scale.
NEEDLE_ID = "scale-needle-note"
NEEDLE_QUERY = "quiescent perihelion checkpoint marker"


def generate_specs(count: int, seed: int = SEED) -> tuple[NoteSpec, ...]:
    """Deterministically build ``count`` notes plus one needle."""
    rng = random.Random(seed)
    specs: list[NoteSpec] = []
    for i in range(count):
        project = SOMA_PROJECT_ID if i % 2 == 0 else CONFUSION_PROJECT_ID
        subject = rng.choice(_SUBJECTS)
        predicate = rng.choice(_PREDICATES)
        kind = rng.choice(_KINDS)
        note_id = f"scale-{i:06d}"
        body = (
            f"The {subject} {predicate}. Sequence marker {i} distinguishes this "
            f"record from its neighbours in the generated set."
        )
        supersedes: tuple[str, ...] = ()
        relations: tuple[tuple[str, str], ...] = ()
        # Every fifth note supersedes the same-project note two positions back,
        # which keeps supersession resolution on the measured path at scale.
        if i >= 2 and i % 5 == 0:
            predecessor = f"scale-{i - 2:06d}"
            supersedes = (predecessor,)
            relations = (("supersedes", predecessor),)
        specs.append(
            NoteSpec(
                note_id=note_id,
                project_id=project,
                kind=kind,
                title=f"Generated record {i}",
                body=body,
                created="2026-07-27",
                source="PLANS.md" if i % 7 else "",
                supersedes=supersedes,
                claims=((f"metric_{i % 11}", str(i)),),
                relations=relations,
            )
        )
    specs.append(
        NoteSpec(
            note_id=NEEDLE_ID,
            project_id=SOMA_PROJECT_ID,
            kind="fact",
            title="Needle record",
            body=(
                "This record carries the quiescent perihelion checkpoint marker "
                "that appears nowhere else in the generated corpus."
            ),
            created="2026-07-27",
            source="PLANS.md",
            claims=(("needle", "present"),),
        )
    )
    return tuple(specs)


def generate_vault(root: Path, count: int, seed: int = SEED) -> Path:
    """Materialize a generated corpus into a disposable directory."""
    root.mkdir(parents=True, exist_ok=True)
    write_vault(root, generate_specs(count, seed))
    return root
