"""
Topologia de mininet para probar el TP de Redes.

Uso:
    sudo python3 topo.py --delay 20ms --loss 10

Crea dos hosts (h1 = cliente, h2 = servidor) conectados por un link con
el delay y la perdida indicados. El delay se aplica en cada extremo del
link, asi que el RTT total termina siendo aproximadamente el doble del
valor pasado (--delay 20ms -> RTT ~40ms).
"""

import argparse

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel


class RedesTopo(Topo):
    def build(self, delay="20ms", loss=10):
        h1 = self.addHost('h1')  # cliente (upload/download)
        h2 = self.addHost('h2')  # servidor
        self.addLink(h1, h2, cls=TCLink, delay=delay, loss=loss)


def parsear_argumentos():
    parser = argparse.ArgumentParser(description="Topologia de prueba para el TP de Redes")
    parser.add_argument("--delay", default="20ms", help="delay aplicado en cada extremo del link (ej: 20ms)")
    parser.add_argument("--loss", type=float, default=10, help="porcentaje de perdida en el link (ej: 10)")
    return parser.parse_args()


if __name__ == '__main__':
    setLogLevel('info')
    args = parsear_argumentos()

    print(f"Levantando topologia: delay={args.delay} por extremo, loss={args.loss}%")
    topo = RedesTopo(delay=args.delay, loss=args.loss)
    # controller=None: no se agrega ningun controlador OpenFlow. Ante la
    # ausencia de controlador, el switch de Open vSwitch cae solo a modo
    # "standalone" (actua como un switch comun de capa 2), que es
    # exactamente el "Falling back to OVS Bridge" que se ve al correr
    # "sudo mn --test pingall". No requiere ningun binario externo.
    net = Mininet(topo=topo, link=TCLink, controller=None)
    net.start()

    h1, h2 = net.get('h1', 'h2')
    print(f"h1 (cliente) IP: {h1.IP()}")
    print(f"h2 (servidor) IP: {h2.IP()}")

    CLI(net)
    net.stop()