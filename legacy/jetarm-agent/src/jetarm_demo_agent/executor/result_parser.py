from jetarm_demo_agent.schemas import ExecutorResult


def parse_executor_result(payload: dict) -> ExecutorResult:
    return ExecutorResult.model_validate(payload)
