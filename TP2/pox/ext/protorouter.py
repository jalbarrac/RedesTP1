# Import some POX stuff
from pox.core import core                       # Main POX object
import pox.openflow.libopenflow_01 as of        # OpenFlow 1.0 library
from pox.lib.addresses import EthAddr, IPAddr   # Address types
from pox.lib.packet.ethernet import ethernet
from pox.lib.packet.udp import udp
from pox.lib.packet.tcp import tcp

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

H1_MAC = EthAddr("00:00:00:00:00:01")   

NAT_PORT_MIN = 10000  
NAT_PORT_MAX = 65535
NAT_PORT_TIMEOUT = 30 


class NatEntry(object):
    """Una conexión traducida (una fila de la tabla del Cuadro 1)."""
    def __init__(self, proto, ip_priv, port_priv, ip_dst, port_dst,
                 port_pub, mac_priv, sw_port):
        self.proto = proto            
        self.ip_priv = ip_priv        
        self.port_priv = port_priv    
        self.ip_dst = ip_dst           
        self.port_dst = port_dst      
        self.port_pub = port_pub     
        self.mac_priv = mac_priv      
        self.sw_port = sw_port      

    def key_out(self):
        """Clave para buscar esta conexión cuando el paquete va hacia afuera."""
        return (self.proto, self.ip_priv, self.port_priv, self.ip_dst, self.port_dst)

    def key_in(self):
        """Clave para buscar esta conexión cuando vuelve la respuesta."""
        return (self.proto, self.port_pub)


class NatTable(object):
    def __init__(self, port_min=NAT_PORT_MIN, port_max=NAT_PORT_MAX):
        self.port_min = port_min
        self.port_max = port_max
        self.next_port_to_try = port_min  
        self.outgoing = {}   
        self.incoming = {}

    def get_out(self, proto, ip_priv, port_priv, ip_dst, port_dst):
        """Busca la traducción de un paquete saliente. None si todavía no existe."""
        return self.outgoing.get((proto, ip_priv, port_priv, ip_dst, port_dst))

    def get_in(self, proto, port_pub):
        """Busca la traducción de un paquete entrante. None si no existe."""
        return self.incoming.get((proto, port_pub))

    def _alloc_port(self, proto):
        """Devuelve un puerto público libre para ese protocolo, o None si no queda ninguno."""
        pool_size = self.port_max - self.port_min + 1
        for _ in range(pool_size):               
            candidate_port = self.next_port_to_try

            if candidate_port >= self.port_max:
                self.next_port_to_try = self.port_min
            else:
                self.next_port_to_try = candidate_port + 1

            port_is_free = (proto, candidate_port) not in self.incoming
            if port_is_free:
                return candidate_port
        return None

    def create(self, proto, ip_priv, port_priv, ip_dst, port_dst, mac_priv, sw_port):
        """Crea una traducción nueva, devuelve la NatEntry, o None si no hay puertos libres"""
        public_port = self._alloc_port(proto)
        if public_port is None:
            return None
        entry = NatEntry(proto, ip_priv, port_priv, ip_dst, port_dst,
                         public_port, mac_priv, sw_port)
        self.outgoing[entry.key_out()] = entry
        self.incoming[entry.key_in()] = entry
        return entry

    def release(self, entry):
        """Borra la traducción y deja el puerto público disponible para reutilizarlo"""
        self.outgoing.pop(entry.key_out(), None)
        self.incoming.pop(entry.key_in(), None)


