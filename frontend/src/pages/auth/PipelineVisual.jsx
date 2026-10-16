/**
 * src/pages/auth/PipelineVisual.jsx
 * Animated pipeline SVG: Embedding → Retrieval → Reranking → LLM
 * Pure CSS/SVG animation with a traveling pulse along the path.
 */
import './PipelineVisual.css';

const NODES = [
  { id: 'embed',    label: 'Embedding',  x: 80,  y: 100, color: '#7C6CF0' },
  { id: 'retrieve', label: 'Retrieval',  x: 80,  y: 200, color: '#4CC9F0' },
  { id: 'rerank',   label: 'Reranking',  x: 80,  y: 300, color: '#FFB547' },
  { id: 'llm',      label: 'LLM',        x: 80,  y: 400, color: '#2DE2A6' },
];

export function PipelineVisual() {
  return (
    <div className="pipeline-visual" aria-hidden="true">
      <svg viewBox="0 0 200 480" className="pipeline-svg" xmlns="http://www.w3.org/2000/svg">
        {/* Connecting lines */}
        {NODES.slice(0, -1).map((node, i) => {
          const next = NODES[i + 1];
          const pathId = `path-${node.id}-${next.id}`;
          return (
            <g key={pathId}>
              <line
                x1={node.x}
                y1={node.y + 28}
                x2={next.x}
                y2={next.y - 28}
                stroke="rgba(255,255,255,0.08)"
                strokeWidth="2"
              />
              <line
                x1={node.x}
                y1={node.y + 28}
                x2={next.x}
                y2={next.y - 28}
                stroke={node.color}
                strokeWidth="2"
                strokeDasharray="60 200"
                opacity="0.5"
                style={{
                  animation: `travelPulse 2.4s ${i * 0.6}s ease-in-out infinite`,
                }}
              />
            </g>
          );
        })}

        {/* Nodes */}
        {NODES.map((node, i) => (
          <g key={node.id} style={{ animation: `fadeUp 0.5s ${i * 0.1}s both` }}>
            {/* Glow */}
            <circle cx={node.x} cy={node.y} r="32" fill={node.color} opacity="0.06" />
            {/* Ring */}
            <circle cx={node.x} cy={node.y} r="26" fill="var(--bg-elevated)" stroke={node.color} strokeWidth="1.5" />
            {/* Pulsing dot */}
            <circle
              cx={node.x}
              cy={node.y}
              r="7"
              fill={node.color}
              style={{ animation: `pulse 2s ${i * 0.5}s ease-in-out infinite` }}
            />
            {/* Label */}
            <text
              x={node.x + 36}
              y={node.y + 5}
              fill="var(--text-secondary)"
              fontSize="13"
              fontFamily="var(--font-ui)"
              fontWeight="500"
            >
              {node.label}
            </text>
          </g>
        ))}

        {/* Document icon at top */}
        <g opacity="0.4">
          <rect x="62" y="22" width="36" height="44" rx="4" fill="none" stroke="var(--text-muted)" strokeWidth="1" />
          <line x1="70" y1="34" x2="90" y2="34" stroke="var(--text-muted)" strokeWidth="1" />
          <line x1="70" y1="42" x2="90" y2="42" stroke="var(--text-muted)" strokeWidth="1" />
          <line x1="70" y1="50" x2="82" y2="50" stroke="var(--text-muted)" strokeWidth="1" />
        </g>
        <text x={80} y={78} textAnchor="middle" fill="var(--text-muted)" fontSize="11" fontFamily="var(--font-ui)">Document</text>

        {/* Answer icon at bottom */}
        <g opacity="0.4">
          <rect x="58" y="438" width="44" height="26" rx="4" fill="none" stroke="var(--accent)" strokeWidth="1" />
          <circle cx="68" cy="451" r="3" fill="var(--accent)" />
          <circle cx="80" cy="451" r="3" fill="var(--accent)" />
          <circle cx="92" cy="451" r="3" fill="var(--accent)" />
        </g>
        <text x={80} y={478} textAnchor="middle" fill="var(--text-muted)" fontSize="11" fontFamily="var(--font-ui)">Answer</text>
      </svg>
    </div>
  );
}
