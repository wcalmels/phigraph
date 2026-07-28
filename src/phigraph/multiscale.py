from __future__ import annotations

import numpy as np
from scipy import sparse

from .graph import GraphDataset


class MultiscaleOperator:
    """Combine normalized graph diffusion operators over several powers."""

    def __init__(self, dataset: GraphDataset):
        self.dataset = dataset

    def build(
        self,
        scales: int = 4,
        decay: float = 0.5,
    ) -> sparse.csr_matrix:
        if scales < 1:
            raise ValueError("scales must be >= 1.")
        if not 0 < decay <= 1:
            raise ValueError("decay must be in (0, 1].")

        adjacency = self.dataset.adjacency().astype(float)
        degree = np.asarray(adjacency.sum(axis=1)).ravel()
        inv_degree = np.divide(
            1.0,
            degree,
            out=np.zeros_like(degree),
            where=degree > 0,
        )
        transition = sparse.diags(inv_degree) @ adjacency

        current = sparse.identity(self.dataset.size, format="csr")
        combined = sparse.csr_matrix(current.shape)
        weight_sum = 0.0
        for q in range(1, scales + 1):
            current = current @ transition
            weight = decay ** (q - 1)
            combined = combined + weight * current
            weight_sum += weight
        return (combined / weight_sum).tocsr()
