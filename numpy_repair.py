"""Mesh repair with numpy only – the method used by vault_stl_repair.py on macOS and Linux (`--method numpy`;
it works on Windows too). English version of tools/napraw_numpy.py from the VAULT configurator – same algorithm.

Defects of the VAULT (USSA) files: pairs of duplicated faces with opposite orientation (zero-thickness walls), flat
zero-height triangles (in layers), slits with T-junctions, a few real holes, flaps lying on or sticking out of
another surface, inside-out shells. Steps: cleaning -> stitching slits -> closing holes -> removing flaps ->
splitting non-manifold edges -> orientation.
Input/output: float64 vertices (n, 3), int64 triangles (m, 3) with indices.

Part of the unofficial VAULT configurator (https://github.com/rawel2/Vault-Konfigurator-wydania).
Authors: rawel2 and Claude (Anthropic). MIT licence. VAULT and its STL files © USSA Design.
"""
import numpy as np

TOL = 1e-3  # mm – the USSA files lie up to 7.5 m from the origin, where float32 has a step of about 0.0005 mm


# ---------- tools ----------
def components(n, u, v):
    """Connected component labels of a graph (n nodes, edges u–v): root hooking + path shortening."""
    lab = np.arange(n)
    if not len(u):
        return lab
    while True:
        lu, lv = lab[u], lab[v]
        m = np.minimum(lu, lv)
        new = lab.copy()
        np.minimum.at(new, lu, m)
        np.minimum.at(new, lv, m)
        while True:
            nn = new[new]
            if np.array_equal(nn, new):
                break
            new = nn
        if np.array_equal(new, lab):
            return lab
        lab = new


def half_edges(f):
    """Half-edges h = 3·face + corner: a -> b. Undirected key and the number of faces at every edge."""
    a = f.ravel()
    b = f[:, [1, 2, 0]].ravel()
    n = int(f.max()) + 1 if len(f) else 1
    k = np.minimum(a, b) * n + np.maximum(a, b)
    _, inv, cnt = np.unique(k, return_inverse=True, return_counts=True)
    return a, b, inv.ravel(), cnt


def errors(f):
    """(open, non-manifold) edges counted by indices."""
    if not len(f):
        return 0, 0
    _, _, _, cnt = half_edges(f)
    return int((cnt == 1).sum()), int((cnt > 2).sum())


def drop_unused(w, f):
    used, inv = np.unique(f.ravel(), return_inverse=True)
    return w[used], inv.reshape(-1, 3)


