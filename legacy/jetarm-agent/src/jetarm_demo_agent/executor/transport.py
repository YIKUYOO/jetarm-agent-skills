from typing import Protocol

from jetarm_demo_agent.schemas import TaskRequest


class ExecutorTransport(Protocol):
    def health(self) -> dict: ...

    def run_task(self, task: TaskRequest) -> dict: ...
