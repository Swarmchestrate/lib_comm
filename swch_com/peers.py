class Peers:
    def __init__(self):
        """
        Initialize the data structure to hold all peer information.
        """
        self.peers = {}

    def get_all_peers_values(self):
        """
        Return a list of all the values of the all_peers dictionary.
        We return a list to avoid giving direct access to the dictionary's
        live values object, thus preventing accidental modifications.
        """
        return list(self.peers.values())

    def get_all_peers_items(self):
        """
        Return a list of all the items (key-value pairs) of the all_peers dictionary.
        We return a list to avoid giving direct access to the dictionary's
        live items view, thus preventing accidental modifications.
        """
        return list(self.peers.items())

    def add_peer(self, peer_id: str) -> None:
        """
        Add a new peer to the data structure if it doesn't exist already.

        :param peer_id: A unique identifier for the peer (e.g., a string or UUID).
        """
        if peer_id not in self.peers:
            self.peers[peer_id] = {
                "local": {},
                "remote": {},
                "public": {}
            }

    def set_local_info(self, peer_id: str, host: str, port: str, transport) -> None:
        """
        Set the local information for a given peer.

        :param peer_id: Identifier for the peer.
        :param host: The local host address (string).
        :param port: The local port (string).
        :param transport: The transport mechanism (e.g., "tcp", "udp", etc.).
        """
        # Ensure the peer exists
        self.add_peer(peer_id)
        self.peers[peer_id]["local"] = {
            "host": host,
            "port": port,
            "transport": transport
        }

    def set_remote_info(self, peer_id: str, host: str, port: str, transport) -> None:
        """
        Set the remote information for a given peer.

        :param peer_id: Identifier for the peer.
        :param host: The remote host address.
        :param port: The remote port.
        :param transport: The transport mechanism.
        """
        self.add_peer(peer_id)
        self.peers[peer_id]["remote"] = {
            "host": host,
            "port": port,
            "transport": transport
        }

    def set_public_info(self, peer_id: str, host: str, port: str) -> None:
        """
        Set the public information for a given peer.

        :param peer_id: Identifier for the peer.
        :param host: The public host address.
        :param port: The public port.
        """
        self.add_peer(peer_id)
        self.peers[peer_id]["public"] = {
            "host": host,
            "port": port
        }

    def get_peer_info(self, peer_id: str) -> dict:
        """
        Retrieve the dictionary for a specific peer.

        :param peer_id: The ID of the peer.
        :return: The peer's dictionary if present, otherwise an empty dictionary.
        """
        return self.peers.get(peer_id, {})

    def remove_peer_info(self, peer_id: str, info_type: str = None) -> bool:
        """
        Remove peer information from the data structure.

        :param peer_id: The ID of the peer to remove or modify.
        :param info_type: The type of peer information to remove.
                         If None, remove the entire peer entry.
                         Otherwise, remove the specified sub-section
                         (e.g., "local", "remote", "public").
        :return: True if removal was successful, False otherwise.
        """
        if peer_id not in self.peers:
            return False  # Peer doesn't exist

        if info_type is None:
            # Remove the entire peer
            del self.peers[peer_id]
            return True
        else:
            # Remove only the specified sub-section if it exists
            if info_type in self.peers[peer_id]:
                self.peers[peer_id][info_type] = {}
                return True
            else:
                return False

    def __str__(self):
        """
        Optional: String representation of the entire peer structure for debugging.
        """
        return str(self.peers)
