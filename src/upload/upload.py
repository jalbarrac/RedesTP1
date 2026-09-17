import argparse
from socket import *

parser = argparse.ArgumentParser(prog="upload", description="Upload a file.")
group = parser.add_mutually_exclusive_group()
group.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
group.add_argument("-q", "--quiet", help="decrease output verbosity", action="store_true")
parser.add_argument("-H", "--host", help="server IP address")
parser.add_argument("-p", "--port", help="server port", type=int)
parser.add_argument("-s", "--src", help="source file path")
parser.add_argument("-n", "--name", help="file name")
parser.add_argument("-r", "--protocol", help="error recovery protocol")

args = parser.parse_args()


server_name = args.host
server_port = args.port
client_socket = socket(AF_INET, SOCK_DGRAM)
message = input('Input lowercase sentence: ')
client_socket.sendto(message.encode(), (server_name, server_port))
modifiedMessage, server_address = client_socket.recvfrom(2048)
print(modifiedMessage.decode())
client_socket.close()
