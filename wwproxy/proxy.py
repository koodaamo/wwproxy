import sys
from urlparse import urlparse
import pkg_resources
from twisted.application import service
from twisted.logger import Logger, globalLogPublisher, textFileLogObserver
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet import defer
from twisted.internet.endpoints import clientFromString
from autobahn.twisted.wamp import ApplicationSessionFactory, ApplicationSession
from autobahn.twisted.websocket import WebSocketServerProtocol, \
                                       WebSocketServerFactory, \
                                       WampWebSocketClientFactory
from autobahn.wamp.exception import ApplicationError

#globalLogPublisher.addObserver(textFileLogObserver(sys.stdout))

PUBSUB = "pubsub"
RPC = "rpc"
RPC_SMS_SEND = "vidamin.services.tele.sms.send"
MSGSEP = ':'

#
# PROTOCOL
#

class WSServer(WebSocketServerProtocol):

   logger = Logger()

   def onConnect(self, request):
      self.logger.info("Client connecting: {0}".format(request.peer))
      self.wamp_session = self.factory.wamp_session_factory._session # live session

   def onOpen(self):
      self.logger.info("WebSocket connection open.")

   def parseWSMessageFormat(self, message):
      try:
         kind, opid, payload = message.decode("UTF-8").split(MSGSEP)
      except:
         return None
      else:
         return kind, opid, payload


   @inlineCallbacks
   def onMessage(self, message, isBinary):

      if isBinary:
         self.logger.info("received binary: {0} bytes".format(len(message)))
      else:
         self.logger.info("received text: {0}".format(message.decode('utf8')))

      parsed = self.parseWSMessageFormat(message)
      if parsed:
         kind, opid, payload = parsed
         if kind=="rpc" and opid in self.wamp_session._registrations:
            try:
               recipient, message = payload.split('|')
            except:
               pass
            else:
               try:
                  yield self.wamp_session.call(opid, recipient, message)
               except ApplicationError as exc:
                  self.logger.warn("WAMP request failed: %s" % str(exc))
               else:
                  self.sendMessage("OK".encode("utf-8"), False)
                  return
      elif kind == "pubsub" and opid in self.wamp_session._subscriptions:
         pass

      # otherwise, fail
      self.sendMessage("FAIL".encode("utf-8"), False)


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
      self.logger.info("CONNECTED")
      self.join("realm1")
      yield self.lookupProcedures()
      yield self.lookupSubscriptions()

   def onJoin(self, details):
      if not getattr(self.factory, "_appSession", None):
         self.factory._session = self # set the session instance

   def onLeave(self, details):
      if getattr(self.factory, "_appSession", None) == self:
         self.factory._appSession = None

      slist = yield self.call("wamp.subscription.list")
      self.logger.info("SUBSCRIPTIONS: %s" % str(slist))
      rlist = yield self.call("wamp.registration.list")
      self.logger.info("REGISTRATIONS: %s" % str(rlist))


#
# SERVICE DEFINITIONS
#

class WebSocketListenerService(service.Service):

   name = "WebSocketListener"

   logger = Logger()

   def __init__(self, connstr, debug=False):
      self.connstr = connstr
      self.address = urlparse(connstr).hostname
      self.port = urlparse(connstr).port
      self.debug = debug

      self.factory = WebSocketServerFactory(connstr)
      self.factory.protocol = WSServer
      self.factory.setProtocolOptions(maxConnections=10)

   def startService(self):
      wampservice = self.parent.getServiceNamed("WAMPClient")
      self.factory.wamp_session_factory = wampservice.session_factory
      self.listener = reactor.listenTCP(self.port, self.factory, interface=self.address)
      self.logger.info("service started")

   def stopService(self):
      self.listener.stopListening()
      self.factory.stopFactory()
      self.logger.info("service stopped")


class WAMPClientService(service.Service):

   name = "WAMPClient"

   logger = Logger()

   def __init__(self, connstr, debug=False):
      self.connstr = connstr
      self.address = urlparse(connstr).hostname
      self.port = urlparse(connstr).port
      self.debug = debug

      self.session_factory = ApplicationSessionFactory() # need to start early
      self.session_factory.session = WAMPClient
      self.transport_factory = WampWebSocketClientFactory(self.session_factory, connstr)

   def startService(self):
      self.client = clientFromString(reactor, "tcp:%s:%i" % (self.address, self.port))
      self.client.connect(self.transport_factory)
      self.logger.info("service started")

   def stopService(self):
      self.client.disconnect()
      self.session_factory.stopFactory()
      self.transport_factory.stopFactory()
      self.logger.info("service stopped")




