import logging
import uuid
from typing import Optional, Dict, Any, List, Callable

from twisted.internet import reactor, defer
from twisted.internet.endpoints import TCP4ServerEndpoint, TCP4ClientEndpoint, connectProtocol
from twisted.internet.task import deferLater

from swch_com.factory import P2PFactory
from swch_com.node import P2PNode
from swch_com.message_types import SystemMessageType

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
        
        self.logger.info(f"SwchAgent initialized with ID: {self.peer_id}, listening on {listen_ip}:{listen_port}, public IP: {public_ip}:{public_port}, metadata: {metadata}")
        self._start_server(self.factory, listen_ip, listen_port)

    def _setup_rejoin_mechanism(self):
        """Set up the automatic rejoin mechanism"""
        def on_all_disconnected():
            if self._rejoin_enabled and not self._rejoin_in_progress:
                self.logger.debug("Recieved all_disconnected event starting rejoin process")
                reactor.callLater(0, self._attempt_rejoin)
        
        self.factory.add_event_listener('peer:all_disconnected', on_all_disconnected)

    def _attempt_rejoin(self):
        """Attempt to rejoin the network by connecting to known peers"""
        if self._rejoin_in_progress:
            return
        
        self._rejoin_in_progress = True
        self.logger.info("Starting rejoin attempts...")
        
        # Start the rejoin process
        d = self._try_rejoin_with_peers(0)
        d.addBoth(lambda _: setattr(self, '_rejoin_in_progress', False))

    def _try_rejoin_with_peers(self, attempt):
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
        
        # Get all known peers with public information (excluding ourselves)
        known_peers = self.factory.peers.get_known_peers_public_info(exclude_peer_id=self.factory.id)
        if not known_peers:
            self.logger.warning("No peers available for rejoin")            

        # Try connecting to peers sequentially
        d = self._try_sequential_connections(known_peers, 0)
        
        def check_and_continue(success):
            if success or self.get_connection_count() > 0:
                self.logger.info("Successfully reconnected to network")
                return defer.succeed(None)
            # Wait for delay and try again if no connection was established
            return deferLater(reactor, delay, lambda: None).addCallback(
                lambda _: self._try_rejoin_with_peers(attempt + 1)
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
        
        def on_success(peer_id):
            return defer.succeed(True)

        def on_error(failure):
            # Connection failed, try next peer
            return self._try_sequential_connections(known_peers, peer_index + 1)
        
        #d.addCallback(on_result)
        self.factory.add_event_listener('peer:connected', on_success)
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
        """Enable the automatic rejoin mechanism for network resilience."""
        self._rejoin_enabled = True
        self.logger.info("Rejoin mechanism enabled")

    def disable_rejoin(self):
        """Disable the automatic rejoin mechanism."""
        self._rejoin_enabled = False
        self.logger.info("Rejoin mechanism disabled")

    def is_rejoin_enabled(self):
        """Check if the automatic rejoin mechanism is currently enabled.
        
        Returns:
            True if automatic rejoin is enabled, False otherwise.
        """
        return self._rejoin_enabled

    def is_rejoin_in_progress(self):
        """Check if an automatic rejoin attempt is currently in progress."""
        return self._rejoin_in_progress

    def register_message_handler(self, message_type: str, func: Callable[[str, Dict[str, Any]], None]) -> None:
        """Register a custom message handler for a specific message type.
        
        This method allows you to define custom handlers for specific message types
        that will be called when messages of that type are received from other peers.
        The handler function will receive the sender's peer ID and the complete message.
        
        Args:
            message_type: The type of message to handle (e.g., 'chat', 'data_sync').
            func: The callback function to invoke when a message of this type is received.
                  The function should accept two parameters:
                  - sender_id (str): The peer ID of the message sender
                  - message (Dict[str, Any]): The complete message dictionary
                  
        Returns:
            None

        Raises:
            ValueError: If the message type is reserved for system messages.
            
        Example:
            def handle_chat(sender_id, message):
                print(f"Chat from {sender_id}: {message['payload']['text']}")
            
            agent.register_message_handler('chat', handle_chat)
        """
        if SystemMessageType.is_system_message(message_type):
            raise ValueError(f"Cannot register handler for system message type: {message_type}")
        self.factory.user_defined_msg_handlers[message_type] = func

    def send(self, peer_id: str, message_type: str, payload: Dict[str, Any]) -> None:
        """Send a message to a specific peer with a message type and payload.
        
        This method sends a targeted message to a specific peer in the network.
        The message will include the specified type and payload, along with routing
        information to ensure it reaches the intended recipient.
        
        Args:
            peer_id: The unique identifier of the peer to send the message to.
                    Must be a valid peer ID of a known peer in the network.
            message_type: The type of the message being sent (e.g., 'chat', 'data_request').
                         This will be used by the recipient to route the message to
                         the appropriate handler.
            payload: The message payload containing the actual data to send.
                    Must be a dictionary with serializable values.
                    
        Returns:
            None
            
        Raises:
            ValueError: If the peer_id is not found in the known peers.
            
        Example:
            agent.send('peer123', 'chat', {'text': 'Hello!', 'timestamp': time.time()})
        """
        message = {
            'message_type': message_type,
            'payload': payload,
            'target_id': peer_id  # Add explicit target
                    }
        self.factory.send_to_peer(peer_id, message)

    def broadcast(self, message_type: str, payload: Dict[str, Any]) -> None:
        """Broadcast a message to all connected peers with a message type and payload.
        
        This method sends a message to all peers in the network.
        The message will be delivered to every peer that has an active connection,
        and each peer will receive the message with the specified type and payload.
        
        Args:
            message_type: The type of the message being broadcast (e.g., 'announcement', 'update').
                         This will be used by recipients to route the message to
                         the appropriate handlers.
            payload: The message payload containing the actual data to broadcast.
                    Must be a dictionary with serializable values that will be
                    sent to all connected peers.
                    
        Returns:
            None
            
        Example:
            agent.broadcast('announcement', {
                'message': 'Server maintenance in 10 minutes',
                'timestamp': time.time()
            })
        """
        message = {
            'message_type': message_type,
            'payload': payload,
            'target_id': '*'  # Explicit broadcast marker
                    }
        self.factory.send_message(message)

    def get_connection_count(self) -> int:
        """Get the current number of active peer connections.
        
        This method returns the total count of currently active connections
        to other peers in the network. This includes both incoming and outgoing
        connections that are established and functioning.
        
        Returns:
            The number of currently active peer connections as an integer.
            Returns 0 if no peers are connected.
            
        Example:
            count = agent.get_connection_count()
            print(f"Currently connected to {count} peers")
        """
        return self.factory.get_connection_count()

    def _start_server(self, factory, ip, port):
        """Start a server to listen for incoming connections."""
        endpoint = TCP4ServerEndpoint(reactor, port, interface=ip)
        endpoint.listen(factory)

        logging.info(f"Peer listening for connections on {ip}:{port}...")

    def on(self, event_name: str, listener: Callable) -> 'SwchAgent':
        """Register an event listener for a specific event type.
        
        This method allows you to register callback functions that will be invoked
        when specific events occur in the P2P network. Events include peer connections,
        disconnections, and other network state changes. The method supports chaining
        for convenient multiple event listener registration.
        
        Args:
            event_name: The name of the event to listen for. Event names include:
                       - 'peer:connected': When a new peer connects us
                       - 'peer:disconnected': When a peer disconnects from us
                       - 'peer:all_disconnected': When all peers disconnect from us (also used for rejoin mechanisn)
                       - 'peer:discovered': When a new peer is discovered in the network
                       - 'peer:undiscovered': When a peer disconnects from the network
                       - 'message': When a message is received from another peer
            listener: The callback function to invoke when the event occurs.
                     The function signature depends on the event type.
                     
        Returns:
            The SwchAgent instance for method chaining.
            
        Example:
            agent.on('peer:connected', lambda peer_id: print(f"Peer {peer_id} connected"))
                 .on('peer:disconnected', lambda peer_id: print(f"Peer {peer_id} disconnected"))
        """
        self.factory.add_event_listener(event_name, listener)
        return self

    def getConnectedPeers(self) -> List[str]:
        """Get a list of peer IDs with live connection to us.
        
        This method examines all known peers and returns a list containing the IDs
        of peers that currently have active transport connections (either local or remote).
        The returned list excludes the peer's own ID.
        
        Returns:
            A list of peer ID strings representing currently connected peers.
            Returns an empty list if no peers are connected.
            
        Example:
            connected = agent.getConnectedPeers()
            for peer_id in connected:
                print(f"Connected to peer: {peer_id}")
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

    def _connect(self, ip: str, port: int) -> defer.Deferred:
        """Connect to a specific peer at the given IP and port with proper error handling."""
        if not ip or not isinstance(port, int) or port <= 0:
            error_msg = f"Invalid connection parameters: ip='{ip}', port={port}"
            self.logger.error(error_msg)
            return defer.fail(ValueError(error_msg))
        
        self.logger.info(f"Attempting to connect to peer at {ip}:{port}")
        
        try:
            endpoint = TCP4ClientEndpoint(reactor, ip, port)
            protocol = P2PNode(self.factory, self.factory.peers, is_initiator=True)
            d = connectProtocol(endpoint, protocol)

            def on_connect_success(protocol_instance):
                self.logger.info(f"Successfully connected to peer at {ip}:{port} as initiator")
                return protocol_instance

            def on_connect_failure(failure):
                error_msg = f"Failed to connect to {ip}:{port}: {failure.getErrorMessage()}"
                self.logger.error(error_msg)
                return failure

            d.addCallback(on_connect_success)
            d.addErrback(on_connect_failure)
            return d
            
        except Exception as e:
            error_msg = f"Exception while attempting connection to {ip}:{port}: {str(e)}"
            self.logger.error(error_msg)
            return defer.fail(e)

    def enter(self, ip: str, port: int) -> defer.Deferred:
        """Join a peer network by connecting to a specific peer address.
        
        This method is typically used to join an existing peer network when you know
        the IP address and port of at least one peer in the network. Once connected,
        the peer discovery mechanism will help you learn about other peers in the network.
        
        Args:
            ip: The IP address of the peer to connect to. Must be a valid IPv4 address
                or hostname that can be resolved.
            port: The port number of the peer to connect to. Must be a valid port number
                  (1-65535) where the target peer is listening for connections.
                  
        Returns:
            A Deferred that fires when the connection attempt completes:
            - On success: fires with the protocol instance
            - On failure: fires with the error that occurred
            
        Example:
            d = agent.enter('192.168.1.100', 8080)
            d.addCallback(lambda protocol: print("Successfully joined network"))
            d.addErrback(lambda failure: print(f"Failed to join: {failure.getErrorMessage()}"))
        """
        return self._connect(ip, port)

    def connect(self, peer_id: str) -> defer.Deferred:
        """Connect to a known peer using their peer ID.
        
        This method establishes a connection to a peer that is already known to the
        local peer registry. It looks up the peer's public connection information
        and attempts to establish a direct connection. The peer must have been
        discovered previously through the network.
        
        Args:
            peer_id: The unique identifier of the peer to connect to. Must be a valid
                    peer ID that exists in the known peers registry and is not the
                    current peer's own ID.
                    
        Returns:
            A Deferred that fires when the connection attempt completes:
            - On success: fires with the protocol instance
            - On failure: fires with a ValueError for invalid parameters or connection errors
            
        Raises:
            ValueError: If peer_id is empty, refers to self, peer not found, already connected,
                       or peer lacks public connection information.
                       
        Example:
            d = agent.connect('peer-uuid-123')
            d.addCallback(lambda protocol: print(f"Connected to peer {peer_id}"))
            d.addErrback(lambda failure: print(f"Connection failed: {failure.getErrorMessage()}"))
        """
        if not peer_id:
            error_msg = "peer_id cannot be empty"
            self.logger.error(error_msg)
            return defer.fail(ValueError(error_msg))
        
        if peer_id == self.factory.id:
            error_msg = "Cannot connect to self"
            self.logger.error(error_msg)
            return defer.fail(ValueError(error_msg))
        
        # Get peer information
        peer_info = self.factory.peers.get_peer_info(peer_id)
        if not peer_info:
            error_msg = f"Peer {peer_id} not found in known peers"
            self.logger.error(error_msg)
            return defer.fail(ValueError(error_msg))
        
        # Check if already connected
        if (peer_info.get('local', {}).get('transport') or 
            peer_info.get('remote', {}).get('transport')):
            error_msg = f"Already connected to peer {peer_id}"
            self.logger.warning(error_msg)
            return defer.fail(ValueError(error_msg))
        
        # Get public connection information
        public_info = peer_info.get('public')
        if not public_info:
            error_msg = f"No public connection information available for peer {peer_id}"
            self.logger.error(error_msg)
            return defer.fail(ValueError(error_msg))
        
        ip = public_info.get('host')
        port = public_info.get('port')
        
        if not ip or not port:
            error_msg = f"Invalid public connection info for peer {peer_id}: host={ip}, port={port}"
            self.logger.error(error_msg)
            return defer.fail(ValueError(error_msg))
        
        self.logger.info(f"Connecting to known peer {peer_id} at {ip}:{port}")
        return self._connect(ip, port)

    def _disconnect(self, peer_id: str, leave: bool= False) -> bool:
        """Disconnects from a specific peer."""
        peer_info = self.factory.peers.get_peer_info(peer_id)
        if not peer_info:
            self.logger.warning(f"Cannot disconnect: peer {peer_id} not found")
            return False

        if not leave and self.factory.get_connection_count() < 2:
            self.logger.warning("Cannot disconnect: this is the last connection")
            return False
        
        if not leave:
            # Notify the peer about the intentional disconnect
            self.factory.send_intentional_disconnect(peer_id)

            # Set intentional disconnect flag
            self.factory.peers.set_is_intentional_disconnect(peer_id, True)

        # Close both local and remote connections if they exist
        for connection_type in ['local', 'remote']:
            if connection_type in peer_info and 'transport' in peer_info[connection_type]:
                transport = peer_info[connection_type]['transport']
                if transport:
                    transport.loseConnection()

        return True

    def disconnect(self, peer_id: str) -> bool:
        """Disconnect from a specific peer.
        
        This method terminates the connection to a specified peer by closing both
        local and remote transport connections if they exist. The disconnection
        will trigger appropriate cleanup and event notifications. Note that if this
        is the last remaining connection, the disconnect may be prevented to avoid
        complete network isolation.
        
        Args:
            peer_id: The unique identifier of the peer to disconnect from. Must be
                    a valid peer ID of a currently connected peer.
                    
        Returns:
            True if the disconnection was initiated successfully, False if the peer
            was not found or disconnection was prevented (e.g., last connection).
            
        Example:
            success = agent.disconnect('peer-uuid-123')
            if success:
                print("Disconnection initiated")
            else:
                print("Could not disconnect from peer")
        """
        self._disconnect(peer_id)

    def leave(self) -> defer.Deferred:
        """Gracefully leave the peer network and shutdown the agent.
        
        This method performs a complete shutdown of the SwchAgent, including:
        1. Disabling the rejoin mechanism to prevent reconnection during shutdown
        2. Notifying all connected peers of the departure
        3. Closing all active connections and waiting for disconnections to complete
        4. Clearing the peer registry and resetting internal state
        
        The method ensures a clean shutdown that properly notifies other peers
        and releases all network resources.
        
        Returns:
            A Deferred that fires when the shutdown process is complete.
            The deferred will fire with None on successful completion.
            
        Example:
            d = agent.leave()
            d.addCallback(lambda _: print("Successfully left the network"))
        """
        self.logger.info("Shutting down SwchAgent...")
        
        # Disable rejoin mechanism during shutdown
        self.disable_rejoin()
        
        # Mark as shutting down to prevent triggering all_disconnected event
        self.factory.set_shutting_down(True)
        
        # Send system remove peer message to all peers
        self.factory.broadcast_remove_peer(self.peer_id)

        # Get list of connected peers before starting disconnections
        connected_peers = self.getConnectedPeers()
        
        if not connected_peers:
            # No connections to close, complete shutdown immediately
            self._complete_shutdown()
            return defer.succeed(None)
        
        # Create a deferred that will fire when all disconnections are complete
        shutdown_deferred = defer.Deferred()
        remaining_disconnections = [len(connected_peers)]  # Use list for mutable reference
        
        def on_disconnection_complete(peer_id):
            remaining_disconnections[0] -= 1
            self.logger.debug(f"Disconnection complete. Remaining: {remaining_disconnections[0]}")
            if remaining_disconnections[0] == 0:
                self._complete_shutdown()
                shutdown_deferred.callback(None)
        
        # Register temporary listener for disconnections during shutdown
        self.factory.add_event_listener('peer:disconnected', on_disconnection_complete)
        
        # Disconnect from all connected peers
        for peer_id in connected_peers:
            self._disconnect(peer_id, leave=True)
        
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

    def start(self):
        """Start the SwarmChestrate P2P system"""
        self.logger.info("Starting SwarmChestrate P2P system...")
        reactor.run()

    def stop(self):
        """Stop the SwarmChestrate P2P system."""
        reactor.stop()
        self.logger.info("Stopping SwarmChestrate P2P system...")

    def findPeers(self, metadata=None):
        """Search for peers based on metadata criteria.
        
        This method searches through all known peers and returns those that match
        the specified metadata criteria. If no metadata is provided, it returns
        all known peers except the current peer. The search performs exact matching
        on all specified metadata fields.
        
        Args:
            metadata (dict, optional): A dictionary of metadata key-value pairs to match.
                                     If None or empty, returns all known peers.
                                     All specified criteria must match for a peer
                                     to be included in the results.
        
        Returns:
            A list of peer ID strings that match the search criteria.
            The current peer's ID is always excluded from results.
            
        Example:
            # Find all peers in the same universe
            universe_peers = agent.findPeers({'universe': 'production'})
            
            # Find all worker type peers
            workers = agent.findPeers({'peer_type': 'worker'})
            
            # Find peers matching multiple criteria
            specific_peers = agent.findPeers({
                'universe': 'test',
                'peer_type': 'coordinator',
                'version': '2.1'
            })
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

    def get_peer_metadata(self, peer_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve metadata for a specific peer by their ID.
        
        This method looks up and returns the metadata dictionary associated with
        a specific peer. Metadata includes attributes that were provided when
        the peer joined the network.
        
        Args:
            peer_id: The unique identifier of the peer whose metadata to retrieve.
                    Must be a valid peer ID of a known peer in the network.
        
        Returns:
            A dictionary containing the peer's metadata if the peer is found,
            or None if the peer ID is not found in the known peers registry.
            
        Example:
            metadata = agent.get_peer_metadata('peer-uuid-123')
            if metadata:
                print(f"Peer type: {metadata.get('peer_type', 'unknown')}")
                print(f"Universe: {metadata.get('universe', 'default')}")
            else:
                print("Peer not found")
        """
        if not self.factory.peers.get_peer_info(peer_id):
            self.logger.warning(f"Peer {peer_id} not found in known peers")
            return None
        return self.factory.peers.get_peer_metadata(peer_id)