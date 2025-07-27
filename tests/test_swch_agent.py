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
    assert a1.get_connection_count() == 1, "a1 did not register the connection"
    assert a2.get_connection_count() == 1, "a2 did not register the connection"
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
    assert a1.get_connection_count() == 1, "a1 should have one outgoing"
    assert a2.get_connection_count() == 1, "a2 should have one outgoing"
    assert a3.get_connection_count() == 2, "a3 should have two incoming"

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

    # --- now test shutdown behavior ---
    # a2 drops both a1 and a3
    a2.shutdown()

    # allow disconnections to propagate
    yield deferLater(reactor, 1, lambda: None)

    # a1 & a3 should have forgotten about a2
    for other in (a1, a3):
        items = other.factory.peers.get_all_peers_items()
        ids   = {pid for pid, _ in items}
        assert a2.peer_id not in ids, (
            f"{other.peer_id} still has {a2.peer_id} in its peers: {ids}"
        )

    # a2 should have an empty peers dict
    assert not a2.factory.peers.get_all_peers_items(), \
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
    assert a2.get_connection_count() == 1
    assert a3.get_connection_count() == 1
    # a1 made two outgoing connections
    assert a1.get_connection_count() == 2

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
    assert a1.get_connection_count() == 1
    # a3 should have one incoming connection from a2
    assert a3.get_connection_count() == 1
    # a2 should have two connections: one incoming from a1 and one outgoing to a3
    assert a2.get_connection_count() == 2

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
    assert a1.get_connection_count() == 2
    # a2 should have two connections: one incoming from a1 and one outgoing to a3
    assert a2.get_connection_count() == 2
    # a3 should have two connections: one incoming from a2 and one outgoing to a1
    assert a3.get_connection_count() == 2

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
def test_custom_message_exchange_1(agent_factory):
    # Create 3 agents
    a1, a2, a3 = agent_factory(3)
    received_messages = {
        a1.peer_id: [],
        a2.peer_id: [],
        a3.peer_id: []
    }

    # Register message event handlers for all agents
    def create_message_event_handler(agent_id):
        def on_message(data):
            received_messages[agent_id].append(data)
        return on_message

    for agent in [a1, a2, a3]:
        agent.on('message', create_message_event_handler(agent.peer_id))

    # Connect agents in a triangle
    a1.connect(a2.public_ip, a2.public_port)
    a2.connect(a3.public_ip, a3.public_port)
    
    # Wait for connections to establish
    yield deferLater(reactor, 0.5, lambda: None)

    # Send a message from a1 to a2
    test_payload = {"content": "Hello, agent 2!"}
    a1.send(a2.peer_id, "custom_type", test_payload)

    # Wait for message to be processed
    yield deferLater(reactor, 0.5, lambda: None)

    # Verify only a2 received the message
    assert len(received_messages[a1.peer_id]) == 0, "a1 should not receive any messages"
    assert len(received_messages[a2.peer_id]) == 1, "a2 should receive exactly one message"
    assert len(received_messages[a3.peer_id]) == 0, "a3 should not receive any messages"

    # Verify message contents
    received = received_messages[a2.peer_id][0]
    assert received['peer_id'] == a1.peer_id, "Message should be from a1"
    assert received['message_type'] == "custom_type", "Message type should match"
    assert received['payload'] == test_payload, "Message payload should match"

@pytest_twisted.inlineCallbacks
def test_custom_message_exchange_with_multiconnection(agent_factory):
    # Create 2 agents
    a1, a2 = agent_factory(2)
    received_messages = {
        a1.peer_id: [],
        a2.peer_id: []
    }

    # Register message event handlers for both agents
    def create_message_event_handler(agent_id):
        def on_message(data):
            received_messages[agent_id].append(data)
        return on_message

    for agent in [a1, a2]:
        agent.on('message', create_message_event_handler(agent.peer_id))

    # Create bidirectional connections - each agent connects to the other
    a1.connect(a2.public_ip, a2.public_port)
    a2.connect(a1.public_ip, a1.public_port)
    
    # Wait for connections to establish
    yield deferLater(reactor, 0.5, lambda: None)

    # Verify both agents have connections (may be 1 or 2 depending on implementation)
    assert a1.get_connection_count() >= 1, "a1 should have at least one connection"
    assert a2.get_connection_count() >= 1, "a2 should have at least one connection"

    # Send a message from a1 to a2
    test_payload = {"content": "Hello with multiple connections!"}
    a1.send(a2.peer_id, "multi_connection_test", test_payload)

    # Wait for message to be processed
    yield deferLater(reactor, 0.5, lambda: None)

    # Verify a2 received the message exactly once despite potential multiple connections
    assert len(received_messages[a1.peer_id]) == 0, "a1 should not receive any messages"
    assert len(received_messages[a2.peer_id]) == 1, "a2 should receive exactly one message"

    # Verify message contents
    received = received_messages[a2.peer_id][0]
    assert received['peer_id'] == a1.peer_id, "Message should be from a1"
    assert received['message_type'] == "multi_connection_test", "Message type should match"
    assert received['payload'] == test_payload, "Message payload should match"

