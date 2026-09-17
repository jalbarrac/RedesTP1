from socket import *
server_port = 54321
server_socket = socket(AF_INET, SOCK_DGRAM)
server_socket.bind(('', server_port))
print("Listening...")
while True:
	message, client_address = server_socket.recvfrom(2048)
	modifiedMessage = message.decode().upper()
	server_socket.sendto(modifiedMessage.encode(), client_address)


