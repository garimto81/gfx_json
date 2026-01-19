"""JsonParser 단위 테스트."""

from __future__ import annotations

import json

import pytest

from src.sync_agent.core.json_parser import JsonParser, ParseResult


@pytest.fixture
def parser():
    """테스트용 JsonParser fixture."""
    return JsonParser()


@pytest.fixture
def sample_json_file(tmp_path):
    """샘플 JSON 파일 생성."""
    data = {
        "session_id": 12345,
        "table_type": "cash",
        "event_title": "Test Event",
        "software_version": "1.0.0",
        "hands": [{"id": 1}, {"id": 2}, {"id": 3}],
        "created_at": "2024-01-01T12:00:00Z",
    }
    file_path = tmp_path / "session_12345.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")
    return str(file_path)


class TestJsonParserParse:
    """parse() 테스트."""

    def test_parse_success(self, parser, sample_json_file):
        """성공적인 파싱."""
        result = parser.parse(sample_json_file, gfx_pc_id="PC01")

        assert result.success is True
        assert result.record is not None
        assert "PC01" in result.record["nas_path"]  # gfx_pc_id가 nas_path에 포함
        assert result.record["session_id"] == 12345
        assert result.record["table_type"] == "MAIN_TABLE"  # cash -> MAIN_TABLE 매핑
        assert result.record["hand_count"] == 3
        assert result.record["file_hash"] is not None
        assert len(result.record["file_hash"]) == 64  # SHA-256

    def test_parse_file_not_found(self, parser):
        """존재하지 않는 파일."""
        result = parser.parse("/nonexistent/file.json", gfx_pc_id="PC01")

        assert result.success is False
        assert result.error == "file_not_found"

    def test_parse_invalid_json(self, parser, tmp_path):
        """잘못된 JSON 형식."""
        file_path = tmp_path / "invalid.json"
        file_path.write_text("{invalid json}", encoding="utf-8")

        result = parser.parse(str(file_path), gfx_pc_id="PC01")

        assert result.success is False
        assert result.error == "json_decode_error"

    def test_parse_encoding_error(self, parser, tmp_path):
        """인코딩 오류."""
        file_path = tmp_path / "bad_encoding.json"
        # 잘못된 바이트 시퀀스 작성
        file_path.write_bytes(b'{"test": "\xff\xfe"}')

        result = parser.parse(str(file_path), gfx_pc_id="PC01")

        assert result.success is False
        assert result.error == "encoding_error"


class TestJsonParserParseContent:
    """parse_content() 테스트."""

    def test_parse_content_success(self, parser):
        """문자열 파싱 성공."""
        content = '{"session_id": 999, "table_type": "tournament"}'

        result = parser.parse_content(content, "test.json", "PC01")

        assert result.success is True
        assert result.record["session_id"] == 999
        assert result.record["table_type"] == "MAIN_TABLE"  # tournament -> MAIN_TABLE 매핑

    def test_parse_content_invalid_json(self, parser):
        """잘못된 JSON 문자열."""
        result = parser.parse_content("not json", "test.json", "PC01")

        assert result.success is False
        assert result.error == "json_decode_error"


class TestJsonParserHash:
    """해시 생성 테스트."""

    def test_hash_consistency(self, parser, tmp_path):
        """동일 내용 = 동일 해시."""
        content = '{"id": 1}'

        file1 = tmp_path / "file1.json"
        file2 = tmp_path / "file2.json"
        file1.write_text(content)
        file2.write_text(content)

        result1 = parser.parse(str(file1), "PC01")
        result2 = parser.parse(str(file2), "PC01")

        assert result1.record["file_hash"] == result2.record["file_hash"]

    def test_hash_different_content(self, parser, tmp_path):
        """다른 내용 = 다른 해시."""
        file1 = tmp_path / "file1.json"
        file2 = tmp_path / "file2.json"
        file1.write_text('{"id": 1}')
        file2.write_text('{"id": 2}')

        result1 = parser.parse(str(file1), "PC01")
        result2 = parser.parse(str(file2), "PC01")

        assert result1.record["file_hash"] != result2.record["file_hash"]


