from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vllm.tokenizers import TokenizerLike

from vllm.entrypoints.openai.protocol import (
    ChatCompletionRequest,
    DeltaMessage,
    ResponsesRequest,
)
from vllm.logger import init_logger
from vllm.reasoning import ReasoningParser, ReasoningParserManager
from vllm.reasoning.identity_reasoning_parser import IdentityReasoningParser

logger = init_logger(__name__)


class StringThinkReasoningParser(ReasoningParser):
    def __init__(self, tokenizer: "TokenizerLike", *args, **kwargs):
        super().__init__(tokenizer, *args, **kwargs)

        self.think_start = r"<think>"
        self.think_end = r"</think>"

        self.is_think_end = False
        self.streaming_buffer = ""

    def is_reasoning_end(self, input_ids: list[int]) -> bool:
        text = self.model_tokenizer.decode(input_ids)
        return self.think_end in text

    def extract_content_ids(self, input_ids: list[int]) -> list[int]:
        return []

    def extract_reasoning(
        self,
        model_output: str,
        request: ChatCompletionRequest | ResponsesRequest,
    ) -> tuple[str | None, str | None]:
        if model_output.startswith(self.think_start):
            model_output = model_output[len(self.think_start):]

        think_end_idx = model_output.find(self.think_end)
        if think_end_idx >= 0:
            reasoning = model_output[:think_end_idx]
            content = model_output[think_end_idx + len(self.think_end):]
            return reasoning, content

        return model_output, None

    def extract_reasoning_streaming(
        self,
        previous_text: str,
        current_text: str,
        delta_text: str,
        previous_token_ids: Sequence[int],
        current_token_ids: Sequence[int],
        delta_token_ids: Sequence[int],
    ) -> DeltaMessage | None:
        if self.is_think_end:
            return DeltaMessage(content=delta_text)

        self.streaming_buffer += delta_text

        if (think_end_idx := self.streaming_buffer.find(self.think_end)) >= 0:
            self.is_think_end = True
            reasoning = self.streaming_buffer[:think_end_idx]
            content = self.streaming_buffer[think_end_idx + len(self.think_end):]
            self.streaming_buffer = ""
            return DeltaMessage(reasoning=reasoning or None, content=content or None)

        for length in range(len(self.think_end) - 1, 0, -1):
            partial_think_end = self.think_end[:length]
            if self.streaming_buffer.endswith(partial_think_end):
                partial_idx = len(self.streaming_buffer) - len(partial_think_end)
                delta = DeltaMessage(reasoning=self.streaming_buffer[:partial_idx])
                self.streaming_buffer = self.streaming_buffer[partial_idx:]
                return delta

        delta = DeltaMessage(reasoning=self.streaming_buffer)
        self.streaming_buffer = ""
        return delta


@ReasoningParserManager.register_module(name="nemotron_nano_v2", force=True)
class NemotronNanoV2ReasoningParser(ReasoningParser):
    def __init__(self, tokenizer: "TokenizerLike", *args, **kwargs):
        super().__init__(tokenizer, *args, **kwargs)

        chat_kwargs = kwargs.pop("chat_template_kwargs", {}) or {}
        enable_thinking = bool(chat_kwargs.pop("enable_thinking", True))

        if enable_thinking:
            self._parser = StringThinkReasoningParser(tokenizer, *args, **kwargs)
        else:
            self._parser = IdentityReasoningParser(tokenizer, *args, **kwargs)

    def is_reasoning_end(self, input_ids: Sequence[int]) -> bool:
        return self._parser.is_reasoning_end(input_ids)

    def is_reasoning_end_streaming(
        self, input_ids: list[int], delta_ids: list[int]
    ) -> bool:
        return self._parser.is_reasoning_end_streaming(input_ids, delta_ids)

    def extract_content_ids(self, input_ids: list[int]) -> list[int]:
        return self._parser.extract_content_ids(input_ids)

    def extract_reasoning(
        self, model_output: str, request: ChatCompletionRequest
    ) -> tuple[str | None, str | None]:
        return self._parser.extract_reasoning(model_output, request)

    def extract_reasoning_streaming(
        self,
        previous_text: str,
        current_text: str,
        delta_text: str,
        previous_token_ids: Sequence[int],
        current_token_ids: Sequence[int],
        delta_token_ids: Sequence[int],
    ) -> DeltaMessage | None:
        return self._parser.extract_reasoning_streaming(
            previous_text,
            current_text,
            delta_text,
            previous_token_ids,
            current_token_ids,
            delta_token_ids,
        )
