from socket import *
import argparse
from enum import IntEnum

class MessageCodes(IntEnum):
	REQUEST_UPLOAD = 1
	ACCEPT_REQUEST = 2
	REJECT_REQUEST = 3
	DATA_SEND = 4
	DATA_ACK = 5
	REQUEST_DOWNLOAD = 6
	DATA_DONE = 7

def filename_ok(string):
	return True

def filesize_ok(size):
	return size < 1073741824


parser = argparse.ArgumentParser(prog="start-server", description="Upload a file.")
group = parser.add_mutually_exclusive_group()
group.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
group.add_argument("-q", "--quiet", help="decrease output verbosity", action="store_true")
parser.add_argument("-H", "--host", help="service IP address")
parser.add_argument("-p", "--port", help="service port", type=int)
parser.add_argument("-s", "--storage", help="storage dir path")

args = parser.parse_args()

#cfg
if not args.host:
	args.host = ''

if not args.port:
	args.port = 54321

service = 0
server_socket = socket(AF_INET, SOCK_DGRAM)
server_socket.bind((args.host, args.port))
print("Listening...")

while True:
	message, client_address = server_socket.recvfrom(1024)

	match message[0]:
		case MessageCodes.REQUEST_UPLOAD:
			if not filename_ok(message[6:].decode()):
				response = bytes([MessageCodes.REJECT_REQUEST]) + "Error - Filename not ok.".encode()
			elif not filesize_ok(int.from_bytes(message[2:6], 'big')):
				response = bytes([MessageCodes.REJECT_REQUEST]) + "Error - File too big.".encode()
			else:
				service = MessageCodes.REQUEST_UPLOAD
				response = bytes([MessageCodes.ACCEPT_REQUEST])

		case MessageCodes.REQUEST_DOWNLOAD:
			if not filename_ok(message[6:].decode()):
				response = bytes([MessageCodes.REJECT_REQUEST]) + "Error - Filename not ok.".encode()
			else:
				service = MessageCodes.REQUEST_DOWNLOAD
				response = bytes([MessageCodes.ACCEPT_REQUEST])
		case _:
			response = bytes([MessageCodes.REJECT_REQUEST]) + "Error - Bad request.".encode()

	server_socket.sendto(response, client_address)


	if service == MessageCodes.REQUEST_UPLOAD:

		filename = message[6:].decode()
		#TO DO: variar segun el protocolo
		f = open(filename, 'ba')

		#loop recibir archivo

		while True:
			message, client_address = server_socket.recvfrom(1024)
			if message[0] == MessageCodes.DATA_SEND:
				f.write(message[5:])
				response = bytes([MessageCodes.DATA_ACK]) + message[1:5]
				server_socket.sendto(response, client_address)
			elif message[0] == MessageCodes.DATA_DONE:
				print("Success. Received file: " + filename)
				break
		f.close()

	elif service == MessageCodes.REQUEST_DOWNLOAD:

		#TO DO: variar segun el protocolo
		f = open(message[2:].decode(), 'br')

		#loop enviar archivo
		data = f.read(1019)
		seqnum = 0
		while data:
			response = bytes([MessageCodes.DATA_SEND]) + seqnum.to_bytes(4,'big') + data
			server_socket.sendto(response, client_address)
			server_socket.settimeout(1)
			try:
				message, client_address = server_socket.recvfrom(1024)
			except socket.timeout:
				continue
			#si recibo ACK, avanzo
			if message[0] == MessageCodes.DATA_ACK and int.from_bytes(message[1:], 'big') == seqnum:
				data = f.read(1019)
				seqnum = seqnum + 1

		#print("Mande todos los datos")
		response = bytes([MessageCodes.DATA_DONE])
		server_socket.sendto(response, client_address)
		f.close()

	service = 0
	server_socket.settimeout(None)
server_socket.close()
