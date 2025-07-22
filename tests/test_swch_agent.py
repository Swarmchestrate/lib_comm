import pytest, socket, uuid

import pytest_twisted
from twisted.internet import reactor
from twisted.internet.task import deferLater

from swch_com.swch_com import SwchAgent

@pytest.fixture
def agent_factory():
    """
    Returns a function create_agents(n, *, prefix="agent") → List[SwchAgent].
    """
    host = "127.0.0.1"
    created = []

    def _create(num_agents, *, universe="test_universe", role="ra", prefix="agent"):
        agents = []
        for i in range(num_agents):
            # pick an ephemeral port
            sock = socket.socket()
            sock.bind((host, 0))
            port = sock.getsockname()[1]
            sock.close()

            agent_id = f"{prefix}{i+1}"
            agent = SwchAgent(agent_id, universe, role,
                              listen_ip=host, listen_port=port)
            agents.append(agent)
            created.append(agent)
        return agents

    yield _create

@pytest_twisted.inlineCallbacks
def test_two_agents_connection(agent_factory):
    agent1, agent2 = agent_factory(2)
    # 1. Initiate connection from agent1 to agent2's listening port
    agent1.connect_to_peer("127.0.0.1", agent2.factory.public_port)

    yield deferLater(reactor, 1, lambda: None)

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
def test_three_agents_connection_1(agent_factory):
    # create 3 agents
    a1, a2, a3 = agent_factory(3)

    # connect a1 → a3 and a2 → a3
    a1.connect_to_peer("127.0.0.1", a3.factory.public_port)
    a2.connect_to_peer("127.0.0.1", a3.factory.public_port)

    # let Twisted do its thing
    yield deferLater(reactor, 1, lambda: None)

    # each peer should see exactly one outgoing on their side
    assert a1.connectionCount == 1
    assert a2.connectionCount == 1
    # a3 made two ingoing connections
    assert a3.connectionCount == 2

    peer_info_a1 = a1.factory.peers.get_all_public_info()
    peer_info_a2 = a2.factory.peers.get_all_public_info()
    peer_info_a3 = a3.factory.peers.get_all_public_info()

    # Sort the lists to ensure consistent ordering
    sorted_a1 = sorted(peer_info_a1, key=lambda x: x['port'])
    sorted_a2 = sorted(peer_info_a2, key=lambda x: x['port'])
    sorted_a3 = sorted(peer_info_a3, key=lambda x: x['port'])

    # Assert that all peers see the same network topology
    assert sorted_a1 == sorted_a2 == sorted_a3, "Peer information lists are not identical"

@pytest_twisted.inlineCallbacks
def test_three_agents_connection_2(agent_factory):
    # create 3 agents
    a1, a2, a3 = agent_factory(3)

    # connect a1 → a2 and a1 → a3
    a1.connect_to_peer("127.0.0.1", a2.factory.public_port)
    a1.connect_to_peer("127.0.0.1", a3.factory.public_port)

    # let Twisted do its thing
    yield deferLater(reactor, 1, lambda: None)

    # each peer should see exactly one incoming on their side
    assert a2.connectionCount == 1
    assert a3.connectionCount == 1
    # a1 made two outgoing connections
    assert a1.connectionCount == 2

    peer_info_a1 = a1.factory.peers.get_all_public_info()
    peer_info_a2 = a2.factory.peers.get_all_public_info()
    peer_info_a3 = a3.factory.peers.get_all_public_info()

    # Sort the lists to ensure consistent ordering
    sorted_a1 = sorted(peer_info_a1, key=lambda x: x['port'])
    sorted_a2 = sorted(peer_info_a2, key=lambda x: x['port'])
    sorted_a3 = sorted(peer_info_a3, key=lambda x: x['port'])

    # Assert that all peers see the same network topology
    assert sorted_a1 == sorted_a2 == sorted_a3, "Peer information lists are not identical"

@pytest_twisted.inlineCallbacks
def test_three_agents_connection_3(agent_factory):
    # create 3 agents
    a1, a2, a3 = agent_factory(3)

    # connect a2 → a3 and a1 → a2
    a2.connect_to_peer("127.0.0.1", a3.factory.public_port)
    a1.connect_to_peer("127.0.0.1", a2.factory.public_port)

    # let Twisted do its thing
    yield deferLater(reactor, 1, lambda: None)

    # a1 should have one outgoing connection to a2
    assert a1.connectionCount == 1
    # a3 should have one incoming connection from a2
    assert a3.connectionCount == 1
    # a2 should have two connections: one incoming from a1 and one outgoing to a3
    assert a2.connectionCount == 2

    peer_info_a1 = a1.factory.peers.get_all_public_info()
    peer_info_a2 = a2.factory.peers.get_all_public_info()
    peer_info_a3 = a3.factory.peers.get_all_public_info()

    # Sort the lists to ensure consistent ordering
    sorted_a1 = sorted(peer_info_a1, key=lambda x: x['port'])
    sorted_a2 = sorted(peer_info_a2, key=lambda x: x['port'])
    sorted_a3 = sorted(peer_info_a3, key=lambda x: x['port'])

    # Assert that all peers see the same network topology
    assert sorted_a1 == sorted_a2 == sorted_a3, "Peer information lists are not identical"

@pytest_twisted.inlineCallbacks
def test_three_agents_connection_4(agent_factory):
    # create 3 agents
    a1, a2, a3 = agent_factory(3)

    # connect a2 → a3 and a1 → a2
    a1.connect_to_peer("127.0.0.1", a2.factory.public_port)
    a2.connect_to_peer("127.0.0.1", a3.factory.public_port)
    a3.connect_to_peer("127.0.0.1", a1.factory.public_port)

    # let Twisted do its thing
    yield deferLater(reactor, 1, lambda: None)

    # a1 should have two connections: one incoming from a3 and one outgoing to a2
    assert a1.connectionCount == 2
    # a2 should have two connections: one incoming from a1 and one outgoing to a3
    assert a2.connectionCount == 2
    # a3 should have two connections: one incoming from a2 and one outgoing to a1
    assert a3.connectionCount == 2

    peer_info_a1 = a1.factory.peers.get_all_public_info()
    peer_info_a2 = a2.factory.peers.get_all_public_info()
    peer_info_a3 = a3.factory.peers.get_all_public_info()

    # Sort the lists to ensure consistent ordering
    sorted_a1 = sorted(peer_info_a1, key=lambda x: x['port'])
    sorted_a2 = sorted(peer_info_a2, key=lambda x: x['port'])
    sorted_a3 = sorted(peer_info_a3, key=lambda x: x['port'])

    # Assert that all peers see the same network topology
    assert sorted_a1 == sorted_a2 == sorted_a3, "Peer information lists are not identical"

@pytest_twisted.inlineCallbacks
def test_custom_message_exchange(agent_factory):
    agent1, agent2 = agent_factory(2)
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