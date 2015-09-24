from setproctitle import setproctitle

import twisted
from twisted.python import usage
from twisted.logger import Logger
from twisted.application import service

from proxy import WebSocketListenerService, WAMPClientService

"""
class ProxyService(MultiService):

   def startService(self):

      # First, connect to router
      self.wamp_service = WAMPClientService(self.router, self.debug)
      self.wamp_service.setName("WAMP client service")
      self.wamp_service.setServiceParent(self)

      # Then set up the service
      self.ws_service = WebSocketListenerService(self.server, self.debug)
      self.ws_service.setName("WebSocket listener service")
      self.ws_service.setServiceParent(self)


      # Need reference
      TODO self.factory.wampfactory = wamp_session_factory


      MultiService.startService(self)

   def stopService(self):
      ""
      self.ws_service.stopService()
      self.wamp_service.stopService()
"""

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
   proxy = service.MultiService()
   server, router, debug = options["server"], options["router"], options["debug"]

   listener = WebSocketListenerService(server, debug=debug)
   listener.setServiceParent(proxy)

   client = WAMPClientService(router, debug=debug)
   client.setServiceParent(proxy)

   setproctitle("ws-wamp proxy [twisted service]")

   return proxy
