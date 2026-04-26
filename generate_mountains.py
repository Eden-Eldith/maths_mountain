import numpy as np
from PIL import Image
import time
from pathlib import Path


def render_mountains(width=2000, height=1200, save_debug=True, output_dir='.'):
    t0 = time.time()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print('Setting up coordinate grids...')
    m = np.arange(1, width + 1, dtype=np.float64)
    n = np.arange(1, height + 1, dtype=np.float64)
    M, N = np.meshgrid(m, n)
    x = (M - 1000.0) / 600.0
    y = (601.0 - N) / 600.0

    def safe_exp(a):
        return np.exp(np.clip(a, -700, 700))

    # === E(x,y) = sum_{s=1}^{50} (24/25)^s * N_s(x,y) ===
    # N_s is a product of TWO outer cosines. In the source formula, the '+ 4 cos(...) + 2 cos(...)'
    # terms sit INSIDE each outer cosine; they are not separate additive terms outside the cosine.
    print('Computing fractal envelope E(x,y)...')
    E = np.zeros_like(x)
    for s in range(1, 51):
        s2 = s * s
        q = (6.0 / 5.0) ** s

        n1_arg = (
            q * (np.cos(s2) * x + np.sin(s2) * y + 2.0 * np.cos(17.0 * s))
            + 4.0 * np.cos(q * (np.cos(9.0 * s) * x + np.sin(9.0 * s) * y))
            + 2.0 * np.cos(5.0 * s2)
        )
        n2_arg = (
            q * (np.cos(s2) * y - np.sin(s2) * x + 2.0 * np.cos(15.0 * s))
            + 4.0 * np.cos(q * (np.cos(8.0 * s) * x + np.sin(8.0 * s) * y))
            + 2.0 * np.cos(7.0 * s2)
        )
        E += (24.0 / 25.0) ** s * np.cos(n1_arg) * np.cos(n2_arg)

        if s % 10 == 0:
            print(f'  E: {s}/50')
    print(f'  E range: [{E.min():.2f}, {E.max():.2f}]')

    # === J_s(x,y) = exp(-exp(-1000(s-1/2)) - exp(2000*shape_arg)) ===
    print('Computing mountain shapes J_s...')
    J = {0: np.zeros_like(x)}
    for s in range(1, 24):
        s2 = s * s
        layer_gate = -safe_exp(-1000.0 * (s - 0.5))
        abs_term = np.abs(x + 1.25 * np.cos(s2))
        slope = 2.0 / 3.0 + 9.0 / 20.0 * np.cos(12.0 * s2) ** 2

        # The first ridge phase is '+ 7s^2' in the printed formula, not '+ 3s^2'.
        ridge1 = np.cos(5.0 * x + np.cos(3.0 * x + 5.0 * s2) + 7.0 * s2) ** 2 / 25.0
        ridge2 = np.cos(17.0 * x + np.cos(8.0 * x + 7.0 * s2) + 8.0 * s2) ** 3 / 50.0
        ridge3 = 7.0 * np.cos(54.0 * x + np.cos(19.0 * x + 9.0 * s2) + 38.0 * s2) ** 3 / 1000.0

        shape_arg = y + 0.5 - s / 15.0 + slope * abs_term + ridge1 + ridge2 + ridge3 + E / 1000.0
        shape_gate = -safe_exp(2000.0 * shape_arg)
        J[s] = safe_exp(layer_gate + shape_gate)

    # === Z_s(x,y) = prod_{u=0}^{s} (1 - J_u) ===
    print('Computing occlusion Z_s...')
    Z = {0: 1.0 - J[0]}
    for s in range(1, 24):
        Z[s] = Z[s - 1] * (1.0 - J[s])
    Z_23 = Z[23]

    # === R, T, B, A ===
    # C depends on B(x,y), so compute B first, then do a second pass for C.
    print('Computing R, T, B, A...')
    R = np.zeros_like(x)
    T = np.zeros_like(x)
    B = np.zeros_like(x)
    A = np.zeros_like(x)

    for s in range(1, 24):
        s2 = s * s
        w = Z[s - 1] * J[s]
        R += w * (9.0 / 10.0 - s / 28.0)

        dx = x + 1.25 * np.cos(s2)
        dy = y + 0.5 - s / 15.0
        T += w * np.sqrt(dx ** 2 + dy ** 2)

        denom = 300.0 * y + 147.0 - 20.0 * s
        B += w * np.arctan((300.0 * x + 375.0 * np.cos(s2)) / (denom + 1e-30))

        A += w * (15.0 + s) / 30.0 * (7.0 / 10.0 - 3.0 / 5.0 * y + 3.0 * s / 75.0)

    # === C(x,y) = sum Z_{s-1}J_s exp(-exp(-6(y + 13/20 - s/26 + B/100))) ===
    print('Computing C...')
    C = np.zeros_like(x)
    for s in range(1, 24):
        w = Z[s - 1] * J[s]
        c_exp = safe_exp(-safe_exp(-6.0 * (y + 13.0 / 20.0 - s / 26.0 + B / 100.0)))
        C += w * c_exp

    print(f'  R: [{R.min():.4f}, {R.max():.4f}]')
    print(f'  T: [{T.min():.4f}, {T.max():.4f}]')
    print(f'  B: [{B.min():.4f}, {B.max():.4f}]')
    print(f'  C: [{C.min():.4f}, {C.max():.4f}]')

    # === K_v(x,y) ===
    # K_v = sum (91/100)^s * exp(-exp(-7/2*T*(cos(arg1)*cos(arg2) - 4/5)))
    # with (11/10)^s and s-dependent sin/cos phases.
    print('Computing lighting K_v...')
    K = {}
    for v in range(3):
        K[v] = np.zeros_like(x)
        yv = y + v / 4000.0
        for s in range(1, 51):
            s2 = s * s
            amp = (91.0 / 100.0) ** s
            q = (11.0 / 10.0) ** s

            arg1 = (
                7.0 / 10.0 * q * (1.5 * np.cos(s2) * B + 4.0 / 5.0 * np.sin(3.0 * s2) * yv)
                + 2.0 * np.cos(15.0 * s2)
            )
            arg2 = (
                7.0 / 10.0 * q * (1.5 * np.sin(s2) * B - 4.0 / 5.0 * np.cos(s2) * yv)
                + 2.0 * np.cos(31.0 * s2)
            )
            inner_arg = -3.5 * T * (np.cos(arg1) * np.cos(arg2) - 4.0 / 5.0)
            K[v] += amp * safe_exp(-safe_exp(inner_arg))

            if s % 10 == 0:
                print(f'  K_{v}: {s}/50')
        print(f'  K_{v} range: [{K[v].min():.4f}, {K[v].max():.4f}]')

    # === S(x,y) ===
    print('Computing sky S...')
    S = 9.0 * Z_23 * (17.0 + 5.0 * y) / 20.0 + 9.0 * (1.0 - Z_23) * (1.0 - R)

    # === H_v(x,y) ===
    print('Computing color channels H_v...')
    lighting_arg = -12000.0 * (K[1] - K[0] + (5.0 + 2.0 * E) / 50000.0)
    lighting = safe_exp(-safe_exp(lighting_arg))
    print(f'  lighting: [{lighting.min():.4f}, {lighting.max():.4f}]')

    H = {}
    for v in range(3):
        c1 = (3.0 * v ** 2 - 3.0 * v) / 25.0
        c2 = (168.0 - 6.0 * v ** 2 + 6.0 * v) / 100.0
        c3 = (7.0 * v ** 2 - 5.0 * v + 32.0) / 400.0
        H[v] = c1 * R * A * C + c2 * R * (1.0 - Z_23) * C * lighting + c3 * S
        print(f'  H_{v}: [{H[v].min():.4f}, {H[v].max():.4f}]')

    if save_debug:
        debug_img = np.zeros((height, width, 3), dtype=np.uint8)
        for v in range(3):
            debug_img[:, :, v] = np.clip(H[v] / 2.0 * 255.0, 0, 255).astype(np.uint8)
        debug_path = output_dir / 'mountains_raw_H.png'
        Image.fromarray(debug_img, 'RGB').save(debug_path)
        print(f'Saved raw H debug image to {debug_path}')

    # === F(x) = floor(255 * exp(-exp(-1000x)) * |x|^(exp(-exp(1000(x-1))))) ===
    print('Applying color compression F...')
    img = np.zeros((height, width, 3), dtype=np.uint8)
    for v in range(3):
        h = H[v]
        sigmoid = safe_exp(-safe_exp(-1000.0 * h))
        power_exp = safe_exp(-safe_exp(1000.0 * (h - 1.0)))
        abs_h = np.abs(h)
        with np.errstate(divide='ignore', invalid='ignore', over='ignore'):
            log_abs = np.where(abs_h > 1e-30, np.log(abs_h), -700.0)
            power_term = safe_exp(power_exp * log_abs)
            power_term = np.where(abs_h > 1e-30, power_term, 0.0)
        f = np.floor(255.0 * sigmoid * power_term)
        img[:, :, v] = np.clip(f, 0, 255).astype(np.uint8)

    elapsed = time.time() - t0
    print(f'\nRendering complete in {elapsed:.1f} seconds')
    return img


if __name__ == '__main__':
    img = render_mountains()
    out_path = Path('mountains.png')
    Image.fromarray(img, 'RGB').save(out_path)
    print(f'Saved to {out_path}')
