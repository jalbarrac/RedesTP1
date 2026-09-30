from mininet.net import Mininet
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.link import TCLink


def main():
    net = Mininet()
    host1 = net.addHost("h1")
    host2 = net.addHost("h2")

    # con failMode=secure no se esta realizando el forwarding del paquete y se termina perdiendo
    switch = net.addSwitch("s1", failMode="standalone") 

    # se crean los enlaces y se agrega delay de 10ms incluyendo 5% de perdida en uno de los enlaces
    net.addLink(host1, switch, cls=TCLink, delay="10ms", loss=5)
    net.addLink(host2, switch, cls=TCLink, delay="10ms")

    net.start()
    CLI(net)
    net.stop()

if __name__ == "__main__":
    setLogLevel("info")
    main()