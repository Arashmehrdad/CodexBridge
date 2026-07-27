"""Set-based scoring, fixed by the contract before measurement."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Score:
    precision: float
    recall: float
    f1: float
    true_positives: tuple[str, ...]
    false_positives: tuple[str, ...]
    false_negatives: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "true_positives": list(self.true_positives),
            "false_positives": list(self.false_positives),
            "false_negatives": list(self.false_negatives),
        }


def score_sets(expected: frozenset[str], retrieved: list[str]) -> Score:
    """Precision/recall/F1 over note-id sets.

    An empty expectation matched by an empty result scores 1.0; that is the
    correct reading for "nothing should be found here", which several
    structural questions rely on.
    """
    got = set(retrieved)
    hits = got & expected
    if not expected and not got:
        return Score(1.0, 1.0, 1.0, (), (), ())
    precision = len(hits) / len(got) if got else 0.0
    recall = len(hits) / len(expected) if expected else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return Score(
        precision,
        recall,
        f1,
        tuple(sorted(hits)),
        tuple(sorted(got - expected)),
        tuple(sorted(expected - got)),
    )


def mean_f1(scores: list[Score]) -> float:
    return sum(s.f1 for s in scores) / len(scores) if scores else 0.0