@pytest_twisted.inlineCallbacks
def test_indirect_message_exchange(agent_factory):
    # Create 3 agents in a linear topology: a1 <-> a2 <-> a3
    a1, a2, a3 = agent_factory(3)
    received_messages = {
        a1.peer_id: [],
        a2.peer_id: [],
        a3.peer_id: []
    }

    # Register message event handlers for all agents
    def create_message_event_handler(agent_id):
        def on_message(data):
            received_messages[agent_id].append(data)
        return on_message

    for agent in [a1, a2, a3]:
        agent.on('message', create_message_event_handler(agent.peer_id))

    # Connect agents linearly: a1 -> a2 -> a3
    a1.connect(a2.public_ip, a2.public_port)
    a2.connect(a3.public_ip, a3.public_port)
    
    # Wait for connections to establish
    yield deferLater(reactor, 0.5, lambda: None)

    # Verify initial connectivity
    assert a1.get_connection_count() == 1, "a1 should have one connection"
    assert a2.get_connection_count() == 2, "a2 should have two connections"
    assert a3.get_connection_count() == 1, "a3 should have one connection"

    # Try sending message from a1 to a3 (they're not directly connected)
    test_payload_1 = {"content": "Hello from a1 to a3!"}
    a1.send(a3.peer_id, "indirect_message", test_payload_1)

    # Try sending message from a3 to a1 (reverse direction)
    test_payload_2 = {"content": "Hello from a3 to a1!"}
    a3.send(a1.peer_id, "indirect_message", test_payload_2)

    # Wait for messages to be processed
    yield deferLater(reactor, 0.5, lambda: None)

    # Verify a3 received the message from a1
    assert len(received_messages[a3.peer_id]) == 1, "a3 should receive exactly one message"
    received_by_a3 = received_messages[a3.peer_id][0]
    assert received_by_a3['peer_id'] == a1.peer_id, "Message should be from a1"
    assert received_by_a3['message_type'] == "indirect_message", "Message type should match"
    assert received_by_a3['payload'] == test_payload_1, "Message payload should match"

    # Verify a1 received the message from a3
    assert len(received_messages[a1.peer_id]) == 1, "a1 should receive exactly one message"
    received_by_a1 = received_messages[a1.peer_id][0]
    assert received_by_a1['peer_id'] == a3.peer_id, "Message should be from a3"
    assert received_by_a1['message_type'] == "indirect_message", "Message type should match"
    assert received_by_a1['payload'] == test_payload_2, "Message payload should match"

    # Verify a2 (intermediary) didn't receive any messages as final recipient
    assert len(received_messages[a2.peer_id]) == 0, "a2 should not receive any messages as final recipient"

@pytest_twisted.inlineCallbacks
def test_broadcast_message_exchange(agent_factory):
    # Create 3 agents
    a1, a2, a3 = agent_factory(3)
    received_messages = {
        a1.peer_id: [],
        a2.peer_id: [],
        a3.peer_id: []
    }

    # Register message event handlers for all agents
    def create_message_event_handler(agent_id):
        def on_message(data):
            received_messages[agent_id].append(data)
        return on_message

    for agent in [a1, a2, a3]:
        agent.on('message', create_message_event_handler(agent.peer_id))

    # Connect agents in a triangle
    a1.connect(a2.public_ip, a2.public_port)
    a2.connect(a3.public_ip, a3.public_port)
    
    # Wait for connections to establish
    yield deferLater(reactor, 0.5, lambda: None)

    # Verify initial connectivity
    assert a1.get_connection_count() == 1, "a1 should have one connection"
    assert a2.get_connection_count() == 2, "a2 should have two connections"
    assert a3.get_connection_count() == 1, "a3 should have one connection"

    # Broadcast a message from a1
    test_payload = {"content": "Broadcast message from a1"}
    a1.broadcast("broadcast_message", test_payload)

    # Wait for messages to be processed
    yield deferLater(reactor, 0.5, lambda: None)

    # Verify both a2 and a3 received the broadcast message
    assert len(received_messages[a1.peer_id]) == 0, "a1 should not receive its own broadcast"
    assert len(received_messages[a2.peer_id]) == 1, "a2 should receive exactly one message"
    assert len(received_messages[a3.peer_id]) == 1, "a3 should receive exactly one message"

    # Verify message contents for a2
    received_by_a2 = received_messages[a2.peer_id][0]
    assert received_by_a2['peer_id'] == a1.peer_id, "Message should be from a1"
    assert received_by_a2['message_type'] == "broadcast_message", "Message type should match"
    assert received_by_a2['payload'] == test_payload, "Message payload should match"

    # Verify message contents for a3
    received_by_a3 = received_messages[a3.peer_id][0]
    assert received_by_a3['peer_id'] == a1.peer_id, "Message should be from a1"
    assert received_by_a3['message_type'] == "broadcast_message", "Message type should match"
    assert received_by_a3['payload'] == test_payload, "Message payload should match"

    # Test broadcast from a different agent (a3)
    test_payload_2 = {"content": "Broadcast message from a3"}
    a3.broadcast("broadcast_message", test_payload_2)

    # Wait for messages to be processed
    yield deferLater(reactor, 0.5, lambda: None)

    # Verify a1 and a2 received the second broadcast
    assert len(received_messages[a1.peer_id]) == 1, "a1 should receive exactly one message"
    assert len(received_messages[a2.peer_id]) == 2, "a2 should receive exactly two messages"
    assert len(received_messages[a3.peer_id]) == 1, "a3 should still have one message"

    # Verify message contents from second broadcast
    received_by_a1 = received_messages[a1.peer_id][0]
    assert received_by_a1['peer_id'] == a3.peer_id, "Message should be from a3"
    assert received_by_a1['message_type'] == "broadcast_message", "Message type should match"
    assert received_by_a1['payload'] == test_payload_2, "Message payload should match"

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
    assert a1.get_connection_count() == 1, "a1 should have one active connection"

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
    assert a1.get_connection_count() == 1, "Initial connection should be established"
    
    # Disconnect from peer
    a1.disconnect(a2.peer_id)
    
    # Wait for disconnection to process
    yield deferLater(reactor, 0.5, lambda: None)

    assert disconnection_count == 1, "Should have received exactly one disconnection event"
    assert a1.get_connection_count() == 0, "a1 should have no active connections"

