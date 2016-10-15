# wwproxy
Twisted WebSocket to WAMP proxy

Make WAMP calls without supporting the WAMP protocol.

To start the proxy, run:

`twist wwproxy`

(or use `twistd` to run in the background)

Default connection strings:

* websocket server: ws://127.0.0.1:9000/ws

* WAMP router: ws://127.0.0.1:8080/ws

To make WAMP requests over Websocket, use the following message notation:

* realm:rpc:identifier:payload

* realm:pubsub:identifier:payload

Where payload is a JSON object with {args:[], kwargs:{}} stanza.
