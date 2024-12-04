import uuid
import logging
from twisted.internet.protocol import Factory

from swch_com.node import P2PNode


class P2PFactory(Factory):
    def __init__(self, public_ip, public_port):
        self.all_peers = {}  # Store peers at the factory level

        self.seen_messages = set()  # Keep track of processed message IDs
        self.id = str(uuid.uuid4())  # Unique ID for this node

        self.public_ip = public_ip
        self.public_port = public_port

        self.all_peers[self.id] = {
            "public": {
                "host": public_ip,
                "port": public_port
            }
        }
        
        print(f"Peer initialized with id: {self.id}, host: {public_ip}, port: {public_port}")
        self.logger = logging.getLogger(__name__)  # Initialize logger

        # Initialize event listeners dictionary
        self.event_listeners = {
            'peer_connected': [],
            'peer_disconnected': [],
        }


    def buildProtocol(self, addr):
        """Create a new P2PNode protocol instance"""
        node = P2PNode(self)  # Pass the factory instance to P2PNode
        return node

    def add_event_listener(self, event_name, listener):
        """Register an event listener for a specific event"""
        if event_name in self.event_listeners:
            self.event_listeners[event_name].append(listener)
        else:
            self.event_listeners[event_name] = [listener]

    def remove_event_listener(self, event_name, listener):
        """Remove an event listener for a specific event"""
        if event_name in self.event_listeners:
            self.event_listeners[event_name].remove(listener)

    def on_peer_connected(self):
        # Trigger the 'peer_connected' event
        for listener in self.event_listeners.get('peer_connected', []):
            listener()

    def on_peer_disconnected(self):
        # Trigger the 'peer_disconnected' event
        for listener in self.event_listeners.get('peer_disconnected', []):
            listener()