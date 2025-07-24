import logging
import uuid
import socket
import json

from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ServerEndpoint, TCP4ClientEndpoint, connectProtocol

from swch_com.factory import P2PFactory
from swch_com.node import P2PNode

class SwchAgent():
    def __init__(self, peer_id, universe, peer_type, listen_ip, listen_port, public_ip=None, public_port=None):
        """
        Initialize the SwchAgent with peer ID, universe, peer type, and network settings.
        :param peer_id: Unique identifier for the peer.
        :param universe: The universe this peer belongs to.
        :param peer_type: The type of the peer (e.g., 'ra', 'sa').
        :param listen_ip: The IP address to listen on for incoming connections.
        :param listen_port: The port to listen on for incoming connections.
        :param public_ip: The advertised IP address of the peer (if different from listen_ip).
        :param public_port: The advertised port of the peer (if different from listen_port).
        """
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
        """Register a custom message handler for a specific message type.
        :param message_type: The type of message to handle.
        :param func: The function to call when a message of this type is received.
        The function should accept two parameters: sender_id and message.
        :return: None
        """
        self.factory.user_defined_msg_handlers[message_type] = func

    def send(self, peer_id: str, message_type: str, payload: dict):
        """Send a message to a specific peer with a message type and payload.
        :param peer_id: The ID of the peer to send the message to.
        :param message_type: The type of the message being sent.
        :param payload: The payload of the message, which can be any serializable dictionary.
        :return: None
        """
        message = {
            'message_type': message_type,
            'payload': payload,
            'target_id': peer_id  # Add explicit target
        }
        self.factory.send_to_peer(peer_id, message)

    def broadcast(self, message_type: str, payload: dict):
        """Broadcast a message to all connected peers with a message type and payload.
        :param message_type: The type of the message being broadcast.
        :param payload: The payload of the message, which can be any serializable dictionary.
        :return: None
        """
        message = {
            'message_type': message_type,
            'payload': payload,
            'target_id': '*'  # Explicit broadcast marker
        }
        self.factory.send_message(message)

    def get_connection_count(self) -> int:
        """Public method to get the current connection count
        :return: The number of currently active connections.
        """
        return self.factory.get_connection_count()

    def _start_server(self, factory, ip, port):
        """Start a server to listen for incoming connections."""
        endpoint = TCP4ServerEndpoint(reactor, port, interface=ip)
        endpoint.listen(factory)

        logging.info(f"Peer listening for connections on {ip}:{port}...")

    def on(self, event_name: str, listener):
        """Register an event listener directly with the factory
        for a specific event.
        :param event_name: The name of the event to listen for.
        :param listener: The callback function to be called when the event occurs.
        :return: self for method chaining.
        """
        self.factory.add_event_listener(event_name, listener)
        return self

    def getConnectedPeers(self):
        """Returns a list of currently connected peers.
        This method checks both local and remote connections for each peer
        and returns a list of peer IDs that have an active transport.
        :return: List of peer IDs that are currently connected.
        """
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
        """Connect to a specific peer at the given IP and port.
        This method creates a TCP client endpoint and connects to the specified peer.
        It initializes a P2PNode protocol as the client initiator and handles the connection.
        :param ip: The IP address of the peer to connect to.
        :param port: The port of the peer to connect to.
        :return: None
        """
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
        """Disconnects from a specific peer.
        This method will close both local and remote connections if they exist.
        :param peer_id: The ID of the peer to disconnect from.
        :return: True if the disconnection was successful, False otherwise.
        """
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

    def shutdown(self):
        """Shuts down the P2P library, closing all connections and releasing resources.
        This method will:
        1. Disconnect from all connected peers
        2. Stop the reactor gracefully
        :return: None
        """
        self.logger.info("Shutting down SwchAgent...")
        
        # Disconnect from all connected peers
        connected_peers = self.getConnectedPeers()
        for peer_id in connected_peers:
            self.disconnect(peer_id)
        
        # Clear peer information
        self.factory.peers.clear_peers()

        self.logger.info("SwchAgent shutdown complete")

    def run(self):
        """Start the Twisted reactor."""
        self.logger.info("Starting Twisted reactor...")
        reactor.run()
        self.logger.info("Twisted reactor started")

    def stop(self):
        """Stop the Twisted reactor."""
        self.logger.info("Stopping Twisted reactor...")
        reactor.stop()
        self.logger.info("Twisted reactor stopped")
