import logging
import argparse
import uuid
from typing import Dict, Any

from twisted.internet.task import LoopingCall

from swch_com.swchagent import SwchAgent


if __name__ == "__main__":
    import sys

    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Set up argument parser
    parser = argparse.ArgumentParser(description="SwCh Resource Agent")
    parser.add_argument(
        "--listen",
        required=True,
        help="IP and port to listen on, in the format ip:port"
    )
    parser.add_argument(
        "--public",
        required=True,
        help="IP and port accessable remotely, in the format ip:port"
    )
    parser.add_argument(
        "--join",
        help="IP and port of peer to connect to, in the format ip:port"
    )
    parser.add_argument(
        "--id",
        help="Custom id to give to this peer, if not provided a random UUID will be generated"
    )
    args = parser.parse_args()

    # Parse listen argument
    try:
        listen_ip, listen_port = args.listen.split(':')
        listen_port = int(listen_port)
    except ValueError:
        logging.error("Invalid format for --listen. Expected format is ip:port")
        sys.exit(1)

    # Parse public argument
    public_ip, public_port = None, None
    if args.public:
        try:
            public_ip, public_port = args.public.split(':')
            public_port = int(public_port)
        except ValueError:
            logging.error("Invalid format for --public. Expected format is ip:port")
            sys.exit(1)

    peer_id = None
    if args.id:
        peer_id = args.id
    else:
        peer_id = str(uuid.uuid4())

    
    com = SwchAgent(peer_id,"swch", "ra", listen_ip, listen_port, public_ip, public_port, 1)
        
    # If join is provided, connect to the specified peer
    if args.join:
        try:
            join_ip, join_port = args.join.split(':')
            join_port = int(join_port)
        except ValueError:
            logging.error("Invalid format for --join. Expected format is ip:port")
            sys.exit(1)

        com.connect(join_ip,join_port)

    """
    def handle_ping(sender_id, message):
        message_id = str(uuid.uuid4())
        logging.info(f"Received ping from {sender_id}")
        message=  {
            "message_type": "pong",
            "message_id": message_id,
            "peer_id": peer_id,
            "message_body": f"Pong from {peer_id}"
        }
        com.send_message(sender_id, message)
    
    def handle_pong(sender_id, message):
        logging.info(f"Received pong from {sender_id}")

    com.register_message_handler("pong", handle_pong)
    com.register_message_handler("ping", handle_ping)
    
    def send_ping():
        message_id = str(uuid.uuid4())
        message = {
            "message_type": "ping",
            "message_id": message_id,
            "peer_id": peer_id,
            "message_body": f"Ping from {peer_id}"
        }
        com.send_message(None,message)

    heartbeat_task = LoopingCall(send_ping)
    heartbeat_task.start(2)
    """
    com.run()

    """
    def client_submit(clientid, message):
        import uuid
        logging.info(f"Client submit arrived: peer: {clientid}, message: {message}")
        message = {
            "message_type": "ack_client_submit",
            "message_id": str(uuid.uuid4())
        }
        com.send_message(clientid, message)
        return
    com.register_message_handler("user_client_submit", client_submit)
    """
