import argparse
import asyncio
from contextlib import asynccontextmanager
from functools import partial, update_wrapper
from typing import TYPE_CHECKING

from dishka import AsyncContainer, make_async_container
from mcp.server import MCPServer
from mcp.server.mcpserver.prompts.base import Prompt
from mcp.server.mcpserver.resources.types import FunctionResource

from stepik_autopilot.infra.schema import DatabaseInitializer
from stepik_autopilot.presentation.promts import autopilot_prompt, resume_prompt, review_prompt, tutor_prompt
from stepik_autopilot.presentation.providers import provider
from stepik_autopilot.presentation.resources import resource_index
from stepik_autopilot.presentation.tools import (
    stepik_batch_commit,
    stepik_courses,
    stepik_plan,
    stepik_read,
    stepik_results_collect,
    stepik_run_control,
    stepik_run_next,
    stepik_run_start,
    stepik_run_status,
    stepik_theory,
)
from stepik_autopilot.settings import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable


def build_mcp(settings: Settings) -> MCPServer:
    container = make_async_container(provider, context={Settings: settings})

    @asynccontextmanager
    async def lifespan(_: MCPServer) -> AsyncGenerator[None]:
        await (await container.get(DatabaseInitializer)).initialize()
        try:
            yield None
        finally:
            await container.close()

    mcp: MCPServer = MCPServer(name="stepik-autopilot", title="Stepik Autopilot", version="0.1.0", lifespan=lifespan)
    mcp.add_tool(bind_handler(stepik_courses, container), name="stepik_courses", description="List accessible courses.")
    mcp.add_tool(
        bind_handler(stepik_plan, container),
        name="stepik_plan",
        description="Inspect a course without attempts. section_numbers or explicit_step_ids select explicit scope.",
    )
    mcp.add_tool(
        bind_handler(stepik_theory, container),
        name="stepik_theory",
        description="List text lectures and their source HTML without attempts or submissions.",
    )
    mcp.add_tool(bind_handler(stepik_run_start, container), name="stepik_run_start", description="Start a durable run.")
    mcp.add_tool(bind_handler(stepik_run_next, container), name="stepik_run_next", description="Lease the next batch.")
    mcp.add_tool(
        bind_handler(stepik_batch_commit, container),
        name="stepik_batch_commit",
        description="Save or submit answers; retry confirmed wrong string, number or code items with action=retry.",
    )
    mcp.add_tool(
        bind_handler(stepik_results_collect, container), name="stepik_results_collect", description="Collect outcomes."
    )
    mcp.add_tool(bind_handler(stepik_run_status, container), name="stepik_run_status", description="Read run status.")
    mcp.add_tool(bind_handler(stepik_read, container), name="stepik_read", description="Read a private run URI.")
    mcp.add_tool(bind_handler(stepik_run_control, container), name="stepik_run_control", description="Control a run.")
    mcp.add_prompt(Prompt.from_function(autopilot_prompt, name="stepik_autopilot"))
    mcp.add_prompt(Prompt.from_function(resume_prompt, name="stepik_resume"))
    mcp.add_prompt(Prompt.from_function(review_prompt, name="stepik_review"))
    mcp.add_prompt(Prompt.from_function(tutor_prompt, name="stepik_tutor"))
    mcp.add_resource(
        FunctionResource.from_function(
            resource_index,
            "stepik://resources",
            name="stepik-resources",
            description="Dynamic run, item and submission reads are available through stepik_read.",
        )
    )

    return mcp


def bind_handler(handler: Callable[..., object], container: AsyncContainer) -> Callable[..., object]:
    bound = update_wrapper(partial(handler, container), handler)
    # Keep the partial's signature so MCP does not expose the bound DI container.
    del bound.__wrapped__
    return bound


async def run_mcp(settings: Settings, transport: str, host: str, port: int) -> None:
    mcp = build_mcp(settings)
    if transport == "stdio":
        await mcp.run_stdio_async()
    else:
        await mcp.run_streamable_http_async(host=host, port=port)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stepik Autopilot MCP")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    arguments = parser.parse_args()
    asyncio.run(run_mcp(Settings(), arguments.transport, arguments.host, arguments.port))  # pyright: ignore[reportCallIssue]
