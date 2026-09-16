from stepik_autopilot.core.enums import Grading, RunMode, Selection, Strategy, Target
from stepik_autopilot.presentation.schemas import RunStartInput


def test_run_start_input_parses_documented_json_enum_values() -> None:
    arguments = RunStartInput.model_validate(
        {
            "course_id": "68343",
            "section_numbers": [1, 2],
            "mode": "autopilot",
            "strategy": "throughput",
            "target": "tasks_complete",
            "grading": "deferred",
            "request_id": "7af71949-2070-43e9-88f4-f6dc83e24630",
        }
    )

    assert arguments.selection is Selection.EXPLICIT
    assert arguments.mode is RunMode.AUTOPILOT
    assert arguments.strategy is Strategy.THROUGHPUT
    assert arguments.target is Target.TASKS_COMPLETE
    assert arguments.grading is Grading.DEFERRED
