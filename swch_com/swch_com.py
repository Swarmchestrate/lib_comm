import logging
import uuid
import socket
import json

from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ServerEndpoint, TCP4ClientEndpoint, connectProtocol

from swch_com.factory import P2PFactory
from swch_com.node import P2PNode

class SwChResourceAgent():
    def __init__(self, id, universe, type, listen_ip=None, listen_port=None, public_ip=None, public_port=None, min_connection_count=1):
        self.connectionCount = 0
        self.min_connection_count = min_connection_count

        if not id:
            id = str(uuid.uuid4())

        if not public_ip or not public_port:
            public_ip = listen_ip
            public_port = listen_port

        self.factory = P2PFactory(id, type, universe, public_ip,public_port)
        self.start_server(self.factory,listen_ip,listen_port)

        self.factory.add_event_listener('peer_connected', self.handle_peer_connected)
        self.factory.add_event_listener('peer_disconnected', self.handle_peer_disconnected)

        self.logger = logging.getLogger(__name__)  # Initialize logger

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
            protocol = P2PNode(self.factory, self.factory.peers, is_initiator=True)
            d = connectProtocol(endpoint, protocol)

            def on_connect(p):
                self.logger.info(f"Connected to peer at {ip}:{port} as initiator")

            d.addCallback(on_connect)
            d.addErrback(lambda e: logging.error(f"Failed to connect to {ip}:{port}: {e}"))

        # Schedule the connection within the reactor
        reactor.callWhenRunning(_connect)

    def rejoin_network(self):
        self.logger.info("Rejoin triggered")
        for peer_id, peer_con in self.factory.peers.get_all_peers_items():
            #Temporary solution, to be fixed
            if (peer_id != self.factory.id) and peer_con["public"]:
                peer_host = peer_con['public'].get('host',"")
                peer_port = peer_con['public'].get('port',"")
                self.logger.info(f"Connecting to peer: {peer_id} : {peer_host}:{peer_port}")
                self.connect_to_peer(peer_host, peer_port)
        
    def run(self):
        """Start the Twisted reactor."""
        reactor.run()


class SwChClient():
    def __init__(self, myid: str, myuniverse: str):
        self.myid = myid
        self.myuniverse = myuniverse
        self.mytype = "CL"
        self.connectedRA={'id': None, 'host': None, 'port': None}
        self.message_buffer = ""
        self.message_lines = []

    def connect_to_RA(self, host: str, port: int) -> None:
        try:
            self.sock = socket.create_connection((host, port))
            #print(f"Connected to {host}:{port}.")
        except (socket.error, OSError) as e:
            print(f"Error: {e}")
        
        welcome_message = {
            "message_type": "peer_info",
            "message_id": str(uuid.uuid4()),
            "peer_id": self.myid,
            "peer_universe": self.myuniverse,
            "peer_type": self.mytype
        }
        serialized_message = json.dumps(welcome_message) + "\n"
        data = serialized_message.encode("utf-8")
        try:
            self.sock.sendall(data)
        except (socket.error, OSError) as e:
            print(f"Socket error: {e}")

        message = self.wait_message()
        peer_id = message.get("peer_id")
        peer_universe = message.get("peer_universe")
        peer_type = message.get("peer_type")

        if self.myuniverse != peer_universe:
            print(f"Remote peer\'s universe (\"%s\") does not match! Exiting..." % peer_universe)
            exit(1)
        if peer_type != "ra":
            print("Remote peer is not an RA! Exiting...")
            exit(1)
        print(f"Successfully connected to RA with id \"%s\"." % peer_id)
        self.connectedRA['id'] = peer_id
        self.connectedRA['host'] = host
        self.connectedRA['port'] = port
        return

    def send_message(self, message_type: str, message_body: dict) -> None:
        message = {
            "peer_id": self.connectedRA['id'],
            "message_id": str(uuid.uuid4()),

            "message_type": message_type,
            "message_body": message_body 
        }
        serialized_message = json.dumps(message) + "\n"
        data = serialized_message.encode("utf-8")
        try:
            self.sock.sendall(data)
            #print(f"Sent message \"{message}\" to {self.host}:{self.port}.")        
        except (socket.error, OSError) as e:
            print(f"Socket error: {e}")
        return
    
    def recv_message(self) -> None:
        return
    
    def wait_message(self) -> dict:
        try:
            while True:
                if not self.message_lines:
                    data = self.sock.recv(1024)  # Receive up to 1024 bytes
                    if not data:
                        break  # Connection closed by server
                    try:
                        decoded_data = data.decode("utf-8")
                    except UnicodeDecodeError:
                        print("Received non-UTF-8 data.")
                
                    self.message_buffer += decoded_data
                    lines = self.message_buffer.split("\n")
                    self.message_lines += lines
                    self.message_buffer = self.message_lines.pop()  # Save incomplete data
                
                message = self.message_lines.pop(0)
                try:
                    parsed_message = json.loads(message)
                except json.JSONDecodeError as e:
                    print(f"Error decoding message: {e}")                
                return parsed_message
        except (socket.error, OSError) as e:
            print(f"Error: {e}")
    
    def disconnect_from_RA(self) -> None:
        try:
            self.sock.close()
        except (socket.error, OSError) as e:
            print(f"Error: {e}")