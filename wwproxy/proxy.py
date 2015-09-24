import sys
from urlparse import urlparse
import pkg_resources
from twisted.application import service
from twisted.logger import Logger, globalLogPublisher, textFileLogObserver
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.endpoints import clientFromString
from autobahn.twisted.wamp import ApplicationSessionFactory, ApplicationSession
from autobahn.twisted.websocket import WebSocketServerProtocol, \
                                       WebSocketServerFactory, \
                                       WampWebSocketClientFactory
from autobahn.wamp.exception import ApplicationError

globalLogPublisher.addObserver(textFileLogObserver(sys.stdout))

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
         if kind=="rpc" and opid=="vidamin.services.tele.sms.send":
            try:
               recipient, message = payload.split('|')
            except:
               pass
            else:
               call = self.factory.wamp_session_factory._session.call # the live session
               try:
                  yield call("vidamin.services.tele.sms.send", recipient, message)
               except ApplicationError:
                  pass
               else:
                  self.sendMessage("OK".encode("utf-8"), False)
                  return

      # otherwise, fail
      self.sendMessage("FAIL".encode("utf-8"), False)


   def onClose(self, wasClean, code, reason):
      self.logger.info("WebSocket connection closed: {0}".format(reason))


class WAMPClient(ApplicationSession):

   logger = Logger()

   @inlineCallbacks
   def lookupSubscriptions(self):
      slist = yield self.call("wamp.subscription.list")
      yield [s["exact"] for s in slist]

   @inlineCallbacks
   def lookupProcedures(self):
      rlist = yield self.call("wamp.registration.list")
      yield [r["exact"] for r in rlist]

   def onConnect(self):
      self.logger.info("CONNECTED")
      self.join("realm1")
      self.logger.info(', '.join(self.lookupProcedures()))
      self.logger.info(', '.join(self.lookupSubscriptions()))

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

   def stopService(self):
      self.listener.stopListening()
      self.factory.stopFactory()


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

   def stopService(self):
      self.client.disconnect()
      self.session_factory.stopFactory()
      self.transport_factory.stopFactory()




