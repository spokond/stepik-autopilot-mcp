import sys
from pathlib import Path

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def server_directory(tmp_path: Path) -> Path:
    project = Path(__file__).resolve().parents[1]
    (tmp_path / ".env").write_text((project / ".env.example").read_text())
    return tmp_path


@pytest.mark.anyio
async def test_installed_stdio_server_loads_dotenv_and_serves_mcp(server_directory: Path) -> None:
    parameters = StdioServerParameters(
        command=str(Path(sys.executable).with_name("stepik-autopilot")),
        args=["--transport", "stdio"],
        cwd=server_directory,
    )
    with anyio.fail_after(20):
        async with stdio_client(parameters) as (read, write), ClientSession(read, write) as session:
            initialized = await session.initialize()
            assert initialized.server_info.name == "stepik-autopilot"
            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "stepik_courses",
                "stepik_plan",
                "stepik_theory",
                "stepik_run_start",
                "stepik_run_next",
                "stepik_batch_commit",
                "stepik_results_collect",
                "stepik_run_status",
                "stepik_read",
                "stepik_run_control",
            }
            for tool in tools.tools:
                assert set(tool.input_schema["properties"]) == {"arguments"}
            result = await session.call_tool("stepik_read", {"arguments": {"uris": ["invalid://resource"]}})
            assert not result.is_error
            assert result.structured_content == {
                "result": {"code": "validation_error", "message": "unsupported private resource URI"},
            }
            resources = await session.list_resources()
            assert [str(resource.uri) for resource in resources.resources] == ["stepik://resources"]
            resource = await session.read_resource("stepik://resources")
            assert resource.contents
            prompts = await session.list_prompts()
            assert {prompt.name for prompt in prompts.prompts} == {
                "stepik_autopilot",
                "stepik_resume",
                "stepik_review",
                "stepik_tutor",
            }
    assert (server_directory / "stepik-autopilot.db").is_file()
