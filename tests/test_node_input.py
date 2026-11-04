import json
import logging
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
    node.transport.getPeer.return_value = MagicMock(host="203.0.113.7", port=40000)
    return node


@pytest.fixture
def known_node(node):
    """A P2PNode whose remote peer has already identified itself with a welcome message."""
    node.remote_id = "remote"
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


HTTP_REQUEST = b"GET / HTTP/1.1\r\nHost: x\r\nUser-Agent: zgrab/0.x\r\nAccept: */*\r\n\r\n"


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


def test_invalid_utf8_line_does_not_drop_following_message(known_node):
    raw = b"\xfc\xfd\xfe\n" + _encode(_app_message())

    known_node.dataReceived(raw)

    known_node.factory.emit_message.assert_called_once()


@pytest.mark.parametrize("line", [b'"hello"', b"42", b"[1, 2]", b"null", b"true"])
def test_non_object_json_is_rejected(known_node, line):
    known_node.dataReceived(line + b"\n" + _encode(_app_message()))

    # The non-object line is skipped without raising, the valid message still arrives
    known_node.factory.emit_message.assert_called_once()


@pytest.mark.parametrize("raw", [
    HTTP_REQUEST,
    b"\x16\x03\x01\x02\x00\x01\x00\x01\xfc\x03\x03\n",  # TLS ClientHello-like binary
    b'"hello"\n',
    b'{"foo": "bar"}\n',  # JSON object without message_id
])
def test_unidentified_connection_with_invalid_data_is_closed(node, caplog, raw):
    with caplog.at_level(logging.DEBUG, logger="swchp2pcom.node"):
        node.dataReceived(raw)

    node.transport.loseConnection.assert_called_once()
    node.factory.emit_message.assert_not_called()

    # Exactly one WARNING, naming the remote address, and no ERRORs
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(warnings) == 1
    assert "203.0.113.7:40000" in warnings[0].getMessage()
    assert errors == []


def test_data_after_rejection_is_ignored(node, caplog):
    with caplog.at_level(logging.DEBUG, logger="swchp2pcom.node"):
        node.dataReceived(HTTP_REQUEST)
        node.dataReceived(HTTP_REQUEST + _encode(_app_message()))

    node.transport.loseConnection.assert_called_once()
    node.factory.emit_message.assert_not_called()
    assert len([r for r in caplog.records if r.levelno >= logging.WARNING]) == 1


def test_known_peer_with_invalid_data_is_not_closed(known_node, caplog):
    with caplog.at_level(logging.DEBUG, logger="swchp2pcom.node"):
        known_node.dataReceived(b"not json\n" + b'{"foo": "bar"}\n' + _encode(_app_message()))

    known_node.transport.loseConnection.assert_not_called()
    known_node.factory.emit_message.assert_called_once()

    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 2
    assert all("peer remote" in e for e in errors)


def test_unidentified_connection_with_valid_message_is_kept(node):
    node.dataReceived(_encode(_app_message()))

    node.transport.loseConnection.assert_not_called()
    node.factory.emit_message.assert_called_once()
