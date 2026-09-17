from stepik_autopilot.application.dto import (
    BlanksAnswerDTO,
    ChoiceAnswerDTO,
    ChoiceDatasetDTO,
    ChoiceReplyDTO,
    CodeAnswerDTO,
    CodeReplyDTO,
    MatchingAnswerDTO,
    NumberReplyDTO,
    SqlAnswerDTO,
    SqlReplyDTO,
    TableAnswerDTO,
    TextAnswerDTO,
    TextReplyDTO,
)
from stepik_autopilot.application.replies import ReplyDTO
from stepik_autopilot.core.exceptions import UnsupportedTaskError, ValidationError
from stepik_autopilot.core.structured_tasks import blanks_reply, matching_reply, table_reply


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

    def build_reply(  # noqa: PLR0911 - One branch per supported answer kind.
        self,
        kind: str,
        answer: ChoiceAnswerDTO
        | TextAnswerDTO
        | SqlAnswerDTO
        | CodeAnswerDTO
        | BlanksAnswerDTO
        | MatchingAnswerDTO
        | TableAnswerDTO,
        dataset: ChoiceDatasetDTO | None,
        code_languages: tuple[str, ...],
        quiz_data: dict[str, object] | None = None,
    ) -> ReplyDTO:
        if quiz_data is not None:
            if kind == "fill-blanks" and isinstance(answer, BlanksAnswerDTO):
                return blanks_reply(answer, quiz_data)
            if kind == "matching" and isinstance(answer, MatchingAnswerDTO):
                return matching_reply(answer, quiz_data)
            if kind == "table" and isinstance(answer, TableAnswerDTO):
                return table_reply(answer, quiz_data)
        if kind == "choice" and isinstance(answer, ChoiceAnswerDTO) and dataset is not None:
            return self._choice.build_reply(answer, dataset)
        if kind == "string" and isinstance(answer, TextAnswerDTO):
            return TextReplyDTO(answer.value)
        if kind == "number" and isinstance(answer, TextAnswerDTO):
            return NumberReplyDTO(answer.value)
        if kind == "sql" and isinstance(answer, SqlAnswerDTO):
            return SqlReplyDTO(answer.code)
        if kind == "code" and isinstance(answer, CodeAnswerDTO):
            if answer.language not in code_languages:
                msg = "code language does not belong to this attempt"
                raise ValidationError(msg)
            return CodeReplyDTO(answer.language, answer.code)
        msg = f"answer kind does not match Stepik block type {kind!r}"
        raise UnsupportedTaskError(msg)

    @staticmethod
    def is_supported(kind: str) -> bool:
        return kind in {"choice", "string", "number", "sql", "code", "fill-blanks", "matching", "table"}

    @staticmethod
    def is_theory(kind: str) -> bool:
        return kind in {"text", "video"}
