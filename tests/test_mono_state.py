import unittest
from unittest.mock import patch
from mono_state import Memory,StateObserver

class ProbeBounds(unittest.TestCase):
    def test_invalid_ranges_never_reach_proc(self):
        m=Memory.__new__(Memory);m.fd=3
        with patch('os.pread') as read:
            for addr,n in [(0,8),(-1,8),(2**47,8),(100,-1),(100,2**20+1),(2**47-4,8)]:
                with self.assertRaises(ValueError):m.read(addr,n)
            read.assert_not_called()
    def test_short_read_rejected(self):
        m=Memory.__new__(Memory);m.fd=3
        with patch('os.pread',return_value=b'\0'):
            with self.assertRaises(RuntimeError):m.read(100,8)
    def test_class_cycle_rejected(self):
        m=Memory.__new__(Memory);m.cache={}
        m.ptr=lambda a:0 if a==100+0x90 else 100
        m.i32=lambda a:0
        with self.assertRaises(RuntimeError):m.fields(100)
    def test_boolean_layout_mismatch_rejected(self):
        m=Memory.__new__(Memory);m.ptr=lambda a:100
        m.fields=lambda c:{'m_busy':(16,False)}
        m.read=lambda a,n:b'\x02'
        with self.assertRaises(RuntimeError):m.value(100,'m_busy','bool')

if __name__=='__main__':unittest.main()

class ObserverFailureTests(unittest.TestCase):
    def test_permission_failure_is_not_retried_for_same_process(self):
        with patch('mono_state.Memory',side_effect=PermissionError) as factory:
            observer=StateObserver()
            self.assertFalse(observer.observe(10)['available'])
            self.assertFalse(observer.observe(10)['available'])
            self.assertEqual(factory.call_count,1)
            observer.observe(11)
            self.assertEqual(factory.call_count,2)
    def test_failed_read_does_not_retain_previous_snapshot(self):
        with patch('mono_state.Memory') as factory, patch('mono_state.classes',return_value={}), patch('mono_state.snapshot',side_effect=[{'m_mode':15},RuntimeError('bad layout')]):
            factory.return_value.pid=10
            observer=StateObserver()
            self.assertTrue(observer.observe(10)['available'])
            result=observer.observe(10)
            self.assertFalse(result['available'])
            self.assertNotIn('m_mode',result)
            factory.return_value.close.assert_called_once()

class UninitializedStaticTests(unittest.TestCase):
    def test_class_without_runtime_info_is_not_a_live_singleton(self):
        m=Memory.__new__(Memory)
        m.fields=lambda c:{'s_instance':(16,True)}
        m.i32=lambda a:0
        addresses=[]
        def read(a):
            addresses.append(a)
            return 0
        m.ptr=read
        self.assertEqual(m.instance(100),0)
        self.assertNotIn(8,addresses)
