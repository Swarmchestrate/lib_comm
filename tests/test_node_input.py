import json
import logging
from unittest.mock import MagicMock

import pytest

from swchp2pcom.message_types import SystemMessageType
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


def test_oversized_message_from_unidentified_connection_is_closed(node, caplog, monkeypatch):
    monkeypatch.setattr(P2PNode, "MAX_UNIDENTIFIED_MESSAGE_SIZE", 100)

    with caplog.at_level(logging.DEBUG, logger="swchp2pcom.node"):
        node.dataReceived(b"x" * 60)
        node.transport.loseConnection.assert_not_called()
        node.dataReceived(b"x" * 60)

    node.transport.loseConnection.assert_called_once()
    assert node.buffer == b""
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "203.0.113.7:40000" in warnings[0] and "exceeds 100 bytes" in warnings[0]


def test_unidentified_message_within_limit_split_across_chunks_is_accepted(node, monkeypatch):
    raw = _encode(_app_message(text="x" * 150))
    monkeypatch.setattr(P2PNode, "MAX_UNIDENTIFIED_MESSAGE_SIZE", len(raw))

    for i in range(0, len(raw), 32):
        node.dataReceived(raw[i:i + 32])

    node.transport.loseConnection.assert_not_called()
    node.factory.emit_message.assert_called_once()


def test_complete_messages_before_oversized_tail_are_processed(node, monkeypatch):
    monkeypatch.setattr(P2PNode, "MAX_UNIDENTIFIED_MESSAGE_SIZE", 100)

    node.dataReceived(_encode(_app_message()) + b"x" * 101)

    node.factory.emit_message.assert_called_once()
    node.transport.loseConnection.assert_called_once()


def test_known_peer_message_size_is_not_limited(known_node, monkeypatch):
    monkeypatch.setattr(P2PNode, "MAX_UNIDENTIFIED_MESSAGE_SIZE", 100)
    raw = _encode(_app_message(text="x" * 1000))

    for i in range(0, len(raw), 32):
        known_node.dataReceived(raw[i:i + 32])

    known_node.transport.loseConnection.assert_not_called()
    known_node.factory.emit_message.assert_called_once()


def test_size_limit_is_lifted_after_welcome_message(node, monkeypatch):
    monkeypatch.setattr(P2PNode, "MAX_UNIDENTIFIED_MESSAGE_SIZE", 100)
    welcome = {
        "message_type": SystemMessageType.SEND_WELCOME_INFO.value,
        "message_id": "welcome",
        "peer_id": "remote",
        "peer_public_info": {"host": "203.0.113.7", "port": 5000},
        "peers": [],
    }
    large = _encode(_app_message(text="x" * 1000))

    # Welcome and the start of a large message arrive in the same chunk
    node.dataReceived(_encode(welcome) + large[:500])
    node.dataReceived(large[500:])

    assert node.remote_id == "remote"
    node.transport.loseConnection.assert_not_called()
    node.factory.emit_message.assert_called_once()


@pytest.mark.parametrize("is_initiator", [False, True])
def test_connection_made_is_logged_at_debug_with_address(node, caplog, is_initiator):
    node.is_initiator = is_initiator
    node.transport.getHost.return_value = MagicMock(host="0.0.0.0", port=5000)

    with caplog.at_level(logging.DEBUG, logger="swchp2pcom.node"):
        node.connectionMade()

    # Nothing above DEBUG, the remote is not identified yet
    assert [r for r in caplog.records if r.levelno > logging.DEBUG] == []
    assert any("203.0.113.7:40000" in r.getMessage() for r in caplog.records)
