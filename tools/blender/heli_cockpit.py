# Siege Wing helicopter — cockpit interior. exec'd by heli.py into its namespace (shares constants, heli_lib, mk_mat, OBJS...).
# cockpit_mats() is called from main() before geometry is built: declare cockpit-only materials there.
def cockpit_mats():
    pass

# ------------------------------------------------------------------ cockpit
PA = rad(15)
RP = Matrix(((1, 0, 0), (0, cos(PA), sin(PA)), (0, -sin(PA), cos(PA))))
PP = V(0, 2.70, 0.55)
MTXT = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))

def pl(u, v, d=0.0, P=None, R=None):
    return (PP if P is None else P) + (RP if R is None else R) @ V(u, -d, v)

def ptext(mb, s, size, u, v, d, mat='GaugeMark', tint=T_W, P=None, R=None):
    if not s: return
    M = Matrix.Translation(pl(u, v, d, P, R)) @ ((RP if R is None else R) @ MTXT).to_4x4()
    P_text(mb, s, size, M, mat, tint)

def pbox(mb, u, v, d, su, sv, sd, mat, tint, bevel=0.0, ang=0.0, P=None, R=None):
    Rr = (RP if R is None else R) @ Matrix.Rotation(ang, 3, 'Y')
    P_box(mb, pl(u, v, d, P, R), (su, sd, sv), mat, tint, bevel, rot=Rr)

def gauge(mb, u, v, label, nums, full=False, r=0.044, P=None, R=None):
    R_ = RP if R is None else R
    nrm = R_ @ V(0, -1, 0)
    c = pl(u, v, 0, P, R)
    P_revolve(mb, c + nrm * 0.0015, nrm, [(0, r)], 'Paint', T_BLACK, seg=24)       # face
    P_torus(mb, c + nrm * 0.004, nrm, r + 0.002, 0.005, 'Metal', T_GUN, seg=24, rseg=6)
    a0, a1 = (-180, 180) if full else (-135, 135)
    nmaj = 12 if full else len(nums) - 1
    steps = nmaj * (3 if full else 5)
    for k in range(steps + (0 if full else 1)):
        a = rad(a0 + (a1 - a0) * k / steps)
        major = k % (3 if full else 5) == 0
        ln = 0.009 if major else 0.005
        rr = r - 0.004 - ln / 2
        pbox(mb, u + rr * sin(a), v + rr * cos(a), 0.0025, 0.0022 if major else 0.0012, ln, 0.001, 'GaugeMark', T_W, ang=a, P=P, R=R)
    if nums:
        for k, s in enumerate(nums):
            a = rad(360.0 * k / len(nums)) if full else rad(a0 + (a1 - a0) * k / (len(nums) - 1))
            rr = r - 0.0205
            ptext(mb, s, 0.0105, u + rr * sin(a), v + rr * cos(a), 0.0025, P=P, R=R)
    if label:
        ptext(mb, label, 0.0075, u, v - r * 0.52, 0.0025, tint=(0.6, 0.6, 0.6), P=P, R=R)
    P_revolve(mb, c + nrm * 0.006, nrm, [(0, 0.006), (0.002, 0.005)], 'Paint', T_INT2, seg=10)   # hub cap

def needle(name, u, v, parent, ang0=0.0):
    mb = MB()
    c = pl(u, v, 0.0045)
    ids = [mb.addv(pl(u + x, v + y, 0.0045), T_W) for x, y in ((-0.0028, -0.009), (0.0028, -0.009), (0.0009, 0.034), (-0.0009, 0.034))]
    mb.addf(ids, 'Needle')
    return build(mb, name, origin=c, rot=RP, parent=parent)


