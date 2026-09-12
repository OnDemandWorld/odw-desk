"""回归：webchat 结构化 message 帧（{type:"message",content}）不得整串入库（2026-09-12）。"""

from desk.channels.webchat import parse_message_frame


class TestParseMessageFrame:
    def test_message_frame_yields_content(self):
        raw = '{"type": "message", "content": "你好，我的订单还没到"}'
        assert parse_message_frame(raw) == "你好，我的订单还没到"

    def test_plain_text_returns_none(self):
        assert parse_message_frame("你好，我的订单还没到") is None

    def test_read_and_media_frames_return_none(self):
        assert parse_message_frame('{"type": "read", "message_id": "m1"}') is None
        assert parse_message_frame('{"type": "image", "url": "https://x/a.png"}') is None

    def test_malformed_json_returns_none(self):
        assert parse_message_frame("{not json") is None

    def test_empty_content_returns_none(self):
        assert parse_message_frame('{"type": "message", "content": "  "}') is None
