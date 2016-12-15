import os
import json
from urlparse import urlparse
from twisted.application import service
from twisted.logger import Logger
from twisted.internet import reactor, defer, ssl
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet.defer import inlineCallbacks
from twisted.internet.endpoints import clientFromString
from autobahn.twisted import websocket
from autobahn.twisted.wamp import ApplicationSession
from autobahn.twisted.websocket import WebSocketServerProtocol, \
                                       WebSocketServerFactory, \
                                       WampWebSocketClientFactory
from autobahn.wamp.exception import ApplicationError


#
# SSL/TLS context factory for client certificate auth
#

class ClientContextFactory(ssl.ClientContextFactory):

   def __init__(self, key_path, crt_path):
      if not (os.path.isfile(key_path) and os.path.isfile(crt_path)):
         raise Exception("key or certificate file not found, cannot proceed!")
      self.key_path = key_path
      self.crt_path = crt_path

   def getContext(self):
      #self.method = SSL.SSLv23_METHOD
      ctx = ssl.ClientContextFactory.getContext(self)
      ctx.use_privatekey_file(self.key_path)
      ctx.use_certificate_file(self.crt_path)
      return ctx


#
# Reconnecting transport factory
#

class WAMPClientFactory(WampWebSocketClientFactory, ReconnectingClientFactory):

   logger = Logger()

   maxDelay = 3

   def clientConnectionFailed(self, connector, reason):
      self.logger.warn("connection failed: %s" % reason)
      ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)

   def clientConnectionLost(self, connector, reason):
      self.logger.warn("connection lost: %s" % reason)
      ReconnectingClientFactory.clientConnectionLost(self, connector, reason)


#
# PROTOCOL
#

class WSServer(WebSocketServerProtocol):

   logger = Logger()

   # bookkeeping for WAMP clients, keyed by realm
   wamp_clients = {}

   def onConnect(self, request):
      self.logger.debug("client connecting: {0}".format(request.peer))

   def onOpen(self):
      self.logger.debug("WebSocket connection open.")


   def sendJSONMessage(self, status, response):
      "convenience for responding back to 'plain' websocket client"
      self.sendMessage(json.dumps((status, response)), False)

   @inlineCallbacks
   def proxy_message(self, client, realm=None, method=None, event=None, args=None, kwargs=None):
      "deliver the received message, converted to WAMP"

      if method: # RPC

         try:
            # make the outgoing WAMP call
            response = yield client.call(method, *args, **kwargs)
         except ApplicationError as exc:
            self.logger.error("WAMP request failed: %s" % exc.error_message())
            self.sendJSONMessage(501, "wamp request failed")
            return
         else:
            self.logger.debug(type(response))
            self.logger.debug(str(response))
            self.sendJSONMessage(200, response)
            return

      elif event: # PUBSUB
         if event not in client._subscriptions:
            self.sendJSONMessage(400, u"event '%s' not subscribed by anyone" % event)
            self.logger.warn("event '%s' published by client is not subscribed by anyone" % event)
            return

         self.logger.warn("pubsub not yet supported")

         self.sendJSONMessage(501, u"pubsub not yet supported")
         return

      else:
         self.logger.warn("client did not specify request type")
         self.sendJSONMessage(400, u"no request type given")


   def get_wamp_client(self, realm):

      if realm in self.wamp_clients:
         self.logger.debug("using existing client for realm '%s'" % realm)
         return defer.succeed(self.wamp_clients[realm])
      else:
         self.logger.debug("connecting new client for realm '%s'" % realm)
         d = defer.Deferred()

         def factory():
            client = WAMPClient()
            client._realm = realm
            client._on_join = d
            self.wamp_clients[realm] = client
            return client

         wamp_transport_factory = WAMPClientFactory(factory, self.service.r_uri)
         addr, port = self.service.r_address, self.service.r_port
         #client = clientFromString(reactor, "tcp:%s:%i" % (addr, port))
         #client.connect(wamp_transport_factory)
         wamp_transport_factory.host = addr
         wamp_transport_factory.port = port

         if wamp_transport_factory.isSecure:
            self.logger.info("securing connection using TLS")
            key, crt = self.service.client_key, self.service.client_crt
            if key and crt:
               self.logger.info("using client certificate authentication")
               self.logger.info("key: %s" % key)
               self.logger.info("certificate: %s" % crt)
               contextFactory = ClientContextFactory(key, crt)
            else:
               # use default (no client certificate auth)
               contextFactory = ssl.ClientContextFactory()

         else:
            contextFactory = None
            self.logger.warn("insecure operation; recommend switching to TLS")

         websocket.connectWS(wamp_transport_factory, contextFactory)
         return d


   @inlineCallbacks
   def onMessage(self, message, isBinary):
      "upon websocket message, parse it, get client for the realm and make the call"

      if isBinary:
         raise Exception("cannot handle binary messages")

      self.logger.debug("received request: {0}".format(message.decode('utf8')))

      try:
         parsed = json.loads(message)
      except:
         self.logger.warn("could not parse client request to JSON")
         self.sendJSONMessage(400, u"parsing request to JSON failed")
         return

         if not parsed.get("realm"):
            self.logger.warn("client did not specify realm")
            self.sendJSONMessage(400, u"realm not specified, please specify")

            return

      # get a connected WAMP client and register message delivery upon connect
      self.get_wamp_client(parsed["realm"]).addCallback(self.proxy_message, **parsed)
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
         self.logger.debug("discovered PubSub subscription: " + str(subscription))

   @inlineCallbacks
   def lookupProcedures(self):
      regsdata = yield self.call("wamp.registration.list")
      rids = [id for id in regsdata["exact"]]
      self._registrations = []
      for rid in rids:
         registration = yield self.call("wamp.registration.get", rid)
         self._registrations.append(registration["uri"])
         self.logger.debug("discovered RPC registration: " + registration["uri"])

   @inlineCallbacks
   def onConnect(self):
      self.logger.info("proxy WAMP client connected to router")
      yield self.join(self._realm, authmethods=[u"tls"])


   def onJoin(self, details):
      self.logger.info("proxy WAMP client joined realm: %s" % details)

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

   def __init__(self, server_uri, router_uri, client_key, client_crt, debug=False):
      self.s_uri = server_uri
      self.s_address = urlparse(server_uri).hostname
      self.s_port = urlparse(server_uri).port

      self.r_uri = router_uri
      self.r_address = urlparse(router_uri).hostname
      self.r_port = urlparse(router_uri).port

      self.client_key = client_key
      self.client_crt = client_crt

      self.debug = debug

      self.s_factory = WebSocketServerFactory(server_uri)
      proto = WSServer
      proto.service = self
      self.s_factory.protocol = proto
      self.s_factory.setProtocolOptions(maxConnections=40)

   def startService(self):
      self.s_listener = reactor.listenTCP(self.s_port, self.s_factory, interface=self.s_address)
      self.logger.info("service started")

   def stopService(self):
      self.s_listener.stopListening()
      self.s_factory.stopFactory()
      self.logger.info("service stopped")

