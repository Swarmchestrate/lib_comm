import socket
import uuid
import json

class SwChClient():
    def __init__(self, myid: str, myuniverse: str):
        self.myid = myid
        self.myuniverse = myuniverse
        self.mytype = "CL"
        self.RAid = None
        self.message_buffer = ""
        self.message_lines = []

    def connect_to_RA(self, host: str, port: int) -> None:
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
        self.RAid = peer_id
        return peer_id

    def send_message(self, message_type: str, message_body: dict) -> None:
        message = {
            "peer_id": self.RAid,
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
    
    def recv_message(self) -> None:
        return
    
    def wait_message(self) -> dict:
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
    
    def disconnect(self) -> None:
        try:
            self.sock.close()
        except (socket.error, OSError) as e:
            print(f"Error: {e}")