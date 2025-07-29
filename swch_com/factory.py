import logging
import json
import uuid
import time
from typing import Optional, Dict, Any, List

from twisted.internet.protocol import Factory
from twisted.internet.task import LoopingCall

from swch_com.node import P2PNode
from swch_com.peers import Peers

class P2PFactory(Factory):
    def __init__(self, peer_id: str, metadata: dict, public_ip: str, public_port: str):
        """
        Initialize the P2P factory with peer information and metadata.
        :param peer_id: Unique identifier for this peer
        :param metadata: Dictionary containing peer metadata (e.g., universe, peer_type, etc.)
        :param public_ip: Public IP address of this peer
        :param public_port: Public port of this peer
        """
        self.peers = Peers()

        self.seen_messages = {}  # Dictionary to store message_id -> timestamp
        self.message_ttl = 20  # Time to live for messages in seconds
        self.id = peer_id  # Unique ID for this node

        self.public_ip = public_ip
        self.public_port = public_port
        self.metadata = metadata

        self.peers.add_peer(self.id)
        self.peers.set_public_info(self.id, public_ip, public_port)
        self.peers.set_peer_metadata(self.id, metadata)

        self.logger = logging.getLogger(__name__)  # Initialize logger
        self.logger.info(f"Initialized P2PFactory with id: {self.id}, metadata: {metadata}, host: {public_ip}, port: {public_port}")

        self.user_defined_msg_handlers=dict()
        
        self.event_listeners = {
            'peer:connected': [],
            'peer:disconnected': [],
            'peer:discovered': [],
            'peer:all_disconnected': [],
            'message': []
        }

        self._connection_count = 0  # Private connection counter
        self._is_shutting_down = False  # Track intentional shutdown

        # Start cleanup task for old messages
        self.cleanup_task = LoopingCall(self._cleanup_old_messages)
        self.cleanup_task.start(5)  # Run cleanup every 5 seconds

    def _cleanup_old_messages(self):
        """Remove messages older than message_ttl seconds"""
        current_time = time.time()
        expired_messages = [
            msg_id for msg_id, timestamp in self.seen_messages.items()
            if current_time - timestamp > self.message_ttl
        ]
        
        for msg_id in expired_messages:
            del self.seen_messages[msg_id]
        
        if expired_messages:
            self.logger.debug(f"Cleaned up {len(expired_messages)} expired messages")

    def _is_message_seen(self, message_id: str) -> bool:
        """Check if a message has been seen before"""
        return message_id in self.seen_messages

    def _mark_message_seen(self, message_id: str):
        """Mark a message as seen with current timestamp"""
        self.seen_messages[message_id] = time.time()

    def buildProtocol(self, addr):
        """Create a new P2PNode protocol instance"""
        node = P2PNode(self, self.peers)  # Pass the factory instance to P2PNode
        return node
    
    def _increment_connection_count(self):
        """Private method to increment connection count"""
        self._connection_count += 1
        self.logger.info(f"Connection established. Connection count: {self._connection_count}")

    def _decrement_connection_count(self):
        """Private method to decrement connection count"""
        self._connection_count -= 1
        self.logger.info(f"Connection lost. Connection count: {self._connection_count}")

    def get_connection_count(self) -> int:
        """Private method to get current connection count"""
        return self._connection_count

    def send_message(self, message: dict, peer_transport: Optional[Any] = None) -> None:
        """Send a message to all connected peers or a specific peer."""
        if "message_id" in message:
            self._mark_message_seen(message["message_id"])
        else:
            self.logger.warning("Message without message_id generating id...")
            message_id = str(uuid.uuid4())
            message["message_id"] = message_id
            self._mark_message_seen(message_id)

        # Ensure the message has required fields
        if "message_type" not in message:
            self.logger.error("Message must have a 'message_type' field.")
            return
        if "peer_id" not in message:
            self.logger.warning("Message must have a 'peer_id' field. Setting to factory ID.")
            message["peer_id"] = self.id

        serialized_message = json.dumps(message) + "\n"
        data = serialized_message.encode("utf-8")

        if peer_transport:
            peer_transport.write(data)
        else:
            for transport in self.peers.get_peer_transports():
                transport.write(data)

    def send_to_peer(self, peer_id: str, message: dict) -> None:
        """Send a message to a specific peer identified by peer_id.
        If the peer is not connected, the message will be sent to all connected peers.
        :param peer_id: Identifier for the peer.
        :param message: The message to send, which must include 'message_type' and 'payload'.
        """
        # Ensure target_id is set
        message["target_id"] = peer_id
        
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
            self.logger.info(f"Peer {peer_id} is not currently connected. Sending to all connected peers.")
            self.send_message(message)
        else:
            self.logger.info(f"Sending message to peer {peer_id}")
            self.send_message(message, transport)

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

    def set_shutting_down(self, shutting_down: bool):
        """Set the shutdown state to distinguish intentional vs unintentional disconnections"""
        self._is_shutting_down = shutting_down

    def on_peer_connected(self):
        """Trigger the peer:connected event"""
        self._increment_connection_count()
        for listener in self.event_listeners.get('peer:connected', []):
            listener()

    def on_peer_disconnected(self):
        """Trigger the peer:disconnected event"""
        self._decrement_connection_count()
        
        # Check if this was the last connection and it wasn't intentional
        if self._connection_count == 0 and not self._is_shutting_down:
            self.logger.info("All connections lost unintentionally - triggering peer:all_disconnected event")
            for listener in self.event_listeners.get('peer:all_disconnected', []):
                listener()
        
        for listener in self.event_listeners.get('peer:disconnected', []):
            listener()

    def add_peer_discovered_event(self, peer_id: str):
        """Trigger the peer:discovered event"""
        for listener in self.event_listeners.get('peer:discovered', []):
            listener(peer_id)

    def emit_message(self, peer_id: str, message: dict):
        """Trigger the message event with formatted payload"""
        event_data = {
            'peer_id': peer_id,
            'message_type': message.get('message_type'),
            'payload': message.get('payload')
        }
        for listener in self.event_listeners.get('message', []):
            listener(event_data)