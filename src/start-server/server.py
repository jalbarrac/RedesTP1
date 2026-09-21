from socket import *
from enum import IntEnum

class MessageCodes(IntEnum):
	REQUEST_UPLOAD = 1
	ACCEPT_UPLOAD = 2
	REJECT_UPLOAD = 3
	DATA_SEND = 4
	DATA_ACK = 5
	REQUEST_DOWNLOAD = 6
	REJECT_DOWNLOAD = 7
	DATA_DONE = 8

def filename_ok(string):
	return True

def filesize_ok(size):
	return size < 1073741824

server_port = 54321
server_socket = socket(AF_INET, SOCK_DGRAM)
server_socket.bind(('', server_port))
print("Listening...")

while True:
	message, client_address = server_socket.recvfrom(1024)

	match message[0]:
		case MessageCodes.REQUEST_UPLOAD:
			if not filename_ok(message[6:].decode()):
				response = bytes([MessageCodes.REJECT_UPLOAD]) + "Error - Filename not ok.".encode()
			elif not filesize_ok(int.from_bytes(message[2:6], 'big')):
				response = bytes([MessageCodes.REJECT_UPLOAD]) + "Error - File too big.".encode()
			else:
				response = bytes([MessageCodes.ACCEPT_UPLOAD])
		case _:
			response = bytes([MessageCodes.REJECT_UPLOAD]) + "Error - Bad request.".encode()

	server_socket.sendto(response, client_address)

	#TO DO: variar segun el protocolo
	f = open(message[6:].decode(), 'ba')

	while True:
		message, client_address = server_socket.recvfrom(1024)
		if message[0] == MessageCodes.DATA_SEND:
			f.write(message[5:])
			response = bytes([MessageCodes.DATA_ACK]) + message[1:5]
			server_socket.sendto(response, client_address)
		elif message[0] == MessageCodes.DATA_DONE:
			break

	f.close()


