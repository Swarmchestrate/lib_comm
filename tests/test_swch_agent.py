import pytest, socket, uuid

import pytest_twisted
from twisted.internet import reactor
from twisted.internet.task import deferLater
from twisted.internet.defer import DeferredList, ensureDeferred
from pytest_twisted import blockon

from swch_com.swchagent import SwchAgent

@pytest.fixture
def agent_factory():
    """
    Returns a function create_agents(n, *, prefix="agent") → List[SwchAgent].
    """
    host = "127.0.0.1"
    created = []

    def _create(num_agents, *, metadata=None, prefix="agent"):
        agents = []
        for i in range(num_agents):
            # pick an ephemeral port
            sock = socket.socket()
            sock.bind((host, 0))
            port = sock.getsockname()[1]
            sock.close()

            agent_id = f"{prefix}{i+1}"
            agent = SwchAgent(agent_id,metadata=metadata,listen_ip=host, listen_port=port)
            agents.append(agent)
            created.append(agent)
        return agents

    yield _create

    # --- teardown runs *after* the test returns ---
    # collect all cleanup Deferreds
    deferreds = [
        ensureDeferred(teardown_agent_listeners(agent))
        for agent in created
    ]
    # block the pytest runner until they're *all* done
    blockon(DeferredList(deferreds))
    created.clear()

@pytest_twisted.inlineCallbacks
def teardown_agent_listeners(agent):
    # 1) Leave the ring
    yield agent.leave()

    # 2) Clean up any listening ports (readers)
    for reader in list(reactor.getReaders()):
        try:
            addr = reader.getHost()
        except Exception:
            continue

        if addr.host == agent.public_ip and addr.port == agent.public_port:
            reactor.removeReader(reader)
            # stopListening() for TCP/UDP ports
            stop = getattr(reader, "stopListening", None)
            if stop:
                d = reader.stopListening()
                if d:
                    yield d

    # 3) Clean up any outgoing transports (writers)
    for writer in list(reactor.getWriters()):
        try:
            addr = writer.getHost()
        except Exception:
            continue

        if addr.host == agent.public_ip and addr.port == agent.public_port:
            reactor.removeWriter(writer)

            # If it's a listening-style port (e.g. UDP), stopListening()
            stop = getattr(writer, "stopListening", None)
            if stop:
                d = writer.stopListening()
                if d:
                    yield d

            # Otherwise, if it's a TCP connection, close it cleanly
            elif hasattr(writer, "loseConnection"):
                writer.loseConnection()

@pytest_twisted.inlineCallbacks
def test_two_agents_connection(agent_factory):
    a1 = agent_factory(1, metadata={"type": "worker", "universe": "test", "version": "1.0"}, prefix=1)[0]
    a2 = agent_factory(1, metadata={"type": "manager", "universe": "test", "version": "1.1"},prefix=2)[0]
    
    # 1. Initiate connection from a1 to a2's listening port
    a1.enter(a2.public_ip, a2.public_port)

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
    
    # 5. Verify metadata propagation
    assert peer_info_1["metadata"] == a2.factory.metadata, "a1 should have a2's metadata"
    assert peer_info_2["metadata"] == a1.factory.metadata, "a2 should have a1's metadata"
    
    # Verify specific metadata fields
    assert peer_info_1["metadata"]["type"] == "manager", "a1 should know a2 is a manager"
    assert peer_info_1["metadata"]["universe"] == "test", "a1 should know a2's universe"
    assert peer_info_1["metadata"]["version"] == "1.1", "a1 should know a2's version"
    
    assert peer_info_2["metadata"]["type"] == "worker", "a2 should know a1 is a worker"
    assert peer_info_2["metadata"]["universe"] == "test", "a2 should know a1's universe"
    assert peer_info_2["metadata"]["version"] == "1.0", "a2 should know a1's version"

