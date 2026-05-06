"""
app/ml/explainer.py — SHAP-based model explainability engine.

Phase 6 differentiator: feature importance + per-prediction SHAP explanation.

Uses TreeExplainer for RandomForest/GBM (fast, exact) and
LinearExplainer fallback for LogisticRegression.

SHAP values tell you: "This feature pushed the prediction up/down by X."
Recruiter-visible value: most candidates cannot explain WHY a model predicts.
"""

from typing import Any

import numpy as np
import pandas as pd
import structlog

from app.ml.pipeline import FEATURE_COLUMNS

logger = structlog.get_logger(__name__)


class ExplainerService:
    """
    Wraps a trained sklearn Pipeline and produces SHAP explanations.
    Instantiated lazily — only when /explain endpoint is called.
    Not part of hot prediction path.
    """

    def __init__(self, pipeline: Any) -> None:
        self._pipeline = pipeline
        self._explainer: Any = None
        self._feature_names: list[str] = []
        self._preprocessor_fitted = False

    def _build_explainer(self) -> None:
        """Lazy-build the SHAP explainer from the loaded pipeline."""
        import shap

        preprocessor = self._pipeline.named_steps.get("preprocessor")
        classifier = self._pipeline.named_steps.get("classifier")

        if preprocessor is None or classifier is None:
            raise ValueError("Pipeline must have 'preprocessor' and 'classifier' steps")

        transformed_names: list[str] = []
        for _name, transformer, cols in preprocessor.transformers_:
            if hasattr(transformer, "get_feature_names_out"):
                transformed_names.extend(
                    transformer.get_feature_names_out(cols).tolist()
                )
            else:
                transformed_names.extend(list(cols))

        self._feature_names = transformed_names

        classifier_type = type(classifier).__name__

        if classifier_type in (
            "RandomForestClassifier",
            "GradientBoostingClassifier",
            "ExtraTreesClassifier",
            "XGBClassifier",
            "LGBMClassifier",
        ):
            self._explainer = shap.TreeExplainer(classifier)
            logger.info("shap_tree_explainer_built", classifier=classifier_type)
        elif classifier_type == "LogisticRegression":
            n_features = len(transformed_names)
            background = np.zeros((1, n_features))
            self._explainer = shap.LinearExplainer(classifier, background)
            logger.info("shap_linear_explainer_built", classifier=classifier_type)
        else:
            n_features = len(transformed_names)
            background = np.zeros((1, n_features))
            predict_fn = lambda x: classifier.predict_proba(x)[:, 1]  # noqa: E731
            self._explainer = shap.KernelExplainer(predict_fn, background)
            logger.info("shap_kernel_explainer_built", classifier=classifier_type)

    def _ensure_explainer(self) -> None:
        if self._explainer is None:
            self._build_explainer()

    @staticmethod
    def _select_positive_class_output(raw_shap: Any) -> np.ndarray:
        """
        Normalize SHAP return values to a NumPy array for class-1 (churn).

        SHAP may return:
        - list[class0, class1]
        - ndarray
        """
        if isinstance(raw_shap, list):
            if not raw_shap:
                raise ValueError("Received empty SHAP output")
            raw_shap = raw_shap[1] if len(raw_shap) > 1 else raw_shap[0]

        return np.asarray(raw_shap)

    @staticmethod
    def _normalize_shap_matrix(raw_shap: Any) -> np.ndarray:
        """
        Convert SHAP output into a 2D matrix of shape (n_records, n_features).
        """
        arr = ExplainerService._select_positive_class_output(raw_shap)

        if arr.ndim == 0:
            return arr.reshape(1, 1)

        if arr.ndim == 1:
            return arr.reshape(1, -1)

        if arr.ndim == 2:
            return arr

        if arr.ndim == 3:
            if arr.shape[-1] == 1:
                return arr.reshape(arr.shape[0], arr.shape[1])

            if arr.shape[-1] >= 2:
                return arr[:, :, 1]

        return np.asarray(arr).reshape(arr.shape[0], -1)

    @staticmethod
    def _expected_value_scalar(expected_value: Any) -> float:
        """
        Convert SHAP expected_value into a scalar churn baseline.
        """
        arr = np.asarray(expected_value)

        if arr.ndim == 0:
            return float(arr.item())

        flat = arr.reshape(-1)
        if flat.size >= 2:
            return float(flat[1])
        if flat.size == 1:
            return float(flat[0])

        raise ValueError("Unable to determine scalar expected value")

    @staticmethod
    def _record_vector(record_shap: Any) -> np.ndarray:
        """
        Flatten a per-record SHAP vector into 1D float values.
        """
        return np.asarray(record_shap).reshape(-1).astype(float)

    def explain_records(
        self,
        records: list[dict[str, Any]],
        top_n: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Explain a list of customer records.

        Returns:
            List of dicts, one per record:
            {
                "churn_probability": float,
                "top_features": [{"feature": str, "shap_value": float, "direction": str}],
                "expected_value": float,
            }
        """
        self._ensure_explainer()

        df = pd.DataFrame(records, columns=FEATURE_COLUMNS)
        preprocessor = self._pipeline.named_steps["preprocessor"]
        classifier = self._pipeline.named_steps["classifier"]

        x_transformed = preprocessor.transform(df)

        raw_shap = self._explainer.shap_values(x_transformed)
        shap_matrix = self._normalize_shap_matrix(raw_shap)

        expected_value = self._expected_value_scalar(self._explainer.expected_value)

        probabilities = classifier.predict_proba(x_transformed)[:, 1]

        results: list[dict[str, Any]] = []
        for i, (record_shap, prob) in enumerate(
            zip(shap_matrix, probabilities, strict=False)
        ):
            record_vector = self._record_vector(record_shap)

            feature_shap_pairs = sorted(
                zip(
                    self._feature_names,
                    record_vector.tolist(),
                    strict=False,
                ),
                key=lambda x: abs(float(x[1])),
                reverse=True,
            )

            top_features = [
                {
                    "feature": fname,
                    "shap_value": round(float(sv), 6),
                    "direction": (
                        "increases_churn" if float(sv) > 0 else "decreases_churn"
                    ),
                    "magnitude": round(abs(float(sv)), 6),
                }
                for fname, sv in feature_shap_pairs[:top_n]
            ]

            results.append(
                {
                    "record_index": i,
                    "churn_probability": round(float(prob), 6),
                    "expected_value": round(float(expected_value), 6),
                    "top_features": top_features,
                    "shap_sum": round(float(np.sum(record_vector)), 6),
                }
            )

        logger.info("shap_explanation_complete", n_records=len(records))
        return results

    def global_feature_importance(
        self,
        records: list[dict[str, Any]],
        top_n: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Compute mean absolute SHAP values across a batch of records.
        Use this for the "global importance" UI panel.
        """
        self._ensure_explainer()

        df = pd.DataFrame(records, columns=FEATURE_COLUMNS)
        preprocessor = self._pipeline.named_steps["preprocessor"]

        x_transformed = preprocessor.transform(df)
        raw_shap = self._explainer.shap_values(x_transformed)
        shap_matrix = self._normalize_shap_matrix(raw_shap)

        mean_abs_shap = np.abs(shap_matrix).mean(axis=0)

        ranked = sorted(
            zip(self._feature_names, mean_abs_shap.tolist(), strict=False),
            key=lambda x: float(x[1]),
            reverse=True,
        )

        return [
            {
                "feature": fname,
                "mean_abs_shap": round(float(val), 6),
                "rank": rank + 1,
            }
            for rank, (fname, val) in enumerate(ranked[:top_n])
        ]


# ── Module-level cache ─────────────────────────────────────────────────────────
# One explainer per loaded pipeline. Reset on model swap.

_explainer_cache: dict[str, ExplainerService] = {}


def get_explainer(pipeline: Any, version_tag: str) -> ExplainerService:
    """Return cached ExplainerService or build a new one."""
    if version_tag not in _explainer_cache:
        _explainer_cache.clear()
        _explainer_cache[version_tag] = ExplainerService(pipeline)
    return _explainer_cache[version_tag]


def invalidate_explainer_cache() -> None:
    """Call this when a new model is promoted."""
    _explainer_cache.clear()
    logger.info("explainer_cache_invalidated")