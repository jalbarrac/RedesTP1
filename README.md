Ejecutar

/RedesTP1/src/start-server$ python3 -p 54321 server.py

/RedesTP1/src/upload$ python3 upload.py -H 127.0.0.1 -p 54321 -n nombre_archivo

/RedesTP1/src/download$ python3 download.py -H 127.0.0.1 -p 54321 -n nombre_archivo

---

Ejecución de Mininet

/RedesTP1/src$ python2 topology.py 

> Nota: si ven necesario, agregar sudo

Se abre la consola de mininet, mostrando la información de la topología

Si usan XTERM, se pueden tener dos terminales abiertas en simultaneo para ejecutar en uno el servidor y en el otro el cliente

Comando: xterm h1 h2

Ejemplo 

h1 (cliente): /RedesTP1/src/upload$ python3 upload.py -H 10.0.0.2 -p 54321 -n nombre_archivo

h2 (server):  /RedesTP1/src/start-server$ python3 server.py -p 54321 







