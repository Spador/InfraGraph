# Directive: Frontend (React + TypeScript + D3.js)

## Objective

Build an interactive, single-page React + TypeScript application that visualizes the infrastructure dependency graph returned by the Flask API. The centerpiece is a D3.js force-directed SVG graph with colored nodes, directed edges, zoom/pan, node filtering, and a detail panel — all driven by a typed API client and a central `useGraph` hook.

---

## Inputs

| Source | Data |
|---|---|
| `GET /graph` | Full graph: `{nodes, edges}` |
| `GET /graph/resource/{id}` | Depth-2 subgraph for a selected node |
| `GET /graph/stats` | Stats: `{node_count, edge_count, most_connected, isolated_count, circular_dependencies}` |
| `POST /parse/terraform` | Upload result: `{node_count, edge_count}` |
| `POST /parse/kubernetes` | Upload result: `{node_count, edge_count}` |
| `POST /graph/reset` | Reset result: `{deleted}` |

---

## Tools / Scripts

- `senior-frontend/scripts/component_generator.py` — CLI pattern reference for component structure
- `senior-frontend/references/react_patterns.md` — hook patterns and component composition
- `senior-frontend/references/frontend_best_practices.md` — TypeScript strictness, accessibility

---

## Build Setup

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install d3@7 @types/d3
```

`tsconfig.json` settings:
- `"strict": true`
- `"moduleResolution": "bundler"`
- `"jsx": "react-jsx"`

`vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/parse': 'http://localhost:5000', '/graph': 'http://localhost:5000' } }
})
```

---

## Types (`src/types/graph.ts`)

```typescript
export interface GraphNode {
  id: string;
  name: string;
  type: string;
  file: string;
  line_number: number;
  source: string;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphStats {
  node_count: number;
  edge_count: number;
  most_connected: { id: string; name: string; type: string; degree: number } | null;
  isolated_count: number;
  circular_dependencies: number;
}

export const NODE_COLORS: Record<string, string> = {
  aws_instance:        '#4A90D9',
  aws_s3_bucket:       '#27AE60',
  aws_iam_role:        '#E74C3C',
  aws_iam_policy:      '#C0392B',
  aws_vpc:             '#16A085',
  aws_subnet:          '#1ABC9C',
  aws_security_group:  '#E74C3C',
  aws_lb:              '#8E44AD',
  aws_db_instance:     '#D35400',
  Deployment:          '#8E44AD',
  Service:             '#E67E22',
  ConfigMap:           '#F1C40F',
  Secret:              '#FF69B4',
  Ingress:             '#3498DB',
  variable:            '#BDC3C7',
  output:              '#95A5A6',
  default:             '#95A5A6',
};
```

---

## API Client (`src/api/client.ts`)

Base URL: `import.meta.env.VITE_API_URL ?? 'http://localhost:5000'`

All functions are typed async wrappers using `fetch`. Throw on non-2xx responses.

```typescript
export const api = {
  fetchGraph: (): Promise<GraphData>
  fetchSubgraph: (id: string): Promise<GraphData>
  fetchStats: (): Promise<GraphStats>
  uploadTerraform: (file: File): Promise<{node_count: number, edge_count: number}>
  uploadKubernetes: (file: File): Promise<{node_count: number, edge_count: number}>
  resetGraph: (): Promise<{deleted: number}>
}
```

---

## useGraph Hook (`src/hooks/useGraph.ts`)

```typescript
interface UseGraphReturn {
  nodes: GraphNode[];
  edges: GraphEdge[];
  loading: boolean;
  error: string | null;
  selectedNode: GraphNode | null;
  setSelectedNode: (node: GraphNode | null) => void;
  refresh: () => void;
  uploadTerraform: (file: File) => Promise<{node_count: number, edge_count: number}>;
  uploadKubernetes: (file: File) => Promise<{node_count: number, edge_count: number}>;
}
```

- `useEffect` with empty deps: call `api.fetchGraph()` on mount
- `uploadTerraform` / `uploadKubernetes`: call API, then call `refresh()` on success
- `selectedNode` state lives here; passed to `GraphCanvas` and `NodeDetailPanel`

---

## Components

### App.tsx — Layout

```
┌─────────────────────────────────────────────────┐
│  StatsBar (top, full width)                     │
├──────────────┬──────────────────────────────────┤
│  UploadZone  │  GraphCanvas (flex: 1)            │
│  (left 280px)│                                   │
│              │                        ┌──────────┤
│  FilterCtrls │                        │ Detail   │
│              │                        │ Panel    │
│              │                        │ (320px)  │
└──────────────┴────────────────────────┴──────────┘
```

Use CSS Flexbox / Grid. `NodeDetailPanel` overlays as a fixed right drawer.

### GraphCanvas.tsx — D3 Force Graph

**Mount**: `const svgRef = useRef<SVGSVGElement>(null)`

**useEffect** (deps: `[nodes, edges, hiddenTypes]`):
1. Clear SVG: `d3.select(svgRef.current).selectAll('*').remove()`
2. Filter nodes by `hiddenTypes`
3. Build degree map: `nodes.forEach(n => degree[n.id] = 0); edges.forEach(e => { degree[e.source]++; degree[e.target]++ })`
4. Node radius: `5 + Math.sqrt(degree[n.id] ?? 0) * 3`
5. Add `<defs><marker id="arrowhead">` for directed edges
6. Create simulation:
   ```typescript
   d3.forceSimulation(nodeData)
     .force('link', d3.forceLink(edgeData).id((d: any) => d.id).distance(80))
     .force('charge', d3.forceManyBody().strength(-300))
     .force('center', d3.forceCenter(width / 2, height / 2))
     .force('collision', d3.forceCollide().radius((d: any) => d.radius + 5))
   ```
7. Render `<line>` edges with `marker-end="url(#arrowhead)"`
8. Render `<circle>` nodes colored by `NODE_COLORS[node.type] ?? NODE_COLORS.default`
9. Render `<text>` labels (truncated to 12 chars)
10. Bind zoom: `d3.zoom().scaleExtent([0.1, 10]).on('zoom', e => g.attr('transform', e.transform))`
11. Bind drag: `d3.drag().on('start/drag/end', ...)`
12. On node click: `setSelectedNode(d)`
13. On simulation `tick`: update `<line>` and `<circle>` positions

**Highlight path**: when `highlightedPath` prop is set, color edges in path yellow.

### UploadZone.tsx

- Hidden `<input type="file" accept=".tf,.yaml,.yml,.zip">`
- Visible drop zone div with `onDragOver`, `onDrop`, `onClick`
- On file drop/select:
  - Detect type by extension: `.tf` → `uploadTerraform`; `.yaml`/`.yml` → `uploadKubernetes`; `.zip` → `uploadTerraform` (backend auto-detects content)
  - Show loading spinner during upload
  - On success: show toast `"+N nodes, +M edges added"`
  - On error: show error toast with message
- `useCallback` on handlers to prevent unnecessary re-renders

### NodeDetailPanel.tsx

CSS:
```css
.detail-panel {
  position: fixed;
  right: 0; top: 0;
  width: 320px; height: 100vh;
  transform: translateX(100%);
  transition: transform 0.3s ease;
  background: #1e1e2e;
  overflow-y: auto;
  z-index: 100;
}
.detail-panel.open { transform: translateX(0); }
```

Contents:
- Close button (`setSelectedNode(null)`)
- Node `type` badge (colored chip using `NODE_COLORS`)
- Properties table: id, name, type, file, line_number, source
- "Show subgraph" button: calls `api.fetchSubgraph(selectedNode.id)`, updates graph to subgraph view

### FilterControls.tsx

- Derive unique types: `[...new Set(nodes.map(n => n.type))]`
- Render checkbox for each type, colored circle using `NODE_COLORS`
- State: `hiddenTypes: Set<string>` — toggled on checkbox change
- Pass `hiddenTypes` up to `App.tsx` which passes to `GraphCanvas`
- "Reset Filters" button: clear `hiddenTypes`
- "Shortest Path" toggle:
  - When active, next 2 node clicks set `pathSource` and `pathTarget`
  - Client-side BFS on current visible nodes/edges to find shortest path
  - Pass `highlightedPath: string[]` (array of node IDs) to `GraphCanvas`

### StatsBar.tsx

- Poll `api.fetchStats()` every 5 seconds using `setInterval` in `useEffect`
- Display: `{node_count} Resources | {edge_count} Edges | {isolated_count} Isolated`
- Red badge: `<span class="badge-red">{circular_dependencies} Cycles</span>` — shown only when `circular_dependencies > 0`
- "Reset Graph" button: calls `api.resetGraph()`, then triggers `refresh()`

---

## Dockerfile (`frontend/Dockerfile`)

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json .
RUN npm ci
COPY . .
ARG VITE_API_URL=http://localhost:5000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

`nginx.conf`:
```nginx
server {
  listen 80;
  root /usr/share/nginx/html;
  index index.html;

  location / {
    try_files $uri $uri/ /index.html;
  }

  location /parse {
    proxy_pass http://backend:5000;
  }

  location /graph {
    proxy_pass http://backend:5000;
  }

  location /health {
    proxy_pass http://backend:5000;
  }
}
```

---

## Edge Cases

| Scenario | Handling |
|---|---|
| Empty graph (no nodes) | Show "Upload a .tf or .yaml file to get started" placeholder in GraphCanvas |
| Very large graph (200+ nodes) | D3 simulation runs; no pagination in MVP |
| Node type not in NODE_COLORS | Use `default` gray `#95A5A6` |
| Upload fails (network error) | Show error toast; do not clear existing graph |
| NodeDetailPanel open during graph re-render | Re-render closes panel if selected node no longer exists |
| D3 ref null on first render | Guard: `if (!svgRef.current) return` at top of useEffect |
| Shortest path not found | Show toast "No path found between selected nodes" |
| Stats polling error | Log to console; do not show error UI; retry on next interval |

---

## Update Log

- Initial version: Vite+React+TS scaffold, D3 force graph, 5 components, useGraph hook, typed API client
- Fix: `import.meta.env` requires `src/vite-env.d.ts` with `/// <reference types="vite/client" />` — without it, TypeScript errors on `Property 'env' does not exist on type 'ImportMeta'`
- Note: `VITE_API_URL` set to `""` (empty string) in Dockerfile so API calls use relative paths — nginx then proxies `/parse`, `/graph`, `/health` to backend:5000
- D3 arrowhead: `refX=10` + line endpoint shortened by `tgt.radius + 2` pixels so arrow sits cleanly at node edge, not overlapping the circle
- SimNode extends `d3.SimulationNodeDatum`; cast `d.source as SimNode` in tick handler to access `.x`/`.y` after D3 resolves string IDs to node objects
- StatsBar uses `setInterval` + cleanup in `useEffect([], [loadStats])` — `loadStats` wrapped in `useCallback` to avoid stale closure re-registering the interval on every render
- UploadZone: `.zip` routes to `onUploadTerraform` (backend infers Terraform vs Kubernetes content from zip file listing)
- NodeDetailPanel: `detail-panel.open` CSS class toggled via prop — existing App.css slide-in animation handles the rest; no inline transition needed in the component
- FilterControls: hides the native checkbox input (`display: none`) and uses a custom colored swatch + label for type rows