# ---------- 1. cleaning ----------
def clean_faces(w, f):
    """Degenerate triangles (by index) removed; duplicated faces: pairs of opposite orientation cancel out,
    of the rest in one orientation one is kept."""
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
    _, inv, cnt = np.unique(np.sort(f, axis=1), axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    r = np.argmin(f, axis=1)
    i = np.arange(len(f))
    sign = np.where(f[i, (r + 1) % 3] < f[i, (r + 2) % 3], 1, -1)
    total = np.bincount(inv, sign)
    many = cnt[inv] > 1
    candidate = many & (np.sign(total[inv]) == sign)
    keep = ~many
    ki = np.nonzero(candidate)[0]
    _, first = np.unique(inv[ki], return_index=True)
    keep[ki[first]] = True
    return f[keep], int(len(f) - keep.sum())


def flat(w, f, tol=TOL):
    """Mask of triangles with height < tol (flat, zero thickness)."""
    v = w[f]
    e = np.stack([v[:, 1] - v[:, 0], v[:, 2] - v[:, 1], v[:, 0] - v[:, 2]], 1)
    length = np.linalg.norm(e, axis=2).max(1)
    area2 = np.linalg.norm(np.cross(e[:, 0], -e[:, 2]), axis=1)
    return area2 < tol * np.maximum(length, tol)


def at_defects(f):
    """Mask of faces that have an open or non-manifold edge."""
    _, _, inv, cnt = half_edges(f)
    return (cnt[inv] != 2).reshape(-1, 3).any(1)


def weld_border(w, f, tol=TOL):
    """Vertices of open and non-manifold edges closer than tol are merged (needle slits whose ends almost
    coincide). The rest of the mesh is unchanged."""
    a, b, inv, cnt = half_edges(f)
    bad = cnt[inv] != 2
    bv = np.unique(np.r_[a[bad], b[bad]])
    if len(bv) < 2:
        return f, 0
    remap = np.arange(len(w))
    for shift in (0.0, 0.5):  # two grids shifted by half a cell – pairs on the cell border
        q = np.floor(w[bv] / tol + shift).astype(np.int64)
        _, first, group = np.unique(q, axis=0, return_index=True, return_inverse=True)
        target = bv[first][group.ravel()]
        remap[bv] = remap[target]
    remap = remap[remap]
    n = int((remap[bv] != bv).sum())
    return remap[f], n


def drop_flat(w, f, tol=TOL):
    """Flat triangles at defects removed – they leave slits that stitch() closes. Only at defects: elsewhere small
    flat fans (arcs) are a valid part of the mesh."""
    m = flat(w, f, tol) & at_defects(f)
    return f[~m], int(m.sum())


# ---------- 2. stitching slits (T-junctions) ----------
def stitch(w, f, tol=TOL, passes=60):
    """Border edge p->q with another border vertex v on it (<= tol from the segment, inside): face (p, q, r) is split
    into (p, v, r) and (v, q, r). After the split p->v and v->q connect to the edges on the other side of the slit."""
    total = 0
    for _ in range(passes):
        a, b, inv, cnt = half_edges(f)
        br = np.nonzero(cnt[inv] == 1)[0]
        if not len(br):
            break
        pv = np.unique(np.r_[a[br], b[br]])
        # the other side of the slit must run in the opposite direction: a border edge v -> y leaves v
        leaving = dict(zip(a[br].tolist(), b[br].tolist()))
        # border components – candidates are searched only in the same loop
        idx = {x: i for i, x in enumerate(pv.tolist())}
        lu = np.array([idx[x] for x in a[br].tolist()])
        lv = np.array([idx[x] for x in b[br].tolist()])
        lab = components(len(pv), lu, lv)
        split = {}
        for c in np.unique(lab):
            verts = pv[lab == c]
            edges = br[lab[lu] == c]
            if len(verts) > 3000:
                continue  # very long border – left to hole closing
            P, Q, X = w[a[edges]][:, None], w[b[edges]][:, None], w[verts][None]
            d = Q - P
            dd = np.maximum((d * d).sum(2), 1e-30)
            t = ((X - P) * d).sum(2) / dd
            dist = np.linalg.norm(P + t[..., None] * d - X, axis=2)
            ok = (t > 1e-6) & (t < 1 - 1e-6) & (dist < tol)
            ok &= (verts[None] != a[edges][:, None]) & (verts[None] != b[edges][:, None])
            for i in np.nonzero(ok.any(1))[0]:
                j = np.nonzero(ok[i])[0]
                # only a v whose border runs towards p (opposite to p -> q) – otherwise it is the other side of a wall
                dq = w[b[edges[i]]] - w[a[edges[i]]]
                j = [x for x in j if int(verts[x]) in leaving
                     and (w[leaving[int(verts[x])]] - w[verts[x]]) @ dq < 0]
                if not j:
                    continue
                j = min(j, key=lambda x: t[i, x])  # nearest to p – further splits in the next passes
                h = edges[i]
                if h // 3 not in split:
                    split[h // 3] = (h % 3, int(verts[j]))
        if not split:
            break
        ts = np.array(list(split))
        corner = np.array([split[t][0] for t in ts])
        vv = np.array([split[t][1] for t in ts])
        p, q, r = f[ts, corner], f[ts, (corner + 1) % 3], f[ts, (corner + 2) % 3]
        f = f.copy()
        f[ts] = np.stack([p, vv, r], 1)
        f = np.vstack([f, np.stack([vv, q, r], 1)])
        total += len(ts)
    return f, total


# ---------- 3. closing holes ----------
def border_loops(f):
    """Loops of border edges in the direction of the hole (opposite to the faces)."""
    a, b, inv, cnt = half_edges(f)
    br = np.nonzero(cnt[inv] == 1)[0]
    out = {}
    for h in br.tolist():
        out.setdefault(int(b[h]), []).append(int(a[h]))  # hole: b -> a
    loops = []
    while out:
        s = next(iter(out))
        loop, x = [s], s
        while True:
            lst = out.get(x)
            if not lst:
                break
            y = lst.pop()
            if not lst:
                del out[x]
            if y == s:
                break
            loop.append(y)
            x = y
        if len(loop) >= 3:
            loops.append(loop)
    return loops


def close_holes(w, f, limit=5000):
    """Every border loop triangulated by the shortest diagonal (the ear with the shortest new edge)."""
    new = []
    closed = 0
    for loop in border_loops(f):
        if len(loop) > limit:
            continue
        p = list(loop)
        while len(p) > 3:
            P = w[p]
            length = np.linalg.norm(np.roll(P, 1, 0) - np.roll(P, -1, 0), axis=1)
            i = int(np.argmin(length))
            new.append([p[i - 1], p[i], p[(i + 1) % len(p)]])
            del p[i]
        new.append(p)
        closed += 1
    if new:
        f = np.vstack([f, np.array(new, np.int64)])
    return f, closed


# ---------- 4. non-manifold edges ----------
def links(w, f, forced=None):
    """Pairs of adjacent faces (t1, t2, u, v). Edge with 2 faces – plain adjacency; with 3+ faces – faces sorted by
    angle around the edge and joined in pairs of neighbours with opposite directions (solid between them),
    unless `forced` ({(u, v): [(t1, t2), ...]}) gives the pairs for this edge."""
    a, b, inv, cnt = half_edges(f)
    order = np.argsort(inv, kind="stable")
    ks = inv[order]
    gr = np.r_[0, np.nonzero(ks[1:] != ks[:-1])[0] + 1, len(ks)]
    il = np.diff(gr)
    e1 = order[gr[:-1][il == 2]]
    e2 = order[gr[:-1][il == 2] + 1]
    result = [np.stack([e1 // 3, e2 // 3, np.minimum(a[e1], b[e1]), np.maximum(a[e1], b[e1])], 1)]
    for s, c in zip(gr[:-1][il > 2].tolist(), il[il > 2].tolist()):
        es = order[s:s + c]
        u, v = int(min(a[es[0]], b[es[0]])), int(max(a[es[0]], b[es[0]]))
        if forced and (u, v) in forced:
            result.append(np.array([[t1, t2, u, v] for t1, t2 in forced[(u, v)]]))
            continue
        d = w[v] - w[u]
        d = d / (np.linalg.norm(d) or 1.0)
        tr = f[es // 3]
        third = tr[(tr != u) & (tr != v)]
        if len(third) != c:
            continue
        x = w[third] - w[u]
        x = x - np.outer(x @ d, d)
        e0 = x[0] / (np.linalg.norm(x[0]) or 1.0)
        angle = np.arctan2(x @ np.cross(d, e0), x @ e0)
        o = np.argsort(angle)
        es = es[o]
        fwd = a[es] == u
        for shift in (0, 1):
            pairs = [((i + shift) % c, (i + 1 + shift) % c) for i in range(0, c - 1, 2)]
            if all(fwd[p] != fwd[q] for p, q in pairs):
                break
        else:
            pairs = []
        if pairs:
            result.append(np.array([[es[p] // 3, es[q] // 3, u, v] for p, q in pairs]))
    return np.concatenate(result)


def fan_pairs(f, limit=200):
    """Pairs of faces at 3+ edges by the fans around their ends: two faces at edge u–v joined by the fan around u
    (through plain edges, without u–v) belong to one surface and form a pair. For edges where the angle does not
    decide – coplanar faces (L5 Module 1F: two surfaces touching along one edge; pairing by angle joins faces on the
    same side and the vertex is not split). Only when the fans around u and v give the same pairs.
    Returns {(u, v): [(t1, t2), ...]}."""
    a, b, inv, cnt = half_edges(f)
    bad = np.nonzero(cnt > 2)[0]
    if not len(bad) or len(bad) > limit:
        return {}
    hb = np.nonzero(cnt[inv] > 2)[0]
    faces = np.nonzero(np.isin(f, np.unique(np.r_[a[hb], b[hb]])).any(1))[0]

    def pairs_around(x, k, h):
        tx = faces[(f[faces] == x).any(1)]
        hx = (tx[:, None] * 3 + np.arange(3)).ravel()
        hx = hx[((a[hx] == x) | (b[hx] == x)) & (inv[hx] != k) & (cnt[inv[hx]] == 2)]
        o = np.argsort(inv[hx], kind="stable")
        hx = hx[o]
        p = np.nonzero(inv[hx][1:] == inv[hx][:-1])[0]
        idx = {int(t): i for i, t in enumerate(tx)}
        lab = components(len(tx), np.array([idx[int(t)] for t in hx[p] // 3], int),
                         np.array([idx[int(t)] for t in hx[p + 1] // 3], int))
        groups = {}
        for hh in h.tolist():
            groups.setdefault(int(lab[idx[hh // 3]]), []).append(hh)
        pairs = []
        for g in groups.values():
            if len(g) != 2 or a[g[0]] == a[g[1]]:
                return None
            pairs.append(tuple(sorted((g[0] // 3, g[1] // 3))))
        return sorted(pairs)

    result = {}
    for k in bad.tolist():
        h = hb[inv[hb] == k]
        u, v = int(min(a[h[0]], b[h[0]])), int(max(a[h[0]], b[h[0]]))
        pu = pairs_around(u, k, h)
        if pu and pu == pairs_around(v, k, h):
            result[(u, v)] = pu
    return result


def split_vertices(w, f, forced=None):
    """A vertex around which the faces form several separate fans (by the links through its edges) gets its own copy
    for every fan. Splits non-manifold edges and vertices."""
    lk = links(w, f, forced)
    nf = len(f)
    vv = np.concatenate([lk[:, 2], lk[:, 3]])
    t1 = np.concatenate([lk[:, 0], lk[:, 0]])
    t2 = np.concatenate([lk[:, 1], lk[:, 1]])
    g1 = t1 * 3 + np.argmax(f[t1] == vv[:, None], axis=1)
    g2 = t2 * 3 + np.argmax(f[t2] == vv[:, None], axis=1)
    lab = components(nf * 3, g1, g2)
    corner_v = f.ravel()
    pair = np.unique(np.stack([corner_v, lab], 1), axis=0)
    cnt = np.bincount(pair[:, 0], minlength=len(w))
    bad = np.nonzero(cnt > 1)[0]
    if not len(bad):
        return w, f, 0
    # every (vertex, fan) pair except the first gets a new vertex
    first = np.r_[True, pair[1:, 0] != pair[:-1, 0]]
    extra = pair[~first]
    new_id = len(w) + np.arange(len(extra))
    key = corner_v * (nf * 3) + lab
    ke = extra[:, 0] * (nf * 3) + extra[:, 1]
    pos = np.searchsorted(ke, key)
    pos[pos >= len(ke)] = 0
    hit = ke[pos] == key
    out = corner_v.copy()
    out[hit] = new_id[pos[hit]]
    return np.vstack([w, w[extra[:, 0]]]), out.reshape(-1, 3), len(bad)


def drop_flaps(f, limit=2000):
    """Flaps removed: a component of faces (joined by edges with 2 faces) whose border consists only of open and
    non-manifold edges – it lies on another surface or sticks out of it (Rounded Edge Piece: a patch on a flat
    bottom; M5 4F sustainer: a "fin" perpendicular to a wall; M4 2F: a second layer of a strip). split_vertices()
    cannot untangle them, because the faces around the edge are coplanar. Only flaps up to `limit` faces whose
    removal lowers the number of bad edges are removed."""
    nf = len(f)
    a, b, inv, cnt = half_edges(f)
    order = np.argsort(inv, kind="stable")
    ks = inv[order]
    pair = np.nonzero((ks[1:] == ks[:-1]) & (cnt[ks[1:]] == 2))[0]
    comp = components(nf, order[pair] // 3, order[pair + 1] // 3)
    _, comp = np.unique(comp, return_inverse=True)
    comp = comp.ravel()
    cm = np.repeat(comp, 3)
    ie = cnt[inv]
    cand = (np.bincount(cm, ie == 1) > 0) & (np.bincount(cm, ie > 2) > 0) & (np.bincount(comp) <= limit)
    h = np.nonzero(cand[cm] & (ie != 2))[0]
    if not len(h):
        return f, 0
    # balance at the contact edges: an edge with c faces, k of them in the flap – bad before when c != 2,
    # after removal when c - k not in {0, 2}
    pairs, k = np.unique(np.stack([cm[h], inv[h]], 1), axis=0, return_counts=True)
    pc, c = pairs[:, 0], cnt[pairs[:, 1]]
    change = np.bincount(pc, ((c - k != 0) & (c - k != 2)).astype(int) - (c != 2), minlength=len(cand))
    gone = cand & (change < 0)
    if not gone.any():
        return f, 0
    new = f[~gone[comp]]
    if sum(errors(new)) >= sum(errors(f)):  # flaps sharing an edge can cancel out – then no change
        return f, 0
    return new, int(gone[comp].sum())


# ---------- 5. orientation ----------
def orient(w, f, skip_flat=False):
    """Consistent orientation in every shell (doubled graph: (face, flipped?) – the components decide the flips),
    then a shell with negative volume is flipped as a whole, unless it lies inside another one (a cavity).
    skip_flat: flat triangles do not pass the orientation on (their direction is often random – twisted slits)."""
    nf = len(f)
    a, b, inv, cnt = half_edges(f)
    order = np.argsort(inv, kind="stable")
    ks = inv[order]
    pair = np.nonzero((ks[1:] == ks[:-1]) & (cnt[ks[1:]] == 2))[0]
    h1, h2 = order[pair], order[pair + 1]
    t1, t2 = h1 // 3, h2 // 3
    if skip_flat:
        fl = flat(w, f)
        ok = ~fl[t1] & ~fl[t2]
        h1, h2, t1, t2 = h1[ok], h2[ok], t1[ok], t2[ok]
    same = a[h1] != a[h2]  # shared edge in opposite directions = the same orientation
    # node 2t = face unchanged, 2t+1 = flipped
    u = np.r_[2 * t1, 2 * t1 + 1]
    v = np.r_[np.where(same, 2 * t2, 2 * t2 + 1), np.where(same, 2 * t2 + 1, 2 * t2)]
    lab = components(2 * nf, u, v)
    l0, l1 = lab[0::2], lab[1::2]
    inconsistent = int((l0 == l1).sum())
    flip = l0 > l1  # in every pair of components the one with the lower label is chosen
    f = f.copy()
    f[flip] = f[flip][:, ::-1]
    # shells: components of face adjacency
    sh = components(nf, t1, t2)
    _, shell = np.unique(sh, return_inverse=True)
    shell = shell.ravel()
    k = int(shell.max()) + 1
    v3 = w[f]
    vol = np.bincount(shell, np.einsum("ij,ij->i", v3[:, 0], np.cross(v3[:, 1], v3[:, 2])) / 6.0, minlength=k)
    mn = np.full((k, 3), np.inf)
    mx = np.full((k, 3), -np.inf)
    np.minimum.at(mn, shell, v3.min(1))
    np.maximum.at(mx, shell, v3.max(1))
    to_flip = []
    if not skip_flat:  # in the first orientation (flat triangles apart – hundreds of thousands of "shells") consistency only
        positive = np.nonzero(vol > 1e-6)[0]
        for c in np.nonzero(vol < -1e-6)[0]:  # shells with a significant volume (flat shreds tell nothing about direction)
            if not (np.all(mn[positive] <= mn[c], 1) & np.all(mx[positive] >= mx[c], 1)).any():
                to_flip.append(c)
    if to_flip:
        m = np.isin(shell, to_flip)
        f[m] = f[m][:, ::-1]
    return f, int(flip.sum()), len(to_flip), inconsistent, k


def conflicting(f):
    """Faces at edges where the orientation cannot be agreed on (BFS over adjacency, inconsistent shells only).
    Returns a face mask."""
    from collections import deque
    nf = len(f)
    a, b, inv, cnt = half_edges(f)
    order = np.argsort(inv, kind="stable")
    ks = inv[order]
    pair = np.nonzero((ks[1:] == ks[:-1]) & (cnt[ks[1:]] == 2))[0]
    h1, h2 = order[pair], order[pair + 1]
    t1, t2 = h1 // 3, h2 // 3
    same = (a[h1] != a[h2]).astype(np.int8)
    # adjacency list (CSR)
    u = np.r_[t1, t2]
    v = np.r_[t2, t1]
    z = np.r_[same, same]
    o = np.argsort(u, kind="stable")
    u, v, z = u[o], v[o], z[o]
    start = np.searchsorted(u, np.arange(nf + 1))
    flip = np.full(nf, -1, np.int8)
    bad = np.zeros(nf, bool)
    vl, zl, sl = v.tolist(), z.tolist(), start.tolist()
    for s in range(nf):
        if flip[s] >= 0:
            continue
        flip[s] = 0
        q = deque([s])
        while q:
            x = q.popleft()
            fx = flip[x]
            for i in range(sl[x], sl[x + 1]):
                y = vl[i]
                expected = fx ^ (1 - zl[i])
                if flip[y] < 0:
                    flip[y] = expected
                    q.append(y)
                elif flip[y] != expected:
                    bad[x] = bad[y] = True
    return bad


def grow(f, mask, rings=2):
    """Mask grown by the faces sharing a vertex (rings times)."""
    for _ in range(rings):
        wv = np.zeros(int(f.max()) + 1, bool)
        wv[f[mask].ravel()] = True
        mask = wv[f].any(1)
    return mask


# ---------- whole ----------
def _rounds(w, f, log, nr0=0):
    for rnd in range(nr0, nr0 + 6):
        if errors(f) == (0, 0):
            break
        f, n = weld_border(w, f)
        f, n2 = clean_faces(w, f)
        log("  [%d] welding border: %d vertices, o/n %d/%d" % ((rnd + 1, n) + errors(f)))
        f, n = drop_flat(w, f)
        f, n2 = clean_faces(w, f)
        log("  [%d] flat triangles at defects: %d removed, o/n %d/%d" % ((rnd + 1, n) + errors(f)))
        f, n = stitch(w, f)
        f, n2 = clean_faces(w, f)
        log("  [%d] stitching slits: %d splits, o/n %d/%d" % ((rnd + 1, n) + errors(f)))
        f, n = close_holes(w, f)
        f, n2 = clean_faces(w, f)
        log("  [%d] closed holes: %d, o/n %d/%d" % ((rnd + 1, n) + errors(f)))
        f, n = drop_flaps(f)
        log("  [%d] flaps: %d faces removed, o/n %d/%d" % ((rnd + 1, n) + errors(f)))
        w, f, n = split_vertices(w, f)
        if not n and errors(f)[1]:  # the angle did not decide (coplanar faces) – pairs by fans
            w, f, n = split_vertices(w, f, fan_pairs(f))
        log("  [%d] split vertices: %d, o/n %d/%d" % ((rnd + 1, n) + errors(f)))
    return w, f


MAX_DEFECTS = 20000  # non-manifold edges after cleaning – above that: multi-layer surfaces (S6 1F/2F sustainer
                     # modules: about 65 thousand, the same wall stored up to 12 times with a different mesh), which this
                     # method does not untangle; S1F (Turn On Supports) 5.3 thousand and L3 Dividers Module 5.4–7.6
                     # thousand repair cleanly in 4–5 min


class TooManyDefects(Exception):
    pass


def repair(w, f, log=print):
    f, n = clean_faces(w, f)
    log("  cleaning: %d duplicated/degenerate faces removed, o/n %d/%d" % ((n,) + errors(f)))
    if errors(f)[1] > MAX_DEFECTS:
        raise TooManyDefects("%d non-manifold edges (multi-layer surfaces)" % errors(f)[1])
    # orientation already on the open mesh: the borders of holes and slits then run consistently (inside-out parts of
    # shells – S5 Roof – gave patches twisted like a Möbius strip)
    f, flipped, _, incons, _ = orient(w, f, skip_flat=True)
    f, n = clean_faces(w, f)
    log("  first orientation: %d faces flipped, inconsistent %d, o/n %d/%d" % ((flipped, incons) + errors(f)))
    w, f = _rounds(w, f, log)
    for attempt in range(3):
        f, flipped, flipped_sh, incons, k = orient(w, f)
        if not incons:
            break
        # twisted part (orientation cannot be agreed on): the area around the conflicting edges cut out and patched again
        bad = grow(f, conflicting(f), 2)
        f = f[~bad]
        log("  twisted part: %d faces cut out, o/n %d/%d" % ((int(bad.sum()),) + errors(f)))
        w, f = _rounds(w, f, log, nr0=10 * (attempt + 1))
    for attempt in range(3):
        if errors(f) == (0, 0) or sum(errors(f)) > 200:
            break
        # leftovers the rounds do not fix (a knot of several edges at one vertex – L5 Module 1F, a flat patch in a
        # narrow slit removed and added again in a loop): the area cut out and patched from scratch
        bad = grow(f, at_defects(f), attempt + 1)
        f = f[~bad]
        log("  leftover defects: %d faces cut out, o/n %d/%d" % ((int(bad.sum()),) + errors(f)))
        w, f = _rounds(w, f, log, nr0=40 + 10 * attempt)
    f, flipped, flipped_sh, incons, k = orient(w, f)
    log("  orientation: %d faces flipped, %d shells inside out (of %d), inconsistent %d" % (flipped, flipped_sh, k, incons))
    w, f = drop_unused(w, f)
    return w, f
