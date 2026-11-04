import json
from unittest.mock import MagicMock

import pytest

from swchp2pcom.node import P2PNode


@pytest.fixture
def node():
    """
    Returns a P2PNode wired to a mocked factory and transport, so incoming
    bytes can be fed directly to dataReceived().
    """
    factory = MagicMock()
    factory.id = "me"
    factory._is_message_seen.return_value = False

    node = P2PNode(factory, MagicMock())
    node.transport = MagicMock()
    return node


def _app_message(message_id="1", **fields):
    message = {
        "message_type": "app_message",
        "message_id": message_id,
        "peer_id": "remote",
        "target_id": "me",
    }
    message.update(fields)
    return message


def _encode(message, ensure_ascii=True):
    return (json.dumps(message, ensure_ascii=ensure_ascii) + "\n").encode("utf-8")


def test_message_in_single_chunk(node):
    node.dataReceived(_encode(_app_message()))

    node.factory.emit_message.assert_called_once()


def test_message_split_across_chunks(node):
    raw = _encode(_app_message())

    node.dataReceived(raw[:10])
    node.factory.emit_message.assert_not_called()

    node.dataReceived(raw[10:])
    node.factory.emit_message.assert_called_once()


def test_multibyte_utf8_split_across_chunks(node):
    message = _app_message(text="Szia, ő")
    raw = _encode(message, ensure_ascii=False)
    cut = raw.index("ő".encode("utf-8")) + 1  # split inside the 2-byte character

    node.dataReceived(raw[:cut])
    node.dataReceived(raw[cut:])

    node.factory.emit_message.assert_called_once()
    _, received = node.factory.emit_message.call_args.args
    assert received["text"] == "Szia, ő"


def test_multiple_messages_in_one_chunk(node):
    raw = _encode(_app_message("1")) + _encode(_app_message("2"))

    node.dataReceived(raw)

    assert node.factory.emit_message.call_count == 2


def test_invalid_utf8_line_does_not_drop_following_message(node):
    raw = b"\xfc\xfd\xfe\n" + _encode(_app_message())

    node.dataReceived(raw)

    node.factory.emit_message.assert_called_once()
