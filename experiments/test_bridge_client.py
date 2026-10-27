import json,os,socket,tempfile,threading,unittest
from pathlib import Path
from bridge_client import command,UnknownOutcome
class BridgeClientTests(unittest.TestCase):
 def test_unknown_action_rejected(self):
  with self.assertRaises(ValueError):command('/missing','arbitrary',session='s'*32,game_id='g',turn=1,options_id=2,entity_id=3)
 def test_public_socket_rejected(self):
  with tempfile.TemporaryDirectory(prefix='bg-',dir='/tmp') as folder:
   path=Path(folder)/'c.sock'
   with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
    server.bind(str(path));path.chmod(0o666)
    with self.assertRaises(PermissionError):command(path,'buy',session='s'*32,game_id='g',turn=1,options_id=2,entity_id=3)
 def test_mismatched_reply_is_unknown_not_retried(self):
  with tempfile.TemporaryDirectory(prefix='bg-',dir='/tmp') as folder:
   path=Path(folder)/'c.sock';seen=[]
   with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
    server.bind(str(path));path.chmod(0o600);server.listen(1);server.settimeout(3)
    def respond():
     conn,_=server.accept()
     with conn:
      seen.append(conn.recv(4096));conn.sendall(b'{"id":"wrong","status":"done"}\n')
    t=threading.Thread(target=respond);t.start()
    with self.assertRaises(UnknownOutcome):command(path,'buy',session='s'*32,game_id='g',turn=1,options_id=2,entity_id=3)
    t.join(3);self.assertFalse(t.is_alive());self.assertEqual(len(seen),1)
if __name__=='__main__':unittest.main()
