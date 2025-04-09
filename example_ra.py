import logging
import argparse

from swch_com.swch_com import SWCH_com


if __name__ == "__main__":
    import sys

    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Set up argument parser
    parser = argparse.ArgumentParser(description="P2P Node")
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

    
    com = SWCH_com(None,"swch", "ra", listen_ip, listen_port, public_ip, public_port, 1)
        
    # If join is provided, connect to the specified peer
    if args.join:
        try:
            join_ip, join_port = args.join.split(':')
            join_port = int(join_port)
        except ValueError:
            logging.error("Invalid format for --join. Expected format is ip:port")
            sys.exit(1)

        com.connect_to_peer(join_ip,join_port)

    def client_submit(clientid, message):
        import uuid
        logging.info(f"Client submit arrived: peer: {clientid}, message: {message}")
        message = {
            "message_type": "ack_client_submit",
            "message_id": str(uuid.uuid4())
        }
        com.send_message(clientid, message)
        return

    #com.register_message_handler(message_id, func)
    com.register_message_handler("user_client_submit", client_submit)


    com.run()
