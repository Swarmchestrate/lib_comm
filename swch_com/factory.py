import logging
import json
from typing import Optional, Dict, Any, List

from twisted.internet.protocol import Factory

from swch_com.node import P2PNode
from swch_com.peers import Peers

class P2PFactory(Factory):
    def __init__(self, peer_id: str, peer_type: str, universe: str, public_ip: str, public_port: str):
        self.peers = Peers()

        self.seen_messages = set()  # Keep track of processed message IDs
        self.id = peer_id  # Unique ID for this node
        self.universe = universe
        self.type = peer_type

        self.public_ip = public_ip
        self.public_port = public_port

        self.peers.add_peer(self.id)
        self.peers.set_public_info(self.id, public_ip, public_port)

        self.logger = logging.getLogger(__name__)  # Initialize logger
        self.logger.info(f"Initialized P2PFactory with id: {self.id}, type: {self.type}, universe: {self.universe}, host: {public_ip}, port: {public_port}")

        self.user_defined_msg_handlers=dict()
        
        self.event_listeners = {
            'peer_connected': [],
            'peer_disconnected': [],
            'peer_discovered': []  # Add new event type
        }

    def send_message(self, message: dict, peer_transport: Optional[Any] = None) -> None:
        """Send a message to all connected peers or a specific peer."""
        message_id = message.get("message_id")
        if message_id:
            self.seen_messages.add(message_id)
        else:
            self.logger.warning("Message without message_id")

        serialized_message = json.dumps(message) + "\n"
        data = serialized_message.encode("utf-8")

        if peer_transport:
            peer_transport.write(data)
        else:
            for transport in self.peers.get_all_transports():
                transport.write(data)

    def send_to_peer(self, peer_id: str, message: dict) -> None:
        peer_info = self.peers.get_peer_info(peer_id)
        if not peer_info:
            self.logger.warning(f"No such peer {peer_id} in registry.")
            return
        # Find an active transport (local or remote) for that peer
        transport = None
        for loc in ("remote", "local"):
            info = peer_info.get(loc)
            if info and "transport" in info:
                transport = info["transport"]
                break
        if not transport:
            self.logger.warning(f"Peer {peer_id} is not currently connected.")
            return

        self.send_message(message, transport)

    def broadcast_message(self, message: dict) -> None:
        self.send_message(message)

    def buildProtocol(self, addr):
        """Create a new P2PNode protocol instance"""
        node = P2PNode(self, self.peers)  # Pass the factory instance to P2PNode
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

    def add_peer_discovered_event(self, peer_id: str):
        """Trigger the peer discovered event"""
        for listener in self.event_listeners.get('peer_discovered', []):
            listener(peer_id)