"""PILOT-MEMORY-1B hardened shadow benchmark.

Shadow-only. This package holds no production authority and is deliberately
separate from ``soma.memory``, which is the real durable project memory store.
Nothing here imports that package, reads the live store, touches ProjectScope
tables, or writes anywhere except an explicitly supplied disposable directory.

Canonical content is Markdown on disk plus Git history. Every index this
package builds is derived, disposable, and reproducible from canonical files
alone; deleting an index must never lose information.
"""

from .contract import (
    BENCHMARK_CONTRACT,
    CONFUSION_PROJECT_ID,
    SOMA_PROJECT_ID,
    contract_hash,
)

__all__ = [
    "BENCHMARK_CONTRACT",
    "CONFUSION_PROJECT_ID",
    "SOMA_PROJECT_ID",
    "contract_hash",
]
