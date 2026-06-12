from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator

from litepaperreader.core.cell import Cell
from litepaperreader.pipeline.tool import PipelineTool, ToolContext


@dataclass
class Toolchain:
    tools: list[PipelineTool] = field(default_factory=list)
    adjacency: dict[int, list[int]] = field(default_factory=dict)

    def add_tool(self, tool: PipelineTool) -> int:
        idx = len(self.tools)
        self.tools.append(tool)
        self.adjacency[idx] = []
        return idx

    def add_edge(self, from_idx: int, to_idx: int):
        if from_idx not in self.adjacency or to_idx not in self.adjacency:
            raise ValueError("Both tool indices must exist")
        self.adjacency[from_idx].append(to_idx)

    def topological_order(self) -> list[int]:
        in_degree = {i: 0 for i in range(len(self.tools))}
        for src in self.adjacency:
            for dst in self.adjacency[src]:
                in_degree[dst] = in_degree.get(dst, 0) + 1
        queue = [i for i, d in in_degree.items() if d == 0]
        order = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in self.adjacency.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        if len(order) != len(self.tools):
            raise ValueError("Cycle detected in toolchain DAG")
        return order

    async def run(self, input_cells: AsyncIterator[Cell], ctx: ToolContext | None = None) -> AsyncIterator[Cell]:
        if ctx is None:
            ctx = ToolContext()

        # Check if any explicit edges exist
        has_edges = any(bool(v) for v in self.adjacency.values())

        if not has_edges and len(self.tools) > 1:
            # No edges: process tools sequentially (output of i -> input of i+1)
            current = input_cells
            for tool in self.tools:
                current = tool.process(current, ctx)
            async for c in current:
                yield c
            return

        # Check if any explicit edges exist
        has_edges = any(bool(v) for v in self.adjacency.values())

        if not has_edges and len(self.tools) > 1:
            # No edges: process tools sequentially
            current = input_cells
            for tool in self.tools:
                current = tool.process(current, ctx)
            async for c in current:
                yield c
            return

        if not self.tools:
            async for c in input_cells:
                yield c
            return

        order = self.topological_order()
        layers = self._layer_order(order)
        current: AsyncIterator[Cell] = input_cells
        for layer in layers:
            current = self._run_layer(layer, current, ctx)
        async for cell in current:
            yield cell

    def _layer_order(self, order: list[int]) -> list[list[int]]:
        depth = {i: 0 for i in range(len(self.tools))}
        for node in order:
            for neighbor in self.adjacency.get(node, []):
                depth[neighbor] = max(depth[neighbor], depth[node] + 1)
        layers: dict[int, list[int]] = {}
        for idx, d in depth.items():
            layers.setdefault(d, []).append(idx)
        return [layers[d] for d in sorted(layers)]

    async def _run_layer(self, indices: list[int], stream: AsyncIterator[Cell], ctx: ToolContext) -> AsyncIterator[Cell]:
        if len(indices) == 1:
            tool = self.tools[indices[0]]
            async for cell in tool.process(stream, ctx):
                yield cell
        else:
            streams = [self._tee(stream) for _ in indices]
            results = await asyncio.gather(*[
                self._collect(tool.process(s, ctx))
                for tool, s in zip([self.tools[i] for i in indices], streams)
            ])
            for r in results:
                for cell in r:
                    yield cell

    async def _collect(self, ait: AsyncIterator[Cell]) -> list[Cell]:
        return [c async for c in ait]

    async def _tee(self, stream: AsyncIterator[Cell]) -> AsyncIterator[Cell]:
        async for cell in stream:
            yield cell
