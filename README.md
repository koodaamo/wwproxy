# wwproxy

Twisted WebSocket to WAMP proxy

Make WAMP calls without supporting the WAMP protocol.

To start the proxy, run:

`twist wwproxy`

(or use `twistd` to run in the background)

Pass '--help' as a parameter for command-line options.

Default connection strings:

* websocket server: ws://127.0.0.1:9000/ws

* WAMP router: ws://127.0.0.1:8080/ws

The following message structures are used for conveying (WAMP) RPC and PubSub semantics,
using JSON-encoded messages. Some inspiration has been taken from JSON-RPC (http://www.jsonrpc.org).

For a RPC request, use the following structure:

   {
    "realm": <string>,
    "method: <string>,
    "args": [<arg>,..],
    "kwargs": {<name>:<value>,..},
   }

For a PUBSUB request, use the following structure:

   {
    "realm": <string>,
    "event: <string>,
    "args": [<arg>,..],
    "kwargs": {<name>:<value>,..},
   }

WAMP responses have the following structure:

   {
    "status": <code>,
    "response": <data>
   }

The following HTTP status codes are re-used. Note that some codes are only used in
responses to RPC calls.

 * 200 OK
 * 400 Bad Request
 * 401 Unauthorized (realm does not exist or insufficient credentials)
 * 404 Not Found (RPC endpoint not found for the requested method)
 * 500 Internal Server Error (RPC endpoint failure)
 * 501 Not Implemented (RPC endpoint not found for the requested method)
 * 503 Service Unavailable (WAMP router not present)
 * 504 Gateway Timeout (waiting for response from router or RPC endpoint timed out)
