from twisted.internet.protocol import Protocol
from twisted.internet.task import LoopingCall
import uuid
import json
import logging
from typing import Optional, Dict, Any, List

from swchp2pcom.peers import Peers
from swchp2pcom.message_types import SystemMessageType

class P2PNode(Protocol):
    def __init__(self, factory, peers: Peers, is_initiator: bool = False, is_entering: bool = False):
        self.factory = factory
        self.peers = peers

        self.buffer = ""  # Buffer to hold partial messages
        self.is_initiator = is_initiator  # Track if this node initiated the connection
        self.is_entering = is_entering # Track if this node is created for entering the network
        self.remote_id: Optional[str] = None  # ID of the remote peer
        self.logger = logging.getLogger(__name__)  # Initialize logger

    def connectionMade(self):
        """Handle new connection."""
        peer = self.transport.getPeer()
        host = self.transport.getHost()

        peer_address = f"{peer.host}:{peer.port}"
        host_address = f"{host.host}:{host.port}"

        self.logger.debug(f"Connected to peer at {peer_address} from {host_address}")
        if self.is_initiator:
            self.logger.info(f"Made connection to a peer...")
        else:
            self.logger.info(f"Peer made connection to us...")

        self.send_welcome_info()

    def dataReceived(self, data: bytes):
        """Handle incoming data."""
        try:
            decoded_data = data.decode("utf-8")
        except UnicodeDecodeError as e:
            self.logger.error(f"Error decoding data: {e}")
            return

        self.buffer += decoded_data
        lines = self.buffer.split("\n")
        self.buffer = lines.pop()  # Save incomplete data

        for line in lines:
            if not line.strip():
                continue  # Skip empty lines
            try:
                parsed_message = json.loads(line)
                self.process_message(parsed_message)
            except json.JSONDecodeError as e:
                self.logger.error(f"Error decoding message: {e}")

    def process_message(self, message: Dict[str, Any]):
        """Handle and forward broadcast messages."""
        message_id = message.get("message_id")
        target_id = message.get("target_id")
        
        if not message_id:
            self.logger.warning("Received message without message_id")
            return

        if self.factory._is_message_seen(message_id):
            return  # Deduplicate messages

        self.logger.debug(f"Received message: {message}")
        self.factory._mark_message_seen(message_id)

        message_type = message.get("message_type")

        match message_type:
            case SystemMessageType.BROADCAST_PEER_LIST_UPDATE.value:
                self.handle_peer_list_update(message)
            case SystemMessageType.SEND_WELCOME_INFO.value:
                self.handle_welcome_info(message)
            case SystemMessageType.BROADCAST_REMOVE_PEER.value:
                self.handle_remove_peer(message)
            case SystemMessageType.SEND_INTENTIONAL_DISCONNECT.value:
                self.handle_intentional_disconnect(message)
            case _:
                # Forward message if we're not the target or not broadcast
                if target_id not in ("*", self.factory.id):
                    self.factory.send_to_peer(target_id, message)
                    return

                # Forward message if it is a broadcast
                if target_id == "*":
                    self.factory.send_message(message)

                # Emit message event
                self.factory.emit_message(message.get("peer_id", ""), message)

    def send_welcome_info(self):
        """Send peer info to the connected peer."""
        message_id = str(uuid.uuid4())
        peer_public_info_list = self.factory.peers.get_known_peers_public_info()
        message = {
            "message_type": SystemMessageType.SEND_WELCOME_INFO.value,
            "message_id": message_id,
            "peer_id": self.factory.id,
            "peer_public_info": self.peers.get_peer_info(self.factory.id)["public"],
            "peer_metadata": self.peers.get_peer_metadata(self.factory.id),
            "peers": peer_public_info_list
        }
        self.factory.send_message(message, peer_transport=self.transport)

    def handle_welcome_info(self, message: Dict[str, Any]):
        """Update peer info upon receiving process_peer_info message."""
        remote_peer_id = message.get("peer_id")

        if not remote_peer_id:
            self.logger.error(f"Received {message.get("message_type")} without id")
            return
        
        # Store the remote peer ID
        self.remote_id = remote_peer_id

        is_new_peer = not self.peers.get_peer_info(remote_peer_id)

        if is_new_peer:
            # Add new peer to the peer list
            self.peers.add_peer(remote_peer_id)
            self.peers.set_public_info(remote_peer_id, message["peer_public_info"]["host"], message["peer_public_info"]["port"])
            self.peers.set_peer_metadata(remote_peer_id, message.get("peer_metadata", {}))
            
        # Set the transport information for the peer
        peer = self.transport.getPeer()
        if self.is_initiator:
            self.peers.set_local_info(remote_peer_id, peer.host, peer.port, self.transport)
        else:
            self.peers.set_remote_info(remote_peer_id, peer.host, peer.port, self.transport)

        # Raise peer discovered and connected events
        if is_new_peer:
            self.factory.on_peer_discovered_event(remote_peer_id)
        self.factory.on_peer_connected_event(remote_peer_id)

        # Process the peers list from the welcome message
        for peer_id, public_info, metadata in message.get("peers", []):
            if not self.peers.get_peer_info(peer_id):
                # Add new peer to the peer list
                self.peers.add_peer(peer_id)
                self.peers.set_public_info(peer_id, public_info["host"], public_info["port"])
                self.peers.set_peer_metadata(peer_id, metadata)

                # Raise peer discovered event
                self.factory.on_peer_discovered_event(peer_id)

        # Let others know about the new peer in the network
        if is_new_peer and len(self.peers.get_all_peers_items()) > 2:
            # If this is a new peer, broadcast the updated peer list
            self.broadcast_peer_list_update()

        if (not self.is_entering) and is_new_peer:
            # Log the public peer list
            self.log_public_peer_list(message=f"Peer {remote_peer_id} entered. Updated peer list")

        if self.is_entering:
            self.log_public_peer_list(message=f"Recieved peers after entering. Current peers")
            self.factory.on_entered_event()
            self.is_entering = False  # Reset entering state

    def broadcast_peer_list_update(self):
        """Broadcast the known peer list to all connected peers."""
        message_id = str(uuid.uuid4())
        peer_public_info_list = self.factory.peers.get_known_peers_public_info()
        message = {
            "message_type": SystemMessageType.BROADCAST_PEER_LIST_UPDATE.value,
            "message_id": message_id,
            "peer_id": self.factory.id,
            "peers": peer_public_info_list
        }
        self.factory.send_message(message)

    def handle_peer_list_update(self, message: Dict[str, Any]):
        """Update the known peer list."""
        peers = message.get("peers", [])
        any_changed = False

        for peer_id, public_info, metadata in peers:
            old = self.peers.get_peer_info(peer_id)

            if not old:
                # Add new peer to the peer list
                self.peers.add_peer(peer_id)
                self.peers.set_public_info(peer_id, public_info["host"], public_info["port"])
                self.peers.set_peer_metadata(peer_id, metadata)
                any_changed = True

                self.factory.on_peer_discovered_event(peer_id)
            if old and (old.get("public") != public_info):
                self.logger.info(f"New public info for peer: {peer_id}, public_info: {public_info}")
                self.peers.set_public_info(peer_id, public_info["host"], public_info["port"])
                any_changed = True

            if old and (old.get("metadata") != metadata):
                self.logger.info(f"New metadata for peer: {peer_id}, metadata: {metadata}")
                self.peers.set_peer_metadata(peer_id, metadata)
                any_changed = True

        if any_changed:
            self.log_public_peer_list()

        # Forward the update peer list message to all peers
        self.factory.send_message(message)

    def handle_remove_peer(self, message: Dict[str, Any]):
        """Remove a peer from all_peers."""
        peer_id = message.get("remove_peer_id")
        if peer_id:
            # Raise peer undiscovered event
            self.factory.on_peer_undiscovered_event(peer_id)

            if self.peers.remove_peer_info(peer_id):
                self.log_public_peer_list(message=f"Peer {peer_id} left. Peer list updated")    
            else:
                self.logger.debug(f"Peer {peer_id} not found in peer list.")
            
        # Propagate the removal to other peers
        self.factory.send_message(message)

    def handle_intentional_disconnect(self, message: Dict[str, Any]):
        """Handle intentional disconnect from a peer."""
        self.peers.set_is_intentional_disconnect(message.get("peer_id"),True)

    def connectionLost(self, reason):
        """Handle lost connection."""
        self.logger.debug(f"Connection lost: {reason.getErrorMessage()}")

        if not self.remote_id:
            self.logger.debug("Remote ID is not set, cannot handle disconnection properly.")
            return

        # If we doesnt have information about the peer (Could be because we already removed him, or the peer was never added)
        if not self.peers.get_peer_info(self.remote_id):
            self.factory.on_peer_disconnected_event(self.remote_id)
            return

        # If it wasnt intentional
        if not self.peers.get_is_intentional_disconnect(self.remote_id):
            self.logger.debug("Unintentional disconnect detected, removing peer info.")
            self.factory.on_peer_undiscovered_event(self.remote_id)
            
            self.peers.remove_peer_info(self.remote_id)
            self.factory.on_peer_disconnected_event(self.remote_id)
            
            # Broadcast the removal of the peer
            self.factory.broadcast_remove_peer(self.remote_id)

            # log the public peer list
            self.log_public_peer_list(message=f"Peer {self.remote_id} left. Peer list updated")
        # If it was intentional, and he doesnt needs to be removed from the network
        else:
            if self.peers.get_peer_info(self.remote_id):
                if self.is_initiator:
                    self.peers.remove_peer_info(self.remote_id,"local")
                else:
                    self.peers.remove_peer_info(self.remote_id,"remote")

            # Reset the intentional disconnect flag
            self.peers.set_is_intentional_disconnect(self.remote_id, False)
            # Raise peer disconnected event
            self.factory.on_peer_disconnected_event(self.remote_id)

    def log_public_peer_list(self, message: str = "Peer list updated"):
        self.logger.info(
            f"\n{'-'*13}\n{message}:\n" +
            "\n".join(f"id: {pid}, host: {info['public']['host']}, port: {info['public']['port']}" 
                    for pid, info in self.peers.get_all_peers_items() if info["public"]) +
            f"\n{'-'*13}"
        )