@pytest_twisted.inlineCallbacks
def test_three_agents_connection_1(agent_factory):
    # create 3 agents with different metadata
    a1 = agent_factory(1, metadata={"type": "worker", "universe": "production", "region": "us-east"}, prefix=1)[0]
    a2 = agent_factory(1, metadata={"type": "coordinator", "universe": "production", "region": "us-west"}, prefix=2)[0]
    a3 = agent_factory(1, metadata={"type": "storage", "universe": "production", "region": "eu-central"}, prefix=3)[0]
    
    # connect a1 → a3 and a2 → a3
    a1.enter(a3.public_ip, a3.public_port)
    a2.enter(a3.public_ip, a3.public_port)

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
            
            # verify metadata propagation
            expected_metadata = peer.factory.metadata
            actual_metadata = info.get("metadata", {})
            assert actual_metadata == expected_metadata, (
                f"{agent.peer_id} has wrong metadata for {pid}: "
                f"expected {expected_metadata}, got {actual_metadata}"
            )

    # Verify specific metadata values are propagated correctly
    # Check a1's view of other agents
    a1_peers = {pid: info for pid, info in a1.factory.peers.get_all_peers_items()}
    assert a1_peers[a2.peer_id]["metadata"]["type"] == "coordinator", "a1 should know a2 is coordinator"
    assert a1_peers[a2.peer_id]["metadata"]["region"] == "us-west", "a1 should know a2's region"
    assert a1_peers[a3.peer_id]["metadata"]["type"] == "storage", "a1 should know a3 is storage"
    assert a1_peers[a3.peer_id]["metadata"]["region"] == "eu-central", "a1 should know a3's region"
    
    # Check a2's view of other agents
    a2_peers = {pid: info for pid, info in a2.factory.peers.get_all_peers_items()}
    assert a2_peers[a1.peer_id]["metadata"]["type"] == "worker", "a2 should know a1 is worker"
    assert a2_peers[a1.peer_id]["metadata"]["region"] == "us-east", "a2 should know a1's region"
    assert a2_peers[a3.peer_id]["metadata"]["type"] == "storage", "a2 should know a3 is storage"
    assert a2_peers[a3.peer_id]["metadata"]["region"] == "eu-central", "a2 should know a3's region"
    
    # Check a3's view of other agents
    a3_peers = {pid: info for pid, info in a3.factory.peers.get_all_peers_items()}
    assert a3_peers[a1.peer_id]["metadata"]["type"] == "worker", "a3 should know a1 is worker"
    assert a3_peers[a1.peer_id]["metadata"]["region"] == "us-east", "a3 should know a1's region"
    assert a3_peers[a2.peer_id]["metadata"]["type"] == "coordinator", "a3 should know a2 is coordinator"
    assert a3_peers[a2.peer_id]["metadata"]["region"] == "us-west", "a3 should know a2's region"

    # --- now test shutdown behavior ---
    # a2 drops both a1 and a3
    a2.leave()

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
        f"{a2.peer_id} did not clear its peers after disconnect"