class TestJsonParserSessionId:
    """session_id 추출 테스트."""

    def test_extract_session_id_direct(self, parser):
        """직접 session_id 필드."""
        content = '{"session_id": 123}'
        result = parser.parse_content(content, "test.json", "PC01")

        assert result.record["session_id"] == 123

    def test_extract_session_id_nested(self, parser):
        """중첩된 session.id 필드."""
        content = '{"session": {"id": 456}}'
        result = parser.parse_content(content, "test.json", "PC01")

        assert result.record["session_id"] == 456

    def test_extract_session_id_fallback(self, parser):
        """id 필드 폴백."""
        content = '{"id": 789}'
        result = parser.parse_content(content, "test.json", "PC01")

        assert result.record["session_id"] == 789

    def test_extract_session_id_missing(self, parser):
        """session_id 없음."""
        content = '{"other": "data"}'
        result = parser.parse_content(content, "test.json", "PC01")

        assert result.record["session_id"] is None


class TestJsonParserHandCount:
    """hand_count 추출 테스트."""

    def test_count_hands_array(self, parser):
        """hands 배열에서 카운트."""
        content = '{"session_id": 1, "hands": [1, 2, 3, 4, 5]}'
        result = parser.parse_content(content, "test.json", "PC01")

        assert result.record["hand_count"] == 5

    def test_count_hands_field(self, parser):
        """hand_count 필드."""
        content = '{"session_id": 1, "hand_count": 10}'
        result = parser.parse_content(content, "test.json", "PC01")

        assert result.record["hand_count"] == 10

    def test_count_hands_camel_case(self, parser):
        """handCount 필드 (camelCase)."""
        content = '{"session_id": 1, "handCount": 15}'
        result = parser.parse_content(content, "test.json", "PC01")

        assert result.record["hand_count"] == 15

    def test_count_hands_missing(self, parser):
        """핸드 정보 없음."""
        content = '{"session_id": 1}'
        result = parser.parse_content(content, "test.json", "PC01")

        # hand_count가 0이면 저장 안됨 (falsy)
        assert result.record.get("hand_count", 0) == 0


class TestJsonParserCreatedAt:
    """created_at 추출 테스트."""

    def test_extract_created_at_standard(self, parser):
        """created_at 필드 추출 메서드 직접 테스트."""
        data = {"created_at": "2024-01-01T00:00:00Z"}
        result = parser._extract_created_at(data)

        assert result == "2024-01-01T00:00:00Z"

    def test_extract_created_at_timestamp(self, parser):
        """timestamp 필드."""
        data = {"timestamp": "2024-06-15T12:30:00Z"}
        result = parser._extract_created_at(data)

        assert result == "2024-06-15T12:30:00Z"

    def test_extract_created_at_missing(self, parser):
        """생성 시간 없음."""
        data = {"session_id": 1}
        result = parser._extract_created_at(data)

        assert result is None


class TestJsonParserValidation:
    """구조 검증 테스트."""

    def test_validate_valid_structure(self, parser):
        """유효한 구조."""
        data = {"session_id": 1}
        errors = parser.validate_json_structure(data)

        assert len(errors) == 0

    def test_validate_missing_session_id(self, parser):
        """session_id 없음."""
        data = {"other": "data"}
        errors = parser.validate_json_structure(data)

        assert len(errors) > 0
        assert "session_id" in errors[0]


class TestParseResult:
    """ParseResult 테스트."""

    def test_parse_result_success(self):
        """성공 결과."""
        result = ParseResult(success=True, record={"id": 1})
        assert result.success is True
        assert result.record is not None

    def test_parse_result_failure(self):
        """실패 결과."""
        result = ParseResult(success=False, error="test_error")
        assert result.success is False
        assert result.error == "test_error"
