import logging
import uuid

from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ServerEndpoint, TCP4ClientEndpoint, connectProtocol

from swch_com.factory import P2PFactory
from swch_com.node import P2PNode

class SWCH_com():
    def __init__(self, id, universe, type, listen_ip=None, listen_port=None, public_ip=None, public_port=None, min_connection_count=1):
        self.connectionCount = 0
        self.min_connection_count = min_connection_count

        if not id:
            id = str(uuid.uuid4())

        if not public_ip or not public_port:
            public_ip = listen_ip
            public_port = listen_port

        self.factory = P2PFactory(id, universe, type, public_ip,public_port)
        self.start_server(self.factory,listen_ip,listen_port)

        self.factory.add_event_listener('peer_connected', self.handle_peer_connected)
        self.factory.add_event_listener('peer_disconnected', self.handle_peer_disconnected)

        self.logger = logging.getLogger(__name__)  # Initialize logger

    def register_message_handler(self, message_type, func ):
        self.factory.node.user_defined_msg_handlers[message_type] = func

    def send_message(self, clientid, message):
        peer_info = self.factory.all_peers.get_peer_info(clientid)
        transport = None
        for location in ["remote", "local"]:
                location_info = peer_info.get(location)
                if location_info and "transport" in location_info:
                    transport = location_info["transport"]
        self.factory.node.send_message(message, transport)

    def handle_peer_connected(self):
        self.connectionCount += 1
        self.logger.info(f"Connection established. Connection count: {self.connectionCount}")

    def handle_peer_disconnected(self):
        self.connectionCount -= 1
        self.logger.info(f"Connection lost. Connection count: {self.connectionCount}")
        if self.connectionCount < self.min_connection_count:
            self.rejoin_network()

    def start_server(self, factory, ip, port):
        """Start a server to listen for incoming connections."""
        endpoint = TCP4ServerEndpoint(reactor, port, interface=ip)
        endpoint.listen(factory)

        logging.info(f"Peer listening for connections on {ip}:{port}...")

    def connect_to_peer(self, ip, port):
        def _connect():
            endpoint = TCP4ClientEndpoint(reactor, ip, port)
            protocol = P2PNode(self.factory, is_initiator=True)
            d = connectProtocol(endpoint, protocol)

            def on_connect(p):
                self.logger.info(f"Connected to peer at {ip}:{port} as initiator")

            d.addCallback(on_connect)
            d.addErrback(lambda e: logging.error(f"Failed to connect to {ip}:{port}: {e}"))

        # Schedule the connection within the reactor
        reactor.callWhenRunning(_connect)

    def rejoin_network(self):
        self.logger.info("Rejoin triggered")
        for peer_id, peer_con in self.factory.all_peers.get_all_peers_items():
            #Temporary solution, to be fixed
            if (peer_id != self.factory.id) and peer_con["public"]:
                peer_host = peer_con['public'].get('host',"")
                peer_port = peer_con['public'].get('port',"")
                self.logger.info(f"Connecting to peer: {peer_id} : {peer_host}:{peer_port}")
                self.connect_to_peer(peer_host, peer_port)
        
    def run(self):
        """Start the Twisted reactor."""
        reactor.run()