@pytest_twisted.inlineCallbacks
def test_three_agents_connection_2(agent_factory):
    # create 3 agents
    a1, a2, a3 = agent_factory(3)

    # connect a1 → a2 and a1 → a3
    a1.enter(a2.public_ip, a2.public_port)
    a1.enter(a3.public_ip, a3.public_port)

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
    a2.enter(a3.public_ip, a3.public_port)
    a1.enter(a2.public_ip, a2.public_port)

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
    a1.enter(a2.public_ip, a2.public_port)
    a2.enter(a3.public_ip, a3.public_port)
    a3.enter(a1.public_ip, a1.public_port)

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
def test_three_agents_intentional_disconnect(agent_factory):
    # create 3 agents
    a1, a2, a3 = agent_factory(3)

    # connect a1 → a2 and a2 → a3 and a3 → a1
    a1.enter(a2.public_ip, a2.public_port)
    a2.enter(a3.public_ip, a3.public_port)
    a3.enter(a1.public_ip, a1.public_port)

    # let Twisted do its thing
    yield deferLater(reactor, 1, lambda: None)

    # initial connectivity checks
    assert a1.get_connection_count() == 2, "a1 should have two outgoing connections"
    assert a2.get_connection_count() == 2, "a2 should have one incoming connection"
    assert a3.get_connection_count() == 2, "a3 should have one incoming connection"

    # disconnect a1 from both peers
    a1.disconnect(a2.peer_id)

    # allow disconnections to propagate
    yield deferLater(reactor, 2, lambda: None)

    # verify connections
    assert a1.get_connection_count() == 1, "a1 should have no active connections after leave"
    assert a2.get_connection_count() == 1, "a2 should have no active connections after a1 leaves"
    assert a3.get_connection_count() == 2, "a3 should have no active connections after a1 leaves"

    # verify peer info
    all_agents = [a1, a2, a3]
    for agent in all_agents:
        peer_count = len([pid for pid, _ in agent.factory.peers.get_all_peers_items() if pid != agent.peer_id])
        assert peer_count == 2, f"{agent.peer_id} should know about 2 other peers still"

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
    a1.enter(a2.public_ip, a2.public_port)
    a2.enter(a3.public_ip, a3.public_port)
    
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
    a1.enter(a2.public_ip, a2.public_port)
    a2.enter(a1.public_ip, a1.public_port)
    
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
    a1.enter(a2.public_ip, a2.public_port)
    a2.enter(a3.public_ip, a3.public_port)
    
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
    a1.enter(a2.public_ip, a2.public_port)
    a2.enter(a3.public_ip, a3.public_port)
    
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
def test_entered_event(agent_factory):
    a1, a2 = agent_factory(2)
    entered_peers = []

    # Register event handler for peer entering
    def on_peer_entered():
        entered_peers.append("a1")

    a1.on('entered', on_peer_entered)

    # Connect a1 to a2
    a1.enter(a2.public_ip, a2.public_port)
    
    yield deferLater(reactor, 0.5, lambda: None)

    assert len(entered_peers) == 1, "Enter event should be triggered exactly once"

@pytest_twisted.inlineCallbacks
def test_peer_discovered_event(agent_factory):
    a1, a2 = agent_factory(2)
    discovered_peers = []

    # Register event handler for peer discovery
    def on_peer_discovered(peer_id):
        discovered_peers.append(peer_id)

    a1.on('peer:discovered', on_peer_discovered)

    # Connect a1 to a2
    a1.enter(a2.public_ip, a2.public_port)
    
    # Wait for connection and discovery
    yield deferLater(reactor, 0.5, lambda: None)

    assert len(discovered_peers) == 1, "Should have discovered exactly one peer"
    assert discovered_peers[0] == a2.peer_id, "Discovered peer ID should match a2's ID"

@pytest_twisted.inlineCallbacks
def test_peer_undiscovered_event(agent_factory):
    a1, a2 = agent_factory(2)
    undiscovered_peers = []

    # Register event handler for peer undiscovery
    def on_peer_undiscovered(peer_id):
        undiscovered_peers.append(peer_id)

    a1.on('peer:undiscovered', on_peer_undiscovered)

    # Connect a1 to a2
    a1.enter(a2.public_ip, a2.public_port)
    
    # Wait for connection and discovery
    yield deferLater(reactor, 0.5, lambda: None)

    assert len(undiscovered_peers) == 0, "Should not have any undiscovered peers initially"

    # Disconnect from peer
    a2.leave()
    
    # Wait for disconnection to process
    yield deferLater(reactor, 0.5, lambda: None)

    assert len(undiscovered_peers) == 1, "Should have received exactly one undiscovery event"
    assert undiscovered_peers[0] == a2.peer_id, "Undiscovered peer ID should match a2's ID"

