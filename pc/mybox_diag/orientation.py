"""Gyro quaternion integration + gravity correction. Relative yaw; no magnetometer claim."""
import math
import numpy as np

def multiply(a,b):
    w,x,y,z=a;v,i,j,k=b
    return np.array([w*v-x*i-y*j-z*k,w*i+x*v+y*k-z*j,w*j-x*k+y*v+z*i,w*k+x*j-y*i+z*v])
def conjugate(q):return q*np.array([1,-1,-1,-1])
def rotation(q):
    w,x,y,z=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
def euler(q):
    w,x,y,z=q
    return tuple(math.degrees(v) for v in (math.atan2(2*(w*x+y*z),1-2*(x*x+y*y)),math.asin(max(-1,min(1,2*(w*y-z*x)))),math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))))
class Orientation:
    def __init__(self):
        self.q=np.array([1.,0,0,0]);self.zero=self.q.copy();self.last_ms=None;self.state='Ожидание данных IMU';self.bias=np.zeros(3);self._bias_sum=np.zeros(3);self._bias_count=0
    def reset_zero(self):self.zero=self.q.copy()
    @property
    def display_q(self):return multiply(conjugate(self.zero),self.q)
    def update(self,sample):
        if not sample.get('fresh',False):self.state='Нет свежих данных';return
        stamp=sample.get('sample_ms');a=np.array(sample.get('accel_m_s2',[]),dtype=float);g=np.array(sample.get('gyro_deg_s',[]),dtype=float)
        if stamp is None or a.shape!=(3,) or g.shape!=(3,) or not np.isfinite(a).all() or not np.isfinite(g).all():self.state='Неверные данные';return
        if self.last_ms is None:
            self.last_ms=stamp
            # Initial gravity alignment; yaw has no absolute reference.
            n=np.linalg.norm(a)
            if n>0:
                u=a/n;target=np.array([0.,0.,1.]);cross=np.cross(u,target);q=np.r_[1+np.dot(u,target),cross]
                self.q=np.array([0.,1.,0.,0.]) if np.linalg.norm(q)<1e-6 else q/np.linalg.norm(q)
            return
        dt=((stamp-self.last_ms)&0xffffffff)/1000.;self.last_ms=stamp
        if dt==0:return
        if dt>0.2:self.state='Разрыв данных; оценка приостановлена';return
        norm=np.linalg.norm(a)
        if abs(norm-9.80665)<0.5 and np.linalg.norm(g)<2 and self._bias_count<100:
            self._bias_sum+=g;self._bias_count+=1;self.bias=self._bias_sum/self._bias_count
        omega=np.radians(g-self.bias)
        if 7.8<norm<11.8:
            predicted=rotation(self.q).T@np.array([0.,0.,1.]);omega+=0.8*np.cross(a/norm,predicted)
        # Integrate using a finite rotation; stable for packet rates 1..100 Hz.
        angle=np.linalg.norm(omega)*dt
        if angle>0:
            dq=np.r_[math.cos(angle/2),omega/np.linalg.norm(omega)*math.sin(angle/2)];self.q=multiply(self.q,dq);self.q/=np.linalg.norm(self.q)
        self.state='Относительный курс · возможен дрейф; оценка по IMU'
