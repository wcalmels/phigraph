# PhiGraph v1.2 Kernel Meta-Learning

This release learns kernel family and hyperparameters by domain and graph context.

Context includes graph size, density, components, degree heterogeneity, signal
variance, temporal snapshot count and multiplex layer count.

Only confirmed experiments contribute to exploitation. Untested configurations
are explored in a controlled order. Historical rewards are weighted by context
similarity and combined with an uncertainty bonus.

The selected kernel is evaluated and stored, but never deployed automatically.
