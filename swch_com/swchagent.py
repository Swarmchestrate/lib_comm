import logging
import uuid
import socket
import json

from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ServerEndpoint, TCP4ClientEndpoint, connectProtocol

from swch_com.factory import P2PFactory
from swch_com.node import P2PNode

class SwchAgent():
    def __init__(self, peer_id, universe, peer_type, listen_ip=None, listen_port=None, public_ip=None, public_port=None):
        self.logger = logging.getLogger(__name__)  # Initialize logger
        self.universe = universe
        self.peer_type = peer_type

        if not peer_id:
            peer_id = str(uuid.uuid4())

        if not public_ip or not public_port:
            public_ip = listen_ip
            public_port = listen_port

        self.peer_id = peer_id
        self.public_ip = public_ip
        self.public_port = public_port
        self.factory = P2PFactory(peer_id, peer_type, universe, public_ip, public_port)
        
        self._start_server(self.factory, listen_ip, listen_port)

    def register_message_handler(self, message_type, func ):
        self.factory.user_defined_msg_handlers[message_type] = func

    def send(self, peer_id: str, message_type: str, payload: dict):
        """Send a message to a specific peer with a message type and payload."""
        message = {
            'message_type': message_type,
            'payload': payload
        }
        self.factory.send_to_peer(peer_id, message)

    def broadcast(self, message_type: str, payload: dict):
        """Broadcast a message to all connected peers with a message type and payload."""
        message = {
            'message_type': message_type,
            'payload': payload
        }
        self.factory.broadcast_message(message)

    def get_connection_count(self) -> int:
        """Public method to get the current connection count"""
        return self.factory.get_connection_count()

    def _start_server(self, factory, ip, port):
        """Start a server to listen for incoming connections."""
        endpoint = TCP4ServerEndpoint(reactor, port, interface=ip)
        endpoint.listen(factory)

        logging.info(f"Peer listening for connections on {ip}:{port}...")

    def on(self, event_name: str, listener):
        """Register an event listener directly with the factory"""
        self.factory.add_event_listener(event_name, listener)
        return self

    def getConnectedPeers(self):
        """Returns a list of currently connected peers."""
        connected_peers = []
        for peer_id, peer_info in self.factory.peers.get_all_peers_items():
            # Skip own peer ID
            if peer_id == self.factory.id:
                continue
            # Check if peer has either local or remote transport
            if (peer_info.get('local', {}).get('transport') or 
                peer_info.get('remote', {}).get('transport')):
                connected_peers.append(peer_id)
        return connected_peers

    def connect(self, ip, port):
        def _connect():
            endpoint = TCP4ClientEndpoint(reactor, ip, port)
            protocol = P2PNode(self.factory, self.factory.peers, is_initiator=True)
            d = connectProtocol(endpoint, protocol)

            def on_connect(p):
                self.logger.info(f"Connected to peer at {ip}:{port} as initiator")

            d.addCallback(on_connect)
            d.addErrback(lambda e: logging.error(f"Failed to connect to {ip}:{port}: {e}"))

        # Schedule the connection within the reactor
        reactor.callWhenRunning(_connect)

    def disconnect(self, peer_id: str):
        """Disconnects from a specific peer."""
        peer_info = self.factory.peers.get_peer_info(peer_id)
        if not peer_info:
            self.logger.warning(f"Cannot disconnect: peer {peer_id} not found")
            return False

        # Close both local and remote connections if they exist
        for connection_type in ['local', 'remote']:
            if connection_type in peer_info and 'transport' in peer_info[connection_type]:
                transport = peer_info[connection_type]['transport']
                if transport:
                    transport.loseConnection()

        return True

    def run(self):
        """Start the Twisted reactor."""
        reactor.run()
