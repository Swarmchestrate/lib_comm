import pytest, socket, uuid

import pytest_twisted
from twisted.internet import reactor
from twisted.internet.task import deferLater

from swch_com.swch_com import SwchAgent

@pytest.fixture
def two_agents():
    """Fixture to start two SwchAgent instances on random local ports and tear them down."""
    host = "127.0.0.1"
    # Find two free TCP ports for the agents
    s1, s2 = socket.socket(), socket.socket()
    s1.bind((host, 0)); port1 = s1.getsockname()[1]; s1.close()
    s2.bind((host, 0)); port2 = s2.getsockname()[1]; s2.close()
    # Initialize two agents with the chosen ports
    agent1 = SwchAgent("agent1", "test_universe", "ra", listen_ip=host, listen_port=port1)
    agent2 = SwchAgent("agent2", "test_universe", "ra", listen_ip=host, listen_port=port2)

    # Yield the agents for testing
    yield agent1, agent2

@pytest_twisted.inlineCallbacks
def test_agent_connection_and_peers(two_agents):
    agent1, agent2 = two_agents
    # 1. Initiate connection from agent1 to agent2's listening port
    agent1.connect_to_peer("127.0.0.1", agent2.factory.public_port)

    yield deferLater(reactor, 0.2, lambda: None)

    # 3. Both agents should have exactly one connection established
    assert agent1.connectionCount == 1, "agent1 did not register the connection"
    assert agent2.connectionCount == 1, "agent2 did not register the connection"
    # 4. Each agent's Peers registry should have an entry for the other
    peer_info_1 = agent1.factory.peers.get_peer_info(agent2.factory.id)
    peer_info_2 = agent2.factory.peers.get_peer_info(agent1.factory.id)
    assert peer_info_1, "agent1 has no peer info for agent2"
    assert peer_info_2, "agent2 has no peer info for agent1"
    # (Optionally, assert that the stored host/port match the known addresses)
    assert peer_info_1["public"]["port"] == agent2.factory.public_port
    assert peer_info_2["public"]["port"] == agent1.factory.public_port

@pytest_twisted.inlineCallbacks
def test_custom_message_exchange(two_agents):
    agent1, agent2 = two_agents
    received = []

    # Register handler on agent2 for "custom_type"
    def on_custom(src_id, body):
        received.append((src_id, body))

    agent2.register_message_handler("custom_type", on_custom)

    # Establish connection first
    agent1.connect_to_peer("127.0.0.1", agent2.factory.public_port)
    yield deferLater(reactor, 0.2, lambda: None)

    # Send a custom message from agent1 → agent2
    msg = {
        "message_type": "custom_type",
        "message_id": str(uuid.uuid4()),
        "peer_id": agent1.factory.id,
        "message_body": {"content": "Hello, world!"}
    }
    agent1.send_message(agent2.factory.id, msg)

    # Wait for the message to arrive
    yield deferLater(reactor, 0.2, lambda: None)

    assert len(received) == 1, "Did not receive exactly one message"
    sender_id, body = received[0]
    assert sender_id == agent1.factory.id
    assert body == {"content": "Hello, world!"}