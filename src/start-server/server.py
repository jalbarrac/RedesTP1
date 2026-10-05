import argparse
import os
import queue
import socket
import threading
import time
from datetime import datetime
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


WINDOW_SIZE = 64
TIMEOUT_SEC = 0.35
MAX_PAYLOAD = 1019
MAX_TIMEOUTS = 20
MAX_SACK_BLOCKS = 32

parser = argparse.ArgumentParser(
    prog="start-server",
    description="Start storage server.")
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
    default="0.0.0.0",
    help="service IP address")
parser.add_argument(
    "-p", "--port",
    default=54321,
    type=int,
    help="service port")
parser.add_argument(
    "-s", "--storage",
    default="./storage",
    help="storage dir path")

args = parser.parse_args()
storage_dir = args.storage
os.makedirs(storage_dir, exist_ok=True)

server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_socket.bind((args.host, args.port))

if not args.quiet:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] "
          f"Servidor escuchando en {args.host}:{args.port}")

sesiones_activas = {}
lock_sesiones = threading.Lock()


def srv_enviar_sack(file_obj, client_address, cola):
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
                + seq.to_bytes(4, 'big') + chunks[seq])
    while base < total_chunks:
        while next_seqnum < base + WINDOW_SIZE and next_seqnum < total_chunks:
            if next_seqnum not in acks_recibidos:
                server_socket.sendto(armar_pkt(next_seqnum), client_address)
            next_seqnum += 1

        if timer_start is None and base < next_seqnum:
            timer_start = time.time()
        hubo_ack = False
        while True:
            try:
                ack_pkt = cola.get_nowait()
            except queue.Empty:
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
                    server_socket.sendto(armar_pkt(seq), client_address)
            timer_start = time.time()
    done_pkt = bytes([MessageCodes.DATA_DONE])
    for _ in range(15):
        server_socket.sendto(done_pkt, client_address)
        try:
            res = cola.get(timeout=0.3)
            if res and res[0] == MessageCodes.DATA_DONE:
                return True
        except queue.Empty:
            continue
    return False


def srv_recibir_sack(file_obj, client_address, cola):
    received_chunks = {}
    cum_ack = 0
    timeouts = 0
    while True:
        try:
            pkt = cola.get(timeout=1.5)
        except queue.Empty:
            timeouts += 1
            if timeouts >= MAX_TIMEOUTS:
                return False
            continue
        timeouts = 0
        codigo = pkt[0]
        if codigo == MessageCodes.DATA_DONE:
            for _ in range(3):
                server_socket.sendto(
                    bytes([MessageCodes.DATA_DONE]),
                    client_address)
            break
        if codigo == MessageCodes.DATA_SEND:
            if len(pkt) < 5:
                continue
            seqnum = int.from_bytes(pkt[1:5], 'big')
            data = pkt[5:]
            if seqnum not in received_chunks:
                received_chunks[seqnum] = data

            while cum_ack in received_chunks:
                cum_ack += 1
            out_of_order = [
                s for s in range(cum_ack + 1, cum_ack + WINDOW_SIZE + 1)
                if s in received_chunks]
            blocks = []
            if out_of_order:
                start = out_of_order[0]
                prev = start
                for s in out_of_order[1:]:
                    if s == prev + 1:
                        prev = s
                    else:
                        blocks.append((start, prev + 1))
                        start = s
                        prev = s
                blocks.append((start, prev + 1))

            num_blocks = min(len(blocks), MAX_SACK_BLOCKS)
            ack_buf = bytearray([MessageCodes.DATA_ACK])
            ack_buf.extend(cum_ack.to_bytes(4, 'big'))
            ack_buf.append(num_blocks)

            for left, right in blocks[:num_blocks]:
                ack_buf.extend(left.to_bytes(4, 'big'))
                ack_buf.extend(right.to_bytes(4, 'big'))

            server_socket.sendto(bytes(ack_buf), client_address)

    for seq in sorted(received_chunks.keys()):
        file_obj.write(received_chunks[seq])
    return True


