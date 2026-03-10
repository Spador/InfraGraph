// NodeDetailPanel.tsx — Slide-in right panel showing details of a selected node

import type { GraphNode } from '../types/graph'
import { nodeColor } from '../types/graph'

interface NodeDetailPanelProps {
  node: GraphNode | null
  onClose: () => void
}

const SOURCE_COLORS: Record<string, string> = {
  terraform:  '#7aa2f7',
  kubernetes: '#9ece6a',
}

export default function NodeDetailPanel({ node, onClose }: NodeDetailPanelProps) {
  return (
    <div className={`detail-panel ${node ? 'open' : ''}`}>
      {node && (
        <>
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#cdd6f4', wordBreak: 'break-all' }}>
                {node.name}
              </div>
            </div>
            <button
              onClick={onClose}
              style={{
                background: 'none', border: 'none', color: '#585b70',
                cursor: 'pointer', fontSize: 18, lineHeight: 1,
                padding: '0 0 0 8px', flexShrink: 0,
              }}
              aria-label="Close panel"
            >
              ✕
            </button>
          </div>

          {/* Type badge */}
          <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <span style={{
              background: nodeColor(node.type),
              color: '#1e1e2e',
              fontSize: 11,
              fontWeight: 700,
              padding: '3px 8px',
              borderRadius: 4,
            }}>
              {node.type}
            </span>
            <span style={{
              background: SOURCE_COLORS[node.source] ?? '#585b70',
              color: '#1e1e2e',
              fontSize: 11,
              fontWeight: 700,
              padding: '3px 8px',
              borderRadius: 4,
            }}>
              {node.source}
            </span>
          </div>

          {/* Properties table */}
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <tbody>
              {(
                [
                  ['ID',          node.id],
                  ['Name',        node.name],
                  ['Type',        node.type],
                  ['Source',      node.source],
                  ['File',        node.file],
                  ['Line',        node.line_number === 0 ? '—' : String(node.line_number)],
                ] as [string, string][]
              ).map(([label, value]) => (
                <tr key={label} style={{ borderBottom: '1px solid #1e1e2e' }}>
                  <td style={{
                    padding: '5px 10px 5px 0',
                    color: '#585b70',
                    whiteSpace: 'nowrap',
                    verticalAlign: 'top',
                    width: '36%',
                  }}>
                    {label}
                  </td>
                  <td style={{
                    padding: '5px 0',
                    color: '#cdd6f4',
                    wordBreak: 'break-all',
                  }}>
                    {value}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}