def seat(mb, y0, zp):
    ta = T_INT2
    P_box(mb, V(0, y0 + 0.22, zp - 0.04), (0.46, 0.48, 0.08), 'Paint', ta, 0.02)
    Rb = Matrix.Rotation(rad(-10), 3, 'X')
    P_box(mb, V(0, y0 - 0.05, zp + 0.3), (0.46, 0.07, 0.7), 'Paint', ta, 0.02, rot=Rb)
    P_box(mb, V(0, y0 - 0.115, zp + 0.74), (0.26, 0.07, 0.22), 'Paint', ta, 0.02, rot=Rb)
    for s in (-1, 1):
        P_box(mb, V(s * 0.24, y0 + 0.14, zp + 0.14), (0.025, 0.42, 0.34), 'Paint', ta, 0.008)
        P_box(mb, V(s * 0.07, y0 - 0.0, zp + 0.36), (0.045, 0.012, 0.56), 'Paint', T_BLACK, rot=Rb)      # harness
    P_box(mb, V(0, y0 + 0.23, zp + 0.012), (0.40, 0.42, 0.04), 'Paint', T_FABRIC, 0.015)
    P_box(mb, V(0, y0 - 0.008, zp + 0.3), (0.38, 0.04, 0.6), 'Paint', T_FABRIC, 0.015, rot=Rb)
    P_box(mb, V(0, y0 - 0.075, zp + 0.74), (0.2, 0.04, 0.16), 'Paint', T_FABRIC, 0.015, rot=Rb)
    P_box(mb, V(0, y0 + 0.2, zp - 0.2), (0.3, 0.3, 0.26), 'Paint', T_INT, 0.01)        # pedestal


def figure(body, head, hip, hands):
    """Seated crew member. hip: Vector, hands: (left, right) target points."""
    h = hip
    # torso
    rings = []
    for (dy, dz, w, d) in ((0.0, -0.04, 0.16, 0.11), (0.01, 0.12, 0.15, 0.10), (0.03, 0.3, 0.185, 0.115), (0.04, 0.44, 0.19, 0.10), (0.05, 0.5, 0.07, 0.06)):
        r = []
        for j in range(12):
            a = 2 * pi * j / 12
            r.append(h + V(w * math.copysign(abs(sin(a)) ** 0.8, sin(a)), dy + d * math.copysign(abs(cos(a)) ** 0.8, cos(a)), dz))
        rings.append(r)
    P_loft(body, rings, 'Paint', T_VEST, cap0=True, cap1=True,
           tintfn=lambda i, j: T_SUIT if i == 0 else T_VEST)
    hc = h + V(0, 0.10, 0.70)
    P_cyl(body, h + V(0, 0.05, 0.48), hc + V(0, -0.02, -0.08), 0.05, 'Paint', T_SUIT, seg=8)
    for s in (-1, 1):
        sh = h + V(s * 0.2, 0.04, 0.42)
        hd = hands[0 if s < 0 else 1]
        mid = (sh + hd) / 2
        el = mid + V(s * 0.09, -0.06, -0.12)
        limb(body, sh, el, 0.052, 0.045, 'Paint', T_SUIT)
        limb(body, el, hd, 0.045, 0.038, 'Paint', T_SUIT)
        P_sphere(body, hd, 0.046, 'Paint', T_BLACK, seg=8, rings=6)
        hipj = h + V(s * 0.1, 0.02, 0.0)
        kn = h + V(s * 0.15, 0.47, 0.07)
        an = h + V(s * 0.13, 0.86, -0.36)
        limb(body, hipj, kn, 0.078, 0.062, 'Paint', T_SUIT)
        limb(body, kn, an, 0.06, 0.048, 'Paint', T_SUIT)
        P_box(body, an + V(0, 0.07, -0.04), (0.1, 0.26, 0.1), 'Paint', T_BLACK, 0.03, rot=Matrix.Rotation(rad(25), 3, 'X'))
    # head
    P_sphere(head, hc, (0.118, 0.135, 0.125), 'Paint', T_HELM, seg=16, rings=10)
    P_sphere(head, hc + V(0, 0.045, -0.012), (0.1, 0.1, 0.075), 'Lens', T_W, seg=14, rings=8)
    P_box(head, hc + V(0, 0.095, -0.085), (0.09, 0.07, 0.07), 'Paint', T_BLACK, 0.02)
    for s in (-1, 1):
        P_cyl(head, hc + V(s * 0.1, 0.0, -0.03), hc + V(s * 0.128, 0.0, -0.03), 0.05, 'Paint', T_HELM, seg=10)
    P_cyl(head, hc + V(-0.11, 0.02, -0.06), hc + V(-0.05, 0.12, -0.09), 0.006, 'Paint', T_BLACK, seg=5)
    P_cyl(head, hc + V(0.04, 0.12, -0.11), h + V(0.1, 0.1, 0.4), 0.014, 'Paint', T_BLACK, seg=6)   # oxygen hose


