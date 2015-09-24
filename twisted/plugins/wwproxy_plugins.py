from twisted.application.service import ServiceMaker

serviceMaker = ServiceMaker('wwproxy',
                            'wwproxy.main',
                            'WebSocket <-> WAMP Proxy Service',
                            'wwproxy')