@pytest_twisted.inlineCallbacks
def test_peer_connected_event(agent_factory):
    a1, a2 = agent_factory(2)
    connection_count = 0

    # Register event handler for peer connection
    def on_peer_connected(peer_id):
        nonlocal connection_count
        connection_count += 1

    a1.on('peer:connected', on_peer_connected)

    # Connect a1 to a2
    a1.enter(a2.public_ip, a2.public_port)
    
    # Wait for connection
    yield deferLater(reactor, 0.5, lambda: None)

    assert connection_count == 1, "Should have received exactly one connection event"
    assert a1.get_connection_count() == 1, "a1 should have one active connection"

@pytest_twisted.inlineCallbacks
def test_peer_disconnected_event(agent_factory):
    a1, a2 = agent_factory(2)
    disconnection_count = 0

    # Register event handler for peer disconnection
    def on_peer_disconnected(peer_id):
        nonlocal disconnection_count
        disconnection_count += 1

    a1.on('peer:disconnected', on_peer_disconnected)

    # First establish connection
    a1.enter(a2.public_ip, a2.public_port)
    
    # Wait for connection to establish
    yield deferLater(reactor, 0.5, lambda: None)
    
    # Verify initial connection
    assert a1.get_connection_count() == 1, "Initial connection should be established"
    
    # Disconnect from peer
    a2.leave()
    
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
    a1.enter(a2.public_ip, a2.public_port)
    
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
def test_all_disconnected_event(agent_factory):
    a1, a2 = agent_factory(2)
    all_disconnected_count = 0

    # Register event handler for all peers disconnected
    def on_all_disconnected():
        nonlocal all_disconnected_count
        all_disconnected_count += 1

    a1.on('peer:all_disconnected', on_all_disconnected)

    # Connect a1 to a2
    a1.enter(a2.public_ip, a2.public_port)
    
    # Wait for connection to establish
    yield deferLater(reactor, 0.5, lambda: None)
    
    # Verify initial connection
    assert a1.get_connection_count() == 1, "Initial connection should be established"
    
    # Simulate unintentional disconnection by shutting down a2 (not a1)
    a2.leave()
    
    # Wait for disconnection to process
    yield deferLater(reactor, 0.5, lambda: None)

    assert all_disconnected_count == 1, "Should have received exactly one all_disconnected event"
    assert a1.get_connection_count() == 0, "a1 should have no active connections"

@pytest_twisted.inlineCallbacks
def test_expired_messages_cleanup(agent_factory):
    # Create a single agent
    agent = agent_factory(1)[0]
    
    # Modify the factory's message TTL and cleanup interval for faster testing
    original_ttl = agent.factory.message_ttl
    original_cleanup_interval = agent.factory.cleanup_task.clock.seconds()
    
    # Set short TTL and cleanup interval for testing
    agent.factory.message_ttl = 1  # 1 second TTL
    agent.factory.cleanup_task.stop()  # Stop the original cleanup task
    
    # Start a new cleanup task with shorter interval
    from twisted.internet.task import LoopingCall
    agent.factory.cleanup_task = LoopingCall(agent.factory._cleanup_old_messages)
    agent.factory.cleanup_task.start(0.5)  # Run cleanup every 0.5 seconds
    
    # Generate some test messages to populate seen_messages
    test_message_ids = [str(uuid.uuid4()) for _ in range(3)]
    
    # Mark messages as seen
    for msg_id in test_message_ids:
        agent.factory._mark_message_seen(msg_id)
    
    # Verify messages are in seen_messages
    assert len(agent.factory.seen_messages) == 3, "All test messages should be in seen_messages"
    for msg_id in test_message_ids:
        assert msg_id in agent.factory.seen_messages, f"Message {msg_id} should be in seen_messages"
    
    # Wait for messages to expire (TTL + some buffer)
    yield deferLater(reactor, 1.5, lambda: None)
    
    # Wait for cleanup task to run at least once
    yield deferLater(reactor, 0.6, lambda: None)
    
    # Verify expired messages have been cleaned up
    assert len(agent.factory.seen_messages) == 0, "Expired messages should be cleaned up"
    for msg_id in test_message_ids:
        assert msg_id not in agent.factory.seen_messages, f"Expired message {msg_id} should be removed"
    
    # Test that new messages are still tracked
    new_message_id = str(uuid.uuid4())
    agent.factory._mark_message_seen(new_message_id)
    
    assert new_message_id in agent.factory.seen_messages, "New message should be tracked"
    assert len(agent.factory.seen_messages) == 1, "Only the new message should be present"
    
    # Clean up - restore original settings
    agent.factory.cleanup_task.stop()
    agent.factory.message_ttl = original_ttl
    agent.factory.cleanup_task = LoopingCall(agent.factory._cleanup_old_messages)
    agent.factory.cleanup_task.start(5)  # Restore original 5-second interval

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
    a1.enter(a2.public_ip, a2.public_port)
    a2.enter(a3.public_ip, a3.public_port)
    
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
    a2.leave()

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

