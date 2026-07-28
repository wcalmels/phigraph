# PhiGraph v0.9 Advanced Meta-Learning

Version 0.9 adds two safeguards and optimization mechanisms:

1. expanding-window temporal cross-validation;
2. UCB1 configuration selection with controlled exploration.

Temporal folds always train on past observations and test on later observations.
The contextual bandit uses only confirmed historical experiment records.

The bandit recommends a next configuration. It does not deploy or execute it
automatically.
