from twisted.internet import reactor, protocol, endpoints
import uuid
import json

class SwChClient(protocol.Protocol):
    def connectionMade(self):
        print("Connected to server")
        self.send_welcome_message()

    def send_message(self, message):
        serialized_message = json.dumps(message) + "\n"
        data = serialized_message.encode("utf-8")
        self.transport.write(data) # Send the message

    def send_welcome_message(self):
        message = {
            "type": "peer_info",
            "message_id": str(uuid.uuid4()),
            "peer_id": "valami",
            "peer_universe": "swch",
            "peer_type": "cl"
        }
        self.send_message(message)

    def dataReceived(self, data):
        print("Received:", data.decode())

    def connectionLost(self, reason):
        print("Connection lost:", reason)
        reactor.stop() # Stop the reactor if connection is lost

class SwChClientFactory(protocol.ClientFactory):
    protocol = SwChClient

def main():
    # Replace with the actual server address and port
    server_address = "127.0.0.1"  # Example: localhost
    server_port = 5000  # Example port

    # Create the endpoint
    endpoint = endpoints.TCP4ClientEndpoint(reactor, server_address, server_port)

    # Connect to the server
    d = endpoint.connect(SwChClientFactory())
    d.addErrback(lambda err: print("Connection error:", err)) # Handle connection errors

    reactor.run()

if __name__ == "__main__":
    main()
