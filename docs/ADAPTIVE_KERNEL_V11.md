# PhiGraph v1.1 Adaptive Kernel Laboratory

## Included kernels

- combinatorial and normalized Laplacians;
- multiplex layer-weighted Laplacian;
- heat/diffusion operator;
- signal-aware operator;
- non-backtracking Bethe-Hessian surrogate;
- line-graph edge kernel;
- temporal block operator.

## New agents

- KernelSelectionAgent;
- KernelUncertaintyAgent.

The selector compares localization concentration, IPR dispersion and operator
complexity. Bootstrap edge perturbation estimates hotspot probability and mean
rank. These are model-selection and uncertainty diagnostics, not proof of
real-world causality.
