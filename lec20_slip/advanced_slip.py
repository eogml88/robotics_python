# Copyright 2022 @RoadBalance
# Reference from https://pab47.github.io/legs.html
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import numpy as np
import matplotlib.pyplot as plt

from scipy import interpolate
from scipy.optimize import fsolve
from scipy.integrate import solve_ivp

# 1. flight eom
#    - contact event
#    - apex event
# 2. stance eom
#    - release event
# 3. one bounce
# 4. animation

class Params:
    def __init__(self):
        self.g = 9.81
        self.ground = 0.0
        self.l = 1
        self.m = 1
        
        # sprint stiffness
        self.k = 150
        # fixed angle
        self.theta = 5 * (np.pi / 180)
        
        # theta control
        self.I = 0.75
        self.phi_des = np.pi / 15
        self.Kp = 0.5
        self.Kd = 5.0
        
        self.pause = 0.001
        self.fps = 10

def contact(t, z, m, g, l0, k, theta):
    x, x_dot, y, y_dot, phi, phi_d = z
    # contact event
    return y - l0 * np.cos(phi)

def release(t, z, m, g, l0, k, I, phi_des, Kp, Kd):
    x, x_dot, y, y_dot, phi, phi_d = z
    l = np.sqrt(x**2 + y**2)
    
    return l - l0

def apex(t, z, m, g, l0, k, theta):
    x, x_dot, y, y_dot, phi, phi_d = z
    return y_dot

def flight(t, z, m, g, l0, k, theta):
    x, x_dot, y, y_dot, phi, phi_d = z
    return [x_dot, 0, y_dot, -g, phi_d, 0]

def controller(Kp, Kd, phi, phi_d, phi_des):
    return -(-Kp*(phi - phi_des) -Kd*phi_d)

def stance(t, z, m, g, l0, k, I, phi_des, Kp, Kd):
    x, x_dot, y, y_dot, phi, phi_d = z
    
    l = np.sqrt(x**2 + y**2)

    # F_spring = k * (l0 - l)
    # Fx_spring = F_spring * (x / l)
    # Fy_spring = F_spring * (y / l)
    # Fy_gravity = m*g
    
    # x_dd = (Fx_spring) / m
    # y_dd = (Fy_spring - Fy_gravity) / m
    
    Tphi = controller(Kp, Kd, phi, phi_d, phi_des)
    
    M = np.array([
        [m, 0, 0],
        [0, m, 0],
        [0, 0, I]
    ])
    
    sin_theta = (x / l)
    cos_theta = (y / l)
    
    # Force by spring
    F_spring = k * (l0 - l)
    G1 = F_spring * sin_theta
    G2 = F_spring * cos_theta - m*g
    G3 = 0
    
    # spring thrust & friection ignored
    F_tau = - Tphi / l
    Tau1 = F_tau * cos_theta
    Tau2 = - F_tau * sin_theta
    Tau3 = - Tphi
    
    # Tau1 = -(Tphi*y)/(l*l)
    # Tau2 = (Tphi*x)/(l*l)
    # Tau3 = -Tphi
    
    b = np.array([
        Tau1 - G1,
        Tau2 - G2,
        Tau3 - G3
    ])
    
    x = np.linalg.solve(M, b)
    
    return [x_dot, x[0], y_dot, x[1], phi_d, x[2]]


