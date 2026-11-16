import json
from pathlib import Path
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from test_web_stats import web


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.now=100.;self.sent=[]
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.feed=web.LiveFeed(Path(self.tmp.name)/'latest.log')
        self.chat=web.ChatGateway(Path('/unused'),self.feed,sender=lambda n,m:self.sent.append((n,m)),clock=lambda:self.now)

    def test_sliding_window_and_independent_peer(self):
        for i in range(5):self.chat.send('a',{'name':'Player','message':str(i)})
        self.assertEqual(self.chat.info('a')['remaining'],0)
        with self.assertRaises(web.ChatError) as caught:self.chat.send('a',{'name':'Other','message':'blocked'})
        self.assertEqual(caught.exception.code,429);self.assertEqual(caught.exception.quota['retryAfter'],30)
        self.chat.send('b',{'name':'Other','message':'allowed'})
        self.now+=29.1;self.assertEqual(self.chat.info('a')['retryAfter'],1)
        self.now+=.9;self.chat.send('a',{'name':'Player','message':'again'})
        self.assertEqual(self.chat.info('a')['remaining'],4)

    def test_global_limit_and_expiration_cleanup(self):
        for i in range(20):self.chat.send(str(i),{'name':'Player','message':'Hello'})
        with self.assertRaises(web.ChatError) as c:self.chat.send('new',{'name':'Player','message':'blocked'})
        self.assertEqual(c.exception.code,429)
        self.now+=31;self.assertEqual(self.chat.info('new')['remaining'],5)
        self.assertEqual(self.chat.peers,{})

    def test_parallel_requests_cannot_bypass_limit(self):
        def send(i):
            try:self.chat.send('a',{'name':'Player','message':str(i)});return True
            except web.ChatError:return False
        with ThreadPoolExecutor(max_workers=12) as pool:results=list(pool.map(send,range(30)))
        self.assertEqual(sum(results),5);self.assertEqual(len(self.sent),5)

    def test_invalid_input_does_not_send_or_spend_quota(self):
        for value in [None,[],{'name':'Player','message':'x','command':'stop'},
                      {'name':'bad name','message':'Hi'}, {'name':'Player','message':'\nstop'},
                      {'name':'Player','message':'\u0000Hi'},{'name':'Player','message':'§cRed'},
                      {'name':'Player','message':'a'*201},{'name':'Player','message':'   '}]:
            with self.assertRaises(web.ChatError):self.chat.send('a',value)
        self.assertEqual(self.sent,[]);self.assertEqual(self.chat.info('a')['remaining'],5)

    def test_ambiguous_delivery_not_retried_and_uses_quota(self):
        def fail(n,m):raise OSError('offline')
        self.chat.sender=fail
        with self.assertRaises(web.ChatError) as c:self.chat.send('a',{'name':'Player','message':'Hi'})
        self.assertEqual(c.exception.code,503);self.assertEqual(self.chat.info('a')['remaining'],4)
        self.assertEqual(list(self.feed.events),[])

    def test_broadcast_is_literal_json_not_a_command_or_selector(self):
        commands=[]
        class Fake:
            def __init__(self,*a,**kw):pass
            def command(self,c):commands.append(c)
            def close(self):pass
        self.chat.sender=self.chat.broadcast
        message='/op Somebody @e "hello" <img src=x>'
        with patch.object(web.exporter,'Rcon',Fake),patch.object(web.exporter,'read_properties',return_value={'enable-rcon':'true'}):
            self.chat.send('a',{'name':'Player','message':message})
        self.assertEqual(len(commands),1);self.assertTrue(commands[0].startswith('tellraw @a '))
        component=json.loads(commands[0][len('tellraw @a '):]);self.assertEqual(component[1],{'text':message,'color':'white'})
        self.assertEqual(self.feed.events[0]['type'],'webchat');self.assertEqual(self.feed.events[0]['text'],message)


class ChatHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.sent=[]
        feed=web.LiveFeed(Path(self.tmp.name)/'latest.log')
        chat=web.ChatGateway(Path('/unused'),feed,limit=2,sender=lambda n,m:self.sent.append((n,m)))
        self.server=ThreadingHTTPServer(('127.0.0.1',0),web.handler(None,Path(self.tmp.name),feed=feed,chat=chat))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def post(self,headers=None,data=None):
        h={'Origin':self.url,'Content-Type':'application/json',**(headers or {})}
        req=Request(self.url+'/api/chat',data=data or json.dumps({'name':'Player','message':'Grüße'}).encode(),headers=h,method='POST')
        try:r=urlopen(req)
        except HTTPError as e:r=e
        with r:return r.status,dict(r.headers),json.load(r)

    def test_server_enforces_limit_and_ignores_forwarded_headers(self):
        for i in range(2):self.assertEqual(self.post({'X-Forwarded-For':str(i)})[0],200)
        status,headers,data=self.post({'X-Forwarded-For':'another-IP'})
        self.assertEqual(status,429);self.assertGreater(int(headers['Retry-After']),0)
        self.assertEqual(data['quota']['remaining'],0);self.assertEqual(len(self.sent),2)
        with urlopen(self.url+'/api/chat') as r:self.assertEqual(json.load(r)['remaining'],0)

    def test_cross_origin_and_large_or_wrong_content_rejected(self):
        self.assertEqual(self.post({'Origin':'https://other.example'})[0],403)
        self.assertEqual(self.post({'Origin':'null'})[0],403)
        self.assertEqual(self.post({'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.post(data=b'x'*2049)[0],413)
        self.assertEqual(self.post(data=b'{invalid')[0],400)
        self.assertEqual(self.sent,[])
