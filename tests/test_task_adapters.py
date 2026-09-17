import pytest

from stepik_autopilot.application.dto import CodeAnswerDTO, CodeReplyDTO, NumberReplyDTO, TextAnswerDTO, TextReplyDTO
from stepik_autopilot.core.exceptions import ValidationError
from stepik_autopilot.core.task_adapters import AdapterRegistry


def test_text_and_number_answers_use_distinct_replies() -> None:
    adapters = AdapterRegistry()

    string_reply = adapters.build_reply("string", TextAnswerDTO("answer"), None, ())
    number_reply = adapters.build_reply("number", TextAnswerDTO("0.0000000000001"), None, ())

    assert isinstance(string_reply, TextReplyDTO)
    assert isinstance(number_reply, NumberReplyDTO)
    assert string_reply.text == "answer"
    assert number_reply.number == "0.0000000000001"


def test_code_answer_requires_language_from_attempt() -> None:
    adapters = AdapterRegistry()

    reply = adapters.build_reply("code", CodeAnswerDTO("python3", "print(1)"), None, ("python3",))
    assert isinstance(reply, CodeReplyDTO)
    assert reply.language == "python3"

    with pytest.raises(ValidationError, match="code language does not belong to this attempt"):
        adapters.build_reply("code", CodeAnswerDTO("java", "class Main {}"), None, ("python3",))
