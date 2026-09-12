from stepik_autopilot.application.dto import ChoiceAnswerDTO, ChoiceDatasetDTO, ChoiceReplyDTO
from stepik_autopilot.core.exceptions import UnsupportedTaskError, ValidationError


class ChoiceAdapter:
    max_items = 12

    def build_reply(self, answer: ChoiceAnswerDTO, dataset: ChoiceDatasetDTO) -> ChoiceReplyDTO:
        if len(set(answer.selected_indexes)) != len(answer.selected_indexes):
            msg = "choice indexes must not be duplicated"
            raise ValidationError(msg)
        if any(index < 0 or index >= len(dataset.options) for index in answer.selected_indexes):
            msg = "choice index does not belong to this attempt"
            raise ValidationError(msg)
        if not dataset.is_multiple_choice and len(answer.selected_indexes) != 1:
            msg = "single-choice attempt requires exactly one index"
            raise ValidationError(msg)
        return ChoiceReplyDTO(tuple(index in answer.selected_indexes for index in range(len(dataset.options))))


class AdapterRegistry:
    def __init__(self) -> None:
        self._choice = ChoiceAdapter()

    def choice(self, kind: str) -> ChoiceAdapter:
        if kind != "choice":
            msg = f"Stepik block type {kind!r} is not a confirmed choice task"
            raise UnsupportedTaskError(msg)
        return self._choice

    @staticmethod
    def is_theory(kind: str) -> bool:
        return kind in {"text", "video"}
