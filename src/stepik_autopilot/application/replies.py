import hashlib
import json
from typing import TYPE_CHECKING

from stepik_autopilot.application.dto import (
    BlanksReplyDTO,
    ChoiceReplyDTO,
    CodeReplyDTO,
    MatchingReplyDTO,
    NumberReplyDTO,
    SqlReplyDTO,
    TableReplyDTO,
    TextReplyDTO,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


type ReplyDTO = (
    ChoiceReplyDTO
    | TextReplyDTO
    | NumberReplyDTO
    | SqlReplyDTO
    | CodeReplyDTO
    | BlanksReplyDTO
    | MatchingReplyDTO
    | TableReplyDTO
)


def reply_payload(reply: ReplyDTO) -> dict[str, object]:  # noqa: PLR0911 - One branch per wire format.
    if isinstance(reply, BlanksReplyDTO):
        return {"blanks": list(reply.blanks)}
    if isinstance(reply, MatchingReplyDTO):
        return {"ordering": list(reply.ordering)}
    if isinstance(reply, TableReplyDTO):
        return {
            "choices": [
                {
                    "name_row": row.name_row,
                    "columns": [{"name": cell.name, "answer": cell.answer} for cell in row.columns],
                }
                for row in reply.choices
            ]
        }
    if isinstance(reply, ChoiceReplyDTO):
        return {"choices": list(reply.choices)}
    if isinstance(reply, TextReplyDTO):
        return {"text": reply.text}
    if isinstance(reply, NumberReplyDTO):
        return {"number": reply.number}
    if isinstance(reply, SqlReplyDTO):
        return {"solve_sql": reply.solve_sql}
    return {"language": reply.language, "code": reply.code}


def hash_payload(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def hash_reply(reply: ReplyDTO) -> str:
    return hash_payload(reply_payload(reply))
