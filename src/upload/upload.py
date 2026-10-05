import argparse
import os
import socket
import sys
import time
from enum import IntEnum


class MessageCodes(IntEnum):
    REQUEST_UPLOAD = 1
    ACCEPT_REQUEST = 2
    REJECT_REQUEST = 3
    DATA_SEND = 4
    DATA_ACK = 5
    REQUEST_DOWNLOAD = 6
    DATA_DONE = 7


class ProtocolCodes(IntEnum):
    STOP_AND_WAIT = 1
    SACK = 2


# Parámetros para SACK y Stop & Wait
WINDOW_SIZE = 64
TIMEOUT_SEC = 0.35
MAX_PAYLOAD = 1019
MAX_TIMEOUTS = 20
MAX_SACK_BLOCKS = 32


parser = argparse.ArgumentParser(
    prog="upload",
    description="Upload a file.")
group = parser.add_mutually_exclusive_group()
group.add_argument(
    "-v", "--verbose",
    help="increase output verbosity",
    action="store_true")
group.add_argument(
    "-q", "--quiet",
    help="decrease output verbosity",
    action="store_true")
parser.add_argument(
    "-H", "--host",
    required=True,
    help="server IP address")
parser.add_argument(
    "-p", "--port",
    type=int,
    default=54321,
    help="server port")
parser.add_argument(
    "-s", "--src",
    default="./",
    help="source file path")
parser.add_argument(
    "-n", "--name",
    required=True,
    help="file name")
parser.add_argument(
    "-r", "--protocol",
    default="saw",
    help="error recovery protocol (saw o sack)")

args = parser.parse_args()

file_path = os.path.join(args.src, args.name)
if not os.path.isfile(file_path):
    sys.exit(f"Error: No existe el archivo '{file_path}'.")

client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
dest_addr = (args.host, args.port)
file_size = os.path.getsize(file_path)
file_size_bytes = file_size.to_bytes(4, 'big')


def enviar_y_esperar(mensaje, codigos_validos, max_intentos=15, timeout=1.0):
    for _ in range(max_intentos):
        client_socket.sendto(mensaje, dest_addr)
        client_socket.settimeout(timeout)
        try:
            respuesta, _ = client_socket.recvfrom(1024)
            if respuesta and respuesta[0] in codigos_validos:
                return respuesta
        except socket.timeout:
            continue
    return None


def enviar_sack(file_obj):
    chunks = []
    while True:
        chunk = file_obj.read(MAX_PAYLOAD)
        if not chunk:
            break
        chunks.append(chunk)
    total_chunks = len(chunks)
    base = 0
    next_seqnum = 0
    acks_recibidos = set()
    timer_start = None
    timeouts_seguidos = 0

    def armar_pkt(seq):
        return (bytes([MessageCodes.DATA_SEND])
                + seq.to_bytes(4, 'big')
                + chunks[seq])

    def recibir_ack():
        try:
            client_socket.settimeout(0.005)
            data, _ = client_socket.recvfrom(1024)
            return data
        except (socket.timeout, ConnectionResetError):
            return None

    while base < total_chunks:
        while next_seqnum < base + WINDOW_SIZE and next_seqnum < total_chunks:
            if next_seqnum not in acks_recibidos:
                client_socket.sendto(armar_pkt(next_seqnum), dest_addr)
            next_seqnum += 1
        if timer_start is None and base < next_seqnum:
            timer_start = time.time()

        hubo_ack = False
        while True:
            ack_pkt = recibir_ack()
            if ack_pkt is None:
                break
            if len(ack_pkt) < 6 or ack_pkt[0] != MessageCodes.DATA_ACK:
                continue
            cum_ack = int.from_bytes(ack_pkt[1:5], 'big')
            num_blocks = ack_pkt[5]
            for i in range(base, min(cum_ack, total_chunks)):
                acks_recibidos.add(i)
            offset = 6
            for _ in range(num_blocks):
                if offset + 8 > len(ack_pkt):
                    break
                left = int.from_bytes(ack_pkt[offset:offset + 4], 'big')
                right = int.from_bytes(ack_pkt[offset + 4:offset + 8], 'big')
                for seq in range(left, min(right, total_chunks)):
                    acks_recibidos.add(seq)
                offset += 8
            hubo_ack = True

        base_anterior = base
        while base in acks_recibidos:
            base += 1
        if base != base_anterior:
            timeouts_seguidos = 0
            timer_start = time.time() if base < next_seqnum else None
        elif hubo_ack and timer_start is not None:
            timer_start = time.time()
        if (timer_start is not None
                and (time.time() - timer_start > TIMEOUT_SEC)):
            timeouts_seguidos += 1
            if timeouts_seguidos >= MAX_TIMEOUTS:
                return False
            for seq in range(base, min(base + WINDOW_SIZE, total_chunks)):
                if seq not in acks_recibidos:
                    client_socket.sendto(armar_pkt(seq), dest_addr)
            timer_start = time.time()

    done_pkt = bytes([MessageCodes.DATA_DONE])
    for _ in range(15):
        client_socket.sendto(done_pkt, dest_addr)
        deadline = time.time() + 0.3
        while time.time() < deadline:
            restante = max(0.01, deadline - time.time())
            try:
                client_socket.settimeout(restante)
                res, _ = client_socket.recvfrom(1024)
                if res and res[0] == MessageCodes.DATA_DONE:
                    return True
            except (socket.timeout, ConnectionResetError):
                break
    return False


def enviar_stop_and_wait(file_obj):
    seqnum = 0
    data = file_obj.read(MAX_PAYLOAD)
    while data:
        pkt = (bytes([MessageCodes.DATA_SEND])
               + seqnum.to_bytes(4, 'big') + data)
        ack = None
        for _ in range(15):
            client_socket.sendto(pkt, dest_addr)
            client_socket.settimeout(1.0)
            try:
                res, _ = client_socket.recvfrom(1024)
                ack_seq = int.from_bytes(res[1:5], 'big')
                if res:
                    if res[0] == MessageCodes.DATA_ACK and ack_seq == seqnum:
                        ack = res
                        break
            except socket.timeout:
                continue
        if ack is None:
            return False
        data = file_obj.read(MAX_PAYLOAD)
        seqnum += 1
    done = bytes([MessageCodes.DATA_DONE])
    enviar_y_esperar(done, (MessageCodes.DATA_DONE,))
    return True


# Handshake
proto_code = (ProtocolCodes.SACK if args.protocol.lower() == 'sack'
              else ProtocolCodes.STOP_AND_WAIT)
req = (bytes([MessageCodes.REQUEST_UPLOAD, proto_code])
       + file_size_bytes + args.name.encode())
resp = enviar_y_esperar(req,
                        (MessageCodes.ACCEPT_REQUEST,
                         MessageCodes.REJECT_REQUEST))

if resp is None:
    sys.exit("Error: El servidor no respondió a la solicitud.")
if resp[0] == MessageCodes.REJECT_REQUEST:
    sys.exit(f"Rechazado por el servidor: {resp[1:].decode(errors='replace')}")

with open(file_path, 'rb') as f:
    if proto_code == ProtocolCodes.SACK:
        ok = enviar_sack(f)
    else:
        ok = enviar_stop_and_wait(f)
if not args.quiet:
    if ok:
        print("OK: Transferencia de subida finalizada con éxito.")
    else:
        print("Error: Falló la transferencia.")
client_socket.close()
