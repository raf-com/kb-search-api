-- ============================================================================
-- Knowledge Base Schema Initialization
-- ============================================================================
-- This script creates all required tables for the KB search system
-- Runs automatically when PostgreSQL container starts

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For full-text search optimization

-- ============================================================================
-- Documents Table (Source of Truth)
-- ============================================================================
CREATE TABLE IF NOT EXISTS kb_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title VARCHAR(255) NOT NULL,
  content TEXT NOT NULL,
  summary VARCHAR(500),
  source VARCHAR(512) NOT NULL UNIQUE,  -- filepath or system name
  owner VARCHAR(128) NOT NULL,          -- team name
  classification VARCHAR(32) NOT NULL,  -- public, internal, confidential
  status VARCHAR(32) DEFAULT 'active',  -- active, archived, deprecated
  created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by VARCHAR(128),
  updated_by VARCHAR(128),
  content_hash VARCHAR(64),              -- for change detection
  external_id VARCHAR(256),              -- for alert linking
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- Topics (Many-to-Many)
-- ============================================================================
CREATE TABLE IF NOT EXISTS kb_topics (
  id SERIAL PRIMARY KEY,
  document_id UUID NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
  topic VARCHAR(128) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- Indexing Status Tracking
-- ============================================================================
CREATE TABLE IF NOT EXISTS kb_indexing_status (
  id SERIAL PRIMARY KEY,
  document_id UUID NOT NULL UNIQUE REFERENCES kb_documents(id) ON DELETE CASCADE,
  meilisearch_indexed BOOLEAN DEFAULT FALSE,
  meilisearch_indexed_at TIMESTAMPTZ,
  qdrant_indexed BOOLEAN DEFAULT FALSE,
  qdrant_indexed_at TIMESTAMPTZ,
  embedding_token_count INTEGER,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- Audit Log (Change Tracking)
-- ============================================================================
CREATE TABLE IF NOT EXISTS kb_audit_log (
  id SERIAL PRIMARY KEY,
  document_id UUID REFERENCES kb_documents(id) ON DELETE CASCADE,
  action VARCHAR(32) NOT NULL,  -- created, updated, deleted, indexed
  actor VARCHAR(128) NOT NULL,
  changes JSONB,                 -- what changed
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- Indexes for Performance
-- ============================================================================

-- Document indexes
CREATE INDEX IF NOT EXISTS idx_kb_documents_owner ON kb_documents(owner);
CREATE INDEX IF NOT EXISTS idx_kb_documents_classification ON kb_documents(classification);
CREATE INDEX IF NOT EXISTS idx_kb_documents_status ON kb_documents(status);
CREATE INDEX IF NOT EXISTS idx_kb_documents_created_date ON kb_documents(created_date DESC);
CREATE INDEX IF NOT EXISTS idx_kb_documents_external_id ON kb_documents(external_id);
CREATE INDEX IF NOT EXISTS idx_kb_documents_source ON kb_documents(source);

-- Full-text search optimization
CREATE INDEX IF NOT EXISTS idx_kb_documents_content_gin ON kb_documents USING gin(to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_kb_documents_title_gin ON kb_documents USING gin(to_tsvector('english', title));

-- Topics indexes
CREATE INDEX IF NOT EXISTS idx_kb_topics_document_id ON kb_topics(document_id);
CREATE INDEX IF NOT EXISTS idx_kb_topics_topic ON kb_topics(topic);

-- Indexing status indexes
CREATE INDEX IF NOT EXISTS idx_kb_indexing_status_document_id ON kb_indexing_status(document_id);
CREATE INDEX IF NOT EXISTS idx_kb_indexing_status_meilisearch ON kb_indexing_status(meilisearch_indexed);
CREATE INDEX IF NOT EXISTS idx_kb_indexing_status_qdrant ON kb_indexing_status(qdrant_indexed);

-- Audit log indexes
CREATE INDEX IF NOT EXISTS idx_kb_audit_log_document_id ON kb_audit_log(document_id);
CREATE INDEX IF NOT EXISTS idx_kb_audit_log_action ON kb_audit_log(action);
CREATE INDEX IF NOT EXISTS idx_kb_audit_log_actor ON kb_audit_log(actor);
CREATE INDEX IF NOT EXISTS idx_kb_audit_log_created_at ON kb_audit_log(created_at DESC);

-- ============================================================================
-- Functions for Automatic Updates
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for documents
DROP TRIGGER IF EXISTS trigger_update_kb_documents_updated_at ON kb_documents;
CREATE TRIGGER trigger_update_kb_documents_updated_at
  BEFORE UPDATE ON kb_documents
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- Trigger for indexing status
DROP TRIGGER IF EXISTS trigger_update_kb_indexing_status_updated_at ON kb_indexing_status;
CREATE TRIGGER trigger_update_kb_indexing_status_updated_at
  BEFORE UPDATE ON kb_indexing_status
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- Sample Data (Optional - Comment out for production)
-- ============================================================================

-- Insert sample document if no documents exist
INSERT INTO kb_documents (
  title, content, summary, source, owner, classification, status, created_by, updated_by
)
SELECT
  'Getting Started with the Knowledge Base API',
  'This is a sample document demonstrating the KB search system. It contains information about how to use the API endpoints and search functionality.',
  'Quick start guide for the Knowledge Base API',
  '/docs/getting-started.md',
  'documentation',
  'public',
  'active',
  'system',
  'system'
WHERE NOT EXISTS (SELECT 1 FROM kb_documents LIMIT 1);

-- ============================================================================
-- Views for Common Queries
-- ============================================================================

-- View for documents with topic counts
CREATE OR REPLACE VIEW v_documents_with_topics AS
SELECT
  d.id,
  d.title,
  d.source,
  d.owner,
  d.classification,
  d.status,
  d.created_date,
  d.updated_date,
  COUNT(t.id) as topic_count,
  ARRAY_AGG(DISTINCT t.topic) FILTER (WHERE t.topic IS NOT NULL) as topics
FROM kb_documents d
LEFT JOIN kb_topics t ON d.id = t.document_id
GROUP BY d.id, d.title, d.source, d.owner, d.classification, d.status, d.created_date, d.updated_date;

-- View for indexing status summary
CREATE OR REPLACE VIEW v_indexing_summary AS
SELECT
  COUNT(*) as total_documents,
  COUNT(CASE WHEN meilisearch_indexed THEN 1 END) as meilisearch_indexed_count,
  COUNT(CASE WHEN qdrant_indexed THEN 1 END) as qdrant_indexed_count,
  COUNT(CASE WHEN error_message IS NOT NULL THEN 1 END) as error_count
FROM kb_indexing_status;
