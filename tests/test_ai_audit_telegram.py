import pytest

from bot.services.ai_audit_telegram import AIAuditTelegramReporter
from bot.services.ai_repo_auditor import AuditFinding, AuditReport


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text, kwargs))


@pytest.mark.asyncio
async def test_reporter_sends_findings():
    bot = FakeBot()
    reporter = AIAuditTelegramReporter(bot, [101, 202])
    report = AuditReport(3, (AuditFinding("high", "x.py", "Найден eval()", "check"),), "fp")
    await reporter(report)
    assert [m[0] for m in bot.messages] == [101, 202]
    assert "Найден eval()" in bot.messages[0][1]


@pytest.mark.asyncio
async def test_reporter_skips_empty_report():
    bot = FakeBot()
    await AIAuditTelegramReporter(bot, [101])(AuditReport(3, (), "fp"))
    assert bot.messages == []
