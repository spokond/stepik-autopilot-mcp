import pytest
from pydantic import ValidationError

from stepik_autopilot.core.enums import Selection
from stepik_autopilot.presentation.schemas import PlanInput


def test_explicit_selection_accepts_section_numbers() -> None:
    value = PlanInput(course_id="42", selection=Selection.EXPLICIT, section_numbers=[2, 4])

    assert value.section_numbers == [2, 4]
    assert value.explicit_step_ids is None


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
