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
        self.connectionCount = 0
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
        self.start_server(self.factory, listen_ip, listen_port)

        self.factory.add_event_listener('peer_connected', self.handle_peer_connected)
        self.factory.add_event_listener('peer_disconnected', self.handle_peer_disconnected)

        self.event_handlers = {
            'peer:discovered': [],
            'peer:connected': [],
            'peer:disconnected': []
        }

        # Register internal event handlers
        self.factory.add_event_listener('peer_discovered', lambda peer_id: self._emit('peer:discovered', peer_id))
        self.factory.add_event_listener('peer_connected', lambda: self._emit('peer:connected', None))
        self.factory.add_event_listener('peer_disconnected', lambda: self._emit('peer:disconnected', None))

    def register_message_handler(self, message_type, func ):
        self.factory.user_defined_msg_handlers[message_type] = func

    def send_message(self, clientid: str, message: dict):
        if not clientid:
            self.factory.broadcast_message(message)
        else:
            self.factory.send_to_peer(clientid, message)

    def handle_peer_connected(self):
        self.connectionCount += 1
        self.logger.info(f"Connection established. Connection count: {self.connectionCount}")

    def handle_peer_disconnected(self):
        self.connectionCount -= 1
        self.logger.info(f"Connection lost. Connection count: {self.connectionCount}")
        if self.connectionCount == 0:
            self.factory.peers.clear_peers()
            self.logger.info("Disconnected from all peers. Peer list cleared")

    def start_server(self, factory, ip, port):
        """Start a server to listen for incoming connections."""
        endpoint = TCP4ServerEndpoint(reactor, port, interface=ip)
        endpoint.listen(factory)

        logging.info(f"Peer listening for connections on {ip}:{port}...")

    def on(self, event_name: str, listener):
        """Register an event listener for the specified event."""
        if event_name in self.event_handlers:
            self.event_handlers[event_name].append(listener)
        else:
            raise ValueError(f"Unknown event type: {event_name}")

    def _emit(self, event_name: str, data=None):
        """Internal method to emit events to registered listeners."""
        if event_name in self.event_handlers:
            for listener in self.event_handlers[event_name]:
                if data is not None:
                    listener(data)
                else:
                    listener()

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
