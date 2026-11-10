"""Auto, Manual, and Compare. Selection never duplicates a single model."""

from __future__ import annotations

from dataclasses import dataclass

from aicmo.modules.creative.gateway.registry import ModelCapability, available_for, get_model


class SelectionError(ValueError):
    pass


@dataclass(frozen=True)
class SelectionPlan:
    models: tuple[ModelCapability, ...]
    explanation: str


def _supports(model: ModelCapability, *, aspect_ratio: str | None, resolution: str | None) -> bool:
    if aspect_ratio and aspect_ratio not in model.aspect_ratios:
        return False
    if resolution and resolution not in model.resolutions:
        return False
    return True


def plan_selection(
    *,
    mode: str,
    task: str,
    model_ids: list[str] | None,
    aspect_ratio: str | None,
    resolution: str | None,
) -> SelectionPlan:
    available = [
        model
        for model in available_for(task)
        if _supports(model, aspect_ratio=aspect_ratio, resolution=resolution)
    ]
    if mode == "auto":
        if not available:
            raise SelectionError(
                "No verified model is configured for this task and those settings."
            )
        chosen = available[0]
        return SelectionPlan(
            models=(chosen,),
            explanation=(
                f"Auto selected {chosen.display_name} ({chosen.model_id}) because it is "
                "the only verified model that supports this request."
                if len(available) == 1
                else (
                    f"Auto selected {chosen.display_name} ({chosen.model_id}). "
                    f"{len(available)} verified models support this request; "
                    "this build has no quality ranking beyond availability, so the "
                    "first matching model is used. Choose Manual or Compare to pick others."
                )
            ),
        )

    if mode == "manual":
        if not model_ids or len(model_ids) != 1:
            raise SelectionError("Manual mode requires exactly one model id.")
        model = get_model(model_ids[0])
        if model is None or not model.available() or model.task != task:
            raise SelectionError("That model is not available.")
        if not _supports(model, aspect_ratio=aspect_ratio, resolution=resolution):
            raise SelectionError("That model does not support the requested settings.")
        return SelectionPlan(
            models=(model,),
            explanation=f"Manual selection: {model.display_name} ({model.model_id}).",
        )

    if mode == "compare":
        if not model_ids:
            ids = [model.model_id for model in available]
        else:
            ids = []
            for model_id in model_ids:
                model = get_model(model_id)
                if model is None or not model.available() or model.task != task:
                    raise SelectionError(f"{model_id} is not available for comparison.")
                if not _supports(model, aspect_ratio=aspect_ratio, resolution=resolution):
                    raise SelectionError(f"{model_id} does not support the requested settings.")
                ids.append(model_id)
        unique = list(dict.fromkeys(ids))
        chosen = [model for model in available if model.model_id in unique]
        if not chosen:
            raise SelectionError("No verified models are available to compare.")
        if len(chosen) == 1:
            only = chosen[0]
            return SelectionPlan(
                models=(only,),
                explanation=(
                    "Only one verified model is configured, so comparison is limited "
                    f"to {only.display_name}. A second result was not generated."
                ),
            )
        names = ", ".join(model.display_name for model in chosen)
        return SelectionPlan(
            models=tuple(chosen),
            explanation=f"Compare will run {len(chosen)} models: {names}.",
        )

    raise SelectionError("Mode must be auto, manual, or compare.")
