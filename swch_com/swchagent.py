import logging
import uuid
import socket
import json
from typing import Optional, Dict, Any, List, Callable

from twisted.internet import reactor, defer
from twisted.internet.endpoints import TCP4ServerEndpoint, TCP4ClientEndpoint, connectProtocol
from twisted.internet.task import deferLater

from swch_com.factory import P2PFactory
from swch_com.node import P2PNode

class SwchAgent():
    def __init__(
        self, 
        peer_id: Optional[str], 
        listen_ip: str, 
        listen_port: int, 
        public_ip: Optional[str] = None, 
        public_port: Optional[int] = None, 
        metadata: Optional[Dict[str, Any]] = None, 
        enable_rejoin: bool = True
    ) -> None:
        """Initialize the SwchAgent with peer ID, network settings, and optional metadata.

        Args:
            peer_id: Unique identifier for the peer. If None, a UUID will be generated.
            listen_ip: The IP address to listen on for incoming connections.
            listen_port: The port to listen on for incoming connections.
            public_ip: The advertised IP address of the peer. Defaults to listen_ip if not provided.
            public_port: The advertised port of the peer. Defaults to listen_port if not provided.
            metadata: Optional dictionary containing peer metadata (e.g., universe, peer_type, etc.).
            enable_rejoin: Whether to enable automatic rejoin mechanism when all peers disconnect.
        """
        self.logger = logging.getLogger(__name__)  # Initialize logger

        if not peer_id:
            peer_id = str(uuid.uuid4())

        if not public_ip or not public_port:
            public_ip = listen_ip
            public_port = listen_port

        if metadata is None:
            metadata = {}

        self.peer_id = peer_id
        self.public_ip = public_ip
        self.public_port = public_port
        self.metadata = metadata
        self.factory = P2PFactory(peer_id, metadata, public_ip, public_port)
        
        # Rejoin mechanism settings
        self._rejoin_enabled = enable_rejoin
        self._rejoin_in_progress = False
        self._max_rejoin_attempts = 10
        self._rejoin_base_delay = 1  # Base delay in seconds
        
        # Set up rejoin mechanism
        self._setup_rejoin_mechanism()
        
        self._start_server(self.factory, listen_ip, listen_port)

    def _setup_rejoin_mechanism(self):
        """Set up the automatic rejoin mechanism"""
        def on_all_disconnected():
            if self._rejoin_enabled and not self._rejoin_in_progress:
                self.logger.info("All peers disconnected - starting rejoin process")
                reactor.callLater(0, self._attempt_rejoin)
        
        self.factory.add_event_listener('peer:all_disconnected', on_all_disconnected)

    def _attempt_rejoin(self):
        """Attempt to rejoin the network by connecting to known peers"""
        if self._rejoin_in_progress:
            return
        
        self._rejoin_in_progress = True
        self.logger.info("Starting rejoin attempts...")
        
        # Get all known peers with public information (excluding ourselves)
        known_peers = self.factory.peers.get_known_peers_public_info(exclude_peer_id=self.factory.id)
        
        if not known_peers:
            self.logger.warning("No known peers to reconnect to")
            self._rejoin_in_progress = False
            return
        
        self.logger.info(f"Found {len(known_peers)} known peers to attempt reconnection")
        
        # Start the rejoin process
        d = self._try_rejoin_with_peers(known_peers, 0)
        d.addBoth(lambda _: setattr(self, '_rejoin_in_progress', False))

    def _try_rejoin_with_peers(self, known_peers, attempt):
        """Try to rejoin with known peers using exponential backoff"""
        if attempt >= self._max_rejoin_attempts:
            self.logger.warning(f"Max rejoin attempts ({self._max_rejoin_attempts}) reached")
            return defer.succeed(None)
        
        if self.get_connection_count() > 0:
            self.logger.info("Successfully reconnected to network")
            return defer.succeed(None)
        
        # Calculate delay with exponential backoff
        delay = self._rejoin_base_delay * (2 ** min(attempt, 5))  # Cap at 32 seconds
        
        self.logger.info(f"Rejoin attempt {attempt + 1}/{self._max_rejoin_attempts} after {delay}s delay")
        
        # Try connecting to peers sequentially
        d = self._try_sequential_connections(known_peers, 0)
        
        def check_and_continue(success):
            if success or self.get_connection_count() > 0:
                self.logger.info("Successfully reconnected to network")
                return defer.succeed(None)
            # Wait for delay and try again if no connection was established
            return deferLater(reactor, delay, lambda: None).addCallback(
                lambda _: self._try_rejoin_with_peers(known_peers, attempt + 1)
            )
        
        d.addCallback(check_and_continue)
        return d

    def _try_sequential_connections(self, known_peers, peer_index):
        """Try connecting to peers sequentially, one at a time"""
        if peer_index >= len(known_peers):
            # Tried all peers, none succeeded
            return defer.succeed(False)
        
        if self.get_connection_count() > 0:
            # Already connected, stop trying
            return defer.succeed(True)
        
        peer_id, public_info, metadata = known_peers[peer_index]
        host = public_info["host"]
        port = public_info["port"]
        self.logger.debug(f"Attempting to connect to {peer_id} at {host}:{port}")
        
        d = self._attempt_single_connection(host, port)
        
        def on_result(result):
            # Check if we're now connected (connection might have succeeded)
            if self.get_connection_count() > 0:
                return defer.succeed(True)
            # Try next peer
            return self._try_sequential_connections(known_peers, peer_index + 1)
        
        def on_error(failure):
            # Connection failed, try next peer
            return self._try_sequential_connections(known_peers, peer_index + 1)
        
        d.addCallback(on_result)
        d.addErrback(on_error)
        return d

    def _attempt_single_connection(self, ip, port):
        """Attempt a single connection with proper error handling"""
        endpoint = TCP4ClientEndpoint(reactor, ip, port)
        protocol = P2PNode(self.factory, self.factory.peers, is_initiator=True)
        d = connectProtocol(endpoint, protocol)
        
        def on_connect(p):
            self.logger.info(f"Successfully reconnected to peer at {ip}:{port}")
            return p
        
        def on_error(failure):
            self.logger.debug(f"Failed to connect to {ip}:{port}: {failure.getErrorMessage()}")
            return failure
        
        d.addCallback(on_connect)
        d.addErrback(on_error)
        return d

    def enable_rejoin(self):
        """Enable the automatic rejoin mechanism"""
        self._rejoin_enabled = True
        self.logger.info("Rejoin mechanism enabled")

    def disable_rejoin(self):
        """Disable the automatic rejoin mechanism"""
        self._rejoin_enabled = False
        self.logger.info("Rejoin mechanism disabled")

    def is_rejoin_enabled(self):
        """Check if rejoin mechanism is enabled"""
        return self._rejoin_enabled

    def is_rejoin_in_progress(self):
        """Check if rejoin is currently in progress"""
        return self._rejoin_in_progress

    def register_message_handler(self, message_type: str, func: Callable[[str, Dict[str, Any]], None]) -> None:
        """Register a custom message handler for a specific message type.
        :param message_type: The type of message to handle.
        :param func: The function to call when a message of this type is received.
        The function should accept two parameters: sender_id and message.
        :return: None
        """
        self.factory.user_defined_msg_handlers[message_type] = func

    def send(self, peer_id: str, message_type: str, payload: Dict[str, Any]) -> None:
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

    def broadcast(self, message_type: str, payload: Dict[str, Any]) -> None:
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

    def on(self, event_name: str, listener: Callable) -> 'SwchAgent':
        """Register an event listener directly with the factory
        for a specific event.
        :param event_name: The name of the event to listen for.
        :param listener: The callback function to be called when the event occurs.
        :return: self for method chaining.
        """
        self.factory.add_event_listener(event_name, listener)
        return self

    def getConnectedPeers(self) -> List[str]:
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

    def connect(self, ip: str, port: int) -> None:
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

    def disconnect(self, peer_id: str) -> bool:
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

    def shutdown(self) -> defer.Deferred:
        """Shuts down the P2P library, closing all connections and releasing resources.
        This method will:
        1. Disable rejoin mechanism to prevent reconnection during shutdown
        2. Mark the agent as shutting down to prevent triggering unintentional disconnect events
        3. Disconnect from all connected peers and wait for disconnections to complete
        4. Clear peer information and reset shutdown state for potential reuse
        :return: A Deferred that fires when shutdown is complete
        """
        self.logger.info("Shutting down SwchAgent...")
        
        # Disable rejoin mechanism during shutdown
        self.disable_rejoin()
        
        # Mark as shutting down to prevent triggering all_disconnected event
        self.factory.set_shutting_down(True)
        
        # Get list of connected peers before starting disconnections
        connected_peers = self.getConnectedPeers()
        
        if not connected_peers:
            # No connections to close, complete shutdown immediately
            self._complete_shutdown()
            return defer.succeed(None)
        
        # Create a deferred that will fire when all disconnections are complete
        shutdown_deferred = defer.Deferred()
        remaining_disconnections = [len(connected_peers)]  # Use list for mutable reference
        
        def on_disconnection_complete():
            remaining_disconnections[0] -= 1
            self.logger.debug(f"Disconnection complete. Remaining: {remaining_disconnections[0]}")
            if remaining_disconnections[0] == 0:
                self._complete_shutdown()
                shutdown_deferred.callback(None)
        
        # Register temporary listener for disconnections during shutdown
        self.factory.add_event_listener('peer:disconnected', on_disconnection_complete)
        
        # Disconnect from all connected peers
        for peer_id in connected_peers:
            self.disconnect(peer_id)
        
        return shutdown_deferred
    
    def _complete_shutdown(self):
        """Complete the shutdown process by clearing peers and resetting state"""
        # Clear peer information
        self.factory.peers.clear_peers()
        
        # Reset shutdown state for potential reuse
        self.factory.set_shutting_down(False)
        
        # Re-enable rejoin mechanism for potential reuse
        self.enable_rejoin()
        
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

    def findPeers(self, metadata=None):
        """
        Searches for peers based on metadata criteria. 
        
        Args:
            metadata (dict, optional): Custom metadata to match
        
        Returns:
            list: List of matching peer IDs excluding self
        """
        if metadata is None:
            metadata = {}
        
        all_peers = self.factory.peers.get_all_peers_items()
        matching_peer_ids = []
        
        for peer_id, peer_info in all_peers:
            # Skip self
            if peer_id == self.peer_id:
                continue
                
            # Check metadata criteria
            if metadata:
                peer_metadata = peer_info.get('metadata', {})
                
                # Check if all search metadata fields match
                match = True
                for key, value in metadata.items():
                    if key not in peer_metadata or peer_metadata[key] != value:
                        match = False
                        break
                
                if match:
                    matching_peer_ids.append(peer_id)
            else:
                # No metadata criteria, return all peers
                matching_peer_ids.append(peer_id)
        
        return matching_peer_ids
