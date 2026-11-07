"""图谱：把档案关系摆成一个可以拖动的图。

布局是自己写的 Fruchterman–Reingold 简化版（纯 Python，不引第三方库）：
节点越多越慢，但 481 站里一次命中的规模通常只有几十个点，够用。

坐标是「逻辑坐标」，页面按自己的画布尺寸缩放，所以这里只保证相对关系。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .identity import Account, score_pair

# 图谱上画线的门槛比聚类的 REVIEW_THRESHOLD 更低：
# 聚类要保守（宁可分开），画图要能看出「同名但证据很弱」这种关系。
GRAPH_MIN_SCORE = 0.20


@dataclass
class Edge:
    a: str
    b: str
    score: float
    strong: bool
    notes: list[str]


def account_key(account: Account) -> str:
    return f"{account.site}|{account.username}"


# 锚定视图的分圈门槛，与 identity / anchor 的判定线保持一致
ANCHOR_STRONG = 0.62
ANCHOR_REVIEW = 0.45
ANCHOR_RINGS = (0.18, 0.30, 0.42)


def anchor_layout(
    keys: list[str],
    seed_key: str,
    scores: dict[str, float],
    width: float = 1000.0,
    height: float = 700.0,
) -> dict[str, tuple[float, float]]:
    """种子居中、候选按证据分分三圈摆放。

    内圈（≥0.62）几乎可以认定是同一个人，中圈（0.45–0.62）看证据，
    外圈是「同名但没证据」。纯几何计算，不随机，刷新结果一致。
    """
    if not keys:
        return {}

    cx, cy = width / 2.0, height / 2.0
    positions: dict[str, tuple[float, float]] = {seed_key: (cx, cy)}

    others = [key for key in keys if key != seed_key]
    bands: list[list[str]] = [[], [], []]
    for key in others:
        score = scores.get(key, 0.0)
        if score >= ANCHOR_STRONG:
            bands[0].append(key)
        elif score >= ANCHOR_REVIEW:
            bands[1].append(key)
        else:
            bands[2].append(key)

    base = min(width, height)
    for index, band in enumerate(bands):
        if not band:
            continue
        radius = base * ANCHOR_RINGS[index]
        band.sort(key=lambda item: (-scores.get(item, 0.0), item))
        # 每一圈错开一个角度，避免三层节点排成一条线
        offset = math.pi / 2.0 + index * (math.pi / 6.0)
        step = 2.0 * math.pi / len(band)
        for position, key in enumerate(band):
            angle = offset + step * position
            positions[key] = (cx + radius * math.cos(angle), cy + radius * math.sin(angle))

    return positions


def build_edges(
    accounts: list[Account], min_score: float = GRAPH_MIN_SCORE, strong_only: bool = False
) -> list[Edge]:
    edges: list[Edge] = []
    for i in range(len(accounts)):
        for j in range(i + 1, len(accounts)):
            pair = score_pair(accounts[i], accounts[j])
            if pair.score < min_score:
                continue
            if strong_only and not pair.strong:
                continue
            edges.append(
                Edge(
                    a=account_key(accounts[i]),
                    b=account_key(accounts[j]),
                    score=pair.score,
                    strong=pair.strong,
                    notes=pair.notes,
                )
            )
    edges.sort(key=lambda e: -e.score)
    return edges


def degrees(keys: list[str], edges: list[Edge]) -> dict[str, float]:
    """加权度数：节点大小用它。"""
    out = {key: 0.0 for key in keys}
    for edge in edges:
        out[edge.a] = out.get(edge.a, 0.0) + edge.score
        out[edge.b] = out.get(edge.b, 0.0) + edge.score
    return out


def layout(
    keys: list[str],
    edges: list[Edge],
    width: float = 900.0,
    height: float = 620.0,
    iterations: int = 220,
    seed: int = 11,
) -> dict[str, tuple[float, float]]:
    """力导向布局：互斥 + 按证据强度吸引，最后归一化到画布内。"""
    n = len(keys)
    if n == 0:
        return {}
    if n == 1:
        return {keys[0]: (width / 2, height / 2)}

    rng = random.Random(seed)
    margin = 40.0
    pos = {
        key: (
            rng.uniform(margin, max(margin + 1, width - margin)),
            rng.uniform(margin, max(margin + 1, height - margin)),
        )
        for key in keys
    }
    area = max(1.0, (width - 2 * margin) * (height - 2 * margin))
    k = math.sqrt(area / n)
    edge_index = {(edge.a, edge.b): edge for edge in edges}
    degree = degrees(keys, edges)

    for step in range(iterations):
        temperature = (1.0 - step / iterations) * (width / 12.0) + 0.5
        disp = {key: [0.0, 0.0] for key in keys}

        for i in range(n):
            for j in range(i + 1, n):
                a, b = keys[i], keys[j]
                ax, ay = pos[a]
                bx, by = pos[b]
                dx, dy = ax - bx, ay - by
                dist = math.hypot(dx, dy) or 0.01
                force = (k * k) / dist
                ux, uy = dx / dist, dy / dist
                disp[a][0] += ux * force
                disp[a][1] += uy * force
                disp[b][0] -= ux * force
                disp[b][1] -= uy * force

        for edge in edges:
            ax, ay = pos[edge.a]
            bx, by = pos[edge.b]
            dx, dy = ax - bx, ay - by
            dist = math.hypot(dx, dy) or 0.01
            force = (dist * dist) / k * (0.35 + edge.score)
            ux, uy = dx / dist, dy / dist
            disp[edge.a][0] -= ux * force
            disp[edge.a][1] -= uy * force
            disp[edge.b][0] += ux * force
            disp[edge.b][1] += uy * force

        for key in keys:
            dx, dy = disp[key]
            length = math.hypot(dx, dy) or 0.01
            limit = min(length, temperature)
            pos[key] = (
                pos[key][0] + dx / length * limit,
                pos[key][1] + dy / length * limit,
            )

    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    inner_w = max(width - 2 * margin, 1.0)
    inner_h = max(height - 2 * margin, 1.0)
    scale = min(inner_w / span_x, inner_h / span_y)
    # 保持比例，居中
    offset_x = margin + (inner_w - span_x * scale) / 2
    offset_y = margin + (inner_h - span_y * scale) / 2
    return {
        key: (
            offset_x + (pos[key][0] - min_x) * scale,
            offset_y + (pos[key][1] - min_y) * scale,
        )
        for key in keys
    }


def cluster_layout(
    clusters: list,
    width: float = 900.0,
    height: float = 620.0,
) -> dict[str, tuple[float, float]]:
    """按"档案"分组的环形布局：一簇一圈，簇内再围一圈。

    力导向在账号数少、证据弱的时候容易挤成一坨（用户能直接看出"没排开"），
    这里改成确定性的分簇布局：不会重叠，也不依赖随机种子。
    """
    keys: list[str] = []
    groups: list[list[str]] = []
    for cluster in clusters:
        members = [account_key(account) for account in getattr(cluster, "accounts", [])]
        members = [m for m in members if m]
        if not members:
            continue
        keys.extend(members)
        groups.append(members)
    if not keys:
        return {}

    cx, cy = width / 2.0, height / 2.0
    margin = 46.0
    if len(groups) == 1:
        ring_r = min(width, height) * 0.30
        return _ring(groups[0], cx, cy, ring_r, single_center=(cx, cy))

    outer = min(width - 2 * margin, height - 2 * margin) * 0.40
    positions: dict[str, tuple[float, float]] = {}
    for index, members in enumerate(groups):
        angle = 2 * math.pi * index / len(groups) - math.pi / 2
        gx = cx + outer * math.cos(angle)
        gy = cy + outer * math.sin(angle)
        inner = 0.0 if len(members) == 1 else min(78.0, 18.0 + 12.0 * len(members))
        positions.update(_ring(members, gx, gy, inner, single_center=(gx, gy)))
    return positions


def _ring(
    members: list[str],
    cx: float,
    cy: float,
    radius: float,
    single_center: tuple[float, float],
) -> dict[str, tuple[float, float]]:
    if len(members) == 1:
        return {members[0]: single_center}
    out: dict[str, tuple[float, float]] = {}
    for index, key in enumerate(members):
        angle = 2 * math.pi * index / len(members) - math.pi / 2
        out[key] = (cx + radius * math.cos(angle), cy + radius * math.sin(angle))
    return out


def node_radius(degree: float, max_degree: float, base: float = 14.0, span: float = 18.0) -> float:
    if max_degree <= 0:
        return base
    return base + span * min(1.0, degree / max_degree)
