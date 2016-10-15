import sys, json
from urlparse import urlparse
import pkg_resources
from twisted.application import service
from twisted.logger import Logger, globalLogPublisher, textFileLogObserver
from twisted.internet import reactor, defer
from twisted.internet.defer import inlineCallbacks
from twisted.internet.endpoints import clientFromString
from autobahn.twisted.wamp import ApplicationSession
from autobahn.twisted.websocket import WebSocketServerProtocol, \
                                       WebSocketServerFactory, \
                                       WampWebSocketClientFactory
from autobahn.wamp.exception import ApplicationError

#globalLogPublisher.addObserver(textFileLogObserver(sys.stdout))

PUBSUB = "pubsub"
RPC = "rpc"
MSGSEP = ':'

#
# PROTOCOL
#

class WSServer(WebSocketServerProtocol):

   logger = Logger()

   # bookkeeping for WAMP clients, keyed by realm
   wamp_clients = {}

   def onConnect(self, request):
      self.logger.info("client connecting: {0}".format(request.peer))

   def onOpen(self):
      self.logger.info("WebSocket connection open.")


   def parseWSMessageFormat(self, message):
      try:
         parts = message.decode("UTF-8").split(MSGSEP)
      except:
         return None
      else:
         # return (realm, rpc/pubsub, opid, args+kwargs)
         argskwargs = message[(len(parts[0]) + len(parts[1]) + len(parts[2]) + 3):]
         return (parts[0], parts[1], parts[2], argskwargs)


   @inlineCallbacks
   def proxy_message(self, client, kind, opid, argdata):
      "deliver the received message, converted to WAMP"

      if kind == RPC and opid in client._registrations:
         try:
            # args+kwargs is a (optional) JSON structure
            if argdata:
               params = json.loads(argdata)
               args = params.get("args") or []
               kwargs = params.get("kwargs") or {}
            else:
               args, kwargs = [], {}
         except:
            self.sendMessage("FAIL could not parse args/kwargs".encode("utf-8"), False)
            return
         else:
            try:
               response = yield client.call(opid, *args, **kwargs)
            except ApplicationError as exc:
               self.logger.warn("WAMP request failed: %s" % str(exc))
               self.sendMessage("FAIL wamp request failed".encode("utf-8"), False)
               return
            else:
               self.sendMessage(json.dumps(response), False)
               return
      elif kind == PUBSUB and opid in client._subscriptions:
         self.sendMessage("FAIL pubsub not yet supported".encode("utf-8"), False)
      else:
         self.sendMessage("FAIL unknown semantics; use 'rpc' or 'pubsub'".encode("utf-8"), False)


   def get_wamp_client(self, realm):

      if realm in self.wamp_clients:
         self.logger.debug("using existing client for realm '%s'" % realm)
         return defer.succeed(self.wamp_clients[realm])
      else:
         self.logger.debug("requesting new client for realm '%s'" % realm)
         d = defer.Deferred()

         def factory():
            client = WAMPClient()
            client._realm = realm
            client._on_join = d
            self.wamp_clients[realm] = client
            return client

         wamp_transport_factory = WampWebSocketClientFactory(factory, self.service.r_uri)
         addr, port = self.service.r_address, self.service.r_port
         client = clientFromString(reactor, "tcp:%s:%i" % (addr, port))
         client.connect(wamp_transport_factory)
         return d


   @inlineCallbacks
   def onMessage(self, message, isBinary):

      if isBinary:
         raise Exception("cannot handle binary messages")
      self.logger.debug("received msg: {0}".format(message.decode('utf8')))

      parsed = self.parseWSMessageFormat(message)

      if not parsed:
         self.sendMessage("FAIL could not parse message at all".encode("utf-8"), False)
         return

      realm, kind, opid, argdata = parsed

      self.get_wamp_client(realm).addCallback(self.proxy_message, kind, opid, argdata)
      yield


   def onClose(self, wasClean, code, reason):
      self.logger.info("WebSocket connection closed: {0}".format(reason))


class WAMPClient(ApplicationSession):

   logger = Logger()

   @inlineCallbacks
   def lookupSubscriptions(self):
      subsdata = yield self.call("wamp.subscription.list")
      sids = [id for id in subsdata["exact"]]
      self._subscriptions = []
      for sid in sids:
         subscription = yield self.call("wamp.subscription.get", sid)
         self._subscriptions.append(subscription["uri"])
         self.logger.info("discovered PubSub subscription: " + str(subscription))

   @inlineCallbacks
   def lookupProcedures(self):
      regsdata = yield self.call("wamp.registration.list")
      rids = [id for id in regsdata["exact"]]
      self._registrations = []
      for rid in rids:
         registration = yield self.call("wamp.registration.get", rid)
         self._registrations.append(registration["uri"])
         self.logger.info("discovered RPC registration: " + registration["uri"])

   @inlineCallbacks
   def onConnect(self):
      self.logger.info("proxy WAMP client connected to router")
      yield self.join(self._realm)


   def onJoin(self, details):
      self.logger.info("proxy WAMP client joined realm")

      def release(_):
         self._on_join.callback(self)

      defs = [self.lookupProcedures(), self.lookupSubscriptions()]
      defer.DeferredList(defs).addCallback(release)


   def onLeave(self, details):
      pass


#
# SERVICE DEFINITION
#

class WebSocketListenerService(service.Service):

   name = "WebSocketListenerService"

   logger = Logger()

   def __init__(self, server_uri, router_uri, debug=False):
      self.s_uri = server_uri
      self.s_address = urlparse(server_uri).hostname
      self.s_port = urlparse(server_uri).port

      self.r_uri = router_uri
      self.r_address = urlparse(router_uri).hostname
      self.r_port = urlparse(router_uri).port

      self.debug = debug

      self.s_factory = WebSocketServerFactory(server_uri)
      proto = WSServer
      proto.service = self
      self.s_factory.protocol = proto
      self.s_factory.setProtocolOptions(maxConnections=10)

   def startService(self):
      self.s_listener = reactor.listenTCP(self.s_port, self.s_factory, interface=self.s_address)
      self.logger.info("service started")

   def stopService(self):
      self.s_listener.stopListening()
      self.s_factory.stopFactory()
      self.logger.info("service stopped")

