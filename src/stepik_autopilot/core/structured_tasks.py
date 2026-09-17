from collections.abc import Mapping

from stepik_autopilot.application.dto import (
    BlanksAnswerDTO,
    BlanksReplyDTO,
    MatchingAnswerDTO,
    MatchingReplyDTO,
    TableAnswerDTO,
    TableCellDTO,
    TableReplyDTO,
    TableRowDTO,
)
from stepik_autopilot.core.exceptions import UnsupportedTaskError, ValidationError

STRUCTURED_KINDS = frozenset({"fill-blanks", "matching", "table"})


def strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        msg = "quiz dataset must contain a list of strings"
        raise UnsupportedTaskError(msg)
    return tuple(value)


def components(data: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw = data.get("components")
    if not isinstance(raw, list) or not raw or not all(isinstance(value, Mapping) for value in raw):
        msg = "fill-blanks dataset has no confirmed components"
        raise UnsupportedTaskError(msg)
    for component in raw:
        if component.get("type") not in {"text", "input", "select"}:
            msg = "unsupported fill-blanks component type"
            raise UnsupportedTaskError(msg)
        if component.get("text") is not None and not isinstance(component["text"], str):
            msg = "fill-blanks component text must be a string"
            raise UnsupportedTaskError(msg)
        if component.get("type") == "select" and not strings(component.get("options")):
            msg = "fill-blanks select component has no options"
            raise UnsupportedTaskError(msg)
    return tuple(raw)


def matching_pairs(data: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw = data.get("pairs")
    if (
        not isinstance(raw, list)
        or not raw
        or not all(
            isinstance(pair, Mapping) and isinstance(pair.get("first"), str) and isinstance(pair.get("second"), str)
            for pair in raw
        )
    ):
        msg = "matching dataset has no confirmed pairs"
        raise UnsupportedTaskError(msg)
    return tuple(raw)


def table_dimensions(data: Mapping[str, object]) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
    rows, columns = strings(data.get("rows")), strings(data.get("columns"))
    checkbox = data.get("is_checkbox", False)
    if not rows or not columns or not isinstance(checkbox, bool):
        msg = "table dataset has invalid rows, columns or selection mode"
        raise UnsupportedTaskError(msg)
    return rows, columns, checkbox


def validate_quiz_data(kind: str, data: Mapping[str, object]) -> dict[str, object]:
    if kind == "fill-blanks":
        components(data)
    elif kind == "matching":
        matching_pairs(data)
    elif kind == "table":
        table_dimensions(data)
    else:
        msg = f"unsupported structured quiz {kind!r}"
        raise UnsupportedTaskError(msg)
    return dict(data)


def blanks_reply(answer: BlanksAnswerDTO, data: Mapping[str, object]) -> BlanksReplyDTO:
    blanks = tuple(component for component in components(data) if component["type"] != "text")
    if len(answer.blanks) != len(blanks):
        msg = "fill-blanks answer must contain one value per input/select component"
        raise ValidationError(msg)
    for value, component in zip(answer.blanks, blanks, strict=True):
        if component["type"] == "select" and value not in strings(component.get("options")):
            msg = "fill-blanks value does not belong to this attempt"
            raise ValidationError(msg)
    return BlanksReplyDTO(answer.blanks)


def matching_reply(answer: MatchingAnswerDTO, data: Mapping[str, object]) -> MatchingReplyDTO:
    size = len(matching_pairs(data))
    if any(type(index) is not int for index in answer.ordering) or sorted(answer.ordering) != list(range(size)):
        msg = "matching ordering must be a permutation of this attempt's zero-based pair indexes"
        raise ValidationError(msg)
    return MatchingReplyDTO(answer.ordering)


def table_reply(answer: TableAnswerDTO, data: Mapping[str, object]) -> TableReplyDTO:
    rows, columns, checkbox = table_dimensions(data)
    if len(answer.selected_columns) != len(rows):
        msg = "table answer must contain a selection for every row"
        raise ValidationError(msg)
    for selected in answer.selected_columns:
        if (
            len(selected) != len(set(selected))
            or any(type(index) is not int or index < 0 or index >= len(columns) for index in selected)
            or (not checkbox and len(selected) != 1)
        ):
            msg = "table column selection does not belong to this attempt or selection mode"
            raise ValidationError(msg)
    return TableReplyDTO(
        tuple(
            TableRowDTO(row, tuple(TableCellDTO(column, index in selected) for index, column in enumerate(columns)))
            for row, selected in zip(rows, answer.selected_columns, strict=True)
        )
    )
