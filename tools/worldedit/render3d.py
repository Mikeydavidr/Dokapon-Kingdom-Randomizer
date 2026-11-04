"""A perspective renderer for the board art, close to the game's tilted camera: depth buffer, texture, vertex colour, alpha.

usage: python render3d.py <out.png> [--dir <Assets folder>] [--at x,z] [--tilt 50] [--dist 220] [--fov 45] [--size 640x400]
As a module: Scene.load(folder) once (cached), then Scene.render(target, ...) per view. Used by views.py to compare two boards.
Not the game's renderer: no fog, lighting or water animation, and texels with alpha under 0.5 are cut out. It is faithful in what
matters for finding oddities: where geometry is, how high, and what texture lies on it.
"""
import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "igb"), str(HERE.parent / "boardview")]
import render_top as rt

SKY = (0.12, 0.25, 0.45)


def _split(P, UV, C, T, longest: float = 120.0):
    """Cut triangles with an edge over `longest` into four (midpoints), until none is: the sea plane is a few huge triangles,
    and one with a corner behind the camera would be dropped whole."""
    while True:
        edge = np.max([np.linalg.norm(P[:, i] - P[:, (i + 1) % 3], axis=1) for i in range(3)], axis=0)
        big = edge > longest
        if not big.any():
            return P, UV, C, T
        keep = ~big
        p, uv, c, t = P[big], UV[big], C[big], T[big]
        m = lambda a: np.stack([(a[:, 0] + a[:, 1]) / 2, (a[:, 1] + a[:, 2]) / 2, (a[:, 2] + a[:, 0]) / 2], 1)
        outs = []
        for a in (p, uv, c):
            mid = m(a)
            outs.append(np.concatenate([np.stack([a[:, 0], mid[:, 0], mid[:, 2]], 1), np.stack([mid[:, 0], a[:, 1], mid[:, 1]], 1),
                                        np.stack([mid[:, 2], mid[:, 1], a[:, 2]], 1), mid]))
        P = np.concatenate([P[keep], outs[0]])
        UV = np.concatenate([UV[keep], outs[1]])
        C = np.concatenate([C[keep], outs[2]])
        T = np.concatenate([T[keep], np.tile(t, 4)])