def onestep(z0, t0, params):
    
    dt = 5
    m, g, k = params.m, params.g, params.k
    # l0, theta = params.l, params.theta
    l0, I = params.l, params.I
    phi_des, Kp, Kd = params.phi_des, params.Kp, params.Kd
    
    x, x_d, y, y_d, phi, phi_d = z0
    
    t_output = np.zeros(1)
    t_output[0] = t0
    # z_output = [x, x_dot, y, y_dot, phi, phi_dot, x_foot, y_foot]
    z_output = np.zeros((1, 8))
    # z_output[0] = [*z0, x+l0*np.sin(theta), y-l0*np.cos(theta)]
    z_output[0] = [*z0, x+l0*np.sin(phi), y-l0*np.cos(phi)]

    #####################################
    ###         contact phase         ###
    #####################################
    contact.direction = -1
    contact.terminal = True
    
    ts = np.linspace(t0, t0+dt, 1001)

    # def contact(t, z, l0, theta):
    contact_sol = solve_ivp(
        flight, [t0, t0+dt], z0, method='RK45', t_eval=np.linspace(t0, t0+dt, 1001),
        dense_output=True, events=contact, atol = 1e-13, rtol = 1e-12, 
        args=(m, g, l0, k, phi)
    )
    
    t_contact = contact_sol.t
    m, n = contact_sol.y.shape
    z_contact = contact_sol.y.T
    # print(z_contact[-1])
    phi = z_contact[-1,4]

    # calculate foot position for animation
    x_foot = z_contact[:,0] + l0*np.sin(phi)
    y_foot = z_contact[:,2] - l0*np.cos(phi)

    # append foot position into z vector
    z_contact_output = np.concatenate((z_contact, x_foot.reshape(-1,1), y_foot.reshape(-1,1)), axis=1)
    
    # add to output
    t_output = np.concatenate((t_output, t_contact[1:]))
    z_output = np.concatenate((z_output, z_contact_output[1:]))

    #####################################
    ## adjust new state for next phase ##
    #####################################
    t0, z0 = t_contact[-1], z_contact[-1]
    # save the x position for future
    x_com = z0[0]
    # relative distance wrt contact point because of 
    # non-holonomic nature of the system
    z0[0] = -l0*np.sin(phi)
    x_foot_gnd = x_com + l0*np.sin(phi)
    y_foot_gnd = params.ground

    #####################################
    ###          stance phase         ###
    #####################################
    release.direction = +1
    release.terminal = True

    ts = np.linspace(t0, t0+dt, 1001)
    # def stance(t, z, m, g, l0, k, theta)
    release_sol = solve_ivp(
        stance, [t0, t0+dt], z0, method='RK45', t_eval=np.linspace(t0, t0+dt, 1001),
        dense_output=True, events=release, atol = 1e-13, rtol = 1e-13, 
        args=(m, g, l0, k, I, phi_des, Kp, Kd)
    )

    t_release = release_sol.t
    m, n = release_sol.y.shape
    z_release = release_sol.y.T
    phi = z_release[-1,4]
    z_release[:,0] = z_release[:,0] + x_com + l0*np.sin(phi)

    # append foot position for animation
    x_foot = x_foot_gnd * np.ones((n,1))
    y_foot = y_foot_gnd * np.ones((n,1))
    z_release_output = np.concatenate((z_release, x_foot, y_foot), axis=1)
    
    # add to output
    t_output = np.concatenate((t_output, t_release[1:]))
    z_output = np.concatenate((z_output, z_release_output[1:]))

    #####################################
    ## adjust new state for next phase ##
    #####################################
    t0, z0 = t_release[-1], z_release[-1]

    #####################################
    ###           apex  phase         ###
    #####################################
    apex.direction = 0
    apex.terminal = True

    ts = np.linspace(t0, t0+dt, 1001)
    apex_sol = solve_ivp(
        flight, [t0, t0+dt], z0, method='RK45', t_eval=np.linspace(t0, t0+dt, 1001),
        dense_output=True, events=apex, atol = 1e-13, rtol = 1e-13, 
        args=(m, g, l0, k, phi)
    )

    t_apex = apex_sol.t
    m, n = apex_sol.y.shape
    z_apex = apex_sol.y.T

    # calculate foot position for animation
    x_foot = z_apex[:,0] + l0*np.sin(phi)
    y_foot = z_apex[:,2] - l0*np.cos(phi)
    z_apex_output = np.concatenate((z_apex, x_foot.reshape(-1,1), y_foot.reshape(-1,1)), axis=1)

    # add to output
    t_output = np.concatenate((t_output, t_apex[1:]))
    z_output = np.concatenate((z_output, z_apex_output[1:]))

    return z_output, t_output

