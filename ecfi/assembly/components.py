from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class UnionFind:
    n: int

    def __post_init__(self) -> None:
        self.parent = list(range(self.n))
        self.rank = [0] * self.n

    def find(self, a: int) -> int:
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1

    def components(self) -> Tuple[List[int], Dict[int, List[int]]]:
        roots = [self.find(i) for i in range(self.n)]
        comp: Dict[int, List[int]] = {}
        for i, r in enumerate(roots):
            comp.setdefault(r, []).append(i)
        return roots, comp