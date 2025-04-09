from swch_com.client import SwChClient

def main() -> None:
    RAhost = "127.0.0.1"  # Replace with the server's IP address
    RAport = 5000         # Replace with the server's port
    myid = "client123"
    myuniverse = "swch"
  
    client = SwChClient(myid, myuniverse)
    client.connect_to_RA(RAhost, RAport)

    appdescr = {
        "param1": "something",
        "param2": "else"
    }
    print("Submitting application to RA (\"%s\")... " % client.RAid)
    client.send_message("user_client_submit", appdescr)
    recv_msg = client.wait_message()
    print(f"Message from RA: {recv_msg}")

    client.disconnect()

if __name__ == "__main__":
    main()
