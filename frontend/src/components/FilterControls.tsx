// FilterControls.tsx — Toggle node visibility by resource type

import type { GraphNode } from '../types/graph'
import { nodeColor } from '../types/graph'

interface FilterControlsProps {
  nodes: GraphNode[]
  hiddenTypes: Set<string>
  onChange: (types: Set<string>) => void
}

export default function FilterControls({ nodes, hiddenTypes, onChange }: FilterControlsProps) {
  // Build type → count map
  const typeCounts = new Map<string, number>()
  for (const n of nodes) {
    typeCounts.set(n.type, (typeCounts.get(n.type) ?? 0) + 1)
  }
  const uniqueTypes = [...typeCounts.keys()].sort()

  function toggle(type: string) {
    const next = new Set(hiddenTypes)
    if (next.has(type)) {
      next.delete(type)
    } else {
      next.add(type)
    }
    onChange(next)
  }

  if (uniqueTypes.length === 0) {
    return (
      <div style={{ fontSize: 11, color: '#45475a', textAlign: 'center', padding: '8px 0' }}>
        No resources loaded yet
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 11, color: '#a6adc8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Filter types
        </span>
        {hiddenTypes.size > 0 && (
          <button
            onClick={() => onChange(new Set())}
            style={{
              background: 'none', border: 'none', color: '#cba6f7',
              cursor: 'pointer', fontSize: 10, padding: 0,
            }}
          >
            show all
          </button>
        )}
      </div>

      {/* Summary */}
      <div style={{ fontSize: 11, color: '#585b70' }}>
        {nodes.length - nodes.filter(n => hiddenTypes.has(n.type)).length}
        {' / '}{nodes.length} visible
      </div>

      {/* Type rows */}
      {uniqueTypes.map(type => {
        const hidden = hiddenTypes.has(type)
        const count = typeCounts.get(type) ?? 0
        const color = nodeColor(type)
        return (
          <label
            key={type}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              cursor: 'pointer',
              opacity: hidden ? 0.4 : 1,
              fontSize: 12,
              color: '#cdd6f4',
              userSelect: 'none',
            }}
          >
            <input
              type="checkbox"
              checked={!hidden}
              onChange={() => toggle(type)}
              style={{ display: 'none' }}
            />
            {/* Color swatch */}
            <span style={{
              width: 10, height: 10, borderRadius: '50%',
              background: color, flexShrink: 0,
              border: hidden ? '1px solid #313244' : 'none',
            }} />
            {/* Type name (truncated) */}
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {type}
            </span>
            {/* Count */}
            <span style={{ color: '#585b70', fontSize: 11 }}>{count}</span>
          </label>
        )
      })}
    </div>
  )
}
