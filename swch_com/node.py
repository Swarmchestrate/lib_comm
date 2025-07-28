from twisted.internet.protocol import Protocol
from twisted.internet.task import LoopingCall
import uuid
import json
import logging
from typing import Optional, Dict, Any, List

from swch_com.peers import Peers

class P2PNode(Protocol):
    def __init__(self, factory, peers: Peers, is_initiator: bool = False):
        self.factory = factory
        self.peers = peers

        self.buffer = ""  # Buffer to hold partial messages
        self.is_initiator = is_initiator  # Track if this node initiated the connection
        self.remote_id: Optional[str] = None  # ID of the remote peer
        self.logger = logging.getLogger(__name__)  # Initialize logger

    def connectionMade(self):
        """Handle new connection."""
        peer = self.transport.getPeer()
        host = self.transport.getHost()

        peer_address = f"{peer.host}:{peer.port}"
        host_address = f"{host.host}:{host.port}"

        self.logger.info(f"Connected to peer at {peer_address} from {host_address}")

        self.send_welcome_info_to_peer()

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
            self.logger.info("Incoming message: %s",str(line))
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

        self.factory._mark_message_seen(message_id)

        message_type = message.get("message_type")

        match message_type:
            case "broadcast_peer_list_add":
                self.update_peer_list(message)
                self.factory.send_message(message)
            case "peer_list_add" | "peer_list_update":
                self.update_peer_list(message)
            case "peer_info":
                self.process_peer_info(message)
            case "broadcast_remove_peer":
                self.remove_peer(message)
                self.factory.send_message(message)
            case "send_message":
                self.factory.send_message(message)
            case _:
                # Forward message if we're not the target or not broadcast
                if target_id not in ("*", self.factory.id):
                    self.factory.send_to_peer(target_id, message)
                    return

                # Forward message if it is a broadcast
                if target_id == "*":
                    self.factory.send_message(message)

                # Handle message since it must be a broadcast or targeted user-defined message
                if message_type in self.factory.user_defined_msg_handlers:
                    func = self.factory.user_defined_msg_handlers[message_type]
                    func(message.get("peer_id",""), message.get("payload",""))
                else:
                    self.logger.warning(f"Unknown message type received: {message_type}")
                    self.logger.warning(f"Message content: {message}")

                # Emit message event
                self.factory.emit_message(message.get("peer_id", ""), message)

    def process_peer_info(self, message: Dict[str, Any]):
        """Update peer info upon receiving process_peer_info message."""
 
        peer_id = message.get("peer_id")
        peer_universe = message.get("peer_universe")
        peer_type = message.get("peer_type")

        self.logger.info("Received peer_info: {},{},{}".format(peer_id,peer_universe,peer_type))
        if not peer_id:
            self.logger.error("Received process_peer_info without id")
            return

        if not self.peers.get_peer_info(peer_id):
            self.logger.info(f"Adding peer {peer_id}")
            self.peers.add_peer(peer_id)
        elif self.peers.get_peer_info(peer_id)["public"]:
            self.logger.info(f"Peer {peer_id} found with connection details.")
        else:
            self.logger.info(f"Peer {peer_id} found without connection details.")
    
        peer = self.transport.getPeer()

        if self.is_initiator:
            self.peers.set_local_info(peer_id, peer.host, peer.port, self.transport)
        else:
            self.peers.set_remote_info(peer_id, peer.host, peer.port, self.transport)

        self.remote_id = peer_id
        #Update factory peer count
        self.factory.on_peer_connected()

        if self.is_initiator:
            self.logger.info(f"I ({peer_id}) am initiator. Broadcasting peer list...")
            self.broadcast_peer_list()
        else:
            if peer_type=="ra":
                self.send_peer_list(self.transport)

    def broadcast_peer_list(self):
        """Broadcast the known peer list to all connected peers."""
        message_id = str(uuid.uuid4())
        peer_list = [
            (peer_id, subdict["public"])
            for peer_id, subdict in self.peers.get_all_peers_items()
            if subdict["public"]
        ]
        message = {
            "message_type": "broadcast_peer_list_add",
            "message_id": message_id,
            "peer_id": self.factory.id,
            "peers": peer_list
        }
        self.factory.send_message(message)

    def send_peer_list(self, transport):
        message_id = str(uuid.uuid4())
        peer_list = [
            (peer_id, subdict["public"])
            for peer_id, subdict in self.peers.get_all_peers_items()
            if subdict["public"]
        ]
        message = {
            "message_type": "peer_list_add",
            "message_id": message_id,
            "peer_id": self.factory.id,
            "peers": peer_list
        }
        self.factory.send_message(message, transport)

    def broadcast_remove_peer(self, peer_id: str):
        """Broadcast a message to all peers to remove a disconnected peer."""
        message_id = str(uuid.uuid4())
        message = {
            "message_type": "broadcast_remove_peer",
            "message_id": message_id,
            "peer_id": self.factory.id,
            "peer_id": peer_id
        }
        self.factory.send_message(message)

    def send_welcome_info_to_peer(self):
        """Send peer info to the connected peer."""
        message_id = str(uuid.uuid4())
        message = {
            "message_type": "peer_info",
            "message_id": message_id,
            "peer_id": self.factory.id,
            "peer_universe": self.factory.universe,
            "peer_type": self.factory.type
        }
        self.factory.send_message(message, peer_transport=self.transport)

    def update_peer_list(self, message: Dict[str, Any]):
        """Update the known peer list."""
        peers = message.get("peers", [])
        changed = False

        for peer_id, public in peers:
            peer_info = self.peers.get_peer_info(peer_id)

            # If we have no info yet, or we have info but no public data
            if not peer_info or not peer_info.get("public"):
                self.logger.info("Received new peer public info")
                self.peers.set_public_info(peer_id, public["host"], public["port"])
                changed = True

        if changed:
            # Emit peer discovered event
            self.factory.add_peer_discovered_event(peer_id)
            #Propagate peer list changes
            self.broadcast_peer_list()
            # Log the updated peer list
            self.log_public_peer_list()

    def remove_peer(self, message: Dict[str, Any]):
        """Remove a peer from all_peers."""
        peer_id = message.get("peer_id")
        if peer_id:
            if self.peers.remove_peer_info(peer_id):
                self.log_public_peer_list(message=f"Peer {peer_id} disconnected. Updated peer list")    
            else:
                self.logger.warning(f"Peer {peer_id} not found in peer list.")

    def connectionLost(self, reason):
        """Handle lost connection."""
        if self.remote_id:
            peer_id = self.remote_id
            if self.peers.get_peer_info(peer_id):
                if self.is_initiator:
                    self.peers.remove_peer_info(peer_id,"local")
                else:
                    self.peers.remove_peer_info(peer_id,"remote")
                
                if not (self.peers.get_peer_info(peer_id)["local"] or
                        self.peers.get_peer_info(peer_id)["remote"]):
                    self.peers.remove_peer_info(peer_id)
                    self.log_public_peer_list(message=f"Peer {peer_id} disconnected. Updated peer list")
                    self.broadcast_remove_peer(peer_id)

                #update factory peer count
                self.factory.on_peer_disconnected()

    def log_public_peer_list(self, message: str = "Peer list updated"):
        self.logger.info(
            f"\n{'-'*13}\n{message}:\n" +
            "\n".join(f"id: {pid}, host: {info['public']['host']}, port: {info['public']['port']}" 
                    for pid, info in self.peers.get_all_peers_items() if info["public"]) +
            f"\n{'-'*13}"
        )

