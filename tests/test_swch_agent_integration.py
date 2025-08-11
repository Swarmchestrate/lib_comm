import pytest
import socket
import uuid
from twisted.internet import reactor
from twisted.internet.task import deferLater
import pytest_twisted

from swch_com.swchagent import SwchAgent


def get_free_port():
    """Get a free port for testing"""
    sock = socket.socket()
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port

@pytest_twisted.inlineCallbacks
def test_swch_agent_integration():
    """Integration test following the 16-step script"""
    
    # Storage for test state - use a simple object instead of dict for setattr
    class TestState:
        def __init__(self):
            self.p4_left_first_time = False
            self.p1_connected_to_p3 = False
            self.p5_started = False
            self.app1SA = None
            self.p4_second_started = False
            self.status_received = False
    
    test_state = TestState()
    
    # Step 1: Start peer P1 with type="RA", id="wmin.ac.uk"
    p1_port = get_free_port()
    p1 = SwchAgent(
        peer_id="wmin.ac.uk",
        listen_ip="127.0.0.1",
        listen_port=p1_port,
        metadata={"type": "RA"}
    )
    yield deferLater(reactor, 0.1, lambda: None)  # Allow server to start
    
    # Step 2: Start peer P2 with type="RA", id="napier.ac.uk"; connecting to P1
    p2_port = get_free_port()
    p2 = SwchAgent(
        peer_id="napier.ac.uk",
        listen_ip="127.0.0.1",
        listen_port=p2_port,
        metadata={"type": "RA"}
    )
    yield p2.enter("127.0.0.1", p1_port)
    yield deferLater(reactor, 0.1, lambda: None)
    
    # Step 3: Start peer P3 with type="RA", id="sztaki.hu"; connecting to P2
    p3_port = get_free_port()
    p3 = SwchAgent(
        peer_id="sztaki.hu",
        listen_ip="127.0.0.1",
        listen_port=p3_port,
        metadata={"type": "RA"}
    )
    yield p3.enter("127.0.0.1", p2_port)
    yield deferLater(reactor, 0.1, lambda: None)
    
    # Step 4: Start peer P4 with type="CL"; connecting to P1
    p4_port = get_free_port()
    p4 = SwchAgent(
        peer_id=str(uuid.uuid4()),
        metadata={"type": "CL"}
    )
    yield p4.enter("127.0.0.1", p1_port)
    yield deferLater(reactor, 0.1, lambda: None)
    
    # Set up message handlers for the workflow
    
    # P1 handler for MSG_SUBMIT
    def p1_handle_msg_submit(sender_id, message):
        if message.get("payload") == "app1":
            # Step 6a: Send MSG_ACKSUBMIT to P4
            p1.send(sender_id, "MSG_ACKSUBMIT", {})
            # Step 6b: Broadcast MSG_GETOFFER
            p1.broadcast("MSG_GETOFFER", {"payload": "app1"})
    
    p1.register_message_handler("MSG_SUBMIT", p1_handle_msg_submit)
    
    # P4 handler for MSG_ACKSUBMIT
    def p4_handle_msg_acksubmit(sender_id, message):
        # Step 7a: P4 leaves the network
        p4.leave().addCallback(lambda _: setattr(test_state, 'p4_left_first_time', True))
    
    p4.register_message_handler("MSG_ACKSUBMIT", p4_handle_msg_acksubmit)
    
    # P2 handler for MSG_GETOFFER
    def p2_handle_msg_getoffer(sender_id, message):
        if message.get("payload") == "app1":
            # Step 8a: P2 sends MSG_OFFER with payload="none"
            p2.send(sender_id, "MSG_OFFER", {"payload": "none"})
    
    p2.register_message_handler("MSG_GETOFFER", p2_handle_msg_getoffer)
    
    # P3 handler for MSG_GETOFFER
    def p3_handle_msg_getoffer(sender_id, message):
        if message.get("payload") == "app1":
            # Step 9a: P3 sends MSG_OFFER with payload="sztaki"
            p3.send(sender_id, "MSG_OFFER", {"payload": "sztaki"})
    
    p3.register_message_handler("MSG_GETOFFER", p3_handle_msg_getoffer)
    
    # P1 handler for MSG_OFFER
    def p1_handle_msg_offer(sender_id, message):
        if message.get("payload") != "none":
            # Step 10a: P1 builds direct connection to P3
            p1.connect(sender_id).addCallback(lambda peer_id: setattr(test_state, 'p1_connected_to_p3', True))
            # Step 10b: P1 sends MSG_NEWSWARM to P3
            p1.send(sender_id, "MSG_NEWSWARM", {"payload": "app1"})

    p1.register_message_handler("MSG_OFFER", p1_handle_msg_offer)
    
    # P3 handler for MSG_NEWSWARM
    def p3_handle_msg_newswarm(sender_id, message):
        if message.get("payload") == "app1":
            # Step 11a: Start peer P5
            global p5
            p5_port = get_free_port()
            p5 = SwchAgent(
                peer_id="app1",
                listen_ip="127.0.0.1",
                listen_port=p5_port,
                metadata={"type": "SA", "appid": "app1"}
            )
            p5.enter("127.0.0.1", p3_port).addCallback(lambda _: setattr(test_state, 'p5_started', True))
    
    p3.register_message_handler("MSG_NEWSWARM", p3_handle_msg_newswarm)
    
    # Step 5: P4 sends MSG_SUBMIT with payload="app1" to P1
    p4.send("wmin.ac.uk", "MSG_SUBMIT", {"payload": "app1"})
    
    # Wait for P4 to leave the first time
    yield deferLater(reactor, 2.0, lambda: None)
    assert test_state.p4_left_first_time, "P4 should have left after receiving MSG_ACKSUBMIT"
    
    # Wait for P1 to connect to P3 and P5 to start
    timeout = 6.0
    elapsed = 0.0
    step = 0.1
    while elapsed < timeout and (not test_state.p1_connected_to_p3 or not test_state.p5_started):
        yield deferLater(reactor, step, lambda: None)
        elapsed += step
    
    assert test_state.p1_connected_to_p3, "P1 should have connected to P3"
    assert test_state.p5_started, "P5 should have been started"
    
    # Step 12: Start new peer P4 (second instance) with type="CL"; connecting to P1
    p4_second_port = get_free_port()
    p4_second = SwchAgent(
        peer_id=str(uuid.uuid4()),
        listen_ip="127.0.0.1",
        listen_port=p4_second_port,
        metadata={"type": "CL"}
    )
    p4_second.enter("127.0.0.1", p1_port).addCallback(lambda _: setattr(test_state, 'p4_second_started', True))
    yield deferLater(reactor, 2.0, lambda: None)  # Allow peer discovery
    
    # Step 13: P4 searches for peers with metadata appid="app1"
    app1_peers = p4_second.findPeers({"appid": "app1"})
    assert len(app1_peers) > 0, "Should find P5 with appid=app1"
    test_state.app1SA = app1_peers[0]  # Store the peer ID
    
    # Set up P5 handler for MSG_GETSTATUS
    def p5_handle_msg_getstatus(sender_id, message):
        if message.get("payload") == "app1":
            # Step 15a: P5 sends MSG_STATUS
            p5.send(sender_id, "MSG_STATUS", {"payload": {"status": "running"}})
    
    p5.register_message_handler("MSG_GETSTATUS", p5_handle_msg_getstatus)
    
    # Set up P4_second handler for MSG_STATUS
    def p4_second_handle_msg_status(sender_id, message):
        payload = message.get("payload", {})
        if payload.get('status') == "running":
            test_state.status_received = True
            # Step 16a: P4 leaves the network
            p4_second.leave()
    
    p4_second.register_message_handler("MSG_STATUS", p4_second_handle_msg_status)
    
    # Step 14: P4 sends MSG_GETSTATUS to the found peer
    p4_second.send(test_state.app1SA, "MSG_GETSTATUS", {"payload": "app1"})
    
    # Wait for status message exchange
    yield deferLater(reactor, 2.0, lambda: None)
    assert test_state.status_received, "P4 should have received MSG_STATUS from P5"
    
    # Cleanup - leave all remaining peers
    yield p1.leave()
    yield p2.leave()
    yield p3.leave()
    if test_state.p5_started:
        yield p5.leave()
    
    # Verify final test state
    assert test_state.p4_left_first_time, "P4 left after MSG_ACKSUBMIT"
    assert test_state.p1_connected_to_p3, "P1 connected to P3"
    assert test_state.p5_started, "P5 was started by P3"
    assert test_state.app1SA is not None, "Found peer with appid=app1"
    assert test_state.p4_second_started, "Second P4 instance started"
    assert test_state.status_received, "P4 received status from P5"