def n_step(zstar,params,steps):
    
    # x0 = 0; x0dot = z0(1);  
    # y0 = z0(2); y0dot = 0;
    
    z0 = zstar
    t0 = 0

    # x, x_d, y, y_d, theta, theta_d, x_foot, y_foot
    z = np.zeros((1, 8))
    t = np.zeros(1)

    i = 0
    for i in range(steps):
        
        if i == 0:
            z, t = onestep(z0, t0, params)
        else:
            z_step, t_step = onestep(z0, t0, params)
            z = np.concatenate((z, z_step[1:]))
            t = np.concatenate((t, t_step[1:]))

        z0 = z[-1][:-2]
        t0 = t[-1]
    
    return z, t

def animate(z, t, parms):
    #interpolation
    data_pts = 1/parms.fps
    t_interp = np.arange(t[0], t[len(t)-1], data_pts)
    m, n = np.shape(z)
    shape = (len(t_interp),n)
    z_interp = np.zeros(shape)

    for i in range(0, n):
        f = interpolate.interp1d(t, z[:,i])
        z_interp[:,i] = f(t_interp)

    l = parms.l

    min_xh = min(z[:,0]); max_xh = max(z[:,0]);
    dist_travelled = max_xh - min_xh;
    camera_rate = dist_travelled/len(t_interp);

    window_xmin = -1*l; window_xmax = 1*l;
    window_ymin = -0.1; window_ymax = 1.9*l;

    #plot
    for i in range(0,len(t_interp)):

        x, y = z_interp[i,0], z_interp[i,2]
        x_foot, y_foot = z_interp[i,6], z_interp[i,7]

        leg, = plt.plot([x, x_foot],[y, y_foot],linewidth=2, color='black')
        hip, = plt.plot(x, y, color='red', marker='o', markersize=10)

        window_xmin = window_xmin + camera_rate;
        window_xmax = window_xmax + camera_rate;
        plt.xlim(window_xmin,window_xmax)
        plt.ylim(window_ymin,window_ymax)
        plt.gca().set_aspect('equal')

        plt.pause(parms.pause)
        hip.remove()
        leg.remove()

    # plt.close()

def partialder(z0, parms):

    pert = 1e-5
    N = len(z0)

    J = np.zeros((N,N))
    z_temp1 = [0]*N
    z_temp2 = [0]*N
    for i in range(0,N):
        for j in range(0,N):
            z_temp1[j] = z0[j]
            z_temp2[j] = z0[j]
        z_temp1[i] = z_temp1[i]+pert
        z_temp2[i] = z_temp2[i]-pert
        [z1,t1] = onestep(z_temp1, 0, parms)
        [z2,t2] = onestep(z_temp2, 0, parms)
        for j in range(0,N):
            J[i,j] = (z1[len(t1)-1,j] - z2[len(t2)-1,j])/(2*pert)

    return J

def fixedpt(z0, parms):
    t0 = 0
    z1, t1 = onestep(z0, t0, parms)
    N = len(t1)-1

    # print(f"z1[N] : {z1[N]}")
    # print(f"z0 : {z0}")
    #F(x0) - x0 = 0
    return z1[N,0]-z0[0], z1[N,1]-z0[1],\
        z1[N,2]-z0[2], z1[N,3]-z0[3],\
        z1[N,4]-z0[4], z1[N,5]-z0[5]

if __name__=="__main__":
    
    params = Params()

    # 이제 state가 3개가 된다. x, y, theta
    x, x_d, y, y_d, phi, phi_d = 0, 0.34271, 1.1, 0, 5 * (np.pi / 180), 0
    z0 = np.array([x, x_d, y, y_d, phi, phi_d])

    # 실패하지 않는 초기 조건을 찾아보자. Jacobian의 최대 eigenvalue를 통해 판별할 수 있다.
    # 
    # max(eig(J)) < 1 => stable
    # max(eig(J)) = 1 => neutrally stable
    # max(eig(J)) > 1 => unstable
    zstar = fsolve(fixedpt, z0, params)
    print(f"zstar : {zstar}")
    
    # Jacobian을 구할 수식이 없다. 따라서 수치적으로 구해본다.
    J = partialder(zstar, params)
    eigVal, eigVec = np.linalg.eig(J)
    print(f"eigVal {eigVal}")
    print(f"eigVec {eigVec}")
    print(f"abs(eigVal) : {np.abs(eigVal)}")

    z, t = n_step(z0, params, 10)
    animate(z, t, params)