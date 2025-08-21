import logging
import argparse
import uuid
from typing import Dict, Any

from twisted.internet.task import LoopingCall

from swchp2pcom import SwchPeer


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

    com = SwchPeer(peer_id, listen_ip, listen_port, 
                    public_ip, public_port,
                    metadata={"peer_type":"RA"})
    
    # If join is provided, connect to the specified peer
    if args.join:
        try:
            join_ip, join_port = args.join.split(':')
            join_port = int(join_port)
        except ValueError:
            logging.error("Invalid format for --join. Expected format is ip:port")
            sys.exit(1)

        com.enter(join_ip,join_port)

    com.start()

