import logging
import json
import uuid
import time
from typing import Optional, Dict, Any, List

from twisted.internet.protocol import Factory
from twisted.internet.task import LoopingCall

from swchp2pcom.node import P2PNode
from swchp2pcom.peers import Peers
from swchp2pcom.message_types import SystemMessageType

class P2PFactory(Factory):
    def __init__(self, peer_id: str, metadata: dict, public_ip: Optional[str] = None, public_port: Optional[str] = None):
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

        self.user_defined_msg_handlers=dict()
        
        self.event_listeners = {
            'entered': [],
            'left': [],
            'peer:connected': [],
            'peer:disconnected': [],
            'peer:discovered': [],
            'peer:undiscovered': [],
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

    def _decrement_connection_count(self):
        """Private method to decrement connection count"""
        self._connection_count -= 1

    def disconnect_from_peer(self, peer_id: str) -> None:
        """Disconnect from a specific peer by closing their transport connection."""
        peer_info = self.peers.get_peer_info(peer_id)
        if not peer_info:
            self.logger.warning(f"Cannot disconnect: peer {peer_id} not found")
            raise ValueError(f"No such peer {peer_id} in registry.")
        # Close both local and remote connections if they exist
        for connection_type in ['local', 'remote']:
            if connection_type in peer_info and 'transport' in peer_info[connection_type]:
                transport = peer_info[connection_type]['transport']
                if transport:
                    transport.loseConnection()      

    def get_connection_count(self) -> int:
        """Private method to get current connection count"""
        return self._connection_count

    def send_message(self, message: dict, peer_transport: Optional[Any] = None) -> None:
        """Send a message to all connected peers or a specific peer."""
        if "message_id" in message:
            self._mark_message_seen(message["message_id"])
        else:
            self.logger.debug("Message without message_id generating id...")
            message_id = str(uuid.uuid4())
            message["message_id"] = message_id
            self._mark_message_seen(message_id)

        # Ensure the message has required fields
        if "message_type" not in message:
            self.logger.error("Message must have a 'message_type' field.")
            return
        if "peer_id" not in message:
            self.logger.debug("Message must have a 'peer_id' field. Setting to factory ID.")
            message["peer_id"] = self.id

        if message.get("peer_id") != self.id:
            self.logger.debug(f"Forwarding message: {message}")
        else:
            self.logger.debug(f"Sending message {message}")

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
            self.logger.error(f"No such peer {peer_id} in registry.")
            raise ValueError(f"No such peer {peer_id} in registry.")

        if message.get("target_id") == self.id:
            self.logger.debug("Message is targeted to self, emitting message event.")
            self.emit_message(self.id, message)
            return

        # Find an active transport (local or remote) for that peer
        transport = None
        for loc in ("remote", "local"):
            info = peer_info.get(loc)
            if info and "transport" in info:
                transport = info["transport"]
                break
        if not transport:
            self.logger.debug(f"Peer {peer_id} is not currently connected. Sending to all connected peers.")
            self.send_message(message)
        else:
            self.logger.debug(f"Sending message to peer {peer_id}")
            self.send_message(message, transport)

    def broadcast_remove_peer(self, peer_id: str):
        """Broadcast a message to all peers to remove a disconnected peer."""
        message_id = str(uuid.uuid4())
        message = {
            "message_type": SystemMessageType.BROADCAST_REMOVE_PEER.value,
            "message_id": message_id,
            "peer_id": self.id,
            "remove_peer_id": peer_id,
        }
        self.send_message(message)

    def send_intentional_disconnect(self, peer_id: str):
        """Send a message to indicate an intentional disconnect."""
        message_id = str(uuid.uuid4())
        message = {
            "message_type": SystemMessageType.SEND_INTENTIONAL_DISCONNECT.value,
            "message_id": message_id,
            "peer_id": self.id,
        }
        self.send_to_peer(peer_id, message)

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

    def on_entered_event(self):
        """Trigger the entered event"""
        self.logger.info(f"Successfully entered the network.")
        for listener in self.event_listeners.get('entered', []):
            listener()

    def on_left_event(self):
        """Trigger the left event"""
        self.logger.info(f"Left the network.")
        for listener in self.event_listeners.get('left', []):
            listener()

    def on_peer_connected_event(self, peer_id: str):
        """Trigger the peer:connected event"""
        self._increment_connection_count()
        self.logger.info(f"Connection established with {peer_id}. Connection count: {self._connection_count}")
        for listener in self.event_listeners.get('peer:connected', []):
            listener(peer_id)

    def on_peer_disconnected_event(self, peer_id: str):
        """Trigger the peer:disconnected event"""
        self._decrement_connection_count()
        self.logger.info(f"Connection lost with {peer_id}. Connection count: {self._connection_count}")
        
        # Check if this was the last connection and it wasn't intentional
        if self._connection_count == 0:
            self.logger.info("Disconnected from all peers.")
            for listener in self.event_listeners.get('peer:all_disconnected', []):
                listener()
        
        for listener in self.event_listeners.get('peer:disconnected', []):
            listener(peer_id)

    def on_peer_discovered_event(self, peer_id: str):
        """Trigger the peer:discovered event"""
        self.logger.info(f"Peer discovered: {peer_id}")
        for listener in self.event_listeners.get('peer:discovered', []):
            listener(peer_id)
    
    def on_peer_undiscovered_event(self, peer_id: str):
        """Trigger the peer:undiscovered event"""
        self.logger.info(f"Peer undiscovered: {peer_id}")
        for listener in self.event_listeners.get('peer:undiscovered', []):
            listener(peer_id)

    def emit_message(self, peer_id: str, message: dict):
        """Trigger the message event with formatted payload and trigger the registered handler"""
        self.logger.debug(f"Message event triggered with {peer_id}: {message}")

        message_type = message.get('message_type')

        if message_type in self.user_defined_msg_handlers:
            func = self.user_defined_msg_handlers[message_type]
            func(message.get("peer_id",""), message.get("payload",""))
        else:
            self.logger.warning(f"Unknown message type received: {message_type}")

        event_data = {
            'peer_id': peer_id,
            'message_type': message_type,
            'payload': message.get('payload')
        }
        for listener in self.event_listeners.get('message', []):
            listener(event_data)