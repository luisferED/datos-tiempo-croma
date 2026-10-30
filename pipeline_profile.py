"""Optional constant-memory stage profiling; percentile upper bounds at 0.05 ms."""
import functools,threading,time
from array import array

class Histogram:
    def __init__(self,step=.05,maximum=1000):
        self.step=step; self.bins=array('Q',[0])*(int(maximum/step)+1)
        self.count=0; self.total=0.0; self.maximum=0.0
    def add(self,value):
        index=min(len(self.bins)-1,int(value/self.step))
        self.bins[index]+=1; self.count+=1; self.total+=value; self.maximum=max(self.maximum,value)
    def snapshot(self):
        targets={p:max(1,__import__('math').ceil(self.count*q)) for p,q in [('p50',.5),('p95',.95),('p99',.99)]}
        result={'count':self.count,'mean':self.total/self.count,'max':self.maximum,'percentile_precision_ms':self.step,'overflow_count':self.bins[-1]}
        cumulative=0
        for index,count in enumerate(self.bins):
            cumulative+=count
            for key,target in targets.items():
                if key not in result and cumulative>=target:
                    result[key]=min(self.maximum,(index+1)*self.step) if index<len(self.bins)-1 else self.maximum
            if all(key in result for key in targets): break
        return result

class StageProfiler:
    def __init__(self,enabled=False):
        self.enabled=enabled; self.lock=threading.Lock(); self.values={}; self.window=None
    def set_window(self,start,end):
        with self.lock:
            self.window=(start,end); self.values.clear()
    def active(self):
        return self.enabled and (self.window is None or self.window[0]<=time.perf_counter()<self.window[1])
    def start(self): return (time.perf_counter_ns(),time.thread_time_ns()) if self.active() else None
    def _add(self,name,wall,cpu):
        with self.lock:
            if name not in self.values: self.values[name]=(Histogram(),Histogram())
            self.values[name][0].add(wall); self.values[name][1].add(cpu)
    def finish(self,name,start):
        if start is not None: self._add(name,(time.perf_counter_ns()-start[0])/1e6,(time.thread_time_ns()-start[1])/1e6)
    def record(self,name,wall_ms):
        if self.active(): self._add(name,wall_ms,0.0)
    def decorate(self,name):
        def decorator(function):
            if not self.enabled: return function
            @functools.wraps(function)
            def wrapper(*args,**kwargs):
                start=self.start()
                try: return function(*args,**kwargs)
                finally: self.finish(name,start)
            return wrapper
        return decorator
    def snapshot(self):
        with self.lock:
            return {name:{'wall_ms':wall.snapshot(),'thread_cpu_ms':cpu.snapshot()} for name,(wall,cpu) in self.values.items()}
