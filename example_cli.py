from swch_com.swch_com import SwChClient

import logging
import argparse
import sys

if __name__ == "__main__":
     # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Set up argument parser
    parser = argparse.ArgumentParser(description="SwCh client")
    parser.add_argument(
        "--join",
        help="IP and port of RA to connect to, in the format ip:port"
    )
    args = parser.parse_args()

    if args.join:
        try:
            RAhost, RAport = args.join.split(':')
            RAport = int(RAport)
        except ValueError:
            logging.error("Invalid format for --join. Expected format is ip:port")
            sys.exit(1)

    myid = "client123"
    myuniverse = "swch"
  
    client = SwChClient(myid, myuniverse)
    client.connect_to_RA(RAhost, RAport)

    appdescr = {
        "param1": "something",
        "param2": "else"
    }
    print("Submitting application to RA (\"%s\")... " % client.connectedRA['id'])
    client.send_message("user_client_submit", appdescr)
    recv_msg = client.wait_message()
    print(f"Message from RA: {recv_msg}")

    client.disconnect_from_RA()

