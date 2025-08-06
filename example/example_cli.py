from swch_com.swchagent import SwchAgent

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
        required=True,
        help="IP and port of RA to connect to, in the format ip:port"
    )
    parser.add_argument(
        "--submit",
        required=False,
        help="Specify an appid to submit"
    )
    parser.add_argument(
        "--getstate",
        required=False,
        help="Specify an appid to get the state"
    )
    args = parser.parse_args()
    
    peer_id = "client123"
    com = SwchAgent(peer_id,
                    enable_rejoin=False,
                    metadata={"peer_type":"CL"})

    if args.join:
        try:
            RAhost, RAport = args.join.split(':')
            RAport = int(RAport)
        except ValueError:
            logging.error("Invalid format for --join. Expected format is ip:port")
            sys.exit(1)

        com.enter(RAhost, RAport)

    submit_target_RA_id="wmin.ac.uk"
    submit_happened=False
    getstate_happened=False

    def on_peer_discovered(peer_id):
        if args.submit:
            global submit_target_RA_id, submit_happened
            if submit_happened or peer_id != submit_target_RA_id:
                return
            logging.info(f"Submitting application: {args.submit}")
            com.send(peer_id, "MSG_SUBMIT", {"appid": args.submit})
            submit_happened = True
            com.leave().addCallback(lambda _: com.stop())

        if args.getstate:
            global getstate_happened
            if getstate_happened:
                return
            sa_id=com.findPeers({"appid":args.getstate, "peer_type":"SA"})
            if not sa_id:
                return
            sa_id = sa_id[0]  # Assuming there is only one SA with the specified appid
            logging.info(f"Getting state for application: {args.getstate}")
            msg_getstate = {"appid": args.getstate}
            com.send(sa_id, "MSG_GETSTATE", msg_getstate)
            getstate_happened = True
            
    def on_state(peer_id, message):
        logging.info(f"Receiving state: {message['appid']}:\"{message['state']}\"")
        com.leave().addCallback(lambda _: com.stop())

    com.register_message_handler("MSG_STATE",on_state)
    com.on('peer:discovered', on_peer_discovered)

    com.start()