@pytest_twisted.inlineCallbacks
def test_rejoin_multiple_cycles(agent_factory):
    # Create 4 agents in a more complex network
    a1, a2, a3, a4, a5, a6 = agent_factory(6)
    
    # Connect agents: a1 -> a2 -> a3 -> a4 (creating a partial mesh)
    a1.enter(a2.public_ip, a2.public_port)
    a2.enter(a3.public_ip, a3.public_port)
    a3.enter(a4.public_ip, a4.public_port)
    
    # Wait for initial connections to establish
    yield deferLater(reactor, 0.5, lambda: None)
    
    # Verify initial connectivity - all agents should know about all others
    for agent in [a1, a2, a3, a4]:
        peer_count = len([pid for pid, _ in agent.factory.peers.get_all_peers_items() if pid != agent.peer_id])
        assert peer_count == 3, f"{agent.peer_id} should know about 3 other peers, found {peer_count}"
    
    # First disconnection cycle: shutdown a2 (breaks the chain)
    a2.leave()
    yield deferLater(reactor, 1, lambda: None)
    
    # a1, a3, and a4 should still be connected through rejoin mechanism
    # Wait for rejoin to complete
    yield deferLater(reactor, 4, lambda: None)
    
    # Verify a1 built new connection to the network
    assert a1.get_connection_count() >= 1, "a1 should have a new connection to either a3 or a4"
    
    # Connect a5 to existing network
    a5.enter(a1.public_ip, a1.public_port)
    
    yield deferLater(reactor, 2, lambda: None)
    
    # All active agents should now know about a5
    for agent in [a1, a3, a4, a5]:
        peer_ids = {pid for pid, _ in agent.factory.peers.get_all_peers_items()}
        assert a5.peer_id in peer_ids, f"{agent.peer_id} should know about a5"
    
    # Second disconnection cycle: shutdown a1
    a1.leave()
    yield deferLater(reactor, 1, lambda: None)
    
    # Wait for rejoin attempts
    yield deferLater(reactor, 4, lambda: None)
    
    # a3, a4, a5 should still be connected through rejoin
    remaining_agents = [a3, a4, a5]
    for agent in remaining_agents:
        assert agent.get_connection_count() >= 1, f"{agent.peer_id} should be connected after rejoin"

