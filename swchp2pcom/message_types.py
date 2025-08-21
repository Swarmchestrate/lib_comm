"""
Message type constants and enums for the SwchPeer P2P communication library.

This module defines standardized message types used for system-level communication
between peers in the network, ensuring consistency and reducing the risk of typos
in message type strings throughout the codebase.
"""

from enum import Enum, unique


@unique
class SystemMessageType(Enum):
    """
    Enumeration of system-level message types used for P2P network management.
    
    These message types are reserved for internal network operations such as
    peer discovery, connection management, and network state synchronization.
    User-defined message types should not use these reserved values.
    """
    
    # System message types
    SEND_WELCOME_INFO = "system_send_welcome_info"
    BROADCAST_PEER_LIST_UPDATE = "system_broadcast_peer_list_update"
    BROADCAST_REMOVE_PEER = "system_broadcast_remove_peer"
    SEND_INTENTIONAL_DISCONNECT = "system_send_intentional_disconnect"
    
    def __str__(self):
        """Return the string value of the message type."""
        return self.value
    
    @classmethod
    def is_system_message(cls, message_type: str) -> bool:
        """
        Check if a message type is a reserved system message.
        
        Args:
            message_type: The message type string to check
            
        Returns:
            True if the message type is a system message, False otherwise
        """
        return message_type in [msg_type.value for msg_type in cls]
    
    @classmethod
    def get_all_system_types(cls) -> list[str]:
        """
        Get a list of all system message type strings.
        
        Returns:
            List of all system message type values
        """
        return [msg_type.value for msg_type in cls]

def is_system_message(message_type: str) -> bool:
    """
    Convenience function to check if a message type is a system message.
    
    Args:
        message_type: The message type string to check
        
    Returns:
        True if the message type is a system message, False otherwise
    """
    return SystemMessageType.is_system_message(message_type)