@pytest_twisted.inlineCallbacks
def test_message_event(agent_factory):
    # Create 2 agents
    a1, a2 = agent_factory(2)
    received_message = None

    # Register on:message event handler
    def on_message(data):
        nonlocal received_message
        received_message = data

    a2.on('message', on_message)

    # Connect agents
    a1.connect(a2.public_ip, a2.public_port)
    
    # Wait for connection to establish
    yield deferLater(reactor, 0.5, lambda: None)

    # Send a test message
    test_payload = {
        "content": "Test message",
        "timestamp": 123456789
    }
    a1.send(a2.peer_id, "test_message", test_payload)

    # Wait for message processing
    yield deferLater(reactor, 0.5, lambda: None)

    # Verify message was received and event handler was triggered
    assert received_message is not None, "Message event handler was not triggered"
    assert received_message['peer_id'] == a1.peer_id, "Unexpected sender ID"
    assert received_message['message_type'] == "test_message", "Wrong message type"
    assert received_message['payload'] == test_payload, "Message payload does not match"

@pytest_twisted.inlineCallbacks
def test_rejoin_behaviour(agent_factory):
    # Create 3 agents
    a1, a2, a3 = agent_factory(3)
    received_messages = {
        a1.peer_id: [],
        a2.peer_id: [],
        a3.peer_id: []
    }

    # Register message event handlers for all agents
    def create_message_event_handler(agent_id):
        def on_message(data):
            received_messages[agent_id].append(data)
        return on_message

    for agent in [a1, a2, a3]:
        agent.on('message', create_message_event_handler(agent.peer_id))

    # Connect agents in a triangle
    a1.connect(a2.public_ip, a2.public_port)
    a2.connect(a3.public_ip, a3.public_port)
    
    # Wait for connections to establish
    yield deferLater(reactor, 0.5, lambda: None)

    # Send a message from a1 to a3
    test_payload = {"content": "Hello, agent 3!"}
    a1.send(a3.peer_id, "custom_type", test_payload)

    # Wait for message to be processed
    yield deferLater(reactor, 0.5, lambda: None)

    # Verify a3 received the message
    assert len(received_messages[a3.peer_id]) == 1, "a3 should receive exactly one message"

    # --- now test after shutdown behavior ---
    # a2 drops both a1 and a3
    a2.shutdown()

    # allow disconnection to propagate
    yield deferLater(reactor, 1, lambda: None)

    # a1 and a3 should have at least one connection
    assert a1.get_connection_count() >= 1, "a1 should still have at least one connection to a3"
    assert a3.get_connection_count() >= 1, "a3 should still have at least one connection to a1"

    # Send a message from a1 to a3 again
    test_payload_2 = {"content": "Hello again, agent 3!"}
    a1.send(a3.peer_id, "custom_type", test_payload_2)

    # Wait for message to be processed
    yield deferLater(reactor, 0.5, lambda: None)

    # Verify a3 recieved the message
    assert len(received_messages[a3.peer_id]) == 2, "a3 should receive exactly two messages"
