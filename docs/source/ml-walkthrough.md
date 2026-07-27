---
myst:
  html_meta:
    description: "Pointer to the in-app ML walkthrough for the Jytte football predictor"
---

# ML Walkthrough

The full from-first-principles machine-learning walkthrough lives at
`docs/ml-walkthrough.md` in the repo and is rendered inside the running
app at <http://localhost:8080/docs/ml> with live figures from the most
recent training run.

## What it covers

1. What ML actually is (vs. statistics, vs. "AI").
2. Supervised vs unsupervised vs reinforcement learning.
3. The pipeline at a glance.
4. Train / validation / test - why all three.
5. Feature engineering deep-dive.
6. Multi-target prediction.
7. Model families and why we chose logistic regression.
8. The math of multinomial logistic regression.
9. Overfitting, regularization, cross-validation.
10. Metrics - accuracy is not enough.
11. Calibration - making probabilities trustworthy.
12. Uncertainty quantification - aleatoric vs epistemic.
13. Why the model fails the way it fails.
14. Retraining: when, how, what triggers it.
15. Wiring this into Jytte's widget plugin.
16. References + further reading.

## Why it lives outside the Sphinx tree

The runtime FastAPI route `/docs/ml` (see `app/main.py:116`) renders the
markdown file directly and rewrites image paths to the in-app
`/docs-files/ml-figures/` mount. Duplicating the file into the Sphinx tree
would create two sources of truth for a doc whose figures are regenerated
every training run.

If you later want the walkthrough fully integrated into the Sphinx site,
move `docs/ml-walkthrough.md` to `docs/source/ml-walkthrough.md`, move
`docs/ml-figures/` to `docs/source/_static/ml-figures/`, and update the
`DOCS_DIR` constant in `app/main.py`.
