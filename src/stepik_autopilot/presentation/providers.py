from collections.abc import AsyncIterator  # noqa: TC003

import aiohttp
from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from stepik_autopilot.application.protocols import BatchRepository as BatchProtocol
from stepik_autopilot.application.protocols import IdempotencyRepository as IdempotencyProtocol
from stepik_autopilot.application.protocols import ItemRepository as ItemProtocol
from stepik_autopilot.application.protocols import OperationRepository as OperationProtocol
from stepik_autopilot.application.protocols import RunRepository as RunProtocol
from stepik_autopilot.application.protocols import (
    StepikAccountGateway,
    StepikAttemptGateway,
    StepikCourseGateway,
    StepikSubmissionGateway,
)
from stepik_autopilot.application.protocols import SubmissionRepository as SubmissionProtocol
from stepik_autopilot.application.use_cases.catalog import ListCourses, ReadRunData
from stepik_autopilot.application.use_cases.run import (
    CollectResults,
    CommitBatch,
    ControlRun,
    NextBatch,
    PlanCourse,
    RunStatus,
    StartRun,
)
from stepik_autopilot.core.task_adapters import AdapterRegistry
from stepik_autopilot.infra.repositories import (
    BatchRepository,
    IdempotencyRepository,
    ItemRepository,
    OperationRepository,
    RunRepository,
    SubmissionRepository,
)
from stepik_autopilot.infra.schema import DatabaseInitializer
from stepik_autopilot.infra.stepik import (
    StepikAccountRepository,
    StepikApiClient,
    StepikAttemptRepository,
    StepikCourseRepository,
    StepikRateLimiter,
    StepikSubmissionRepository,
    StepikTokenProvider,
)
from stepik_autopilot.settings import Settings


class ApplicationProvider(Provider):
    @provide(scope=Scope.APP)
    async def create_engine(self, settings: Settings) -> AsyncIterator[AsyncEngine]:
        engine = create_async_engine(str(settings.db.url), echo=settings.db.echo)
        try:
            yield engine
        finally:
            await engine.dispose()

    @provide(scope=Scope.APP)
    async def create_http_session(self) -> AsyncIterator[aiohttp.ClientSession]:
        # aiohttp[speedups] installs aiodns, whose resolver may not be able to
        # reach the system-configured DNS servers.  curl uses the system
        # resolver, so use aiohttp's threaded equivalent for the same network
        # behaviour.
        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
        async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=20)) as session:
            yield session

    @provide(scope=Scope.APP)
    def create_adapter_registry(self) -> AdapterRegistry:
        return AdapterRegistry()

    @provide(scope=Scope.REQUEST)
    async def create_connection(self, engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
        async with engine.connect() as connection:
            yield connection


provider = ApplicationProvider()
provider.provide(DatabaseInitializer, scope=Scope.APP)
provider.provide(IdempotencyRepository, scope=Scope.REQUEST, provides=IdempotencyProtocol)
provider.provide(RunRepository, scope=Scope.REQUEST, provides=RunProtocol)
provider.provide(ItemRepository, scope=Scope.REQUEST, provides=ItemProtocol)
provider.provide(BatchRepository, scope=Scope.REQUEST, provides=BatchProtocol)
provider.provide(OperationRepository, scope=Scope.REQUEST, provides=OperationProtocol)
provider.provide(SubmissionRepository, scope=Scope.REQUEST, provides=SubmissionProtocol)
provider.provide(StepikTokenProvider, scope=Scope.APP)
provider.provide(StepikRateLimiter, scope=Scope.APP)
provider.provide(StepikApiClient, scope=Scope.APP)
provider.provide(StepikAccountRepository, scope=Scope.REQUEST, provides=StepikAccountGateway)
provider.provide(StepikCourseRepository, scope=Scope.REQUEST, provides=StepikCourseGateway)
provider.provide(StepikAttemptRepository, scope=Scope.REQUEST, provides=StepikAttemptGateway)
provider.provide(StepikSubmissionRepository, scope=Scope.REQUEST, provides=StepikSubmissionGateway)
provider.provide(PlanCourse, scope=Scope.REQUEST)
provider.provide(StartRun, scope=Scope.REQUEST)
provider.provide(NextBatch, scope=Scope.REQUEST)
provider.provide(CommitBatch, scope=Scope.REQUEST)
provider.provide(CollectResults, scope=Scope.REQUEST)
provider.provide(ControlRun, scope=Scope.REQUEST)
provider.provide(RunStatus, scope=Scope.REQUEST)
provider.provide(ListCourses, scope=Scope.REQUEST)
provider.provide(ReadRunData, scope=Scope.REQUEST)
