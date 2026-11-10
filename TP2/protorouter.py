# Import some POX stuff
from pox.core import core                       # Main POX object
import pox.openflow.libopenflow_01 as of        # OpenFlow 1.0 library
from pox.lib.addresses import EthAddr, IPAddr   # Address types
from pox.lib.packet.ethernet import ethernet
from pox.lib.packet.arp import arp
import time


log = core.getLogger()
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"


def log_color(color, msg):
    log.info(f"{color}{msg}{RESET}")


PRIVATE_SUBNET = IPAddr("192.168.1.0")      # Red interna
PRIVATE_MASK = 24                           # Máscara de la red interna
PRIVATE_IP = IPAddr("192.168.1.254")        # IP del router en la red privada
PUBLIC_IP = IPAddr("200.0.0.254")           # IP del router en la red pública
PUBLIC_MAC = EthAddr("00:00:00:aa:aa:aa")   # MAC del router hacia la red pública
PRIVATE_MAC = EthAddr("00:00:00:bb:bb:bb")  # MAC del router hacia la red privada
PUBLIC_PORT = 1                             # Puerto del switch conectado a la red pública
ARP_TTL = 90                                # Tiempo de vigencia de las entradas de la tabla ARP en segundos

class ProtoRouter(object):
    def __init__(self, connection):
        self.connection = connection
        connection.addListeners(self)
        self.arp_table = {}
        self.packet_queues = {}

    def _handle_PacketIn(self, event):
        if not event.parsed.parsed:
            log.warning("[DROP] PacketIn con trama no reconocida. POX no pudo decodificar el paquete.")
            return

        if event.parsed.type == ethernet.IP_TYPE:
            self.handle_ip(event)
        elif event.parsed.type == ethernet.ARP_TYPE:
            self.handle_arp(event)
        else:
            log_color(YELLOW, f"Paquete ignorado: protocolo no reconocido.")

    def handle_ip(self, event):
        packet = event.parsed
        ip_pkt = packet.payload
        in_port = event.port

        log_color(
            YELLOW, f"[IP] RECIBIDO: {ip_pkt.srcip} → {ip_pkt.dstip} | "
            f"MAC: {packet.src} → {packet.dst} | In Port: {in_port}")

        if ip_pkt.srcip.inNetwork(PRIVATE_SUBNET, PRIVATE_MASK):
            #para conexiones que aun no tienen flujo, admito solo salientes desde red privada.
            log_color(GREEN, f"[IP] MATCH: {ip_pkt.srcip} pertenece a la red privada {PRIVATE_SUBNET}/{PRIVATE_MASK}")

            #busco ip destino en tabla ARP
            arp_entry = self.arp_table.get(ip_pkt.dstip)

            expired = False
            if arp_entry is not None:
                expired = ((time.time() - arp_entry[2]) > ARP_TTL)

            if expired:
                self.arp_table.pop(ip_pkt.dstip)

            if arp_entry is None or expired:
                if self.packet_queues.get(ip_pkt.dstip) is None:# si no esta vacia, quiere decir que en un paso anterior ya mande un request y estoy esperando el reply
                    self.arp_request_addr(ip_pkt.dstip)
                    self.packet_queues[ip_pkt.dstip] = []

                self.packet_queues[ip_pkt.dstip].append(event)
                return

            #Si llegue hasta aca es porque pude resolver la MAC
            dst_mac, out_port, arp_ttl = arp_entry


            # Instalar Flujo Saliente
            fm = of.ofp_flow_mod()
            fm.idle_timeout = 10
            fm.hard_timeout = ARP_TTL

            # Filtro (Saliente)
            fm.match.nw_src = ip_pkt.srcip
            fm.match.dl_type = 0x800  # IPv4
            fm.match.in_port = in_port

            # Acción (Saliente)
            fm.actions.append(of.ofp_action_dl_addr.set_src(PUBLIC_MAC))
            fm.actions.append(of.ofp_action_dl_addr.set_dst(dst_mac))
            fm.actions.append(of.ofp_action_output(port=out_port))
            self.connection.send(fm)

            # Instalar Flujo Entrante (para respuesta)
            fm_back = of.ofp_flow_mod()
            fm_back.idle_timeout = 10
            fm_back.hard_timeout = ARP_TTL

            # Filtro (Entrante)
            fm_back.match.nw_src = ip_pkt.dstip
            fm_back.match.nw_dst = ip_pkt.srcip
            fm_back.match.dl_type = 0x800  # IPv4
            fm_back.match.in_port = out_port

            # Acción (Entrante)
            fm_back.actions.append(of.ofp_action_dl_addr.set_src(PRIVATE_MAC))
            fm_back.actions.append(of.ofp_action_dl_addr.set_dst(packet.src))
            fm_back.actions.append(of.ofp_action_output(port=in_port))
            self.connection.send(fm_back)

            # Reenviar paquete actual con MACs actualizadas (Los posteriores pasan por flujo)
            packet.src = PUBLIC_MAC
            packet.dst = dst_mac
            msg = of.ofp_packet_out()
            msg.data = packet.pack()
            msg.actions.append(of.ofp_action_output(port=out_port))
            log_color(CYAN, f"[IP] ENVIANDO: {ip_pkt.srcip} → {ip_pkt.dstip} | MAC: {PUBLIC_MAC} → {dst_mac} | Out Port: {out_port}")
            self.connection.send(msg)

        else:
            log_color(RED, f"[IP] NO MATCH: {ip_pkt.srcip} no pertenece a {PRIVATE_SUBNET}/{PRIVATE_MASK}")

    def handle_arp(self, event):
        packet = event.parsed
        arp_pkt = packet.payload

        log_color(
            YELLOW, f"[ARP] RECIBIDO: {arp_pkt.protosrc} → {arp_pkt.protodst} | "
            f"MAC: {arp_pkt.hwsrc} → {arp_pkt.hwdst} | In Port: {event.port}")

        self.arp_table[arp_pkt.protosrc] = (arp_pkt.hwsrc, event.port, time.time())

        queue = self.packet_queues.pop(arp_pkt.protosrc, None)

        if queue is not None:
            for e in queue:
                self.handle_ip(e)

        if arp_pkt.opcode == arp.REQUEST:
            arp_reply = arp()
            arp_reply.opcode = arp.REPLY
            
            if arp_pkt.protodst == PRIVATE_IP and event.port != PUBLIC_PORT:
                arp_reply.hwsrc = PRIVATE_MAC
            elif arp_pkt.protodst == PUBLIC_IP and event.port == PUBLIC_PORT:
                arp_reply.hwsrc = PUBLIC_MAC
            else:
                log_color(RED, f"[ARP] NO MATCH | IP Destino: {arp_pkt.protodst} | Puerto: {event.port}")
                return

            arp_reply.hwdst = arp_pkt.hwsrc
            arp_reply.protosrc = arp_pkt.protodst
            arp_reply.protodst = arp_pkt.protosrc
            ether = ethernet()
            ether.type = ethernet.ARP_TYPE
            ether.dst = arp_reply.hwdst
            ether.src = arp_reply.hwsrc
            ether.payload = arp_reply

            msg = of.ofp_packet_out()
            msg.data = ether.pack()
            msg.actions.append(of.ofp_action_output(port=event.port))
            self.connection.send(msg)
            log_color(CYAN, f"[ARP] ENVIANDO REPLY: {arp_reply.protosrc} → {arp_reply.protodst} | MAC: {arp_reply.hwsrc} → {arp_reply.hwdst} | Puerto: {event.port}")
        
        self.display_arp_table()

    def arp_request_addr(self, ip):

        out_ports = []
        if ip.inNetwork(PRIVATE_SUBNET, PRIVATE_MASK):
            req_hwsrc = PRIVATE_MAC
            req_protosrc = PRIVATE_IP

            for p in self.connection.ports.keys():
                if p not in [PUBLIC_PORT, of.OFPP_LOCAL]:
                    out_ports.append(p)

        else:
            req_hwsrc = PUBLIC_MAC
            req_protosrc = PUBLIC_IP
            out_ports.append(PUBLIC_PORT)

        #armo solicitud ARP
        arp_request = arp()
        arp_request.opcode = arp.REQUEST
        arp_request.hwsrc = req_hwsrc
        arp_request.protosrc = req_protosrc
        arp_request.hwdst = EthAddr("00:00:00:00:00:00")
        arp_request.protodst = ip

        ether = ethernet()
        ether.type = ethernet.ARP_TYPE
        ether.dst = EthAddr("ff:ff:ff:ff:ff:ff")
        ether.src = req_hwsrc
        ether.payload = arp_request

        msg = of.ofp_packet_out()
        msg.data = ether.pack()
        for p in out_ports:
            msg.actions.append(of.ofp_action_output(port=p))
        log_color(CYAN, f"[ARP] ENVIANDO REQUEST (quien es {ip})?")
        self.connection.send(msg)

    def display_arp_table(self):
        entries = self.arp_table.items()
        log_color(YELLOW, f"       IP      |       MAC       |Puerto|    Estado    ")
        log_color(YELLOW, f"---------------|-----------------|------|----------------------------")
        for (k, v) in entries:
            true_ttl = ARP_TTL - (time.time() - v[2])
            status = f"Vence en {true_ttl:.0f} s" if true_ttl > 0 else "Vencida"
            log_color(YELLOW, f"{str(k):<15}|{str(v[0]):<17}|{v[1]:<6}|{status}")
        log_color(YELLOW, f"                                                                     ")

def launch():

    def start_switch(event):
        log_color(YELLOW, f"Iniciando ProtoRouter para Switch {event.connection.dpid}")
        ProtoRouter(event.connection)

    core.openflow.addListenerByName("ConnectionUp", start_switch)