class ProtoRouter(object):
    def __init__(self, connection):
        self.connection = connection
        self.nat = NatTable()
        connection.addListeners(self)

    def _handle_PacketIn(self, event):
        if not event.parsed.parsed:
            log.warning("[DROP] PacketIn con trama no reconocida. POX no pudo decodificar el paquete.")
            return

        if event.parsed.type == ethernet.IP_TYPE:
            self.handle_ip(event)
        else:
            log_color(YELLOW, f"Paquete ignorado: protocolo distinto de IPv4.")

    def handle_ip(self, event):
        packet = event.parsed
        ip_pkt = packet.payload
        in_port = event.port

        log_color(
            YELLOW, f"RECIBIDO: {ip_pkt.srcip} → {ip_pkt.dstip} | "
            f"MAC: {packet.src} → {packet.dst} | In Port: {in_port}")

        if ip_pkt.srcip.inNetwork(PRIVATE_SUBNET, PRIVATE_MASK):

            log_color(GREEN, f"MATCH: {ip_pkt.srcip} pertenece a la red privada {PRIVATE_SUBNET}/{PRIVATE_MASK}")
            transport = ip_pkt.payload
            if not isinstance(transport, (tcp, udp)):
                log_color(YELLOW, "PAT: solo se traduce TCP/UDP, descarto")
                return
            entry = self.nat.get_out(ip_pkt.protocol, ip_pkt.srcip, transport.srcport,
                                     ip_pkt.dstip, transport.dstport)
            if entry is None:
                entry = self.nat.create(ip_pkt.protocol, ip_pkt.srcip, transport.srcport,
                                        ip_pkt.dstip, transport.dstport,
                                        packet.src, in_port)
                if entry is None:
                    log_color(RED, "PAT: no quedan puertos públicos libres, descarto")
                    return
                log_color(GREEN, f"PAT NUEVO: {entry.ip_priv}:{entry.port_priv} ↔ {PUBLIC_IP}:{entry.port_pub}")
            else:
                log_color(CYAN, f"PAT REUSO: {entry.ip_priv}:{entry.port_priv} ↔ {PUBLIC_IP}:{entry.port_pub}")

            fm = of.ofp_flow_mod()
            fm.idle_timeout = 10

            fm.match.nw_src = ip_pkt.srcip
            fm.match.nw_dst = ip_pkt.dstip
            fm.match.nw_proto = ip_pkt.protocol
            fm.match.tp_src = transport.srcport
            fm.match.tp_dst = transport.dstport
            fm.match.dl_type = 0x800  # IPv4
            fm.match.in_port = in_port

            fm.actions.append(of.ofp_action_dl_addr.set_src(PUBLIC_MAC))
            fm.actions.append(of.ofp_action_dl_addr.set_dst(H1_MAC))
            fm.actions.append(of.ofp_action_nw_addr.set_src(PUBLIC_IP))
            fm.actions.append(of.ofp_action_tp_port.set_src(entry.port_pub))
            fm.actions.append(of.ofp_action_output(port=PUBLIC_PORT))
            self.connection.send(fm)

            fm_back = of.ofp_flow_mod()
            fm_back.idle_timeout = 10

            fm_back.match.nw_src = ip_pkt.dstip
            fm_back.match.nw_dst = PUBLIC_IP
            fm_back.match.nw_proto = ip_pkt.protocol
            fm_back.match.tp_src = transport.dstport
            fm_back.match.tp_dst = entry.port_pub
            fm_back.match.dl_type = 0x800  # IPv4
            fm_back.match.in_port = PUBLIC_PORT

            fm_back.actions.append(of.ofp_action_dl_addr.set_src(PRIVATE_MAC))
            fm_back.actions.append(of.ofp_action_dl_addr.set_dst(entry.mac_priv))
            fm_back.actions.append(of.ofp_action_nw_addr.set_dst(entry.ip_priv))
            fm_back.actions.append(of.ofp_action_tp_port.set_dst(entry.port_priv))
            fm_back.actions.append(of.ofp_action_output(port=in_port))
            self.connection.send(fm_back)
            msg = of.ofp_packet_out(data=event.ofp, in_port=in_port)
            msg.actions = fm.actions
            log_color(CYAN, f"ENVIANDO: {PUBLIC_IP}:{entry.port_pub} → {ip_pkt.dstip}:{transport.dstport} | Out Port: {PUBLIC_PORT}")
            self.connection.send(msg)
        else:
            log_color(RED, f"NO MATCH: {ip_pkt.srcip} no pertenece a {PRIVATE_SUBNET}/{PRIVATE_MASK}")


def launch():

    def start_switch(event):
        log_color(YELLOW, f"Iniciando ProtoRouter para Switch {event.connection.dpid}")
        ProtoRouter(event.connection)

    core.openflow.addListenerByName("ConnectionUp", start_switch)