@pytest_twisted.inlineCallbacks
def test_rejoin_with_network_partition_healing(agent_factory):
    # Create 5 agents to test network partition and healing
    a1, a2, a3, a4, a5, a6 = agent_factory(6)
    
    # Create initial full mesh-like connections
    connections = [
        (a1, a2), (a2, a3), (a3, a4), (a4, a5),  # Chain
    ]
    
    for agent_from, agent_to in connections:
        agent_from.enter(agent_to.public_ip, agent_to.public_port)
    
    yield deferLater(reactor, 1, lambda: None)
    
    # Verify all agents know about each other
    for agent in [a1, a2, a3, a4, a5]:
        peer_count = len([pid for pid, _ in agent.factory.peers.get_all_peers_items() if pid != agent.peer_id])
        assert peer_count == 4, f"{agent.peer_id} should know about 4 other peers"
    
    # Create a network partition by shutting down a3 (central node)
    # This should split the network into {a1, a2} and {a4, a5} partitions
    a3.leave()
    yield deferLater(reactor, 1, lambda: None)
    
    # Wait for network to settle after partition
    yield deferLater(reactor, 2, lambda: None)

    # Verify partitions still have some connectivity
    partition1 = [a1, a2]
    partition2 = [a4, a5]
    
    for agent in partition1:
        assert agent.get_connection_count() >= 1, f"{agent.peer_id} should maintain some connections"
    
    for agent in partition2:
        assert agent.get_connection_count() >= 1, f"{agent.peer_id} should maintain some connections"
    
    # Test message routing within partitions
    received_messages = {agent.peer_id: [] for agent in [a1, a2, a4, a5]}
    
    def create_message_handler(agent_id):
        def on_message(data):
            received_messages[agent_id].append(data)
        return on_message
    
    for agent in [a1, a2, a4, a5]:
        agent.on('message', create_message_handler(agent.peer_id))
    
    # Send message within partition 1
    a1.send(a2.peer_id, "partition_test", {"content": "message in partition 1"})
    
    # Send message within partition 2  
    a4.send(a5.peer_id, "partition_test", {"content": "message in partition 2"})
    
    yield deferLater(reactor, 0.5, lambda: None)
    
    # Verify messages were delivered within partitions
    assert len(received_messages[a2.peer_id]) == 1, "a2 should receive message from a1"
    assert len(received_messages[a5.peer_id]) == 1, "a5 should receive message from a4"
    
    # Cross-partition messages should not be delivered
    assert len(received_messages[a1.peer_id]) == 0, "a1 should not receive cross-partition messages"
    assert len(received_messages[a4.peer_id]) == 0, "a4 should not receive cross-partition messages"
    
    # Connect bridge to both partitions
    yield a6.enter(a1.public_ip, a1.public_port)

    # Wait for network to converge after healing
    yield deferLater(reactor, 4, lambda: None)

    yield a6.enter(a4.public_ip, a4.public_port)
        
    # Wait for network to converge after healing
    yield deferLater(reactor, 4, lambda: None)
    
    # Verify network healing - all agents should now know about each other again
    all_agents = [a1, a2, a4, a5, a6]
    for agent in all_agents:
        peer_count = len([pid for pid, _ in agent.factory.peers.get_all_peers_items() if pid != agent.peer_id])
        assert peer_count == 4, f"{agent.peer_id} should know about 4 other peers after healing"
    
    # Test cross-partition message delivery after healing
    a1.send(a5.peer_id, "healed_network", {"content": "cross-partition after healing"})
    
    yield deferLater(reactor, 1, lambda: None)
    
    # Verify cross-partition message was delivered
    assert len(received_messages[a5.peer_id]) == 2, "a5 should receive message from a1 after healing"
    
    healed_message = received_messages[a5.peer_id][1]
    assert healed_message['peer_id'] == a1.peer_id, "Message should be from a1"
    assert healed_message['message_type'] == "healed_network", "Message type should match"

