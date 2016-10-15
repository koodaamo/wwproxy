from setproctitle import setproctitle

import twisted
from twisted.python import usage
from twisted.logger import Logger
from twisted.application import service

from proxy import WebSocketListenerService


class Options(usage.Options):

   srv_connstr = "ws://127.0.0.1:9000/ws"
   rtr_connstr = "ws://127.0.0.1:8080/ws"

   optFlags = [['debug', 'd', 'Emit debug messages']]
   explanation = " WebSocket connection string (default %s)"
   optParameters = [
      ["server", "s", srv_connstr, "Server" + explanation % srv_connstr],
      ["router", "r", rtr_connstr, "Router" + explanation % rtr_connstr],
   ]


def makeService(options):
   "create and return an application service for the twistd plugin system"

   server, router, debug = options["server"], options["router"], options["debug"]
   listener = WebSocketListenerService(server, router, debug=debug)

   setproctitle("ws-wamp proxy [twisted service]")

   return listener
