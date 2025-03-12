import socket
import uuid
import json
import time

class SwChClient():
    def __init__(self, myid, myuniverse, mytype):
        self.myid = myid
        self.myuniverse = myuniverse
        self.mytype = mytype
        self.RA = None
        self.message_buffer = ""
        self.message_lines = []

    def connect_to_RA(self, host, port):
        self.host = host
        self.port = port
        try:
            self.sock = socket.create_connection((host, port))
            #print(f"Connected to {host}:{port}.")
        except (socket.error, OSError) as e:
            print(f"Error: {e}")
        
        welcome_message = {
            "message_type": "peer_info",
            "message_id": str(uuid.uuid4()),
            "peer_id": self.myid,
            "peer_universe": self.myuniverse,
            "peer_type": self.mytype
        }
        serialized_message = json.dumps(welcome_message) + "\n"
        data = serialized_message.encode("utf-8")
        try:
            self.sock.sendall(data)
        except (socket.error, OSError) as e:
            print(f"Socket error: {e}")

        message = self.wait_message()
        peer_id = message.get("peer_id")
        peer_universe = message.get("peer_universe")
        peer_type = message.get("peer_type")

        if self.myuniverse != peer_universe:
            print(f"Remote peer\'s universe (\"%s\") does not match! Exiting..." % peer_universe)
            exit(1)
        if peer_type != "ra":
            print("Remote peer is not an RA! Exiting...")
            exit(1)
        print(f"Successfully connected to RA with id \"%s\"." % peer_id)
        self.RA = peer_id
        return

    def send_message(self, message_type, message_body):
        message = {
            "peer_id": self.myid,
            "message_id": str(uuid.uuid4()),

            "message_type": message_type,
            "message_body": message_body 
        }
        serialized_message = json.dumps(message) + "\n"
        data = serialized_message.encode("utf-8")
        try:
            self.sock.sendall(data)
            #print(f"Sent message \"{message}\" to {self.host}:{self.port}.")        
        except (socket.error, OSError) as e:
            print(f"Socket error: {e}")
        return
    
    def recv_message(self):
        return
    
    def wait_message(self):
        try:
            while True:
                if not self.message_lines:
                    data = self.sock.recv(1024)  # Receive up to 1024 bytes
                    if not data:
                        break  # Connection closed by server
                    try:
                        decoded_data = data.decode("utf-8")
                    except UnicodeDecodeError:
                        print("Received non-UTF-8 data.")
                
                    self.message_buffer += decoded_data
                    lines = self.message_buffer.split("\n")
                    self.message_lines += lines
                    self.message_buffer = self.message_lines.pop()  # Save incomplete data
                
                message = self.message_lines.pop(0)
                try:
                    parsed_message = json.loads(message)
                except json.JSONDecodeError as e:
                    print(f"Error decoding message: {e}")                
                return parsed_message
        except (socket.error, OSError) as e:
            print(f"Error: {e}")
    
    def disconnect(self):
        try:
            self.sock.close()
        except (socket.error, OSError) as e:
            print(f"Error: {e}")

    def submit(self):
        print("Submitting application to RA (\"%s\")... " % self.RA)
        appdescr = {
            "param1": "something",
            "param2": "else"
        }
        self.send_message("user_client_submit", appdescr)
        recv_msg = self.wait_message()
        print(f"Message from RA: {recv_msg}")

        
def main():
    host = "127.0.0.1"  # Replace with the server's IP address
    port = 5000         # Replace with the server's port
    myid = "client123"
    myuniverse = "swch"
    mytype = "cl"

    client = SwChClient(myid, myuniverse, mytype)
    client.connect_to_RA(host, port)

    client.submit()

    client.disconnect()
    

if __name__ == "__main__":
    main()
