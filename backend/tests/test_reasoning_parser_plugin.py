import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def test_reasoning_parser_plugin_is_tracked_in_backend_and_registers_parser(monkeypatch):
    repo_root = Path(__file__).resolve().parents[2]
    plugin_path = repo_root / "backend" / "vllm_plugins" / "nemotron_nano_v2_reasoning_parser.py"

    assert plugin_path.exists(), f"expected tracked parser plugin at {plugin_path}"

    registered = {}

    def install_module(name: str, module: ModuleType):
        monkeypatch.setitem(sys.modules, name, module)

    protocol_module = ModuleType("vllm.entrypoints.openai.protocol")
    protocol_module.ChatCompletionRequest = type("ChatCompletionRequest", (), {})
    protocol_module.DeltaMessage = type("DeltaMessage", (), {"__init__": lambda self, **kwargs: self.__dict__.update(kwargs)})
    protocol_module.ResponsesRequest = type("ResponsesRequest", (), {})

    logger_module = ModuleType("vllm.logger")
    logger_module.init_logger = lambda name: object()

    reasoning_module = ModuleType("vllm.reasoning")

    class FakeReasoningParser:
        def __init__(self, tokenizer, *args, **kwargs):
            self.model_tokenizer = tokenizer

    class FakeReasoningParserManager:
        @staticmethod
        def register_module(name: str, force: bool = False):
            def decorator(cls):
                registered[name] = {"cls": cls, "force": force}
                return cls

            return decorator

    reasoning_module.ReasoningParser = FakeReasoningParser
    reasoning_module.ReasoningParserManager = FakeReasoningParserManager

    identity_module = ModuleType("vllm.reasoning.identity_reasoning_parser")
    identity_module.IdentityReasoningParser = type(
        "IdentityReasoningParser",
        (FakeReasoningParser,),
        {},
    )

    install_module("vllm", ModuleType("vllm"))
    install_module("vllm.entrypoints", ModuleType("vllm.entrypoints"))
    install_module("vllm.entrypoints.openai", ModuleType("vllm.entrypoints.openai"))
    install_module("vllm.entrypoints.openai.protocol", protocol_module)
    install_module("vllm.logger", logger_module)
    install_module("vllm.reasoning", reasoning_module)
    install_module("vllm.reasoning.identity_reasoning_parser", identity_module)

    spec = importlib.util.spec_from_file_location("nemotron_parser_plugin", plugin_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert "nemotron_nano_v2" in registered
    assert registered["nemotron_nano_v2"]["force"] is True