class Scene:
    def __init__(self, P, UV, C, T, textures):
        self.P, self.UV, self.C, self.T, self.textures = P, UV, C, T, textures
        self.lo, self.hi = P.min(1), P.max(1)                      # per-triangle bounding boxes, for culling

    @classmethod
    def load(cls, folder: Path | None, cache: Path | None = None) -> "Scene":
        if cache and cache.exists():
            with cache.open("rb") as f:
                return cls(*pickle.load(f))
        P, UV, C, T, textures, seen = [], [], [], [], [], {}
        for f in rt.FILES:
            name = f"F00_{f}.model"
            path = folder / name if folder and (folder / name).exists() else rt.F00 / name
            for xz, _, uv, col, tex, ys in rt.triangles(path, None):
                k = id(tex)
                if k not in seen:
                    seen[k] = len(textures)
                    textures.append(tex)
                P.append(np.stack([xz[:, 0], ys, xz[:, 1]], 1))
                UV.append(uv)
                C.append(col)
                T.append(seen[k])
        data = (*_split(np.array(P, np.float32), np.array(UV, np.float32), np.array(C, np.float32), np.array(T, np.int32)), textures)
        if cache:
            with cache.open("wb") as f:
                pickle.dump(data, f, protocol=4)
        return cls(*data)

    def render(self, target, tilt=50.0, dist=220.0, fov=45.0, size=(640, 400), yaw=0.0) -> np.ndarray:
        """The picture (h, w, 3 floats) looking at `target` (x, y, z) from `dist` units away, `tilt` degrees down from the
        horizontal, towards +z (the game's way) turned by `yaw` degrees."""
        W, H = size
        t, yw = np.radians(tilt), np.radians(yaw)
        fwd = np.array([np.sin(yw) * np.cos(t), -np.sin(t), np.cos(yw) * np.cos(t)])
        cam = np.asarray(target, float) - fwd * dist
        right = np.cross(fwd, [0, 1, 0]); right /= np.linalg.norm(right)       # +x is on the left, as in the game's picture
        up = np.cross(right, fwd)
        foc = (H / 2) / np.tan(np.radians(fov) / 2)
        # triangles near the view: a box generous enough around the target for the far end of the picture
        reach = dist * 2.2
        near = ((self.hi[:, 0] > target[0] - reach) & (self.lo[:, 0] < target[0] + reach) & (self.hi[:, 2] > target[2] - reach)
                & (self.lo[:, 2] < target[2] + reach)).nonzero()[0]
        if not len(near):
            return np.full((H, W, 3), SKY, np.float32)
        P = self.P[near].astype(np.float64) - cam
        X, Y, Z = P @ right, P @ up, P @ fwd
        ok = (Z > 4).all(1)
        near, X, Y, Z = near[ok], X[ok], Y[ok], Z[ok]
        sx, sy = W / 2 + foc * X / Z, H / 2 - foc * Y / Z
        vis = ~(((sx < 0).all(1)) | ((sx > W).all(1)) | ((sy < 0).all(1)) | ((sy > H).all(1)))
        near, sx, sy, Z = near[vis], sx[vis], sy[vis], Z[vis]
        # screen-space area sign culls nothing (the game draws both sides of most pieces); far to near for blending
        order = np.argsort(-Z.mean(1))
        img = np.empty((H, W, 3), np.float32)
        img[:] = SKY
        zb = np.full((H, W), 1e9, np.float32)
        for n in order:
            ti = near[n]
            ax, ay, bx, by, cx, cy = sx[n, 0], sy[n, 0], sx[n, 1], sy[n, 1], sx[n, 2], sy[n, 2]
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(den) < 1e-6:
                continue
            x0, x1 = max(int(np.floor(min(ax, bx, cx))), 0), min(int(np.ceil(max(ax, bx, cx))), W - 1)
            y0, y1 = max(int(np.floor(min(ay, by, cy))), 0), min(int(np.ceil(max(ay, by, cy))), H - 1)
            if x1 < x0 or y1 < y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            l0 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / den
            l1 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / den
            l2 = 1 - l0 - l1
            inside = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
            if not inside.any():
                continue
            w = np.stack([l0[inside], l1[inside], l2[inside]], 1)
            iz = 1.0 / Z[n]
            pz = w @ iz                                           # interpolate 1/z: perspective-correct attributes
            wp = w * iz / pz[:, None]
            z = 1.0 / pz
            u = wp @ self.UV[ti]
            col = wp @ self.C[ti]
            tex = self.textures[self.T[ti]]
            if tex is not None:
                th, tw = tex.shape[:2]
                texel = tex[(u[:, 1] % 1 * th).astype(int) % th, (u[:, 0] % 1 * tw).astype(int) % tw]
            else:
                texel = np.ones((len(u), 4), np.float32)
            rgb, a = texel[:, :3] * col[:, :3], texel[:, 3] * col[:, 3]
            yy, xx = gy[inside].astype(int), gx[inside].astype(int)
            keep = (a > 0.05) & (z < zb[yy, xx])
            if not keep.any():
                continue
            yy, xx, z, rgb, a = yy[keep], xx[keep], z[keep], rgb[keep], a[keep]
            solid = a >= 0.5                                      # a cut-out texel hides what is behind; fainter ones only tint
            blend = np.where(solid, 1.0, a * 2)[:, None]
            img[yy, xx] = img[yy, xx] * (1 - blend) + rgb * blend
            zb[yy[solid], xx[solid]] = z[solid]
        return img


def save(img: np.ndarray, path: Path) -> None:
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--dir", default=None)
    ap.add_argument("--at", default="0,0")
    ap.add_argument("--tilt", type=float, default=50)
    ap.add_argument("--dist", type=float, default=220)
    ap.add_argument("--fov", type=float, default=45)
    ap.add_argument("--size", default="640x400")
    a = ap.parse_args()
    x, z = (float(v) for v in a.at.split(","))
    sc = Scene.load(Path(a.dir) if a.dir else None)
    save(sc.render((x, 8, z), a.tilt, a.dist, a.fov, tuple(int(v) for v in a.size.split("x"))), Path(a.out))
