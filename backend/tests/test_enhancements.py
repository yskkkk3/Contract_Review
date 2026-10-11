"""New capability tests: rule engine, redis lock, mcp server, multi-engine parse."""

import os
import tempfile

import pytest

from app.skills.rules import apply_all_rules, apply_rules


class TestRuleEngine:
    def test_prepayment_ratio(self):
        out = apply_rules("预付款比例 40% 在合同签订后支付", "财务与付款")
        assert out and out[0]["risk_level"] == "高"

    def test_penalty_base(self):
        out = apply_rules("乙方逾期付款按日万分之五支付违约金", "违约责任与解除")
        assert out and "基数" in out[0]["risk_analysis"]

    def test_acceptance_standard(self):
        out = apply_rules("采购合同验收由双方组织", "验收交付与质保")
        assert out and out[0]["risk_level"] == "高"

    def test_apply_all_rules(self):
        out = apply_all_rules(["预付款比例 40% 支付", "验收双方组织", "正常条款"])
        assert len(out) >= 2


class TestRedisLock:
    @pytest.mark.asyncio
    async def test_acquire_release(self):
        import fakeredis

        from app.core import redis as redis_mod
        from app.core.cache import acquire_lock, release_lock

        redis_mod.redis_client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        try:
            key, token = "test:lock", "tok-1"
            assert await acquire_lock(key, token, ttl=5)
            assert not await acquire_lock(key, "tok-2", ttl=5)  # 已被占用
            await release_lock(key, token)
            assert await acquire_lock(key, token, ttl=5)  # 释放后可再抢
        finally:
            redis_mod.redis_client = None


class TestMCPServer:
    @pytest.mark.asyncio
    async def test_build_server(self):
        from app.mcp.server import _build_server

        mcp = _build_server()
        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert {"search_knowledge_base", "ask_contract_assistant", "health_check"} <= names


class TestParseFallback:
    def test_txt_parse(self):
        from app.services.document_parse import extract_text_from_file

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("甲方：深圳大学\n乙方：测试公司\n合同金额：100000元")
            path = f.name
        try:
            text = extract_text_from_file(path, "txt")
            assert "深圳大学" in text
        finally:
            os.unlink(path)

    def test_missing_file_raises(self):
        from app.services.document_parse import extract_text_from_file

        with pytest.raises(ValueError):
            extract_text_from_file("/nonexistent/a.pdf", "pdf")
