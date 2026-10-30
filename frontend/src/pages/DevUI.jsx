/**
 * src/pages/DevUI.jsx
 * Dev-only route: /dev/ui
 * Renders every UI primitive in every state.
 */

import { useState } from 'react';
import { FileText, Trash2, Search, Plus } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Input, PasswordInput, Select, Textarea } from '../components/ui/Input';
import { Card, CardHeader, CardBody, CardFooter } from '../components/ui/Card';
import { Badge, StatusBadge } from '../components/ui/Badge';
import { Tabs } from '../components/ui/Tabs';
import { Tooltip } from '../components/ui/Tooltip';
import { Skeleton, SkeletonText } from '../components/ui/Skeleton';
import { EmptyState } from '../components/ui/EmptyState';
import { Kbd } from '../components/ui/Kbd';
import { Modal } from '../components/ui/Modal';

const Section = ({ title, children }) => (
  <section style={{ marginBottom: '48px' }}>
    <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: '20px', marginBottom: '20px', color: 'var(--text-primary)', borderBottom: '1px solid var(--border)', paddingBottom: '10px' }}>
      {title}
    </h2>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'flex-start' }}>
      {children}
    </div>
  </section>
);

export default function DevUI() {
  const [activeTab, setActiveTab] = useState('a');
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <div style={{ padding: '40px', maxWidth: '1000px', margin: '0 auto' }}>
      <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: '32px', marginBottom: '8px', background: 'linear-gradient(135deg, var(--accent), var(--accent-2))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
        UI Primitives
      </h1>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '40px', fontSize: '14px' }}>
        Design system playground — all tokens, components, and states.
      </p>

      <Section title="Typography">
        <div style={{ width: '100%' }}>
          <p style={{ fontFamily: 'var(--font-heading)', fontSize: '28px', color: 'var(--text-primary)' }}>Space Grotesk — Heading</p>
          <p style={{ fontFamily: 'var(--font-ui)', fontSize: '16px', color: 'var(--text-primary)', marginTop: '8px' }}>Inter Variable — Body text at 16px</p>
          <p style={{ fontFamily: 'var(--font-ui)', fontSize: '14px', color: 'var(--text-secondary)', marginTop: '4px' }}>Inter Variable — Secondary text at 14px</p>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '14px', color: 'var(--accent)', marginTop: '8px' }}>JetBrains Mono — 1234567890 — IDs and metrics</p>
        </div>
      </Section>

      <Section title="Color Tokens">
        {[
          { name: '--bg-base', val: '#0B0F1A' },
          { name: '--bg-panel', val: '#111726' },
          { name: '--bg-elevated', val: '#172033' },
          { name: '--border', val: '#1F2A44' },
          { name: '--text-primary', val: '#E6EAF5' },
          { name: '--text-secondary', val: '#8A94AD' },
          { name: '--accent', val: '#2DE2A6' },
          { name: '--accent-2', val: '#7C6CF0' },
          { name: '--warn', val: '#FFB547' },
          { name: '--danger', val: '#FF5C7A' },
          { name: '--info', val: '#4CC9F0' },
        ].map(c => (
          <div key={c.name} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px', width: '80px' }}>
            <div style={{ width: '60px', height: '60px', background: `var(${c.name})`, borderRadius: '10px', border: '1px solid var(--border)' }} />
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textAlign: 'center', wordBreak: 'break-all' }}>{c.name}</span>
          </div>
        ))}
      </Section>

      <Section title="Buttons">
        <Button variant="primary">Primary</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="danger">Danger</Button>
        <Button variant="primary" loading>Loading</Button>
        <Button variant="primary" disabled>Disabled</Button>
        <Button variant="primary" size="sm">Small</Button>
        <Button variant="primary" size="lg">Large</Button>
        <Button variant="secondary" icon={<Search size={14} />}>With Icon</Button>
        <Button variant="ghost" iconOnly icon={<Plus size={16} />} aria-label="Add">Add</Button>
        <Button variant="danger" iconOnly icon={<Trash2 size={14} />} aria-label="Delete">Delete</Button>
      </Section>

      <Section title="Inputs">
        <div style={{ width: '260px' }}>
          <Input label="Username" placeholder="your_username" />
        </div>
        <div style={{ width: '260px' }}>
          <Input label="With Error" placeholder="..." error="This field is required" />
        </div>
        <div style={{ width: '260px' }}>
          <PasswordInput label="Password" placeholder="••••••••" hint="Minimum 8 characters" />
        </div>
        <div style={{ width: '260px' }}>
          <Select label="Model">
            <option>Groq — Qwen</option>
            <option>OpenRouter — Nemotron</option>
          </Select>
        </div>
        <div style={{ width: '320px' }}>
          <Textarea label="Query" placeholder="Ask anything…" rows={3} />
        </div>
      </Section>

      <Section title="Badges">
        <Badge variant="success">Success</Badge>
        <Badge variant="warn">Warning</Badge>
        <Badge variant="danger">Danger</Badge>
        <Badge variant="info">Info</Badge>
        <Badge variant="neutral">Neutral</Badge>
        <Badge variant="accent2">Accent 2</Badge>
        <Badge variant="success" dot>With Dot</Badge>
        <StatusBadge status="pending" />
        <StatusBadge status="processing" />
        <StatusBadge status="completed" />
        <StatusBadge status="failed" />
      </Section>

      <Section title="Tabs">
        <Tabs
          tabs={[
            { value: 'a', label: 'Sources', count: 4 },
            { value: 'b', label: 'Tables' },
            { value: 'c', label: 'Images', count: 2 },
            { value: 'd', label: 'Trace' },
          ]}
          active={activeTab}
          onChange={setActiveTab}
        />
      </Section>

      <Section title="Card / Panel">
        <Card style={{ width: '280px' }}>
          <CardHeader>
            <span style={{ fontWeight: 600, fontSize: '14px' }}>Card Title</span>
            <Badge variant="success">Live</Badge>
          </CardHeader>
          <CardBody>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Card body content goes here. This is the main content area.</p>
          </CardBody>
          <CardFooter>
            <Button variant="ghost" size="sm">Cancel</Button>
            <Button variant="primary" size="sm">Save</Button>
          </CardFooter>
        </Card>
        <Card hover style={{ width: '200px' }}>
          <CardBody>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Hover card — lifts on hover.</p>
          </CardBody>
        </Card>
      </Section>

      <Section title="Tooltip">
        <Tooltip content="Documents page" placement="top">
          <Button variant="secondary" icon={<FileText size={14} />}>Hover me (top)</Button>
        </Tooltip>
        <Tooltip content="Right side tooltip" placement="right">
          <Button variant="secondary">Hover me (right)</Button>
        </Tooltip>
      </Section>

      <Section title="Skeleton">
        <div style={{ width: '300px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <Skeleton width="100%" height="60px" />
          <Skeleton width="80%" height="16px" />
          <Skeleton width="60%" height="16px" />
          <SkeletonText lines={3} />
        </div>
      </Section>

      <Section title="Empty State">
        <div style={{ width: '400px', border: '1px solid var(--border)', borderRadius: '10px', background: 'var(--bg-panel)' }}>
          <EmptyState
            icon={<FileText size={24} />}
            title="No documents yet"
            description="Upload a file to get started with multimodal RAG processing."
            action={<Button variant="primary" size="sm">Upload Document</Button>}
          />
        </div>
      </Section>

      <Section title="Keyboard Hints">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: 'var(--text-secondary)' }}>
          Submit with <Kbd>Ctrl</Kbd>+<Kbd>Enter</Kbd>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: 'var(--text-secondary)' }}>
          Open palette <Kbd>⌘K</Kbd>
        </div>
      </Section>

      <Section title="Modal / Dialog">
        <Button variant="secondary" onClick={() => setModalOpen(true)}>Open Modal</Button>
        <Modal
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          title="Confirm Delete"
          footer={
            <>
              <Button variant="ghost" onClick={() => setModalOpen(false)}>Cancel</Button>
              <Button variant="danger" onClick={() => setModalOpen(false)}>Delete</Button>
            </>
          }
        >
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: 1.6 }}>
            Are you sure you want to delete this document? All chunks and embeddings will be removed permanently.
          </p>
        </Modal>
      </Section>
    </div>
  );
}
