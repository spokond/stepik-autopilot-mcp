import pytest
from pydantic import ValidationError

from stepik_autopilot.core.enums import Selection
from stepik_autopilot.presentation.schemas import PlanInput


def test_explicit_selection_accepts_section_numbers() -> None:
    value = PlanInput.model_validate({"course_id": "42", "selection": "explicit", "section_numbers": [2, 4]})

    assert value.selection is Selection.EXPLICIT
    assert value.section_numbers == [2, 4]
    assert value.explicit_step_ids is None


def test_selection_is_inferred_from_explicit_scope() -> None:
    value = PlanInput.model_validate({"course_id": "42", "section_numbers": [2, 4]})

    assert value.selection is Selection.EXPLICIT


def test_selection_defaults_to_remaining_without_explicit_scope() -> None:
    value = PlanInput.model_validate({"course_id": "42"})

    assert value.selection is Selection.REMAINING


@pytest.mark.parametrize(
    "values",
    [
        {"course_id": "42", "selection": Selection.EXPLICIT},
        {
            "course_id": "42",
            "selection": Selection.EXPLICIT,
            "explicit_step_ids": ["501"],
            "section_numbers": [2],
        },
        {"course_id": "42", "selection": Selection.REMAINING, "section_numbers": [2]},
        {"course_id": "42", "selection": Selection.EXPLICIT, "section_numbers": [2, 2]},
    ],
)
def test_selection_scope_rejects_ambiguous_values(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PlanInput.model_validate(values)
