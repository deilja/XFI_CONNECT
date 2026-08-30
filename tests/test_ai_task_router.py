from bot.services.ai_task_router import AITaskRouter


class Selector:
    def choose(self, task, preferred_provider=None):
        return type("Choice", (), {"provider": "groq", "model": "test-model", "reason": task})()


def test_code_request_routes_to_code():
    routed = AITaskRouter(Selector()).route("проверь ошибку в Python файле")
    assert routed.task_type == "code"
    assert routed.choice.provider == "groq"


def test_generic_request_routes_to_analysis():
    assert AITaskRouter(Selector()).route("проанализируй ситуацию").task_type == "analysis"
