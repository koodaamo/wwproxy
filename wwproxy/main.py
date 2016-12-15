from setproctitle import setproctitle
from twisted.python import usage
from proxy import WebSocketListenerService


class Options(usage.Options):

   srv_connstr = "ws://127.0.0.1:9000/ws"
   rtr_connstr = "ws://127.0.0.1:8080/ws"

   key = "key.pem"
   cert = "cert.pem"

   optFlags = [['debug', 'd', 'Emit debug messages']]
   explanation = " WebSocket connection string"
   optParameters = [
      ["server", "s", srv_connstr, "Server" + explanation],
      ["router", "r", rtr_connstr, "Router" + explanation],
      ["client_key", "k", key, "Client key"],
      ["client_certificate", "c", cert, "Client certificate"],
   ]


def makeService(options):
   "create and return an application service for the twistd plugin system"

   server_cs, router_cs, debug = options["server"], options["router"], options["debug"]

   # If TLS is used, we switch on client certificates if present
   if router_cs.startswith("wss:"):
      key, crt = options["client_key"], options["client_certificate"]
   else:
      key = crt = None
   listener = WebSocketListenerService(server_cs, router_cs, key, crt, debug=debug)

   setproctitle("ws-wamp proxy [twisted service]")

   return listener
