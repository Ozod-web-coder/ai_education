"""Подставной LLM-клиент для тестов: отдаёт заранее заданные ответы и запоминает запросы."""

import copy
import json

from .llm import ChatResult, ToolCall


class FakeLLM:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def chat(self, messages, *, tools=None, tool_choice=None):
        self.calls.append({"messages": copy.deepcopy(messages), "tools": tools, "tool_choice": tool_choice})
        if not self.results:
            raise AssertionError("Неожиданный запрос к модели")
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def text(content: str) -> ChatResult:
    return ChatResult(content=content)


def call(name: str, call_id: str = "call_1", **arguments) -> ChatResult:
    return ChatResult(content="", tool_calls=[ToolCall(id=call_id, name=name, arguments=json.dumps(arguments))])
