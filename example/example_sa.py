from swch_com.swchagent import SwchAgent

import logging
import argparse
import sys

if __name__ == "__main__":
     # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Set up argument parser
    parser = argparse.ArgumentParser(description="SwCh SA")
    parser.add_argument(
        "--listen",
        required=True,
        help="IP and port to listen on, in the format ip:port"
    )
    parser.add_argument(
        "--join",
        required=True,
        help="IP and port of RA to connect to, in the format ip:port"
    )
    parser.add_argument(
        "--appid",
        required=False,
        help="Specify an appid to register"
    )
    args = parser.parse_args()
    
    # Parse listen argument
    try:
        listen_ip, listen_port = args.listen.split(':')
        listen_port = int(listen_port)
    except ValueError:
        logging.error("Invalid format for --listen. Expected format is ip:port")
        sys.exit(1)

    peer_id = "SA123"
    com = SwchAgent(peer_id,
                    listen_ip, listen_port,
                    metadata={"peer_type":"SA","appid":args.appid})

    if args.join:
        try:
            RAhost, RAport = args.join.split(':')
            RAport = int(RAport)
        except ValueError:
            logging.error("Invalid format for --join. Expected format is ip:port")
            sys.exit(1)

        com.enter(RAhost, RAport)

    def on_getstate(peer_id, message):
        logging.info(f"Sending state for application: {message['appid']}")
        com.send(peer_id, "MSG_STATE", {"appid": message['appid'], "state": "running"})

    com.register_message_handler("MSG_GETSTATE",on_getstate)

    com.start()