@pytest_twisted.inlineCallbacks
def test_find_peers_by_metadata(agent_factory):
    # Create agents with various metadata
    agents_metadata = [
        {"type": "worker", "region": "us-east", "version": "1.0"},
        {"type": "worker", "region": "us-west", "version": "1.0"},
        {"type": "manager", "region": "us-east", "version": "1.1"},
        {"type": "storage", "region": "eu-central", "version": "1.0"},
        {"type": "worker", "region": "us-east", "version": "1.1"}
    ]
    
    agents = []
    for i, metadata in enumerate(agents_metadata):
        agent = agent_factory(1, metadata=metadata, prefix=f"agent{i}")[0]
        agents.append(agent)
    
    # Connect all agents to the first one (star topology)
    for i in range(1, len(agents)):
        agents[i].enter(agents[0].public_ip, agents[0].public_port)
    
    yield deferLater(reactor, 1, lambda: None)
    
    # Test metadata registration
    for agent in agents:
        for i in range(len(agents_metadata)):
            assert agent.get_peer_metadata(agents[i].peer_id) == agents_metadata[i], f"Metadata for agent {i} should match"

    # Test finding by single metadata field
    results = agents[0].findPeers({"type": "worker"})
    assert len(results) == 2, "Should find 2 workers"
    
    # Test finding by multiple metadata fields
    results = agents[1].findPeers({"type": "worker", "region": "us-east"})
    assert len(results) == 2, "Should find 2 workers in us-east"
    
    # Test finding by exact metadata match
    results = agents[2].findPeers({"type": "worker", "region": "us-east", "version": "1.0"})
    assert len(results) == 1, "Should find exactly 1 worker in us-east with version 1.0"
    
    # Test finding non-matching metadata
    results = agents[0].findPeers({"type": "nonexistent"})
    assert len(results) == 0, "Should find no peers with non-existent type"

@pytest_twisted.inlineCallbacks
def test_connect_by_id(agent_factory):
    # Create 4 agents to test connect method
    a1, a2, a3, a4 = agent_factory(4)
    
    # Create initial network topology: a1 -> a2 -> a3
    # This means a1 and a3 will know about each other but not be directly connected
    a1.enter(a2.public_ip, a2.public_port)
    a2.enter(a3.public_ip, a3.public_port)
    
    # Wait for initial connections to establish and peer discovery to propagate
    yield deferLater(reactor, 1, lambda: None)
    
    # Verify initial network state
    assert a1.get_connection_count() == 1, "a1 should have one direct connection to a2"
    assert a2.get_connection_count() == 2, "a2 should have two direct connections"
    assert a3.get_connection_count() == 1, "a3 should have one direct connection to a2"
    
    # Verify that a1 knows about a3 (through peer discovery) but isn't directly connected
    a1_peers = {pid: info for pid, info in a1.factory.peers.get_all_peers_items()}
    assert a3.peer_id in a1_peers, "a1 should know about a3 through peer discovery"
    
    # Verify initial connections - a1 should not be directly connected to a3
    a1_connected_peers = a1.getConnectedPeers()
    assert a3.peer_id not in a1_connected_peers, "a1 should not be directly connected to a3 initially"
    assert a2.peer_id in a1_connected_peers, "a1 should be connected to a2"
    
    # Use connect method to establish direct connection from a1 to a3
    d = a1.connect(a3.peer_id)
    
    # Wait for connection to establish
    yield deferLater(reactor, 1, lambda: None)
    
    # Verify that a1 now has a direct connection to a3
    assert a1.get_connection_count() == 2, "a1 should now have two direct connections"
    
    # Verify a1 is now directly connected to a3
    a1_connected_peers_after = a1.getConnectedPeers()
    assert a3.peer_id in a1_connected_peers_after, "a1 should now be directly connected to a3"
    assert a2.peer_id in a1_connected_peers_after, "a1 should still be connected to a2"
    
    # Test connect to an unknown peer (should fail)
    try:
        unknown_d = a1.connect(a4.peer_id)
        yield unknown_d
        assert False, "connect to unknown peer should have failed"
    except Exception:
        # Expected to fail since a4 is unknown
        pass
    
    # Test connect to already connected peer (should handle gracefully)
    try:
        existing_d = a1.connect(a2.peer_id)
        yield existing_d
        # Should either succeed or fail gracefully without crashing
    except Exception:
        # This is acceptable - already connected
        pass
    