from typing import List

class Peers:
    def __init__(self):
        """
        Initialize the data structure to hold all peer information.

        The structure is a dictionary where each key is a peer ID,
        and the value is another dictionary containing:
        - "local": A dictionary with local host, port, and transport information.
        - "remote": A dictionary with remote host, port, and transport information.
        - "public": A dictionary with public host and port information.
        This allows for easy access and modification of peer information
        """
        self.peers = {}

    def get_all_public_info(self):
        """
        Return a list of all public information dictionaries from the peers dictionary.
        We return a list to avoid giving direct access to the dictionary's
        live values object, thus preventing accidental modifications.
        """
        public_info = []
        for peer_info in self.peers.values():
            if "public" in peer_info and peer_info["public"]:
                public_info.append(peer_info["public"])
        return public_info

    def get_peer_transports(self):
        """
        Gather and return a list of transport objects from each peer in the peers dictionary.
        Returns a list rather than the live .values() view to prevent accidental modifications.
        """
        transports = []
        for peer_info in self.peers.values():
            for location in ["remote", "local"]:
                if peer_info[location] and "transport" in peer_info[location]:
                    transports.append(peer_info[location]["transport"])
                    break
        return transports

    def get_all_peers_values(self):
        """
        Return a list of all the values of the peers dictionary.
        We return a list to avoid giving direct access to the dictionary's
        live values object, thus preventing accidental modifications.
        """
        return list(self.peers.values())

    def get_all_peers_items(self):
        """
        Return a list of all the items (key-value pairs) of the peers dictionary.
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
        :param transport: The transport object.
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
        :param transport: The transport object.
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
    
    def clear_peers(self) -> None:
        """
        Clear all peer information from the data structure.
        This will remove all entries in the peers dictionary.
        """
        self.peers.clear()

    def get_known_peers_with_public_info(self, exclude_peer_id: str = None) -> List[tuple]:
        """
        Get all known peers that have public information, optionally excluding a specific peer.
        
        :param exclude_peer_id: Optional peer ID to exclude from the results
        :return: List of tuples (peer_id, host, port) for peers with public info
        """
        known_peers = [
            (peer_id, subdict["public"]["host"], subdict["public"]["port"])
            for peer_id, subdict in self.peers.items()
            if subdict["public"] and (exclude_peer_id is None or peer_id != exclude_peer_id)
        ]
        return known_peers

    def __str__(self):
        """
        Optional: String representation of the entire peer structure for debugging.
        """
        return str(self.peers)
