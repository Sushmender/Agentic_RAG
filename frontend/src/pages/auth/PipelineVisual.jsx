/**
 * src/pages/auth/PipelineVisual.jsx
 * Animated pipeline SVG: Document → Embedding → Retrieval → Reranking → LLM → Answer
 * Pure CSS/SVG animation with a traveling pulse along the path.
 */
import './PipelineVisual.css';

const NODES = [
  { id: 'embed',    label: 'Embedding',  x: 80,  y: 125, color: '#7C6CF0' },
  { id: 'retrieve', label: 'Retrieval',  x: 80,  y: 215, color: '#4CC9F0' },
  { id: 'rerank',   label: 'Reranking',  x: 80,  y: 305, color: '#FFB547' },
  { id: 'llm',      label: 'LLM',        x: 80,  y: 395, color: '#2DE2A6' },
];

export function PipelineVisual() {
  return (
    <div className="pipeline-visual" aria-hidden="true">
      <svg viewBox="0 0 220 500" className="pipeline-svg" xmlns="http://www.w3.org/2000/svg">
        {/* Document icon at top */}
        <g opacity="0.5">
          <rect x="64" y="16" width="32" height="38" rx="4" fill="none" stroke="var(--text-muted)" strokeWidth="1.2" />
          <line x1="71" y1="26" x2="89" y2="26" stroke="var(--text-muted)" strokeWidth="1" />
          <line x1="71" y1="33" x2="89" y2="33" stroke="var(--text-muted)" strokeWidth="1" />
          <line x1="71" y1="40" x2="82" y2="40" stroke="var(--text-muted)" strokeWidth="1" />
        </g>
        <text x={80} y={68} textAnchor="middle" fill="var(--text-muted)" fontSize="11" fontFamily="var(--font-ui)" fontWeight="500">
          Document
        </text>

        {/* Lead-in line to Embedding node */}
        <line
          x1={80}
          y1={74}
          x2={80}
          y2={99}
          stroke="rgba(255,255,255,0.12)"
          strokeWidth="1.5"
          strokeDasharray="3 3"
        />

        {/* Inter-node connecting lines */}
        {NODES.slice(0, -1).map((node, i) => {
          const next = NODES[i + 1];
          const pathId = `path-${node.id}-${next.id}`;
          return (
            <g key={pathId}>
              <line
                x1={node.x}
                y1={node.y + 26}
                x2={next.x}
                y2={next.y - 26}
                stroke="rgba(255,255,255,0.08)"
                strokeWidth="2"
              />
              <line
                x1={node.x}
                y1={node.y + 26}
                x2={next.x}
                y2={next.y - 26}
                stroke={node.color}
                strokeWidth="2"
                strokeDasharray="50 180"
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
            <circle cx={node.x} cy={node.y} r="25" fill="var(--bg-elevated)" stroke={node.color} strokeWidth="1.5" />
            {/* Pulsing dot */}
            <circle
              cx={node.x}
              cy={node.y}
              r="6.5"
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

        {/* Lead-out line from LLM to Answer */}
        <line
          x1={80}
          y1={420}
          x2={80}
          y2={440}
          stroke="rgba(45,226,166,0.3)"
          strokeWidth="1.5"
          strokeDasharray="3 3"
        />

        {/* Answer icon at bottom */}
        <g opacity="0.6">
          <rect x="58" y="442" width="44" height="24" rx="4" fill="none" stroke="var(--accent)" strokeWidth="1.2" />
          <circle cx="68" cy="454" r="2.5" fill="var(--accent)" />
          <circle cx="80" cy="454" r="2.5" fill="var(--accent)" />
          <circle cx="92" cy="454" r="2.5" fill="var(--accent)" />
        </g>
        <text x={80} y={482} textAnchor="middle" fill="var(--text-muted)" fontSize="11" fontFamily="var(--font-ui)" fontWeight="500">
          Answer
        </text>
      </svg>
    </div>
  );
}