def build_cockpit():
    mb = MB()
    # ---------- pilot station (rear)
    seat(mb, 1.6, 0.12)
    # bulkhead / armour between cockpits + panel support
    P_box(mb, V(0, 2.98, 0.0), (0.9, 0.5, 0.72), 'Paint', T_INT, 0.02)
    P_box(mb, V(0, 3.0, 0.42), (0.6, 0.4, 0.2), 'Paint', T_INT, 0.03)
    # panel board + glareshield
    pbox(mb, 0, 0, -0.016, 0.9, 0.39, 0.03, 'Paint', T_INT2, 0.006)
    pbox(mb, 0, 0.215, 0.05, 0.94, 0.03, 0.2, 'Paint', T_BLACK, 0.008)
    for s in (-1, 1):
        pbox(mb, s * 0.455, 0.1, 0.04, 0.025, 0.22, 0.15, 'Paint', T_BLACK, 0.006)
    # MFD bezels + keys
    for s, nm in ((-1, 'MFD_L'), (1, 'MFD_R')):
        u0 = s * 0.285; v0 = 0.015
        for (du, dv, su, sv) in ((0, 0.108, 0.24, 0.02), (0, -0.108, 0.24, 0.02), (-0.11, 0, 0.02, 0.2), (0.11, 0, 0.02, 0.2)):
            pbox(mb, u0 + du, v0 + dv, 0.006, su, sv, 0.012, 'Paint', T_BLACK, 0.003)
        for k in range(5):
            pbox(mb, u0 - 0.075 + k * 0.0375, v0 + 0.108, 0.013, 0.022, 0.01, 0.004, 'Paint', T_INT2, 0.001)
            pbox(mb, u0 - 0.075 + k * 0.0375, v0 - 0.108, 0.013, 0.022, 0.01, 0.004, 'Paint', T_INT2, 0.001)
            pbox(mb, u0 - 0.11, v0 - 0.07 + k * 0.035, 0.013, 0.01, 0.02, 0.004, 'Paint', T_INT2, 0.001)
            pbox(mb, u0 + 0.11, v0 - 0.07 + k * 0.035, 0.013, 0.01, 0.02, 0.004, 'Paint', T_INT2, 0.001)
        q = MB()
        ids = [q.addv(pl(u0 + a, v0 + b, 0.002), T_W) for a, b in ((-0.098, -0.098), (0.098, -0.098), (0.098, 0.098), (-0.098, 0.098))]
        q.addf(ids, nm, [(0, 0), (1, 0), (1, 1), (0, 1)])
        build(q, nm, origin=pl(u0, v0, 0.002), rot=RP, parent='Cockpit_')
    # gauges
    G = {'Needle_Speed': (-0.1, 0.105), 'Needle_Alt': (0.1, 0.105), 'Needle_VS': (-0.1, 0.005), 'Needle_RPM': (0.1, 0.005),
         'Needle_Torque': (-0.1, -0.095), 'Needle_Temp': (0.0, -0.095)}
    gauge(mb, *G['Needle_Speed'], 'KTS', ['0', '4', '8', '12', '16', '20'])
    gauge(mb, *G['Needle_Alt'], 'ALT', ['0', '1', '2', '3', '4', '5'])
    gauge(mb, *G['Needle_VS'], 'VS', ['-2', '-1', '0', '1', '2'])
    gauge(mb, *G['Needle_RPM'], 'RPM', ['0', '2', '4', '6', '8', '10'])
    gauge(mb, *G['Needle_Torque'], 'TQ', ['0', '2', '4', '6', '8', '10'])
    gauge(mb, *G['Needle_Temp'], 'TEMP', ['0', '2', '4', '6', '8'])
    gauge(mb, 0.0, 0.005, None, ['N', 'E', 'S', 'W'], full=True)
    gauge(mb, 0.1, -0.095, 'FUEL', ['E', '', '', '', 'F'])
    pbox(mb, 0.1 + 0.012, -0.095 + 0.012, 0.0045, 0.002, 0.03, 0.001, 'GaugeMark', T_W, ang=rad(45))
    pbox(mb, 0.0, 0.005 + 0.012, 0.0045, 0.006, 0.03, 0.001, 'GaugeMark', T_W)
    # red-line arcs on torque / temp
    for nm in ('Needle_Torque', 'Needle_Temp', 'Needle_RPM'):
        u, v = G[nm]
        for k in range(6):
            a = rad(100 + k * 7)
            pbox(mb, u + 0.0415 * sin(a), v + 0.0415 * cos(a), 0.0026, 0.006, 0.0025, 0.001, 'Paint', T_RED, ang=a)
    # attitude indicator housing + aircraft symbol
    hu, hv = 0.0, 0.105
    nrm = RP @ V(0, -1, 0)
    P_torus(mb, pl(hu, hv, 0.004), nrm, 0.046, 0.006, 'Metal', T_GUN, seg=24, rseg=6)
    pbox(mb, hu - 0.02, hv, 0.012, 0.018, 0.003, 0.001, 'Paint', T_YEL)
    pbox(mb, hu + 0.02, hv, 0.012, 0.018, 0.003, 0.001, 'Paint', T_YEL)
    pbox(mb, hu, hv, 0.012, 0.004, 0.004, 0.001, 'Paint', T_YEL)
    P_revolve(mb, pl(hu, hv, -0.05), nrm, [(0, 0.05), (0.045, 0.05)], 'Paint', T_BLACK, seg=20, cap1=False, flip=True)
    # warning lamp labels
    W = {'Warn_Master': (-0.345, 0.155, 0.07, 'MASTER'), 'Warn_Engine': (-0.25, 0.155, 0.058, 'ENG'),
         'Warn_Tail': (0.215, 0.155, 0.058, 'TAIL'), 'Warn_Hyd': (0.285, 0.155, 0.058, 'HYD'), 'Warn_Rotor': (0.355, 0.155, 0.058, 'ROTOR')}
    for nm, (u, v, w, lab) in W.items():
        ptext(mb, lab, 0.011, u, v, 0.0078, mat='Paint', tint=T_BLACK)
        pbox(mb, u, v, 0.001, w + 0.008, 0.036, 0.004, 'Paint', T_BLACK, 0.001)
    # misc panel labels + switches below gauges
    for k in range(7):
        pbox(mb, -0.14 + k * 0.035 + 0.035, -0.165, 0.008, 0.008, 0.016, 0.014, 'Metal', T_STEEL, 0.002)
    ptext(mb, 'ARM', 0.008, -0.2, -0.165, 0.002)
    ptext(mb, 'SAFE', 0.008, 0.2, -0.165, 0.002)
    pbox(mb, -0.25, -0.165, 0.006, 0.03, 0.02, 0.01, 'Paint', T_RED, 0.003)
    pbox(mb, 0.25, -0.165, 0.006, 0.03, 0.02, 0.01, 'Paint', T_YEL, 0.003)
    # side consoles
    for s in (-1, 1):
        P_box(mb, V(s * 0.37, 2.08, 0.05), (0.2, 1.0, 0.36), 'Paint', T_INT, 0.015)
        P_box(mb, V(s * 0.37, 2.08, 0.232), (0.17, 0.94, 0.006), 'Paint', T_BLACK)
        for i in range(8):
            for k in range(3):
                p = V(s * (0.32 + k * 0.05), 1.72 + i * 0.1, 0.24)
                if (i + k) % 3 == 0:
                    P_cyl(mb, p, p + V(0, 0, 0.018), 0.012, 'Paint', T_INT2, seg=8)
                else:
                    P_box(mb, p + V(0, 0, 0.006), (0.008, 0.008, 0.022), 'Metal', T_STEEL, rot=Matrix.Rotation(rad(15 if (i * 3 + k) % 2 else -15), 3, 'X'))
            P_box(mb, V(s * 0.37, 1.77 + i * 0.1, 0.2355), (0.13, 0.004, 0.001), 'GaugeMark', T_W)
    # throttle quadrant (left console)
    P_box(mb, V(-0.37, 2.42, 0.25), (0.12, 0.16, 0.05), 'Paint', T_INT2, 0.008)
    for dx in (-0.025, 0.025):
        P_cyl(mb, V(-0.37 + dx, 2.42, 0.25), V(-0.37 + dx, 2.46, 0.34), 0.008, 'Metal', T_STEEL, seg=6)
        P_box(mb, V(-0.37 + dx, 2.46, 0.345), (0.03, 0.03, 0.03), 'Paint', T_RED if dx < 0 else T_YEL, 0.008)
    # pedals
    for s in (-1, 1):
        P_box(mb, V(s * 0.13, 2.76, -0.12), (0.1, 0.02, 0.14), 'Metal', T_GUN, 0.006, rot=Matrix.Rotation(rad(-20), 3, 'X'))
        P_cyl(mb, V(s * 0.13, 2.78, -0.18), V(s * 0.13, 2.74, -0.3), 0.012, 'Metal', T_GUN, seg=6)
    # HUD mount arms
    for s in (-1, 1):
        P_cyl(mb, pl(s * 0.09, 0.225, 0.1), V(s * 0.09, 2.52, 0.845), 0.006, 'Metal', T_GUN, seg=6)
    P_box(mb, V(0, 2.5, 0.84), (0.2, 0.02, 0.012), 'Metal', T_GUN, 0.003)
    P_box(mb, V(0, 2.6, 0.775), (0.1, 0.08, 0.05), 'Paint', T_BLACK, 0.01)     # projector
    # standby compass on canopy frame + grab handle
    P_box(mb, V(0, 2.5, 1.2), (0.06, 0.05, 0.045), 'Paint', T_BLACK, 0.01)
    # fire extinguisher, map case
    P_cyl(mb, V(0.4, 1.52, -0.2), V(0.4, 1.52, 0.02), 0.045, 'Paint', T_RED, seg=10)
    # ---------- gunner station (front)
    seat(mb, 3.38, -0.30)
    GP_ = V(0, 4.32, 0.02); GR = Matrix.Rotation(rad(-20), 3, 'X') @ Matrix.Identity(3)
    GR = Matrix(((1, 0, 0), (0, cos(rad(20)), sin(rad(20))), (0, -sin(rad(20)), cos(rad(20)))))
    pbox(mb, 0, 0, -0.016, 0.74, 0.3, 0.03, 'Paint', T_INT2, 0.006, P=GP_, R=GR)
    pbox(mb, 0, 0.165, 0.05, 0.78, 0.03, 0.16, 'Paint', T_BLACK, 0.008, P=GP_, R=GR)
    for s in (-1, 1):   # gunner screens (static)
        pbox(mb, s * 0.23, 0.0, 0.004, 0.2, 0.2, 0.01, 'Paint', T_BLACK, 0.003, P=GP_, R=GR)
        pbox(mb, s * 0.23, 0.0, 0.0095, 0.17, 0.17, 0.001, 'Lens', T_W, P=GP_, R=GR)
    gauge(mb, 0, 0.07, None, ['N', 'E', 'S', 'W'], full=True, r=0.04, P=GP_, R=GR)
    gauge(mb, 0, -0.06, 'KTS', ['0', '4', '8', '12', '16', '20'], r=0.04, P=GP_, R=GR)
    # sight eyepiece hood
    P_cyl(mb, V(0, 4.3, 0.2), V(0, 4.0, 0.36), 0.05, 'Paint', T_BLACK, r1=0.065, seg=12)
    P_box(mb, V(0, 4.36, 0.2), (0.2, 0.16, 0.16), 'Paint', T_INT, 0.02)
    for s in (-1, 1):    # hand grips
        P_cyl(mb, V(s * 0.15, 4.2, -0.02), V(s * 0.15, 4.1, 0.08), 0.02, 'Paint', T_BLACK, seg=8)
        P_cyl(mb, V(s * 0.15, 4.2, -0.02), V(s * 0.1, 4.33, -0.02), 0.012, 'Metal', T_GUN, seg=6)
        P_box(mb, V(s * 0.36, 3.85, -0.3), (0.18, 0.8, 0.3), 'Paint', T_INT, 0.015)
        for i in range(5):
            P_box(mb, V(s * 0.36, 3.55 + i * 0.12, -0.146), (0.12, 0.004, 0.001), 'GaugeMark', T_W)
            P_box(mb, V(s * 0.36, 3.6 + i * 0.12, -0.14), (0.008, 0.008, 0.02), 'Metal', T_STEEL)
    for s in (-1, 1):
        for (ya, yb, th_, w_) in ((1.7, 2.5, 96, 0.16), (3.4, 4.2, 100, 0.14)):
            yy = list(np.arange(ya, yb + 0.01, 0.1)); th = rad(th_) * s
            pts = [spi(y, th, 0.037) for y in yy]; nr = [-sn(y, th) for y in yy]
            P_sweep(mb, pts, nr, w_, 0.014, 0.0, 'Paint', T_INT2)
            for k, y in enumerate(yy[1:-1]):
                p = spi(y, th, 0.052)
                P_box(mb, p + V(0, 0, 0.03), (0.012, 0.03, 0.02), 'Paint', T_BLACK if k % 3 else T_YEL, 0.003)
                P_box(mb, p + V(0, 0, -0.03), (0.012, 0.05, 0.004), 'GaugeMark', T_W)
        # canopy jettison handle (striped)
        p = spi(2.3, rad(80) * s, 0.06)
        P_box(mb, p, (0.03, 0.14, 0.03), 'Paint', T_YEL, 0.008)
        for k in range(3):
            P_box(mb, p + V(0, -0.045 + k * 0.045, 0), (0.032, 0.015, 0.032), 'Paint', T_BLACK)
    build(mb, 'Cockpit', parent='Body')

    # needles
    for nm, (u, v) in G.items():
        needle(nm, u, v, 'Cockpit')
    # warning lamps
    for nm, (u, v, w, lab) in W.items():
        q = MB()
        pbox(q, u, v, 0.005, w, 0.028, 0.005, nm, T_W, 0.0015)
        build(q, nm, origin=pl(u, v, 0.005), rot=RP, parent='Cockpit')
    # horizon ball
    hb = MB()
    c = pl(hu, hv, -0.014)
    up = RP @ V(0, 0, 1)
    R0 = 0.042
    def lat(a): return (R0 * sin(a) + R0, R0 * cos(a))     # distance along up from south pole, radius
    sky = (0.12, 0.33, 0.8); gnd = (0.22, 0.11, 0.04)
    south = c - up * R0
    P_revolve(hb, south, up, [lat(rad(a)) for a in range(-90, -1, 11)] + [lat(rad(-2))], 'Paint', gnd, seg=20, cap0=False, cap1=False)
    P_revolve(hb, south, up, [lat(rad(-2)), lat(rad(2))], 'Paint', (0.9, 0.9, 0.9), seg=20, cap0=False, cap1=False)
    P_revolve(hb, south, up, [lat(rad(2))] + [lat(rad(a)) for a in range(13, 91, 11)], 'Paint', sky, seg=20, cap0=False, cap1=False)
    for a in (-40, -20, 20, 40):    # pitch ladder rings
        P_revolve(hb, south, up, [lat(rad(a - 0.6)), lat(rad(a + 0.6))], 'Paint', (0.9, 0.9, 0.9), seg=20, cap0=False, cap1=False)
    build(hb, 'Horizon', origin=c, rot=RP, parent='Cockpit')
    # controls
    cy = MB()
    pv = V(0, 2.22, -0.29)
    P_cyl(cy, pv, pv + V(0, -0.03, 0.3), 0.014, 'Metal', T_GUN, seg=8)
    P_cyl(cy, pv + V(0, -0.03, 0.3), pv + V(0, -0.09, 0.5), 0.014, 'Metal', T_GUN, seg=8)
    P_cyl(cy, pv + V(0, -0.09, 0.48), pv + V(0, -0.11, 0.62), 0.024, 'Paint', T_BLACK, r1=0.028, seg=10)
    P_box(cy, pv + V(0, -0.1, 0.63), (0.05, 0.06, 0.04), 'Paint', T_BLACK, 0.012)
    P_cyl(cy, pv + V(0.02, -0.08, 0.64), pv + V(0.02, -0.08, 0.665), 0.007, 'Paint', T_RED, seg=6)
    P_revolve(cy, pv, V(0, 0, 1), [(0, 0.05), (0.06, 0.02)], 'Paint', T_BLACK, seg=10)      # boot
    build(cy, 'Cyclic', origin=pv, parent='Cockpit')
    co = MB()
    pv2 = V(-0.3, 1.74, 0.02)
    tipc = pv2 + V(0, 0.36, 0.2)
    P_cyl(co, pv2, tipc, 0.016, 'Metal', T_GUN, seg=8)
    P_cyl(co, tipc + (tipc - pv2).normalized() * -0.12, tipc + (tipc - pv2).normalized() * 0.03, 0.026, 'Paint', T_BLACK, seg=10)
    P_box(co, tipc + V(0, 0.03, 0.03), (0.05, 0.05, 0.06), 'Paint', T_INT2, 0.01)
    build(co, 'Collective', origin=pv2, parent='Cockpit')
    # HUD combiner
    hg = MB()
    Rg = Matrix.Rotation(rad(-18), 3, 'X')
    cgl = V(0, 2.5, 0.915)
    ids = [hg.addv(cgl + Rg @ V(a, 0, b), T_W) for a, b in ((-0.085, -0.07), (0.085, -0.07), (0.085, 0.07), (-0.085, 0.07))]
    hg.addf(ids, 'Glass', [(0, 0), (1, 0), (1, 1), (0, 1)])
    build(hg, 'HUDGlass', origin=cgl, parent='Cockpit')
    # crew
    pb = MB(); ph = MB()
    figure(pb, ph, V(0, 1.72, 0.2), (tipc + V(0, 0.0, 0.03), pv + V(0, -0.1, 0.57)))
    build(pb, 'Pilot', parent='Cockpit')
    build(ph, 'PilotHead', parent='Pilot')
    gb = MB()
    figure(gb, gb, V(0, 3.5, -0.22), (V(-0.15, 4.12, 0.06), V(0.15, 4.12, 0.06)))
    build(gb, 'Gunner', parent='Cockpit')
    empty('PilotEye', EYE, 'Body')
    empty('GunnerEye', V(0, 3.69, 0.5), 'Body')


