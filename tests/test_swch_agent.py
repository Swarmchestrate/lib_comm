import pytest, socket, uuid

import pytest_twisted
from twisted.internet import reactor
from twisted.internet.task import deferLater

from swch_com.swchagent import SwchAgent

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
    a1, a2 = agent_factory(2)
    # 1. Initiate connection from a1 to a2's listening port
    a1.connect(a2.public_ip, a2.public_port)

    yield deferLater(reactor, 1, lambda: None)

    # 3. Both agents should have exactly one connection established
    assert a1.connectionCount == 1, "a1 did not register the connection"
    assert a2.connectionCount == 1, "a2 did not register the connection"
    # 4. Each agent's Peers registry should have an entry for the other
    peer_info_1 = a1.factory.peers.get_peer_info(a2.peer_id)
    peer_info_2 = a2.factory.peers.get_peer_info(a1.peer_id)
    assert peer_info_1, "a1 has no peer info for a2"
    assert peer_info_2, "a2 has no peer info for a1"
    # (Optionally, assert that the stored host/port match the known addresses)
    assert peer_info_1["public"]["port"] == a2.public_port
    assert peer_info_2["public"]["port"] == a1.public_port

@pytest_twisted.inlineCallbacks
def test_three_agents_connection_1(agent_factory):
    # create 3 agents
    a1, a2, a3 = agent_factory(3)

    # connect a1 → a3 and a2 → a3
    a1.connect(a3.public_ip, a3.public_port)
    a2.connect(a3.public_ip, a3.public_port)

    # let Twisted process connections
    yield deferLater(reactor, 1, lambda: None)

    # initial connectivity checks
    assert a1.connectionCount == 1, "a1 should have one outgoing"
    assert a2.connectionCount == 1, "a2 should have one outgoing"
    assert a3.connectionCount == 2, "a3 should have two incoming"

    # --- validate peer-info lists via get_all_peers_items() ---
    agents = {a1.peer_id: a1, a2.peer_id: a2, a3.peer_id: a3}
    for agent in (a1, a2, a3):
        items = agent.factory.peers.get_all_peers_items()
        # should know exactly two other peers
        assert len(items) == 3, f"{agent.peer_id} knows wrong number of peers: {items}"

        # expected peer_ids
        expected_ids = set(agents)
        seen_ids     = {pid for pid, _ in items}
        assert seen_ids == expected_ids, (
            f"{agent.peer_id} sees wrong peer IDs: expected {expected_ids}, got {seen_ids}"
        )

        # verify public info matches each peer's public_ip/port
        for pid, info in items:
            pub = info.get("public", {})
            peer = agents[pid]
            assert pub.get("host") == peer.public_ip, (
                f"{agent.peer_id} has wrong public.host for {pid}: "
                f"expected {peer.public_ip}, got {pub.get('host')}"
            )
            assert pub.get("port") == peer.public_port, (
                f"{agent.peer_id} has wrong public.port for {pid}: "
                f"expected {peer.public_port}, got {pub.get('port')}"
            )

    # --- now test disconnect behavior ---
    # a1 drops both a2 and a3
    a1.disconnect(a3.peer_id)

    # allow disconnections to propagate
    yield deferLater(reactor, 1, lambda: None)

    # a2 & a3 should have forgotten about a1
    for other in (a2, a3):
        items = other.factory.peers.get_all_peers_items()
        ids   = {pid for pid, _ in items}
        assert a1.peer_id not in ids, (
            f"{other.peer_id} still has {a1.peer_id} in its peers: {ids}"
        )

    # a1 should have an empty peers dict
    assert not a1.factory.peers.get_all_peers_items(), \
        f"{a1.peer_id} did not clear its peers after disconnect"

@pytest_twisted.inlineCallbacks
def test_three_agents_connection_2(agent_factory):
    # create 3 agents
    a1, a2, a3 = agent_factory(3)

    # connect a1 → a2 and a1 → a3
    a1.connect(a2.public_ip, a2.public_port)
    a1.connect(a3.public_ip, a3.public_port)

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
    a2.connect(a3.public_ip, a3.public_port)
    a1.connect(a3.public_ip, a2.public_port)

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
    a1.connect(a2.public_ip, a2.public_port)
    a2.connect(a3.public_ip, a3.public_port)
    a3.connect(a1.public_ip, a1.public_port)

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
    a1, a2 = agent_factory(2)
    received = []

    # Register handler on a2 for "custom_type"
    def on_custom(src_id, body):
        received.append((src_id, body))

    a2.register_message_handler("custom_type", on_custom)

    # Establish connection first
    a1.connect(a2.public_ip, a2.public_port)
    yield deferLater(reactor, 0.2, lambda: None)

    # Send a custom message from a1 → a2
    msg = {
        "message_type": "custom_type",
        "message_id": str(uuid.uuid4()),
        "peer_id": a1.peer_id,
        "message_body": {"content": "Hello, world!"}
    }
    a1.send_message(a2.peer_id, msg)

    # Wait for the message to arrive
    yield deferLater(reactor, 0.2, lambda: None)

    assert len(received) == 1, "Did not receive exactly one message"
    sender_id, body = received[0]
    assert sender_id == a1.peer_id
    assert body == {"content": "Hello, world!"}

@pytest_twisted.inlineCallbacks
def test_peer_discovered_event(agent_factory):
    a1, a2 = agent_factory(2)
    discovered_peers = []

    # Register event handler for peer discovery
    def on_peer_discovered(peer_id):
        discovered_peers.append(peer_id)

    a1.on('peer:discovered', on_peer_discovered)

    # Connect a1 to a2
    a1.connect(a2.public_ip, a2.public_port)
    
    # Wait for connection and discovery
    yield deferLater(reactor, 0.5, lambda: None)

    assert len(discovered_peers) == 1, "Should have discovered exactly one peer"
    assert discovered_peers[0] == a2.peer_id, "Discovered peer ID should match a2's ID"

@pytest_twisted.inlineCallbacks
def test_peer_connected_event(agent_factory):
    a1, a2 = agent_factory(2)
    connection_count = 0

    # Register event handler for peer connection
    def on_peer_connected():
        nonlocal connection_count
        connection_count += 1

    a1.on('peer:connected', on_peer_connected)

    # Connect a1 to a2
    a1.connect(a2.public_ip, a2.public_port)
    
    # Wait for connection
    yield deferLater(reactor, 0.5, lambda: None)

    assert connection_count == 1, "Should have received exactly one connection event"
    assert a1.connectionCount == 1, "a1 should have one active connection"

@pytest_twisted.inlineCallbacks
def test_peer_disconnected_event(agent_factory):
    a1, a2 = agent_factory(2)
    disconnection_count = 0

    # Register event handler for peer disconnection
    def on_peer_disconnected():
        nonlocal disconnection_count
        disconnection_count += 1

    a1.on('peer:disconnected', on_peer_disconnected)

    # First establish connection
    a1.connect(a2.public_ip, a2.public_port)
    
    # Wait for connection to establish
    yield deferLater(reactor, 0.5, lambda: None)
    
    # Verify initial connection
    assert a1.connectionCount == 1, "Initial connection should be established"
    
    # Disconnect from peer
    a1.disconnect(a2.peer_id)
    
    # Wait for disconnection to process
    yield deferLater(reactor, 0.5, lambda: None)

    assert disconnection_count == 1, "Should have received exactly one disconnection event"
    assert a1.connectionCount == 0, "a1 should have no active connections"