def atender_upload(mensaje_solicitud, client_address, cola):
    try:
        proto_code = mensaje_solicitud[1]
        file_size = int.from_bytes(mensaje_solicitud[2:6], 'big')
        filename = mensaje_solicitud[6:].decode(errors='replace')
        if not filename:
            server_socket.sendto(
                (bytes([MessageCodes.REJECT_REQUEST])
                 + b"Nombre invalido"), client_address)
            return
        if file_size > 1073741824:
            server_socket.sendto(
                (bytes([MessageCodes.REJECT_REQUEST])
                 + b"Archivo demasiado grande"), client_address)
            return
        for _ in range(3):
            server_socket.sendto(
                bytes([MessageCodes.ACCEPT_REQUEST]),
                client_address)
        filepath = os.path.join(storage_dir, filename)

        with open(filepath, 'wb') as f:
            if proto_code == ProtocolCodes.SACK:
                srv_recibir_sack(f, client_address, cola)
            else:
                seq_esperado = 0
                while True:
                    try:
                        pkt = cola.get(timeout=10.0)
                    except queue.Empty:
                        return
                    if pkt[0] == MessageCodes.DATA_SEND:
                        seq = int.from_bytes(pkt[1:5], 'big')
                        if seq == seq_esperado:
                            f.write(pkt[5:])
                            seq_esperado += 1
                        server_socket.sendto(
                            (bytes([MessageCodes.DATA_ACK])
                             + seq.to_bytes(4, 'big')), client_address)
                    elif pkt[0] == MessageCodes.DATA_DONE:
                        for _ in range(3):
                            server_socket.sendto(
                                bytes([MessageCodes.DATA_DONE]),
                                client_address)
                        break
        if not args.quiet:
            print(f"[{datetime.now().strftime('%H:%M:%S')}][UPLOAD OK] "
                  f"{filename} desde {client_address}")
    finally:
        with lock_sesiones:
            if sesiones_activas.get(client_address) is cola:
                del sesiones_activas[client_address]


def atender_download(mensaje_solicitud, client_address, cola):
    try:
        proto_code = mensaje_solicitud[1]
        filename = mensaje_solicitud[2:].decode(errors='replace')
        filepath = os.path.join(storage_dir, filename)

        if not os.path.isfile(filepath):
            server_socket.sendto(
                (bytes([MessageCodes.REJECT_REQUEST])
                 + b"Archivo no encontrado"), client_address)
            return

        for _ in range(3):
            server_socket.sendto(bytes([MessageCodes.ACCEPT_REQUEST]),
                                 client_address)

        with open(filepath, 'rb') as f:
            if proto_code == ProtocolCodes.SACK:
                srv_enviar_sack(f, client_address, cola)
            else:
                seqnum = 0
                data = f.read(MAX_PAYLOAD)
                while data:
                    pkt = (bytes([MessageCodes.DATA_SEND])
                           + seqnum.to_bytes(4, 'big') + data)
                    confirmado = False
                    for _ in range(15):
                        server_socket.sendto(pkt, client_address)
                        try:
                            res = cola.get(timeout=1.0)
                            ack_seq = int.from_bytes(res[1:5], 'big')
                            if (res[0] == MessageCodes.DATA_ACK
                                    and ack_seq == seqnum):
                                confirmado = True
                                break
                        except queue.Empty:
                            continue
                    if not confirmado:
                        return
                    data = f.read(MAX_PAYLOAD)
                    seqnum += 1

                for _ in range(5):
                    server_socket.sendto(
                        bytes([MessageCodes.DATA_DONE]),
                        client_address)
                    try:
                        res = cola.get(timeout=0.3)
                        if res[0] == MessageCodes.DATA_DONE:
                            break
                    except queue.Empty:
                        pass
        if not args.quiet:
            print(f"[{datetime.now().strftime('%H:%M:%S')}][DOWNLOAD OK] "
                  f"{filename} hacia {client_address}")
    finally:
        with lock_sesiones:
            if sesiones_activas.get(client_address) is cola:
                del sesiones_activas[client_address]


while True:
    try:
        mensaje, client_address = server_socket.recvfrom(1024)
        if not mensaje:
            continue
        codigo = mensaje[0]

        if codigo == MessageCodes.REQUEST_UPLOAD:
            cola = queue.Queue()
            with lock_sesiones:
                sesiones_activas[client_address] = cola
            threading.Thread(target=atender_upload,
                             args=(mensaje, client_address, cola),
                             daemon=True).start()

        elif codigo == MessageCodes.REQUEST_DOWNLOAD:
            cola = queue.Queue()
            with lock_sesiones:
                sesiones_activas[client_address] = cola
            threading.Thread(target=atender_download,
                             args=(mensaje, client_address, cola),
                             daemon=True).start()

        else:
            with lock_sesiones:
                cola = sesiones_activas.get(client_address)
            if cola is not None:
                cola.put(mensaje)
    except KeyboardInterrupt:
        break

server_socket.close()
